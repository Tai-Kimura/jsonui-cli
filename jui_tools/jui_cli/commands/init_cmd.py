"""jui init command — project initialization."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ..core.config_manager import ConfigManager
from .sync_tool_cmd import (
    PLATFORM_TO_TOOL,
    _resolve_source_root,
    _sync_one_tool,
)


def register_init_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the init subcommand."""
    init_parser = subparsers.add_parser("init", aliases=["i"], help="Initialize a JsonUI project")
    init_parser.add_argument("--project-name", required=True, help="Project name")
    init_parser.add_argument("--ios", metavar="PATH", help="iOS project root path")
    init_parser.add_argument("--ios-mode", default="swiftui", choices=["swiftui", "uikit", "all"],
                             help="iOS rendering mode (default: swiftui)")
    init_parser.add_argument("--android", metavar="PATH", help="Android project root path")
    init_parser.add_argument("--android-mode", default="compose", choices=["compose", "xml"],
                             help="Android rendering mode (default: compose)")
    init_parser.add_argument("--package-name", help="Android package name (e.g., com.example.app)")
    init_parser.add_argument("--web", metavar="PATH", help="Web project root path")
    init_parser.add_argument(
        "--no-sync-tools",
        action="store_true",
        help="Don't copy platform tools (sjui_tools/kjui_tools/rjui_tools) into each platform root after init. "
             "The copies are required for `rjui g converter` etc. to work against a project-local tree; skip "
             "this only if you have your own tool layout.",
    )


def cmd_init(args: argparse.Namespace) -> int:
    """Execute jui init."""
    config_mgr = ConfigManager()
    if config_mgr.exists():
        print(f"ERROR: {config_mgr.CONFIG_FILENAME} already exists at {config_mgr.path}")
        print("Use --force to overwrite (not yet implemented)")
        return 1

    # Build config
    config = {
        "project_name": args.project_name,
        "spec_directory": "docs/screens/json",
        "component_spec_directory": "docs/components/json",
        "strings_file": "",
        "type_map_file": ".jsonui-type-map.json",
        "platforms": {},
    }

    if args.ios:
        config["platforms"]["ios"] = {
            "root": args.ios,
            "mode": args.ios_mode,
        }

    if args.android:
        android_config = {
            "root": args.android,
            "mode": args.android_mode,
        }
        if args.package_name:
            android_config["package_name"] = args.package_name
        config["platforms"]["android"] = android_config

    if args.web:
        config["platforms"]["web"] = {
            "root": args.web,
        }

    # Create directories
    project_root = Path.cwd()
    spec_dir = project_root / config["spec_directory"]
    component_dir = project_root / config["component_spec_directory"]
    spec_dir.mkdir(parents=True, exist_ok=True)
    component_dir.mkdir(parents=True, exist_ok=True)

    # Save config
    config_mgr.save(config)
    print(f"Created {config_mgr.CONFIG_FILENAME}")

    # Create default type map
    _create_default_type_map(project_root / config["type_map_file"])

    # Seed the shared Layouts / Styles / Resources tree so the canonical
    # placement is visible from the first commit:
    #   - {layouts_directory}/              — Layout JSON (single source of truth)
    #   - {layouts_directory}/Resources/    — strings.json, colors.json (under Layouts)
    #   - {styles_directory}/               — shared style files (SIBLING to Layouts)
    # Without the seed, agents sometimes infer the wrong convention (e.g. placing
    # Styles under Layouts) and `jui build` silently skips their output.
    _seed_layouts_tree(project_root, config)

    # Run platform init commands
    failed = []
    if args.ios:
        ios_root = project_root / args.ios
        ios_root.mkdir(parents=True, exist_ok=True)
        if not _run_tool(["sjui", "init", "--mode", args.ios_mode], ios_root):
            failed.append("ios (sjui init)")

    if args.android:
        android_root = project_root / args.android
        android_root.mkdir(parents=True, exist_ok=True)
        if not _run_tool(["kjui", "init", "--mode", args.android_mode], android_root):
            failed.append("android (kjui init)")

    if args.web:
        web_root = project_root / args.web
        web_root.mkdir(parents=True, exist_ok=True)
        if not _run_tool(["rjui", "init"], web_root):
            failed.append("web (rjui init)")

    if failed:
        print(f"\nWARNING: Init failed for: {', '.join(failed)}")
        print("You can run these commands manually.")

    # Copy platform tools (sjui_tools / kjui_tools / rjui_tools) from the home
    # install into each platform root. Generated custom converter files use
    # `require_relative ../base_converter` and therefore need a project-local
    # tool tree to resolve; without this step the first `rjui g converter`
    # would write to a nonsense path or fail.
    if not args.no_sync_tools and config["platforms"]:
        print("\n--- Copying platform tools ---")
        try:
            source_root = _resolve_source_root(None)
        except FileNotFoundError as exc:
            print(f"  WARNING: {exc}")
            print("  Skipping tool copy. Run `jui sync_tool` later once ~/.jsonui-cli/ is available.")
        else:
            print(f"  Source: {source_root}")
            for platform_name, pconfig in config["platforms"].items():
                tool_name = PLATFORM_TO_TOOL.get(platform_name)
                if not tool_name:
                    continue
                src = source_root / tool_name
                platform_root = project_root / pconfig["root"]
                dst = platform_root / tool_name
                if not src.exists():
                    print(f"  [{platform_name}] skipped — source missing: {src}")
                    continue
                if not platform_root.exists():
                    print(f"  [{platform_name}] skipped — platform root missing: {platform_root}")
                    continue
                try:
                    counters = _sync_one_tool(
                        src, dst, platform_root,
                        prune=False,
                        dry_run=False,
                    )
                except Exception as exc:
                    print(f"  [{platform_name}] ERROR: {exc}")
                    continue
                print(
                    f"  [{platform_name}] copied={counters['copied']} "
                    f"updated={counters['updated']} "
                    f"ruby-pin={counters['ruby_pin']}"
                )

    print("\nProject initialized successfully!")
    print(f"  Spec directory: {spec_dir}")
    print(f"  Component directory: {component_dir}")
    for platform, pconfig in config["platforms"].items():
        print(f"  {platform}: {pconfig['root']}")

    return 0


def _run_tool(cmd: list[str], cwd: Path) -> bool:
    """Run a platform tool, handling missing executables gracefully."""
    try:
        result = subprocess.run(cmd, cwd=cwd)
        return result.returncode == 0
    except FileNotFoundError:
        print(f"  WARNING: '{cmd[0]}' not found in PATH — skipping")
        return False


def _seed_layouts_tree(project_root: Path, config: dict) -> None:
    """Seed layouts/, styles/, and Resources/colors.json.

    Agents read file-locations.md to learn where to place things; seeding
    the directories at init time makes the convention visible immediately
    (before any layout is written) and avoids the common mistake of
    nesting Styles under Layouts.
    """
    import json

    layouts_dir = project_root / config.get("layouts_directory", "docs/screens/layouts")
    styles_dir = project_root / config.get("styles_directory", "docs/screens/styles")
    resources_dir = layouts_dir / "Resources"

    layouts_dir.mkdir(parents=True, exist_ok=True)
    styles_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Empty colors.json — jui build auto-populates it from hex literals found
    # in Layout JSON. Seeding an empty file removes the "file not found"
    # surprise on the first build and gives authors a visible target for
    # semantic color names.
    colors_file = resources_dir / "colors.json"
    if not colors_file.exists():
        colors_file.write_text("{}\n", encoding="utf-8")
        print(f"Created {colors_file.relative_to(project_root)}")


def _create_default_type_map(path: Path) -> None:
    """Create default .jsonui-type-map.json."""
    import json

    # TypeMapper already has builtins for primitives, closures, collections,
    # and common generic patterns. The template only needs to document the
    # shape and seed commented-out examples of custom types so authors can
    # fill in the specifics for their project. Run `jui verify` to list
    # unregistered custom types referenced in specs.
    type_map = {
        "version": "1.0",
        "_comment": (
            "Cross-platform custom type mappings. Builtins already cover "
            "String/Int/Bool/Double/Void/Data/URL/Date/callback/Map(K,V)/"
            "Array(T)/[T]/T?/AsyncThrowingStream<T,E>. Add entries here only "
            "for types that live in a Swift Package, Kotlin module outside "
            "the main source tree, or a TypeScript path that needs an "
            "explicit import. Run `jui verify` to see which custom types "
            "are referenced in specs but not registered."
        ),
        "_example_swift_package_type": {
            "_comment": (
                "A type defined in a Swift Package / Framework. The `imports` "
                "list maps to `import <module>` on iOS and "
                "`import { <class> } from \"<path>\"` on Web."
            ),
            "ItemImage": {
                "class": "ItemImage",
                "imports": ["Models"],
                "web": {
                    "class": "ItemImage",
                    "imports": ["@/types/ItemImage"],
                },
            },
        },
        "_example_cross_platform_type": {
            "_comment": (
                "Different native type per platform (rare — use pipe-union "
                "`A|B|C` in spec.type for simple cases first)."
            ),
            "ByteArrayData": {
                "class": "Data",
                "android": {"class": "ByteArray"},
                "web": {"class": "Uint8Array"},
            },
        },
        "types": {},
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(type_map, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Created {path.name}")
