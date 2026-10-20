"""The simulation (plan, L-B): a scenario (infra/load.py's normalized one) over the room's model, priced from a Book.

For each node of the environment: its rule (infra/rules lookup), how many run and which step each hour (scale.py),
what it carries each hour (the load's quantities times the hour's multiplier; the part over capacity left out unless
the rule charges it), its meters (the rule's formula), and each meter's price and charge on the month's total so far
(parts.py; the totals are kept per price row: a free amount and the steps are the account's). A node billed by the
hour with no load row runs the model's count all month; one billed by use with no load row is "load undefined".

The result keeps, per node, per meter, one number per hour; day_lines and month_totals read it. Nothing raises: a
problem is a warning naming the function, the node, the hour and the meter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import load as LD
from .. import rules as RULES
from . import formulas as F
from . import parts
from . import pricebook as PB
from . import scale


@dataclass
class NodeRun:
    node: str
    rule: str | None
    provider: str
    service: str
    region: str
    hours: int
    running: list[float]
    sku: list[str | None]
    demand: list[float] | None = None
    capacity: list[float | None] | None = None
    served: list[float] | None = None
    overflow: list[float] | None = None
    demand_quantity: str | None = None
    at_max: list[bool] | None = None
    range: dict | None = None                 # autoscale's {min, max} by hour (for 「2〜10」)
    quantities: dict = field(default_factory=dict)   # name -> {unit, label, per, perHour: [...]} (what was carried)
    meters: dict = field(default_factory=dict)       # name -> {unit, sku, service, quantity, amount: [...], usd: [...], price}
    note: str = ""


@dataclass
class Result:
    scenario: str
    month: str
    hours: list[dict]
    nodes: list[NodeRun]
    warnings: list[dict]


def _warn(out: list, fn: str, message: str, node: str | None = None, hour: dict | None = None,
          meter: str | None = None) -> None:
    w = {"fn": fn, "message": message}
    if node:
        w["node"] = node
    if hour:
        w["hour"] = f"{hour['date']}T{hour['hour']:02d}"
    if meter:
        w["meter"] = meter
    out.append(w)


def per_hour_of(amount: float, per: str | None) -> float:
    """An amount per ``per`` (default hour) as an amount per hour."""
    return amount / LD.per_hours()[per or "hour"]


def demand_of(row: dict) -> tuple[str | None, float | None, str | None]:
    """(the quantity scaling is judged on, one instance's amount per hour, its per) from autoscale or vertical."""
    a, v = row.get("autoscale") or {}, row.get("vertical") or {}
    pi = a.get("per_instance")
    if pi:
        return pi["quantity"], per_hour_of(pi["amount"], pi.get("per")), pi.get("per")
    if v.get("quantity"):
        return v["quantity"], None, v.get("per")
    return None, None, None


def flow_series(row: dict, name: str) -> list[float]:
    q = row["quantities"].get(name) or {}
    return [q.get("perHour", 0.0) * m for m in row["multiplier"]]


def instances_and_steps(row: dict, node: dict, hourly: bool, n: int) -> dict:
    """{running, sku, atMax, range, demand, capacity}: instance-hours and the step each hour, and what they can take."""
    if not hourly:
        return {"running": [0.0] * n, "sku": [row.get("sku")] * n}
    qname, per_inst, per = demand_of(row)
    demand = flow_series(row, qname) if qname else None
    v, a = row.get("vertical"), row.get("autoscale")
    steps: list[str | None] = [row.get("sku")] * n
    per_inst_by_hour: list[float | None] = [per_inst] * n
    if v:
        lo = a["minByHour"] if a else (row["count"] or [float(node["count"])] * n)
        hi = a["maxByHour"] if a else lo
        steps = scale.vertical(demand or [0.0] * n, v["ladder"], v.get("target_utilization", 1.0), v["minByHour"],
                               v["maxByHour"], v.get("order", "schedule_vertical"), lo, hi, v.get("change_delay_min", 60),
                               LD.per_hours()[v.get("per") or "hour"])
        amounts = {s["sku"]: s.get("amount") for s in v["ladder"]}
        per_inst_by_hour = [per_hour_of(amounts[s], v.get("per")) if amounts.get(s) is not None else None for s in steps]
    out: dict = {"sku": steps}
    if a and demand is not None and all(p is not None for p in per_inst_by_hour):
        counts, at_max = scale.autoscale(demand, per_inst_by_hour, a.get("target_utilization", 1.0), a["minByHour"],
                                         a["maxByHour"], a.get("step"), a.get("scale_out_delay_min"),
                                         a.get("scale_in_delay_min"))
        out.update(running=[float(c) for c in counts], atMax=at_max, range={"min": a["minByHour"], "max": a["maxByHour"]})
    elif a:
        out.update(running=[float(x) for x in a["minByHour"]], range={"min": a["minByHour"], "max": a["maxByHour"]})
    else:
        out["running"] = row["count"] if row["count"] is not None else [float(node["count"])] * n
    if demand is not None:
        out["demand"] = demand
        out["capacity"] = [scale.capacity(c, p) for c, p in zip(out["running"], per_inst_by_hour)]
    return out


def hour_quantities(row: dict, k: int, demand_quantity: str | None, served_ratio: float) -> tuple[dict, dict]:
    """(quantity -> this hour's amount, cdn_egress_gb by zone): flows times the hour's multiplier (the scaling quantity
    times what was served of it), levels and per-request values as written."""
    q, by_zone, m = {}, {}, row["multiplier"][k]
    for name, e in row["quantities"].items():
        if "byZone" in e:
            by_zone = {z: gb * m for z, gb in e["byZone"].items()}
        elif e["kind"] == "flow":
            q[name] = e["perHour"] * m * (served_ratio if name == demand_quantity else 1.0)
        else:
            q[name] = e["value"]
    return q, by_zone


def meters_of(rule, node: dict, hour_ctx: F.Hour, warnings: list, hour: dict) -> list[F.Meter]:
    try:
        return list(rule.cost(hour_ctx))
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:   # a rule's bug is a warning, not a crash
        _warn(warnings, "meters_of", f"the rule {rule.id} failed ({type(exc).__name__}: {exc})", node["id"], hour)
        return []


def price_meter(book: PB.Book, totals: dict, meter: F.Meter, node: dict, region: str, on: str
                ) -> tuple[float | None, dict | None]:
    """(usd, price trace) of one meter's hour, the month's total of its price row moved on; (None, None): no price."""
    provider = node.get("providerResolved") or node.get("provider") or ""
    found = book.find(provider, meter.service or node.get("service") or "", meter.sku, meter.unit, region, on)
    if not found:
        return None, None
    row = found["row"]
    key = (found["layer"], row.get("file"), row.get("index"))
    before = totals.get(key, 0.0)
    usd, _detail = parts.charge(before, meter.amount, row)
    totals[key] = before + meter.amount
    return usd, PB.ref(found)


def _meter_slot(run: NodeRun, m: F.Meter, n: int) -> dict:
    return run.meters.setdefault(m.name, {"unit": m.unit, "sku": m.sku, "service": m.service, "quantity": m.quantity,
                                          "amount": [0.0] * n, "usd": [0.0] * n, "price": None, "priced": True})


def run_node(row: dict, node: dict, rule, book: PB.Book, totals: dict, hours: list[dict], on: str,
             warnings: list) -> NodeRun:
    n = len(hours)
    hourly = bool(rule and rule.hourly)
    inst = instances_and_steps(row, node, hourly, n)
    qname = demand_of(row)[0] if hourly else None
    run = NodeRun(node=node["id"], rule=rule.id if rule else None, provider=node.get("providerResolved") or "",
                  service=node.get("service") or "", region=row.get("region") or "", hours=n, running=inst["running"],
                  sku=inst["sku"], at_max=inst.get("atMax"), range=inst.get("range"), demand_quantity=qname)
    if "demand" in inst:
        run.demand, run.capacity = inst["demand"], inst["capacity"]
        run.served, run.overflow = [], []
        for d, c in zip(run.demand, run.capacity):
            s, o = scale.served(d, c)
            run.served.append(s)
            run.overflow.append(o)
    for name, e in row["quantities"].items():
        run.quantities[name] = {"unit": e["unit"], "label": e["label"], "per": e.get("per", "hour"), "perHour": [0.0] * n}
    charge_overflow = bool(rule and rule.extra.get("charge_overflow"))
    for k, hour in enumerate(hours):
        ratio = 1.0
        if run.demand is not None and run.demand[k] > 0 and not charge_overflow:
            ratio = run.served[k] / run.demand[k]
        q, by_zone = hour_quantities(row, k, qname, ratio)
        for name in run.quantities:
            run.quantities[name]["perHour"][k] = q.get(name, sum(by_zone.values()) if name == "cdn_egress_gb" else 0.0)
        ctx = F.Hour(node=node, q=q, by_zone=by_zone, running=run.running[k], sku=run.sku[k], hours_in_month=n)
        for m in meters_of(rule, node, ctx, warnings, hour):
            usd, ref = price_meter(book, totals, m, node, run.region, on)
            slot = _meter_slot(run, m, n)
            slot["amount"][k] += m.amount
            if usd is None:
                if not m.optional and slot["priced"]:
                    _warn(warnings, "price_meter", f"no price for {m.service or run.service or '(no service)'} {m.sku} ({m.unit}) in "
                          f"{run.region or 'no region'}", node["id"], hour, m.name)
                slot["priced"] = slot["priced"] and m.optional
                slot["usd"][k] = None if not m.optional else 0.0
            else:
                slot["usd"][k] = (slot["usd"][k] or 0.0) + usd
                slot["price"] = slot["price"] or ref
    return run


def implied_row(node: dict, n: int) -> dict:
    """A node billed by the hour with no load row: the model's count all month, nothing carried."""
    return {"node": node["id"], "quantities": {}, "multiplier": [1.0] * n, "count": [float(node["count"])] * n,
            "autoscale": None, "vertical": None, "sku": None, "region": node.get("regionResolved") or ""}


def run_edge(edge: dict, nodes: dict, book: PB.Book, totals: dict, hours: list[dict], on: str,
             warnings: list) -> NodeRun:
    """An edge's transfer, priced as the from node's provider's data-transfer in its region."""
    a, b = nodes[edge["from"]], nodes[edge["to"]]
    n = len(hours)
    ra, rb = a.get("regionResolved") or "", b.get("regionResolved") or ""
    run = NodeRun(node=f"{edge['from']}>{edge['to']}", rule="transfer", provider=a.get("providerResolved") or "",
                  service="data-transfer", region=ra, hours=n, running=[0.0] * n, sku=[None] * n)
    for k, hour in enumerate(hours):
        gb = {}
        for name, e in edge["quantities"].items():
            amount = e["perHour"] * edge["multiplier"][k]
            kind = "egress" if name == "egress_gb" else ("transfer-inter-region" if ra and rb and ra != rb
                                                         else "transfer-regional")
            gb[kind] = gb.get(kind, 0.0) + amount
        for m in F.transfer(gb):
            usd, ref = price_meter(book, totals, m, a, ra, on)
            slot = _meter_slot(run, m, n)
            slot["amount"][k] += m.amount
            if usd is None:
                if slot["priced"]:
                    _warn(warnings, "run_edge", f"no price for data-transfer {m.sku} in {ra or 'no region'}",
                          run.node, hour, m.name)
                slot["priced"] = False
                slot["usd"][k] = None
            else:
                slot["usd"][k] = (slot["usd"][k] or 0.0) + usd
                slot["price"] = slot["price"] or ref
    return run


def simulate(scenario: dict, model: dict, book: PB.Book) -> Result:
    """The scenario's month, priced. Hours outer and nodes inner would share a free amount fairly by time; the totals
    are kept per price row across nodes in the model's order, hour by hour within a node (a simplification said on the
    page: a shared free amount goes to the first nodes)."""
    hours, warnings = scenario["hours"], []
    n, on = len(hours), scenario["month"] + "-01"
    nodes = {nd["id"]: nd for nd in model["nodes"]}
    rows = {r["node"]: r for r in scenario["loads"]}
    totals: dict = {}
    runs = []
    for node in model["nodes"]:
        if scenario["environment"] not in node["environments"]:
            continue
        rule = RULES.lookup(node)
        row = rows.get(node["id"])
        if rule is None or rule.cost is None:
            runs.append(NodeRun(node=node["id"], rule=None, provider=node.get("providerResolved") or "",
                                service=node.get("service") or "", region=node.get("regionResolved") or "", hours=n,
                                running=[0.0] * n, sku=[None] * n, note="no rule"))
            continue
        if row is None and not rule.hourly:
            runs.append(NodeRun(node=node["id"], rule=rule.id, provider=node.get("providerResolved") or "",
                                service=node.get("service") or "", region=node.get("regionResolved") or "", hours=n,
                                running=[0.0] * n, sku=[None] * n, note="load undefined"))
            continue
        runs.append(run_node(row or implied_row(node, n), node, rule, book, totals, hours, on, warnings))
    for edge in scenario.get("edges", []):
        if edge["from"] in nodes and edge["to"] in nodes:
            runs.append(run_edge(edge, nodes, book, totals, hours, on, warnings))
    return Result(scenario=scenario["id"], month=scenario["month"], hours=hours, nodes=runs, warnings=warnings)


# ---------------------------------------------------------------- reading the result

def node_usd(run: NodeRun, k: int) -> float | None:
    """The node's charge in hour k: None when a meter has no price that hour and nothing else is priced."""
    vals = [m["usd"][k] for m in run.meters.values()]
    priced = [v for v in vals if v is not None]
    return sum(priced) if priced else (None if vals else 0.0)


def rate(perhour: float, per: str) -> float:
    """An amount per hour as per ``per`` (100/sec from 360000/h)."""
    return perhour * LD.per_hours()[per]


def day_lines(result: Result, date: str) -> list[dict]:
    """Every node's hours of one date, a line per meter: what was carried (the quantity's rate as written: リクエスト
    100/sec), the billed amount, its unit and price trace, the charge, the instances and step, and demand / served /
    capacity / overflow where the capacity is known."""
    out = []
    for k, hour in enumerate(result.hours):
        if hour["date"] != date:
            continue
        for run in result.nodes:
            base = {"node": run.node, "hour": hour["hour"], "rule": run.rule, "running": run.running[k], "sku": run.sku[k]}
            if run.range:
                base["range"] = [run.range["min"][k], run.range["max"][k]]
            if run.at_max:
                base["atMax"] = run.at_max[k]
            if run.demand is not None:
                base.update(demand=run.demand[k], capacity=run.capacity[k], served=run.served[k],
                            overflow=run.overflow[k], demandQuantity=run.demand_quantity)
            if run.note:
                out.append(dict(base, note=run.note))
                continue
            for name, m in run.meters.items():
                q = run.quantities.get(m["quantity"] or "")
                line = dict(base, meter=name, amount=m["amount"][k], unit=m["unit"], sku=m["sku"], usd=m["usd"][k],
                            price=m["price"], quantity=m["quantity"])
                if q:          # the meter's own share when it counts the quantity itself (a CDN zone's requests)
                    per_hour = m["amount"][k] if m["unit"] == q["unit"] else q["perHour"][k]
                    line["rate"] = {"value": rate(per_hour, q["per"]), "per": q["per"], "unit": q["unit"],
                                    "label": q["label"]}
                out.append(line)
    return out


def month_totals(result: Result) -> dict:
    """Day by day: the charge of every node, of each provider and of all; the month's; the nodes with no rule, with
    load undefined, the meters with no price, the hours over capacity."""
    days: dict[str, dict] = {}
    no_price, overflow = [], {}
    for run in result.nodes:
        for name, m in run.meters.items():
            if not m["priced"]:
                no_price.append({"node": run.node, "meter": name, "sku": m["sku"], "unit": m["unit"]})
        if run.overflow:
            hours_over = sum(1 for o in run.overflow if o > 0)
            if hours_over:
                overflow[run.node] = hours_over
        for k, hour in enumerate(result.hours):
            d = days.setdefault(hour["date"], {"date": hour["date"], "usd": 0.0, "byNode": {}, "byProvider": {}})
            usd = node_usd(run, k)
            if usd:
                d["usd"] += usd
                d["byNode"][run.node] = d["byNode"].get(run.node, 0.0) + usd
                d["byProvider"][run.provider] = d["byProvider"].get(run.provider, 0.0) + usd
    return {"scenario": result.scenario, "month": result.month, "days": list(days.values()),
            "usd": sum(d["usd"] for d in days.values()),
            "noRule": [r.node for r in result.nodes if r.note == "no rule"],
            "loadUndefined": [r.node for r in result.nodes if r.note == "load undefined"],
            "noPrice": no_price, "overflowHours": overflow, "warnings": result.warnings}
