"""`jsonui-doc cost infra --migration <plan>`: what a migration plan does to the month (ticket
2026-10-22-viz-infra-migration-plan, the requester 10-22: 「コストの差の表示は欲しいね」).

Nothing new is priced: the old model and the model after each step of the plan (migration.Plan.model_at) are each
simulated with the same engine, the same scenario (its rows read against that model, so a row for a node the plan
adds counts once the node is there) and the same price book as `cost infra`, and the reply is their
months side by side — old, new, new - old, by node and by provider, and the total after every step with the step's
own difference. A node the plan changes whose month is not all priced (no price, no rule, no load) is named
(unpricedChanged, and "unpriced" on its row): the difference leaves its part out. With account, each model's account (its environments' scenarios priced with one total, as viz's
コスト chooses them) is given too.

reply() -> (exit code, reply): 0 priced; 1 priced, but a load definition has an error; 2 nothing priced (the room,
the load folder, the scenario, no such plan "no_plan", a plan with an error "bad_plan", no account "no_account").
"""
from __future__ import annotations

from pathlib import Path

from .. import load as L
from .. import migration as MG
from .. import room as R
from . import engine as E
from . import pricebook as PB
from .run import FIRST, _problem, _refuse

MAX_STEPS = 200


def account_scenarios(scenarios: list[dict], model: dict, chosen: dict) -> tuple[bool, list[dict], list[str]]:
    """The account's scenarios, chosen as viz's コスト chooses them (jui_cli/viz/infra_cost.account_scenarios; a test
    holds the two to one answer): (whether it can be had, its scenarios in the model's environments' order, the
    environments left out)."""
    envs = [e["id"] for e in model.get("environments") or []]
    available = len(envs) > 1 and all(any(s["environment"] == e for s in scenarios) for e in envs)
    picked, missing = [], []
    for e in envs:
        s = chosen if chosen["environment"] == e else next(
            (x for x in scenarios if x["environment"] == e and x["month"] == chosen["month"]), None)
        (picked.append(s) if s else missing.append(e))
    return available, picked, missing


def _scenarios(root: Path, model: dict) -> list[dict]:
    """The room's load definitions read against ``model`` (a row for a node the plan adds counts once it is there)."""
    got = L.read(root, model=dict(model, ok=True))
    return got["scenarios"] if got.get("ok") else []


def _month(root: Path, chosen: dict, model: dict, book) -> dict:
    """{usd, byNode, byProvider, noRule, loadUndefined, noPrice, unpriced} of one simulated month: the chosen scenario
    as read against this model."""
    scenario = next((s for s in _scenarios(root, model) if s["id"] == chosen["id"]), chosen)
    t = E.month_totals(E.simulate(scenario, model, book))
    by_node: dict[str, float] = {}
    by_prov: dict[str, float] = {}
    for d in t["days"]:
        for n, v in d["byNode"].items():
            by_node[n] = by_node.get(n, 0.0) + v
        for p, v in d["byProvider"].items():
            by_prov[p] = by_prov.get(p, 0.0) + v
    no_price = sorted({x["node"] for x in t["noPrice"]})
    return {"usd": t["usd"], "byNode": by_node, "byProvider": by_prov, "noRule": t["noRule"],
            "loadUndefined": t["loadUndefined"], "noPrice": no_price,
            "unpriced": set(t["noRule"]) | set(t["loadUndefined"]) | set(no_price)}


def _account(root: Path, model: dict, chosen: dict, book) -> float | None:
    scenarios = _scenarios(root, model)
    chosen = next((s for s in scenarios if s["id"] == chosen["id"]), chosen)
    available, picked, _missing = account_scenarios(scenarios, model, chosen)
    if not available:
        return None
    return E.account_totals(E.simulate_account(picked, model, book))["usd"]


def _rows(old: dict, new: dict, key: str, change: dict | None = None, unpriced: set | None = None) -> list[dict]:
    """Old, new and the difference by ``key``; with ``unpriced`` (by node), whether a part of the node has no price, no
    rule or no load in either month (its 0 is not its cost)."""
    names = list(dict.fromkeys([*old, *new, *(change or {})]))
    rows = [{key: n, **({"change": (change or {}).get(n, "same")} if change is not None else {}),
             **({"unpriced": n in unpriced} if unpriced is not None else {}),
             "old": old.get(n, 0.0), "new": new.get(n, 0.0), "diff": new.get(n, 0.0) - old.get(n, 0.0)} for n in names]
    return sorted(rows, key=lambda r: (-abs(r["diff"]), r[key]))


def reply(root: Path | str, plan_name: str, scenario: str | None = None, account: bool = False,
          env: dict | None = None) -> tuple[int, dict]:
    try:
        return _reply(Path(root), plan_name, scenario, account, env)
    except R.Refused as r:
        return _refuse(r.reason, r.message)


def _reply(root: Path, plan_name: str, scenario: str | None, account: bool, env: dict | None) -> tuple[int, dict]:
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
    plan, plan_problems, old_model = MG.load(root, plan_name)
    if not old_model.get("ok"):
        return _refuse(old_model.get("reason", "invalid"), old_model.get("message", ""))
    if plan is None or MG.M.errors(plan_problems):
        no = any(p["code"] == "migration.no_plan" for p in plan_problems)
        return 2, {"ok": False, "reason": "no_plan" if no else "bad_plan",
                   "message": f"no plan {plan_name!r}" if no else f"the plan {plan_name!r} has errors: jsonui-doc validate infra --migration {plan_name}",
                   "problems": [_problem(p) for p in plan_problems[:FIRST]]}
    book, warnings = PB.load(root, env)
    models = [old_model] + [plan.model_at(k)[0] for k in range(1, plan.last + 1)]
    old, new = _month(root, chosen, models[0], book), _month(root, chosen, models[-1], book)
    change = {s["node"]: {"add": "added", "replace": "replaced", "remove": "removed"}[s["kind"]] for s in plan.steps if s["node"]}
    steps, before = [], old["usd"]
    for s in plan.steps:
        usd = (new["usd"] if s["index"] == plan.last else _month(root, chosen, models[s["index"]], book)["usd"]) \
            if s["index"] <= MAX_STEPS or s["index"] == plan.last else None
        steps.append({"index": s["index"], "node": s["node"], "usd": usd,
                      "diff": None if usd is None or before is None else usd - before})
        before = usd
    acct = None
    if account:
        a_old, a_new = _account(root, models[0], chosen, book), _account(root, models[-1], chosen, book)
        if a_old is None or a_new is None:
            return _refuse("no_account", "the account needs two environments or more, each with a load definition "
                                         "(in the old model and in the new)")
        acct = {"on": True, "old": a_old, "new": a_new, "diff": a_new - a_old}
    problems = [p for p in loads["problems"] if p["severity"] in ("error", "warning")]
    out = {"ok": True, "dir": loads["dir"], "migration": plan_name, "scenario": chosen["id"],
           "scenarios": [{"id": s["id"], "label": s["label"], "file": s["file"], "month": s["month"],
                          "environment": s["environment"]} for s in scenarios],
           "old": {k: old[k] for k in ("usd", "noRule", "loadUndefined", "noPrice")},
           "new": {k: new[k] for k in ("usd", "noRule", "loadUndefined", "noPrice")}, "diff": {"usd": new["usd"] - old["usd"]},
           # the nodes the plan changes whose month is not all priced (no price, no rule, no load) in the old or the new:
           # the difference leaves their part out
           "unpricedChanged": sorted(n for n in change if n in old["unpriced"] | new["unpriced"]),
           "byNode": _rows(old["byNode"], new["byNode"], "node", change, old["unpriced"] | new["unpriced"]),
           "byProvider": _rows(old["byProvider"], new["byProvider"], "provider"),
           "steps": steps, "account": acct,
           "problems": {"count": len(problems), "errors": sum(1 for p in problems if p["severity"] == "error"),
                        "first": [_problem(p) for p in problems[:FIRST]]},
           "prices": {"warnings": warnings[:FIRST], "warningCount": len(warnings)}}
    return (1 if out["problems"]["errors"] else 0), out
