"""Pass/fail judgment for conformance runs (``jui conformance gate``).

This is the logic that used to live twice as a Python heredoc — once in
``ci.yml`` (web fail/error only) and once in ``conformance-mobile.yml``
(the full 3-platform judgment). Housing it here makes the gate runnable
locally, unit-testable, and impossible to drift between the two workflows:
both now call the same command with different arguments.

The gate renders REPORT.md (via :func:`generate_report`) and then judges
**only the platforms selected with ``--platform``**. That scoping matters:
the per-push web lane runs against committed iOS/Android results whose
screenshots are not on the runner — judging those platforms there would
fail them for artifacts that were never supposed to exist.

Checks, per selected platform:

- results file present / not stale / no fixture ids outside the manifest
- zero ``fail`` / ``error`` results
- with ``visual=True`` (the default): screenshots actually compared
  (a comparison that could not run is not a pass), zero visual regressions
  vs the committed baseline, zero attributes gone inert vs their control,
  and the ``missing_artifact`` / ``no_baseline`` ratchets below
- cross-platform mismatches, only when all three platforms are selected
  (fewer selected platforms means the other results are not from this run)
- with ``--cross-effect``: activeness agreement across the selected
  platforms (see :mod:`.cross_effect`) — unrecorded findings and stale
  ``cross_effect.json`` entries fail under env ``local``, notice elsewhere

Ratchets (``conformance/gate_ratchet.json``): ``missing_artifact`` counts
baseline entries whose fixture produced no screenshot this run — the way a
fixture silently exits visual coverage. The committed ceilings are the
as-of-introduction reality; a count above its ceiling fails, a count below
prints a reminder to tighten the ceiling. Lowering is routine, raising is a
coverage regression that needs justification in the file itself.

Render environments (``--env``): baselines live under ``baselines/<env>/``
and every visual fact is relative to one environment's renderer. Ratchet
ceilings nest by env for the same reason (a flat per-platform table is read
as the ``local`` env). The attribute-effect ledger (control_diff.json) is
asserted from local renders; under any other env an inert regression is
reported as a notice, not a failure — the 2026-08-01 CI run showed 4 iOS
entries (SelectBox/selectedValue, Switch statics) rendering identical to
their control on the CI simulator while holding locally, i.e. the assertion
itself is environment-scoped. Measurement still runs everywhere so the
report keeps the visibility.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .baseline import DEFAULT_ENV
from . import cross_effect as cross_effect_mod
from .report import ReportSummary, generate_report

RATCHET_FILENAME = "gate_ratchet.json"

#: Metrics gate_ratchet.json may set per-platform ceilings for.
RATCHET_METRICS = ("missing_artifact", "no_baseline")

_ALL_PLATFORMS = frozenset({"android", "ios", "web"})


@dataclass
class GateOutcome:
    """What the gate decided, and why."""

    problems: list[str] = field(default_factory=list)  # each one fails the gate
    notices: list[str] = field(default_factory=list)  # informational only
    summary: ReportSummary | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def load_ratchet(conformance_dir: Path) -> dict[str, dict[str, int]]:
    """Read ratchet ceilings; a missing file means every ceiling is 0.

    Returned as read (flat per-platform, or nested per-env) — resolution to
    one env's per-platform table happens in :func:`ratchet_for_env`, so both
    the file and direct ``judge(ratchet=...)`` callers may use either shape.
    """
    path = Path(conformance_dir) / RATCHET_FILENAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    ceilings: dict[str, dict] = {}
    for metric in RATCHET_METRICS:
        values = data.get(metric)
        if isinstance(values, dict):
            ceilings[metric] = values
    return ceilings


def ratchet_for_env(ratchet: dict, env: str) -> dict[str, dict[str, int]]:
    """Resolve a ratchet table to ``{metric: {platform: ceiling}}`` for *env*.

    Two accepted shapes per metric:

    - nested by env: ``{"local": {"android": 12}, "ci": {"android": 0}}``
    - flat per platform: ``{"android": 12}`` — the pre-env shape, read as
      the ``local`` env (that is what every flat ceiling was measured on).

    An env with no entry means every ceiling is 0 — a fresh environment
    starts strict and earns slack only by committing measured reality.
    """
    resolved: dict[str, dict[str, int]] = {}
    for metric in RATCHET_METRICS:
        values = ratchet.get(metric)
        if not isinstance(values, dict):
            continue
        nested = any(isinstance(v, dict) for v in values.values())
        table = values.get(env, {}) if nested else (values if env == DEFAULT_ENV else {})
        if isinstance(table, dict):
            resolved[metric] = {
                platform: int(ceiling)
                for platform, ceiling in table.items()
                if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool)
            }
    return resolved


def evaluate(
    conformance_dir: Path,
    platforms: Sequence[str],
    *,
    results_dir: Path | None = None,
    out_path: Path | None = None,
    visual: bool = True,
    ratchet: dict[str, dict[str, int]] | None = None,
    env: str = DEFAULT_ENV,
    parity: bool = False,
    cross_effect: bool = False,
    inert_complete: bool = False,
    definitions_path: Path | None = None,
    semantics_path: Path | None = None,
) -> GateOutcome:
    """Render REPORT.md and judge *platforms*. Raises ReportError on bad inputs."""
    conformance_dir = Path(conformance_dir)
    summary = generate_report(
        conformance_dir, results_dir=results_dir, out_path=out_path, env=env
    )
    if ratchet is None:
        ratchet = load_ratchet(conformance_dir)
    outcome = judge(summary, platforms, visual=visual, ratchet=ratchet, env=env)

    if cross_effect:
        if not visual:
            outcome.problems.append(
                "--cross-effect needs the visual checks: activeness verdicts come "
                "from the fixture-vs-control comparison, which --no-visual skips"
            )
        else:
            ledger = cross_effect_mod.load_ledger(
                cross_effect_mod.ledger_path(conformance_dir)
            )
            contract = cross_effect_mod.load_contract(
                cross_effect_mod.contract_path(conformance_dir)
            )
            problems, notices = judge_cross_effect(
                summary, platforms, ledger, contract=contract, env=env
            )
            outcome.problems.extend(problems)
            outcome.notices.extend(notices)

    if inert_complete:
        if not visual:
            outcome.problems.append(
                "--inert-complete needs the visual checks: an inert verdict IS "
                "the fixture-vs-control comparison, which --no-visual skips"
            )
        else:
            problems, notices = judge_inert_complete(
                conformance_dir,
                platforms,
                results_dir=results_dir,
                definitions_path=definitions_path,
                semantics_path=semantics_path,
                env=env,
            )
            outcome.problems.extend(problems)
            outcome.notices.extend(notices)

    if parity and visual:
        # dynamic ≡ codegen, judged per selected platform against the same
        # env's dynamic baseline. Requested explicitly (--parity) — a missing
        # codegen artifacts dir is then a failure, not a silent skip: the
        # lane that asks for parity must actually have run the codegen host.
        from . import parity as parity_mod

        ledger = parity_mod.load_ledger(parity_mod.ledger_path(conformance_dir))
        for p in list(dict.fromkeys(platforms)):
            if p not in parity_mod.PARITY_PLATFORMS:
                continue  # web's host already renders through codegen
            result = parity_mod.measure(conformance_dir, p, env=env)
            verdict = parity_mod.check(result, ledger)
            if verdict.error:
                outcome.problems.append(f"{p}: parity not measured — {verdict.error}")
                continue
            if verdict.unrecorded:
                shown = ", ".join(verdict.unrecorded[:5]) + (
                    " …" if len(verdict.unrecorded) > 5 else ""
                )
                outcome.problems.append(
                    f"{p}: {len(verdict.unrecorded)} codegen-parity deviation(s) not in "
                    f"{parity_mod.LEDGER_NAME} — dynamic and generated code no longer "
                    f"draw the same thing: {shown}"
                )
            if verdict.stale:
                shown = ", ".join(verdict.stale[:5]) + (
                    " …" if len(verdict.stale) > 5 else ""
                )
                outcome.problems.append(
                    f"{p}: {len(verdict.stale)} stale {parity_mod.LEDGER_NAME} entr(y/ies) — "
                    f"codegen now matches; prune with `jui conformance parity --update "
                    f"--platform {p}`: {shown}"
                )
            if verdict.ok:
                outcome.notices.append(
                    f"{p}: codegen parity OK — {len(result.matched)} matched, "
                    f"{verdict.accepted} accepted deviation(s) on ledger"
                )
    return outcome


def judge(
    summary: ReportSummary,
    platforms: Sequence[str],
    *,
    visual: bool = True,
    ratchet: dict[str, dict[str, int]] | None = None,
    env: str = DEFAULT_ENV,
) -> GateOutcome:
    """The pure judgment: summary in, problems/notices out. No filesystem."""
    ratchet = ratchet_for_env(ratchet or {}, env)
    selected = list(dict.fromkeys(platforms))
    outcome = GateOutcome(summary=summary)
    problems, notices = outcome.problems, outcome.notices

    present = set(summary.platforms)
    missing = [p for p in selected if p not in present]
    if missing:
        problems.append(f"missing platform results: {', '.join(missing)}")

    for p in selected:
        if p in summary.stale_platforms:
            problems.append(
                f"{p}: stale results (manifestHash != current manifest) — re-run the {p} suite"
            )
        ids = summary.unknown_ids.get(p)
        if ids:
            problems.append(f"{p}: {len(ids)} fixture id(s) not in manifest")
        tally = summary.status_tallies.get(p)
        if tally is not None:
            bad = tally.get("fail", 0) + tally.get("error", 0)
            if bad:
                problems.append(f"{p}: {bad} fail/error result(s)")

    # Cross-platform mismatch needs every platform's results to come from this
    # run; with a partial selection the others are committed snapshots and a
    # mismatch against them is the full lane's business, not this one's.
    if _ALL_PLATFORMS <= set(selected) and summary.mismatch_count:
        problems.append(
            f"{summary.mismatch_count} cross-platform mismatch(es) — see REPORT.md"
        )

    if visual:
        for p in selected:
            # A comparison that could not run is not a pass. Silence here is
            # what let the visual check sit inert in CI (Pillow missing) while
            # an iOS runner upgrade re-rendered every fixture.
            why = summary.baseline_errors.get(p)
            if why:
                problems.append(f"{p}: screenshots were not compared — {why}")
            count = summary.visual_regressions.get(p, 0)
            if count:
                env_flag = f" --env {env}" if env != DEFAULT_ENV else ""
                problems.append(
                    f"{p}: {count} visual regression(s) vs committed baseline — if "
                    f"intended, re-baseline with `jui conformance baseline update "
                    f"--platform {p}{env_flag}` and commit baselines/{env}/{p}.hashes.json"
                )
            ids = summary.inert_regressions.get(p) or []
            if ids:
                shown = ", ".join(ids[:5]) + (" …" if len(ids) > 5 else "")
                message = (
                    f"{p}: {len(ids)} attribute(s) no longer change what is rendered "
                    f"(identical to their control): {shown}"
                )
                if env == DEFAULT_ENV:
                    problems.append(message)
                else:
                    # The expected-to-differ ledger is asserted from local
                    # renders; on another renderer an identical render can be
                    # the environment, not a regression (measured: 4 iOS
                    # entries held locally and went inert on the CI sim).
                    # Keep the measurement visible, don't fail on it.
                    notices.append(
                        message
                        + f" — ledger assertions are local-env; informational under env '{env}'"
                    )
            unrecorded = summary.inert_unrecorded.get(p, 0)
            if unrecorded:
                notices.append(
                    f"{p}: {unrecorded} fixture(s) render identically to their control "
                    "and are not yet recorded in control_diff.json"
                )

        for metric, values in (
            ("missing_artifact", summary.missing_artifact),
            ("no_baseline", summary.no_baseline),
        ):
            ceilings = ratchet.get(metric, {})
            for p in selected:
                if p in summary.baseline_errors or p not in present:
                    continue  # nothing was measured — already reported above
                count = values.get(p, 0)
                ceiling = ceilings.get(p, 0)
                if count > ceiling:
                    problems.append(
                        f"{p}: {metric} {count} > ratchet ceiling {ceiling} — "
                        f"fixture(s) quietly exited visual coverage (see REPORT.md; "
                        f"ceilings live in {RATCHET_FILENAME})"
                    )
                elif count < ceiling:
                    notices.append(
                        f"{p}: {metric} {count} < ceiling {ceiling} — "
                        f"tighten {RATCHET_FILENAME}"
                    )

    return outcome


def judge_inert_complete(
    conformance_dir: Path,
    platforms: Sequence[str],
    *,
    results_dir: Path | None = None,
    definitions_path: Path | None = None,
    semantics_path: Path | None = None,
    env: str = DEFAULT_ENV,
) -> tuple[list[str], list[str]]:
    """Judge inert COMPLETENESS: every unattributed inert verdict is on file.

    The other lanes each answer "is this specific thing still true". This one
    answers the question none of them can: is there an inert verdict nobody
    has an opinion about? An attribute that silently stops rendering produces
    exactly that — a fixture identical to its control, no ledger entry, no
    contract line, and no failure anywhere.

    Both directions, like every other ratchet here: an unattributed inert
    verdict missing from inert_audit.json fails, and an entry the measurement
    no longer supports fails too (a fixed attribute must not keep an excuse
    on file). Asserted under env `local` — activeness verdicts come from
    local renders, same reasoning as cross-effect.
    """
    import hashlib
    import json as _json

    from . import control_diff as control_diff_mod
    from . import cross_effect as ce_mod
    from . import inert_audit as ia
    from . import rules as rules_mod
    from .report import load_platform_results

    problems: list[str] = []
    notices: list[str] = []
    conformance_dir = Path(conformance_dir)
    selected = list(dict.fromkeys(platforms))

    manifest_path = conformance_dir / "manifest.json"
    if not manifest_path.is_file():
        problems.append(f"--inert-complete: manifest not found: {manifest_path}")
        return problems, notices
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    results_dir = Path(results_dir) if results_dir else conformance_dir / "results"
    loaded = {p.platform: p for p in load_platform_results(results_dir, manifest_hash)}
    diffs = {}
    for platform in selected:
        pr = loaded.get(platform)
        if pr is None:
            continue
        diffs[platform] = control_diff_mod.compare(
            conformance_dir, platform, manifest, pr.results
        )

    definitions: dict = {}
    if definitions_path and Path(definitions_path).is_file():
        definitions = _json.loads(Path(definitions_path).read_text(encoding="utf-8"))

    coverage_path = conformance_dir / "coverage.json"
    coverage_doc = (
        _json.loads(coverage_path.read_text(encoding="utf-8"))
        if coverage_path.is_file()
        else {}
    )

    verdicts = ce_mod.verdicts_from_diffs(diffs)
    result = ia.audit(
        manifest,
        verdicts,
        selected,
        control_diff_ledger=control_diff_mod.load_ledger_all(
            control_diff_mod.ledger_path(conformance_dir)
        ),
        cross_effect_ledger=ce_mod.load_ledger(ce_mod.ledger_path(conformance_dir)),
        contract=ce_mod.load_contract(semantics_path) if semantics_path else {},
        coverage=ia.coverage_gaps(coverage_doc),
        enum_values=ce_mod.enum_fixture_values(manifest, definitions),
    )
    ia.triage(
        result,
        defaults=ia.attribute_defaults(definitions),
        control_identical=ia.control_identical_fixtures(conformance_dir, manifest),
        manifest=manifest,
        fallback_values=(rules_mod.DEFAULT_STRING, rules_mod.DEFAULT_NUMBER),
        sibling_active=ia.sibling_value_evidence(manifest, verdicts, result),
    )

    ledger_file = ia.ledger_path(conformance_dir)
    unrecorded, stale = ia.check_ledger(result, ia.load_ledger(ledger_file))

    def _report(message: str) -> None:
        if env == DEFAULT_ENV:
            problems.append(message)
        else:
            notices.append(
                message
                + f" — inert verdicts are asserted local-env; informational under env '{env}'"
            )

    if unrecorded:
        shown = ", ".join(item.fixture for item in unrecorded[:5]) + (
            " …" if len(unrecorded) > 5 else ""
        )
        _report(
            f"{len(unrecorded)} inert verdict(s) no ledger accounts for "
            f"({ia.LEDGER_FILENAME}) — an attribute that stops rendering looks "
            f"exactly like this; adjudicate or record with `jui conformance "
            f"inert-audit --update`: {shown}"
        )
    if stale:
        shown = ", ".join(stale[:5]) + (" …" if len(stale) > 5 else "")
        _report(
            f"{len(stale)} stale {ia.LEDGER_FILENAME} entr(y/ies) — the fixture is "
            f"no longer an unattributed inert; prune with `jui conformance "
            f"inert-audit --update`: {shown}"
        )
    if not unrecorded and not stale:
        notices.append(
            f"inert completeness OK ({', '.join(selected)}): "
            f"{sum(result.unattributed.values())} unattributed inert verdict(s), "
            "all on the ledger"
        )
    return problems, notices


def judge_cross_effect(
    summary: ReportSummary,
    platforms: Sequence[str],
    ledger: dict,
    *,
    contract: dict | None = None,
    env: str = DEFAULT_ENV,
) -> tuple[list[str], list[str]]:
    """Judge cross-platform activeness agreement. Pure: (problems, notices).

    Comparison spans the *selected* platforms only — results for unselected
    platforms are committed snapshots, not this run's (same reasoning as the
    status-mismatch check). Activeness verdicts, like the control_diff
    ledger, are asserted from local renders: under any other env a finding
    is a notice, not a failure (measured 2026-08-01: attributes hold locally
    and go inert on the CI simulator).
    """
    problems: list[str] = []
    notices: list[str] = []
    selected = list(dict.fromkeys(platforms))
    if len(selected) < 2:
        problems.append(
            "--cross-effect needs at least two selected platforms — activeness "
            f"agreement across {selected or ['(none)']} compares nothing"
        )
        return problems, notices

    result = cross_effect_mod.measure(
        summary.effect_scope,
        summary.effect_verdicts,
        selected,
        summary.effect_enum_values,
    )
    verdict = cross_effect_mod.check(result, ledger, contract)

    def _report(message: str) -> None:
        if env == DEFAULT_ENV:
            problems.append(message)
        else:
            notices.append(
                message
                + f" — activeness is asserted local-env; informational under env '{env}'"
            )

    if verdict.contract_violations:
        shown = "; ".join(verdict.contract_violations[:5]) + (
            " …" if len(verdict.contract_violations) > 5 else ""
        )
        _report(
            f"{len(verdict.contract_violations)} semantics-contract violation(s) "
            f"({cross_effect_mod.CONTRACT_NAME}) — fix the platform or change the "
            f"contract, a ledger reason cannot excuse these: {shown}"
        )
    if verdict.contract_unverified:
        shown = ", ".join(verdict.contract_unverified[:5]) + (
            " …" if len(verdict.contract_unverified) > 5 else ""
        )
        notices.append(
            f"{len(verdict.contract_unverified)} contract expectation(s) could not "
            f"be verified this run (fixture not compared everywhere): {shown}"
        )
    if verdict.unrecorded:
        shown = "; ".join(verdict.unrecorded[:5]) + (
            " …" if len(verdict.unrecorded) > 5 else ""
        )
        _report(
            f"{len(verdict.unrecorded)} cross-platform attribute-effect finding(s) "
            f"not in {cross_effect_mod.LEDGER_NAME} — fix the platform or record + "
            f"justify with `jui conformance cross-effect --update`: {shown}"
        )
    if verdict.stale:
        shown = ", ".join(verdict.stale[:5]) + (" …" if len(verdict.stale) > 5 else "")
        _report(
            f"{len(verdict.stale)} stale {cross_effect_mod.LEDGER_NAME} entr(y/ies) — "
            f"the measurement no longer supports them; prune with "
            f"`jui conformance cross-effect --update`: {shown}"
        )
    if verdict.unverified:
        shown = ", ".join(verdict.unverified[:5]) + (
            " …" if len(verdict.unverified) > 5 else ""
        )
        notices.append(
            f"{len(verdict.unverified)} {cross_effect_mod.LEDGER_NAME} entr(y/ies) "
            f"could not be verified this run (fixture not compared everywhere): {shown}"
        )
    if verdict.ok:
        judged = len(result.consistent) + len(result.mismatched)
        notices.append(
            f"cross-effect OK ({', '.join(selected)}): {judged} fixture(s) judged, "
            f"{verdict.accepted} accepted finding(s) on ledger, "
            f"{verdict.contract_verified} contract expectation(s) verified"
        )
    return problems, notices
