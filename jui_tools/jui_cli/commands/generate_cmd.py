"""jui generate command — file generation from specs."""
from __future__ import annotations

import argparse
from pathlib import Path


def register_generate_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the generate subcommand."""
    gen_parser = subparsers.add_parser(
        "generate", aliases=["g"], help="Generate files from specs"
    )
    gen_sub = gen_parser.add_subparsers(dest="generate_type")

    # jui g project
    project_parser = gen_sub.add_parser("project", help="Generate all files from specs")
    project_parser.add_argument("--file", metavar="SPEC_FILE", help="Single spec file to process")
    project_parser.add_argument("--force", action="store_true", help="Force overwrite declaration files")
    project_parser.add_argument("--skip-layout", action="store_true", help="Skip Layout JSON generation")
    project_parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    project_parser.add_argument("--ios-only", action="store_true", help="Generate iOS files only")
    project_parser.add_argument("--android-only", action="store_true", help="Generate Android files only")
    project_parser.add_argument("--web-only", action="store_true", help="Generate Web files only")
    project_parser.add_argument("--type-map", metavar="PATH", help="Path to type map file")

    # jui g screen
    screen_parser = gen_sub.add_parser("screen", help="Create spec template for new screen")
    screen_parser.add_argument("names", nargs="+", help="Screen names (PascalCase)")
    screen_parser.add_argument("--display-name", help="Display name (for single screen)")

    # jui g converter
    converter_parser = gen_sub.add_parser("converter", help="Generate custom component converter")
    converter_parser.add_argument("name", nargs="?", help="Component name")
    converter_parser.add_argument("--from", dest="from_spec", metavar="SPEC_FILE",
                                  help="Generate from component spec file — a filename resolved "
                                       "against component_spec_directory, or a path to the spec")
    converter_parser.add_argument("--all", dest="all_specs", action="store_true",
                                  help="Generate from all component specs")
    converter_parser.add_argument("--attributes", help="Attributes (key:type,...)")
    converter_parser.add_argument("--container", action="store_true", help="Container component")
    converter_parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip converters that already exist (used by `jui build`)",
    )

    # jui g api — preview swagger-driven DTO + Domain model generation
    api_parser = gen_sub.add_parser(
        "api",
        help="Preview swagger → DTO + Domain model generation (uses api.schemas filter)",
    )
    api_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated, but don't write any files",
    )
    api_parser.add_argument(
        "--platform",
        choices=("ios", "android", "web"),
        help="Restrict to a single platform",
    )
    api_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON (used by MCP wrappers)",
    )

    # jui g attr-bindings — typed attribute extraction codegen (SSoT pillar C)
    ab_parser = gen_sub.add_parser(
        "attr-bindings",
        help=(
            "Generate typed attribute extraction code (Swift/Kotlin/Ruby) "
            "from shared/core/attribute_definitions.json"
        ),
    )
    ab_parser.add_argument(
        "--lang",
        choices=("swift", "kotlin", "ruby", "all"),
        default="all",
        help="Target language (default: all)",
    )
    ab_parser.add_argument(
        "--out",
        metavar="DIR",
        help=(
            "Output directory (default: <tool repo>/build/attr_codegen/<lang>). "
            "With --lang all, per-language subdirectories are created under DIR."
        ),
    )
    ab_parser.add_argument(
        "--definitions",
        metavar="PATH",
        help="Override the attribute definitions file (default: bundled SSoT)",
    )


def cmd_generate(args: argparse.Namespace) -> int:
    """Execute jui generate."""
    gen_type = getattr(args, "generate_type", None)

    if gen_type == "project":
        return _cmd_generate_project(args)
    elif gen_type == "screen":
        return _cmd_generate_screen(args)
    elif gen_type == "converter":
        return _cmd_generate_converter(args)
    elif gen_type == "api":
        return _cmd_generate_api(args)
    elif gen_type == "attr-bindings":
        return _cmd_generate_attr_bindings(args)
    else:
        print("Usage: jui generate <project|screen|converter|api|attr-bindings> [options]")
        return 1


def _cmd_generate_attr_bindings(args: argparse.Namespace) -> int:
    """Execute jui g attr-bindings — typed attribute extraction codegen.

    Emission is deterministic (sorted components/attributes, no
    timestamps), so re-running always produces byte-identical output —
    the results can sit under `jui verify`-style diff checks. The default
    output stays inside this repo (build/attr_codegen/<lang>); writing
    into external library repos requires an explicit ``--out``
    (07/08/09 sync the build output instead of cross-repo writes).
    """
    import hashlib
    import json
    import shutil
    from pathlib import Path

    from ..generators.attr_codegen import model as attr_model
    from ..generators.attr_codegen import (
        kotlin_emitter,
        ruby_emitter,
        swift_emitter,
    )

    definitions = (
        Path(args.definitions).resolve()
        if args.definitions
        else attr_model.default_definitions_path()
    )
    if not definitions.exists():
        print(f"ERROR: attribute definitions not found: {definitions}")
        return 1

    model = attr_model.load_model(definitions)

    emitters = {
        "swift": swift_emitter.emit,
        "kotlin": kotlin_emitter.emit,
        "ruby": ruby_emitter.emit,
    }
    langs = list(emitters) if args.lang == "all" else [args.lang]

    # Tool repo root (build/ output default) — generate_cmd.py lives at
    # jui_tools/jui_cli/commands/, so repo root is three levels up.
    repo_root = Path(__file__).resolve().parents[3]

    skipped = attr_model.skipped_payload(model)
    common_count = len(model.common.attrs)
    component_count = len(model.components)
    component_attr_count = sum(len(c.attrs) for c in model.components)

    # `<lang>/<rel_path>` -> sha256 of the emitted content, for the manifest.
    manifest_files: dict[str, str] = {}

    for lang in langs:
        if args.out:
            out_dir = Path(args.out)
            if args.lang == "all":
                out_dir = out_dir / lang
        else:
            out_dir = repo_root / "build" / "attr_codegen" / lang
            # Default dir is owned by this generator — wipe stale output so
            # renamed/removed components never leave orphan files behind.
            if out_dir.exists():
                shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        files = emitters[lang](model)
        for rel_path, content in files.items():
            target = out_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            manifest_files[f"{lang}/{rel_path}"] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()

        skip_path = out_dir / "skipped_attributes.json"
        skipped_text = (
            json.dumps(skipped, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        )
        skip_path.write_text(skipped_text, encoding="utf-8")
        manifest_files[f"{lang}/skipped_attributes.json"] = hashlib.sha256(
            skipped_text.encode("utf-8")
        ).hexdigest()

        print(f"[{lang}] wrote {len(files) + 1} file(s) → {out_dir}")

    # Manifest: per-file sha256 + source provenance, so the library repos'
    # CI can verify their vendored copies against a pinned jsonui-cli ref
    # (swift/kotlin have no in-repo diff guard the way ruby does). Only a
    # full default emit describes the complete set — partial --lang or
    # --out runs don't touch it. Deterministic on purpose (sorted, no
    # timestamps, no version string): it changes iff the emitted bytes or
    # the SSoT source change, and CI fails when the committed copy goes
    # stale, same as the fixture-freshness gate.
    if args.lang == "all" and not args.out:
        try:
            source_label = str(definitions.relative_to(repo_root))
        except ValueError:
            source_label = definitions.name
        manifest = {
            "_comment": (
                "sha256 manifest of the attr-codegen emit. Committed so "
                "SwiftJsonUI / KotlinJsonUI CI can verify their vendored "
                "attribute tables against a pinned jsonui-cli ref. "
                "Regenerate: jui generate attr-bindings --lang all "
                "(re-vendor and manifest belong in the same commit)."
            ),
            "generatedBy": "jui generate attr-bindings --lang all",
            "source": {
                "file": source_label,
                "sha256": hashlib.sha256(definitions.read_bytes()).hexdigest(),
            },
            "files": {key: manifest_files[key] for key in sorted(manifest_files)},
        }
        manifest_path = repo_root / "build" / "attr_codegen" / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[manifest] wrote {manifest_path} ({len(manifest_files)} file hashes)")

    print(
        f"\nComponents: {component_count} (+ common), attributes: "
        f"{common_count} common + {component_attr_count} component-level, "
        f"skipped: {len(model.skipped)}"
    )
    if model.skipped:
        print("Skipped (see skipped_attributes.json):")
        for s in model.skipped:
            print(f"  - {s.component}.{s.name}: {s.reason}")
    return 0


def _cmd_generate_api(args: argparse.Namespace) -> int:
    """Preview / drive the swagger → DTO + Domain pipeline.

    v1 only supports ``--dry-run`` (returns the filter result + planned
    file list without writing). A future ``jui g api`` without ``--dry-run``
    will trigger the same emit path as ``jui build`` for the API model
    portion only (use case 1 in the v3 plan §7 Phase 4). For now,
    without ``--dry-run`` the user is pointed to ``jui build``.
    """
    import json

    from ..core.api_model_sync import (
        collect_docs,
        has_planner,
        plan_for,
        planners_for,
    )
    from ..core.config_manager import ConfigManager
    from ..core.openapi_loader import OpenAPILoadError

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        msg = "jui.config.json not found. Run 'jui init' first."
        if getattr(args, "as_json", False):
            print(json.dumps({"error": msg}, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {msg}")
        return 1

    if not args.dry_run:
        # Without --dry-run we don't write here either — `jui build` is the
        # canonical write path for the full pipeline. Surface that.
        msg = (
            "`jui g api` currently supports --dry-run only. "
            "Use `jui build` to actually write DTO + Domain files."
        )
        if getattr(args, "as_json", False):
            print(json.dumps({"error": msg}, indent=2, ensure_ascii=False))
        else:
            print(msg)
        return 1

    config = config_mgr.load()
    platforms = config.get("platforms") or {}

    # Loader returns docs with kept/filtered_out already populated.
    try:
        docs = collect_docs(config_mgr)
    except OpenAPILoadError as e:
        payload = {
            "error": str(e),
            "code": getattr(e, "code", "openapi-load-error"),
            "source": getattr(e, "source", ""),
            "pointer": getattr(e, "pointer", ""),
        }
        if getattr(args, "as_json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR [{payload['code']}]: {payload['error']}")
        return 1

    selected_platforms = (
        [args.platform] if args.platform else planners_for(args)
    )

    swagger_files = [
        {
            "source_path": d.source_path,
            "title": d.title,
            "version": d.version,
            "kept": sorted(s.name for s in d.schemas) + sorted(e.name for e in d.enums),
            "filtered_out": sorted(d.filtered_out),
            "skip_domain_matches": sorted(d.skip_domain_overrides),
        }
        for d in docs
    ]

    per_platform: dict[str, dict] = {}
    for platform in selected_platforms:
        if platform not in platforms or not has_planner(platform):
            continue
        try:
            plan = plan_for(platform, config_mgr, platforms[platform], docs)
        except OpenAPILoadError as e:
            per_platform[platform] = {"error": str(e)}
            continue
        per_platform[platform] = {
            "would_write_dto": sorted(str(p) for p in plan.expected_files),
            "would_write_domain_scaffold": sorted(str(p) for p in plan.domain_scaffolds),
        }

    payload = {
        "filter_active": any(d.filtered_out or d.skip_domain_overrides for d in docs),
        "swagger_files": swagger_files,
        "platforms": per_platform,
    }

    if getattr(args, "as_json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        # Human-readable summary
        for sf in swagger_files:
            print(f"swagger: {sf['source_path']}")
            print(f"  title:   {sf['title']} v{sf['version']}")
            print(f"  kept:    {len(sf['kept'])} schemas/enums")
            print(f"  excluded: {len(sf['filtered_out'])}")
            if sf["skip_domain_matches"]:
                print(f"  skip_domain: {', '.join(sf['skip_domain_matches'])}")
        for platform, info in per_platform.items():
            if "error" in info:
                print(f"\n[{platform}] ERROR: {info['error']}")
                continue
            dtos = info["would_write_dto"]
            doms = info["would_write_domain_scaffold"]
            print(f"\n[{platform}] would write {len(dtos)} DTO files, {len(doms)} domain scaffolds")
    return 0


def _spec_matches_file(sf, spec_dir, requested: str) -> bool:
    """--file accepts either the bare filename (login.spec.json) or a path
    relative to spec_directory (learn/installation.spec.json). The bare-name
    form is kept for backward compatibility with flat spec directories."""
    try:
        rel = sf.resolve().relative_to(spec_dir.resolve()).as_posix()
    except ValueError:
        rel = sf.name
    return rel == requested or sf.name == requested


def _cmd_generate_project(args: argparse.Namespace) -> int:
    """Execute jui g project."""
    from ..core.config_manager import ConfigManager
    from ..core.spec_extractor import extract_screen_spec
    from ..core.type_mapper import TypeMapper
    from ..core.repository_aggregator import RepositoryAggregator
    from ..core.parent_spec_merger import ParentSpecMerger
    from ..generators.layout_generator import LayoutGenerator
    from ..generators.cell_layout_generator import CellLayoutGenerator
    from ..generators.ios_generator import IosGenerator
    from ..generators.android_generator import AndroidGenerator
    from ..generators.web_generator import WebGenerator
    from ..core.diff_checker import DiffChecker

    import json
    from pathlib import Path

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    config = config_mgr.load()
    spec_dir = config_mgr.spec_directory

    # Collect spec files. --file scopes PER-SCREEN artifacts only (the
    # generation loop below filters on args.file); the aggregated
    # Repository / UseCase protocols are built from every spec in the
    # project, so all specs are always collected and parsed — otherwise a
    # single-spec run would silently rewrite the aggregated protocols with
    # just that spec's methods.
    if args.file:
        requested = spec_dir / args.file
        if not requested.exists():
            print(f"ERROR: Spec file not found: {requested}")
            return 1
        spec_files = sorted(spec_dir.glob("*.spec.json"))
        if requested not in spec_files:
            # --file may point into a subdirectory of spec_directory
            spec_files.append(requested)
        print(f"Found {len(spec_files)} spec file(s) "
              f"(generating {args.file}; aggregation uses all)")
    else:
        spec_files = sorted(spec_dir.glob("*.spec.json"))
        if not spec_files:
            print(f"No spec files found in {spec_dir}")
            return 1
        print(f"Found {len(spec_files)} spec file(s)")

    # Validate specs
    config_mgr.ensure_document_tools_importable()
    try:
        from document_tools.jsonui_doc_cli.spec_doc.validator import SpecValidator
        validator = SpecValidator()
        for sf in spec_files:
            result = validator.validate_file(sf)
            if not result.is_valid:
                print(f"\nERROR: Validation failed for {sf.name}:")
                for e in result.errors:
                    print(f"  {e}")
                return 1
            for w in result.warnings:
                print(f"  {w}")
    except ImportError:
        print("WARNING: document_tools not available, skipping validation")

    # Load type mapper
    type_map_path = Path(args.type_map) if args.type_map else config_mgr.type_map_file
    type_mapper = TypeMapper(type_map_path)

    # Resolve sub-spec paths referenced by any parent_spec (they should
    # not be generated on their own — they're merged into the parent).
    sub_spec_paths: set[Path] = set()
    for sf in spec_files:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                head = json.load(f)
        except json.JSONDecodeError:
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

    # Parse all specs (merging parent_spec + sub-specs as we go)
    all_specs = []
    for sf in spec_files:
        if sf.resolve() in sub_spec_paths:
            # Skip sub-specs — they're represented by their parent
            continue
        with open(sf, "r", encoding="utf-8") as f:
            spec_data = json.load(f)

        if spec_data.get("type") == "screen_parent_spec":
            merge_result = merger.merge_from_file(sf)
            if merge_result.has_conflicts:
                # First-write-wins is already applied inside ParentSpecMerger.merge,
                # so merge_result.spec is usable. Surface the conflicts as warnings
                # and continue — halting the whole project generate over a single
                # parent's overlap would block unrelated specs from regenerating.
                print(f"\nWARNING: parent_spec merge conflicts in {sf.name} (kept first-write-wins):")
                for c in merge_result.conflicts:
                    print(f"  {c.path}: {c.message}")
            spec_data = merge_result.spec

        screen_spec = extract_screen_spec(spec_data, sf)
        all_specs.append((sf, screen_spec))

    if args.file:
        # The generation loop scopes on args.file — fail loudly here if the
        # requested spec won't match anything (e.g. it is a sub-spec that
        # was folded into its parent) instead of silently generating nothing.
        if not any(_spec_matches_file(sf, spec_dir, args.file)
                   for sf, _ in all_specs):
            if (spec_dir / args.file).resolve() in sub_spec_paths:
                print(f"ERROR: {args.file} is a sub-spec of a parent_spec — "
                      f"generate the parent spec instead.")
            else:
                print(f"ERROR: {args.file} did not yield a screen spec.")
            return 1

    # Aggregate repositories / use cases across all specs
    aggregator = RepositoryAggregator()
    for sf, screen_spec in all_specs:
        aggregator.add_spec(sf.name, screen_spec)

    try:
        aggregated = aggregator.aggregate()
    except ValueError as e:
        print(f"\nERROR: {e}")
        return 1
    if aggregated.has_conflicts:
        # Same philosophy as parent_spec merge conflicts: warn and proceed
        # with the first-seen signature so an in-progress rename doesn't
        # halt the whole project regenerate.
        print(
            f"\nWARNING: {len(aggregated.conflicts)} aggregator signature "
            f"conflict(s) (kept first-write-wins):"
        )
        for c in aggregated.conflicts:
            print(c.format())
            print()

    # Save cache
    aggregator.save_cache(config_mgr.project_root / ".jui_cache.json", spec_files)

    # Determine target platforms
    platforms = _resolve_platforms(args, config)

    diff_checker = DiffChecker()
    generated_files = []
    skipped_files = []
    warnings = []
    errors: list[str] = []

    # Per-screen generation (Layout + ViewModel)
    for sf, screen_spec in all_specs:
        if args.file and not _spec_matches_file(sf, spec_dir, args.file):
            continue

        print(f"\nProcessing: {sf.name} ({screen_spec.name})")

        # Layout JSON — output to shared layouts_directory (single source of truth)
        # Skip when spec uses layoutFile mode with no components (layout JSON is
        # authored externally — generating would overwrite it with a stub).
        # The @generated marker is injected during `jui build` distribution,
        # not here, so both spec-generated and externally-authored source
        # layouts remain marker-free and hand-editable.
        uses_external_layout = (
            screen_spec.layout_file and not screen_spec.layout_components
        )
        if uses_external_layout:
            print(f"  Skipped layout (authored externally): {screen_spec.layout_file}.json")
        elif not args.skip_layout:
            layout_gen = LayoutGenerator(type_mapper)
            layout_json = layout_gen.generate(screen_spec)
            cell_gen = CellLayoutGenerator(layout_gen)
            cell_entries = _extract_cell_entries(sf)

            layouts_dir = config_mgr.layouts_directory
            if screen_spec.layout_file:
                layout_path = layouts_dir / f"{screen_spec.layout_file}.json"
            else:
                snake_name = _to_snake_case(screen_spec.name)
                layout_path = layouts_dir / f"{snake_name}.json"

            # Hard error if the existing Layout JSON has data entries that
            # won't survive the regen — spec is the single source of truth
            # for data shape (Layout JSON → spec is never automatic), so any
            # orphan means the author needs to either declare it in
            # stateManagement.uiVariables or consciously drop it.
            orphans: list[tuple[str, str]] = []
            if layout_path.exists():
                orphans = _find_data_orphans(layout_path, layout_json)

            if orphans:
                rel = layout_path.relative_to(config_mgr.project_root)
                lines = [
                    f"ERROR: {rel}: existing Layout JSON has data entries "
                    f"not declared in spec.uiVariables:"
                ]
                for name, klass in orphans:
                    lines.append(f"  - data.{name} ({klass})")
                lines.append(
                    "  → add each to stateManagement.uiVariables, or "
                    "delete the entry from the Layout JSON's data section "
                    "to acknowledge the removal. Layout JSON is regenerated "
                    "from spec and these entries would otherwise be silently "
                    "dropped."
                )
                errors.append("\n".join(lines))
                skipped_files.append(layout_path)
            elif args.dry_run:
                print(f"  [DRY-RUN] Would create: {layout_path}")
            else:
                layout_path.parent.mkdir(parents=True, exist_ok=True)
                with open(layout_path, "w", encoding="utf-8") as f:
                    json.dump(layout_json, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                generated_files.append(layout_path)
                print(f"  Created: {layout_path.relative_to(config_mgr.project_root)}")

            # Generate cell Layout JSON when opted in — for every declared
            # Collection (structure.collection + structure.collections[]).
            for coll_def, coll_cell_entry in zip(screen_spec.collections, cell_entries):
                if not cell_gen.should_generate(coll_def):
                    continue
                cell_json = cell_gen.generate(coll_def, screen_spec)
                cell_path = cell_gen.resolve_output_path(
                    coll_def,
                    layouts_dir,
                    coll_cell_entry,
                )
                if args.dry_run:
                    print(f"  [DRY-RUN] Would create cell: {cell_path}")
                else:
                    cell_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cell_path, "w", encoding="utf-8") as f:
                        json.dump(cell_json, f, indent=2, ensure_ascii=False)
                        f.write("\n")
                    generated_files.append(cell_path)
                    print(f"  Created cell: {cell_path.relative_to(layouts_dir)}")

        # Extract subdir from metadata.layoutFile (e.g. "mypage/change_email_sheet" -> "mypage")
        vm_subdir = ""
        if screen_spec.layout_file and "/" in screen_spec.layout_file:
            vm_subdir = "/".join(screen_spec.layout_file.split("/")[:-1])

        # ViewModel (per platform)
        for platform, pconfig in platforms.items():
            generator = _get_generator(platform, pconfig, config_mgr, type_mapper)
            if not generator:
                continue

            # ViewModel declaration (auto-update)
            decl_path = generator.viewmodel_protocol_path(screen_spec.name, vm_subdir)
            if platform == "web":
                # Same filter as jui build: only <Name>Data members may be
                # initialized in the Base's updateData literal (TS2353).
                from ..generators.web_generator import (
                    collect_layout_event_names,
                    resolve_layout_path,
                )
                decl_content = generator.generate_viewmodel_protocol(
                    screen_spec,
                    layout_event_names=collect_layout_event_names(
                        resolve_layout_path(
                            config_mgr.layouts_directory, screen_spec
                        )
                    ),
                )
            else:
                decl_content = generator.generate_viewmodel_protocol(screen_spec)

            # Findings raised while emitting (e.g. a var the generated Base
            # can only declare with `!`) join this command's warning stream.
            for w in getattr(generator, "warnings", []):
                warnings.append(f"WARNING [spec:{w.spec_name}] {w.message}")
            if hasattr(generator, "warnings"):
                generator.warnings.clear()

            if decl_path.exists() and not args.force:
                diff = diff_checker.check(decl_path, decl_content)
                if diff:
                    warnings.append(f"WARNING: {decl_path.relative_to(config_mgr.project_root)}\n{diff}")
                else:
                    skipped_files.append(decl_path)
            else:
                if args.dry_run:
                    print(f"  [DRY-RUN] Would create: {decl_path}")
                else:
                    decl_path.parent.mkdir(parents=True, exist_ok=True)
                    decl_path.write_text(decl_content, encoding="utf-8")
                    generated_files.append(decl_path)

            # ViewModel implementation (never overwrite)
            impl_path = generator.viewmodel_impl_path(screen_spec.name, vm_subdir)
            if impl_path.exists():
                skipped_files.append(impl_path)
            else:
                impl_content = generator.generate_viewmodel_impl(screen_spec)
                if args.dry_run:
                    print(f"  [DRY-RUN] Would create: {impl_path}")
                else:
                    impl_path.parent.mkdir(parents=True, exist_ok=True)
                    impl_path.write_text(impl_content, encoding="utf-8")
                    generated_files.append(impl_path)

    # Aggregated Repository / UseCase generation
    print("\nGenerating aggregated Repository / UseCase files...")
    for platform, pconfig in platforms.items():
        generator = _get_generator(platform, pconfig, config_mgr, type_mapper)
        if not generator:
            continue

        has_separate_protocol = getattr(generator, "has_separate_protocol", True)

        for repo_name, repo_def in aggregated.repositories.items():
            filtered_repo = _filter_for_platform(repo_def, platform)
            if not filtered_repo.methods:
                continue

            # Declaration (skip when generator has no separate protocol file)
            if has_separate_protocol:
                decl_path = generator.repository_protocol_path(repo_name)
                decl_content = generator.generate_repository_protocol(repo_name, filtered_repo)
                if decl_path.exists() and not args.force:
                    diff = diff_checker.check(decl_path, decl_content)
                    if diff:
                        warnings.append(f"WARNING: {decl_path.relative_to(config_mgr.project_root)}\n{diff}")
                    else:
                        skipped_files.append(decl_path)
                else:
                    if not args.dry_run:
                        decl_path.parent.mkdir(parents=True, exist_ok=True)
                        decl_path.write_text(decl_content, encoding="utf-8")
                        generated_files.append(decl_path)

            # Implementation
            impl_path = generator.repository_impl_path(repo_name)
            if impl_path.exists():
                skipped_files.append(impl_path)
            elif not args.dry_run:
                impl_content = generator.generate_repository_impl(repo_name, filtered_repo)
                impl_path.parent.mkdir(parents=True, exist_ok=True)
                impl_path.write_text(impl_content, encoding="utf-8")
                generated_files.append(impl_path)

        for uc_name, uc_def in aggregated.use_cases.items():
            filtered_uc = _filter_for_platform(uc_def, platform)
            if not filtered_uc.methods:
                continue

            # Declaration (skip when generator has no separate protocol file)
            if has_separate_protocol:
                decl_path = generator.usecase_protocol_path(uc_name)
                decl_content = generator.generate_usecase_protocol(uc_name, filtered_uc)
                if decl_path.exists() and not args.force:
                    diff = diff_checker.check(decl_path, decl_content)
                    if diff:
                        warnings.append(f"WARNING: {decl_path.relative_to(config_mgr.project_root)}\n{diff}")
                    else:
                        skipped_files.append(decl_path)
                else:
                    if not args.dry_run:
                        decl_path.parent.mkdir(parents=True, exist_ok=True)
                        decl_path.write_text(decl_content, encoding="utf-8")
                        generated_files.append(decl_path)

            # Implementation
            impl_path = generator.usecase_impl_path(uc_name)
            if impl_path.exists():
                skipped_files.append(impl_path)
            elif not args.dry_run:
                impl_content = generator.generate_usecase_impl(uc_name, filtered_uc)
                impl_path.parent.mkdir(parents=True, exist_ok=True)
                impl_path.write_text(impl_content, encoding="utf-8")
                generated_files.append(impl_path)

    # Summary
    print(f"\n--- Summary ---")
    print(f"  Generated: {len(generated_files)} file(s)")
    print(f"  Skipped (existing): {len(skipped_files)} file(s)")
    if warnings:
        print(f"  Warnings: {len(warnings)}")
        for w in warnings:
            print(f"\n{w}")

    if errors:
        print(f"\n--- Errors ---")
        print(f"  {len(errors)} spec(s) had unresolved Data orphans:")
        for e in errors:
            print(f"\n{e}")
        return 1

    return 0


def _filter_for_platform(definition, platform: str):
    """Return a copy of a Repository/UseCase with only methods for *platform*.

    A method with an empty `platforms` list is considered available on every
    platform (default behavior before this feature).
    """
    from dataclasses import replace
    kept = [
        m for m in definition.methods
        if not m.platforms or platform in m.platforms
    ]
    return replace(definition, methods=kept)


def _resolve_platforms(args: argparse.Namespace, config: dict) -> dict:
    """Resolve which platforms to generate for."""
    all_platforms = config.get("platforms", {})
    if args.ios_only:
        return {k: v for k, v in all_platforms.items() if k == "ios"}
    if args.android_only:
        return {k: v for k, v in all_platforms.items() if k == "android"}
    if args.web_only:
        return {k: v for k, v in all_platforms.items() if k == "web"}
    return all_platforms


def _get_layout_path(platform: str, pconfig: dict, screen_name: str, config_mgr: ConfigManager) -> Path:
    """Get the layout JSON path for a platform."""
    root = config_mgr.project_root / pconfig["root"]
    snake_name = _to_snake_case(screen_name)
    if platform == "android":
        return root / "app/src/main/assets/Layouts" / f"{snake_name}.json"
    elif platform == "web":
        return root / "src/Layouts" / f"{snake_name}.json"
    else:  # ios
        return root / "Layouts" / f"{snake_name}.json"


def _get_generator(platform: str, pconfig: dict, config_mgr, type_mapper):
    """Get the appropriate generator for a platform."""
    from ..generators.ios_generator import IosGenerator
    from ..generators.android_generator import AndroidGenerator
    from ..generators.web_generator import WebGenerator

    root = config_mgr.project_root / pconfig["root"]
    if platform == "ios":
        return IosGenerator(root, pconfig, type_mapper)
    elif platform == "android":
        return AndroidGenerator(root, pconfig, type_mapper)
    elif platform == "web":
        return WebGenerator(root, pconfig, type_mapper)
    return None


def _find_data_orphans(
    existing_layout_path,
    new_layout_json: dict,
) -> list[tuple[str, str]]:
    """Return ``(name, class)`` pairs that are present in the existing
    Layout JSON's ``data`` section but not in the freshly-generated one.

    Used to surface migration regressions — e.g. spec event_handlers used
    to emit callbacks into Data but no longer do, so the next regen
    silently loses those entries unless the author migrated them to
    ``uiVariables``.
    """
    import json as _json

    try:
        with open(existing_layout_path, "r", encoding="utf-8") as f:
            old = _json.load(f)
    except (OSError, ValueError):
        return []

    old_data = old.get("data") or []
    new_data = new_layout_json.get("data") or []
    if not isinstance(old_data, list) or not isinstance(new_data, list):
        return []

    new_names = {
        entry.get("name") for entry in new_data if isinstance(entry, dict)
    }
    orphans: list[tuple[str, str]] = []
    for entry in old_data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name and name not in new_names:
            orphans.append((name, entry.get("class", "?")))
    return orphans


def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    import re
    s = re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")
    return s


def _extract_cell_entries(spec_file: Path) -> list[dict | None]:
    """Raw ``cell`` dicts for structure.collection + structure.collections[].

    Used by the cell layout generator to resolve output paths (``layout``
    field). The list is aligned with ``ScreenSpec.collections`` — both use
    the same "non-empty dict" filter over the same slots.
    """
    import json as _json

    try:
        with open(spec_file, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except (OSError, ValueError):
        return []
    structure = data.get("structure") or {}
    entries: list[dict | None] = []
    for coll in [structure.get("collection"), *(structure.get("collections") or [])]:
        if isinstance(coll, dict) and coll:
            cell = coll.get("cell")
            entries.append(cell if isinstance(cell, dict) else None)
    return entries


def _cmd_generate_screen(args: argparse.Namespace) -> int:
    """Execute jui g screen."""
    from ..core.config_manager import ConfigManager
    import json

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    spec_dir = config_mgr.spec_directory
    spec_dir.mkdir(parents=True, exist_ok=True)

    for name in args.names:
        snake_name = _to_snake_case(name)
        file_path = spec_dir / f"{snake_name}.spec.json"
        if file_path.exists():
            print(f"SKIP: {file_path.name} already exists")
            continue

        display_name = args.display_name if args.display_name and len(args.names) == 1 else name
        template = _screen_spec_template(name, display_name)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Created: {file_path}")

    return 0


def _screen_spec_template(name: str, display_name: str) -> dict:
    """Create a minimal screen spec template."""
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": name,
            "displayName": display_name,
            "description": "",
        },
        "structure": {
            "components": [
                {
                    "type": "View",
                    "id": "root_view",
                    "description": "Root container",
                }
            ],
            "layout": {
                "root": "root_view",
                "children": [],
            },
        },
        "dataFlow": {
            "repositories": [],
            "useCases": [],
            "apiEndpoints": [],
        },
        "stateManagement": {
            "uiVariables": [],
            "eventHandlers": [],
            "displayLogic": [],
        },
    }


def _cmd_generate_converter(args: argparse.Namespace) -> int:
    """Execute jui g converter."""
    from ..core.config_manager import ConfigManager

    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return 1

    config = config_mgr.load()
    platforms = config.get("platforms", {})
    skip_existing = bool(getattr(args, "skip_existing", False))

    # Converters are emitted per platform — with no platform configured the
    # generation loop runs zero times, which used to exit 0 without creating
    # any file. Fail loudly instead.
    if not any(p in ("ios", "android", "web") for p in platforms):
        print("ERROR: No platforms configured in jui.config.json — "
              "run platform setup (platforms.ios / platforms.android / platforms.web) "
              "before generating converters.")
        return 1

    if args.all_specs:
        comp_dir = config_mgr.component_spec_directory
        specs_to_process = sorted(comp_dir.glob("*.component.json"))
        if not specs_to_process:
            print(f"No component specs found in {comp_dir}")
            return 1
        return _run_converters_from_specs(
            specs_to_process, platforms, config_mgr, skip_existing=skip_existing
        )
    if args.from_spec:
        # Accept either a bare filename (resolved against component_spec_directory)
        # or a direct path to the spec file — joining a cwd-relative path onto
        # component_spec_directory used to produce a doubled path that never exists.
        direct_path = Path(args.from_spec)
        if direct_path.is_file():
            spec_path = direct_path
        else:
            spec_path = config_mgr.component_spec_directory / args.from_spec
        if not spec_path.exists():
            print(f"ERROR: Component spec not found: {spec_path}")
            return 1
        return _run_converters_from_specs(
            [spec_path], platforms, config_mgr, skip_existing=skip_existing
        )
    if args.name:
        # Direct mode — pass through to platform tools.
        return _run_converter_direct(
            args.name, args.attributes, args.container, platforms, config_mgr,
            skip_existing=skip_existing,
        )
    print("Usage: jui g converter <name> | --from <spec> | --all")
    return 1


def _run_converters_from_specs(
    specs_to_process: list,
    platforms: dict,
    config_mgr,
    *,
    skip_existing: bool = False,
) -> int:
    """Iterate component spec files and invoke each platform's `g converter`.

    Also used by `jui build` to auto-generate converters before the per-platform
    build phase — callers pass ``skip_existing=True`` so the platform tools
    leave existing converter files untouched instead of prompting.
    """
    import json

    failed = []
    seen_names = set()
    for spec_path in specs_to_process:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_data = json.load(f)

        comp_name = spec_data.get("metadata", {}).get("name", spec_path.stem)
        if comp_name in seen_names:
            continue
        seen_names.add(comp_name)

        props = spec_data.get("props", {}).get("items", [])
        attr_pairs = [
            (p["name"], p["type"]) for p in props
            if "name" in p and "type" in p
        ]
        # stateManagement.exposedEvents are callback props — merge them into
        # the attribute list as Callback-typed attrs so the platform
        # generators wire `"onFoo": "@{handler}"` bindings (unknown types
        # fall through to binding-only in every generator, which is exactly
        # what an event needs).
        seen_attrs = {name for name, _ in attr_pairs}
        events = (spec_data.get("stateManagement") or {}).get("exposedEvents") or []
        for event in events:
            event_name = event.get("name") if isinstance(event, dict) else None
            if event_name and event_name not in seen_attrs:
                seen_attrs.add(event_name)
                attr_pairs.append((event_name, "Callback"))
        attrs = ",".join(f"{name}:{type_}" for name, type_ in attr_pairs)
        has_slots = bool(spec_data.get("slots", {}).get("items", []))

        print(f"\nGenerating converter: {comp_name}")
        result = _run_converter_direct(
            comp_name, attrs or None, has_slots, platforms, config_mgr,
            skip_existing=skip_existing,
        )
        if result != 0:
            failed.append(comp_name)

    if failed:
        print(f"\nERROR: Converter generation failed for: {', '.join(failed)}")
        return 1
    return 0


def split_top_level_commas(value: str) -> list[str]:
    """Split a comma-joined attribute list on top-level commas only.

    Spec prop types may themselves contain commas — e.g. the multi-arg
    closure type ``((String, String) -> Void)?`` — so a plain split(',')
    tears one attribute into invalid ``key:type`` fragments. Commas nested
    inside parentheses or brackets belong to the type, not the list.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in value:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _run_converter_direct(
    name: str,
    attributes: str | None,
    container: bool,
    platforms: dict,
    config_mgr,
    *,
    skip_existing: bool = False,
) -> int:
    """Run converter generation on each platform tool.

    Uses ``tool_resolver.resolve_tool`` so project-local installations of
    ``sjui`` / ``kjui`` / ``rjui`` work without the tools being on $PATH.
    When ``skip_existing`` is true, ``JUI_SKIP_EXISTING=1`` is exported —
    the Ruby converter generators read that and bypass their interactive
    "Overwrite? (y/n)" prompt, leaving existing files in place.
    """
    import subprocess

    from ..core.tool_resolver import build_tool_env, resolve_tool

    extra_env = {"JUI_SKIP_EXISTING": "1"} if skip_existing else None

    failed = []
    for platform, pconfig in platforms.items():
        root = config_mgr.project_root / pconfig["root"]
        if platform == "ios":
            tool_name = "sjui"
            cmd = [tool_name, "g", "converter", name]
            if attributes:
                cmd += ["--attributes", attributes]
            if container:
                cmd.append("--container")
        elif platform == "android":
            tool_name = "kjui"
            cmd = [tool_name, "g", "converter", name]
            if attributes:
                for attr in split_top_level_commas(attributes):
                    cmd += ["--attr", attr]
            if container:
                cmd.append("--container")
        elif platform == "web":
            tool_name = "rjui"
            cmd = [tool_name, "g", "converter", name]
            if attributes:
                cmd += ["--attributes", attributes]
            if container:
                cmd.append("--container")
        else:
            continue

        resolved = resolve_tool(tool_name, root)
        actual_cmd = [resolved] + cmd[1:]
        env = build_tool_env(resolved, tool_name, extra=extra_env)

        try:
            result = subprocess.run(actual_cmd, cwd=root, env=env)
        except FileNotFoundError:
            print(f"  WARNING: '{tool_name}' not found (searched local and PATH) — skipping {platform}")
            failed.append(platform)
            continue
        if result.returncode != 0:
            failed.append(platform)

    if failed:
        print(f"  Failed: {', '.join(failed)}")
        return 1
    return 0
