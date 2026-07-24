"""jui build command — build all platforms."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..core.config_manager import ConfigManager
from ..core.generated_marker import json_marker
from ..core.image_converter import ImageConverter
from ..core.impl_updater import (
    atomic_write_text,
    ensure_kotlin_import,
    ensure_kotlin_inheritance,
    ensure_swift_inheritance,
    extract_expected_labels_from_swift_sig,
    extract_swift_method_labels,
    inject_kotlin_override,
    inject_kotlin_var_override,
)
from ..core.method_extractor import ExtractionError
from ..core.platform_resolver import PlatformResolver
from ..core.protocol_sync import (
    collect_protocol_members,
    list_impl_method_names,
    list_impl_var_names,
)
from ..core.spec_extractor import ScreenSpec, extract_screen_spec
from ..core.spec_validator import (
    SpecValidationError,
    emit_warnings,
    validate_screen_spec,
)


def register_build_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the build subcommand."""
    build_parser = subparsers.add_parser("build", aliases=["b"], help="Build all platforms")
    build_parser.add_argument("--clean", action="store_true", help="Clean build (regenerate all)")
    build_parser.add_argument("--ios-only", action="store_true", help="Build iOS only")
    build_parser.add_argument("--android-only", action="store_true", help="Build Android only")
    build_parser.add_argument("--web-only", action="store_true", help="Build Web only")



def cmd_build(args: argparse.Namespace) -> int:
    """Execute jui build."""
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    config = config_mgr.load()
    platforms = config.get("platforms", {})
    clean = ["--clean"] if args.clean else []
    failed = []

    # Distribute shared assets to each platform before build
    _distribute_layouts(config_mgr, platforms, args)
    _distribute_styles(config_mgr, platforms, args)
    _distribute_resources(config_mgr, platforms, args)
    _distribute_images(config_mgr, config, platforms, args)
    _distribute_hotload_config(config_mgr, platforms, args)

    # Sync swagger-derived DTO + Domain scaffold files. Halts on §3.3
    # invariants (oneOf, multi-file $ref, direct self-ref, etc.) so the
    # downstream platform builds never see a broken model.
    if _sync_api_models(config_mgr, platforms, args) is False:
        return 1

    # Converter scaffolding is an explicit, one-time author action — run
    # `jui g converter --from <spec>` (or `--all --skip-existing`) yourself
    # when you add or change a `docs/components/json/*.component.json`. We
    # used to auto-run that here, but it surprised users (every build
    # touched extension/ directories) and blocked non-interactive callers
    # (MCP, CI) on the downstream generators that still prompt. See
    # `docs/bugs/reports/2026-04-23-jui-build-auto-converter-removed.md`.

    # Sync ViewModel Protocol / Base files from spec.event_handlers + Impl
    # markers. Hard error if any spec-declared handler has no matching Impl
    # function — catches drift before the platform build starts.
    if _sync_viewmodel_protocols(config_mgr, config, platforms, args) is False:
        return 1

    # Hard gate for navigationMode:"isolated" — the embedded screen's spec
    # must not declare present-type transitions (sheet/modal/dialog/dismiss).
    if _check_isolated_embed_constraints(config_mgr) is False:
        return 1

    should_build_ios = "ios" in platforms and not args.android_only and not args.web_only
    should_build_android = "android" in platforms and not args.ios_only and not args.web_only
    should_build_web = "web" in platforms and not args.ios_only and not args.android_only

    if should_build_ios:
        ios_root = config_mgr.project_root / platforms["ios"]["root"]
        print(f"\n--- Building iOS ({ios_root}) ---")
        if not _run_tool(["sjui", "build"] + clean, ios_root):
            failed.append("ios")

    if should_build_android:
        android_root = config_mgr.project_root / platforms["android"]["root"]
        print(f"\n--- Building Android ({android_root}) ---")
        if not _run_tool(["kjui", "build"] + clean, android_root):
            failed.append("android")

    if should_build_web:
        web_root = config_mgr.project_root / platforms["web"]["root"]
        print(f"\n--- Building Web ({web_root}) ---")
        if not _run_tool(["rjui", "build"] + clean, web_root):
            failed.append("web")

    if failed:
        print(f"\nERROR: Build failed for: {', '.join(failed)}")
        return 1

    print("\nBuild completed successfully!")
    return 0


def _run_tool(cmd: list[str], cwd: Path) -> bool:
    """Run a platform tool, handling missing executables gracefully."""
    from ..core.tool_resolver import build_tool_env, resolve_tool

    tool_name = cmd[0]
    resolved = resolve_tool(tool_name, cwd)
    actual_cmd = [resolved] + cmd[1:]
    env = build_tool_env(resolved, tool_name)

    try:
        result = subprocess.run(actual_cmd, cwd=cwd, env=env)
        return result.returncode == 0
    except FileNotFoundError:
        print(f"  WARNING: '{tool_name}' not found (searched local and PATH) — skipping")
        return False


def _prune_orphans(
    dest_dir: Path,
    valid_rel_paths: set,
    skip_prefixes: set,
) -> int:
    """Remove *.json files in *dest_dir* that are not in *valid_rel_paths*.

    Skips top-level subdirectories listed in *skip_prefixes* (e.g. Resources,
    Styles) so platform-specific resources aren't deleted.
    """
    if not dest_dir.exists():
        return 0
    removed = 0
    for dest_file in dest_dir.rglob("*.json"):
        rel = dest_file.relative_to(dest_dir)
        if rel.parts[0] in skip_prefixes:
            continue
        if rel not in valid_rel_paths:
            dest_file.unlink()
            removed += 1
    # Clean up empty directories
    for subdir in sorted(dest_dir.rglob("*"), reverse=True):
        if subdir.is_dir() and subdir != dest_dir and not any(subdir.iterdir()):
            try:
                subdir.rmdir()
            except OSError:
                pass
    return removed


def _normalize_layouts_enabled(config_mgr: ConfigManager) -> bool:
    """``jui.config.json`` → ``"build": {"normalizeLayouts": ...}``.

    Default is TRUE (L1-canonicalized distribution) since renderer SSoT
    phase 14: verified against a real consumer (byte-identical generated
    code, intended layout diffs only) and the conformance suite (L0 vs L1
    status-identical). ``"normalizeLayouts": false`` is the escape hatch
    for byte-identical-to-legacy distribution.
    """
    config = config_mgr.load()
    build_cfg = config.get("build") or {}
    if isinstance(build_cfg, dict) and "normalizeLayouts" in build_cfg:
        return bool(build_cfg.get("normalizeLayouts"))
    return True


def _distribute_layouts(config_mgr: ConfigManager, platforms: dict, args) -> None:
    """Copy Layout JSON from shared layouts/ to each platform.

    If a Layout file contains ``platform`` overrides they are resolved
    for the target platform before writing.

    When normalizeLayouts is enabled (default since SSoT phase 14; set
    ``"build": {"normalizeLayouts": false}`` in ``jui.config.json`` to opt out), the distributed copies are L1-canonicalized
    (alias → canonical attribute rewrite + ``$jui`` marker). The shared
    source files under ``layouts_directory`` are NEVER rewritten — the
    authoring surface stays L0.
    """
    layouts_src = config_mgr.layouts_directory
    if not layouts_src.exists():
        return

    canonicalizer = None
    if _normalize_layouts_enabled(config_mgr):
        # Lazy import — the normalizer is never loaded on flag-off builds.
        from ..core.normalizer import Canonicalizer
        from ..core.normalizer.alias_table import AliasTable

        alias_table = AliasTable.from_file()
        if alias_table.is_empty():
            # Stamping L1 markers WITHOUT alias rewriting corrupts
            # consumers on the canonical-only path (they skip alias
            # fallbacks trusting the marker) — refuse to normalize.
            print(
                "  WARNING [normalize]: attribute_definitions.json not "
                "found near the installed jui_tools — distributing RAW "
                "(L0) layouts instead of a marker-only pass"
            )
        else:
            canonicalizer = Canonicalizer(alias_table)
            print(
                "normalizeLayouts enabled: distributing "
                "L1-canonicalized layouts"
            )

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue

        layouts_rel = pconfig.get("layoutsDir")
        if not layouts_rel:
            continue

        dest_dir = config_mgr.project_root / pconfig["root"] / layouts_rel
        resolver = PlatformResolver(platform)
        count = 0

        # Determine which subdirectories to skip (handled separately)
        styles_src = config_mgr.styles_directory
        skip_prefixes = {"Resources"}
        if styles_src.exists() and layouts_src in styles_src.parents:
            skip_prefixes.add(styles_src.relative_to(layouts_src).parts[0])

        shared_rel_paths: set[Path] = set()
        for src_file in sorted(layouts_src.rglob("*.json")):
            rel = src_file.relative_to(layouts_src)
            if rel.parts[0] in skip_prefixes:
                continue

            data = json.loads(src_file.read_text())

            # Respect platforms whitelist on the layout root (e.g.
            # "platforms": ["ios"] limits this file to iOS only).
            allowed_platforms = data.get("platforms") if isinstance(data, dict) else None
            if isinstance(allowed_platforms, list) and platform not in allowed_platforms:
                continue

            shared_rel_paths.add(rel)

            # Strip platforms metadata from the output — it's a build directive,
            # not a runtime attribute.
            if isinstance(data, dict) and "platforms" in data:
                data = {k: v for k, v in data.items() if k != "platforms"}

            # Resolve platform-specific overrides
            if PlatformResolver.has_platform_key(data):
                data = resolver.resolve_tree(data)

            # L1 canonicalization (opt-in). Applies only to the
            # distributed platform-side copy; ``layouts_src`` is L0.
            if canonicalizer is not None and isinstance(data, dict):
                data, norm_warnings = canonicalizer.canonicalize(
                    data, source=rel.as_posix()
                )
                for warning in norm_warnings:
                    print(f"  WARNING [normalize]: {warning}")

            # Inject the @generated marker *at distribution time* — the
            # per-platform copy is the truly auto-generated artifact (the
            # shared source in layouts_directory is user-editable).
            if isinstance(data, dict):
                data.pop("_generated", None)  # drop any leftover from older builds
                marker_source = f"{config_mgr.layouts_directory.name}/{rel.as_posix()}"
                data = {
                    "_generated": json_marker(
                        source=marker_source,
                        generator="jui build",
                    ),
                    **data,
                }

            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            count += 1

        # Remove platform-side layouts that no longer exist in shared layouts.
        # Only preserve Resources/ (platform-generated files like colors.json);
        # Styles/ under Layouts/ is legacy placement — safe to prune.
        prune_skip = {"Resources"}
        removed = _prune_orphans(dest_dir, shared_rel_paths, prune_skip)

        print(f"Distributed {count} layout(s) → {platform}" + (f" (removed {removed} orphan(s))" if removed else ""))


def _distribute_styles(config_mgr: ConfigManager, platforms: dict, args) -> None:
    """Copy Styles/ to each platform at the same level as Layouts/."""
    styles_src = config_mgr.styles_directory
    if not styles_src.exists():
        return

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue

        layouts_rel = pconfig.get("layoutsDir")
        if not layouts_rel:
            continue

        # Styles/ sits alongside Layouts/, not inside it
        layouts_dest = config_mgr.project_root / pconfig["root"] / layouts_rel
        styles_dest = layouts_dest.parent / "Styles"
        count = 0

        shared_rel_paths: set[Path] = set()
        for src_file in sorted(styles_src.rglob("*.json")):
            rel = src_file.relative_to(styles_src)
            shared_rel_paths.add(rel)
            dest = styles_dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            count += 1

        removed = _prune_orphans(styles_dest, shared_rel_paths, set())

        if count or removed:
            suffix = f" (removed {removed} orphan(s))" if removed else ""
            print(f"Distributed {count} style(s) → {platform}{suffix}")


def _distribute_resources(config_mgr: ConfigManager, platforms: dict, args) -> None:
    """Copy Resources/ (strings, colors, etc.) into each platform's Layouts/Resources/."""
    # Resources live inside layouts_directory/Resources/
    resources_src = config_mgr.layouts_directory / "Resources"

    # Also copy strings_file if configured separately
    strings_src = config_mgr.strings_file

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue

        layouts_rel = pconfig.get("layoutsDir")
        if not layouts_rel:
            continue

        resources_dest = config_mgr.project_root / pconfig["root"] / layouts_rel / "Resources"
        count = 0

        # Copy all files from shared Resources/
        if resources_src.exists():
            for src_file in sorted(resources_src.rglob("*")):
                if src_file.is_dir():
                    continue
                rel = src_file.relative_to(resources_src)
                dest = resources_dest / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest)
                count += 1

        # Copy strings_file if it's configured separately (not inside Resources/)
        if strings_src and strings_src.exists():
            if not resources_src.exists() or resources_src not in strings_src.parents:
                dest = resources_dest / "strings.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(strings_src, dest)
                count += 1

        if count:
            print(f"Distributed {count} resource(s) → {platform}")


_NSC_BEGIN = "<!-- BEGIN kjui hotload IPs (managed by jui build — do not edit) -->"
_NSC_END = "<!-- END kjui hotload IPs -->"


def _android_hotload_ips(client_ip: str) -> list[str]:
    """IPs that need cleartext permission for kjui hotload.

    Always includes the emulator loopback (10.0.2.2) and local loopbacks;
    adds the dev-machine LAN IP when it's a real non-loopback address.
    """
    base = ["10.0.2.2", "localhost", "127.0.0.1"]
    if client_ip and client_ip not in base and client_ip not in ("0.0.0.0", ""):
        base.append(client_ip)
    return base


def _render_nsc_managed_block(ips: list[str], indent: str = "        ") -> str:
    lines = [indent + _NSC_BEGIN]
    for ip in ips:
        lines.append(f'{indent}<domain includeSubdomains="true">{ip}</domain>')
    lines.append(indent + _NSC_END)
    return "\n".join(lines)


def _extract_user_domains_outside_markers(content: str) -> set[str]:
    """Return `<domain>` text values that live outside the kjui managed
    block. Used to avoid duplicate entries that would crash Android's NSC
    parser (``10.0.2.2 has already been specified``).
    """
    import re

    stripped = re.sub(
        re.escape(_NSC_BEGIN) + r".*?" + re.escape(_NSC_END),
        "",
        content,
        flags=re.DOTALL,
    )
    values = re.findall(r"<domain[^>]*>([^<]+)</domain>", stripped)
    return {v.strip() for v in values if v.strip()}


def _filter_managed_ips(ips: list[str], user_domains: set[str]) -> list[str]:
    """Drop any managed IPs the user already declared outside the block.

    Empty result is allowed — the managed block still carries BEGIN/END
    markers so subsequent builds can locate it, but emits no `<domain>`
    entries when the user has them all.
    """
    return [ip for ip in ips if ip not in user_domains]


def _fresh_nsc_xml(ips: list[str]) -> str:
    block = _render_nsc_managed_block(ips, indent="        ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<network-security-config>\n'
        '    <!-- Allow cleartext traffic for hot reload development server -->\n'
        '    <domain-config cleartextTrafficPermitted="true">\n'
        f"{block}\n"
        '    </domain-config>\n'
        '\n'
        '    <!-- Default configuration for production -->\n'
        '    <base-config cleartextTrafficPermitted="false">\n'
        '        <trust-anchors>\n'
        '            <certificates src="system" />\n'
        '        </trust-anchors>\n'
        '    </base-config>\n'
        '</network-security-config>\n'
    )


def _resolve_android_debug_res_xml(platform_root: Path) -> Path:
    """Resolve the Android debug-variant ``res/xml`` directory for the
    given platform root, honoring Gradle module layout.

    Mirrors ``compose_setup.rb``:
        source_dir = kjui.config.json ``source_directory`` (default ``src/main``)
        debug_dir  = source_dir.replace('/main', '/debug', 1)
        target     = platform_root / debug_dir / 'res' / 'xml'

    Examples:
        source_directory = "app/src/main" → platform_root / "app/src/debug/res/xml"
        source_directory = "src/main"     → platform_root / "src/debug/res/xml"
    """
    source_dir = "src/main"
    kjui_config = platform_root / "kjui.config.json"
    if kjui_config.exists():
        try:
            with open(kjui_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg_source = data.get("source_directory")
            if cfg_source:
                source_dir = cfg_source
        except (OSError, json.JSONDecodeError):
            pass
    debug_dir = source_dir.replace("/main", "/debug", 1)
    return platform_root / debug_dir / "res" / "xml"


def _sync_android_network_security(platform_root: Path, client_ip: str) -> None:
    """Sync the kjui-managed cleartext domain list into the Android debug
    variant's ``network_security_config.xml``.

    Strategy (matches bug kjui-hotload-android-cleartext-sync, C 案):

    - If the file exists and contains the managed-block markers, rewrite
      only the content between them.
    - If the file exists but has no markers, insert a managed block at
      the top of the first ``<domain-config cleartextTrafficPermitted="true">``
      (creating one if absent). User-added ``<domain>`` entries elsewhere
      are preserved.
    - If the file does not exist, create it from the scaffold template.

    Target path: ``<platform_root>/<source_dir with main→debug>/res/xml/network_security_config.xml``
    (resolved from kjui.config.json ``source_directory``; defaults to
    ``src/main`` when the file is missing, matching compose_setup.rb).
    """
    import re

    target = _resolve_android_debug_res_xml(platform_root) / "network_security_config.xml"
    ips = _android_hotload_ips(client_ip)

    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_fresh_nsc_xml(ips), encoding="utf-8")
        print(f"Created Android network_security_config.xml with kjui managed block "
              f"({target.relative_to(platform_root)})")
        return

    content = target.read_text(encoding="utf-8")
    user_domains = _extract_user_domains_outside_markers(content)
    managed_ips = _filter_managed_ips(ips, user_domains)
    dropped = [ip for ip in ips if ip in user_domains]

    # Case 1: markers exist → rewrite between them (preserve surrounding indent)
    if _NSC_BEGIN in content and _NSC_END in content:
        pattern = re.compile(
            r"([ \t]*)" + re.escape(_NSC_BEGIN) + r".*?" + re.escape(_NSC_END),
            re.DOTALL,
        )
        match = pattern.search(content)
        if match:
            indent = match.group(1)
            new_block = _render_nsc_managed_block(managed_ips, indent=indent)
            new_content = pattern.sub(lambda _: new_block, content, count=1)
            if new_content != content:
                target.write_text(new_content, encoding="utf-8")
                if managed_ips:
                    print(f"Synced Android network_security_config.xml managed block "
                          f"(IPs: {', '.join(managed_ips)})")
                else:
                    print("Synced Android network_security_config.xml managed block "
                          "(empty — user already declares all hotload IPs)")
                if dropped:
                    print(f"  Skipped {', '.join(dropped)} — already present outside managed block")
            return

    # Case 2: no markers → inject into cleartext domain-config (creating one if absent)
    cleartext_open_re = re.compile(
        r"(<domain-config[^>]*cleartextTrafficPermitted\s*=\s*\"true\"[^>]*>)",
        re.IGNORECASE,
    )
    open_match = cleartext_open_re.search(content)
    if open_match:
        insertion_indent = "        "
        block = "\n" + _render_nsc_managed_block(managed_ips, indent=insertion_indent)
        new_content = (
            content[: open_match.end()] + block + content[open_match.end():]
        )
        target.write_text(new_content, encoding="utf-8")
        if managed_ips:
            print(f"Injected kjui managed block into {target.relative_to(platform_root)} "
                  f"(IPs: {', '.join(managed_ips)})")
        else:
            print(f"Injected empty kjui managed block into {target.relative_to(platform_root)} "
                  "(user already declares all hotload IPs)")
        if dropped:
            print(f"  Skipped {', '.join(dropped)} — already present outside managed block")
        return

    # Case 3: no cleartext domain-config at all — create one before </network-security-config>
    closing_re = re.compile(r"</network-security-config>", re.IGNORECASE)
    close_match = closing_re.search(content)
    if close_match:
        block = _render_nsc_managed_block(managed_ips, indent="        ")
        insertion = (
            "    <!-- Allow cleartext traffic for hot reload development server -->\n"
            "    <domain-config cleartextTrafficPermitted=\"true\">\n"
            f"{block}\n"
            "    </domain-config>\n\n"
        )
        new_content = content[: close_match.start()] + insertion + content[close_match.start():]
        target.write_text(new_content, encoding="utf-8")
        if managed_ips:
            print(f"Added cleartext domain-config + kjui managed block to "
                  f"{target.relative_to(platform_root)} (IPs: {', '.join(managed_ips)})")
        else:
            print(f"Added cleartext domain-config + empty kjui managed block to "
                  f"{target.relative_to(platform_root)} (user already declares all hotload IPs)")
        if dropped:
            print(f"  Skipped {', '.join(dropped)} — already present outside managed block")
        return

    # Malformed file — leave it alone but tell the user
    print(f"WARNING: {target} has no </network-security-config> — skipping hotload IP sync. "
          f"Add <domain> entries for {', '.join(ips)} manually.")


def _resolve_hotload_client_ip(config_path: Path) -> str:
    """Read client.ip from the just-distributed hotload config, falling
    back to the dev-machine's detected LAN IP when empty."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    ip = (raw.get("client") or {}).get("ip") or ""
    if ip:
        return ip
    from ..hotloader.config_loader import _detect_local_ip
    return _detect_local_ip()


def _distribute_hotload_config(
    config_mgr: ConfigManager, platforms: dict, args
) -> None:
    """Copy ``docs/hotload/config.json`` into each platform's runtime
    bundle location as ``hotloader.json``.

    - iOS: ``<platform_root>/<layoutsDir>/Resources/hotloader.json`` —
      lands inside the app bundle since SwiftJsonUI treats the
      ``Layouts/Resources`` tree as a bundle resource.
    - Android: ``<platform_root>/<layoutsDir>/../hotloader.json`` —
      the assets root (typically ``src/main/assets/``) so
      KotlinJsonUI's ``HotLoaderConfigReader`` can load it via
      ``AssetManager.open``.
    - Web is not a hotload target; skipped.

    Auto-generates ``docs/hotload/config.json`` with defaults when the
    project doesn't have one yet — this matches what
    ``docs/hotload/README.md`` and consumer-side migration plans promise
    ("auto-generated if missing"). Skipping auto-generate when no
    iOS/Android platforms are configured (web-only project).
    """
    has_native = any(
        platform in ("ios", "android")
        and not (platform == "ios" and args.android_only)
        and not (platform == "android" and args.ios_only)
        and not args.web_only
        for platform in platforms
    )
    src = config_mgr.project_root / "docs" / "hotload" / "config.json"
    if not src.exists():
        if not has_native:
            return
        # Lazy import so build doesn't require aiohttp/watchdog just to write
        # the file — config_loader.write_default_config only touches the JSON.
        from ..hotloader.config_loader import write_default_config
        src = write_default_config(config_mgr.project_root)
        print(f"Created hotload config: {src.relative_to(config_mgr.project_root)}")

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue
        if platform == "web":
            # web uses HMR, no hotload config needed
            continue

        layouts_rel = pconfig.get("layoutsDir")
        if not layouts_rel:
            continue

        platform_root = config_mgr.project_root / pconfig["root"]
        if platform == "ios":
            dest = platform_root / layouts_rel / "Resources" / "hotloader.json"
        else:  # android
            # layoutsDir points at "src/main/assets/Layouts"; assets root
            # is its parent, and hotloader.json sits there so it loads
            # via AssetManager.open("hotloader.json").
            dest = platform_root / layouts_rel / ".." / "hotloader.json"
            dest = dest.resolve()

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"Distributed hotload config → {platform}")

        if platform == "android":
            client_ip = _resolve_hotload_client_ip(src)
            _sync_android_network_security(platform_root, client_ip)


def _sync_api_models(
    config_mgr: ConfigManager,
    platforms: dict,
    args,
) -> bool:
    """Emit swagger-derived DTO + Domain scaffold for each enabled platform.

    Returns True on success / no-op (no swagger files), False on a fatal
    schema error (callers should abort the build).

    Per platform behavior:

    - iOS: full implementation in Phase 1 — DTOs are regenerated, Domain
      scaffolds emitted only when absent, orphan DTOs pruned.
    - Android / Web: planners arrive in Phase 2 / 3 — until then they are
      silently skipped (no warning) so consumers can adopt the iOS portion
      first.
    """
    from ..core.api_model_sync import (
        apply_plan,
        collect_docs,
        has_planner,
        plan_for,
        planners_for,
    )
    from ..core.openapi_loader import OpenAPILoadError

    try:
        docs = collect_docs(config_mgr)
    except OpenAPILoadError as e:
        print(f"\nERROR [api-model]: {e}")
        return False

    if not docs:
        return True

    # Report filter activity (v2 plan §2.5). Aggregated across all docs;
    # in practice consumers have one swagger file, so the per-doc breakdown
    # is overkill.
    filtered_out = sorted({n for doc in docs for n in doc.filtered_out})
    if filtered_out:
        preview = ", ".join(filtered_out[:8])
        more = f", ... (+{len(filtered_out) - 8} more)" if len(filtered_out) > 8 else ""
        print(
            f"[api-codegen] filtered out {len(filtered_out)} schema(s) not "
            f"reachable from configured paths/schemas: {preview}{more}"
        )

    selected_platforms = planners_for(args)
    total_dto = 0
    total_scaffold = 0
    total_pruned = 0

    for platform in selected_platforms:
        if platform not in platforms:
            continue
        if not has_planner(platform):
            continue  # Phase 2 / 3 placeholder
        pconfig = platforms[platform]
        try:
            plan = plan_for(platform, config_mgr, pconfig, docs)
        except OpenAPILoadError as e:
            print(f"\nERROR [api-model:{platform}]: {e}")
            return False
        dto_written, scaffold_written, pruned = apply_plan(plan, prune_orphans=True)
        total_dto += dto_written
        total_scaffold += scaffold_written
        total_pruned += pruned

    if total_dto or total_scaffold or total_pruned:
        suffix_parts = []
        if total_dto:
            suffix_parts.append(f"{total_dto} DTO file(s)")
        if total_scaffold:
            suffix_parts.append(f"{total_scaffold} new domain scaffold(s)")
        if total_pruned:
            suffix_parts.append(f"pruned {total_pruned} orphan(s)")
        print("API model sync: " + ", ".join(suffix_parts))

    return True


def _load_all_specs(config_mgr: ConfigManager) -> list[tuple[Path, ScreenSpec]]:
    """Load every ``*.spec.json`` under the project's spec directory.

    Applies ``ParentSpecMerger`` to parent specs and skips files referenced
    as sub-specs. Mirrors the logic in ``generate_cmd._cmd_generate_project``
    so the sync operates on the same merged specs the scaffold generation did.
    """
    from ..core.parent_spec_merger import ParentSpecMerger

    spec_dir = config_mgr.spec_directory
    if not spec_dir.exists():
        return []
    spec_files = sorted(spec_dir.glob("*.spec.json"))
    if not spec_files:
        return []

    sub_spec_paths: set[Path] = set()
    for sf in spec_files:
        try:
            head = json.loads(sf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if head.get("type") != "screen_parent_spec":
            continue
        for entry in head.get("subSpecs", []) or []:
            ref = entry.get("file")
            if not ref:
                continue
            resolved = (sf.parent / ref).resolve()
            if resolved.exists():
                sub_spec_paths.add(resolved)

    merger = ParentSpecMerger(spec_dir=spec_dir)
    results: list[tuple[Path, ScreenSpec]] = []
    for sf in spec_files:
        if sf.resolve() in sub_spec_paths:
            continue
        try:
            spec_data = json.loads(sf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if spec_data.get("type") == "screen_parent_spec":
            merge_result = merger.merge_from_file(sf)
            if merge_result.has_conflicts:
                # First-write-wins is already applied by ParentSpecMerger.merge, so
                # merge_result.spec is usable. Warn so the user can investigate, but
                # don't drop the parent — its sub-specs still need ViewModelProtocol
                # sync etc. Mirrors `jui g project` behavior so the two commands
                # stay symmetric.
                print(
                    f"\nWARNING: parent_spec merge conflicts in {sf.name} "
                    f"(kept first-write-wins):"
                )
                for c in merge_result.conflicts:
                    print(f"  {c.path}: {c.message}")
            spec_data = merge_result.spec
        results.append((sf, extract_screen_spec(spec_data)))
    return results


# Transition/action vocabulary that presents OUTSIDE the embed's bounds.
# iOS sheets present on the parent window, so "a modal visually contained
# in the embed" is not implementable — parity would break, hence the hard
# error for screens hosted inside an isolated embed. Matched defensively
# against several free-form spec keys (transitions are list[dict] with no
# fixed schema).
_PRESENT_LIKE = re.compile(
    r"^(present|sheet|modal|dialog|fullscreencover|bottomsheet|dismiss)$",
    re.IGNORECASE,
)
_PRESENT_KEYS = ("type", "style", "presentation", "mode", "action")


def _walk_embed_nodes(node):
    """Yield every Embed dict inside a layout JSON tree."""
    if isinstance(node, dict):
        if node.get("type") == "Embed":
            yield node
        for value in node.values():
            yield from _walk_embed_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_embed_nodes(item)


def _spec_present_like_entries(spec: ScreenSpec) -> list[str]:
    """Describe present-type transitions declared by a spec (empty = none)."""
    found: list[str] = []
    for idx, transition in enumerate(spec.transitions or []):
        if not isinstance(transition, dict):
            continue
        for key in _PRESENT_KEYS:
            value = transition.get(key)
            if isinstance(value, str) and _PRESENT_LIKE.match(value):
                found.append(f"transitions[{idx}].{key}='{value}'")
    return found


def _check_isolated_embed_constraints(config_mgr: ConfigManager) -> bool:
    """Hard gate: screens hosted in an isolated Embed must not present.

    Scans every layout for ``Embed`` nodes with ``navigationMode:"isolated"``
    and rejects the build when the embedded screen's spec declares a
    present-type transition (sheet/modal/dialog/dismiss/...). Returns False
    on violation (build aborts), True otherwise.
    """
    layouts_dir = config_mgr.layouts_directory
    if not layouts_dir.exists():
        return True

    isolated_targets: dict[str, list[str]] = {}
    for layout_path in sorted(layouts_dir.rglob("*.json")):
        if "Resources" in layout_path.parts:
            continue
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for embed in _walk_embed_nodes(layout):
            if embed.get("navigationMode") != "isolated":
                continue
            screen = embed.get("screen")
            if isinstance(screen, str) and screen:
                isolated_targets.setdefault(screen, []).append(
                    layout_path.name
                )

    if not isolated_targets:
        return True

    def _snake_to_pascal(name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_"))

    errors: list[str] = []
    specs = _load_all_specs(config_mgr)
    for screen, host_layouts in sorted(isolated_targets.items()):
        pascal = _snake_to_pascal(screen)
        spec = next(
            (
                s
                for _sf, s in specs
                if s.name in (pascal, screen)
                or Path(s.layout_file or "").stem == screen
            ),
            None,
        )
        if spec is None:
            continue  # no spec — nothing to check (layout-only screens)
        for entry in _spec_present_like_entries(spec):
            errors.append(
                f"'{screen}' is hosted in an isolated Embed "
                f"({', '.join(sorted(set(host_layouts)))}) but its spec "
                f"declares {entry}. Present-type transitions are forbidden "
                f"inside navigationMode:\"isolated\" — iOS sheets present on "
                f"the parent window, so visual containment cannot be "
                f"guaranteed cross-platform. Use the params callback escape "
                f"hatch and present from the host screen instead."
            )

    if errors:
        print("\nERROR [embed-isolated]:")
        for line in errors:
            print(f"  - {line}")
        return False
    return True


def _format_label_sig(name: str, labels: list[tuple[str, str]]) -> str:
    """Render ``func name(label internal, _ internal, name)`` — omits types
    for a compact drift report."""
    parts = []
    for label, internal in labels:
        if label == internal:
            parts.append(f"{internal}:")
        elif label == "_":
            parts.append(f"_ {internal}:")
        else:
            parts.append(f"{label} {internal}:")
    return f"func {name}({', '.join(parts)})"


def _vm_subdir_for(spec: ScreenSpec) -> str:
    if spec.layout_file and "/" in spec.layout_file:
        return "/".join(spec.layout_file.split("/")[:-1])
    return ""


def _sync_viewmodel_protocols(
    config_mgr: ConfigManager,
    config: dict,
    platforms: dict,
    args,
) -> bool:
    """Regenerate Protocol/Base files + patch Impl inheritance/override.

    Returns True on success, False on any hard error (invalid spec,
    spec→Impl drift, marker extraction failure) — callers should abort the
    build when False.
    """
    from ..core.type_mapper import TypeMapper
    from ..generators.android_generator import AndroidGenerator
    from ..generators.ios_generator import IosGenerator
    from ..generators.web_generator import (
        WebGenerator,
        collect_layout_event_names,
        resolve_layout_path,
    )

    specs = _load_all_specs(config_mgr)
    if not specs:
        return True

    # Validate specs up front — invalid platforms values halt the build
    # before we've written anything.
    validation_failed = False
    all_warnings = []
    for _sf, spec in specs:
        try:
            all_warnings.extend(validate_screen_spec(spec))
        except SpecValidationError as e:
            print(f"\nERROR: {e}")
            validation_failed = True
    if validation_failed:
        return False
    if all_warnings:
        emit_warnings(all_warnings)

    type_mapper = TypeMapper(config_mgr.type_map_file)

    # Auto-register swagger-derived schema names so Repository/UseCase
    # signatures like ``returnType: "User"`` resolve without `jui verify`
    # warnings. Per plan §9.2 / C5, manual entries in
    # `.jsonui-type-map.json` always win — `register_schemas` skips
    # shadowed names and returns them for info-level reporting.
    try:
        from ..core.api_model_sync import collect_docs as _collect_api_docs
        api_docs = _collect_api_docs(config_mgr)
    except Exception:
        api_docs = []
    if api_docs:
        schema_names = [
            schema.name
            for doc in api_docs
            for schema in doc.schemas
        ] + [
            enum.name
            for doc in api_docs
            for enum in doc.enums
        ]
        shadowed = type_mapper.register_schemas(schema_names)
        if shadowed:
            preview = ", ".join(shadowed[:5]) + ("..." if len(shadowed) > 5 else "")
            print(
                f"  info: {len(shadowed)} swagger schema(s) shadowed by user "
                f"mapping in .jsonui-type-map.json ({preview})"
            )

    # Map platform name → (generator_factory, Impl-patch helpers)
    def _get_gen(platform: str, pconfig: dict):
        root = config_mgr.project_root / pconfig["root"]
        if platform == "ios":
            return IosGenerator(root, pconfig, type_mapper)
        if platform == "android":
            return AndroidGenerator(root, pconfig, type_mapper)
        if platform == "web":
            return WebGenerator(root, pconfig, type_mapper)
        return None

    errors: list[str] = []
    protocol_writes = 0
    impl_writes = 0

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue

        generator = _get_gen(platform, pconfig)
        if generator is None:
            continue

        for _sf, spec in specs:
            subdir = _vm_subdir_for(spec)
            impl_path = generator.viewmodel_impl_path(spec.name, subdir)
            proto_path = generator.viewmodel_protocol_path(spec.name, subdir)

            impl_source: str | None = None
            impl_method_names: set[str] | None = None
            impl_var_names: set[str] | None = None
            if impl_path.exists():
                try:
                    impl_source = impl_path.read_text(encoding="utf-8")
                except OSError as e:
                    errors.append(
                        f"[{platform}] could not read Impl {impl_path}: {e}"
                    )
                    continue
                # Web members live inside <Name>Data or the ViewModelBase
                # auto-emit — the `func`/`var` scanner doesn't understand
                # TypeScript, so skip the consistency check there.
                if platform != "web":
                    impl_method_names = list_impl_method_names(impl_source)
                    impl_var_names = list_impl_var_names(impl_source)

            sync_platform = platform
            try:
                sync_result = collect_protocol_members(
                    spec,
                    platform=sync_platform,
                    impl_source=impl_source,
                    impl_method_names=impl_method_names,
                    impl_var_names=impl_var_names,
                    method_signature_builder=getattr(
                        generator, "_method_proto_signature", None,
                    ),
                    var_signature_builder=getattr(
                        generator, "_var_proto_signature", None,
                    ),
                )
            except ExtractionError as e:
                errors.append(
                    f"[{platform}] {spec.name}: marker parse failed in "
                    f"{impl_path}: {e}"
                )
                continue

            kw_fn = "func" if platform == "ios" else "fun"
            for missing in sync_result.missing_methods_in_impl:
                errors.append(
                    f"[{platform}] {impl_path}: dataFlow.viewModel.methods "
                    f"declares '{missing}' but no matching {kw_fn} found in Impl. "
                    f"Add '{kw_fn} {missing}()' or remove from spec."
                )
            for missing in sync_result.missing_vars_in_impl:
                errors.append(
                    f"[{platform}] {impl_path}: dataFlow.viewModel.vars "
                    f"declares '{missing}' but no matching var/val found in Impl. "
                    f"Add the property declaration or remove from spec."
                )

            # Swift: external-label drift between Protocol signature and Impl.
            # Kotlin and TS don't have external labels, so this is iOS-only.
            if platform == "ios" and impl_source is not None:
                for method in sync_result.methods:
                    expected = extract_expected_labels_from_swift_sig(
                        method.signature
                    )
                    actual = extract_swift_method_labels(
                        impl_source, method.name
                    )
                    if actual is None:
                        continue  # missing_methods_in_impl already reported
                    if expected != actual:
                        errors.append(
                            f"[ios] {impl_path}: '{method.name}' "
                            f"external-label drift. Protocol expects "
                            f"{_format_label_sig(method.name, expected)}, "
                            f"Impl declares "
                            f"{_format_label_sig(method.name, actual)}. "
                            f"Align the Impl signature or set "
                            f"\"label\" on the spec param "
                            f"(e.g. `{{\"name\": \"x\", \"type\": \"T\", \"label\": \"_\"}}`)."
                        )

            # Protocol / Base file.
            if platform == "web":
                # Restrict initializeEventHandlers to members that actually
                # exist in the rjui-generated <Name>Data (layout-derived) —
                # spec-only methods in the updateData literal are a TS2353.
                layout_event_names = collect_layout_event_names(
                    resolve_layout_path(config_mgr.layouts_directory, spec)
                )
                content = generator.generate_viewmodel_protocol(
                    spec, layout_event_names=layout_event_names
                )
            else:
                content = generator.generate_viewmodel_protocol(
                    spec,
                    impl_source=impl_source,
                    sync_result=sync_result,
                )
            if atomic_write_text(proto_path, content):
                protocol_writes += 1

            # Impl-side inheritance + (Kotlin) override injection.
            if impl_source is not None and platform in ("ios", "android"):
                protocol_name = f"{spec.name}ViewModelProtocol"
                try:
                    if platform == "ios":
                        updated = ensure_swift_inheritance(
                            impl_source, f"{spec.name}ViewModel", protocol_name,
                        )
                    else:
                        updated = ensure_kotlin_inheritance(
                            impl_source, f"{spec.name}ViewModel", protocol_name,
                        )
                        # Impl and Protocol live in sibling packages
                        # (viewmodel(s) vs viewmodel.protocol), so adding the
                        # protocol to the inheritance list also requires an
                        # explicit `import` — otherwise kotlinc reports
                        # `Unresolved reference`.
                        proto_fqn_fn = getattr(
                            generator, "viewmodel_protocol_fqn", None,
                        )
                        if callable(proto_fqn_fn):
                            updated = ensure_kotlin_import(
                                updated, proto_fqn_fn(spec.name),
                            )
                        method_names = [m.name for m in sync_result.methods]
                        # `data` is hard-coded on the Protocol's first line
                        # (matching the Compose `StateFlow<XData>` convention)
                        # so the existing Impl declaration needs `override`
                        # too — otherwise kotlinc warns
                        # "data hides member of supertype".
                        var_names = ["data"] + [v.name for v in sync_result.vars]
                        updated = inject_kotlin_override(updated, method_names)
                        updated = inject_kotlin_var_override(updated, var_names)
                except ValueError as e:
                    errors.append(
                        f"[{platform}] {impl_path}: {e}"
                    )
                    continue
                if atomic_write_text(impl_path, updated):
                    impl_writes += 1

    if errors:
        print("\nERROR [protocol-sync]:")
        for line in errors:
            print(f"  - {line}")
        return False

    if protocol_writes or impl_writes:
        print(
            f"Protocol sync: updated {protocol_writes} protocol(s), "
            f"{impl_writes} impl file(s)"
        )
    return True


def _distribute_images(
    config_mgr: ConfigManager,
    config: dict,
    platforms: dict,
    args,
) -> None:
    """Convert SVGs in images_directory and distribute to each platform.

    - iOS:     *.xcassets/{name}.imageset/ (SVG + Contents.json)
    - Android: res/drawable/{name}.xml    (Vector Drawable)
    - Web:     public/images/{name}.svg   (copy as-is)
    """
    images_src = config_mgr.images_directory
    if not images_src.exists():
        return

    svg_files = sorted(images_src.rglob("*.svg"))
    if not svg_files:
        return

    for platform, pconfig in platforms.items():
        if args.ios_only and platform != "ios":
            continue
        if args.android_only and platform != "android":
            continue
        if args.web_only and platform != "web":
            continue

        platform_root = config_mgr.project_root / pconfig["root"]
        count = 0
        raster_count = 0

        if platform == "ios":
            # Find *.xcassets directory
            xcassets_dir = pconfig.get("xcassetsDir", "")
            if xcassets_dir:
                dest = platform_root / xcassets_dir
            else:
                # Auto-detect
                candidates = list(platform_root.rglob("*.xcassets"))
                if not candidates:
                    print(f"  WARNING: No .xcassets found in {platform_root} — skipping iOS images")
                    continue
                dest = candidates[0]

            for svg in svg_files:
                result = ImageConverter.convert_ios(svg, dest)
                if result:
                    count += 1

        elif platform == "android":
            drawable_dir = pconfig.get("drawableDir", "")
            if drawable_dir:
                dest = platform_root / drawable_dir
            else:
                dest = platform_root / "app" / "src" / "main" / "res" / "drawable"

            for svg in svg_files:
                result = ImageConverter.convert_android(svg, dest)
                if result:
                    count += 1
                    # Raster fallbacks land in the sibling drawable-nodpi/
                    if result.parent.name.startswith("drawable-nodpi"):
                        raster_count += 1

        elif platform == "web":
            web_images_dir = pconfig.get("imagesDir", "")
            if web_images_dir:
                dest = platform_root / web_images_dir
            else:
                dest = platform_root / "public" / "images"

            for svg in svg_files:
                result = ImageConverter.convert_web(svg, dest)
                if result:
                    count += 1

        if count:
            if platform == "android" and raster_count:
                vector_count = count - raster_count
                print(
                    f"Converted {count} image(s) → {platform} "
                    f"({vector_count} vector + {raster_count} raster)"
                )
            else:
                print(f"Converted {count} image(s) → {platform}")
