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

Ratchets (``conformance/gate_ratchet.json``): ``missing_artifact`` counts
baseline entries whose fixture produced no screenshot this run — the way a
fixture silently exits visual coverage. The committed ceilings are the
as-of-introduction reality; a count above its ceiling fails, a count below
prints a reminder to tighten the ceiling. Lowering is routine, raising is a
coverage regression that needs justification in the file itself.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

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
    """Read ratchet ceilings; a missing file means every ceiling is 0."""
    path = Path(conformance_dir) / RATCHET_FILENAME
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    ceilings: dict[str, dict[str, int]] = {}
    for metric in RATCHET_METRICS:
        values = data.get(metric)
        if isinstance(values, dict):
            ceilings[metric] = {
                platform: int(ceiling)
                for platform, ceiling in values.items()
                if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool)
            }
    return ceilings


def evaluate(
    conformance_dir: Path,
    platforms: Sequence[str],
    *,
    results_dir: Path | None = None,
    out_path: Path | None = None,
    visual: bool = True,
    ratchet: dict[str, dict[str, int]] | None = None,
) -> GateOutcome:
    """Render REPORT.md and judge *platforms*. Raises ReportError on bad inputs."""
    conformance_dir = Path(conformance_dir)
    summary = generate_report(conformance_dir, results_dir=results_dir, out_path=out_path)
    if ratchet is None:
        ratchet = load_ratchet(conformance_dir)
    return judge(summary, platforms, visual=visual, ratchet=ratchet)


def judge(
    summary: ReportSummary,
    platforms: Sequence[str],
    *,
    visual: bool = True,
    ratchet: dict[str, dict[str, int]] | None = None,
) -> GateOutcome:
    """The pure judgment: summary in, problems/notices out. No filesystem."""
    ratchet = ratchet or {}
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
                problems.append(
                    f"{p}: {count} visual regression(s) vs committed baseline — if "
                    f"intended, re-baseline with `jui conformance baseline update "
                    f"--platform {p}` and commit baselines/{p}.hashes.json"
                )
            ids = summary.inert_regressions.get(p) or []
            if ids:
                shown = ", ".join(ids[:5]) + (" …" if len(ids) > 5 else "")
                problems.append(
                    f"{p}: {len(ids)} attribute(s) no longer change what is rendered "
                    f"(identical to their control): {shown}"
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
