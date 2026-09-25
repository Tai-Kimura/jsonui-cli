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
    unmeasured  (platform, spec, op, cause) — unbound endpoint, no mock, not
                in OpenAPI; and (platform, spec, op, STATUS, cause) for no
                scenario, which is per status (v4.21: keyed per op, a status
                that lost its scenario later passed as matched)
  Declaration errors and cannot-start are never recorded: they are fixed on the
  spot. Neither is anything else on the exit-3 side (a row that could not be
  bound — not evaluated —, an unreadable screen, HTTP with nothing evaluated):
  those are NOT baselinable, so they keep failing the gate.
- `jsonui-test contracts baseline` writes it: the current set when there is no
  file — only with `--initial` (v4.21: the first recording accepts all current
  debt, the user's decision); existing ∩ current when there is. THE TOOL ONLY
  SHRINKS IT. Adding is done by hand, and shows in the commit's diff.
- Compared with the current entries: matched (in both), new (current only),
  stale (baseline only — closed, still listed). The gate passes only when new
  and stale are both 0: a closed entry left in the baseline would silently
  swallow the same entry when it came back.
- HIDDEN (v4.21): a baselined entry under what cannot be measured NOW — its
  op has no mock, is not in the OpenAPI, or is an unbound endpoint; or, for a
  status, it has no scenario — is not closed, only unmeasured. It is neither
  matched nor stale, and the command keeps it. (Dropping it was the loss the
  "nothing written" guard exists for; these causes are baselinable, so the
  guard did not see them.)
- VANISHED (v4.22, ee; hole #41 generalised): a baselined entry whose unit is
  not in the run at all — the screen left the platform, the spec file is gone
  (a rename too), the method or the op is no longer declared, the status is
  gone from the OpenAPI. Only an entry the run MEASURED and found answered by
  a decision (a row, alsoStatuses, excludedOutcomes, unreachedOps; for an
  unmeasured one, its op or status measured now) is closed — stale, and the
  command drops it. A vanished one fails the gate and the command keeps it:
  removing or re-keying it is done by hand, where the diff shows it — the
  user's decision. Dropping an endpoint, a status or a platform is no longer
  a way out of the debt.
  baselined = matched + stale + hidden + vanished.
"""
from __future__ import annotations

import json
from pathlib import Path

BASELINE_FILE = "contracts_coverage_baseline.json"
UNMEASURED_CAUSES = ("unbound endpoint", "no scenario", "no mock", "not in OpenAPI")
#: The causes that hide every status of an op; "no scenario" hides one.
OP_LEVEL_CAUSES = ("unbound endpoint", "no mock", "not in OpenAPI")


def entry_key(entry: dict) -> tuple:
    """A total, deterministic order over entries of both kinds."""
    if entry["kind"] == "uncovered":
        return ("uncovered", entry["platform"], entry["spec"], entry["method"] or "",
                entry["op"], entry["status"])
    return ("unmeasured", entry["platform"], entry["spec"], "", entry["op"], entry["cause"],
            entry.get("status") or "")


def _status_of(key: tuple) -> str:
    return key[5] if key[0] == "uncovered" else key[6]


def measured(report) -> dict:
    """{(platform, spec): ScreenResult} of the screens the run evaluated."""
    return {(b.platform, s.spec): s for b in report.platforms for s in b.screens
            if not s.platform_excluded and not s.not_evaluated_reason}


def _closed(key: tuple, screen) -> bool:
    """Did the run measure *key*'s unit and find it answered by a decision?"""
    if screen is None:
        return False
    if key[0] == "uncovered":
        method, op, status = key[3] or None, key[4], key[5]
        return ((method, op, status) in screen.answered or (op, status) in screen.answered_any
                or (method is None and any(a[1:] == (op, status) for a in screen.answered)))
    op, cause, status = key[4], key[5], key[6]
    if cause == "no scenario":
        return (op, status) in screen.measured_statuses
    return op in screen.measured_ops


def _hidden_keys(base: set, now: set) -> set:
    """The baselined keys under what cannot be measured in the current run."""
    op_level = {(k[1], k[2], k[4]) for k in now
                if k[0] == "unmeasured" and k[5] in OP_LEVEL_CAUSES}
    no_scenario = {(k[1], k[2], k[4], k[6]) for k in now
                   if k[0] == "unmeasured" and k[5] == "no scenario"}
    return {k for k in base - now
            if (k[1], k[2], k[4]) in op_level
            or (k[1], k[2], k[4], _status_of(k)) in no_scenario}


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
                entry = {"kind": "unmeasured", "platform": block.platform,
                         "spec": s.spec, "op": item["op"], "cause": item["cause"]}
                if item.get("status"):
                    entry["status"] = item["status"]
                entries.append(entry)
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
    # Every way it cannot be read names the file and whose call the repair is
    # (v4.21, ee): a conflict-marked file used to surface as a bare
    # "Expecting value: line 1 column 1".
    repair = "repairing it is the user's decision"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"{path} cannot be read ({e}) — {repair}") from e
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected an object with an 'entries' list — {repair}")
    return sorted(entries, key=entry_key)


def dump(entries: list) -> str:
    """The file's bytes: sorted, no timestamps — the same set, the same bytes."""
    return json.dumps({"entries": sorted(entries, key=entry_key)},
                      ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _gone_keys(base: set, now: set, units) -> tuple:
    """(hidden, vanished) among the baselined keys the run does not hold.
    Without *units* (no run to read), none vanish: everything not hidden is
    closed, as before v4.22."""
    hidden = _hidden_keys(base, now)
    if units is None:
        return hidden, set()
    vanished = {k for k in base - now - hidden if not _closed(k, units.get((k[1], k[2])))}
    return hidden, vanished


def compare_items(current: list, baseline, units=None) -> dict:
    """Per platform: {new, stale, hidden, vanished} as lists of entries
    (sorted). No baseline: every current entry is new (the gate then asks
    exactly what exit 0 asked). *units* is `measured(report)`."""
    base = {entry_key(e): e for e in (baseline or [])}
    now = {entry_key(e): e for e in current}
    hidden, vanished = _gone_keys(set(base), set(now), units)
    out = {}
    for p in sorted({k[1] for k in set(base) | set(now)}):
        out[p] = {
            "new": [now[k] for k in sorted(now) if k[1] == p and k not in base],
            "stale": [base[k] for k in sorted(base) if k[1] == p and k not in now
                      and k not in hidden and k not in vanished],
            "hidden": [base[k] for k in sorted(base) if k[1] == p and k in hidden],
            "vanished": [base[k] for k in sorted(base) if k[1] == p and k in vanished]}
    return out


def compare(current: list, baseline, units=None) -> dict:
    """Per platform: {baselined, matched, new, stale, hidden, vanished} —
    baselined = matched + stale + hidden + vanished."""
    base = {entry_key(e) for e in (baseline or [])}
    now = {entry_key(e) for e in current}
    items = compare_items(current, baseline, units)
    out = {}
    for p, lists in items.items():
        b = {k for k in base if k[1] == p}
        out[p] = {"baselined": len(b), "matched": len(b & now), "new": len(lists["new"]),
                  "stale": len(lists["stale"]), "hidden": len(lists["hidden"]),
                  "vanished": len(lists["vanished"])}
        assert out[p]["baselined"] == (out[p]["matched"] + out[p]["stale"] + out[p]["hidden"]
                                       + out[p]["vanished"])
    return out


def counts_for(comparison: dict, platform: str) -> dict:
    return comparison.get(platform, {"baselined": 0, "matched": 0, "new": 0, "stale": 0,
                                     "hidden": 0, "vanished": 0})


def by_spec(entries: list) -> str:
    """`detail 2, other 1` — where to look, most first."""
    counts: dict = {}
    for e in entries:
        counts[e["spec"]] = counts.get(e["spec"], 0) + 1
    return ", ".join(f"{s} {n}" for s, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def shrink(current: list, baseline, units=None) -> tuple:
    """(entries to write, removed, kept, new-not-added, kept-hidden,
    kept-vanished). With no baseline, the current set is written; with one,
    only what both hold, what is hidden under what cannot be measured now,
    and what vanished from the run — never more. Only a CLOSED entry goes."""
    if baseline is None:
        return list(current), 0, len(current), 0, 0, 0
    base = {entry_key(e): e for e in baseline}
    now = {entry_key(e) for e in current}
    hidden, vanished = _gone_keys(set(base), now, units)
    kept = [base[k] for k in sorted(base) if k in now or k in hidden or k in vanished]
    return (kept, len(base) - len(kept), len(kept), len(now - set(base)), len(hidden),
            len(vanished))
