#!/usr/bin/env python3
"""
JsonUI Test CLI

Command-line interface for validating and generating test files.
For documentation generation, use jsonui-doc (document_tools).
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from . import __version__
from .validator import TestValidator
from .report import load_results_file, generate_junit, generate_html


def cmd_validate(args):
    """Handle validate command."""
    validator = TestValidator()
    total_errors = 0
    total_warnings = 0
    files_checked = 0
    valid_test_files = []

    # Collect files
    files_to_validate = []
    for path in args.files:
        p = Path(path)
        if p.is_dir():
            # Collect test files
            files_to_validate.extend(p.rglob("*.test.json"))
            # Collect mock definition files
            files_to_validate.extend(p.rglob("*.mock.json"))
            # Collect description files in descriptions folders
            for desc_dir in p.rglob("descriptions"):
                if desc_dir.is_dir():
                    files_to_validate.extend(desc_dir.glob("*.json"))
        elif p.exists():
            files_to_validate.append(p)
        else:
            print(f"Warning: Path not found: {path}", file=sys.stderr)

    if not files_to_validate:
        print("No test or description files found")
        return 1

    # Validate each file
    for file_path in sorted(files_to_validate):
        files_checked += 1
        result = validator.validate_file(file_path)

        if args.verbose or result.errors or result.warnings:
            print(f"\n{file_path}")

        if result.errors:
            for error in result.errors:
                print(error)
            total_errors += len(result.errors)

        if result.warnings and not args.quiet:
            for warning in result.warnings:
                print(warning)
            total_warnings += len(result.warnings)

        if result.is_valid and not result.warnings and args.verbose:
            print("  OK")

        if result.is_valid and Path(file_path).name.endswith(".test.json"):
            valid_test_files.append(Path(file_path))

    # Summary
    print(f"\n{'='*50}")
    status = "PASSED" if total_errors == 0 else "FAILED"
    print(f"Result: {status}")
    print(f"Files: {files_checked}, Errors: {total_errors}, Warnings: {total_warnings}")

    if total_errors > 0:
        return 1

    # Mock contract drift, on the same gate. `--check` existed but nothing
    # called it, so a mock encoding a contract the server does not have kept
    # the suite green (mock-contract-validation-does-not-run).
    if not getattr(args, "no_mock_check", False):
        mock_rc = _check_mocks_against_swagger(getattr(args, "config", None))
        if mock_rc != 0:
            return mock_rc

    # Success-gated flatten-install: distribute validated tests to the platform
    # locations declared in config (no-op when nothing is configured).
    if not getattr(args, "no_install", False):
        install_rc = _install_validated_tests(valid_test_files, getattr(args, "config", None))
        if install_rc != 0:
            return install_rc

    return 0


def _check_mocks_against_swagger(config_path):
    """Regenerate `generated/` if needed, then check the mocks against swagger.

    Silent no-op when the project has no mock config, so this stays free for
    projects that do not use mocks.
    """
    from .mock.generate import GENERATED_DIR, generate, CheckReport

    config, cfg_path = _load_mock_config(config_path)
    swaggers = config.get("swagger") or []
    mock_dir = config.get("mockDir")
    if not swaggers or not mock_dir:
        return 0
    root = cfg_path.parent if cfg_path else Path(".")
    mock_path = Path(mock_dir)
    if not mock_path.is_absolute():
        mock_path = root / mock_path
    if not mock_path.exists():
        return 0

    resolved = _resolve_swaggers(swaggers, root, cfg_path)
    if not resolved:
        return 0

    scope = _load_path_scope(config_path)

    # generated/ is meant to be gitignorable, so it has to rebuild itself on a
    # fresh clone or a first CI run. Rebuilding when it is missing or older
    # than the swagger keeps `validate` the single entry point.
    gen_root = mock_path / GENERATED_DIR
    newest_swagger = max(
        (Path(s).stat().st_mtime for s in resolved if Path(s).exists()), default=0)
    generated_at = max(
        (p.stat().st_mtime for p in gen_root.rglob("*.mock.json")), default=0)
    if generated_at < newest_swagger:
        try:
            built = generate(resolved, mock_path, scope=scope)
        except (OSError, ValueError, KeyError) as e:
            # Running the suite against an empty generated/ turns every
            # unmocked operation into a 404 and a confusing red.
            print(f"\n{'='*50}")
            print(f"Mock generation failed: {e}")
            return 1
        if built.created:
            print(f"\nRegenerated {len(built.created)} mock file(s) "
                  f"into {mock_dir}/{GENERATED_DIR}/")

    report = generate(resolved, mock_path, check=True, scope=scope,
                      strict=bool(config.get("checkOptionalFields", False)))
    if not isinstance(report, CheckReport) or not report.has_drift:
        return 0

    print(f"\n{'='*50}")
    print("Mock contract drift:")
    for rel in report.missing:
        print(f"  [MISSING] {rel} (in swagger, no mock file)")
    for rel in report.orphaned:
        print(f"  [ORPHAN]  {rel} (mock file, not in swagger)")
    for msg in report.drifted:
        print(f"  [DRIFT]   {msg}")
    for drift in report.errors:
        print(f"  [BODY]    {drift}")
    print("Fix with `jsonui-test mock generate --update-default`, "
          "or pass --no-mock-check to skip this gate.")
    return 1


def _load_test_config(explicit_path=None):
    """Read the 'test' section from jui.config.json (or an explicit config path).

    Returns (test_config_dict, config_path_or_None).
    """
    candidates = [Path(explicit_path)] if explicit_path else [
        Path("jui.config.json"), Path("jsonui-test.config.json")]
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("test", {}), c
            except (OSError, json.JSONDecodeError):
                pass
    return {}, None


# addMedia fixture types shared by the iOS/Android drivers.
MEDIA_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".mp4")


def _resolve_media_files(test_config, project_root):
    """Collect addMedia fixtures from `test.mediaDir` (default tests/media)."""
    media_dir = Path(test_config.get("mediaDir") or "tests/media")
    if not media_dir.is_absolute():
        media_dir = project_root / media_dir
    if not media_dir.is_dir():
        return []
    return sorted(
        p for p in media_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS
    )


def _install_validated_tests(valid_test_files, config_path):
    """Flatten-install valid .test.json files per config. Returns exit code."""
    from .install import resolve_targets, flatten_install

    test_config, cfg_path = _load_test_config(config_path)
    if not cfg_path:
        return 0  # no config → validate-only

    project_root = cfg_path.parent
    targets = resolve_targets(test_config, project_root)
    if not targets:
        return 0  # no install destinations declared → validate-only

    media_files = _resolve_media_files(test_config, project_root)
    report = flatten_install(valid_test_files, targets, media_files=media_files)

    if report.has_collision:
        print(f"\n{'='*50}")
        print("Install ABORTED: duplicate file names (flat layout needs unique names per target):")
        for platform, name, srcs in report.collisions:
            print(f"  [COLLISION] {name} ({platform})")
            for src in srcs:
                print(f"              {src}")
        return 1

    print(f"\n{'='*50}")
    print(f"Installed {len(report.copied)} test file(s) → {len(targets)} target(s)"
          f" (cleaned {report.removed} stale):")
    for platform, dest in report.targets:
        installed = len(report.installed.get(platform, []))
        details = []
        skipped = len(report.skipped_files.get(platform, []))
        if skipped:
            details.append(f"{skipped} skipped")
        pruned = len(report.pruned_cases.get(platform, []))
        if pruned:
            details.append(f"{pruned} case(s) pruned")
        flows = report.skipped_flows.get(platform, [])
        if flows:
            details.append(f"{len(flows)} flow(s) dropped: {', '.join(flows)}")
        media = len(report.media_copied.get(platform, []))
        if media:
            details.append(f"{media} media file(s) → media/")
        detail = f" ({', '.join(details)})" if details else ""
        print(f"  {platform}: {installed} test(s){detail} → {dest}")
    return 0


def cmd_generate_test_screen(args):
    """Handle 'generate test screen' command - create screen test file template."""
    name = args.name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/screens/{name.lower()}/{name.lower()}.test.json"

    # Create test template
    test_template = {
        "type": "screen",
        "metadata": {
            "name": f"{name}_test",
            "description": f"Tests for {name} screen"
        },
        "cases": [
            {
                "name": "initial_display",
                "description": "Verify initial screen state",
                "steps": [
                    {"assert": "visible", "id": "TODO_element_id"}
                ]
            }
        ]
    }

    # Add platform if specified
    if args.platform:
        test_template["platform"] = args.platform

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(test_template, f, indent=2, ensure_ascii=False)

    print(f"Created screen test file: {output}")
    print(f"  Edit the file to add proper element IDs and test cases.")

    return 0


def cmd_generate_test_flow(args):
    """Handle 'generate test flow' command - create flow test file template."""
    name = args.name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/flows/{name.lower()}/{name.lower()}.test.json"

    # Create flow test template
    test_template = {
        "type": "flow",
        "metadata": {
            "name": f"{name}_flow",
            "description": f"{name} flow test"
        },
        "steps": [
            {"action": "waitFor", "id": "TODO_start_screen"},
            {"action": "tap", "id": "TODO_element_id"},
            {"assert": "visible", "id": "TODO_end_screen"}
        ]
    }

    # Add platform if specified
    if args.platform:
        test_template["platform"] = args.platform

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(test_template, f, indent=2, ensure_ascii=False)

    print(f"Created flow test file: {output}")
    print(f"  Edit the file to add proper element IDs and test steps.")

    return 0


def cmd_generate_description(args):
    """Handle 'generate description' command - create description JSON file for a specific test case."""
    test_type = args.test_type  # "screen" or "flow"
    name = args.name
    case_name = args.case_name
    output_path = args.path

    # Determine output path if not specified
    if not output_path:
        output_path = f"tests/{test_type}s/{name.lower()}/descriptions/{case_name}.json"

    # Create description JSON
    description_data = {
        "case_name": case_name,
        "summary": "",
        "preconditions": [],
        "test_procedure": [],
        "expected_results": [],
        "notes": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    # Write file
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(description_data, f, indent=2, ensure_ascii=False)

    print(f"Created description file: {output}")
    print(f"  Edit the file to add test documentation.")
    print(f"\nTo link to test file, add 'descriptionFile' to the case:")
    print(f'  "descriptionFile": "descriptions/{case_name}.json"')

    return 0


def cmd_report(args):
    """Handle 'report' command - convert results JSON to JUnit XML or HTML."""
    runs = []
    total_errors = 0

    for path in args.files:
        file_path = Path(path)
        if not file_path.exists():
            print(f"Error: Results file not found: {path}", file=sys.stderr)
            total_errors += 1
            continue

        data, errors = load_results_file(file_path)
        if errors:
            print(f"\n{file_path}", file=sys.stderr)
            for error in errors:
                print(f"  [ERROR] {error}", file=sys.stderr)
            total_errors += len(errors)
            continue

        runs.append(data)

    if total_errors > 0:
        print(f"\nError: {total_errors} error(s) in results file(s). "
              f"Input must match results.schema.json (jsonui-test-results format).", file=sys.stderr)
        return 1

    if args.format == "junit":
        content = generate_junit(runs)
        default_output = "report.xml"
    else:
        content = generate_html(runs)
        default_output = "report.html"

    output = Path(args.output) if args.output else Path(default_output)
    if output.parent != Path('.'):
        output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w', encoding='utf-8') as f:
        f.write(content)

    total_cases = sum(len(s.get("results", [])) for run in runs for s in run.get("suites", []))
    print(f"Created {args.format} report: {output}")
    print(f"  Files: {len(runs)}, Test cases: {total_cases}")

    return 0


def _read_config_doc(explicit_path=None):
    """The whole jui.config.json document, or ({}, None) when there is none."""
    candidates = [Path(explicit_path)] if explicit_path else [
        Path("jui.config.json"), Path("jsonui-test.config.json")]
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f), c
            except (OSError, json.JSONDecodeError):
                pass
    return {}, None


def _load_mock_config(explicit_path=None):
    """Read the 'mock' section from jui.config.json (or an explicit config path).

    `swagger` is normalised to a list here rather than at each call site: a
    bare string is the obvious thing to write, and every consumer of this
    config iterates the value — so a string was opened one character at a
    time and failed with `Is a directory: '.'`, an error that points at the
    filesystem instead of at the key.
    """
    data, c = _read_config_doc(explicit_path)
    if c is None:
        return {}, None
    config = dict(data.get("mock", data))
    swagger = config.get("swagger")
    if isinstance(swagger, str):
        config["swagger"] = [swagger]
    elif swagger is not None and not isinstance(swagger, list):
        print(f"Warning: mock.swagger in {c} is "
              f"{type(swagger).__name__}; expected a path or a list "
              "of paths — ignoring", file=sys.stderr)
        config["swagger"] = []
    return config, c


def _load_path_scope(explicit_path=None):
    """The endpoints this project declares it consumes.

    Read from the same config the DTO codegen already filters on
    (`api.schemas.include_paths` / `exclude_paths`), so a shared swagger's
    other realms stop being counted as mocks this project owes.
    """
    from .mock.scope import PathScope

    data, _ = _read_config_doc(explicit_path)
    return PathScope.from_config(data)


def _resolve_swaggers(swaggers, root, config_path):
    """Absolute swagger paths, reporting the ones the config points nowhere at."""
    resolved = []
    for entry in swaggers:
        path = Path(entry)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            where = f" (mock.swagger in {config_path})" if config_path else ""
            print(f"Warning: swagger not found: {path}{where}", file=sys.stderr)
            continue
        resolved.append(str(path))
    return resolved


def cmd_mock_generate(args):
    """Scaffold or diff mock definition files from OpenAPI specs."""
    from .mock.generate import generate, update_default, GenerateReport, CheckReport

    config, _ = _load_mock_config(getattr(args, "config", None))
    swaggers = list(args.swagger) if args.swagger else list(config.get("swagger") or [])
    mock_dir = args.out or config.get("mockDir", "tests/mocks")
    if not swaggers:
        print("Error: no swagger specified (use --swagger or set mock.swagger in jui.config.json)", file=sys.stderr)
        return 1

    if getattr(args, "update_default", False):
        dry_run = getattr(args, "dry_run", False)
        upd = update_default(swaggers, mock_dir, dry_run=dry_run,
                             scope=_load_path_scope(getattr(args, "config", None)))
        for rel in upd.updated:
            paths = upd.added.get(rel)
            detail = f" (+{', '.join(paths)})" if paths else " (source route)"
            print(f"  [{'WOULD UPDATE' if dry_run else 'UPDATED'}] {rel}{detail}")
        verb = "Would repair" if dry_run else "Repaired"
        print(f"\n{verb} the default scenario of {len(upd.updated)} mock file(s), "
              f"{len(upd.unchanged)} already current, {len(upd.skipped)} not present "
              f"(run without --update-default to scaffold those).")
        print("Only missing required fields were added — no existing value was "
              "overwritten, nothing was removed, and other scenarios were not touched.")
        if upd.needs_review:
            print(f"\n{len(upd.needs_review)} mock(s) have violations a merge cannot "
                  "decide — fix these by hand, keeping your test data:")
            for rel, problems in upd.needs_review:
                print(f"  {rel}")
                for problem in problems:
                    print(f"    {problem}")
        return 0

    report = generate(swaggers, mock_dir, check=args.check,
                      strict=getattr(args, "strict", False),
                      scope=_load_path_scope(getattr(args, "config", None)))

    if isinstance(report, CheckReport):
        for rel in report.missing:
            print(f"  [MISSING] {rel} (in swagger, no mock file)")
        for rel in report.orphaned:
            print(f"  [ORPHAN]  {rel} (mock file, not in swagger)")
        for rel in report.out_of_scope:
            print(f"  [SCOPE]   {rel} — outside this project's API paths, "
                  "safe to delete")
        for msg in report.drifted:
            print(f"  [DRIFT]   {msg}")
        for drift in report.errors:
            print(f"  [BODY]    {drift}")
        notes = [d for d in report.bodies
                 if d.is_note_only and not d.generated and not report.strict]
        for drift in notes:
            print(f"  [NOTE]    {drift}")
        for rel in report.misnamed:
            print(f"  [NAME]    {rel}")
        for note in report.unmatched:
            print(f"  [NOTE]    {note} — not compared")
        for warning in report.warnings:
            print(f"  [WARN]    {warning}")
        if report.scope_note:
            print(f"\nAPI path scope: {report.scope_note} "
                  f"({report.scope_excluded} endpoint(s) outside it, not checked)")
        if report.has_drift:
            print(f"\nDrift detected: {len(report.missing)} missing, "
                  f"{len(report.orphaned)} orphaned, {len(report.drifted)} drifted, "
                  f"{len(report.errors)} stale body(ies)")
            if report.errors:
                print("Refresh the generated bodies with "
                      "`jsonui-test mock generate --update-default` "
                      "(hand-grown scenarios are preserved).")
            return 1
        print("No drift: mocks are in sync with swagger.")
        return 0

    for w in report.warnings:
        print(f"  [WARN] {w}")
    print(f"\nGenerated {len(report.created)} mock file(s) into "
          f"{mock_dir}/generated/ (rewritten each run — safe to gitignore); "
          f"{len(report.skipped)} route(s) already served by a hand-written mock.")
    if report.out_of_scope:
        print(f"{len(report.out_of_scope)} endpoint(s) outside this project's "
              "API paths were not scaffolded.")
    return 0


def _make_artifacts_post_run_hook(explicit_config):
    """Post-run hook for `mock serve --artifacts`: pull artifacts for the target.

    RunManager wraps the hook in try/except and logs failures to its own
    line buffer, so this never crashes the server.
    """
    from . import artifacts

    def hook(target, returncode):
        platform = str(target).lower()
        if platform not in ("ios", "android", "web"):
            return  # custom targets have no known artifact source
        test_cfg, cfg_path = _load_test_config(explicit_config)
        project_root = cfg_path.parent if cfg_path else Path(".")
        out_root = artifacts.resolve_out_root(test_cfg, project_root)
        if platform == "ios":
            result = artifacts.pull_ios(test_cfg, project_root, out_root)
        elif platform == "android":
            result = artifacts.pull_android(test_cfg, project_root, out_root)
        else:
            result = artifacts.pull_web(test_cfg, project_root, out_root)
        line = f"[artifacts] {platform}: {len(result.files)} file(s) -> {result.stamp_dir or out_root}"
        if result.skipped:
            line += f" (skipped: {'; '.join(result.skipped)})"
        print(line, flush=True)

    return hook


def cmd_mock_serve(args):
    """Start the local mock server + control panel."""
    from .mock.contract import ContractIndex, ContractLog
    from .mock.server import MockStore, MockServer, RunManager

    config, config_path = _load_mock_config(getattr(args, "config", None))
    mock_dir = args.mock_dir or config.get("mockDir", "tests/mocks")
    # `is not None` (not `or`): --port 0 means "pick an ephemeral port" and
    # must not fall through to the config/default port.
    port = args.port if args.port is not None else config.get("server", {}).get("port", 8790)
    run_targets = config.get("runTargets", {})
    project_root = config_path.parent if config_path else Path(".")

    if not Path(mock_dir).exists():
        print(f"Error: mock dir not found: {mock_dir} (run 'jsonui-test mock generate' first)", file=sys.stderr)
        return 1

    post_run_hook = None
    if getattr(args, "artifacts", False):
        post_run_hook = _make_artifacts_post_run_hook(getattr(args, "config", None))

    # Request-contract checking. On by default: a mock that answers a
    # request the real API would reject is the failure mode this exists for,
    # and an opt-in check is one nobody opts into.
    contract = ContractIndex()
    contract_log = ContractLog()
    if config.get("validateRequests", True) and not getattr(args, "no_validate_requests", False):
        contract = ContractIndex.load(list(config.get("swagger") or []))
        if not contract:
            print("  request validation: off (no swagger configured)")

    store = MockStore.load(mock_dir)
    server = MockServer(store, RunManager(run_targets, project_root,
                                          post_run_hook=post_run_hook,
                                          contract_log=contract_log),
                        port=port, contract=contract, contract_log=contract_log)
    # Bind BEFORE printing the banner: consumers parse the URL/token from
    # stdout as the "server is up" signal, so a banner followed by a bind
    # failure reads as a successful start. Bind also resolves port 0 to
    # the real ephemeral port.
    try:
        server.bind()
    except OSError as e:
        reason = e.strerror or str(e)
        print(f"Error: cannot bind 127.0.0.1:{port} ({reason})", file=sys.stderr)
        return 1
    print(f"JsonUI mock server: http://127.0.0.1:{server.port}")
    print(f"  loaded {len(store.endpoints)} endpoint(s) from {mock_dir}/")
    if store.overrides:
        # A hand-written mock silently shadowing a generated one is the
        # confusing case, so say so.
        print(f"  {len(store.overrides)} hand-written mock(s) overlay the generated tree:")
        for rel in store.overrides[:10]:
            print(f"    {rel}")
        if len(store.overrides) > 10:
            print(f"    ... and {len(store.overrides) - 10} more")
    print(f"  control panel: http://127.0.0.1:{server.port}/__jsonui__/panel")
    # flush: piped stdout is block-buffered and serve_forever() never
    # returns — without an explicit flush the banner (and the admin token,
    # whose only channel is stdout) never reaches the consumer.
    print(f"  admin token:   {server.token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()
    # Violations from requests made outside a panel-driven run (a suite
    # pointed straight at the server) would otherwise go unreported.
    summary = contract_log.summary()
    if summary:
        print()
        for line in summary:
            print(line)
        return 1
    return 0


def cmd_artifacts_pull(args):
    """Pull test artifacts (xcresult attachments / on-device files) locally."""
    from . import artifacts

    test_cfg, cfg_path = _load_test_config(getattr(args, "config", None))
    project_root = cfg_path.parent if cfg_path else Path(".")
    out_root = artifacts.resolve_out_root(test_cfg, project_root, override=args.out)

    platforms = ["ios", "android", "web"] if args.platform == "all" else [args.platform]
    results = []
    for platform in platforms:
        try:
            if platform == "ios":
                results.append(artifacts.pull_ios(
                    test_cfg, project_root, out_root,
                    xcresult_override=args.xcresult))
            elif platform == "android":
                results.append(artifacts.pull_android(
                    test_cfg, project_root, out_root,
                    serial_override=args.serial, clean=args.clean))
            else:
                results.append(artifacts.pull_web(
                    test_cfg, project_root, out_root, clean=args.clean))
        except artifacts.ArtifactsConfigError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    files = [f for r in results for f in r.files]
    skipped = [f"{r.platform}: {reason}" for r in results for reason in r.skipped]

    if args.json:
        print(json.dumps({
            "outputDir": str(out_root),
            "files": files,
            "skipped": skipped,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r.files:
                print(f"{r.platform}: pulled {len(r.files)} file(s) -> {r.stamp_dir}")
            for reason in r.skipped:
                print(f"{r.platform}: skipped ({reason})")
        print(f"Output dir: {out_root}")

    return artifacts.pull_exit_code(args.platform, results)


def cmd_artifacts_status(args):
    """Show resolved artifacts config and files currently in the artifacts dir."""
    from . import artifacts

    test_cfg, cfg_path = _load_test_config(getattr(args, "config", None))
    project_root = cfg_path.parent if cfg_path else Path(".")
    info = artifacts.status(test_cfg, project_root)

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"Artifacts dir: {info['artifactsDir']}")
        print(f"  ios.xcresult:   {info['ios']['xcresult'] or '(none found)'}")
        print(f"  android.appId:  {info['android']['appId'] or '(not set)'}")
        print(f"  android.serial: {info['android']['serial'] or '(default device)'}")
        print(f"  existing files: {len(info['existing'])}")
        for f in info["existing"]:
            print(f"    {f}")

    return 0


def _steps_use_add_media(steps):
    """True if any step (or nested repeat/retry step) is an addMedia step
    reachable on iOS (i.e. not gated off ios by its own `when.platform`)."""
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        when = step.get("when")
        when_platform = when.get("platform") if isinstance(when, dict) else None
        if when_platform is not None:
            allowed = when_platform if isinstance(when_platform, list) else [when_platform]
            if "ios" not in allowed and "all" not in allowed:
                continue
        if step.get("action") == "addMedia":
            return True
        if _steps_use_add_media(step.get("steps")):
            return True
    return False


def _platform_reaches_ios(value):
    """Mirror of the install-time platform-membership rules, for target ios."""
    if value is None:
        return True
    if isinstance(value, str):
        return value in ("all", "ios")
    if isinstance(value, list):
        return "ios" in value
    return True


def _test_uses_add_media_on_ios(data):
    """True if a parsed test file can execute an addMedia step on iOS."""
    if not isinstance(data, dict):
        return False
    if not _platform_reaches_ios(data.get("platform")):
        return False
    if data.get("type") == "screen":
        for case in data.get("cases") or []:
            if not isinstance(case, dict):
                continue
            if not _platform_reaches_ios(case.get("platform")):
                continue
            if _steps_use_add_media(case.get("steps")):
                return True
        return False
    return any(_steps_use_add_media(data.get(k)) for k in ("setup", "steps", "teardown"))


def cmd_pregrant(args):
    """Pre-grant photo-library add access to the iOS UITest runner.

    addMedia on iOS seeds the photo library from the xctrunner process, which
    needs photos-add authorization. Granting it up front (before xcodebuild)
    means no permission alert ever appears. Probed on iOS 18.6: the service
    must be `photos-add` — `photos` is written to TCC but not honored for the
    runner — and the grant works pre-install and survives reinstalls.
    """
    import subprocess

    test_config, cfg_path = _load_test_config(getattr(args, "config", None))

    # 1) Scan for addMedia usage reachable on iOS.
    paths = getattr(args, "paths", None) or []
    files = []
    if paths:
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                files.extend(sorted(pp.rglob("*.test.json")))
            elif pp.exists():
                files.append(pp)
            else:
                print(f"Warning: Path not found: {p}", file=sys.stderr)
    else:
        root = cfg_path.parent if cfg_path else Path(".")
        tests_dir = root / "tests"
        if tests_dir.is_dir():
            files = sorted(tests_dir.rglob("*.test.json"))

    uses = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _test_uses_add_media_on_ios(data):
            uses.append(f)
    if not uses and not getattr(args, "force", False):
        print("pregrant: no iOS-reachable addMedia steps found — nothing to grant")
        return 0

    # 2) UITest bundle id → runner id (<bundle-id>.xctrunner).
    bundle_id = getattr(args, "bundle_id", None)
    if not bundle_id:
        ios_entry = (test_config.get("install") or {}).get("ios")
        if isinstance(ios_entry, dict):
            bundle_id = ios_entry.get("uitestBundleId") or ios_entry.get("uitest_bundle_id")
    if not bundle_id:
        print("pregrant: UITest bundle id unknown — pass --bundle-id or set "
              "test.install.ios.uitestBundleId in the config", file=sys.stderr)
        return 1
    runner_id = bundle_id if bundle_id.endswith(".xctrunner") else bundle_id + ".xctrunner"

    # 3) Simulator UDID (simctl privacy needs a booted device).
    udid = getattr(args, "udid", None)
    if not udid:
        try:
            out = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "booted", "-j"],
                capture_output=True, text=True, check=True).stdout
            devices = [d for devs in json.loads(out).get("devices", {}).values()
                       for d in devs if d.get("state") == "Booted"]
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"pregrant: could not list booted simulators: {e}", file=sys.stderr)
            return 1
        if len(devices) == 1:
            udid = devices[0]["udid"]
        elif not devices:
            print("pregrant: no booted simulator — boot one first "
                  "(simctl privacy needs a booted device)", file=sys.stderr)
            return 1
        else:
            print("pregrant: multiple booted simulators — pass --udid:", file=sys.stderr)
            for d in devices:
                print(f"  {d['udid']}  {d.get('name', '?')}", file=sys.stderr)
            return 1

    # 4) Grant.
    cmd = ["xcrun", "simctl", "privacy", udid, "grant", "photos-add", runner_id]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"pregrant: {' '.join(cmd)} failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"pregrant: granted photos-add to {runner_id} on {udid}"
          f" ({len(uses)} test file(s) use addMedia)")
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="jsonui-test",
        description="JsonUI Test CLI - Validate and generate test files"
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        aliases=["v"],
        help="Validate test files"
    )
    validate_parser.add_argument(
        "files",
        nargs="+",
        help="Files or directories to validate"
    )
    validate_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all files, including valid ones"
    )
    validate_parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Hide warnings, show only errors"
    )
    validate_parser.add_argument(
        "--no-install",
        action="store_true",
        help="Validate only; skip flatten-install even if test.install is configured"
    )
    validate_parser.add_argument(
        "--no-mock-check",
        action="store_true",
        help="Skip the mock-vs-swagger contract check (runs when mock.swagger "
             "and mock.mockDir are configured)"
    )
    validate_parser.add_argument(
        "--config",
        help="Config file for test.install destinations (default: jui.config.json)"
    )

    # Generate command with subcommands
    generate_parser = subparsers.add_parser(
        "generate",
        aliases=["g"],
        help="Generate test files and descriptions"
    )
    generate_subparsers = generate_parser.add_subparsers(dest="generate_type", help="Generation type")

    # Generate test subcommand with screen/flow subcommands
    gen_test_parser = generate_subparsers.add_parser(
        "test",
        aliases=["t"],
        help="Generate test file template"
    )
    gen_test_subparsers = gen_test_parser.add_subparsers(dest="test_type", help="Test type")

    # Generate test screen subcommand
    gen_test_screen_parser = gen_test_subparsers.add_parser(
        "screen",
        help="Generate screen test file template"
    )
    gen_test_screen_parser.add_argument(
        "name",
        help="Screen name (e.g., login, home)"
    )
    gen_test_screen_parser.add_argument(
        "--path",
        help="Output test file path (default: tests/screens/<name>/<name>.test.json)"
    )
    gen_test_screen_parser.add_argument(
        "-p", "--platform",
        choices=["ios", "android", "web", "all"],
        help="Target platform"
    )

    # Generate test flow subcommand
    gen_test_flow_parser = gen_test_subparsers.add_parser(
        "flow",
        help="Generate flow test file template"
    )
    gen_test_flow_parser.add_argument(
        "name",
        help="Flow name (e.g., login, checkout)"
    )
    gen_test_flow_parser.add_argument(
        "--path",
        help="Output test file path (default: tests/flows/<name>/<name>.test.json)"
    )
    gen_test_flow_parser.add_argument(
        "-p", "--platform",
        choices=["ios", "android", "web", "all"],
        help="Target platform"
    )

    # Generate description subcommand with screen/flow subcommands
    gen_desc_parser = generate_subparsers.add_parser(
        "description",
        aliases=["d", "desc"],
        help="Generate description JSON file for a test case"
    )
    gen_desc_subparsers = gen_desc_parser.add_subparsers(dest="test_type", help="Test type")

    # Generate description screen subcommand
    gen_desc_screen_parser = gen_desc_subparsers.add_parser(
        "screen",
        help="Generate description for screen test case"
    )
    gen_desc_screen_parser.add_argument(
        "name",
        help="Screen name (e.g., login, home)"
    )
    gen_desc_screen_parser.add_argument(
        "case_name",
        help="Test case name (e.g., initial_display, error_case_1)"
    )
    gen_desc_screen_parser.add_argument(
        "--path",
        help="Output file path (default: tests/screens/<name>/descriptions/<case_name>.json)"
    )

    # Generate description flow subcommand
    gen_desc_flow_parser = gen_desc_subparsers.add_parser(
        "flow",
        help="Generate description for flow test case"
    )
    gen_desc_flow_parser.add_argument(
        "name",
        help="Flow name (e.g., login, checkout)"
    )
    gen_desc_flow_parser.add_argument(
        "case_name",
        help="Test case name (e.g., happy_path, error_handling)"
    )
    gen_desc_flow_parser.add_argument(
        "--path",
        help="Output file path (default: tests/flows/<name>/descriptions/<case_name>.json)"
    )

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        aliases=["r"],
        help="Convert results JSON (results.schema.json) to JUnit XML or HTML"
    )
    report_parser.add_argument(
        "files",
        nargs="+",
        help="Results JSON files to convert (multiple inputs merge into one report)"
    )
    report_parser.add_argument(
        "-f", "--format",
        choices=["junit", "html"],
        required=True,
        help="Report format"
    )
    report_parser.add_argument(
        "-o", "--output",
        help="Output file path (default: report.xml / report.html)"
    )

    # Mock command (nested: mock generate | mock serve)
    mock_parser = subparsers.add_parser(
        "mock",
        aliases=["m"],
        help="Generate and serve API mocks from OpenAPI"
    )
    mock_subparsers = mock_parser.add_subparsers(dest="mock_action", help="Mock action")

    mock_gen_parser = mock_subparsers.add_parser("generate", help="Scaffold mock files from swagger")
    mock_gen_parser.add_argument("--swagger", action="append", help="Path to an OpenAPI file (repeatable)")
    mock_gen_parser.add_argument("--out", help="Output mock dir (default: mock.mockDir or tests/mocks)")
    mock_gen_parser.add_argument("--config", help="Config file (default: jui.config.json)")
    mock_gen_parser.add_argument("--check", action="store_true", help="Report drift vs swagger, do not write")
    mock_gen_parser.add_argument(
        "--strict", action="store_true",
        help="With --check, treat a missing OPTIONAL field as drift too "
             "(same as mock.checkOptionalFields=true). Off by default: "
             "omitting an optional field is a valid instance, and failing on "
             "it buries the real violations",
    )
    mock_gen_parser.add_argument(
        "--dry-run", action="store_true",
        help="With --update-default, report what would change without writing",
    )
    mock_gen_parser.add_argument(
        "--update-default", action="store_true",
        help="Repair each existing mock's default scenario: add the required "
             "fields the contract has and the body lacks, refresh the source "
             "route, and change nothing else. No existing value is overwritten",
    )

    mock_serve_parser = mock_subparsers.add_parser("serve", help="Run the mock server + panel")
    mock_serve_parser.add_argument("--port", type=int, help="Port (default: mock.server.port or 8790)")
    mock_serve_parser.add_argument("--mock-dir", help="Mock dir (default: mock.mockDir or tests/mocks)")
    mock_serve_parser.add_argument("--config", help="Config file (default: jui.config.json)")
    mock_serve_parser.add_argument(
        "--no-validate-requests", action="store_true",
        help="Do not check requests against the swagger contract "
             "(same as mock.validateRequests=false)",
    )
    mock_serve_parser.add_argument("--artifacts", action="store_true",
                                   help="After an ios/android run target finishes, pull its artifacts automatically")

    # Artifacts command (nested: artifacts pull | artifacts status)
    artifacts_parser = subparsers.add_parser(
        "artifacts",
        aliases=["a"],
        help="Pull test artifacts (screenshots/recordings) from devices and xcresults"
    )
    artifacts_subparsers = artifacts_parser.add_subparsers(dest="artifacts_action", help="Artifacts action")

    artifacts_pull_parser = artifacts_subparsers.add_parser(
        "pull", help="Pull artifacts into the artifacts dir")
    artifacts_pull_parser.add_argument("--platform", choices=["ios", "android", "web", "all"], default="all",
                                       help="Platform to pull from (default: all)")
    artifacts_pull_parser.add_argument("--xcresult",
                                       help="Explicit .xcresult path or glob (overrides test.artifacts.ios.xcresult)")
    artifacts_pull_parser.add_argument("--serial",
                                       help="adb device serial (overrides test.artifacts.android.serial)")
    artifacts_pull_parser.add_argument("--out",
                                       help="Output dir (overrides test.artifacts.dir, default: tests/artifacts)")
    artifacts_pull_parser.add_argument("--config", help="Config file (default: jui.config.json)")
    artifacts_pull_parser.add_argument("--clean", action="store_true",
                                       help="Remove pulled artifact dirs from the Android device after pulling")
    artifacts_pull_parser.add_argument("--json", action="store_true",
                                       help="Print result as a single JSON object")

    artifacts_status_parser = artifacts_subparsers.add_parser(
        "status", help="Show resolved artifacts config and existing files")
    artifacts_status_parser.add_argument("--config", help="Config file (default: jui.config.json)")
    artifacts_status_parser.add_argument("--json", action="store_true",
                                         help="Print status as a single JSON object")

    # Pregrant command (iOS addMedia)
    pregrant_parser = subparsers.add_parser(
        "pregrant",
        help="Pre-grant simulator photo-library add access to the iOS UITest "
             "runner so addMedia never prompts (run before xcodebuild)")
    pregrant_parser.add_argument(
        "paths", nargs="*",
        help="Test files/dirs to scan for addMedia (default: tests/)")
    pregrant_parser.add_argument(
        "--bundle-id",
        help="UITest target bundle id ('.xctrunner' appended automatically; "
             "default: test.install.ios.uitestBundleId from config)")
    pregrant_parser.add_argument(
        "--udid", help="Simulator UDID (default: the single booted simulator)")
    pregrant_parser.add_argument("--config", help="Config file (default: jui.config.json)")
    pregrant_parser.add_argument(
        "--force", action="store_true",
        help="Grant even when no addMedia usage is found")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if args.command in ["validate", "v"]:
        return cmd_validate(args)
    elif args.command in ["report", "r"]:
        return cmd_report(args)
    elif args.command in ["mock", "m"]:
        if getattr(args, "mock_action", None) == "generate":
            return cmd_mock_generate(args)
        elif getattr(args, "mock_action", None) == "serve":
            return cmd_mock_serve(args)
        mock_parser.print_help()
        return 0
    elif args.command in ["artifacts", "a"]:
        if getattr(args, "artifacts_action", None) == "pull":
            return cmd_artifacts_pull(args)
        elif getattr(args, "artifacts_action", None) == "status":
            return cmd_artifacts_status(args)
        artifacts_parser.print_help()
        return 0
    elif args.command == "pregrant":
        return cmd_pregrant(args)
    elif args.command in ["generate", "g"]:
        # Check for subcommand
        if hasattr(args, 'generate_type') and args.generate_type:
            if args.generate_type in ["test", "t"]:
                # Check for test type subcommand
                if hasattr(args, 'test_type') and args.test_type:
                    if args.test_type == "screen":
                        return cmd_generate_test_screen(args)
                    elif args.test_type == "flow":
                        return cmd_generate_test_flow(args)
                gen_test_parser.print_help()
                return 0
            elif args.generate_type in ["description", "d", "desc"]:
                # Check for test type subcommand
                if hasattr(args, 'test_type') and args.test_type:
                    if args.test_type in ["screen", "flow"]:
                        return cmd_generate_description(args)
                gen_desc_parser.print_help()
                return 0
        else:
            generate_parser.print_help()
            return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
