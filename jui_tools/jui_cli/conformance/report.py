"""Merge per-platform conformance results into ``REPORT.md``.

Inputs (see ``conformance/RESULTS_SCHEMA.md`` for the contract):

- ``conformance/manifest.json`` — fixture list, in generation order
- ``conformance/results/<platform>.results.json`` — one file per platform

Output: ``conformance/REPORT.md`` with, from top to bottom:

1. cross-platform mismatch table (the primary purpose of the harness)
2. per-platform summary + staleness warnings
3. full fixture x platform matrix, grouped by component
4. skipped attribute table (reasons — silent drops are forbidden)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import baseline as baseline_mod
from . import control_diff as control_diff_mod
from . import cross_effect as cross_effect_mod

REPORT_GENERATOR = "jui conformance report"

STATUS_SYMBOLS = {
    "pass": "✅",      # ✅
    "fail": "❌",      # ❌
    "error": "⚠️",  # ⚠️
    "skipped": "–",   # –
}
MISSING_SYMBOL = ""
KNOWN_STATUSES = set(STATUS_SYMBOLS)

#: Statuses that participate in mismatch detection (skipped / missing do not).
COMPARABLE_STATUSES = {"pass", "fail", "error"}


@dataclass
class PlatformResults:
    """One parsed ``<platform>.results.json``."""

    platform: str
    path: Path
    manifest_hash: str
    runner: dict
    results: dict[str, dict]  # fixture id -> result entry
    stale: bool = False


@dataclass
class ReportSummary:
    """What one ``jui conformance report`` run produced."""

    out_path: Path
    platforms: list[str] = field(default_factory=list)
    #: Render-environment key the visual comparisons ran against
    #: (``baselines/<env>/``). Facts below marked "visual" are relative to it.
    env: str = baseline_mod.DEFAULT_ENV
    mismatch_count: int = 0
    stale_platforms: list[str] = field(default_factory=list)
    unknown_ids: dict[str, list[str]] = field(default_factory=dict)
    visual_regressions: dict[str, int] = field(default_factory=dict)  # platform -> count
    no_baseline: dict[str, int] = field(default_factory=dict)  # platform -> count
    #: platform -> count of baseline entries with no fresh screenshot (plus
    #: result-referenced screenshots whose PNG is gone). A fixture that stops
    #: producing a screenshot exits visual coverage without failing anything —
    #: this is the number the gate ratchets so that exit is no longer silent.
    missing_artifact: dict[str, int] = field(default_factory=dict)
    #: platform -> {pass/fail/error/skipped: count} over that platform's
    #: results (unknown statuses count as error, like the matrix rendering).
    status_tallies: dict[str, dict[str, int]] = field(default_factory=dict)
    #: platform -> why its screenshots could not be compared at all. A gate
    #: that ignores this reports "0 regressions" for a comparison that never
    #: ran — which is how the whole visual check sat inert in CI (Pillow was
    #: not installed) while an iOS runner upgrade re-rendered every fixture.
    baseline_errors: dict[str, str] = field(default_factory=dict)
    #: platform -> fixtures that render identically to their control despite
    #: being recorded as expected-to-differ. The attribute stopped doing
    #: anything, which no baseline comparison can see: a dropped attribute
    #: renders the default and matches the default it recorded last time.
    inert_regressions: dict[str, list] = field(default_factory=dict)
    #: platform -> count of fixtures indistinguishable from their control and
    #: NOT yet recorded. Reported, not failed — see control_diff.
    inert_unrecorded: dict[str, int] = field(default_factory=dict)
    #: fixture -> SSoT-declared platforms, for every control-bearing fixture.
    #: Carried so the gate can re-measure cross-platform activeness over its
    #: *selected* platforms (the report section below spans all loaded ones).
    effect_scope: dict[str, list[str]] = field(default_factory=dict)
    #: platform -> {fixture: "active"|"inert"} — the control-diff verdicts,
    #: the input to cross_effect.measure. A platform whose comparison errored
    #: contributes no verdicts (its fixtures count as not compared).
    effect_verdicts: dict[str, dict[str, str]] = field(default_factory=dict)
    #: fixture -> declared enum value, for fixtures testing an SSoT-enumerated
    #: value — the population of the uniformly-inert check. Empty when the
    #: attribute definitions were not available to the report run.
    effect_enum_values: dict[str, object] = field(default_factory=dict)


class ReportError(RuntimeError):
    """Raised when required inputs are missing or unreadable."""


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_platform_results(results_dir: Path, current_manifest_hash: str) -> list[PlatformResults]:
    """Load every ``*.results.json`` under *results_dir*, sorted by filename."""
    loaded: list[PlatformResults] = []
    if not results_dir.is_dir():
        return loaded
    for path in sorted(results_dir.glob("*.results.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        platform = raw.get("platform") or path.name[: -len(".results.json")]
        manifest_hash = raw.get("manifestHash", "")
        results: dict[str, dict] = {}
        for entry in raw.get("results", []):
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                results[entry["id"]] = entry
        loaded.append(
            PlatformResults(
                platform=platform,
                path=path,
                manifest_hash=manifest_hash,
                runner=raw.get("runner") or {},
                results=results,
                stale=(manifest_hash != current_manifest_hash),
            )
        )
    return loaded


def _status_of(platform: PlatformResults, fixture_id: str) -> str | None:
    entry = platform.results.get(fixture_id)
    if entry is None:
        return None
    status = entry.get("status")
    return status if status in KNOWN_STATUSES else "error"


def _symbol(status: str | None) -> str:
    if status is None:
        return MISSING_SYMBOL
    return STATUS_SYMBOLS.get(status, STATUS_SYMBOLS["error"])


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #


def _mismatch_rows(
    fixtures: list[dict], platforms: list[PlatformResults]
) -> list[tuple[dict, dict[str, str | None]]]:
    rows = []
    for fixture in fixtures:
        statuses = {p.platform: _status_of(p, fixture["id"]) for p in platforms}
        comparable = {s for s in statuses.values() if s in COMPARABLE_STATUSES}
        if len(comparable) > 1:
            rows.append((fixture, statuses))
    return rows


def _detail_cell(platforms: list[PlatformResults], fixture_id: str) -> str:
    parts = []
    for p in platforms:
        entry = p.results.get(fixture_id)
        if not entry:
            continue
        status = entry.get("status")
        detail = entry.get("detail")
        if status != "pass" and detail:
            parts.append(f"{p.platform}: {_escape_cell(str(detail))}")
    return "<br>".join(parts)


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_report(
    manifest: dict,
    manifest_hash: str,
    platforms: list[PlatformResults],
    visual: dict[str, "baseline_mod.VisualComparison"] | None = None,
    diffs: dict[str, "control_diff_mod.DiffResult"] | None = None,
    env: str = baseline_mod.DEFAULT_ENV,
    enum_values: dict[str, object] | None = None,
) -> tuple[str, ReportSummary]:
    """Render REPORT.md content. Pure function of its inputs (deterministic).

    ``visual`` carries the per-platform baseline comparisons computed by
    :func:`generate_report` (kept out of this function so rendering stays
    filesystem-free and unit-testable).
    """
    fixtures: list[dict] = manifest.get("fixtures", [])
    skipped: list[dict] = manifest.get("skipped", [])
    counts: dict = manifest.get("counts", {})
    platform_names = [p.platform for p in platforms]
    known_ids = {f["id"] for f in fixtures}
    visual = visual or {}

    summary = ReportSummary(
        out_path=Path("REPORT.md"), platforms=platform_names, env=env
    )

    lines: list[str] = []
    lines.append(f"<!-- @generated by {REPORT_GENERATOR} — DO NOT EDIT -->")
    lines.append("")
    lines.append("# JsonUI Conformance Report")
    lines.append("")
    lines.append(f"- Manifest: `{manifest_hash}` (sha256)")
    lines.append(f"- Definitions: `{manifest.get('generatedFrom', 'unknown')}` (sha256)")
    lines.append(
        f"- Fixtures: {counts.get('fixtures', len(fixtures))} "
        f"(assertable: {counts.get('assertable', '?')}, visual: {counts.get('visual', '?')}, "
        f"interactive: {counts.get('interactive', 0)}) / "
        f"skipped attributes: {counts.get('skipped', len(skipped))}"
    )
    lines.append("")
    lines.append("Legend: ✅ pass / ❌ fail / ⚠️ error / – skipped / (blank) no result")
    lines.append("")

    # --- 1. Cross-platform mismatches (always first — the raison d'être) --- #
    lines.append("## Cross-platform mismatches")
    lines.append("")
    mismatches = _mismatch_rows(fixtures, platforms)
    summary.mismatch_count = len(mismatches)
    if not platforms:
        lines.append("_No platform results loaded — run the platform conformance suites first._")
    elif not mismatches:
        lines.append("_No cross-platform mismatches._")
    else:
        header = ["Fixture", "Class"] + platform_names + ["Detail"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for fixture, statuses in mismatches:
            cells = [f"`{fixture['id']}`", fixture.get("class", "")]
            cells += [_symbol(statuses.get(name)) for name in platform_names]
            cells.append(_detail_cell(platforms, fixture["id"]))
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- 1b. Interactive fixtures (v2: binding / callback promotions) --- #
    lines.append("## Interactive fixtures")
    lines.append("")
    interactive_fixtures = [f for f in fixtures if f.get("class") == "interactive"]
    promoted = counts.get("promoted", {}) or {}
    if not interactive_fixtures:
        lines.append("_No interactive fixtures in the manifest (regenerate with v2)._")
    else:
        promoted_label = (
            ", ".join(f"{reason}: {count}" for reason, count in sorted(promoted.items()))
            if promoted
            else "none"
        )
        remaining = {}
        for entry in skipped:
            reason = entry.get("reason", "")
            if reason in ("callback", "binding-only"):
                remaining[reason] = remaining.get(reason, 0) + 1
        remaining_label = (
            ", ".join(f"{reason}: {count}" for reason, count in sorted(remaining.items()))
            if remaining
            else "none"
        )
        lines.append(
            f"- Interactive fixtures: {len(interactive_fixtures)} · "
            f"attributes promoted out of skip reasons: {promoted_label} · "
            f"still skipped: {remaining_label}"
        )
        lines.append("")
        header = ["Fixture", "Case", "Promoted from"] + platform_names + ["Detail"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for fixture in interactive_fixtures:
            cells = [
                f"`{fixture['id']}`",
                f"`{fixture.get('case', '')}`",
                fixture.get("promotedFrom") or "—",
            ]
            cells += [_symbol(_status_of(p, fixture["id"])) for p in platforms]
            cells.append(_detail_cell(platforms, fixture["id"]))
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- 1c. Visual regression (same-platform screenshot baselines) --- #
    lines.append("## Visual regression (same-platform baselines)")
    lines.append("")
    lines.append(
        f"Screenshots are compared against `baselines/{env}/<platform>.hashes.json` "
        f"(render environment `{env}`; algorithm `{baseline_mod.ALGORITHM}`, "
        "Hamming distance > threshold ⇒ regression). Baselines only ever compare "
        "within one render environment — cross-environment and cross-platform "
        "pixel comparison are out of scope by design."
    )
    lines.append("")
    if not platforms:
        lines.append("_No platform results loaded._")
    else:
        lines.append("| Platform | Baseline | Compared | Regressions | No baseline | Missing artifact |")
        lines.append("|---|---|---|---|---|---|")
        for p in platforms:
            comparison = visual.get(p.platform)
            if comparison is None:
                lines.append(f"| {p.platform} | (not evaluated) | | | | |")
                continue
            summary.visual_regressions[p.platform] = len(comparison.regressions)
            summary.no_baseline[p.platform] = len(comparison.no_baseline)
            summary.missing_artifact[p.platform] = len(comparison.missing_artifact)
            if comparison.error:
                summary.baseline_errors[p.platform] = comparison.error
                lines.append(
                    f"| {p.platform} | ⚠️ {_escape_cell(comparison.error)} | | | | |"
                )
                continue
            if not comparison.baseline_exists:
                env_flag = f" --env {env}" if env != baseline_mod.DEFAULT_ENV else ""
                lines.append(
                    f"| {p.platform} | none recorded — run `jui conformance baseline update "
                    f"--platform {p.platform}{env_flag}` | 0 | 0 | {len(comparison.no_baseline)} | 0 |"
                )
                continue
            if comparison.algorithm_mismatch is not None:
                summary.baseline_errors[p.platform] = (
                    f"baseline hashed with `{comparison.algorithm_mismatch}`, "
                    f"current algorithm is `{baseline_mod.ALGORITHM}` — nothing was compared"
                )
                lines.append(
                    f"| {p.platform} | ⚠️ STALE algorithm `{comparison.algorithm_mismatch}` "
                    f"(current `{baseline_mod.ALGORITHM}`) — re-run baseline update | | | | |"
                )
                continue
            regression_label = (
                f"❌ {len(comparison.regressions)}" if comparison.regressions else "0"
            )
            lines.append(
                f"| {p.platform} | threshold {comparison.threshold} | {comparison.compared} "
                f"| {regression_label} | {len(comparison.no_baseline)} "
                f"| {len(comparison.missing_artifact)} |"
            )
        for p in platforms:
            comparison = visual.get(p.platform)
            if comparison is None or comparison.error or not comparison.baseline_exists:
                continue
            if comparison.regressions:
                lines.append("")
                lines.append(f"### {p.platform}: regressions")
                lines.append("")
                lines.append("| Screenshot | Distance | Threshold |")
                lines.append("|---|---|---|")
                for name, distance in comparison.regressions:
                    lines.append(f"| `{name}` | {distance} | {comparison.threshold} |")
            if comparison.no_baseline:
                lines.append("")
                shown = ", ".join(f"`{n}`" for n in comparison.no_baseline[:10])
                more = " …" if len(comparison.no_baseline) > 10 else ""
                lines.append(
                    f"> {p.platform}: {len(comparison.no_baseline)} screenshot(s) without a "
                    f"baseline hash (not compared — NOT a pass): {shown}{more}"
                )
    lines.append("")

    # --- 1d. Attribute effect (fixture vs its control) --- #
    lines.append("## Attribute effect (fixture vs control)")
    lines.append("")
    lines.append(
        "Each visual fixture is compared against its **control** — the same layout "
        "with the attribute under test removed. An identical render means the "
        "attribute did nothing on this platform. Both images come from THIS run, "
        "so no baseline is involved and a runner upgrade cannot mask it."
    )
    lines.append("")
    if not diffs:
        lines.append("_No results to compare._")
    else:
        lines.append("| Platform | Compared | Active | Inert | Recorded-but-inert | Unmeasured |")
        lines.append("|---|---|---|---|---|---|")
        for p in platforms:
            d = diffs.get(p.platform)
            if d is None:
                lines.append(f"| {p.platform} | — | | | | |")
                continue
            if d.error:
                summary.baseline_errors.setdefault(p.platform, d.error)
                lines.append(f"| {p.platform} | **not compared**: {_escape_cell(d.error)} | | | | |")
                continue
            summary.inert_unrecorded[p.platform] = len(d.inert) - len(d.regressions)
            if d.regressions:
                summary.inert_regressions[p.platform] = list(d.regressions)
            compared = len(d.active) + len(d.inert)
            flagged = f"**{len(d.regressions)}**" if d.regressions else "0"
            lines.append(
                f"| {p.platform} | {compared} | {len(d.active)} | {len(d.inert)} "
                f"| {flagged} | {len(d.unmeasured)} |"
            )
        for p in platforms:
            d = diffs.get(p.platform)
            if d is None or d.error:
                continue
            if d.regressions:
                lines.append("")
                lines.append(
                    f"**{p.platform}: {len(d.regressions)} fixture(s) recorded as "
                    "expected-to-differ now render identically to their control — "
                    "the attribute stopped taking effect.**"
                )
                lines.append("")
                for fid in d.regressions[:20]:
                    lines.append(f"- `{fid}`")
                if len(d.regressions) > 20:
                    lines.append(f"- … {len(d.regressions) - 20} more")
            if d.no_control:
                lines.append("")
                lines.append(
                    f"> {p.platform}: {len(d.no_control)} fixture(s) had no usable "
                    "control screenshot (not compared — NOT a pass)"
                )
    lines.append("")

    # --- 1e. Cross-platform attribute effect (activeness agreement) --- #
    lines.append("## Cross-platform attribute effect")
    lines.append("")
    lines.append(
        "Pixel comparison across platforms is out of scope by design, but each "
        "platform's control-diff verdict — *did the attribute change the render?* — "
        "is platform-independent. A fixture whose activeness disagrees across the "
        "platforms its attribute is declared for is a semantic-drift suspect, and "
        "an SSoT-enumerated value that is inert on **every** platform is flagged "
        "uniformly-inert (default rendering, or dead everywhere). Only fixtures "
        "compared on **all** their in-scope platforms are judged; findings are "
        f"accepted (with a reason) in `{cross_effect_mod.LEDGER_NAME}` and "
        "enforced by `jui conformance gate --cross-effect`."
    )
    lines.append("")
    summary.effect_scope = cross_effect_mod.scope_from_manifest(manifest)
    summary.effect_verdicts = cross_effect_mod.verdicts_from_diffs(diffs or {})
    summary.effect_enum_values = dict(enum_values or {})
    cross = cross_effect_mod.measure(
        summary.effect_scope,
        summary.effect_verdicts,
        platform_names,
        summary.effect_enum_values,
    )
    if len(platform_names) < 2:
        lines.append("_Fewer than two platforms loaded — nothing to cross-compare._")
    else:
        lines.append(
            f"- Compared on all in-scope platforms: "
            f"{len(cross.consistent) + len(cross.mismatched)} "
            f"(consistent: {len(cross.consistent)}, "
            f"**diverging: {len(cross.mismatched)}**, "
            f"**uniformly-inert declared values: {len(cross.uniform_inert)}**) · "
            f"not compared everywhere: {len(cross.not_compared)} · "
            f"in scope on <2 platforms: {cross.out_of_scope}"
        )
        if not enum_values:
            lines.append(
                "- _Attribute definitions unavailable to this run — the "
                "uniformly-inert check did not participate._"
            )
        if cross.mismatched:
            lines.append("")
            header = ["Fixture"] + platform_names
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "---|" * len(header))
            for fid in sorted(cross.mismatched):
                verdicts = cross.mismatched[fid]
                cells = [f"`{fid}`"] + [
                    verdicts.get(name, "—") for name in platform_names
                ]
                lines.append("| " + " | ".join(cells) + " |")
        if cross.uniform_inert:
            lines.append("")
            lines.append(
                "Declared values inert on every in-scope platform "
                "(default rendering, or dead everywhere):"
            )
            lines.append("")
            for fid in sorted(cross.uniform_inert):
                lines.append(f"- `{fid}` (value `{cross.uniform_inert[fid]!r}`)")
    lines.append("")

    # --- 2. Platform summaries + staleness --- #
    lines.append("## Platforms")
    lines.append("")
    if not platforms:
        lines.append("_No results found under `results/`._")
    else:
        lines.append("| Platform | Runner | Results | pass | fail | error | skipped | Manifest |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for p in platforms:
            tally = {"pass": 0, "fail": 0, "error": 0, "skipped": 0}
            for fixture_id in p.results:
                status = _status_of(p, fixture_id)
                if status in tally:
                    tally[status] += 1
            summary.status_tallies[p.platform] = dict(tally)
            runner = p.runner or {}
            runner_label = str(runner.get("name", "?"))
            if runner.get("version"):
                runner_label += f" {runner['version']}"
            manifest_state = "⚠️ STALE" if p.stale else "current"
            lines.append(
                f"| {p.platform} | {runner_label} | {len(p.results)} "
                f"| {tally['pass']} | {tally['fail']} | {tally['error']} | {tally['skipped']} "
                f"| {manifest_state} |"
            )
        for p in platforms:
            if p.stale:
                summary.stale_platforms.append(p.platform)
                lines.append("")
                lines.append(
                    f"> ⚠️ `{p.path.name}` was produced against manifest "
                    f"`{p.manifest_hash or '(missing manifestHash)'}` but the current manifest is "
                    f"`{manifest_hash}` — results are stale; re-run the {p.platform} suite."
                )
            unknown = sorted(set(p.results) - known_ids)
            if unknown:
                summary.unknown_ids[p.platform] = unknown
                lines.append("")
                lines.append(
                    f"> ⚠️ `{p.path.name}` contains {len(unknown)} fixture id(s) "
                    f"not present in the manifest: " + ", ".join(f"`{u}`" for u in unknown[:10])
                    + (" …" if len(unknown) > 10 else "")
                )
    lines.append("")

    # --- 3. Full matrix, grouped by component in manifest order --- #
    lines.append("## Matrix")
    lines.append("")
    if not fixtures:
        lines.append("_Manifest contains no fixtures._")
    current_component = None
    header = ["Fixture", "Case", "Class"] + platform_names
    for fixture in fixtures:
        component = fixture.get("component", "")
        if component != current_component:
            if current_component is not None:
                lines.append("")
            current_component = component
            lines.append(f"### {component}")
            lines.append("")
            lines.append("| " + " | ".join(header) + " |")
            lines.append("|" + "---|" * len(header))
        alias_note = " (alias)" if fixture.get("aliasOf") else ""
        cells = [
            f"`{fixture.get('attribute', '')}`{alias_note}",
            f"`{fixture.get('case', '')}`",
            fixture.get("class", ""),
        ]
        cells += [_symbol(_status_of(p, fixture["id"])) for p in platforms]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- 4. Skipped attributes --- #
    lines.append("## Skipped attributes")
    lines.append("")
    if not skipped:
        lines.append("_None._")
    else:
        lines.append("| Component | Attribute | Reason |")
        lines.append("|---|---|---|")
        for entry in skipped:
            lines.append(
                f"| {entry.get('component', '')} | `{entry.get('attribute', '')}` "
                f"| {_escape_cell(str(entry.get('reason', '')))} |"
            )
    lines.append("")

    return "\n".join(lines), summary


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def generate_report(
    conformance_dir: Path,
    results_dir: Path | None = None,
    out_path: Path | None = None,
    env: str = baseline_mod.DEFAULT_ENV,
    definitions_path: Path | None = None,
) -> ReportSummary:
    """Read manifest + results and write REPORT.md. Returns a summary.

    *definitions_path* feeds the uniformly-inert check (which fixtures test
    an SSoT-enumerated value). Left as None it resolves to the repo layout
    (``<conformance_dir>/../shared/core/attribute_definitions.json``); a
    missing file just disables that check — the report says so.
    """
    conformance_dir = Path(conformance_dir)
    manifest_path = conformance_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ReportError(
            f"manifest not found: {manifest_path} — run 'jui conformance generate' first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    if results_dir is None:
        results_dir = conformance_dir / "results"
    platforms = load_platform_results(Path(results_dir), manifest_hash)

    # Same-platform screenshot baseline comparison (plan 12 §3). The names
    # come from the `screenshot` fields the platform runner recorded.
    visual: dict[str, baseline_mod.VisualComparison] = {}
    for p in platforms:
        screenshot_names = [
            Path(entry["screenshot"]).name
            for entry in p.results.values()
            if isinstance(entry.get("screenshot"), str)
        ]
        visual[p.platform] = baseline_mod.compare_platform(
            conformance_dir, p.platform, screenshot_names, env=env
        )

    # Fixture-vs-control comparison: does the attribute change anything on
    # this platform at all? Independent of baselines — both images come from
    # this run — so it survives a runner upgrade that invalidates every hash.
    #
    # The env key IS needed, and the comment that used to sit here said the
    # opposite: "both screenshots come off the same device in the same run".
    # Same run is not same instant. The android CI capture includes a live
    # status bar, and a fixture and its control are photographed seconds
    # apart, so the clock alone put 120 fixtures on the active side (49-E,
    # measured; a8583be taught control_diff to crop for it via ignore_bands).
    # These verdicts feed cross_effect and the semantics contracts through
    # `effect_verdicts` below, so dropping the key here re-introduced the
    # clock into every contract judgement — 13 of the 18 violations reported
    # on round 4.
    diffs: dict[str, control_diff_mod.DiffResult] = {}
    for p in platforms:
        diffs[p.platform] = control_diff_mod.compare(
            conformance_dir, p.platform, manifest, p.results, env=env
        )

    if definitions_path is None:
        definitions_path = (
            conformance_dir.parent / "shared" / "core" / "attribute_definitions.json"
        )
    enum_values: dict[str, object] = {}
    if Path(definitions_path).is_file():
        definitions = json.loads(Path(definitions_path).read_text(encoding="utf-8"))
        enum_values = cross_effect_mod.enum_fixture_values(manifest, definitions)

    content, summary = render_report(
        manifest,
        manifest_hash,
        platforms,
        visual=visual,
        diffs=diffs,
        env=env,
        enum_values=enum_values,
    )

    if out_path is None:
        out_path = conformance_dir / "REPORT.md"
    out_path = Path(out_path)
    out_path.write_text(content, encoding="utf-8")
    summary.out_path = out_path
    return summary
