"""`jsonui-doc cost infra`: the cost simulator's month or day without jui viz (ticket
2026-10-21-agents-skills-mcp-for-server-room §3a-1).

The same reads and the same shapes as viz's /api/infra-cost (jui_cli/viz/infra_cost.py): the load definitions against
the model (infra.load), the model (infra.room), the price book (the room's price files > the fetched cache in
<viz home>/cloud-prices > the bundled table), engine.simulate, then view.month_view or view.day_view. Nothing is kept
between runs.

reply() -> (exit code, reply): 0 the month or the day was simulated; 1 it was, but a load definition has an error (a
file with an error is left out, so the month may lack a scenario's part); 2 nothing could be simulated
(the room, the load folder, the scenario or the date; the reply says which: {ok: False, reason, message}).
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import load as L
from .. import room as R
from . import engine as E
from . import pricebook as PB
from . import view as V

DATE = re.compile(r"^20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
FIRST = 20


def _refuse(reason: str, message: str) -> tuple[int, dict]:
    return 2, {"ok": False, "reason": reason, "message": message}


def _problem(p: dict) -> dict:
    return {k: p.get(k) for k in ("file", "path", "code", "message", "short", "severity", "node")}


def reply(root: Path | str, scenario: str | None = None, date: str | None = None, by: str = "provider",
          env: dict | None = None) -> tuple[int, dict]:
    """(exit code, reply). No date: {ok, dir, scenario, scenarios, month, topNodes, problems, prices}, the month as
    viz's; a date: {ok, dir, scenario, scenarios, day, problems, prices}. A read the room refuses is 2 with its reason."""
    try:
        return _reply(Path(root), scenario, date, by, env)
    except R.Refused as r:
        return _refuse(r.reason, r.message)


def _reply(root: Path, scenario: str | None, date: str | None, by: str, env: dict | None) -> tuple[int, dict]:
    if date is not None and not DATE.match(date):
        return _refuse("bad_request", "the date is YYYY-MM-DD")
    if by not in ("provider", "node"):
        return _refuse("bad_request", "by is provider or node")
    loads = L.read(root)
    if not loads.get("ok"):
        return 2, {"ok": False, "reason": loads.get("reason", "invalid"), "message": loads.get("message", ""),
                   "problems": [_problem(p) for p in loads.get("problems", [])[:FIRST]]}
    scenarios = loads["scenarios"]
    if not scenarios:
        return _refuse("no_load", f"no usable load definition in {loads['dir']}")
    chosen = next((s for s in scenarios if s["id"] == scenario), None) if scenario else scenarios[0]
    if chosen is None:
        return _refuse("no_scenario", f"no scenario {scenario!r}; there are: {', '.join(s['id'] for s in scenarios)}")
    if date is not None and not any(h["date"] == date for h in chosen["hours"]):
        return _refuse("bad_request", f"{date} is not in the scenario's month ({chosen['month']})")
    model = R.read(root)
    book, warnings = PB.load(root, env)
    result = E.simulate(chosen, model, book)
    problems = [p for p in loads["problems"] if p["severity"] in ("error", "warning")]   # the model's: validate infra
    out = {"ok": True, "dir": loads["dir"], "scenario": chosen["id"],
           "scenarios": [{"id": s["id"], "label": s["label"], "file": s["file"], "month": s["month"],
                          "environment": s["environment"]} for s in scenarios],
           "problems": {"count": len(problems), "errors": sum(1 for p in problems if p["severity"] == "error"),
                        "first": [_problem(p) for p in problems[:FIRST]]},
           "prices": {"warnings": warnings[:FIRST], "warningCount": len(warnings)}}
    if date is not None:
        out["day"] = V.day_view(result, model, date)
    else:
        out["month"] = V.month_view(result, model, by)
        for w in out["month"]["warnings"]:   # each its line (the CLI prints it; room.COST_JA)
            w["short"] = R.cost_short(w)
        totals = E.month_totals(result)
        by_node: dict[str, float] = {}
        for d in totals["days"]:
            for n, usd in d["byNode"].items():
                by_node[n] = by_node.get(n, 0.0) + usd
        out["topNodes"] = [{"node": n, "usd": usd} for n, usd in sorted(by_node.items(), key=lambda x: -x[1])[:10]]
    return (1 if out["problems"]["errors"] else 0), out
