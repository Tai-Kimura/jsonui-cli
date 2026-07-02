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


def cmd_conformance(args: argparse.Namespace) -> int:
    """Dispatch to the right ``conformance`` subcommand."""
    target = getattr(args, "conformance_target", None)
    if target == "generate":
        return _cmd_generate(args)
    if target == "report":
        return _cmd_report(args)
    print("Usage: jui conformance <generate|report> [options]")
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
        f"(assertable: {summary.assertable_count}, visual: {summary.visual_count})"
    )
    print(f"  skipped attributes (with reason): {summary.skipped_count}")
    print(f"  files written: {summary.files_written} (incl. manifest.json)")
    return 0


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
    if summary.stale_platforms:
        print(f"  STALE results: {', '.join(summary.stale_platforms)}")
    for platform, ids in summary.unknown_ids.items():
        print(f"  WARNING: {platform} has {len(ids)} fixture id(s) not in manifest")
    return 0
