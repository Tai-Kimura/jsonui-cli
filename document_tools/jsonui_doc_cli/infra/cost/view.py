"""The cost simulator's screens, shaped from engine.simulate's Result (plan, L-C): what the page draws, nothing it has
to compute. month_view: the days stacked by provider or by node (the month's top nodes and the rest), the days with
an hour over capacity or at the autoscale's top, the month's sum, and what is not priced. day_view: one date's top
nodes, hour by hour, each a bar of its meters with the quantity's rate as written, the charge and the price's trace,
the instances and step, and demand / served / capacity / overflow where the capacity is known.
"""
from __future__ import annotations

from . import engine as E

OTHERS = "__others__"
#: a meter's name on the page when no quantity names it (the quantities' own names come from x-label)
METER_LABELS = {"instance": "稼働", "hour": "稼働", "cluster": "クラスター", "storage": "保存", "vcpu": "vCPU",
                "memory": "メモリ", "lcu": "LCU", "capacity": "容量", "shard": "シャード", "plan": "プラン",
                "egress": "インターネットへの転送", "transfer-regional": "ゾーンを跨ぐ転送",
                "transfer-inter-region": "地域を跨ぐ転送"}


def _labels(model: dict) -> dict[str, str]:
    return {n["id"]: n.get("label") or n["id"] for n in model["nodes"]}


def node_hour_usd(run: E.NodeRun, k: int) -> float:
    return E.node_usd(run, k) or 0.0


def day_hours(result: E.Result, date: str) -> list[int]:
    """The indexes of the date's hours in the month."""
    return [k for k, h in enumerate(result.hours) if h["date"] == date]


def ranked(result: E.Result, ks: list[int]) -> list[E.NodeRun]:
    """The nodes with a charge or a note, the most costly over those hours first (then by the model's order)."""
    runs = [r for r in result.nodes if r.meters or r.note]
    return sorted(runs, key=lambda r: -sum(node_hour_usd(r, k) for k in ks))


def flags_by_day(result: E.Result) -> dict[str, dict]:
    """date -> {overflowHours, atMaxHours}: hours any node was over capacity, or wanted more than its max."""
    out: dict[str, dict] = {}
    for k, h in enumerate(result.hours):
        d = out.setdefault(h["date"], {"overflowHours": 0, "atMaxHours": 0})
        if any(r.overflow and r.overflow[k] > 0 for r in result.nodes):
            d["overflowHours"] += 1
        if any(r.at_max and r.at_max[k] for r in result.nodes):
            d["atMaxHours"] += 1
    return out


def month_view(result: E.Result, model: dict, by: str = "provider", top: int = 8) -> dict:
    """{scenario, month, usd, days: [{date, usd, stack: {key: usd}, overflowHours, atMaxHours}], keys: [{key, label}],
    noPrice, noRule, loadUndefined, overflowHours, warnings}. by "provider": one key per provider; "node": the month's
    top nodes and the rest (OTHERS)."""
    totals = E.month_totals(result)
    labels = _labels(model)
    all_k = list(range(len(result.hours)))
    if by == "node":
        order = ranked(result, all_k)
        keep = [r.node for r in order[:top]]
        keys = [{"key": n, "label": labels.get(n, n)} for n in keep]
        if len(order) > top:
            keys.append({"key": OTHERS, "label": f"その他（{len(order) - top}）"})
    else:
        provs = sorted({r.provider or "(none)" for r in result.nodes if r.meters})
        keys = [{"key": p, "label": p} for p in provs]
    flags = flags_by_day(result)
    days = []
    for day in totals["days"]:
        ks = day_hours(result, day["date"])
        stack: dict[str, float] = {}
        for r in result.nodes:
            usd = sum(node_hour_usd(r, k) for k in ks)
            if not usd:
                continue
            key = (r.node if r.node in {x["key"] for x in keys} else OTHERS) if by == "node" else (r.provider or "(none)")
            stack[key] = stack.get(key, 0.0) + usd
        days.append({"date": day["date"], "usd": day["usd"], "stack": stack, **flags.get(day["date"], {})})
    return {"scenario": result.scenario, "month": result.month, "usd": totals["usd"], "by": by, "keys": keys,
            "days": days, "noPrice": totals["noPrice"], "noRule": totals["noRule"],
            "loadUndefined": totals["loadUndefined"], "overflowHours": totals["overflowHours"],
            "warnings": totals["warnings"][:50], "warningCount": len(totals["warnings"])}


def segment(run: E.NodeRun, name: str, m: dict, k: int) -> dict:
    """One meter of one hour: its label, the quantity's rate as written, the amount, the charge, the price's trace."""
    q = run.quantities.get(m["quantity"] or "")
    label = (q or {}).get("label") or METER_LABELS.get(name) or name
    if q and ":" in name:   # one model's tokens (<model>:input-tokens): the quantity's label and the model
        label = f"{label}（{name.rsplit(':', 1)[0]}）"
    out = {"meter": name, "label": label,
           "amount": m["amount"][k], "unit": m["unit"], "sku": m["sku"], "usd": m["usd"][k], "price": m["price"]}
    if q:
        per_hour = m["amount"][k] if m["unit"] == q["unit"] else q["perHour"][k]
        out["rate"] = {"value": E.rate(per_hour, q["per"]), "per": q["per"], "unit": q["unit"]}
    return out


def node_hour(run: E.NodeRun, k: int) -> dict:
    """One node's bar in hour k."""
    out = {"usd": node_hour_usd(run, k), "running": run.running[k], "sku": run.sku[k],
           "segments": [segment(run, name, m, k) for name, m in run.meters.items() if m["amount"][k] or m["usd"][k]]}
    if run.range:
        out["range"] = [run.range["min"][k], run.range["max"][k]]
    if run.at_max:
        out["atMax"] = bool(run.at_max[k])
    if k and run.sku[k] != run.sku[k - 1]:
        out["stepChanged"] = True
    if run.demand is not None:
        q = run.quantities.get(run.demand_quantity or "", {})
        per = q.get("per", "hour")
        out["load"] = {"quantity": run.demand_quantity, "label": q.get("label", run.demand_quantity), "per": per,
                       "unit": q.get("unit"), "demand": E.rate(run.demand[k], per), "served": E.rate(run.served[k], per),
                       "capacity": None if run.capacity[k] is None else E.rate(run.capacity[k], per),
                       "overflow": E.rate(run.overflow[k], per)}
    return out


def day_view(result: E.Result, model: dict, date: str, top: int = 20) -> dict:
    """{date, hours: [0..23], usd, nodes: [{node, label, provider, rule, note, usd, hours: [node_hour]}], others}:
    the date's top nodes by its charge, the rest summed per hour (others: {count, usd: [24]})."""
    ks = day_hours(result, date)
    labels = _labels(model)
    order = ranked(result, ks)
    nodes = [{"node": r.node, "label": labels.get(r.node, r.node), "provider": r.provider, "rule": r.rule,
              "note": r.note, "usd": sum(node_hour_usd(r, k) for k in ks), "hours": [node_hour(r, k) for k in ks]}
             for r in order[:top]]
    rest = order[top:]
    others = {"count": len(rest), "usd": [sum(node_hour_usd(r, k) for r in rest) for k in ks]}
    return {"scenario": result.scenario, "date": date, "hours": [result.hours[k]["hour"] for k in ks],
            "usd": sum(node_hour_usd(r, k) for r in result.nodes for k in ks), "nodes": nodes, "others": others}


def account_view(pairs: list[tuple[dict, E.Result]], model: dict) -> dict:
    """The account's month (engine.simulate_account's results, one scenario per environment): month_view's shape with
    the days stacked by environment, the sum of all, each scenario's own month, and what is not priced said with its
    environment ({environment} on the items, "<environment> · " before a name)."""
    envs = {e["id"]: e.get("label") or e["id"] for e in model.get("environments") or []}
    each = [(sc, month_view(r, model)) for sc, r in pairs]
    keys = [{"key": sc["environment"], "label": envs.get(sc["environment"], sc["environment"])} for sc, _ in each]
    days: dict[str, dict] = {}
    for sc, mv in each:
        for d in mv["days"]:
            got = days.setdefault(d["date"], {"date": d["date"], "usd": 0.0, "stack": {}, "overflowHours": 0, "atMaxHours": 0})
            got["usd"] += d["usd"]
            got["stack"][sc["environment"]] = got["stack"].get(sc["environment"], 0.0) + d["usd"]
            got["overflowHours"] += d.get("overflowHours", 0)
            got["atMaxHours"] += d.get("atMaxHours", 0)
    warnings = [dict(w, environment=sc["environment"]) for sc, mv in each for w in mv["warnings"]]
    return {"scenario": pairs[0][0]["id"], "month": pairs[0][0]["month"], "usd": sum(mv["usd"] for _, mv in each),
            "by": "environment", "keys": keys, "days": [days[d] for d in sorted(days)],
            "scenarios": [{"scenario": sc["id"], "label": sc.get("label") or sc["id"], "environment": sc["environment"],
                           "usd": mv["usd"]} for sc, mv in each],
            "noPrice": [dict(x, environment=sc["environment"]) for sc, mv in each for x in mv["noPrice"]],
            "noRule": [f"{sc['environment']} · {x}" for sc, mv in each for x in mv["noRule"]],
            "loadUndefined": [f"{sc['environment']} · {x}" for sc, mv in each for x in mv["loadUndefined"]],
            "overflowHours": {f"{sc['environment']} · {n}": h for sc, mv in each for n, h in mv["overflowHours"].items()},
            "warnings": warnings[:50], "warningCount": sum(mv["warningCount"] for _, mv in each)}
