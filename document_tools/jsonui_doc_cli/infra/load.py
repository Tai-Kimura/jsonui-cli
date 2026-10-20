"""The load definitions of the cost simulator (infra-load.v0, plan docs/plans/2026-10-20-jui-viz-backend-load-and-cost-
simulator.md, L-A): read, validated in three passes as the model is, and normalized for the cost (L-B).

The contract is infra-load.v0.schema.json next to this file: the fields, the limits and the closed vocabulary of
quantities (each with its unit x-unit, its kind x-kind and its display name x-label) are read from it, never copied.
Which quantities a node reads and whether it is billed by the hour come from its pricing rule (infra/rules).

1. per file (an error leaves the file out whole): JSON, the schema, the shapes of secrets, and what the file says of
   itself — the profiles and schedules it names are there, its dates are in its month, the timezone is known, a rule
   ends after it starts, min <= max, autoscale and vertical name a flow quantity the row writes, a ladder's steps grow.
2. against the room's merged model (a warning, and only that row is left out): a node or an edge not there, not in the
   scenario's environment, a selector matching none, two rows for one node, a quantity or a schedule the node's rule
   does not read, a flow while the node is stopped.
3. normalized: the month's hours (wall-clock hours of the timezone: a day is 24 of them, a daylight-saving change is
   not counted), and per row the multiplier, the count (a schedule, else the model's count; None for a node not billed
   by the hour), the autoscale and vertical ranges per hour, each quantity per hour with its unit and the "per" it was
   written in, and the region (the node's, its group's, else the scenario's defaults.region).

A problem never carries a value found; where it can, it names the function (fn), the node, the hour and the quantity.
"""
from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

from . import model as M
from . import room as R
from . import rules as RULES

SCHEMA_PATH = Path(__file__).with_name("infra-load.v0.schema.json")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_SCHEMA: list[dict] = []


def schema() -> dict:
    if not _SCHEMA:
        _SCHEMA.append(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return _SCHEMA[0]


def quantities() -> dict[str, dict]:
    """name -> {unit, kind, label}: the closed vocabulary, from the schema."""
    props = schema()["$defs"]["quantities"]["properties"]
    return {k: {"unit": v["x-unit"], "kind": v["x-kind"], "label": v["x-label"]} for k, v in props.items()}


def per_hours() -> dict[str, float]:
    """A rate's "per" -> how many hours it is (second 1/3600 ... month 730)."""
    return dict(schema()["$defs"]["per"]["x-hours"])


def _p(file: str, path: str, code: str, message: str, severity: str = "error", **where) -> dict:
    out = M._problem(file, path, code, message, severity)
    out.update({k: v for k, v in where.items() if v is not None})
    return out


# ---------------------------------------------------------------- 1. one file

def read_file(name: str, raw: bytes) -> tuple[dict | None, list[dict]]:
    """(the file's object, problems): JSON, the shapes of secrets, the schema. None when any of them is an error."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, [dict(_p(name, "/", "json", f"not JSON (line {exc.lineno}, column {exc.colno})", fn="read_file"),
                           line=exc.lineno)]
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return None, [_p(name, "/", "json", f"not JSON ({type(exc).__name__})", fn="read_file")]
    root = schema()
    try:
        strings = list(M._walk_strings(data, "", root))
        found = M.check_schema(data, root=root)
    except RecursionError:
        return None, [_p(name, "/", "json", "nested too deeply to read", fn="read_file")]
    problems = [_p(name, path, f"secret.{kind}", f"holds the shape of a secret ({kind.replace('_', ' ')}): a load "
                   "definition keeps no values", fn="read_file")
                for path, text in strings for kind in M.secret_findings(text)]
    problems += [_p(name, path, "schema", why, fn="check_schema") for path, why in found]
    return (None if problems else data), problems


def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def check_timezone(name: str, doc: dict) -> list[dict]:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415
    tz = doc.get("timezone", "UTC")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return [_p(name, "/timezone", "load.timezone", "not a timezone this machine knows", fn="check_timezone")]
    return []


def check_dates(name: str, doc: dict) -> list[dict]:
    """days[] and holidays[] are real dates of the month; a date in days[] once."""
    out, seen = [], set()
    month = doc["month"]
    for kind in ("days", "holidays"):
        for i, item in enumerate(doc.get(kind, [])):
            d = item["date"] if kind == "days" else item
            path = f"/{kind}/{i}" + ("/date" if kind == "days" else "")
            try:
                date.fromisoformat(d)
            except ValueError:
                out.append(_p(name, path, "load.date", "not a date of the calendar", fn="check_dates"))
                continue
            if not d.startswith(month + "-"):
                out.append(_p(name, path, "load.date", f"not in the month {month}", fn="check_dates"))
            if kind == "days":
                if d in seen:
                    out.append(_p(name, path, "load.date", "the same date twice in days", fn="check_dates"))
                seen.add(d)
    return out


def check_refs(name: str, doc: dict) -> list[dict]:
    """Every profile and schedule named is defined."""
    profiles, schedules, out = set(doc.get("profiles", {})), set(doc.get("schedules", {})), []

    def need(value, have, path, what):
        if value is not None and value not in have:
            out.append(_p(name, path, "load.ref", f"names a {what} not defined in this file", fn="check_refs"))
    for d in DAYS:
        need(doc.get("week", {}).get(d), profiles, f"/week/{d}", "profile")
    for i, item in enumerate(doc.get("days", [])):
        need(item.get("profile"), profiles, f"/days/{i}/profile", "profile")
    for kind in ("loads", "edges"):
        for i, row in enumerate(doc.get(kind, [])):
            need(row.get("profile"), profiles, f"/{kind}/{i}/profile", "profile")
    for i, row in enumerate(doc.get("loads", [])):
        need(row.get("schedule"), schedules, f"/loads/{i}/schedule", "schedule")
    return out


def check_schedules(name: str, doc: dict) -> list[dict]:
    """A rule ends after it starts; its min is not above its max."""
    out = []
    for sname, sch in doc.get("schedules", {}).items():
        for i, rule in enumerate(sch.get("rules", [])):
            path = f"/schedules/{M._seg(sname, schema())}/rules/{i}"
            if _minutes(rule["to"]) <= _minutes(rule["from"]):
                out.append(_p(name, path, "load.rule", "ends at or before it starts (a rule past midnight is two rules)",
                              fn="check_schedules"))
            if "min" in rule and "max" in rule and rule["min"] > rule["max"]:
                out.append(_p(name, path, "load.minmax", "min is above max", fn="check_schedules"))
    return out


def _flow_written(row: dict, quantity: str) -> bool:
    q = quantities().get(quantity)
    return bool(q and q["kind"] == "flow" and quantity in row.get("quantities", {}))


def check_autoscale(name: str, i: int, row: dict, sch: dict | None) -> list[dict]:
    """min <= max (with the schedule's rules applied too); per_instance names a flow quantity the row writes."""
    a, path, out = row.get("autoscale"), f"/loads/{i}/autoscale", []
    if not a:
        return out
    if a["min"] > a["max"]:
        out.append(_p(name, path, "load.minmax", "min is above max", fn="check_autoscale"))
    for j, rule in enumerate((sch or {}).get("rules", [])):
        lo, hi = rule.get("min", a["min"]), rule.get("max", a["max"])
        if lo > hi:
            out.append(_p(name, f"{path}", "load.minmax",
                          f"min is above max in the hours of its schedule's rule {j}", fn="check_autoscale"))
    pi = a.get("per_instance")
    if pi is None and not row.get("vertical"):
        out.append(_p(name, path, "load.autoscale", "per_instance is required (it may be left out only with vertical, "
                      "whose steps say what one instance takes)", fn="check_autoscale"))
    elif pi is not None and not _flow_written(row, pi["quantity"]):
        out.append(_p(name, f"{path}/per_instance/quantity", "load.autoscale",
                      "names no flow quantity this row writes", fn="check_autoscale", quantity=pi["quantity"]))
    elif pi is not None and row.get("vertical") and pi["quantity"] != row["vertical"].get("quantity"):
        out.append(_p(name, f"{path}/per_instance/quantity", "load.autoscale",
                      "with vertical, the quantity must be vertical's", fn="check_autoscale", quantity=pi["quantity"]))
    return out


def _grows(prev: dict, cur: dict) -> bool:
    if "amount" in prev and "amount" in cur:
        return cur["amount"] > prev["amount"]
    pv, pm = prev.get("vcpu", 0), prev.get("memory_gb", 0)
    cv, cm = cur.get("vcpu", 0), cur.get("memory_gb", 0)
    return cv >= pv and cm >= pm and (cv > pv or cm > pm)


def check_vertical(name: str, i: int, row: dict, sch: dict | None) -> list[dict]:
    """The ladder: skus once each, each step bigger than the last, min's step not above max's; the quantity a flow the
    row writes; a schedule's sku one of the steps."""
    v, path, out = row.get("vertical"), f"/loads/{i}/vertical", []
    if not v:
        return out
    skus = [s["sku"] for s in v["ladder"]]
    if len(set(skus)) != len(skus):
        out.append(_p(name, f"{path}/ladder", "load.ladder", "the same sku twice", fn="check_vertical"))
    for k, step in enumerate(v["ladder"]):
        if "amount" not in step and "vcpu" not in step and "memory_gb" not in step:
            out.append(_p(name, f"{path}/ladder/{k}", "load.ladder", "says neither amount nor vcpu / memory_gb",
                          fn="check_vertical"))
        elif k and not _grows(v["ladder"][k - 1], step):
            out.append(_p(name, f"{path}/ladder/{k}", "load.ladder", "not bigger than the step before it",
                          fn="check_vertical"))
    for end in ("min", "max"):
        if end in v and v[end] not in skus:
            out.append(_p(name, f"{path}/{end}", "load.ladder", "not a step of the ladder", fn="check_vertical"))
    if v.get("min") in skus and v.get("max") in skus and skus.index(v["min"]) > skus.index(v["max"]):
        out.append(_p(name, path, "load.minmax", "min's step is above max's", fn="check_vertical"))
    if any("amount" in s for s in v["ladder"]):
        if "quantity" not in v:
            out.append(_p(name, path, "load.ladder", "the steps say amounts: quantity is required", fn="check_vertical"))
        elif not _flow_written(row, v["quantity"]):
            out.append(_p(name, f"{path}/quantity", "load.ladder", "names no flow quantity this row writes",
                          fn="check_vertical", quantity=v["quantity"]))
    for j, rule in enumerate((sch or {}).get("rules", [])):
        if "sku" in rule and rule["sku"] not in skus:
            out.append(_p(name, path, "load.ladder", f"its schedule's rule {j} names a sku not in the ladder",
                          fn="check_vertical"))
    return out


def check_rows(name: str, doc: dict) -> list[dict]:
    out = []
    schedules = doc.get("schedules", {})
    for i, row in enumerate(doc.get("loads", [])):
        if ("node" in row) == ("nodes" in row):
            out.append(_p(name, f"/loads/{i}", "load.target", "needs exactly one of node and nodes", fn="check_rows"))
        sch = schedules.get(row.get("schedule"))
        out += check_autoscale(name, i, row, sch) + check_vertical(name, i, row, sch)
    for i, row in enumerate(doc.get("edges", [])):
        by_id, by_ends, any_end = "edge" in row, "from" in row and "to" in row, "from" in row or "to" in row
        if not ((by_id and not any_end) or (by_ends and not by_id)):
            out.append(_p(name, f"/edges/{i}", "load.target", "needs the edge's id, or both from and to",
                          fn="check_rows"))
    return out


def check_file(name: str, raw: bytes) -> tuple[dict | None, list[dict]]:
    """Pass 1: the file alone. (the object, problems); the object is None when the file has any error."""
    doc, problems = read_file(name, raw)
    if doc is None:
        return None, problems
    for check in (check_timezone, check_dates, check_refs, check_schedules, check_rows):
        problems += check(name, doc)
    return (None if M.errors(problems) else doc), problems


# ---------------------------------------------------------------- 3. the hours (pass 3's frame, used by pass 2)

def month_hours(doc: dict) -> list[dict]:
    """The month's hours: {date, hour, dow, holiday}, wall-clock hours of the timezone (24 a day)."""
    y, m = map(int, doc["month"].split("-"))
    holidays = set(doc.get("holidays", []))
    out = []
    for day in range(1, calendar.monthrange(y, m)[1] + 1):
        d = date(y, m, day)
        iso = d.isoformat()
        for h in range(24):
            out.append({"date": iso, "hour": h, "dow": DAYS[d.weekday()], "holiday": iso in holidays})
    return out


def day_shape(doc: dict, hour: dict, row_profile: str | None) -> float:
    """One hour's multiplier: the row's profile, else the date's (days[]), else the day of the week's (week); times
    the date's multiplier. No profile: 1.0."""
    special = next((d for d in doc.get("days", []) if d["date"] == hour["date"]), {})
    name = row_profile or special.get("profile") or doc.get("week", {}).get(hour["dow"])
    shape = doc["profiles"][name]["hourly"][hour["hour"]] if name else 1.0
    return shape * special.get("multiplier", 1.0)


def rule_covers(rule: dict, hour: dict, dow: str, half: int) -> bool:
    """Whether the rule covers that half of the hour (0: :00-:30, 1: :30-:00) on that day. Rules start and end on the
    hour or the half hour, so a half is covered whole or not at all."""
    if dow not in rule["days"] and not (hour["holiday"] and "holiday" in rule["days"]):
        return False
    start = hour["hour"] * 60 + half * 30
    return _minutes(rule["from"]) <= start and start + 30 <= _minutes(rule["to"])


def half_hour(sch: dict, hour: dict, dow: str, half: int) -> dict:
    """What the schedule says for one half of the hour: the default count, then each rule covering it in order (a
    later rule wins): its count (and as "fixed"), min, max, sku."""
    out: dict = {"count": float(sch.get("default", 1))}
    for rule in sch.get("rules", []):
        if rule_covers(rule, hour, dow, half):
            out.update({k: rule[k] for k in ("min", "max", "sku") if k in rule})
            if "count" in rule:
                out["count"] = float(rule["count"])
                out["fixed"] = rule["count"]
    return out


def schedule_hour(sch: dict, hour: dict) -> dict:
    """One hour of a schedule: {count} — the two halves' counts averaged (instance-hours) — and the min, max, sku and
    fixed count of a rule covering at least half of it (each half decided on its own; when the halves differ, the
    second's, as the hour ends in it). A holiday "off" is 0; "weekend" reads as a sunday."""
    if hour["holiday"] and sch.get("holidays") == "off":
        return {"count": 0.0, "min": 0, "max": 0, "off": True}
    dow = "sun" if hour["holiday"] and sch.get("holidays") == "weekend" else hour["dow"]
    first, second = half_hour(sch, hour, dow, 0), half_hour(sch, hour, dow, 1)
    out = {k: v for k, v in {**first, **second}.items() if k != "count"}
    out["count"] = (first["count"] + second["count"]) / 2
    return out


# ---------------------------------------------------------------- 2. against the model

def environment_of(name: str, doc: dict, model: dict) -> tuple[str, list[dict]]:
    envs = [e["id"] for e in model["environments"]]
    want = doc.get("environment")
    if want is None:
        return envs[0], ([_p(name, "/environment", "load.environment",
                             f"not given and the model has {len(envs)} environments: the first is used", "warning",
                             fn="environment_of")] if len(envs) > 1 else [])
    if want not in envs:
        return envs[0], [_p(name, "/environment", "load.environment",
                            "not an environment of the model: the first is used", "warning", fn="environment_of")]
    return want, []


def _in_group(node: dict, gid: str, groups: dict) -> bool:
    cur, seen = node.get("group"), set()
    while cur and cur not in seen:
        if cur == gid:
            return True
        seen.add(cur)
        cur = groups.get(cur, {}).get("parent")
    return False


def _matches(sel: dict, n: dict, groups: dict) -> bool:
    svc = n.get("service") or ""
    return ((not sel.get("category") or n["category"] == sel["category"])
            and (not sel.get("provider") or n["providerResolved"] == sel["provider"])
            and (not sel.get("service") or sel["service"] in (svc, svc.split(".", 1)[0]))
            and (not sel.get("group") or _in_group(n, sel["group"], groups)))


def select(sel: dict, nodes: list[dict], groups: dict) -> list[dict]:
    """The nodes matching every field of a selector (service: the node's, or its head before ".")."""
    return [n for n in nodes if _matches(sel, n, groups)]


def assign_rows(name: str, doc: dict, env: str, model: dict) -> tuple[dict[str, tuple[int, dict]], list[dict]]:
    """node id -> (row index, row): a node's own row beats a selector's; among the same kind the later wins."""
    nodes_all = {n["id"]: n for n in model["nodes"]}
    in_env = [n for n in model["nodes"] if env in n["environments"]]
    groups = {g["id"]: g for g in model["groups"]}
    got: dict[str, tuple[int, dict, bool]] = {}
    out = []
    for i, row in enumerate(doc.get("loads", [])):
        if "node" in row:
            nid = row["node"]
            if nid not in nodes_all:
                out.append(_p(name, f"/loads/{i}/node", "load.node_missing", "names a node the model does not have: "
                              "this row is left out", "warning", fn="assign_rows", node=nid))
                continue
            if env not in nodes_all[nid]["environments"]:
                out.append(_p(name, f"/loads/{i}/node", "load.not_in_environment",
                              "the node is not in this scenario's environment: this row is left out", "warning",
                              fn="assign_rows", node=nid))
                continue
            targets, own = [nid], True
        else:
            targets, own = [n["id"] for n in select(row["nodes"], in_env, groups)], False
            if not targets:
                out.append(_p(name, f"/loads/{i}/nodes", "load.select_none", "matches no node of the environment",
                              "warning", fn="assign_rows"))
        for nid in targets:
            prev = got.get(nid)
            if prev is not None and prev[2] and not own:      # a node's own row beats a selector's
                out.append(_p(name, f"/loads/{i}", "load.overlap", f"the node has its own row {prev[0]}: that one is "
                              "used", "warning", fn="assign_rows", node=nid))
                continue
            if prev is not None:
                out.append(_p(name, f"/loads/{i}", "load.overlap", f"the node already has row {prev[0]}: this later "
                              "row is used", "warning", fn="assign_rows", node=nid))
            got[nid] = (i, row, own)
    return {k: (i, r) for k, (i, r, _o) in got.items()}, out


def check_against_rule(name: str, i: int, row: dict, node: dict) -> list[dict]:
    """A quantity, a schedule, autoscale or vertical that the node's pricing rule does not read: a warning."""
    rule = RULES.lookup(node)
    if rule is None:
        return []
    out = []
    for q in row.get("quantities", {}):
        if q not in rule.reads:
            out.append(_p(name, f"/loads/{i}/quantities/{q}", "load.quantity_unused",
                          f"a {node['category']} node does not read {q} ({rule.id})", "warning",
                          fn="check_against_rule", node=node["id"], quantity=q))
    if not rule.hourly:
        for k in ("schedule", "autoscale", "vertical"):
            if k in row:
                out.append(_p(name, f"/loads/{i}/{k}", "load.schedule_unused",
                              f"a {node['category']} node is not billed by the hour ({rule.id}): {k} changes nothing",
                              "warning", fn="check_against_rule", node=node["id"]))
    return out


def resolve_edges(name: str, doc: dict, env: str, model: dict) -> tuple[list[tuple[int, dict, dict]], list[dict]]:
    """(row index, row, the model's edge) for each edges[] row whose edge is there."""
    out, found = [], []
    edges = [e for e in model["edges"] if env in e["environments"]]
    for i, row in enumerate(doc.get("edges", [])):
        if "edge" in row:
            hits = [e for e in edges if e.get("id") == row["edge"]]
        else:
            hits = [e for e in edges if e["from"] == row["from"] and e["to"] == row["to"]]
        if not hits:
            out.append(_p(name, f"/edges/{i}", "load.edge_missing", "names an edge the model does not have in this "
                          "environment: this row is left out", "warning", fn="resolve_edges"))
            continue
        if len(hits) > 1:
            out.append(_p(name, f"/edges/{i}", "load.edge_ambiguous", f"{len(hits)} edges join these nodes: the first "
                          "is used (name it by its id)", "warning", fn="resolve_edges"))
        found.append((i, row, hits[0]))
    return found, out


# ---------------------------------------------------------------- 3. normalized

def per_hour(value) -> tuple[float, str]:
    """A flow quantity as (amount per hour, the per it was written in)."""
    if isinstance(value, dict):
        per = value.get("per", "hour")
        return value["amount"] / per_hours()[per], per
    return float(value), "hour"


def normalize_quantities(qs: dict) -> dict:
    vocab, out = quantities(), {}
    for name, value in qs.items():
        q = vocab[name]
        entry = {"unit": q["unit"], "kind": q["kind"], "label": q["label"]}
        if name == "cdn_egress_gb":
            per = value.get("per", "hour")
            entry.update(byZone={z: a / per_hours()[per] for z, a in value["by_zone"].items()}, per=per)
        elif q["kind"] == "flow":
            entry["perHour"], entry["per"] = per_hour(value)
        else:
            entry["value"] = float(value)
        out[name] = entry
    return out


def region_of(node: dict, doc: dict) -> tuple[str, str]:
    """(the region, where it came from: node / group / defaults / "")."""
    if node.get("region"):
        return node["region"], "node"
    if node.get("regionResolved"):
        return node["regionResolved"], "group"
    d = doc.get("defaults", {}).get("region")
    return (d, "defaults") if d else ("", "")


def scaling_hours(row: dict, sch: dict | None, hours: list[dict]) -> tuple[dict | None, dict | None]:
    """The autoscale min/max and the vertical step range per hour, the schedule's rules applied."""
    a, v = row.get("autoscale"), row.get("vertical")
    auto = vert = None
    if a:
        auto = {k: a[k] for k in a}
        auto["minByHour"], auto["maxByHour"] = [], []
    if v:
        skus = [s["sku"] for s in v["ladder"]]
        vert = {k: v[k] for k in v}
        vert.setdefault("min", skus[0])
        vert.setdefault("max", skus[-1])
        vert.setdefault("order", "schedule_vertical")
        vert.setdefault("change_delay_min", 60)
        vert["minByHour"], vert["maxByHour"] = [], []
    for hour in hours:
        sh = schedule_hour(sch, hour) if sch else {}
        if auto is not None:
            lo, hi = sh.get("min", a["min"]), sh.get("max", a["max"])
            if "fixed" in sh:
                lo = hi = sh["fixed"]
            if sh.get("off"):
                lo = hi = 0
            auto["minByHour"].append(lo)
            auto["maxByHour"].append(hi)
        if vert is not None:
            lo, hi = vert["min"], vert["max"]
            if "sku" in sh:
                lo = sh["sku"]
                if vert["order"] == "schedule_vertical":
                    hi = sh["sku"]
            vert["minByHour"].append(lo)
            vert["maxByHour"].append(hi)
    return auto, vert


def count_hours(row: dict, sch: dict | None, node: dict, hours: list[dict], hourly: bool) -> list[float] | None:
    """Instance-hours per hour for a fixed row: its schedule's, else the model's count; None when the node is not
    billed by the hour or its row scales by autoscale (L-B counts those)."""
    if not hourly or row.get("autoscale"):
        return None
    if sch is None:
        return [float(node["count"])] * len(hours)
    return [schedule_hour(sch, h)["count"] for h in hours]


def check_stopped(name: str, i: int, node_id: str, quantities_: dict, mult: list[float], running: list[float] | None,
                  hours: list[dict]) -> list[dict]:
    """A flow in an hour the node is stopped (0 running): a warning with the number of hours and the first."""
    if running is None:
        return []
    flows = [q for q, e in quantities_.items() if e["kind"] == "flow" and (e.get("perHour") or e.get("byZone"))]
    if not flows:
        return []
    stopped = [k for k, (c, m) in enumerate(zip(running, mult)) if c == 0 and m > 0]
    if not stopped:
        return []
    h = hours[stopped[0]]
    return [_p(name, f"/loads/{i}", "load.while_stopped",
               f"{len(stopped)} hour(s) carry {', '.join(flows)} while the node runs 0 (first {h['date']} "
               f"{h['hour']:02d}:00)", "warning", fn="check_stopped", node=node_id, quantity=flows[0],
               hour=f"{h['date']}T{h['hour']:02d}")]


def normalize(name: str, doc: dict, model: dict) -> tuple[dict, list[dict]]:
    """Passes 2 and 3: the scenario as the cost reads it, and the warnings."""
    env, problems = environment_of(name, doc, model)
    hours = month_hours(doc)
    nodes = {n["id"]: n for n in model["nodes"]}
    rows, found = assign_rows(name, doc, env, model)
    problems += found
    out_rows = []
    for nid, (i, row) in rows.items():
        node = nodes[nid]
        problems += check_against_rule(name, i, row, node)
        rule = RULES.lookup(node)
        hourly = bool(rule and rule.hourly)
        sch = doc.get("schedules", {}).get(row.get("schedule")) if row.get("schedule") else None
        mult = [day_shape(doc, h, row.get("profile")) * row.get("multiplier", 1.0) for h in hours]
        qs = normalize_quantities(row.get("quantities", {}))
        count = count_hours(row, sch, node, hours, hourly)
        auto, vert = scaling_hours(row, sch, hours) if hourly else (None, None)
        running = count if count is not None else (auto["maxByHour"] if auto else None)
        problems += check_stopped(name, i, nid, qs, mult, running, hours)
        region, region_from = region_of(node, doc)
        out_rows.append({"node": nid, "row": i, "rule": rule.id if rule else None, "hourly": hourly,
                         "region": region, "regionFrom": region_from, "schedule": row.get("schedule"),
                         "profile": row.get("profile"), "quantities": qs, "multiplier": mult, "count": count,
                         "autoscale": auto, "vertical": vert})
    edges, found = resolve_edges(name, doc, env, model)
    problems += found
    out_edges = [{"edge": e.get("id"), "from": e["from"], "to": e["to"], "row": i, "crossProvider": e["crossProvider"],
                  "quantities": normalize_quantities(row.get("quantities", {})),
                  "multiplier": [day_shape(doc, h, row.get("profile")) * row.get("multiplier", 1.0) for h in hours]}
                 for i, row, e in edges]
    scenario = {"id": doc["id"], "label": doc.get("label", doc["id"]), "file": name, "environment": env,
                "month": doc["month"], "timezone": doc.get("timezone", "UTC"), "currency": "USD",
                "hours": hours, "loads": out_rows, "edges": out_edges}
    return scenario, problems


# ---------------------------------------------------------------- the room's load definitions

def read(root: Path) -> dict:
    """Every load definition of the room against its model: {ok, dir, files, scenarios, problems}, or {ok: False,
    reason, message} when the model or the folder cannot be read. Blocking: call it off the event loop."""
    root = Path(root)
    model = R.read(root)
    if not model.get("ok"):
        return {"ok": False, "reason": model.get("reason", "invalid"), "message": "the infra model cannot be read: "
                + model.get("message", ""), "problems": model.get("problems", [])}
    try:
        folder = R.side_dir(root, "load_dir")
        files, problems = R.read_json_folder(root, folder)
    except R.Refused as r:
        return {"ok": False, "reason": r.reason, "message": r.message, "problems": []}
    scenarios, used, ids = [], [], {}
    for name, raw in files:
        doc, found = check_file(name, raw)
        problems += found
        if doc is None:
            continue
        if doc["id"] in ids:
            problems.append(_p(name, "/id", "id.duplicate", f"scenario id is already used in {ids[doc['id']]}",
                               fn="read"))
            continue
        ids[doc["id"]] = name
        scenario, found = normalize(name, doc, model)
        problems += found
        scenarios.append(scenario)
        used.append(name)
    return {"ok": True, "dir": folder, "files": used, "scenarios": scenarios, "problems": problems}
