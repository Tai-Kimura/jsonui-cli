"""`jui verify` — compare generated Layout JSON to on-disk implementation."""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path


# Identifiers that look like type names (PascalCase, no separators).
_TYPE_IDENT_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\b")

# Commonly-used names that should never be flagged as "custom type needing
# registration" — includes Swift/Kotlin/TS primitives and TypeMapper
# builtins.
_STDLIB_TYPES = {
    "String", "Int", "Double", "Float", "Bool", "Boolean", "Char", "Byte",
    "Short", "Long", "Any", "Void", "Unit", "Nothing",
    "Data", "URL", "Date",
    "Array", "List", "Set", "Map", "Dictionary",
    "MutableList", "MutableMap", "MutableSet", "Pair", "Triple",
    "Visibility", "CollectionDataSource",
    "Flow", "Promise", "Record", "Uint8Array", "ByteArray",
    "AsyncThrowingStream", "AsyncIterable",
}


def register_verify_command(subparsers: argparse._SubParsersAction) -> None:
    """Register ``jui verify``."""
    parser = subparsers.add_parser(
        "verify",
        help="Compare generated Layout JSON to existing Layouts/*.json",
    )
    parser.add_argument(
        "--file",
        help="Verify a single spec file (e.g. 'login.spec.json')",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Include per-screen diff details in the report",
    )
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Exit non-zero if any diff is detected (useful for CI)",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="Target platform (defaults to the first platform in config)",
    )
    parser.set_defaults(func=cmd_verify)


def cmd_verify(args: argparse.Namespace) -> int:
    from ..core.config_manager import ConfigManager
    from ..core.spec_extractor import extract_screen_spec
    from ..core.type_mapper import TypeMapper
    from ..core.parent_spec_merger import ParentSpecMerger
    from ..core.view_diff_checker import ViewDiffChecker, render_report
    from ..generators.layout_generator import LayoutGenerator

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    config = config_mgr.load()
    spec_dir = config_mgr.spec_directory

    platform = args.platform
    if platform is None:
        platforms = config.get("platforms") or {}
        platform = next(iter(platforms), None)
    if not platform:
        print("ERROR: No platform configured. Specify --platform explicitly.")
        return 1

    # Prefer shared layouts_directory; fall back to per-platform path
    layouts_root = config_mgr.layouts_directory
    if not layouts_root.exists():
        layouts_root = _resolve_layouts_root(config, platform, config_mgr)
    if layouts_root is None:
        print(f"ERROR: Could not resolve Layouts directory for platform '{platform}'")
        return 1

    if args.file:
        spec_files = [spec_dir / args.file]
        if not spec_files[0].exists():
            print(f"ERROR: Spec file not found: {spec_files[0]}")
            return 1
    else:
        spec_files = sorted(spec_dir.glob("*.spec.json"))

    # Resolve sub_spec paths referenced by parent_spec
    sub_spec_paths: set[Path] = set()
    for sf in spec_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                head = json.load(f)
        except (OSError, ValueError):
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
    type_mapper = TypeMapper(config_mgr.type_map_file)
    layout_gen = LayoutGenerator(type_mapper)

    # On normalizeLayouts projects (experimental), apply the same L1
    # canonicalization to BOTH sides of every comparison so alias
    # rewriting / the $jui marker can never register as drift.
    normalizer = None
    from .build_cmd import _normalize_layouts_enabled
    if _normalize_layouts_enabled(config_mgr):
        from ..core.normalizer import Canonicalizer

        _canonicalizer = Canonicalizer()

        def normalizer(tree):
            canonical, _warnings = _canonicalizer.canonicalize(tree)
            return canonical

    # ``layouts_root`` lets the checker follow cellClasses/include
    # references into neighbouring cell Layout JSON files so the
    # actual-layout view of ids matches the aggregated spec tree.
    checker = ViewDiffChecker(layouts_root=layouts_root, normalizer=normalizer)

    results = []
    missing_layouts: list[str] = []
    skipped_external: list[str] = []
    data_orphans: list[tuple[str, list[tuple[str, str]]]] = []
    unregistered_types: "OrderedDict[str, list[str]]" = OrderedDict()
    for sf in spec_files:
        if sf.resolve() in sub_spec_paths:
            continue
        with open(sf, "r", encoding="utf-8") as f:
            spec_data = json.load(f)
        if spec_data.get("type") == "screen_parent_spec":
            merge_result = merger.merge_from_file(sf)
            spec_data = merge_result.spec
        screen_spec = extract_screen_spec(spec_data)

        # Skip specs whose layout is authored externally (layoutFile mode
        # with no components). Generating would produce an empty stub,
        # causing a false diff against the real layout.
        if screen_spec.layout_file and not screen_spec.layout_components:
            skipped_external.append(
                f"{sf.stem} -> {screen_spec.layout_file}.json"
            )
            continue

        generated = layout_gen.generate(screen_spec)
        actual_path = _resolve_actual_layout(
            layouts_root, sf.stem, screen_spec.name,
            layout_file=screen_spec.layout_file,
        )
        if not actual_path or not actual_path.exists():
            missing_layouts.append(sf.stem)
            continue
        with open(actual_path, "r", encoding="utf-8") as f:
            actual = json.load(f)

        # Canonicalize both sides up front (idempotent — the checker also
        # normalizes) so the data-section diff below sees the same trees.
        if normalizer is not None:
            generated = normalizer(generated)
            actual = normalizer(actual)

        diff = checker.compare(
            generated, actual, screen=sf.stem.replace(".spec", "")
        )
        results.append(diff)

        # Layout JSON `data[]` entries not declared in spec (not in
        # uiVariables and not derived from displayLogic/collection/tabView).
        orphans = _diff_data_section(generated, actual)
        if orphans:
            data_orphans.append((str(sf.stem), orphans))

        # Custom types referenced by spec but not registered in the
        # type-map. Flagging these lets authors fill in `.jsonui-type-map.json`
        # with `imports` hints so iOS/Web codegen can emit the right
        # import statements for Swift modules / TS paths.
        for ident, location in _collect_custom_type_refs(screen_spec):
            if type_mapper.is_registered(ident):
                continue
            bucket = unregistered_types.setdefault(ident, [])
            bucket.append(f"{sf.stem}:{location}")

    report = render_report(results, detail=args.detail)
    print(report)

    if skipped_external:
        print("\n**Skipped (layout authored externally):**")
        for name in skipped_external:
            print(f"- {name}")

    if missing_layouts:
        print("\n**Layouts not found on disk (skipped):**")
        for name in missing_layouts:
            print(f"- {name}")

    if unregistered_types:
        print(
            f"\n**WARNING: {len(unregistered_types)} custom type(s) "
            "referenced but not registered in TypeMapper.** "
            "If any live in a Swift Package / separate module, or need "
            "explicit TS import paths, add entries to "
            "`.jsonui-type-map.json`:"
        )
        print("```json")
        print("{")
        print("  \"types\": {")
        for ident in unregistered_types:
            print(f'    "{ident}": {{ "class": "{ident}", "imports": [] }},')
        print("  }")
        print("}")
        print("```")
        print("\n  Usage locations:")
        for ident, locs in unregistered_types.items():
            preview = ", ".join(locs[:3]) + ("..." if len(locs) > 3 else "")
            print(f"  - {ident}: {preview}")

    if data_orphans:
        total = sum(len(entries) for _, entries in data_orphans)
        print(
            f"\n**WARNING: {total} data-section entries not declared in "
            f"spec.uiVariables** across {len(data_orphans)} Layout JSON file(s):"
        )
        for stem, entries in data_orphans:
            print(f"- {stem}:")
            for name, klass in entries:
                print(f"    - data.{name} ({klass})")
        print(
            "  → add each missing entry to stateManagement.uiVariables "
            "(or remove it from the Layout JSON's data section) so "
            "regeneration is idempotent."
        )

    # Screens with no spec at all. Every other gate compares things that
    # exist: build generates from the Layout, verify diffs declared against
    # actual, validate checks the specs on disk. A screen shipped without a
    # spec is absent from all three inputs, so nothing was ever in a
    # position to notice it — one went five days unremarked.
    coverage = _check_spec_coverage(config_mgr, config, spec_dir, layouts_root)
    require_coverage = bool((config.get("verify") or {}).get("requireSpecPerScreen"))
    if coverage.missing_specs:
        print(
            f"\n**{'ERROR' if require_coverage else 'WARNING'}: "
            f"{len(coverage.missing_specs)} screen layout(s) have no spec:**"
        )
        for name in coverage.missing_specs:
            print(f"- {name}")
        print(
            "  → author the spec (`jsonui-doc init spec`), or if the layout "
            "is not a screen, declare that on the layout root with "
            '`"role": "cell"` so the classification says so rather than a '
            "list here having to."
        )
    if coverage.missing_layouts:
        print(
            f"\n**{'ERROR' if require_coverage else 'WARNING'}: "
            f"{len(coverage.missing_layouts)} spec(s) name a layout that "
            "does not exist:**"
        )
        for name in coverage.missing_layouts:
            print(f"- {name}")
        print(
            "  → a rename that moved only one side leaves exactly this. "
            "Fix `metadata.layoutFile` or restore the layout."
        )
    if (coverage.missing_specs or coverage.missing_layouts) and not require_coverage:
        print(
            '  (set `"verify": {"requireSpecPerScreen": true}` in '
            "jui.config.json to make this fail `--fail-on-diff`)"
        )

    # API model drift — independent of Layout drift, gated by --fail-on-diff.
    api_drift = _check_api_model_drift(config_mgr, config, args)
    if api_drift:
        print(
            f"\n**API model drift detected ({len(api_drift)} file(s)):**"
        )
        for line in api_drift:
            print(f"- {line}")
        print(
            "  → run `jui build` (or `jui g api` once available) to regenerate."
        )

    coverage_gap = bool(coverage.missing_specs or coverage.missing_layouts)
    if args.fail_on_diff and (
        any(r.has_diff for r in results) or data_orphans or api_drift
        or (require_coverage and coverage_gap)
    ):
        return 1
    return 0


@dataclass
class SpecCoverage:
    """Screens without a spec, and specs naming a layout that is not there."""

    missing_specs: list[str] = field(default_factory=list)
    missing_layouts: list[str] = field(default_factory=list)


def _check_spec_coverage(config_mgr, config, spec_dir, layouts_root) -> SpecCoverage:
    """Reconcile the set of screen layouts with the set of specs.

    Correspondence runs through `metadata.layoutFile` rather than file
    names, since that is what declares the link. Which layouts are screens
    comes from the existing classification, so a fragment is excused by its
    own `"role": "cell"` declaration rather than by an exclusion list here —
    a list would go stale in the same silence this check exists to end.
    Sub-specs are skipped: they inherit their parent's layout and claim none.
    """
    from ..core.screen_identity import build_screen_index, screen_id_for_path

    coverage = SpecCoverage()
    if layouts_root is None or not Path(layouts_root).is_dir():
        return coverage

    def as_id(value: str) -> str:
        return screen_id_for_path(value if value.endswith(".json") else value + ".json")

    index = build_screen_index(
        layouts_root, (config.get("test") or {}).get("appOwnedScreens")
    )
    screens = set(index.screen_ids)

    claimed: set[str] = set()
    for spec_file in sorted(Path(spec_dir).rglob("*.spec.json")):
        try:
            with open(spec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("type") == "screen_sub_spec":
            continue
        layout_file = (data.get("metadata") or {}).get("layoutFile")
        if isinstance(layout_file, str) and layout_file:
            claimed.add(as_id(layout_file))
        else:
            claimed.add(as_id(spec_file.name[: -len(".spec.json")]))

    coverage.missing_specs = sorted(screens - claimed)
    coverage.missing_layouts = sorted(
        name for name in claimed - screens if not index.is_known(name)
    )
    return coverage


def _check_api_model_drift(config_mgr, config, args) -> list[str]:
    """Compare in-memory swagger regen output against on-disk DTOs.

    Implements the §5.5 semantic: ``jui verify`` regenerates the DTO
    bytes in memory and compares against the files written by the last
    ``jui build``. Independent of the build pipeline — running
    ``jui verify`` directly catches drift even when ``jui build``
    hasn't been run.

    Returns a list of human-readable drift descriptions (empty = no drift).
    Schema errors (oneOf, multi-file ref, etc.) surface as drift entries
    so the user sees them via the same report path.
    """
    from ..core.api_model_sync import (
        collect_docs,
        diff_plan,
        has_planner,
        plan_for,
    )
    from ..core.openapi_loader import OpenAPILoadError

    platforms = config.get("platforms") or {}
    selected_platforms = [args.platform] if args.platform else list(platforms.keys())

    try:
        docs = collect_docs(config_mgr)
    except OpenAPILoadError as e:
        return [f"swagger load error: {e}"]

    if not docs:
        return []

    drift: list[str] = []
    for platform in selected_platforms:
        if platform not in platforms or not has_planner(platform):
            continue
        try:
            plan = plan_for(platform, config_mgr, platforms[platform], docs)
        except OpenAPILoadError as e:
            drift.append(f"[{platform}] swagger error: {e}")
            continue
        drift.extend(f"[{platform}] {line}" for line in diff_plan(plan))
    return drift


def _collect_custom_type_refs(spec):
    """Yield ``(type_identifier, location_path)`` for every capitalised
    identifier that appears in a spec's type fields.

    Built-in primitives (String/Int/Bool/Map/...) are filtered out so the
    caller only sees names that *might* need a ``.jsonui-type-map.json``
    entry.
    """
    def _walk_type(type_str: str, location: str):
        if not isinstance(type_str, str):
            return
        for ident in _TYPE_IDENT_RE.findall(type_str):
            if ident in _STDLIB_TYPES:
                continue
            yield ident, location

    for v in spec.ui_variables:
        yield from _walk_type(v.type or "", f"uiVariables.{v.name}")

    vm = spec.view_model
    for m in vm.methods:
        for p in m.params:
            yield from _walk_type(p.type, f"viewModel.methods.{m.name}.params.{p.name}")
        yield from _walk_type(m.return_type, f"viewModel.methods.{m.name}.returnType")
    for v in vm.vars:
        yield from _walk_type(v.type, f"viewModel.vars.{v.name}")

    for repo in spec.repositories:
        for m in repo.methods:
            for p in m.params:
                yield from _walk_type(
                    p.type, f"repositories.{repo.name}.{m.name}.params.{p.name}"
                )
            yield from _walk_type(
                m.return_type, f"repositories.{repo.name}.{m.name}.returnType"
            )

    for uc in spec.use_cases:
        for m in uc.methods:
            for p in m.params:
                yield from _walk_type(
                    p.type, f"useCases.{uc.name}.{m.name}.params.{p.name}"
                )
            yield from _walk_type(
                m.return_type, f"useCases.{uc.name}.{m.name}.returnType"
            )


def _diff_data_section(
    generated: dict, actual: dict,
) -> list[tuple[str, str]]:
    """Return ``(name, class)`` tuples present in *actual*'s ``data[]``
    but missing from the spec-driven *generated* ``data[]``.
    """
    gen_data = generated.get("data") or []
    act_data = actual.get("data") or []
    if not isinstance(gen_data, list) or not isinstance(act_data, list):
        return []
    gen_names = {
        e.get("name") for e in gen_data if isinstance(e, dict)
    }
    orphans: list[tuple[str, str]] = []
    for e in act_data:
        if not isinstance(e, dict):
            continue
        name = e.get("name")
        if name and name not in gen_names:
            orphans.append((name, e.get("class", "?")))
    return orphans


def _resolve_layouts_root(config: dict, platform: str, config_mgr) -> Path | None:
    """Locate the Layouts/ directory for a given platform."""
    platforms = config.get("platforms") or {}
    pconfig = platforms.get(platform) or {}
    layouts_rel = pconfig.get("layoutsDir") or pconfig.get("layouts_dir")
    if layouts_rel:
        return (config_mgr.project_root / layouts_rel).resolve()

    # Fallback: common project-relative path
    fallback = config_mgr.project_root / "Layouts"
    if fallback.exists():
        return fallback
    return None


# Alternate names used by some projects (parallel to the gap report logic)
_NAME_MAP = {
    "favoritelist": "favorite_list",
    "itemslist": "bar_items_list",
    "followinglist": "following_bar_list",
    "itemlist": "bar_list",
    "siteslist": "purchase_sites_list",
    "itemdetail": "item_detail",
    "itemdetail": "item_detail",
    "forgotpassword": "forgot_password",
    "resetpassword": "reset_password",
}


def _resolve_actual_layout(
    layouts_root: Path, spec_stem: str, screen_name: str,
    layout_file: str = "",
) -> Path | None:
    """Find the Layout JSON that corresponds to a given spec.

    ``layout_file`` is ``metadata.layoutFile`` from the spec. When set, it
    takes priority — a spec can live under ``json/learn/installation.spec.json``
    and point at ``layouts/learn/installation.json``, which the stem-only
    candidates below would miss and report as "not found".
    """
    name = spec_stem.replace(".spec", "")
    candidates: list[Path] = []
    if layout_file:
        candidates.append(layouts_root / f"{layout_file}.json")
    candidates.extend([
        layouts_root / f"{name}.json",
        layouts_root / f"{_NAME_MAP.get(name, name)}.json",
        layouts_root / f"{_camel_to_snake(screen_name)}.json",
    ])
    for c in candidates:
        if c.exists():
            return c
    return None


def _camel_to_snake(name: str) -> str:
    import re
    return re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")
