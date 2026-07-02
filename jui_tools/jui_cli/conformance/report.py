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
    mismatch_count: int = 0
    stale_platforms: list[str] = field(default_factory=list)
    unknown_ids: dict[str, list[str]] = field(default_factory=dict)


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


def render_report(manifest: dict, manifest_hash: str, platforms: list[PlatformResults]) -> tuple[str, ReportSummary]:
    """Render REPORT.md content. Pure function of its inputs (deterministic)."""
    fixtures: list[dict] = manifest.get("fixtures", [])
    skipped: list[dict] = manifest.get("skipped", [])
    counts: dict = manifest.get("counts", {})
    platform_names = [p.platform for p in platforms]
    known_ids = {f["id"] for f in fixtures}

    summary = ReportSummary(out_path=Path("REPORT.md"), platforms=platform_names)

    lines: list[str] = []
    lines.append(f"<!-- @generated by {REPORT_GENERATOR} — DO NOT EDIT -->")
    lines.append("")
    lines.append("# JsonUI Conformance Report")
    lines.append("")
    lines.append(f"- Manifest: `{manifest_hash}` (sha256)")
    lines.append(f"- Definitions: `{manifest.get('generatedFrom', 'unknown')}` (sha256)")
    lines.append(
        f"- Fixtures: {counts.get('fixtures', len(fixtures))} "
        f"(assertable: {counts.get('assertable', '?')}, visual: {counts.get('visual', '?')}) / "
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
) -> ReportSummary:
    """Read manifest + results and write REPORT.md. Returns a summary."""
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

    content, summary = render_report(manifest, manifest_hash, platforms)

    if out_path is None:
        out_path = conformance_dir / "REPORT.md"
    out_path = Path(out_path)
    out_path.write_text(content, encoding="utf-8")
    summary.out_path = out_path
    return summary
