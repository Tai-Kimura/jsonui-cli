#!/usr/bin/env python3
"""
JsonUI Document CLI

Command-line interface for generating documentation from JsonUI test files
and specification documents.
"""

import argparse
import json
import re
import sys
import warnings
from pathlib import Path


def _resolve_layouts_dir_from_config() -> Path | None:
    """Auto-detect layouts_directory from jui.config.json.

    The jsonui-doc bin wrapper only adds ``document_tools/`` to sys.path,
    so ``jui_cli`` isn't importable by default. Insert the sibling
    ``jui_tools/`` directory on demand. Returns None when no config is
    found or import fails, but surfaces the failure reason via warnings
    so silent breakage doesn't reoccur (see bug
    doc-structure-auto-detect-layouts-dir-fails.md).
    """
    try:
        here = Path(__file__).resolve()
        # document_tools/jsonui_doc_cli/cli.py → up 3 → jsonui-cli root
        repo_root = here.parents[2]
        jui_tools_dir = repo_root / "jui_tools"
        if jui_tools_dir.is_dir() and str(jui_tools_dir) not in sys.path:
            sys.path.insert(0, str(jui_tools_dir))

        from jui_cli.core.config_manager import ConfigManager
        config_mgr = ConfigManager()
        if config_mgr.exists():
            return config_mgr.layouts_directory
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"jsonui-doc: layouts_dir auto-detect failed ({exc!r}); "
            "structure section will be empty. Pass --layouts-dir to override.",
            stacklevel=2,
        )
    return None

from . import __version__
from .test_doc import (
    DocumentGenerator,
    generate_schema_reference,
    generate_html_directory,
    get_page_failures,
    get_pages_written,
    generate_mermaid_diagram,
    generate_mermaid_html,
    generate_adapter,
    ADAPTER_PLATFORMS,
)
from .spec_doc import (
    SpecValidator,
    generate_spec_markdown,
    generate_spec_html,
    generate_component_html,
    generate_component_markdown,
    create_spec_file,
    create_component_file,
)
from .figma import fetch_file, fetch_nodes, parse_figma_url, resolve_token, FigmaAPIError
from .figma.api_client import PLAN_CHOICES
from .figma.image_fetcher import fetch_and_download_images


def cmd_generate_doc(args):
    """Handle 'generate doc' command - generate HTML/MD documentation."""
    generator = DocumentGenerator()

    # Determine output format
    output_format = args.format
    if args.output and not output_format:
        ext = Path(args.output).suffix.lower()
        if ext == ".html":
            output_format = "html"
        else:
            output_format = "markdown"
    elif not output_format:
        output_format = "markdown"

    # Handle schema reference
    if args.schema:
        content = generate_schema_reference(format=output_format)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Schema reference written to: {output_path}")
        else:
            print(content)
        return 0

    # Handle test file documentation
    if not args.file:
        print("Error: Either --file or --schema is required", file=sys.stderr)
        return 1

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        output_path = Path(args.output) if args.output else None
        content = generator.generate(file_path, output_path, format=output_format)

        if content:
            print(content)
        else:
            print(f"Documentation written to: {output_path}")

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_html(args):
    """Handle 'generate html' command - generate HTML directory with index."""
    input_dir = Path(args.input)
    output_dir = Path(args.output) if args.output else Path("html")
    title = args.title or "JsonUI Test Documentation"

    # --with-checks: explicit sugar for `check` then `generate html`.
    # Generation must succeed even when checks fail — the drift page is most
    # useful exactly when things drifted (plan 01 §4).
    if getattr(args, "with_checks", False):
        import argparse as _argparse
        check_args = _argparse.Namespace(filter=None, list=False, project=None)
        check_exit = cmd_check(check_args)
        if check_exit != 0:
            print(f"  Note: checks exited {check_exit} "
                  "(mismatch or error) — continuing with generation.")

    # Process multiple --docs options
    docs_dirs = []
    if args.docs:
        for doc_path in args.docs:
            doc_dir = Path(doc_path)
            if not doc_dir.exists():
                print(f"Error: Docs directory not found: {doc_dir}", file=sys.stderr)
                return 1
            docs_dirs.append(doc_dir)

    # Process --figma option
    figma_dir = None
    if args.figma:
        figma_dir = Path(args.figma)
        if not figma_dir.exists():
            print(f"  Warning: Figma directory not found: {figma_dir} (skipping)")
            figma_dir = None

    # Process --app options
    apps = None
    if args.app:
        apps = []
        for app_spec in args.app:
            if ':' not in app_spec:
                print(f"Error: --app must be in 'name:path' format, got: {app_spec}", file=sys.stderr)
                return 1
            name, path_str = app_spec.split(':', 1)
            app_path = Path(path_str)
            if not app_path.exists():
                print(f"Error: App docs directory not found: {app_path}", file=sys.stderr)
                return 1
            apps.append({'name': name.strip(), 'docs_path': app_path})

    # --layouts-dir override (per-spec auto-detection used when absent)
    layouts_dir_override = None
    if hasattr(args, 'layouts_dir') and args.layouts_dir:
        layouts_dir_override = Path(args.layouts_dir)

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        return 1

    print(f"Generating HTML documentation...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}")
    for doc_dir in docs_dirs:
        print(f"  Docs: {doc_dir}")
    if figma_dir:
        print(f"  Figma: {figma_dir}")
    if apps:
        for app in apps:
            print(f"  App: {app['name']} -> {app['docs_path']}")
    print()

    try:
        generate_html_directory(input_dir, output_dir, title, docs_dirs if docs_dirs else None, figma_dir=figma_dir, apps=apps, layouts_dir=layouts_dir_override)
        print()
        # Count every page written, not just the test pages in the return
        # value — the old number was smaller than the lines printed above it,
        # so it could not serve as a "did everything come out?" signal.
        print(f"Generated {get_pages_written()} HTML files")
        print(f"Open {output_dir}/index.html to view documentation")

        failures = get_page_failures()
        if failures:
            # The summary goes to stderr; flush stdout first so it lands
            # after the generation log instead of ahead of it.
            sys.stdout.flush()
            print()
            print(f"{len(failures)} page(s) failed to generate:", file=sys.stderr)
            for f in failures:
                where = f" [{f['source']}]" if f['source'] else ""
                print(f"  {f['kind']} {f['name']}{where}", file=sys.stderr)
                print(f"      {f['error']}", file=sys.stderr)
            if getattr(args, 'allow_partial', False):
                print(
                    "Continuing anyway (--allow-partial). Placeholder pages "
                    "were written in their place.",
                    file=sys.stderr,
                )
                return 0
            print(
                "The documentation is incomplete. Fix the inputs above, or "
                "pass --allow-partial to accept a partial site.",
                file=sys.stderr,
            )
            return 1
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_mermaid(args):
    """Handle 'generate mermaid' command - generate Mermaid flow diagram."""
    input_dir = Path(args.input)
    output_path = Path(args.output) if args.output else None
    title = args.title or "Flow Diagram"
    screens_dir = Path(args.screens) if args.screens else None

    # Determine flows directory
    flows_dir = input_dir / "flows" if (input_dir / "flows").exists() else input_dir

    if not flows_dir.exists():
        print(f"Error: Input directory not found: {flows_dir}", file=sys.stderr)
        return 1

    # Determine screens directory
    if screens_dir is None:
        if (input_dir / "screens").exists():
            screens_dir = input_dir / "screens"
        else:
            screens_dir = flows_dir.parent / "screens"

    print(f"Generating Mermaid diagram...")
    print(f"  Flows: {flows_dir}")
    print(f"  Screens: {screens_dir}")

    # Layout tree (optional): lets the generator tell screens from cells so
    # Collection cells stop being drawn as screens.
    layouts_dir = Path(args.layouts_dir) if getattr(args, "layouts_dir", None) else _resolve_layouts_dir_from_config()

    try:
        if output_path:
            # Generate HTML with embedded Mermaid
            mermaid_code = generate_mermaid_html(flows_dir, output_path, title, screens_dir, layouts_dir)
            print()
            if mermaid_code:
                print(f"Generated: {output_path}")
                print(f"Open in browser to view the diagram")
            else:
                print("No screen transitions found — no diagram written")
        else:
            # Output Mermaid code to stdout
            mermaid_code = generate_mermaid_diagram(flows_dir, screens_dir, layouts_dir)
            print()
            print(mermaid_code)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_generate_adapter(args):
    """Handle 'generate adapter' command - generate adapter files for custom actions."""
    platform = args.platform
    output_dir = Path(args.output) if args.output else Path(".")
    project_name = args.name or "MyApp"

    # Parse custom actions from JSON file if provided
    custom_actions = None
    if args.actions:
        actions_path = Path(args.actions)
        if actions_path.exists():
            with open(actions_path, 'r', encoding='utf-8') as f:
                custom_actions = json.load(f)
                if isinstance(custom_actions, dict):
                    custom_actions = custom_actions.get("actions", [])

    print(f"Generating {platform} adapter...")
    print(f"  Output: {output_dir}")
    print(f"  Project: {project_name}")
    if custom_actions:
        print(f"  Custom actions: {len(custom_actions)}")

    try:
        generated = generate_adapter(
            platform=platform,
            output_dir=output_dir,
            project_name=project_name,
            custom_actions=custom_actions
        )

        print()
        print("Generated files:")
        for name, path in generated.items():
            print(f"  {name}: {path}")

        print()
        print("Next steps:")
        if platform == "ios":
            print("  1. Add JsonUITestAdapter.swift to your UITest target")
            print("  2. Call applyJsonUIConfig() before app.launch()")
            print("  3. Implement your custom action handlers")
        elif platform == "android":
            print("  1. Add JsonUITestAdapter.kt to your androidTest directory")
            print("  2. Call JsonUITestAdapter.configure() before activity launch")
            print("  3. Implement your custom action handlers")
        elif platform == "web":
            print("  1. Import JsonUITestAdapter in your test setup")
            print("  2. Call adapter.configure() before navigation")
            print("  3. Implement your custom action handlers")

        print()
        print(f"Schema file: {generated.get('schema')}")
        print("  Use this schema in your test JSON files for validation:")
        print('  { "$schema": "./jsonui-test-custom.schema.json", ... }')

        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_validate_spec(args):
    """Handle 'validate spec' command - validate screen specification JSON."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: Path not found: {file_path}", file=sys.stderr)
        return 1

    # A directory validates every spec under it, the way `generate spec`
    # already accepts one. Without this the standing "is the whole project
    # still clean?" check had to be a hand-written loop, and the asymmetry
    # only announced itself as Errno 21.
    if file_path.is_dir():
        return cmd_validate_spec_batch(file_path)

    validator = SpecValidator()
    result = validator.validate_file(file_path)

    if not validator._custom_rules.is_empty:
        print(f"Using custom rules: {validator._custom_rules.config_path}")

    print(f"\nValidating: {file_path}")
    print("=" * 50)

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(error)

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(warning)

    print()
    if result.is_valid:
        print("Result: PASSED")
    else:
        print("Result: FAILED")

    print(f"Errors: {result.error_count}, Warnings: {result.warning_count}")

    return 0 if result.is_valid else 1


def cmd_validate_spec_batch(input_dir: Path):
    """Validate every .spec.json under *input_dir*."""
    spec_files = sorted(input_dir.rglob("*.spec.json"))
    if not spec_files:
        print(f"Error: No .spec.json files found in {input_dir}", file=sys.stderr)
        return 1

    validator = SpecValidator()
    if not validator._custom_rules.is_empty:
        print(f"Using custom rules: {validator._custom_rules.config_path}")

    print(f"\nValidating {len(spec_files)} spec file(s) in: {input_dir}")
    print("=" * 50)

    failed: list[Path] = []
    total_errors = 0
    total_warnings = 0
    for spec_file in spec_files:
        result = validator.validate_file(spec_file)
        total_errors += result.error_count
        total_warnings += result.warning_count
        if not result.is_valid:
            failed.append(spec_file)
        if result.errors or result.warnings:
            print(f"\n{spec_file}")
            for error in result.errors:
                print(error)
            for warning in result.warnings:
                print(warning)

    # Only reachable in batch mode, and only worth reaching there: one
    # repository method declared by several screens is how a shared component
    # records where it is used, and a disagreement between those declarations
    # is invisible from any single file. Both consumer lanes that looked found
    # real defects of this shape by hand.
    cross = _cross_spec_disagreements(spec_files)
    if cross:
        print()
        for key, entries in cross:
            print(f"[ERROR] {key} is declared differently by "
                  f"{len(entries)} spec(s) — one implementation cannot match "
                  f"more than one of them:")
            for source, description in entries:
                print(f"    {source}: {description}")
        total_errors += len(cross)

    print()
    if failed or cross:
        print(f"Result: FAILED ({len(failed)} of {len(spec_files)} spec file(s)"
              + (f", {len(cross)} cross-spec disagreement(s)" if cross else "")
              + ")")
        for spec_file in failed:
            print(f"  - {spec_file}")
    else:
        print(f"Result: PASSED ({len(spec_files)} spec file(s))")
    print(f"Errors: {total_errors}, Warnings: {total_warnings}")

    return 1 if (failed or cross) else 0


def _cross_spec_disagreements(spec_files):
    """Same declaration, different content, across files. `[]` when unknowable.

    Silent rather than approximate when `shared/core` is not in the tool tree:
    a partial answer here reads exactly like agreement.
    """
    from . import shared_core
    canon = shared_core.openapi_canonical()
    if canon is None:
        return []
    specs = []
    for path in spec_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                specs.append((path.name, json.load(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return canon.cross_spec_disagreements(specs)


def cmd_generate_spec(args):
    """Handle 'generate spec' command - generate MD/HTML from spec JSON."""
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: Path not found: {input_path}", file=sys.stderr)
        return 1

    # Check if input is a directory (batch mode)
    if input_path.is_dir():
        return cmd_generate_spec_batch(args, input_path)

    # Single file mode
    file_path = input_path

    # Load and validate spec
    validator = SpecValidator()
    result = validator.validate_file(file_path)

    if not result.is_valid:
        print(f"Error: Validation failed for {file_path}", file=sys.stderr)
        for error in result.errors:
            print(error, file=sys.stderr)
        return 1

    spec_data = result.spec_data

    # Determine output format
    output_format = args.format
    if args.output and not output_format:
        ext = Path(args.output).suffix.lower()
        if ext == ".html":
            output_format = "html"
        else:
            output_format = "markdown"
    elif not output_format:
        output_format = "markdown"

    # Resolve layouts_directory for layoutFile import
    if hasattr(args, 'layouts_dir') and args.layouts_dir:
        layouts_dir = Path(args.layouts_dir)
    else:
        layouts_dir = _resolve_layouts_dir_from_config()

    # Generate content
    if output_format == "html":
        content = generate_spec_html(spec_data, layouts_dir=layouts_dir)
    else:
        content = generate_spec_markdown(spec_data, layouts_dir=layouts_dir)

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Generated: {output_path}")
    else:
        print(content)

    return 0


def cmd_generate_spec_batch(args, input_dir: Path):
    """Handle batch generation of spec docs from a directory.

    `--format` is honoured here as it is for a single file. It used to be
    read only on the single-file path, so `--format markdown` over a
    directory wrote HTML into `.html` files and said nothing.

    Its ABSENCE still means HTML, which is not what the single-file path
    does. There is nothing to infer from: the output is a directory, so
    there is no extension to read a format off. Everything about the batch
    form says HTML — the default output directory is `<parent>/html`, the
    documented invocation is `generate spec docs/specs/ -o docs/html`, and
    the progress line announces HTML — so defaulting to markdown would
    change what that documented command produces rather than fix anything.
    The help text is what was wrong, and it now says this.
    """
    output_dir = Path(args.output) if args.output else input_dir.parent / "html"
    output_format = args.format or "html"
    to_html = output_format == "html"
    suffix = ".html" if to_html else ".md"

    # Find all .spec.json files (recursive to support subdirectories)
    spec_files = list(input_dir.rglob("*.spec.json"))
    if not spec_files:
        print(f"Error: No .spec.json files found in {input_dir}", file=sys.stderr)
        return 1

    # Resolve layouts_directory for layoutFile import
    if hasattr(args, 'layouts_dir') and args.layouts_dir:
        layouts_dir = Path(args.layouts_dir)
    else:
        layouts_dir = _resolve_layouts_dir_from_config()

    print(f"Generating {output_format} for {len(spec_files)} spec files...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    validator = SpecValidator()
    success_count = 0
    error_count = 0

    for spec_file in sorted(spec_files):
        result = validator.validate_file(spec_file)

        if not result.is_valid:
            print(f"  FAILED: {spec_file.relative_to(input_dir)}")
            for error in result.errors:
                print(f"    {error}")
            error_count += 1
            continue

        # layouts_dir is passed either way so layoutFile import works
        content = (generate_spec_html(result.spec_data, layouts_dir=layouts_dir)
                   if to_html
                   else generate_spec_markdown(result.spec_data, layouts_dir=layouts_dir))

        # Preserve subdirectory structure in output
        rel_path = spec_file.relative_to(input_dir)
        output_name = rel_path.with_name(rel_path.name.replace(".spec.json", suffix))
        output_path = output_dir / output_name

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"  OK: {rel_path} -> {output_name}")
        success_count += 1

    print()
    print(f"Generated: {success_count} files")
    if error_count > 0:
        print(f"Failed: {error_count} files")
        return 1

    return 0


def cmd_init_spec(args):
    """Handle 'init spec' command - create a new screen specification template."""
    screen_name = args.name
    display_name = args.display_name
    output_dir = Path(args.output) if args.output else None
    file_path = getattr(args, "file_path", None)

    # Validate screen name format (PascalCase)
    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', screen_name):
        print(f"Error: Screen name must be PascalCase (e.g., 'Login', 'UserProfile')", file=sys.stderr)
        print(f"  Got: {screen_name}", file=sys.stderr)
        return 1

    try:
        output_path = create_spec_file(screen_name, output_dir, display_name, file_path=file_path)
        print(f"Created: {output_path}")
        print()
        print("Next steps:")
        print(f"  1. Edit {output_path} to fill in the specification")
        print(f"  2. Run: jsonui-doc validate spec {output_path}")
        print(f"  3. Run: jsonui-doc generate spec {output_path} -o docs/screens/html/{screen_name.lower()}.html")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_init_component(args):
    """Handle 'init component' command - create a new component specification template."""
    component_name = args.name
    display_name = args.display_name
    category = args.category or "other"
    output_dir = Path(args.output) if args.output else None

    # Validate component name format (PascalCase)
    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', component_name):
        print(f"Error: Component name must be PascalCase (e.g., 'UserCard', 'SearchBar')", file=sys.stderr)
        print(f"  Got: {component_name}", file=sys.stderr)
        return 1

    try:
        output_path = create_component_file(component_name, output_dir, display_name, category)
        print(f"Created: {output_path}")
        print()
        print("Next steps:")
        print(f"  1. Edit {output_path} to fill in the specification")
        print(f"  2. Run: jsonui-doc validate component {output_path}")
        print(f"  3. Run: jsonui-doc generate component {output_path} -o docs/components/html/{component_name.lower()}.html")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_validate_component(args):
    """Handle 'validate component' command - validate component specification JSON."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    validator = SpecValidator()
    result = validator.validate_file(file_path)

    if not validator._custom_rules.is_empty:
        print(f"Using custom rules: {validator._custom_rules.config_path}")

    print(f"\nValidating: {file_path}")
    print("=" * 50)

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(error)

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(warning)

    print()
    if result.is_valid:
        print("Result: PASSED")
    else:
        print("Result: FAILED")

    print(f"Errors: {result.error_count}, Warnings: {result.warning_count}")

    return 0 if result.is_valid else 1


def cmd_rules_init(args):
    """Handle 'rules init' command - create template config file."""
    from .spec_doc.rules_config import (
        generate_template_config, generate_flutter_config, CONFIG_FILENAME,
    )

    output_dir = Path(args.output) if args.output else Path.cwd()
    output_path = output_dir / CONFIG_FILENAME

    if output_path.exists():
        print(f"Error: {output_path} already exists", file=sys.stderr)
        return 1

    if args.flutter:
        template = generate_flutter_config()
    else:
        template = generate_template_config()

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"Created: {output_path}")
    print()
    print("Next steps:")
    print(f"  1. Edit {output_path} to customize validation rules")
    print(f"  2. Run: jsonui-doc rules show")
    print(f"  3. Validate spec files - custom rules are auto-detected")
    return 0


def cmd_rules_show(args):
    """Handle 'rules show' command - display effective rules."""
    from .spec_doc.rules_config import find_config_file, load_config, CustomRules

    search_dir = Path(args.directory) if args.directory else Path.cwd()
    config_path = find_config_file(search_dir)

    rules = None
    if config_path:
        print(f"Config file: {config_path}")
        rules = load_config(config_path)
    else:
        print("Config file: (none found)")
        rules = CustomRules()

    validator = SpecValidator(custom_rules=rules)

    print()
    print("Effective Rules:")
    print("=" * 50)

    print()
    print("Screen Component Types:")
    for t in sorted(validator._effective_screen_component_types):
        marker = " (custom)" if rules and t in rules.extra_screen_component_types else ""
        print(f"  - {t}{marker}")

    print()
    print("Component Types:")
    for t in sorted(validator._effective_component_types):
        marker = " (custom)" if rules and t in rules.extra_component_types else ""
        print(f"  - {t}{marker}")

    print()
    print("File Types:")
    for t in sorted(validator._effective_file_types):
        marker = " (custom)" if rules and t in rules.extra_file_types else ""
        print(f"  - {t}{marker}")

    print()
    print("Component Categories:")
    for c in sorted(validator._effective_component_categories):
        marker = " (custom)" if rules and c in rules.extra_component_categories else ""
        print(f"  - {c}{marker}")

    print()
    print("Event Handler Naming:")
    print(f"  Base pattern: ^on[A-Z][a-zA-Z0-9]*$")
    if rules and rules.allowed_event_handler_names:
        print(f"  Allowed names: {', '.join(sorted(rules.allowed_event_handler_names))}")
    if rules and rules.extra_event_handler_patterns:
        for p in rules.extra_event_handler_patterns:
            print(f"  Additional pattern: {p}")

    print()
    print("Variable Naming:")
    print(f"  Base pattern: ^[a-z][a-zA-Z0-9]*$")
    if rules and rules.extra_variable_patterns:
        for p in rules.extra_variable_patterns:
            print(f"  Additional pattern: {p}")

    return 0


def cmd_generate_component(args):
    """Handle 'generate component' command - generate MD/HTML from component spec JSON."""
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: Path not found: {input_path}", file=sys.stderr)
        return 1

    # Check if input is a directory (batch mode)
    if input_path.is_dir():
        return cmd_generate_component_batch(args, input_path)

    # Single file mode
    file_path = input_path

    # Load and validate spec
    validator = SpecValidator()
    result = validator.validate_file(file_path)

    if not result.is_valid:
        print(f"Error: Validation failed for {file_path}", file=sys.stderr)
        for error in result.errors:
            print(error, file=sys.stderr)
        return 1

    spec_data = result.spec_data

    # Determine output format
    output_format = args.format
    if args.output and not output_format:
        ext = Path(args.output).suffix.lower()
        if ext == ".html":
            output_format = "html"
        else:
            output_format = "markdown"
    elif not output_format:
        output_format = "markdown"

    # Generate content (reuse spec generators for now, can be customized later)
    if output_format == "html":
        content = generate_component_html(spec_data)
    else:
        content = generate_component_markdown(spec_data)

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Generated: {output_path}")
    else:
        print(content)

    return 0


def cmd_generate_component_batch(args, input_dir: Path):
    """Handle batch generation of component docs from a directory.

    The sibling of `cmd_generate_spec_batch`, and it had the same defect for
    the same reason: `cmd_generate_component` dispatches here on `is_dir()`
    before it works out a format, and this never read `args.format`.

    Same resolution too — an explicit `--format` is honoured, its absence
    still means HTML. See the note on the spec batch for why the default
    stays put.
    """
    output_dir = Path(args.output) if args.output else input_dir.parent / "html"
    output_format = args.format or "html"
    to_html = output_format == "html"
    suffix = ".html" if to_html else ".md"

    # Find all .component.json files (recursive to support subdirectories)
    component_files = list(input_dir.rglob("*.component.json"))
    if not component_files:
        print(f"Error: No .component.json files found in {input_dir}", file=sys.stderr)
        return 1

    print(f"Generating {output_format} for {len(component_files)} component files...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    validator = SpecValidator()
    success_count = 0
    error_count = 0

    for component_file in sorted(component_files):
        result = validator.validate_file(component_file)

        if not result.is_valid:
            print(f"  FAILED: {component_file.relative_to(input_dir)}")
            for error in result.errors:
                print(f"    {error}")
            error_count += 1
            continue

        content = (generate_component_html(result.spec_data) if to_html
                   else generate_component_markdown(result.spec_data))

        # Preserve subdirectory structure in output
        rel_path = component_file.relative_to(input_dir)
        output_name = rel_path.with_name(rel_path.name.replace(".component.json", suffix))
        output_path = output_dir / output_name

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"  OK: {rel_path} -> {output_name}")
        success_count += 1

    print()
    print(f"Generated: {success_count} files")
    if error_count > 0:
        print(f"Failed: {error_count} files")
        return 1

    return 0


def cmd_figma_fetch(args):
    """Handle 'figma fetch' command - fetch Figma file JSON via API."""
    # Resolve file_key: --url takes priority, then positional file_key
    node_id_from_url = None
    if args.url:
        try:
            file_key, node_id_from_url = parse_figma_url(args.url)
        except FigmaAPIError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    elif args.file_key:
        file_key = args.file_key
    else:
        print("Error: file_key or --url is required.", file=sys.stderr)
        return 1

    # Resolve API token
    try:
        token = resolve_token(args.token if hasattr(args, 'token') else None)
    except FigmaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine output path (default: figma/{file_key}.json)
    if args.output:
        output_path = Path(args.output)
    else:
        safe_key = "".join(c if c.isalnum() else "_" for c in file_key)
        output_path = Path("figma") / f"{safe_key}.json"

    depth = args.depth if hasattr(args, 'depth') else None
    node_ids = getattr(args, 'node_ids', None)
    select_pages = getattr(args, 'pages', False)

    # If URL had node-id and no explicit --node-ids, use the URL's node-id
    if node_id_from_url and not node_ids:
        node_ids = [node_id_from_url]

    # Interactive page selection mode
    if select_pages:
        rc, data = _fetch_with_page_selection(file_key, token, output_path, depth)
        if rc != 0 or data is None:
            return rc
    # Fetch specific nodes
    elif node_ids:
        rc, data = _fetch_specific_nodes(file_key, token, node_ids, output_path, depth)
        if rc != 0:
            return rc
    else:
        # Fetch full file
        print(f"Fetching Figma file: {file_key}")
        if depth is not None:
            print(f"  Depth limit: {depth}")
        print(f"  Output: {output_path}")
        print()

        try:
            data = fetch_file(file_key, token, depth=depth)
        except FigmaAPIError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Summary
        file_name = data.get("name", "Unknown")
        last_modified = data.get("lastModified", "Unknown")
        print(f"Fetched: {file_name}")
        print(f"  Last modified: {last_modified}")
        print(f"  Saved to: {output_path}")

    # Download images if --images flag is set (shared across all fetch paths)
    if getattr(args, 'images', False) and data is not None:
        print()
        figma_dir = output_path.parent
        plan = getattr(args, 'plan', 'starter')
        manifest = fetch_and_download_images(file_key, token, data, figma_dir, plan=plan, after_api_call=True)
        fill_count = len(manifest.get("fills", {}))
        render_count = len(manifest.get("renders", {}))
        print(f"\nImages: {fill_count} fills, {render_count} renders downloaded")

    return 0


def cmd_figma_images(args):
    """Handle 'figma images' command - download images for existing JSON."""
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
        return 1

    try:
        token = resolve_token(args.token if hasattr(args, 'token') else None)
    except FigmaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Extract file_key from the JSON or from --file-key arg
    file_key = getattr(args, 'file_key', None)
    if not file_key:
        # Try to infer from filename (figma/{key}.json)
        stem = json_path.stem
        file_key = stem
        print(f"Using file key from filename: {file_key}")

    print(f"Loading {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        figma_json = json.load(f)

    figma_dir = json_path.parent
    plan = getattr(args, 'plan', 'starter')
    manifest = fetch_and_download_images(file_key, token, figma_json, figma_dir, plan=plan)
    fill_count = len(manifest.get("fills", {}))
    render_count = len(manifest.get("renders", {}))
    print(f"\nDone! {fill_count} fills, {render_count} renders downloaded")

    return 0


def _fetch_with_page_selection(file_key, token, output_path, depth):
    """Fetch pages list, let user select, then fetch selected nodes.

    Returns:
        Tuple of (return_code, data_dict_or_None).
    """
    print(f"Fetching page list for: {file_key}")
    print()

    try:
        data = fetch_file(file_key, token, depth=1)
    except FigmaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1, None

    file_name = data.get("name", "Unknown")
    pages = data.get("document", {}).get("children", [])
    if not pages:
        print("No pages found in this file.", file=sys.stderr)
        return 1, None

    # Show pages
    print(f"File: {file_name}")
    print(f"Pages ({len(pages)}):")
    print()
    for i, page in enumerate(pages, 1):
        page_name = page.get("name", "Untitled")
        child_count = len(page.get("children", []))
        print(f"  {i}. {page_name}  ({child_count} top-level frames)")
    print()
    print("  0. All pages (fetch entire file)")
    print()

    # Prompt for selection
    try:
        selection = input("Select pages (comma-separated numbers, e.g. 1,3): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 0, None

    if not selection:
        print("No selection. Cancelled.")
        return 0, None

    # Parse selection
    if selection == "0":
        # Fetch entire file
        print()
        print("Fetching entire file...")
        try:
            full_data = fetch_file(file_key, token, depth=depth)
        except FigmaAPIError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1, None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)
        print(f"Saved to: {output_path}")
        return 0, full_data

    try:
        indices = [int(s.strip()) for s in selection.split(",")]
    except ValueError:
        print("Error: Invalid input. Enter numbers separated by commas.", file=sys.stderr)
        return 1, None

    selected_ids = []
    selected_names = []
    for idx in indices:
        if idx < 1 or idx > len(pages):
            print(f"Error: Invalid page number: {idx}", file=sys.stderr)
            return 1, None
        page = pages[idx - 1]
        selected_ids.append(page["id"])
        selected_names.append(page.get("name", "Untitled"))

    print()
    print(f"Fetching {len(selected_ids)} page(s): {', '.join(selected_names)}")

    try:
        nodes_data = fetch_nodes(file_key, token, selected_ids, depth=depth)
    except FigmaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1, None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(nodes_data, f, ensure_ascii=False, indent=2)

    print(f"Saved to: {output_path}")
    return 0, nodes_data


def _fetch_specific_nodes(file_key, token, node_ids, output_path, depth):
    """Fetch specific nodes by ID.

    Returns:
        Tuple of (return_code, data_dict_or_None).
    """
    print(f"Fetching nodes from: {file_key}")
    print(f"  Node IDs: {', '.join(node_ids)}")
    print(f"  Output: {output_path}")
    print()

    try:
        data = fetch_nodes(file_key, token, node_ids, depth=depth)
    except FigmaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1, None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    file_name = data.get("name", "Unknown")
    print(f"Fetched: {file_name}")
    print(f"  Saved to: {output_path}")
    return 0, data


def cmd_check(args):
    """Run declared contract checks (docs ⇔ implementation).

    Exit codes: 0 = clean / 1 = mismatch / 2 = execution error.
    This is the ONLY command that executes project-declared code; it never
    runs implicitly from generate (doc-contract-check plan 01 §6).
    """
    from .project_config import (
        ProjectConfigError,
        find_jui_config,
        load_checks,
        load_config_dict,
        load_databases,
    )
    from .check.runner import EXIT_ERROR, run_checks

    start = Path(args.project).resolve() if args.project else Path.cwd()
    config_path = find_jui_config(start)
    if config_path is None:
        print("Error: jui.config.json not found (checks are declared there).",
              file=sys.stderr)
        return EXIT_ERROR
    project_root = config_path.parent
    try:
        config = load_config_dict(config_path)
        decls = load_checks(config, project_root)
        databases = load_databases(config)
    except ProjectConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return run_checks(
        decls,
        project_root,
        databases,
        filter_expr=args.filter,
        list_only=args.list,
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="jsonui-doc",
        description="JsonUI Document CLI - Generate documentation for JsonUI projects"
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Init command
    init_parser = subparsers.add_parser(
        "init",
        aliases=["i"],
        help="Initialize new specification files"
    )
    init_subparsers = init_parser.add_subparsers(dest="init_type", help="Initialization type")

    # Init spec subcommand
    init_spec_parser = init_subparsers.add_parser(
        "spec",
        help="Create a new screen specification template"
    )
    init_spec_parser.add_argument(
        "name",
        help="Screen name in PascalCase (e.g., 'Login', 'UserProfile')"
    )
    init_spec_parser.add_argument(
        "-d", "--display-name",
        help="Localized display name (default: same as name)"
    )
    init_spec_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: docs/screens/json)"
    )
    init_spec_parser.add_argument(
        "-f", "--file-path",
        dest="file_path",
        help=(
            "Explicit relative file path under the output directory "
            "(e.g., 'learn/hello-world.spec.json'). If omitted, the file "
            "name is derived from the PascalCase name via kebab-case."
        ),
    )

    # Init component subcommand
    init_component_parser = init_subparsers.add_parser(
        "component",
        help="Create a new component specification template"
    )
    init_component_parser.add_argument(
        "name",
        help="Component name in PascalCase (e.g., 'UserCard', 'SearchBar')"
    )
    init_component_parser.add_argument(
        "-d", "--display-name",
        help="Localized display name (default: same as name)"
    )
    init_component_parser.add_argument(
        "-c", "--category",
        choices=["card", "form", "list", "navigation", "input", "display", "layout", "feedback", "other"],
        help="Component category (default: other)"
    )
    init_component_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: docs/components/json)"
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        aliases=["v"],
        help="Validate specification files"
    )
    validate_subparsers = validate_parser.add_subparsers(dest="validate_type", help="Validation type")

    # Validate spec subcommand
    validate_spec_parser = validate_subparsers.add_parser(
        "spec",
        help="Validate screen specification JSON file"
    )
    validate_spec_parser.add_argument(
        "file",
        help=(
            "Specification file to validate (.spec.json), or a directory to "
            "validate every spec under it"
        )
    )

    # Validate component subcommand
    validate_component_parser = validate_subparsers.add_parser(
        "component",
        help="Validate component specification JSON file"
    )
    validate_component_parser.add_argument(
        "file",
        help="Component specification file to validate (.component.json)"
    )

    # Rules command
    rules_parser = subparsers.add_parser(
        "rules",
        aliases=["r"],
        help="Manage custom validation rules"
    )
    rules_subparsers = rules_parser.add_subparsers(dest="rules_type", help="Rules command type")

    # Rules init subcommand
    rules_init_parser = rules_subparsers.add_parser(
        "init",
        help="Create a template .jsonui-doc-rules.json config file"
    )
    rules_init_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current directory)"
    )
    rules_init_parser.add_argument(
        "--flutter",
        action="store_true",
        help="Include Flutter-specific rules (Scaffold, AppBar, lifecycle methods, etc.)"
    )

    # Rules show subcommand
    rules_show_parser = rules_subparsers.add_parser(
        "show",
        help="Show current effective rules (base + custom)"
    )
    rules_show_parser.add_argument(
        "-d", "--directory",
        help="Directory to search for config file (default: current directory)"
    )

    # Generate command with subcommands
    generate_parser = subparsers.add_parser(
        "generate",
        aliases=["g"],
        help="Generate documentation"
    )
    generate_subparsers = generate_parser.add_subparsers(dest="generate_type", help="Generation type")

    # Generate doc subcommand
    gen_doc_parser = generate_subparsers.add_parser(
        "doc",
        help="Generate HTML/Markdown documentation from test files"
    )
    gen_doc_parser.add_argument(
        "-f", "--file",
        help="Test file to generate documentation for"
    )
    gen_doc_parser.add_argument(
        "-o", "--output",
        help="Output file path"
    )
    gen_doc_parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        help="Output format (default: inferred from output or markdown)"
    )
    gen_doc_parser.add_argument(
        "--schema",
        action="store_true",
        help="Generate schema reference instead of test documentation"
    )

    # Generate html subcommand
    gen_html_parser = generate_subparsers.add_parser(
        "html",
        help="Generate HTML directory with index for all test files"
    )
    gen_html_parser.add_argument(
        "input",
        help="Input directory containing .test.json files"
    )
    gen_html_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: html)"
    )
    gen_html_parser.add_argument(
        "-t", "--title",
        help="Title for index page (default: JsonUI Test Documentation)"
    )
    gen_html_parser.add_argument(
        "-d", "--docs",
        action="append",
        metavar="DIR",
        help="Directory containing OpenAPI/Swagger files (can be specified multiple times)"
    )
    gen_html_parser.add_argument(
        "-fig", "--figma",
        metavar="DIR",
        help="Directory containing Figma JSON files (default: auto-detect figma/ next to input)"
    )
    gen_html_parser.add_argument(
        "--app",
        action="append",
        metavar="NAME:DIR",
        help="App with docs directory in 'name:path' format (can be specified multiple times for multi-app docs)"
    )
    gen_html_parser.add_argument(
        "--layouts-dir",
        help="Override layouts directory for layoutFile import (default: auto-detect per spec via jui.config.json)"
    )
    gen_html_parser.add_argument(
        "--allow-partial",
        action="store_true",
        dest="allow_partial",
        help=(
            "Exit 0 even when some pages failed to generate. Without it a "
            "failed page fails the command: an exit-0 run that quietly "
            "dropped a page leaves the index linking to a 404 nobody "
            "notices. Unrelated to --with-checks, which is about drift."
        ),
    )
    gen_html_parser.add_argument(
        "--with-checks",
        action="store_true",
        dest="with_checks",
        help=(
            "Run `jsonui-doc check` first, then generate (sugar for the "
            "explicit two-step). Generation succeeds even when checks find "
            "mismatches — gating on drift is the check command's exit code."
        ),
    )

    # Generate mermaid subcommand
    gen_mermaid_parser = generate_subparsers.add_parser(
        "mermaid",
        help="Generate Mermaid flow diagram from flow tests"
    )
    gen_mermaid_parser.add_argument(
        "input",
        help="Input directory containing tests (with flows/ and screens/ subdirs)"
    )
    gen_mermaid_parser.add_argument(
        "-o", "--output",
        help="Output HTML file path (if not specified, outputs Mermaid code to stdout)"
    )
    gen_mermaid_parser.add_argument(
        "-t", "--title",
        help="Title for diagram page (default: Flow Diagram)"
    )
    gen_mermaid_parser.add_argument(
        "-s", "--screens",
        help="Path to screens directory (default: auto-detect)"
    )
    gen_mermaid_parser.add_argument(
        "--layouts-dir",
        help=(
            "Path to the layout tree (default: auto-detect from jui.config.json). "
            "Used to tell screens from Collection cells / partials so sub-areas "
            "are not drawn as screens."
        )
    )

    # Generate adapter subcommand
    gen_adapter_parser = generate_subparsers.add_parser(
        "adapter",
        aliases=["a"],
        help="Generate adapter files for custom actions and configurations"
    )
    gen_adapter_parser.add_argument(
        "platform",
        choices=ADAPTER_PLATFORMS,
        help="Target platform (ios, android, web)"
    )
    gen_adapter_parser.add_argument(
        "-o", "--output",
        help="Output directory (default: current directory)"
    )
    gen_adapter_parser.add_argument(
        "-n", "--name",
        help="Project name for namespacing (default: MyApp)"
    )
    gen_adapter_parser.add_argument(
        "-a", "--actions",
        help="Path to JSON file defining custom actions"
    )

    # Generate spec subcommand
    gen_spec_parser = generate_subparsers.add_parser(
        "spec",
        help="Generate HTML/Markdown documentation from screen specification JSON"
    )
    gen_spec_parser.add_argument(
        "file",
        help="Specification file (.spec.json) or directory containing .spec.json files"
    )
    gen_spec_parser.add_argument(
        "-o", "--output",
        help="Output file path (for single file) or output directory (for batch)"
    )
    gen_spec_parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        help="Output format (default: for a single file, inferred from the "
             "output extension, else markdown; for a directory, html)"
    )
    gen_spec_parser.add_argument(
        "--layouts-dir",
        help="Path to shared layouts directory (for layoutFile import; auto-detected from jui.config.json if omitted)"
    )

    # Generate component subcommand
    gen_component_parser = generate_subparsers.add_parser(
        "component",
        help="Generate HTML/Markdown documentation from component specification JSON"
    )
    gen_component_parser.add_argument(
        "file",
        help="Component specification file (.component.json) or directory containing .component.json files"
    )
    gen_component_parser.add_argument(
        "-o", "--output",
        help="Output file path (for single file) or output directory (for batch)"
    )
    gen_component_parser.add_argument(
        "--format",
        choices=["markdown", "html"],
        help="Output format (default: for a single file, inferred from the "
             "output extension, else markdown; for a directory, html)"
    )

    # Figma command
    figma_parser = subparsers.add_parser(
        "figma",
        aliases=["f"],
        help="Figma integration tools"
    )
    figma_subparsers = figma_parser.add_subparsers(dest="figma_type", help="Figma command type")

    # Figma fetch subcommand
    figma_fetch_parser = figma_subparsers.add_parser(
        "fetch",
        help="Fetch Figma file JSON via API"
    )
    figma_fetch_parser.add_argument(
        "file_key",
        nargs="?",
        default=None,
        help="Figma file key (from URL: figma.com/file/{FILE_KEY}/...)"
    )
    figma_fetch_parser.add_argument(
        "--url",
        help="Figma URL (auto-extracts file key and node-id)"
    )
    figma_fetch_parser.add_argument(
        "-o", "--output",
        help="Output JSON file path (default: figma/{file_key}.json)"
    )
    figma_fetch_parser.add_argument(
        "-t", "--token",
        help="Figma API token (default: FIGMA_TOKEN environment variable)"
    )
    figma_fetch_parser.add_argument(
        "--depth",
        type=int,
        help="Limit response tree depth (Figma API depth parameter)"
    )
    figma_fetch_parser.add_argument(
        "--node-ids",
        nargs="+",
        help="Specific node IDs to fetch (e.g. 0:1 1:2)"
    )
    figma_fetch_parser.add_argument(
        "--pages", "-p",
        action="store_true",
        help="Interactive page selection: list pages and choose which to fetch"
    )
    figma_fetch_parser.add_argument(
        "--images",
        action="store_true",
        help="Also download images (fills and vector renders) after fetching JSON"
    )
    figma_fetch_parser.add_argument(
        "--plan",
        choices=PLAN_CHOICES,
        default="starter",
        help="Figma plan for API rate limit throttling (default: starter)"
    )

    # Figma images subcommand
    figma_images_parser = figma_subparsers.add_parser(
        "images",
        help="Download images for an existing Figma JSON file"
    )
    figma_images_parser.add_argument(
        "json_file",
        help="Path to Figma JSON file (e.g. figma/abc123.json)"
    )
    figma_images_parser.add_argument(
        "-k", "--file-key",
        help="Figma file key (default: inferred from filename)"
    )
    figma_images_parser.add_argument(
        "-t", "--token",
        help="Figma API token (default: FIGMA_TOKEN environment variable)"
    )
    figma_images_parser.add_argument(
        "--plan",
        choices=PLAN_CHOICES,
        default="starter",
        help="Figma plan for API rate limit throttling (default: starter)"
    )

    # Check command (contract checks: docs ⇔ implementation)
    check_parser = subparsers.add_parser(
        "check",
        help=(
            "Run declared contract checks (real DB / implementation OpenAPI "
            "vs docs). Executes only commands declared in jui.config.json."
        ),
    )
    check_parser.add_argument(
        "filter",
        nargs="?",
        help=(
            "Restrict which checks run: 'db' / 'api' / 'db:<name>' / "
            "a declared check name (default: all)"
        ),
    )
    check_parser.add_argument(
        "--list",
        action="store_true",
        help="Show what would run (name, type, exact command) without running",
    )
    check_parser.add_argument(
        "-p", "--project",
        help="Project directory (default: walk up from cwd to jui.config.json)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command in ["init", "i"]:
        if hasattr(args, 'init_type') and args.init_type:
            if args.init_type == "spec":
                return cmd_init_spec(args)
            elif args.init_type == "component":
                return cmd_init_component(args)
        else:
            init_parser.print_help()
            return 0
    elif args.command in ["validate", "v"]:
        if hasattr(args, 'validate_type') and args.validate_type:
            if args.validate_type == "spec":
                return cmd_validate_spec(args)
            elif args.validate_type == "component":
                return cmd_validate_component(args)
        else:
            validate_parser.print_help()
            return 0
    elif args.command in ["rules", "r"]:
        if hasattr(args, 'rules_type') and args.rules_type:
            if args.rules_type == "init":
                return cmd_rules_init(args)
            elif args.rules_type == "show":
                return cmd_rules_show(args)
        else:
            rules_parser.print_help()
            return 0
    elif args.command in ["generate", "g"]:
        if hasattr(args, 'generate_type') and args.generate_type:
            if args.generate_type == "doc":
                return cmd_generate_doc(args)
            elif args.generate_type == "html":
                return cmd_generate_html(args)
            elif args.generate_type == "mermaid":
                return cmd_generate_mermaid(args)
            elif args.generate_type in ["adapter", "a"]:
                return cmd_generate_adapter(args)
            elif args.generate_type == "spec":
                return cmd_generate_spec(args)
            elif args.generate_type == "component":
                return cmd_generate_component(args)
        else:
            generate_parser.print_help()
            return 0
    elif args.command in ["figma", "f"]:
        if hasattr(args, 'figma_type') and args.figma_type:
            if args.figma_type == "fetch":
                return cmd_figma_fetch(args)
            elif args.figma_type == "images":
                return cmd_figma_images(args)
        else:
            figma_parser.print_help()
            return 0
    elif args.command == "check":
        return cmd_check(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
