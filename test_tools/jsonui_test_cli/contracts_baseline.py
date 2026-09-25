"""The coverage baseline (ratchet): today's debt, recorded once, only ever shrunk.

Design §6.1 P3c (the user's ruling U7). When validate starts gating on contracts
coverage, eight of nine platform blocks measured would turn red at once, and a
face's only ways out were closing everything or switching the gate off. With a
baseline, the gate holds NEW code to the rule at once while the recorded debt
is closed over time.

- One file per app, `<spec_directory>/contracts_coverage_baseline.json`,
  committed. It holds the entries that make coverage exit non-zero, sorted, no
  timestamps (the diff is deterministic):
    uncovered   (platform, spec, method|null, op, status)
    unmeasured  (platform, spec, op, cause) — unbound endpoint, no scenario,
                no mock, not in OpenAPI
  Declaration errors and cannot-start are never recorded: they are fixed on the
  spot. Neither is anything else on the exit-3 side (a row that could not be
  bound — not evaluated —, an unreadable screen, HTTP with nothing evaluated):
  those are NOT baselinable, so they keep failing the gate.
- `jsonui-test contracts baseline` writes it: the current set when there is no
  file; existing ∩ current when there is. THE TOOL ONLY SHRINKS IT. Adding is
  done by hand, and shows in the commit's diff.
- Compared with the current entries: matched (in both), new (current only),
  stale (baseline only — closed, still listed). The gate passes only when new
  and stale are both 0: a closed entry left in the baseline would silently
  swallow the same entry when it came back.
"""
from __future__ import annotations

import json
from pathlib import Path

BASELINE_FILE = "contracts_coverage_baseline.json"
UNMEASURED_CAUSES = ("unbound endpoint", "no scenario", "no mock", "not in OpenAPI")


def entry_key(entry: dict) -> tuple:
    """A total, deterministic order over entries of both kinds."""
    if entry["kind"] == "uncovered":
        return ("uncovered", entry["platform"], entry["spec"], entry["method"] or "",
                entry["op"], entry["status"])
    return ("unmeasured", entry["platform"], entry["spec"], "", entry["op"], entry["cause"])


def current_entries(report) -> list:
    """The baselinable entries of a coverage report, sorted."""
    entries = []
    for block in report.platforms:
        for s in block.screens:
            if s.platform_excluded:
                continue
            for item in s.uncovered:
                for status in item["statuses"]:
                    entries.append({"kind": "uncovered", "platform": block.platform,
                                    "spec": s.spec, "method": item["method"],
                                    "op": item["op"], "status": status})
            for item in getattr(s, "unmeasured_items", []):
                entries.append({"kind": "unmeasured", "platform": block.platform,
                                "spec": s.spec, "op": item["op"], "cause": item["cause"]})
    unique = {entry_key(e): e for e in entries}
    return [unique[k] for k in sorted(unique)]


def unbaselinable(block) -> dict:
    """What fails the gate whatever the baseline says — by cause, 0s dropped."""
    active = [s for s in block.screens if not s.platform_excluded]
    counts = {
        "declaration errors": sum(len(s.declaration_errors) for s in active) + len(block.app_errors),
        "not evaluated": sum(s.breakdown["not_evaluated"] for s in active),
        "screens not evaluated": sum(1 for s in active if s.not_evaluated_reason),
        "HTTP endpoints with nothing evaluated": block.unmeasured.get("http_without_evaluation", 0),
    }
    return {k: v for k, v in counts.items() if v}


def path_for(spec_dir: Path) -> Path:
    return Path(spec_dir) / BASELINE_FILE


def load(path: Path):
    """The recorded entries, sorted — or None when there is no file."""
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected an object with an 'entries' list")
    return sorted(entries, key=entry_key)


def dump(entries: list) -> str:
    """The file's bytes: sorted, no timestamps — the same set, the same bytes."""
    return json.dumps({"entries": sorted(entries, key=entry_key)},
                      ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def compare(current: list, baseline) -> dict:
    """Per platform: {baselined, matched, new, stale}. No baseline: every
    current entry is new (the gate then asks exactly what exit 0 asked)."""
    base = {entry_key(e) for e in (baseline or [])}
    now = {entry_key(e) for e in current}
    platforms = {k[1] for k in base | now}
    out = {}
    for p in sorted(platforms):
        b = {k for k in base if k[1] == p}
        c = {k for k in now if k[1] == p}
        out[p] = {"baselined": len(b), "matched": len(b & c), "new": len(c - b),
                  "stale": len(b - c)}
    return out


def counts_for(comparison: dict, platform: str) -> dict:
    return comparison.get(platform, {"baselined": 0, "matched": 0, "new": 0, "stale": 0})


def shrink(current: list, baseline) -> tuple:
    """(entries to write, removed, kept, new-not-added). With no baseline, the
    current set is written; with one, only what both hold — never more."""
    if baseline is None:
        return list(current), 0, len(current), 0
    base = {entry_key(e): e for e in baseline}
    now = {entry_key(e) for e in current}
    kept = [base[k] for k in sorted(base) if k in now]
    return kept, len(base) - len(kept), len(kept), len(now - set(base))
