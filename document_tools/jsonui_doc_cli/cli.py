#!/usr/bin/env python3
"""
JsonUI Document CLI

Command-line interface for generating documentation from JsonUI test files
and specification documents.
"""

import argparse
import json
import os
import re
import sys
import warnings
from pathlib import Path


def _config_for(start: Path) -> Path | None:
    """The config governing *start*: itself if it holds one, else walk up.

    Resolved either way. `find_jui_config` resolves and the direct hit did
    not, so the same file came back in two spellings depending on which
    branch found it — and on macOS those differ by a `/private` prefix, which
    is the kind of difference that shows up in a banner and in nothing else.
    """
    from .project_config import find_jui_config
    here = Path(start) / "jui.config.json"
    if here.is_file():
        return here.resolve()
    return find_jui_config(Path(start))


def _declares_specs(config: Path) -> bool:
    """Whether this config can enumerate specs at all."""
    try:
        return bool(json.loads(config.read_text(encoding="utf-8")).get("spec_directory"))
    except (OSError, ValueError, AttributeError):
        return False


def _extends_target(config: Path) -> Path | None:
    """The config this one extends, resolved against its own directory.

    ⚠️ Same rule as `shared/core/openapi_canonical._follow_extends`, which
    resolves against the directory of the config it is reading. Both accept a
    DIRECTORY and complete it with `jui.config.json`: a consumer writing
    `extends: "../../admin"` must not resolve on one face and fail on the
    other. Change one and change the other.
    """
    try:
        raw = json.loads(config.read_text(encoding="utf-8"))
        extends = raw.get("extends")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(extends, str) or not extends.strip():
        return None
    resolved = (config.parent / extends).resolve()
    if resolved.is_dir():
        resolved = resolved / "jui.config.json"
    return resolved


#: How far `extends` is followed, matching
#: `openapi_canonical._follow_extends`'s `_depth > 4`: four hops past the
#: first config, so five files at most. Bounded because the chain is data —
#: a config that extends itself, or two that extend each other, must end the
#: search rather than the process.
_MAX_EXTENDS_HOPS = 4


def _follow_extends(config: Path) -> tuple[Path | None, Path]:
    """``(a config that declares specs, the last file actually read)``.

    ⚠️ Shares a name with `shared/core/openapi_canonical._follow_extends` and
    does a different job: that one MERGES — it walks the chain and returns the
    config that owns the tree, for reading settings out of. This one only
    RESOLVES A PATH, and stops at the first config that can enumerate specs.
    The traversal rules are deliberately identical (resolve against the
    config's own directory, complete a directory with `jui.config.json`, four
    hops), because a consumer writes one `extends` and both faces read it.
    Change the rules in one and change them in the other.

    A config that cannot enumerate but declares `extends` is not a dead end —
    it is a POINTER, and the project wrote it deliberately. The real tree
    keeps a stub at `docs/<app>/jui.config.json` carrying only
    `layouts_directory` and `extends: ../../<app>/jui.config.json`, so a
    search that stops at the first file it finds stops on a signpost and
    reports that the destination does not exist.

    The second element is what to name when nothing declares: the file the
    search actually ended on, so the warning points at something real rather
    than at where the search began.
    """
    seen: set[Path] = set()
    current, last = config, config
    # hops + 1 visits: the first config is not a hop, matching
    # `openapi_canonical._follow_extends`, which refuses at `_depth > 4`
    # having already read five files.
    for _ in range(_MAX_EXTENDS_HOPS + 1):
        if current in seen:
            break
        seen.add(current)
        last = current
        if _declares_specs(current):
            return current, current
        nxt = _extends_target(current)
        if nxt is None or not nxt.is_file():
            break
        current = nxt
    return None, last


def _config_for_app(app_name: str, docs_path: Path) -> Path | None:
    """The config governing one app's specs.

    An app's DOCS and its CONFIG need not share a tree. The reported shape has
    the specs at `docs/<app>/screens/json` and the config at
    `<app>/jui.config.json` pointing back out at them, so walking up from the
    docs directory leaves the app's subtree entirely and lands on the
    repository root — whose config carries only `checks`.

    So when the config found that way cannot enumerate specs, one more
    candidate is tried: `<app_name>/jui.config.json` beside it. That is not
    searching harder — `app_name` is the name the caller just supplied in
    `--app`, so it is a named candidate rather than a guess, and a config that
    also cannot enumerate is kept as the answer so the warning names the file
    that was actually read.
    """
    cfg = _config_for(docs_path)
    if cfg is None:
        return None
    found, last = _follow_extends(cfg)
    if found is not None:
        return found
    beside = cfg.parent / app_name / "jui.config.json"
    if beside.is_file():
        found, _ = _follow_extends(beside.resolve())
        if found is not None:
            return found
    return last


def _resolve_unit_roots(
    config_arg: str | None, apps: list[dict] | None, fallback_start: Path
) -> list[dict]:
    """``{app, config, root}`` for every place unitContracts may be declared.

    Three inputs, in order of how directly they say what to read:

    ``--config``  an explicit file. No walk-up at all — the reason it exists
                  is that the walk-up cannot be steered from outside.
    ``--app``     one root per app, resolved from that app's own directory. A
                  split tree keeps the spec config beside each app while the
                  repository root carries a different config (commonly just
                  `checks`, which is legitimate and declares no
                  `spec_directory`). A single walk-up from the tests directory
                  stops at that root, so before this the apps' contracts were
                  unreachable no matter where the command was run from.
    neither       the historical single walk-up, unchanged.
    """
    if config_arg:
        cfg = Path(config_arg)
        if not cfg.is_file():
            print(f"Error: --config not found: {cfg}", file=sys.stderr)
            return []
        # Named explicitly, and `extends` is followed anyway: naming a file is
        # a declaration, and so is the pointer inside it. Someone who points
        # at the stub beside their docs means the config it extends.
        found, last = _follow_extends(cfg.resolve())
        use = found if found is not None else last
        return [{"app": None, "config": use, "root": use.parent}]

    if apps:
        roots: list[dict] = []
        for app in apps:
            cfg = _config_for_app(app["name"], Path(app["docs_path"]))
            if cfg is not None:
                roots.append({"app": app["name"], "config": cfg, "root": cfg.parent})
        if roots:
            return roots

    cfg = _config_for(fallback_start)
    if cfg is None:
        return []
    found, last = _follow_extends(cfg)
    use = found if found is not None else last
    return [{"app": None, "config": use, "root": use.parent}]


def _component_spec_dir_from_config() -> Path | None:
    """`component_spec_directory` from jui.config.json, or None.

    ⚠️ Warns rather than returning a quiet None. The first cut swallowed every
    exception, and because it named two attributes ConfigManager does not have
    (`config`, `config_path` — they are `load()` and `path`) it returned None
    for every project. The links then all rendered as text: no dangling link,
    no error, and a run that looked like the fix working. A helper whose
    failure and whose correct-but-empty answer are the same value has to say
    which one happened.
    """
    try:
        here = Path(__file__).resolve()
        repo_root = here.parents[2]
        jui_tools_dir = repo_root / "jui_tools"
        if jui_tools_dir.is_dir() and str(jui_tools_dir) not in sys.path:
            sys.path.insert(0, str(jui_tools_dir))
        from jui_cli.core.config_manager import ConfigManager
        config_mgr = ConfigManager()
        if not config_mgr.exists():
            return None
        return Path(config_mgr.component_spec_directory).resolve()
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"jsonui-doc: component_spec_directory lookup failed ({exc!r}); "
            "component references will be rendered as text instead of links.",
            stacklevel=2,
        )
        return None


def _output_is_in_the_source_tree(output_dir: Path, spec_dir: Path) -> bool:
    """Is *output_dir* an in-place render, beside the specs it came from?

    The docs root is taken as the specs' grandparent — `docs/screens/json`
    gives `docs`, and an in-place render lands under it (`docs/screens/html`).
    A render into a temp directory, a build area or anywhere else does not,
    and for those the source tree must not be used as a link target: the href
    would leave the generated site entirely and name an absolute path.

    ⚠️ Errs toward FALSE. When the answer cannot be computed, the caller
    falls back to the output-relative root and, if that has no pages, renders
    text — which is the behaviour a reader can act on. An href naming
    somebody's home directory is not.
    """
    try:
        docs_root = spec_dir.resolve().parent.parent
        output_dir.resolve().relative_to(docs_root)
    except (ValueError, OSError):
        return False
    return True


def _component_pages_on_disk(output_dir: Path) -> dict[str, Path]:
    """`<name>.component.json` -> the page that exists for it, or {}.

    ⚠️ Existence is the whole point. The path this replaces was a template —
    ``f"../../components/html/{html_file}"`` — built from the component's NAME
    and never checked, so it produced a link for a page that was somewhere
    else, or nowhere. Measured across five consumer trees on 2026-09-08: of the
    component links in already-shipped generated docs, 11 pointed at a page
    that exists at a DIFFERENT path in the same repository, and the template
    was right for only the one project laid out the way its author's was.

    Three ways it went wrong, all from the same missing step:
      A the page is a directory deeper, so `../../` leaves the spec tree
        (a nested spec's page sits further from the component tree, and the
        template counted the hops for a top-level page only);
      B there is no sibling `components/html/` at all, because the project
        keeps component specs in the same directory as screen specs — that
        project's links were dead at EVERY depth, which is what showed the
        cause was not depth;
      C the page has not been generated, which the site path already handles
        by rendering text instead of a link.

    So this asks the disk instead. A name that is not found here is left out
    of the map, and `generate_spec_html` renders it as text — the behaviour
    its own comment describes and the caller never gave it the data for.
    """
    pages: dict[str, Path] = {}
    spec_dir = _component_spec_dir_from_config()
    roots = []
    if spec_dir is not None and _output_is_in_the_source_tree(output_dir, spec_dir):
        # The generated pages sit beside the specs' directory, not inside it.
        #
        # ⚠️ ONLY when the output tree IS the source tree. This root is an
        # ABSOLUTE path in the source checkout, and `relpath` from an output
        # directory somewhere else turns it into a chain that climbs out to
        # the filesystem root and back down through the user's home — which
        # then gets WRITTEN INTO the generated HTML. A consumer whose
        # generated docs are tracked in a public repository reported it as a
        # leak, and their gate that renders into a temp directory and diffs
        # against the tracked pages could never match, because the href
        # depended on where `-o` happened to point.
        #
        # Regression introduced 2026-09-08 (v1.8.53) by the fix that made
        # these links resolve at all: asking the disk was right, but one of
        # the two places it asks only answers for the in-place render.
        roots.append(spec_dir.parent / "html")
    # The layout the old template assumed. Kept as a candidate — where it was
    # right it stays right — but now confirmed rather than presumed.
    roots.append((output_dir.parent / "components" / "html").resolve())

    for root in roots:
        if not root.is_dir():
            continue
        for page in sorted(root.glob("*.html")):
            spec_name = f"{page.stem}.component.json"
            # A page is only a component's page if that component's spec is
            # there too. Without this a project whose component specs share a
            # directory with its screen specs matches SCREEN pages by name.
            if spec_dir is not None and not (spec_dir / spec_name).is_file():
                continue
            pages.setdefault(spec_name, page)
    return pages


def _component_links_for_page(pages: dict[str, Path], page_dir: Path) -> dict[str, str]:
    """Relative hrefs from one output page to the component pages that exist.

    Relative to THIS page's own directory, which is what makes a nested spec
    work: the number of `../` is computed, never assumed.
    """
    links: dict[str, str] = {}
    for spec_name, target in pages.items():
        try:
            links[spec_name] = os.path.relpath(target, page_dir)
        except ValueError:
            # Different drive on Windows; no relative path exists. Leaving it
            # out renders text, which beats an href that cannot resolve.
            continue
    return links


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
    generation_summary_line,
    generation_warnings,
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

    # Where to read unitContracts from. Named in the banner below rather than
    # resolved silently: a walk-up that lands on the wrong config reports
    # "0 declared", which is indistinguishable from a project that declares
    # nothing, so the file it read is printed where someone would look.
    unit_roots = _resolve_unit_roots(
        getattr(args, "config", None), apps,
        input_dir if input_dir.exists() else Path.cwd())

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
    for entry in unit_roots:
        where = f"{entry['app']}: " if entry.get("app") else ""
        print(f"  Unit contracts: {where}{entry['config']}")
    if not unit_roots:
        # Counted spelling, not a note: with no config there is no scan, and
        # an absent Unit section then reads exactly like a project that
        # declares no contracts. `--config` is the way out, so name it.
        print("  WARNING [doc]: no jui.config.json found for unitContracts "
              "(pass --config <path>, or --app <name>:<dir> for a split tree) "
              "— the Unit Tests section will be absent, which is NOT evidence "
              "that none are declared")
    print()

    try:
        generate_html_directory(input_dir, output_dir, title, docs_dirs if docs_dirs else None, figma_dir=figma_dir, apps=apps, layouts_dir=layouts_dir_override, unit_roots=[{"app": e.get("app"), "root": e["root"]} for e in unit_roots])
        print()
        # Count every page written, not just the test pages in the return
        # value — the old number was smaller than the lines printed above it,
        # so it could not serve as a "did everything come out?" signal. The
        # denominators come with it: a page count alone cannot separate an
        # empty input, a mistyped path, a project declaring no contracts, and
        # a half-updated install, all of which end in a small number and 0.
        print(generation_summary_line())
        for line in generation_warnings():
            print(f"  {line}")
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

    # Component declarations, both directions. Batch mode for the same reason
    # as the cross-spec check above: neither direction is visible from one
    # file — one needs every spec in the face, the other needs the component
    # directory beside it.
    comp_errors, comp_warnings = _component_declaration_gaps(spec_files, input_dir)
    if comp_errors or comp_warnings:
        print()
        for line in comp_errors:
            print(line)
        for line in comp_warnings:
            print(line)
        total_errors += len(comp_errors)
        total_warnings += len(comp_warnings)

    print()
    if failed or cross or comp_errors:
        print(f"Result: FAILED ({len(failed)} of {len(spec_files)} spec file(s)"
              + (f", {len(cross)} cross-spec disagreement(s)" if cross else "")
              + (f", {len(comp_errors)} component declaration gap(s)"
                 if comp_errors else "")
              + ")")
        for spec_file in failed:
            print(f"  - {spec_file}")
    else:
        print(f"Result: PASSED ({len(spec_files)} spec file(s))")
    print(f"Errors: {total_errors}, Warnings: {total_warnings}")

    return 1 if (failed or cross or comp_errors) else 0


def _component_sibling_dirs(input_dir: Path):
    """``(component spec files, screens/layouts)`` for the face *input_dir* is in.

    ⚠️ The component files are FOUND, not computed. The first cut of this
    check looked in `<face>/components/json` — the layout this tool writes —
    and two consumer faces keep their `*.component.json` beside the screen
    specs instead. The check returned `([], [])` there and read as a clean
    face: a silent skip, in a release whose whole subject is that a rule
    reapplied in a second place goes wrong the moment a tree differs.

    So the face root is derived from `input_dir` and the component specs are
    whatever `*.component.json` it contains. `None` for the file list means
    the shape did not match at all, which the caller reports rather than
    treating as "nothing found" — the two produce the same empty list and
    mean opposite things.
    """
    d = Path(input_dir).resolve()
    if d.name != "json" or d.parent.name != "screens":
        return None, None
    face = d.parent.parent
    comps = sorted(face.rglob("*.component.json"))
    layouts = face / "screens" / "layouts"
    return comps, (layouts if layouts.is_dir() else None)


def _component_declaration_gaps(spec_files, input_dir):
    """Component specs and the screens that declare them, reconciled.

    Ruled 2026-09-08. Two faces had four component pages that no screen
    declared: the pages were generated and nothing linked to them, so they
    were unreachable from the site. Two other faces had the opposite —
    declarations naming a `specFile` that does not exist.

    ⚠️ The two directions are independent. A check for one is silent on the
    other, which is how both survived: the reporting lane found the first and
    the delivery lane found the second, on different faces, hours apart.

    Ownership here does NOT come from where the declaration sits — that is
    what makes this checkable today while the same question for unit
    contracts is not. A component's users are the layouts that name it, which
    is a fact about the tree rather than about the declaration being checked.

    Severity follows the evidence:
      declared, file missing        error — the reference resolves to nothing
      file exists, layouts use it   error — it IS used and nobody declared it
      file exists, no layout uses   warning — possibly not wired up yet
    Without a layouts directory the second and third cannot be separated, so
    everything undeclared degrades to a warning and the message says which
    check did not run. A severity assigned without the evidence for it is the
    line that is always wrong.
    """
    comp_files, layouts_dir = _component_sibling_dirs(input_dir)
    if comp_files is None:
        return [], [f"[WARNING] component declarations were not checked: "
                    f"{input_dir} is not a <face>/screens/json directory, so "
                    f"the face root could not be derived"]

    declared: dict[str, list[str]] = {}
    #: component NAME -> specs that name it without giving a `specFile`.
    named_only: dict[str, list[str]] = {}
    for spec_file in spec_files:
        try:
            with open(spec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for cc in ((data.get("structure") or {}).get("customComponents") or []):
            name = (cc or {}).get("specFile")
            if isinstance(name, str) and name:
                declared.setdefault(name, []).append(str(spec_file))
                continue
            # ⚠️ An entry with a `name` but no `specFile` matches on nothing
            # here, because this reconciliation is keyed on the file name. The
            # component it names then falls into the undeclared branch below
            # and is reported as "declared by no screen spec" — while its
            # declaration is sitting in this very list. Kept so that message
            # can say what is actually wrong instead of what is merely true.
            by_name = (cc or {}).get("name")
            if isinstance(by_name, str) and by_name:
                named_only.setdefault(by_name, []).append(str(spec_file))

    on_disk = {f.name: f for f in comp_files}

    errors: list[str] = []
    warnings: list[str] = []

    for name in sorted(set(declared) - set(on_disk)):
        where = ", ".join(sorted(declared[name]))
        errors.append(
            f"[ERROR] customComponents declares {name!r}, which does not exist "
            f"anywhere under the face — the link built from it resolves "
            f"to nothing "
            f"(declared by: {where})")

    for name in sorted(set(on_disk) - set(declared)):
        # A declaration that named this component but gave no `specFile` is
        # the likelier story, and it points at the field to fix rather than at
        # a declaration to add that is already there.
        incomplete = _declared_by_name_only(on_disk[name], named_only)
        if incomplete:
            where = ", ".join(sorted(incomplete))
            errors.append(
                f"[ERROR] {name} is declared by {len(incomplete)} spec(s) that "
                f"name it but give no 'specFile', so nothing links the "
                f"declaration to this file ({where}) — add "
                f"\"specFile\": \"{name}\" to that entry. Reported as "
                f"\"declared by no screen spec\" before this check existed, "
                f"which sent authors to add a declaration they already had.")
            continue
        users = _layouts_naming_component(on_disk[name], layouts_dir)
        if users is None:
            warnings.append(
                f"[WARNING] {name} is declared by no screen spec, so its page "
                f"is generated and nothing links to it. Whether any screen "
                f"USES it could not be checked: this face has no "
                f"screens/layouts directory")
        elif users:
            shown = ", ".join(users[:3]) + ("..." if len(users) > 3 else "")
            errors.append(
                f"[ERROR] {name} is used by {len(users)} layout(s) and declared "
                f"by no screen spec — its page is generated and unreachable "
                f"({shown})")
        else:
            warnings.append(
                f"[WARNING] {name} is declared by no screen spec and named by "
                f"no LAYOUT — its page is generated and nothing links to it. "
                f"⚠️ Only layouts were searched: a component used by another "
                f"COMPONENT is invisible to this check, so this is not a "
                f"finding that it is unused. Verify before removing anything "
                f"— a face read an earlier wording of this line as "
                f"\"unused\" and came close to deleting a live component.")

    return errors, warnings


def _declared_by_name_only(component_file: Path, named_only) -> list[str]:
    """Specs that named this component but gave no `specFile`, or []."""
    if not named_only:
        return []
    try:
        data = json.loads(component_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    name = ((data.get("metadata") or {}).get("name")
            if isinstance(data, dict) else None)
    if not isinstance(name, str) or not name:
        return []
    return list(named_only.get(name, []))


def _layouts_naming_component(component_file: Path, layouts_dir):
    """Layout files that name this component, or None when unknowable.

    None rather than an empty list when there is no layouts directory: "no
    layout uses it" and "nobody looked" are different answers and the caller
    picks a different severity for each.
    """
    if layouts_dir is None:
        return None
    try:
        data = json.loads(component_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = ((data.get("metadata") or {}).get("name")
            if isinstance(data, dict) else None)
    if not isinstance(name, str) or not name:
        return None
    needle = f'"{name}"'
    hits = []
    for layout in sorted(Path(layouts_dir).rglob("*.json")):
        try:
            if needle in layout.read_text(encoding="utf-8", errors="ignore"):
                hits.append(layout.name)
        except OSError:
            continue
    return hits


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
        # Where this page will land decides the hrefs, so an -o is read before
        # the page is built. Without -o the page goes to stdout and there is no
        # directory to be relative to, so nothing is offered and component
        # references render as text — the honest answer when the destination
        # is unknown, and never a link built from a guess.
        out_dir = Path(args.output).parent if getattr(args, "output", None) else None
        content = generate_spec_html(
            spec_data, layouts_dir=layouts_dir, spec_dir=file_path.parent,
            component_links=(
                _component_links_for_page(_component_pages_on_disk(out_dir), out_dir)
                if out_dir is not None else {}))
    else:
        content = generate_spec_markdown(spec_data, layouts_dir=layouts_dir,
                                         spec_dir=file_path.parent)

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            # ⚠️ The single-file form stamps too, with the SAME FAMILY as
            # the batch form. v1.8.58 stamped only the batch forms, so a
            # directory maintained by this form stayed permanently unmarked
            # while the tool's own output told its reader the mark would
            # arrive 'once rewritten'. Same family, so rewriting with
            # either form is silent — which is the whole point of naming
            # the family rather than the subcommand.
            f.write(stamp_producer(
                    content, "spec",
                    ".html" if output_format == "html" else ".md"))
        print(f"Generated: {output_path}")
    else:
        print(content)

    return 0


#: The producer name this command records in what it writes. NAME ONLY —
#: no version, no timestamp, no path, no host.
#:
#: 🚨 THE THREE CONSTRAINTS ARE NOT STYLE. Measured and supplied by the docs
#: face, which byte-compares 220 tracked generated files as a gate:
#:
#:   deterministic   a timestamp/path/host/pid makes that gate unpassable by
#:                   construction — regeneration would differ every time
#:   no version      a version in the mark rewrites all 220 files EVERY
#:                   RELEASE, and a real change then hides inside the churn
#:                   (their 1.8.56 uptake needed no regeneration at all:
#:                   208 files were byte-identical)
#:   no absolute paths  the face is a public repo and its pre-commit refuses
#:                   `/Users/`, which currently appears 0 times
#:
#: ⚠️ A version is not needed for the question this answers. The collision
#: this detects is with ANOTHER COMMAND's output, not with an older version
#: of this command's own.
PRODUCER_ATTR = "jsonui-doc-producer"


#: What v1.8.58 wrote. Read, never written any more — see `producer_family`.
LEGACY_PRODUCER_VALUES = {
    "spec-batch": "jsonui-doc:spec",
    "component-batch": "jsonui-doc:component",
}


def producer_family(command: str) -> str:
    """The FAMILY *command* belongs to, which is what the check asks about.

    🚨 v1.8.58 STAMPED THE SUBCOMMAND, AND THAT IS FINER THAN THE QUESTION.
    Reported 2026-09-09 by a consumer lane that traced a 6-vs-5 discrepancy in
    its own uptake: the mark said `component-batch`, so extending it to the
    single-file form had no correct spelling —

        single-file says "component-batch"  -> the mark LIES; batch did not
                                               write it, and the mark exists
                                               to answer who did
        single-file says "component"        -> rewriting with the batch form
                                               reports a FALSE COLLISION

    The check never needed the subcommand. It asks "is this my own output?",
    so the mark names the family and the comparison is by family. Extra
    precision in an identifier does not add information here; it manufactures
    false positives.

    ⚠️ `generate doc` is deliberately absent: it writes one document from one
    input and has never shared an output directory with the batch forms. Add
    it when a collision involving it is actually reported, not before.
    """
    return "jsonui-doc:" + ("spec" if command.startswith("spec") else "component")


def producer_mark(command: str, suffix: str) -> str:
    """The one line *command* stamps into each file it writes."""
    family = producer_family(command)
    if suffix == ".html":
        return f'<meta name="{PRODUCER_ATTR}" content="{family}">'
    return f'<!-- {PRODUCER_ATTR}: {family} -->'


def stamp_producer(text: str, command: str, suffix: str) -> str:
    """*text* with this command's mark, or unchanged if it cannot be placed.

    ⚠️ Never raises and never mangles: a document with no `<head>` is written
    exactly as the emitter produced it. An unmarked file is a file this check
    cannot speak about, which is a state the caller already reports — far
    better than a corrupted page.
    """
    mark = producer_mark(command, suffix)
    if mark in text:
        return text
    # 🚨 REPLACE ANY MARK ALREADY THERE, DO NOT ADD A SECOND ONE. The identity
    # check reads the FIRST mark it finds, so a leftover would be invisible to
    # it while sitting in the shipped page forever — and the value the rename
    # was supposed to migrate would never actually leave the file.
    #
    # Found by an arm the receiving face asked for: it wanted the REPLACEMENT
    # counted, not just the absence of a warning, because "0 warnings" is
    # produced both by the normalisation working and by nothing having been
    # rewritten. Stamping v1.8.58's own output left two meta tags.
    text = re.sub(
        r'[ \t]*<meta name="' + re.escape(PRODUCER_ATTR) + r'" content="[^"]*">\n?',
        "", text)
    text = re.sub(
        r'\n*<!-- ' + re.escape(PRODUCER_ATTR) + r': [^>]*-->\n?', "", text)
    if suffix != ".html":
        # ⚠️ APPENDED, NOT PREPENDED. The first draft put it first and broke
        # `test_markdown_writes_markdown_content`, whose discriminator is that
        # a markdown body starts with `#`. That arm is right and the stamp was
        # wrong: a mark must not change what the document IS. The gate caught
        # it — which is the arm doing exactly its job.
        return f"{text.rstrip(chr(10))}\n\n{mark}\n"
    i = text.find("<head>")
    if i < 0:
        return text
    j = i + len("<head>")
    return f"{text[:j]}\n    {mark}{text[j:]}"


def read_producer(path: Path) -> str | None:
    """The command that wrote *path*, or None when it carries no mark.

    🚨 None is NOT "another producer". It is "this check has nothing to go
    on" — the state every file predating the mark is in. Saying those two
    with the same word is the confusion this release spent the day removing
    from the toolchain-version check, where a skipped comparison read
    exactly like agreement.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # ⚠️ BOTH ENDS. HTML carries the mark in `<head>`; markdown carries it at
    # the END, because prepending changed what the document starts with and a
    # real arm caught that. A reader that only looked at the head would report
    # every marked markdown file as unmarked — the same silence this whole
    # check exists to remove, reintroduced by the fix for a different one.
    window = text[:4096] + "\n" + text[-4096:]
    for opener, closer in ((f'<meta name="{PRODUCER_ATTR}" content="', '"'),
                           (f'<!-- {PRODUCER_ATTR}: ', ' -->')):
        i = window.find(opener)
        if i < 0:
            continue
        j = window.find(closer, i + len(opener))
        if j > 0:
            found = window[i + len(opener):j]
            # ⚠️ v1.8.58's files say `spec-batch` / `component-batch`. They are
            # this tool's own output and must not start reporting as a foreign
            # producer the moment the spelling changes — that would turn a
            # rename into a collision on every face at once.
            return LEGACY_PRODUCER_VALUES.get(found, found)
    return None


def report_overwrites_by_another_producer(output_dir: Path, will_write,
                                          command: str) -> list[str]:
    """Files this run OVERWRITES that something else wrote, and files it
    cannot speak about.

    🚨 WHY THIS EXISTS SEPARATELY FROM `report_foreign_output`. That one
    reports SURPLUS — files left behind. Measured on the very tree the
    incident happened on:

        existing *.html in the output dir   8
        this run will write                 8
        surplus                             0   -> IT SAID NOTHING

    The site route writes one page per component spec and this command
    writes the same names, so the reported 2755-line clobber produces no
    surplus at all. **The check shipped as that incident's fix would have
    been silent for that incident.** Raised by a consumer lane as a
    question; measured before answering, with a control (dropping one
    planned file makes the surplus check name it).

    ⚠️ TWO OUTCOMES, TWO WORDINGS, on that lane's insistence:

        a different mark  -> a collision that EXISTS. One line per file.
        no mark at all    -> this check knows nothing about them; they
                             predate it. ONE line for the whole directory.

    Saying both with the same word floods the first run of every face, and
    a reader who has once been shown a flood stops reading the line that
    finally matters.

    🚨 WHICH FILES HAVE NO MARK — STATED WIDER THAN THE FIRST DRAFT SAID.
    A consumer lane read the design and asked whether the limit is really
    "identical filenames". It is not; that wording understates it. Only
    `spec-batch` and `component-batch` stamp. Everything below is unmarked
    and therefore lands in the rolled-up line, never in a per-file warning:

        every page written before this version, on every face
        every page from `generate html` (11+ write sites in
            `test_doc/generator.py` — not stamped here, deliberately: a
            change that size was not worth making at the end of a release
            this large)
        every page from the single-file `generate spec` / `generate
            component` forms

    ⚠️ So a site-route page overwritten by this command is REPORTED, but as
    "no mark" rather than as a named collision. That is a weaker report, not
    silence — and the distinction is exactly why the two wordings differ.
    A reader must not take "no per-file warning" to mean "no collision".

    ⚠️ MIXED VERSIONS MAKE THE MARK COME AND GO. Raised by a consumer lane:
    regenerating with a CLI older than this one rewrites the page WITHOUT a
    mark, so the rolled-up line reappears on the next run of a new CLI. That
    is normal for the transition and is NOT evidence that another tool
    touched the directory. The toolchain-version NOTE this release also adds
    is the instrument that says a mixed version is in play.
    """
    if not output_dir.is_dir():
        return []
    lines = []
    foreign, unmarked = [], []
    for q in sorted(will_write):
        if not q.is_file():
            continue
        who = read_producer(q)
        if who is None:
            unmarked.append(q)
        elif who != producer_family(command):
            foreign.append((q, who))
    for q, who in foreign:
        lines.append(
            f"{q.name} in {output_dir} was written by `{who}` and this run "
            f"overwrites it with `{producer_family(command)}` output. Nothing "
            f"is deleted by this warning — check the directory is the one you "
            f"meant.")
    if unmarked:
        shown = ", ".join(q.name for q in unmarked[:5])
        more = "\u2026" if len(unmarked) > 5 else ""
        # 🚨 EVERY SENTENCE IS ONE FRAGMENT, DELIBERATELY. The v1.8.59 wording
        # split `will not gain one` across two f-string pieces, and THREE
        # people independently grepped the shipped text and got 0 — including
        # the one whose own index says a phrase can break on a line wrap. A
        # user quoting this line to support gets a maintainer who cannot find
        # it. Keep each sentence whole even when the line runs long; this file
        # already has 35 lines over 88 columns and no line-length gate.
        #
        # 🚨 AND THE POPULATIONS MOVE. v1.8.58 said these files "will carry it
        # once rewritten", which was false for a form that never rewrote them.
        # v1.8.59 fixed that by asserting the opposite for `generate html` as a
        # whole — and then c3c74f77 (v1.8.61) made `generate html` stamp the
        # pages it pre-generates into the source tree, so the new wording went
        # false in the other direction, and stayed there for two releases.
        # ⚠️ THE SECOND DIRECTION IS THE WORSE ONE: "no mark here is normal"
        # CLOSES the reader's search, and after v1.8.61 an unmarked page under
        # `<docs>/screens/html` may be a page the stamping missed.
        # Measured by running the command, not by reading it (2026-09-09):
        # of 8 html/md files one run wrote, 4 carried the mark and 4 did not;
        # stripping the mark from one of the 4 and re-running put it back.
        #
        # ⚠️ NOBODY READS THIS AFTER RUNNING `generate html`. The two call
        # sites are `cmd_generate_spec_batch` and `cmd_generate_component_batch`
        # — so the reader arrives by pointing `generate spec -o` at a directory
        # `generate html` had already written into, and is being told about a
        # command they did not run. That is why the wording names the PLACE a
        # file was written rather than the command that wrote it.
        #
        # 🚫 AND IT NAMES THE PRODUCER, NOT THE PATHS — THIRD TIME AROUND.
        # v1.8.58 said "rewrite it and the mark arrives" and had not counted a
        # form that never rewrites. v1.8.59 said `generate html` never marks
        # and c3c74f77 made it mark. The first cut of THIS fix listed
        # `<docs>/screens` and `<docs>/components`, and the code also calls
        # `_pre_generate_spec_docs(..., spec_subdir="requirements")` at
        # generator.py:1417 under `--app` — so a `requirements` page would have
        # landed in the "expected" bucket, which is the direction named twelve
        # lines up as the worse one. Caught by a triage lane before the tag.
        # Same mechanism all three times: the population was written from ONE
        # run instead of derived from the declaration, and the declaration says
        # `spec_subdir: str = "screens"` with a docstring naming a second value.
        # An enumeration of paths goes false the next time a path is added; a
        # sentence naming the producer does not. An arm below requires that
        # this text enumerate none of them.
        #
        # ⚠️ AND THE POPULATION IS NARROWER THAN "unmarked files in the
        # directory": `unmarked` is built from `will_write`, so it holds only
        # files THIS run is about to overwrite. An unmarked leftover the run
        # does not touch surfaces in `report_foreign_output` instead and never
        # reaches this sentence. Unchanged by this fix, stated so the next
        # reader does not have to re-derive it.
        lines.append(
            f"{len(unmarked)} file(s) in {output_dir} carry no producer mark "
            f"({shown}{more}), so this run cannot tell whether they came from this command. "
            f"Anything `jsonui-doc` wrote before v1.8.58 has no mark and will not gain one. "
            f"Neither does what `generate html` writes into its own `-o` site directory, as of v1.8.62. "
            f"The pages it pre-generates back into the source tree are the other case: those have carried the mark since v1.8.61, so an unmarked file among them is worth looking at rather than expected. "
            f"This is not a report of a collision.")
    return lines


def report_foreign_output(output_dir: Path, will_write, suffix: str) -> list[str]:
    """Files already in *output_dir* that this run does NOT write.

    🚨 WHY. A delivery lane pointed `generate component -o` at a directory
    holding `generate html`'s pages and lost 2755 lines — sidebar and styles
    replaced by a different format. Nothing looked: `-o` is taken as the
    output directory and its existing contents are never asked about.

    ⚠️ The discriminator is NOT "the directory is non-empty" — re-running a
    command over its own output is normal and must stay silent. It is "there
    are files here this command will not write", which is what a foreign
    producer leaves behind (that case: component writes 8 pages into a
    directory holding far more, each with a nav).

    ⚠️ LIMIT, stated because the count cannot state it: a foreign producer
    whose file names match this command's exactly is INVISIBLE here. The
    overwrite still happens; only the surplus is detectable.

    🚨 AND THAT LIMIT WAS THE REPORTED INCIDENT. Measured on the tree it
    happened on: 8 existing pages, 8 planned, surplus 0 — this function said
    nothing. `report_overwrites_by_another_producer` was added to cover it.
    Do not read this function as the whole check; it answers "what is left
    behind", not "whose work is being replaced".

    Reported, never refused, and the exit code is untouched — deliberately
    overwriting a directory is a real thing to want.
    """
    if not output_dir.is_dir():
        return []
    planned = {q.resolve() for q in will_write}
    existing = [q for q in sorted(output_dir.rglob(f"*{suffix}"))
                if q.is_file() and q.resolve() not in planned]
    if not existing:
        return []
    shown = ", ".join(q.name for q in existing[:5])
    more = "\u2026" if len(existing) > 5 else ""
    return [
        f"{len(existing)} file(s) already in {output_dir} will NOT be written "
        f"by this command ({shown}{more}). If they came from another generator "
        f"(`generate html` writes pages here too), this run overwrites the ones "
        f"whose names DO collide and leaves these behind. Nothing is deleted by "
        f"this warning \u2014 check the directory is the one you meant."
    ]


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

    # What this run will write, computed BEFORE writing, so the comparison is
    # against the directory as the operator left it.
    _planned = [
        output_dir / _f.relative_to(input_dir).with_name(
            _f.relative_to(input_dir).name.replace(".spec.json", suffix))
        for _f in spec_files
    ]
    for _line in report_foreign_output(output_dir, _planned, suffix):
        print(f"WARNING: {_line}", file=sys.stderr)
    for _line in report_overwrites_by_another_producer(
            output_dir, _planned, "spec-batch"):
        print(f"WARNING: {_line}", file=sys.stderr)

    validator = SpecValidator()
    success_count = 0
    error_count = 0
    # Scanned once for the run, not per spec: the answer is the same for every
    # page, and only the relative path from each page differs.
    component_pages = _component_pages_on_disk(output_dir) if to_html else {}

    for spec_file in sorted(spec_files):
        result = validator.validate_file(spec_file)

        if not result.is_valid:
            print(f"  FAILED: {spec_file.relative_to(input_dir)}")
            for error in result.errors:
                print(f"    {error}")
            error_count += 1
            continue

        # layouts_dir is passed either way so layoutFile import works
        # Preserve subdirectory structure in output
        rel_path = spec_file.relative_to(input_dir)
        output_name = rel_path.with_name(rel_path.name.replace(".spec.json", suffix))
        output_path = output_dir / output_name

        # Computed from where THIS page lands, which is why it is done here
        # and not inside the emitter: a nested spec's page is further from the
        # component pages than a top-level one, and the emitter is not told
        # where it is being written.
        content = (generate_spec_html(
                       result.spec_data, layouts_dir=layouts_dir,
                       spec_dir=spec_file.parent,
                       component_links=_component_links_for_page(
                           component_pages, output_path.parent))
                   if to_html
                   else generate_spec_markdown(result.spec_data, layouts_dir=layouts_dir,
                                               spec_dir=spec_file.parent))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(stamp_producer(content, "spec-batch", suffix))

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
            # ⚠️ The single-file form stamps too, with the SAME FAMILY as
            # the batch form. v1.8.58 stamped only the batch forms, so a
            # directory maintained by this form stayed permanently unmarked
            # while the tool's own output told its reader the mark would
            # arrive 'once rewritten'. Same family, so rewriting with
            # either form is silent — which is the whole point of naming
            # the family rather than the subcommand.
            f.write(stamp_producer(
                    content, "component",
                    ".html" if output_format == "html" else ".md"))
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

    # What this run will write, computed BEFORE writing, so the comparison is
    # against the directory as the operator left it.
    _planned = [
        output_dir / _f.relative_to(input_dir).with_name(
            _f.relative_to(input_dir).name.replace(".component.json", suffix))
        for _f in component_files
    ]
    for _line in report_foreign_output(output_dir, _planned, suffix):
        print(f"WARNING: {_line}", file=sys.stderr)
    for _line in report_overwrites_by_another_producer(
            output_dir, _planned, "component-batch"):
        print(f"WARNING: {_line}", file=sys.stderr)

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
            f.write(stamp_producer(content, "component-batch", suffix))

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
        help="Generate HTML directory with index for all test files "
             "(ALSO writes outside -o: see --help)",
        description=(
            "Generate the documentation site for all test files.\n"
            "\n"
            "⚠️ THIS COMMAND WRITES OUTSIDE -o.\n"
            "Before building the site it regenerates, in the SOURCE tree:\n"
            "    <docs>/<screens|requirements>/html/  and  .../md/\n"
            "    <docs>/components/html/              and  .../md/\n"
            "for the root scope and for EVERY --app passed in the same run.\n"
            "So one run with two --app flags rewrites both apps' trees, and two\n"
            "lanes pointing -o at different directories are NOT isolated from\n"
            "each other -- whichever runs last leaves its version in the source\n"
            "tree. Reported 2026-09-08 after two lanes measured against that\n"
            "assumption for a whole release cycle.\n"
            "\n"
            "The paths actually written are printed at the end of the run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gen_html_parser.add_argument(
        "input",
        help="Input directory containing .test.json files"
    )
    gen_html_parser.add_argument(
        "-o", "--output",
        help="Site output directory (default: html). NOT the only place this "
             "command writes -- see the command description."
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
        "--config",
        metavar="PATH",
        help="jui.config.json to read unitContracts from (default: walk up from "
             "the input directory, or per --app directory). Use this when the "
             "config governing specs is not the first one above the tests tree "
             "— a split tree often has an unrelated config at the repository root"
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
