"""`jui conformance` — cross-platform conformance harness commands.

Two subcommands:

- ``jui conformance generate`` — build fixtures/ + manifest.json from
  ``shared/core/attribute_definitions.json``. Deterministic: running it twice
  produces zero diff.
- ``jui conformance report`` — merge ``results/*.results.json`` written by the
  per-platform runners (plans 02/03/04) into ``REPORT.md``. The results file
  contract is documented in ``conformance/RESULTS_SCHEMA.md``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

#: jsonui-cli repo root (…/jui_tools/jui_cli/commands/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DEFINITIONS = _REPO_ROOT / "shared" / "core" / "attribute_definitions.json"
_DEFAULT_OUT = _REPO_ROOT / "conformance"
_PLATFORMS = ("ios", "android", "web")


def register_conformance_command(subparsers: argparse._SubParsersAction) -> None:
    """Register ``jui conformance`` + its two subcommands."""
    parser = subparsers.add_parser(
        "conformance",
        help="Generate cross-platform conformance fixtures / compatibility report",
    )
    sub = parser.add_subparsers(dest="conformance_target")

    generate = sub.add_parser(
        "generate",
        help="Generate fixtures/ + manifest.json from attribute_definitions.json",
    )
    generate.add_argument(
        "--definitions",
        default=None,
        help=f"Path to attribute_definitions.json (default: {_DEFAULT_DEFINITIONS})",
    )
    generate.add_argument(
        "--out",
        default=None,
        help=f"Output directory (default: {_DEFAULT_OUT})",
    )

    report = sub.add_parser(
        "report",
        help="Merge results/*.results.json into REPORT.md (compat matrix)",
    )
    report.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory containing manifest.json (default: {_DEFAULT_OUT})",
    )
    report.add_argument(
        "--results",
        default=None,
        help="Results directory (default: <dir>/results)",
    )
    report.add_argument(
        "--out",
        default=None,
        help="Report output path (default: <dir>/REPORT.md)",
    )

    compat = sub.add_parser(
        "compat-doc",
        help="Generate the @generated attribute-compatibility markdown",
    )
    compat.add_argument(
        "--platform",
        required=True,
        choices=["ios", "android", "web"],
        help="Platform whose conformance results feed the coverage column",
    )
    compat.add_argument(
        "--definitions",
        default=None,
        help=f"Path to attribute_definitions.json (default: {_DEFAULT_DEFINITIONS})",
    )
    compat.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    compat.add_argument(
        "-o",
        "--out",
        required=True,
        help="Output markdown path (e.g. Docs/attribute_compatibility.md)",
    )

    baseline = sub.add_parser(
        "baseline",
        help="Screenshot baseline management (perceptual-hash manifests)",
    )
    baseline_sub = baseline.add_subparsers(dest="baseline_action")
    baseline_update = baseline_sub.add_parser(
        "update",
        help="Hash artifacts/<platform>/*.png into baselines/<platform>.hashes.json",
    )
    baseline_update.add_argument(
        "--platform",
        required=True,
        choices=["ios", "android", "web"],
        help="Platform whose artifacts to baseline",
    )
    baseline_update.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    baseline_update.add_argument(
        "--artifacts",
        default=None,
        help="Artifacts directory (default: <dir>/artifacts/<platform>)",
    )

    cov = sub.add_parser(
        "coverage",
        help="Check declared attributes against what each platform's converters read",
    )
    cov.add_argument(
        "--platform",
        action="append",
        choices=list(_PLATFORMS),
        help="Limit the check to a platform (repeatable; default: all)",
    )
    cov.add_argument(
        "--definitions",
        default=None,
        help=f"Path to attribute_definitions.json (default: {_DEFAULT_DEFINITIONS})",
    )
    cov.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory holding coverage.json (default: {_DEFAULT_OUT})",
    )
    cov.add_argument(
        "--repo-root",
        default=None,
        help=f"Repo root holding the converter sources (default: {_REPO_ROOT})",
    )
    cov.add_argument(
        "--update",
        action="store_true",
        help="Rewrite coverage.json from the current gaps (reasons are preserved)",
    )


def cmd_conformance(args: argparse.Namespace) -> int:
    """Dispatch to the right ``conformance`` subcommand."""
    target = getattr(args, "conformance_target", None)
    if target == "generate":
        return _cmd_generate(args)
    if target == "report":
        return _cmd_report(args)
    if target == "compat-doc":
        return _cmd_compat_doc(args)
    if target == "baseline":
        return _cmd_baseline(args)
    if target == "coverage":
        return _cmd_coverage(args)
    print("Usage: jui conformance <generate|report|baseline|coverage> [options]")
    return 1


def _cmd_generate(args: argparse.Namespace) -> int:
    from ..conformance.fixture_generator import generate_conformance

    definitions = Path(args.definitions) if args.definitions else _DEFAULT_DEFINITIONS
    out_dir = Path(args.out) if args.out else _DEFAULT_OUT

    if not definitions.is_file():
        print(f"ERROR: attribute definitions not found: {definitions}")
        return 1

    summary = generate_conformance(definitions, out_dir)

    print(f"conformance fixtures written to {summary.out_dir}")
    print(
        f"  fixtures: {summary.fixture_count} "
        f"(assertable: {summary.assertable_count}, visual: {summary.visual_count}, "
        f"interactive: {summary.interactive_count})"
    )
    print(f"  skipped attributes (with reason): {summary.skipped_count}")
    if summary.promoted:
        promoted = ", ".join(f"{k}: {v}" for k, v in sorted(summary.promoted.items()))
        print(f"  promoted out of skip reasons: {promoted}")
    print(f"  files written: {summary.files_written} (incl. manifest.json)")
    return 0


def _cmd_compat_doc(args: argparse.Namespace) -> int:
    from ..conformance.compat_doc import generate_compat_doc

    definitions = Path(args.definitions) if args.definitions else _DEFAULT_DEFINITIONS
    conformance_dir = Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    out_path = Path(args.out)

    if not definitions.is_file():
        print(f"ERROR: attribute definitions not found: {definitions}")
        return 1

    summary = generate_compat_doc(definitions, conformance_dir, args.platform, out_path)
    for warning in summary.warnings:
        print(f"WARNING: {warning}")
    print(
        f"compat doc written to {summary.out_path} "
        f"({summary.components} components, {summary.attributes} attributes, "
        f"{summary.covered} with {args.platform} conformance coverage)"
    )
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    from ..conformance.baseline import BaselineError, update_baseline

    action = getattr(args, "baseline_action", None)
    if action != "update":
        print("Usage: jui conformance baseline update --platform <ios|android|web> [options]")
        return 1

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    artifacts_dir = Path(args.artifacts) if args.artifacts else None

    try:
        summary = update_baseline(conformance_dir, args.platform, artifacts_dir=artifacts_dir)
    except BaselineError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"baseline written to {summary.out_path}")
    print(f"  platform: {summary.platform}, screenshots hashed: {summary.hashed}")
    return 0


def _cmd_coverage(args: argparse.Namespace) -> int:
    import json

    from ..conformance import coverage as cov

    definitions_path = Path(args.definitions) if args.definitions else _DEFAULT_DEFINITIONS
    conformance_dir = Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    repo_root = Path(args.repo_root) if args.repo_root else _REPO_ROOT
    platforms = tuple(args.platform) if args.platform else cov.PLATFORMS

    if not definitions_path.is_file():
        print(f"ERROR: attribute definitions not found: {definitions_path}")
        return 1
    definitions = json.loads(definitions_path.read_text(encoding="utf-8"))

    result = cov.check(definitions, repo_root, conformance_dir, platforms=platforms)
    ledger_path = cov.coverage_path(conformance_dir)

    if args.update:
        existing = cov.load_ledger(ledger_path)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            cov.render_ledger(result.gaps, existing=existing, definitions=definitions),
            encoding="utf-8",
        )
        print(f"coverage ledger written to {ledger_path}")
        print(f"  {len(result.gaps)} gap(s) over {result.checked} declared attribute/platform pairs")
        return 0

    print(f"attribute coverage: {result.checked} declared attribute/platform pairs checked")
    print(f"  recorded gaps: {len(result.gaps) - len(result.unrecorded)}")
    for reason, count in sorted(result.by_reason.items()):
        print(f"    {reason}: {count}")

    if result.unrecorded:
        print(f"\n{len(result.unrecorded)} declared attribute(s) no converter reads:")
        for gap in result.unrecorded:
            print(f"  {gap}")
        print(
            "\nImplement it, narrow platform/mode in attribute_definitions.json, or "
            f"record it with `jui conformance coverage --update` (then set a reason in "
            f"{ledger_path.name})."
        )

    if result.stale:
        print(f"\n{len(result.stale)} stale ledger entr(y/ies) — the gap is closed or the")
        print("attribute is gone; drop them with `jui conformance coverage --update`:")
        for entry in result.stale:
            print(f"  {entry}")

    if result.ok:
        print("\nNo unrecorded gaps.")
        return 0
    return 1


def _cmd_report(args: argparse.Namespace) -> int:
    from ..conformance.report import ReportError, generate_report

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    results_dir = Path(args.results) if args.results else None
    out_path = Path(args.out) if args.out else None

    try:
        summary = generate_report(conformance_dir, results_dir=results_dir, out_path=out_path)
    except ReportError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"report written to {summary.out_path}")
    print(f"  platforms: {', '.join(summary.platforms) if summary.platforms else '(none)'}")
    print(f"  cross-platform mismatches: {summary.mismatch_count}")
    for platform, count in summary.visual_regressions.items():
        no_baseline = summary.no_baseline.get(platform, 0)
        print(
            f"  {platform}: visual regressions: {count}"
            + (f", screenshots without baseline: {no_baseline}" if no_baseline else "")
        )
    if summary.stale_platforms:
        print(f"  STALE results: {', '.join(summary.stale_platforms)}")
    for platform, ids in summary.unknown_ids.items():
        print(f"  WARNING: {platform} has {len(ids)} fixture id(s) not in manifest")
    return 0
