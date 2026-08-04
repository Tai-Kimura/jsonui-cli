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
    report.add_argument(
        "--env",
        default=None,
        help=(
            "Render-environment key for the visual comparison — baselines are "
            "read from baselines/<env>/ (default: local). A baseline is a fact "
            "about one renderer; CI lanes pass their own key and never compare "
            "against developer-machine bakes."
        ),
    )

    gate = sub.add_parser(
        "gate",
        help="Render REPORT.md and fail on regressions — the CI gate, runnable locally",
    )
    gate.add_argument(
        "--platform",
        action="append",
        required=True,
        choices=list(_PLATFORMS),
        help=(
            "Platform whose results this gate judges (repeatable). Cross-platform "
            "mismatches are judged only when all three platforms are selected — "
            "with fewer, the unselected results are committed snapshots, not this run's."
        ),
    )
    gate.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory containing manifest.json (default: {_DEFAULT_OUT})",
    )
    gate.add_argument(
        "--results",
        default=None,
        help="Results directory (default: <dir>/results)",
    )
    gate.add_argument(
        "--out",
        default=None,
        help="Report output path (default: <dir>/REPORT.md)",
    )
    gate.add_argument(
        "--no-visual",
        action="store_true",
        help=(
            "Skip the screenshot-dependent checks (baseline comparison, attribute "
            "effect, artifact ratchets). For lanes that cannot compare renders — "
            "the per-push web lane runs on a different OS than the committed "
            "baselines were rendered on and does not install Pillow."
        ),
    )
    gate.add_argument(
        "--env",
        default=None,
        help=(
            "Render-environment key (default: local). Visual checks compare "
            "against baselines/<env>/ and use that env's ratchet ceilings; the "
            "attribute-effect ledger fails the gate only under env 'local' "
            "(asserted there) and is reported as a notice elsewhere."
        ),
    )
    gate.add_argument(
        "--parity",
        action="store_true",
        help=(
            "Also judge dynamic ≡ codegen: codegen-host screenshots "
            "(artifacts/<platform>-codegen) must match the dynamic baseline "
            "within its threshold, deviations must be recorded in "
            "codegen_parity.json, and recorded entries must still measure — "
            "unrecorded drift and stale entries fail."
        ),
    )
    gate.add_argument(
        "--cross-effect",
        action="store_true",
        dest="cross_effect",
        help=(
            "Also judge cross-platform activeness agreement: a fixture's "
            "control-diff verdict (active/inert) must agree across the selected "
            "platforms its attribute is declared for, and SSoT-enumerated values "
            "must not be inert everywhere. Findings must be recorded in "
            "cross_effect.json, and recorded entries must still measure — "
            "unrecorded findings and stale entries fail (env 'local'; a notice "
            "elsewhere). Needs ≥2 selected platforms and the visual checks."
        ),
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
    baseline_update.add_argument(
        "--env",
        default=None,
        help=(
            "Render-environment key to bake under (baselines/<env>/, default: "
            "local). Bake 'ci' baselines from CI-run artifacts, never from a "
            "local render — the manifest records the env and refuses to be "
            "compared under a different one."
        ),
    )
    baseline_update.add_argument(
        "--threshold",
        type=int,
        default=None,
        help=(
            "Comparison threshold stored in this manifest (default: the "
            "shared calibrated value). Per-(env, platform) recalibration — "
            "measure the renderer's repeat-run noise first and record the "
            "numbers in baselines/README.md."
        ),
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

    par = sub.add_parser(
        "parity",
        help="Compare codegen-host screenshots against the dynamic baseline (dynamic ≡ codegen)",
    )
    par.add_argument(
        "--platform",
        required=True,
        choices=list(_PLATFORMS),
        help="Platform whose codegen artifacts to measure",
    )
    par.add_argument(
        "--env",
        default=None,
        help="Render-environment key of the dynamic baseline to compare against (default: local)",
    )
    par.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    par.add_argument(
        "--codegen-artifacts",
        default=None,
        help="Codegen screenshots directory (default: <dir>/artifacts/<platform>-codegen)",
    )
    par.add_argument(
        "--update",
        action="store_true",
        help=(
            "Record the measured deviations into codegen_parity.json (reasons "
            "and notes of surviving entries are preserved; new entries get the "
            "unreviewed marker). Without --update, unrecorded deviations and "
            "stale entries exit non-zero — the same check `gate --parity` runs."
        ),
    )

    cross = sub.add_parser(
        "cross-effect",
        help=(
            "Compare attribute activeness (control-diff verdicts) across platforms "
            "— disagreement is semantic drift unless ledgered with a reason"
        ),
    )
    cross.add_argument(
        "--platform",
        action="append",
        choices=list(_PLATFORMS),
        help=(
            "Platform to include in the comparison (repeatable; default: all "
            "three). At least two are required — activeness agreement across "
            "one platform compares nothing."
        ),
    )
    cross.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    cross.add_argument(
        "--results",
        default=None,
        help="Results directory (default: <dir>/results)",
    )
    cross.add_argument(
        "--definitions",
        default=None,
        help=(
            "Path to attribute_definitions.json, for the uniformly-inert check "
            f"(default: {_DEFAULT_DEFINITIONS})"
        ),
    )
    cross.add_argument(
        "--semantics",
        default=None,
        help=(
            "Path to the attribute-semantics contract; adjudicated rulings are "
            "verified from it instead of the ledger "
            f"(default: {_REPO_ROOT / 'shared' / 'core' / 'attribute_semantics.json'})"
        ),
    )
    cross.add_argument(
        "--update",
        action="store_true",
        help=(
            "Record the measured findings into cross_effect.json (reasons and "
            "notes of entries whose fact still holds are preserved; new entries "
            "get the unreviewed marker; entries no longer supported are pruned). "
            "Without --update, unrecorded findings and stale entries exit "
            "non-zero — the same check `gate --cross-effect` runs."
        ),
    )

    inert = sub.add_parser(
        "inert-audit",
        help=(
            "Inventory the inert control-diff verdicts no ledger accounts for "
            "— the completeness audit behind the adjudication queue"
        ),
    )
    inert.add_argument(
        "--platform",
        action="append",
        choices=list(_PLATFORMS),
        help=(
            "Platform to audit (repeatable; default: all three). Attribution "
            "is per platform, but the queue reports every item's full "
            "cross-platform picture."
        ),
    )
    inert.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    inert.add_argument(
        "--results",
        default=None,
        help="Results directory (default: <dir>/results)",
    )
    inert.add_argument(
        "--definitions",
        default=None,
        help=(
            "Path to attribute_definitions.json, for the declared-value and "
            f"value-is-default triage (default: {_DEFAULT_DEFINITIONS})"
        ),
    )
    inert.add_argument(
        "--semantics",
        default=None,
        help=(
            "Path to the attribute-semantics contract; fixtures it declares an "
            "observable for are attributed to the contract "
            f"(default: {_REPO_ROOT / 'shared' / 'core' / 'attribute_semantics.json'})"
        ),
    )
    inert.add_argument(
        "--json",
        dest="json_out",
        default=None,
        help=(
            "Write the adjudication queue to this path as JSON. The file is a "
            "report, not a ledger — nothing reads it back."
        ),
    )
    inert.add_argument(
        "--untriaged-only",
        action="store_true",
        help="List only the items no mechanical triage family closes",
    )

    eff = sub.add_parser(
        "effect",
        help="Record/check which fixtures render differently from their control",
    )
    eff.add_argument(
        "--platform",
        required=True,
        choices=list(_PLATFORMS),
        help="Platform whose artifacts to measure",
    )
    eff.add_argument(
        "--dir",
        dest="conformance_dir",
        default=None,
        help=f"Conformance directory (default: {_DEFAULT_OUT})",
    )
    eff.add_argument(
        "--artifacts",
        default=None,
        help="Directory holding this platform's screenshots (default: <dir>/artifacts/<platform>)",
    )
    eff.add_argument(
        "--update",
        action="store_true",
        help=(
            "Record every fixture that currently differs from its control into "
            "control_diff.json. Existing entries are kept: an attribute that "
            "used to have an effect must not lose it because one run measured "
            "nothing."
        ),
    )


def cmd_conformance(args: argparse.Namespace) -> int:
    """Dispatch to the right ``conformance`` subcommand."""
    target = getattr(args, "conformance_target", None)
    if target == "generate":
        return _cmd_generate(args)
    if target == "report":
        return _cmd_report(args)
    if target == "gate":
        return _cmd_gate(args)
    if target == "compat-doc":
        return _cmd_compat_doc(args)
    if target == "baseline":
        return _cmd_baseline(args)
    if target == "coverage":
        return _cmd_coverage(args)
    if target == "effect":
        return _cmd_effect(args)
    if target == "parity":
        return _cmd_parity(args)
    if target == "cross-effect":
        return _cmd_cross_effect(args)
    if target == "inert-audit":
        return _cmd_inert_audit(args)
    print(
        "Usage: jui conformance <generate|report|gate|baseline|coverage|effect|"
        "parity|cross-effect|inert-audit> [options]"
    )
    return 1


def _cmd_cross_effect(args: argparse.Namespace) -> int:
    import hashlib
    import json

    from ..conformance import control_diff as control_diff_mod
    from ..conformance import cross_effect as ce
    from ..conformance.report import load_platform_results

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    results_dir = Path(args.results) if args.results else conformance_dir / "results"
    platforms = (
        list(dict.fromkeys(args.platform)) if args.platform else list(_PLATFORMS)
    )
    if len(platforms) < 2:
        print(
            "ERROR: cross-effect needs at least two platforms — activeness "
            "agreement across one compares nothing"
        )
        return 1

    manifest_path = conformance_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    loaded = {p.platform: p for p in load_platform_results(results_dir, manifest_hash)}
    diffs = {}
    for platform in platforms:
        pr = loaded.get(platform)
        if pr is None:
            print(f"note: no results for {platform} — its fixtures count as not compared")
            continue
        if pr.stale:
            print(
                f"note: {platform} results are stale vs the current manifest — "
                "activeness verdicts are within-run facts, but re-run the suite "
                "before trusting fixture-level conclusions"
            )
        diffs[platform] = control_diff_mod.compare(
            conformance_dir, platform, manifest, pr.results
        )
        if diffs[platform].error:
            print(f"note: {platform} comparison errored — {diffs[platform].error}")

    definitions_path = (
        Path(args.definitions) if args.definitions else _DEFAULT_DEFINITIONS
    )
    enum_values: dict = {}
    if definitions_path.is_file():
        enum_values = ce.enum_fixture_values(
            manifest, json.loads(definitions_path.read_text(encoding="utf-8"))
        )
    else:
        print(
            f"note: {definitions_path} not found — the uniformly-inert check "
            "did not participate"
        )

    semantics_path = (
        Path(args.semantics)
        if getattr(args, "semantics", None)
        else _REPO_ROOT / "shared" / "core" / ce.CONTRACT_NAME
    )
    contract = ce.load_contract(semantics_path)

    result = ce.measure(
        ce.scope_from_manifest(manifest),
        ce.verdicts_from_diffs(diffs),
        platforms,
        enum_values,
    )

    judged = len(result.consistent) + len(result.mismatched)
    print(
        f"cross-effect ({', '.join(platforms)}): {judged} fixture(s) compared on "
        f"all their in-scope platforms"
    )
    print(f"  consistent:          {len(result.consistent)}")
    print(f"  diverging:           {len(result.mismatched)}")
    print(f"  uniformly-inert:     {len(result.uniform_inert)} (declared enum values)")
    print(f"  not compared everywhere: {len(result.not_compared)}")
    print(f"  in scope on <2 platforms: {result.out_of_scope}")
    if result.mismatched:
        print()
        print("diverging fixtures (activeness disagrees):")
        for fid in sorted(result.mismatched)[:40]:
            verdicts = result.mismatched[fid]
            label = ", ".join(f"{p}: {verdicts[p]}" for p in sorted(verdicts))
            print(f"  {fid} — {label}")
        if len(result.mismatched) > 40:
            print(f"  … {len(result.mismatched) - 40} more")
    if result.uniform_inert:
        print()
        print("declared values inert on every in-scope platform:")
        for fid in sorted(result.uniform_inert)[:40]:
            print(f"  {fid} — value {result.uniform_inert[fid]!r}")
        if len(result.uniform_inert) > 40:
            print(f"  … {len(result.uniform_inert) - 40} more")

    path = ce.ledger_path(conformance_dir)
    ledger = ce.load_ledger(path)

    if args.update:
        merged = ce.update_ledger(ledger, result, contract)
        path.write_text(ce.render_ledger(merged), encoding="utf-8")
        unreviewed = sum(
            1 for e in merged.values() if e.get("reason") == ce.UNREVIEWED
        )
        print()
        print(
            f"  ledger written to {path} ({len(merged)} entr(y/ies), "
            f"{unreviewed} unreviewed)"
        )
        return 0

    verdict = ce.check(result, ledger, contract)
    if verdict.contract_violations:
        print()
        print(
            f"{len(verdict.contract_violations)} semantics-contract violation(s) "
            f"({semantics_path.name}) — fix the platform or change the contract, "
            "a ledger reason cannot excuse these:"
        )
        for line in verdict.contract_violations[:40]:
            print(f"  {line}")
    if verdict.contract_unverified:
        print()
        print(
            f"note: {len(verdict.contract_unverified)} contract expectation(s) "
            "could not be verified this run (fixture not compared everywhere)"
        )
    if verdict.unrecorded:
        print()
        print(
            f"{len(verdict.unrecorded)} finding(s) not recorded in {path.name} — "
            "fix the platform or record + justify with `jui conformance "
            "cross-effect --update`:"
        )
        for line in verdict.unrecorded[:40]:
            print(f"  {line}")
        if len(verdict.unrecorded) > 40:
            print(f"  … {len(verdict.unrecorded) - 40} more")
    if verdict.stale:
        print()
        print(
            f"{len(verdict.stale)} ledger entr(y/ies) the measurement no longer "
            "supports (prune with `jui conformance cross-effect --update`):"
        )
        for fid in verdict.stale[:40]:
            print(f"  {fid}")
    if verdict.unverified:
        print()
        print(
            f"note: {len(verdict.unverified)} ledger entr(y/ies) could not be "
            "verified this run (fixture not compared everywhere)"
        )
    if verdict.ok:
        print()
        print(
            f"cross-effect OK: no unrecorded findings "
            f"({verdict.accepted} accepted on ledger, "
            f"{verdict.contract_verified} contract expectation(s) verified)"
        )
        return 0
    return 1


def _cmd_inert_audit(args: argparse.Namespace) -> int:
    import hashlib
    import json

    from ..conformance import control_diff as control_diff_mod
    from ..conformance import cross_effect as ce
    from ..conformance import inert_audit as ia
    from ..conformance.report import load_platform_results

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    results_dir = Path(args.results) if args.results else conformance_dir / "results"
    platforms = (
        list(dict.fromkeys(args.platform)) if args.platform else list(_PLATFORMS)
    )

    manifest_path = conformance_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    loaded = {p.platform: p for p in load_platform_results(results_dir, manifest_hash)}
    diffs = {}
    for platform in platforms:
        pr = loaded.get(platform)
        if pr is None:
            print(
                f"note: no results for {platform} — its fixtures have no verdict "
                "to attribute"
            )
            continue
        if pr.stale:
            print(
                f"note: {platform} results are stale vs the current manifest — "
                "re-run the suite before trusting fixture-level conclusions"
            )
        diffs[platform] = control_diff_mod.compare(
            conformance_dir, platform, manifest, pr.results
        )
        if diffs[platform].error:
            print(f"note: {platform} comparison errored — {diffs[platform].error}")

    definitions_path = (
        Path(args.definitions) if args.definitions else _DEFAULT_DEFINITIONS
    )
    definitions = {}
    if definitions_path.is_file():
        definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
    else:
        print(
            f"note: {definitions_path} not found — declared-value classification "
            "and the value-is-default triage did not participate"
        )

    semantics_path = (
        Path(args.semantics)
        if getattr(args, "semantics", None)
        else _REPO_ROOT / "shared" / "core" / ce.CONTRACT_NAME
    )
    coverage_path = conformance_dir / "coverage.json"
    coverage_doc = (
        json.loads(coverage_path.read_text(encoding="utf-8"))
        if coverage_path.is_file()
        else {}
    )

    result = ia.audit(
        manifest,
        ce.verdicts_from_diffs(diffs),
        platforms,
        control_diff_ledger=control_diff_mod.load_ledger_all(
            control_diff_mod.ledger_path(conformance_dir)
        ),
        cross_effect_ledger=ce.load_ledger(ce.ledger_path(conformance_dir)),
        contract=ce.load_contract(semantics_path),
        coverage=ia.coverage_gaps(coverage_doc),
        enum_values=ce.enum_fixture_values(manifest, definitions),
    )
    from ..conformance import rules as rules_mod

    ia.triage(
        result,
        defaults=ia.attribute_defaults(definitions),
        control_identical=ia.control_identical_fixtures(conformance_dir, manifest),
        manifest=manifest,
        fallback_value=rules_mod.DEFAULT_STRING,
    )

    print(f"inert-audit ({', '.join(platforms)}):")
    for platform in platforms:
        attributed = result.attributed.get(platform, {})
        claimed = ", ".join(
            f"{channel} {attributed[channel]}"
            for channel in ia.CHANNELS
            if attributed.get(channel)
        )
        print(
            f"  {platform:<8} inert {result.measured.get(platform, 0):>4}  "
            f"attributed {sum(attributed.values()):>4}"
            + (f" ({claimed})" if claimed else "")
            + f"  unadjudicated {result.unattributed.get(platform, 0):>4}"
        )
    print()
    print(
        f"  queue: {len(result.items)} fixture(s), "
        f"{len(result.untriaged)} untriaged after mechanical triage"
    )

    by_kind: dict = {}
    by_family: dict = {}
    for item in result.items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        by_family[item.family] = by_family.get(item.family, 0) + 1
    for label, counts in (("kind", by_kind), ("family", by_family)):
        if not counts:
            continue
        print(f"  by {label}:")
        for key in sorted(counts, key=lambda k: (-counts[k], k)):
            print(f"    {key:<32} {counts[key]}")

    listed = result.untriaged if args.untriaged_only else result.items
    if listed:
        print()
        print("adjudication queue:")
        for item in listed[:200]:
            verdicts = ", ".join(
                f"{p}: {item.verdicts.get(p) or '—'}" for p in item.scope
            )
            print(f"  {item.fixture} [{item.kind}] {verdicts}")
            if item.family != ia.FAMILY_UNTRIAGED:
                print(f"      triage: {item.family} — {item.evidence}")
        if len(listed) > 200:
            print(f"  … {len(listed) - 200} more")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(ia.render_queue(result), encoding="utf-8")
        print()
        print(f"  queue written to {out}")

    # Reporting only: the completeness ratchet is plan 34 Phase 3 and cannot
    # be armed before the queue is empty.
    return 0


def _cmd_parity(args: argparse.Namespace) -> int:
    from ..conformance import parity as par
    from ..conformance.baseline import DEFAULT_ENV

    conformance_dir = Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    env = getattr(args, "env", None) or DEFAULT_ENV
    codegen_dir = Path(args.codegen_artifacts) if args.codegen_artifacts else None

    result = par.measure(conformance_dir, args.platform, env=env, codegen_dir=codegen_dir)
    if result.error:
        print(f"ERROR: nothing was measured: {result.error}")
        return 1

    compared = len(result.matched) + len(result.mismatched)
    print(
        f"codegen parity ({args.platform}, env {env}, threshold {result.threshold}): "
        f"{compared} screenshot(s) compared against the dynamic baseline"
    )
    print(f"  dynamic ≡ codegen: {len(result.matched)}")
    print(f"  mismatched:        {len(result.mismatched)}")
    print(f"  missing (no codegen render): {len(result.missing)}")
    if result.extra:
        print(f"  extra codegen shots without a baseline hash: {len(result.extra)}")

    path = par.ledger_path(conformance_dir)
    ledger = par.load_ledger(path)

    if args.update:
        merged = par.update_ledger(ledger, result)
        path.write_text(par.render_ledger(merged), encoding="utf-8")
        platform_entries = sum(1 for k in merged if k[1] == args.platform)
        unreviewed = sum(
            1
            for k, e in merged.items()
            if k[1] == args.platform and e.get("reason") == par.UNREVIEWED
        )
        print(
            f"  ledger written to {path} ({platform_entries} entr(y/ies) for "
            f"{args.platform}, {unreviewed} unreviewed)"
        )
        return 0

    verdict = par.check(result, ledger)
    if verdict.unrecorded:
        print()
        print(
            f"{len(verdict.unrecorded)} deviation(s) not recorded in {path.name} — "
            "fix the codegen or record + justify with `jui conformance parity --update`:"
        )
        for line in verdict.unrecorded[:30]:
            print(f"  {line}")
        if len(verdict.unrecorded) > 30:
            print(f"  … {len(verdict.unrecorded) - 30} more")
    if verdict.stale:
        print()
        print(
            f"{len(verdict.stale)} ledger entr(y/ies) the measurement no longer supports "
            "(codegen now matches — prune with `jui conformance parity --update`):"
        )
        for name in verdict.stale[:30]:
            print(f"  {name}")
    if verdict.ok:
        print()
        print(
            f"parity OK: no unrecorded drift ({verdict.accepted} accepted deviation(s) on ledger)"
        )
        return 0
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
        f"interactive: {summary.interactive_count}, control: {summary.control_count})"
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
    from ..conformance.baseline import DEFAULT_ENV, BaselineError, update_baseline

    action = getattr(args, "baseline_action", None)
    if action != "update":
        print("Usage: jui conformance baseline update --platform <ios|android|web> [options]")
        return 1

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    artifacts_dir = Path(args.artifacts) if args.artifacts else None
    env = getattr(args, "env", None) or DEFAULT_ENV
    threshold = getattr(args, "threshold", None)

    try:
        summary = update_baseline(
            conformance_dir,
            args.platform,
            artifacts_dir=artifacts_dir,
            env=env,
            threshold=threshold,
        )
    except BaselineError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"baseline written to {summary.out_path}")
    print(
        f"  platform: {summary.platform}, env: {summary.env}, "
        f"screenshots hashed: {summary.hashed}"
    )
    return 0


def _cmd_effect(args: argparse.Namespace) -> int:
    """Measure fixture-vs-control renders, and record or check the ledger."""
    import json as _json

    from ..conformance import control_diff as cd

    conformance_dir = Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    manifest_path = conformance_dir / "manifest.json"
    results_path = conformance_dir / "results" / f"{args.platform}.results.json"

    for path, hint in (
        (manifest_path, "run `jui conformance generate` first"),
        (results_path, f"run the {args.platform} conformance host first"),
    ):
        if not path.is_file():
            print(f"ERROR: not found: {path} — {hint}")
            return 1

    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = _json.loads(results_path.read_text(encoding="utf-8"))
    results = {
        entry["id"]: entry
        for entry in raw.get("fixtures", raw.get("results", [])) or []
        if isinstance(entry, dict) and entry.get("id")
    }

    artifacts = Path(args.artifacts) if args.artifacts else None
    result = cd.compare(
        conformance_dir, args.platform, manifest, results, artifacts_dir=artifacts
    )
    if result.error:
        print(f"ERROR: nothing was compared: {result.error}")
        return 1

    compared = len(result.active) + len(result.inert)
    print(f"attribute effect ({args.platform}): {compared} fixture(s) compared to their control")
    print(f"  differ from control (attribute took effect): {len(result.active)}")
    print(f"  identical to control (no effect measured):   {len(result.inert)}")
    if result.no_control:
        print(f"  no usable control screenshot: {len(result.no_control)}")

    path = cd.ledger_path(conformance_dir)
    if args.update:
        # Union within this platform, and other platforms are left alone: a run
        # on a device where one fixture failed to screenshot would otherwise
        # quietly drop that attribute's guarantee, and recording web's results
        # against iOS would fail iOS for a gap it has not been measured for.
        ledger = cd.load_ledger_all(path)
        before = sum(1 for f, ps in ledger.items() if args.platform in ps)
        for fid in result.active:
            ledger.setdefault(fid, set()).add(args.platform)
        path.write_text(cd.render_ledger(ledger), encoding="utf-8")
        after = sum(1 for f, ps in ledger.items() if args.platform in ps)
        print(
            f"  ledger written to {path} "
            f"({after} fixture(s) for {args.platform}, +{after - before} new)"
        )
        return 0

    if result.regressions:
        print()
        print(
            f"{len(result.regressions)} fixture(s) recorded as expected-to-differ now "
            "render identically to their control — the attribute stopped taking effect:"
        )
        for fid in result.regressions[:30]:
            print(f"  {fid}")
        if len(result.regressions) > 30:
            print(f"  … {len(result.regressions) - 30} more")
        return 1

    if result.unmeasured:
        print()
        print(
            f"{len(result.unmeasured)} recorded fixture(s) produced no screenshot, so "
            "their effect was not verified (not a pass):"
        )
        for fid in result.unmeasured[:30]:
            print(f"  {fid}")
        return 1

    print()
    print("No regression: every recorded attribute still changes what is rendered.")
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
    from ..conformance.baseline import DEFAULT_ENV
    from ..conformance.report import ReportError, generate_report

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    results_dir = Path(args.results) if args.results else None
    out_path = Path(args.out) if args.out else None
    env = getattr(args, "env", None) or DEFAULT_ENV

    try:
        summary = generate_report(
            conformance_dir, results_dir=results_dir, out_path=out_path, env=env
        )
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


def _cmd_gate(args: argparse.Namespace) -> int:
    import hashlib
    import os

    from ..conformance.baseline import DEFAULT_ENV
    from ..conformance.gate import evaluate
    from ..conformance.report import ReportError, _status_of, load_platform_results

    conformance_dir = (
        Path(args.conformance_dir) if args.conformance_dir else _DEFAULT_OUT
    )
    results_dir = Path(args.results) if args.results else conformance_dir / "results"
    out_path = Path(args.out) if args.out else None
    selected = list(dict.fromkeys(args.platform))
    env = getattr(args, "env", None) or DEFAULT_ENV

    try:
        outcome = evaluate(
            conformance_dir,
            selected,
            results_dir=results_dir,
            out_path=out_path,
            visual=not args.no_visual,
            env=env,
            parity=bool(getattr(args, "parity", False)),
            cross_effect=bool(getattr(args, "cross_effect", False)),
        )
    except ReportError as e:
        print(f"ERROR: {e}")
        return 1

    summary = outcome.summary
    print(f"report written to {summary.out_path}")
    for platform in selected:
        tally = summary.status_tallies.get(platform)
        if tally is not None:
            print(f"{platform}: {tally}")

    # List the failing fixtures so a red gate is diagnosable from the log
    # alone (same 30-entry cap the workflow heredocs used).
    has_bad_results = any(
        tally.get("fail", 0) + tally.get("error", 0)
        for platform in selected
        if (tally := summary.status_tallies.get(platform)) is not None
    )
    if has_bad_results:
        manifest_hash = hashlib.sha256(
            (conformance_dir / "manifest.json").read_bytes()
        ).hexdigest()
        loaded = {p.platform: p for p in load_platform_results(results_dir, manifest_hash)}
        for platform in selected:
            p = loaded.get(platform)
            if p is None:
                continue
            bad = [
                (fixture_id, entry)
                for fixture_id, entry in p.results.items()
                if _status_of(p, fixture_id) in ("fail", "error")
            ]
            for fixture_id, entry in bad[:30]:
                status = _status_of(p, fixture_id)
                print(f"  {status:5} {fixture_id} — {entry.get('detail', '')}")
            if len(bad) > 30:
                print(f"  … {len(bad) - 30} more")

    on_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for notice in outcome.notices:
        print(f"::notice::{notice}" if on_actions else f"note: {notice}")
    if outcome.problems:
        for problem in outcome.problems:
            print(f"::error::{problem}" if on_actions else f"GATE FAIL: {problem}")
        return 1

    checks = "0 fail / 0 error"
    if set(_PLATFORMS) <= set(selected):
        checks = "0 mismatch / " + checks
    if not args.no_visual:
        checks += f" / visual + ratchets OK (env {env})"
    if getattr(args, "cross_effect", False):
        checks += " / cross-effect OK"
    print(f"conformance gate: OK ({', '.join(selected)} — {checks})")
    return 0
