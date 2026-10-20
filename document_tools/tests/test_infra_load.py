"""The cost simulator's load definitions and price files (infra/load.py, infra/prices.py, plan
docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-A): the schema walked from its own file, the three
passes, the normalized hours, node.region, the pricing rules' registry, check builtin:infra-load and seed keeping the
declared ids.

A room for a test is aws-three-tier's model (tests/fixtures/infra) copied into tmp_path with the load definitions the
test writes; the examples make_examples.py writes there must be valid as they are.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jsonui_doc_cli.check import infra_check as C
from jsonui_doc_cli.check.report import report_path_for
from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import prices as P
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra import rules as RULES
from jsonui_doc_cli.infra import seed as S
from jsonui_doc_cli.infra.rules import Rule

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"
TOOLS = Path(__file__).resolve().parents[1]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
ALL_DAYS = WEEKDAYS + ["sat", "sun"]


def _room(tmp_path: Path, loads: dict | None = None, prices: dict | None = None, config: dict | None = None) -> Path:
    """aws-three-tier's model in tmp_path/room, and the given files: {name: object or text} under docs/infra/load and
    docs/infra/prices (or the folders config names)."""
    root = tmp_path / "room"
    shutil.copytree(FIX / "aws-three-tier" / "docs" / "infra", root / "docs" / "infra",
                    ignore=shutil.ignore_patterns("load", "prices"))
    if config is not None:
        (root / "jui.config.json").write_text(json.dumps(config))
    for folder, files in (((config or {}).get("infra", {}).get("load_dir", "docs/infra/load"), loads),
                          ((config or {}).get("infra", {}).get("prices_dir", "docs/infra/prices"), prices)):
        for name, data in (files or {}).items():
            path = root / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
    return root


def _scenario(**extra) -> dict:
    return {"version": 0, "id": "s", "month": "2026-11", "environment": "production", **extra}


def _codes(result: dict, severity: str | None = None) -> list[str]:
    return [p["code"] for p in result["problems"] if severity is None or p["severity"] == severity]


def _one(tmp_path, doc, **kw) -> dict:
    return L.read(_room(tmp_path, {"s.json": doc}, **kw))


def _row(result: dict, node: str) -> dict:
    return next(r for r in result["scenarios"][0]["loads"] if r["node"] == node)


# ---------------------------------------------------------------- the schema, walked from its own file

def test_the_schema_walker_reads_the_new_words_and_the_model_is_unchanged():
    root = L.schema()
    # type number, exclusiveMinimum, a list of types, a table by name (propertyNames, additionalProperties a schema)
    assert M.check_schema(0.5, {"type": "number", "exclusiveMinimum": 0}, root=root) == []
    assert M.check_schema(0, {"type": "number", "exclusiveMinimum": 0}, root=root)
    assert M.check_schema(True, {"type": "number"}, root=root)                    # a boolean is no number
    assert M.check_schema(float("nan"), {"type": "number"}, root=root)
    assert M.check_schema(3, {"$ref": "#/$defs/flow"}, root=root) == []
    assert M.check_schema({"amount": 3, "per": "second"}, {"$ref": "#/$defs/flow"}, root=root) == []
    assert M.check_schema("3", {"$ref": "#/$defs/flow"}, root=root)
    assert M.check_schema({"Bad Name": {"hourly": [1] * 24}}, root["properties"]["profiles"], root=root)
    assert M.check_schema({"day": {"hourly": [1] * 23}}, root["properties"]["profiles"], "/profiles", root)[0][0] \
        == "/profiles/<key>/hourly"                                               # a name is masked in a path
    # the model's schema reads as before: a word it does not have is still refused with its own message
    assert M.check_schema({"version": 0, "x": 1}) == [("/<key>", "is not a field of the infra model v0")]
    assert ("/x", "is not a field of the infra load v0") not in M.check_schema(_scenario(x=1), root=root)
    assert M.check_schema(_scenario(x=1), root=root) == [("/<key>", "is not a field of the infra load v0")]


def test_the_quantities_are_closed_with_one_unit_each_and_the_price_units_hold_them():
    q = L.quantities()
    assert {"requests", "read_units", "get_requests", "rows_read", "storage_gb", "cdn_egress_gb", "lcu"} <= set(q)
    assert "reads" not in q and "writes" not in q          # one name, one unit (cd 21:0x)
    assert q["storage_gb"]["unit"] == "GB" and q["storage_gb"]["kind"] == "level"
    assert q["requests"]["label"] == "リクエスト"
    assert {v["unit"] for v in q.values()} <= set(P.units())
    assert L.per_hours()["second"] == pytest.approx(1 / 3600) and L.per_hours()["month"] == 730
    for rule in RULES.REGISTRY:          # every rule reads only quantities of the vocabulary
        assert set(rule.reads) <= set(q), rule.id


# ---------------------------------------------------------------- the examples

def test_the_examples_are_valid():
    got = L.read(FIX / "aws-three-tier")
    assert got["ok"] and got["files"] == ["ordinary.json", "sale.json"]
    assert _codes(got, "error") == []
    assert [s["id"] for s in got["scenarios"]] == ["ordinary", "sale"]
    pr = P.read(FIX / "aws-three-tier")
    assert pr["ok"] and len(pr["prices"]) == 5 and pr["problems"] == []
    # the model still does not take the load and prices folders for model files
    assert R.read(FIX / "aws-three-tier")["files"] == ["external.json", "main.json"]


# ---------------------------------------------------------------- pass 1: one file

@pytest.mark.parametrize("raw,code", [
    ("{", "json"),
    (json.dumps(_scenario(month="2026-13")), "schema"),
    (json.dumps(_scenario(label="db at 10.0.1.23")), "secret.ip_address"),
    (json.dumps(_scenario(timezone="Mars/Olympus")), "load.timezone"),
    (json.dumps(_scenario(days=[{"date": "2026-12-01"}])), "load.date"),
    (json.dumps(_scenario(days=[{"date": "2026-11-31"}])), "load.date"),
    (json.dumps(_scenario(days=[{"date": "2026-11-02"}, {"date": "2026-11-02"}])), "load.date"),
    (json.dumps(_scenario(week={"mon": "nope"})), "load.ref"),
    (json.dumps(_scenario(loads=[{"node": "cdn", "schedule": "nope"}])), "load.ref"),
    (json.dumps(_scenario(schedules={"x": {"rules": [{"days": ["mon"], "from": "10:00", "to": "09:00", "count": 1}]}})), "load.rule"),
    (json.dumps(_scenario(schedules={"x": {"rules": [{"days": ["mon"], "from": "09:00", "to": "10:00", "min": 3, "max": 2}]}})), "load.minmax"),
    (json.dumps(_scenario(loads=[{"node": "api-prod", "nodes": {"category": "cache"}}])), "load.target"),
    (json.dumps(_scenario(loads=[{}])), "load.target"),
    (json.dumps(_scenario(edges=[{"edge": "e", "from": "a", "to": "b"}])), "load.target"),
    (json.dumps(_scenario(edges=[{"from": "a"}])), "load.target"),
])
def test_one_file_is_refused_whole_for(tmp_path, raw, code):
    got = _one(tmp_path, raw)
    assert got["ok"] and got["scenarios"] == [] and code in _codes(got, "error"), got["problems"]


def _auto(**a) -> dict:
    return {"min": 1, "max": 4, "per_instance": {"quantity": "requests", "amount": 50}, **a}


LADDER = [{"sku": "a.large", "amount": 100}, {"sku": "a.xlarge", "amount": 200}]


@pytest.mark.parametrize("row,schedules,code", [
    ({"autoscale": _auto(min=5)}, None, "load.minmax"),
    ({"autoscale": _auto(), "schedule": "x"}, {"x": {"rules": [{"days": ["mon"], "from": "00:00", "to": "01:00", "min": 6}]}}, "load.minmax"),
    ({"autoscale": {"min": 1, "max": 2}}, None, "load.autoscale"),                                   # no per_instance
    ({"autoscale": _auto(per_instance={"quantity": "storage_gb", "amount": 1})}, None, "load.autoscale"),  # not a flow
    ({"autoscale": _auto(per_instance={"quantity": "messages", "amount": 1})}, None, "load.autoscale"),    # not written
    ({"vertical": {"quantity": "requests", "ladder": [LADDER[0], LADDER[0]]}}, None, "load.ladder"),
    ({"vertical": {"quantity": "requests", "ladder": [LADDER[1], LADDER[0]]}}, None, "load.ladder"),
    ({"vertical": {"quantity": "requests", "ladder": LADDER, "min": "z.small"}}, None, "load.ladder"),
    ({"vertical": {"quantity": "requests", "ladder": LADDER, "min": "a.xlarge", "max": "a.large"}}, None, "load.minmax"),
    ({"vertical": {"ladder": LADDER}}, None, "load.ladder"),                                          # no quantity
    ({"vertical": {"quantity": "requests", "ladder": [{"sku": "a.large"}]}}, None, "load.ladder"),    # no size at all
    ({"vertical": {"quantity": "requests", "ladder": [{"sku": "a", "vcpu": 2, "memory_gb": 8}, {"sku": "b", "vcpu": 4, "memory_gb": 4}]}}, None, "load.ladder"),
    ({"vertical": {"quantity": "requests", "ladder": LADDER}, "schedule": "x"},
     {"x": {"rules": [{"days": ["mon"], "from": "00:00", "to": "01:00", "sku": "z.small"}]}}, "load.ladder"),
    ({"vertical": {"quantity": "requests", "ladder": LADDER}, "autoscale": _auto(per_instance={"quantity": "messages", "amount": 1})},
     None, "load.autoscale"),
])
def test_scaling_that_contradicts_itself_is_an_error(tmp_path, row, schedules, code):
    row = {"node": "api-prod", "quantities": {"requests": 100}, **row}
    doc = _scenario(loads=[row], **({"schedules": schedules} if schedules else {}))
    got = _one(tmp_path, doc)
    assert code in _codes(got, "error"), got["problems"]


def test_scaling_written_well_passes(tmp_path):
    doc = _scenario(schedules={"x": {"rules": [{"days": WEEKDAYS, "from": "08:00", "to": "20:00", "min": 2, "max": 8, "sku": "a.xlarge"}]}},
                    loads=[{"node": "api-prod", "schedule": "x", "quantities": {"requests": {"amount": 100, "per": "second"}},
                            "autoscale": {"min": 1, "max": 4}, "vertical": {"quantity": "requests", "ladder": LADDER}}])
    got = _one(tmp_path, doc)
    assert _codes(got, "error") == [], got["problems"]


def test_a_scenario_id_twice_leaves_the_later_file_out(tmp_path):
    got = L.read(_room(tmp_path, {"a.json": _scenario(), "b.json": _scenario()}))
    assert [s["file"] for s in got["scenarios"]] == ["a.json"] and "id.duplicate" in _codes(got, "error")


# ---------------------------------------------------------------- pass 2: against the model

@pytest.mark.parametrize("doc,code", [
    (_scenario(loads=[{"node": "no-such-node", "quantities": {"requests": 1}}]), "load.node_missing"),
    (_scenario(loads=[{"node": "api-stg", "quantities": {"requests": 1}}]), "load.not_in_environment"),
    (_scenario(loads=[{"nodes": {"category": "cache"}, "quantities": {"requests": 1}}]), "load.select_none"),
    (_scenario(loads=[{"node": "cdn", "quantities": {"storage_gb": 1}}]), "load.quantity_unused"),
    (_scenario(schedules={"x": {"default": 1}}, loads=[{"node": "cdn", "schedule": "x"}]), "load.schedule_unused"),
    (_scenario(edges=[{"from": "cdn", "to": "db-prod", "quantities": {"transfer_gb": 1}}]), "load.edge_missing"),
    ({k: v for k, v in _scenario().items() if k != "environment"}, "load.environment"),
    (_scenario(environment="nope"), "load.environment"),
])
def test_a_row_that_does_not_meet_the_model_is_a_warning_and_left_out(tmp_path, doc, code):
    got = _one(tmp_path, doc)
    assert got["scenarios"] and code in _codes(got, "warning") and _codes(got, "error") == [], got["problems"]
    p = next(p for p in got["problems"] if p["code"] == code)
    assert p["fn"]                                         # each problem names the function that found it
    if code in ("load.node_missing", "load.not_in_environment"):
        assert p["node"] and got["scenarios"][0]["loads"] == []


def test_a_nodes_own_row_beats_a_selectors_and_the_later_wins_among_equals(tmp_path):
    doc = _scenario(loads=[{"node": "api-prod", "quantities": {"requests": 1}},
                           {"nodes": {"category": "compute.container"}, "quantities": {"requests": 2}},
                           {"node": "db-prod", "quantities": {"storage_gb": 1}},
                           {"node": "db-prod", "quantities": {"storage_gb": 2}}])
    got = _one(tmp_path, doc)
    assert _row(got, "api-prod")["quantities"]["requests"]["perHour"] == 1
    assert _row(got, "db-prod")["quantities"]["storage_gb"]["value"] == 2
    assert _codes(got, "warning").count("load.overlap") == 2


def test_a_flow_while_the_node_is_stopped_is_a_warning_with_its_hours(tmp_path):
    doc = _scenario(schedules={"night": {"default": 1, "rules": [{"days": ALL_DAYS, "from": "01:00", "to": "06:00", "count": 0}]}},
                    loads=[{"node": "api-prod", "schedule": "night", "quantities": {"requests": 10}}])
    got = _one(tmp_path, doc)
    p = next(p for p in got["problems"] if p["code"] == "load.while_stopped")
    assert p["severity"] == "warning" and p["node"] == "api-prod" and p["quantity"] == "requests"
    assert p["message"].startswith("150 hour(s)") and p["hour"] == "2026-11-01T01"


# ---------------------------------------------------------------- pass 3: normalized

def test_the_months_hours_days_of_the_week_and_holidays(tmp_path):
    got = _one(tmp_path, _scenario(holidays=["2026-11-03"]))
    hours = got["scenarios"][0]["hours"]
    assert len(hours) == 720 and hours[0] == {"date": "2026-11-01", "hour": 0, "dow": "sun", "holiday": False}
    assert all(h["holiday"] for h in hours if h["date"] == "2026-11-03")
    assert len(L.month_hours({"month": "2026-10"})) == 744 and len(L.month_hours({"month": "2028-02"})) == 29 * 24


def test_the_multiplier_from_the_week_the_date_and_the_row():
    doc = {"month": "2026-11", "profiles": {"a": {"hourly": [2.0] * 24}, "b": {"hourly": [3.0] * 24}},
           "week": {"sun": "a"}, "days": [{"date": "2026-11-27", "multiplier": 5}, {"date": "2026-11-08", "profile": "b"}]}
    hours = {(h["date"], h["hour"]): h for h in L.month_hours(doc)}
    assert L.day_shape(doc, hours[("2026-11-01", 0)], None) == 2.0       # sunday's profile
    assert L.day_shape(doc, hours[("2026-11-02", 0)], None) == 1.0       # monday: none
    assert L.day_shape(doc, hours[("2026-11-27", 0)], None) == 5.0       # the date's multiplier
    assert L.day_shape(doc, hours[("2026-11-08", 0)], None) == 3.0       # the date's profile beats the week's
    assert L.day_shape(doc, hours[("2026-11-08", 0)], "a") == 2.0        # the row's beats both


def test_a_schedule_hour_by_hour():
    hours = {(h["date"], h["hour"]): h for h in L.month_hours({"month": "2026-11", "holidays": ["2026-11-03"]})}
    sch = {"default": 1, "rules": [{"days": WEEKDAYS, "from": "09:30", "to": "18:00", "count": 3, "min": 2, "max": 9}]}
    assert L.schedule_hour(sch, hours[("2026-11-02", 9)])["count"] == 2.0      # half the hour at 3, half at 1
    assert L.schedule_hour(sch, hours[("2026-11-02", 10)]) == {"count": 3.0, "min": 2, "max": 9, "fixed": 3}
    assert L.schedule_hour(sch, hours[("2026-11-01", 10)]) == {"count": 1.0}   # sunday
    assert L.schedule_hour(sch, hours[("2026-11-03", 10)])["count"] == 3.0     # a holiday as it is (as-is)
    assert L.schedule_hour(dict(sch, holidays="off"), hours[("2026-11-03", 10)])["count"] == 0
    assert L.schedule_hour(dict(sch, holidays="weekend"), hours[("2026-11-03", 10)])["count"] == 1.0
    hol = {"default": 1, "rules": [{"days": ["holiday"], "from": "00:00", "to": "24:00", "count": 0}]}
    assert L.schedule_hour(hol, hours[("2026-11-03", 23)])["count"] == 0 and L.schedule_hour(hol, hours[("2026-11-04", 23)])["count"] == 1


def test_two_rules_each_covering_half_an_hour_count_the_same_in_either_order():
    """サポート7's verification of L-A: 8:00-9:30 at 2 and 9:30-18:00 at 4 is 3.0 instance-hours at 9, whatever the order."""
    hour = next(h for h in L.month_hours({"month": "2026-11"}) if h["date"] == "2026-11-02" and h["hour"] == 9)
    a = {"days": WEEKDAYS, "from": "08:00", "to": "09:30", "count": 2}
    b = {"days": WEEKDAYS, "from": "09:30", "to": "18:00", "count": 4}
    assert L.schedule_hour({"default": 1, "rules": [a, b]}, hour)["count"] == 3.0
    assert L.schedule_hour({"default": 1, "rules": [b, a]}, hour)["count"] == 3.0
    # a rule over exactly half the hour gives that hour its min and max (and sku); the half it does not cover keeps none
    half = {"default": 1, "rules": [{"days": WEEKDAYS, "from": "09:00", "to": "09:30", "min": 3, "max": 6, "sku": "a.xlarge"}]}
    assert L.schedule_hour(half, hour) == {"count": 1.0, "min": 3, "max": 6, "sku": "a.xlarge"}
    late = {"default": 1, "rules": [{"days": WEEKDAYS, "from": "09:30", "to": "10:00", "min": 3}]}
    assert L.schedule_hour(late, hour) == {"count": 1.0, "min": 3}
    assert L.schedule_hour(late, dict(hour, hour=10)) == {"count": 1.0}
    # the halves differ: the second's (the hour ends in it)
    both = {"default": 1, "rules": [{"days": WEEKDAYS, "from": "09:00", "to": "09:30", "max": 6},
                                    {"days": WEEKDAYS, "from": "09:30", "to": "10:00", "max": 8}]}
    assert L.schedule_hour(both, hour)["max"] == 8


def test_quantities_per_hour_with_the_per_they_were_written_in(tmp_path):
    doc = _scenario(loads=[{"node": "cdn", "quantities": {"requests": {"amount": 100, "per": "second"},
                                                          "cdn_egress_gb": {"by_zone": {"japan": 24}, "per": "day"}}},
                           {"node": "assets", "quantities": {"get_requests": 7, "storage_gb": 500}}])
    got = _one(tmp_path, doc)
    cdn, assets = _row(got, "cdn")["quantities"], _row(got, "assets")["quantities"]
    assert cdn["requests"] == {"unit": "request", "kind": "flow", "label": "リクエスト", "perHour": pytest.approx(360000), "per": "second"}
    assert cdn["cdn_egress_gb"]["byZone"] == {"japan": 1.0} and cdn["cdn_egress_gb"]["per"] == "day"
    assert assets["get_requests"]["perHour"] == 7 and assets["get_requests"]["per"] == "hour"
    assert assets["storage_gb"] == {"unit": "GB", "kind": "level", "label": "保存量", "value": 500.0}
    assert "put_requests" not in assets                  # not written: undefined, not 0


def test_count_autoscale_and_vertical_by_hour(tmp_path):
    doc = _scenario(schedules={"day": {"default": 1, "rules": [
        {"days": WEEKDAYS, "from": "08:00", "to": "20:00", "min": 3, "max": 9, "sku": "a.xlarge"},
        {"days": ALL_DAYS, "from": "02:00", "to": "03:00", "count": 2}]}},
        loads=[{"node": "api-prod", "schedule": "day", "quantities": {"requests": 100},
                "autoscale": {"min": 1, "max": 4}, "vertical": {"quantity": "requests", "ladder": LADDER}},
               {"node": "db-prod", "schedule": "day", "quantities": {"requests": 1},
                "vertical": {"quantity": "requests", "ladder": LADDER, "order": "vertical_first"}},
               {"node": "alb-prod", "quantities": {"lcu": 1}}, {"node": "cdn", "quantities": {"requests": 1}}])
    got = _one(tmp_path, doc)
    api, db = _row(got, "api-prod"), _row(got, "db-prod")
    mon10, mon2, sun10 = 24 + 10, 24 + 2, 10                 # 11-01 is a sunday, 11-02 a monday
    assert (api["autoscale"]["minByHour"][mon10], api["autoscale"]["maxByHour"][mon10]) == (3, 9)
    assert (api["autoscale"]["minByHour"][sun10], api["autoscale"]["maxByHour"][sun10]) == (1, 4)
    assert (api["autoscale"]["minByHour"][mon2], api["autoscale"]["maxByHour"][mon2]) == (2, 2)   # a fixed count
    assert api["count"] is None                              # autoscale: counted by the cost (L-B)
    assert api["vertical"]["minByHour"][mon10] == api["vertical"]["maxByHour"][mon10] == "a.xlarge"   # schedule_vertical
    assert (api["vertical"]["minByHour"][sun10], api["vertical"]["maxByHour"][sun10]) == ("a.large", "a.xlarge")
    assert (db["vertical"]["minByHour"][mon10], db["vertical"]["maxByHour"][mon10]) == ("a.xlarge", "a.xlarge")
    assert db["vertical"]["change_delay_min"] == 60 and db["count"][mon2] == 2.0 and db["count"][sun10] == 1.0
    assert _row(got, "alb-prod")["count"] == [1.0] * 720     # no schedule: the model's count, all the time
    assert _row(got, "cdn")["count"] is None and _row(got, "cdn")["hourly"] is False   # billed by use


def test_the_region_from_the_node_its_group_or_the_scenario(tmp_path):
    doc = _scenario(defaults={"region": "us-east-1"},
                    loads=[{"node": "assets", "quantities": {"storage_gb": 1}}, {"node": "db-prod", "quantities": {"storage_gb": 1}},
                           {"node": "cdn", "quantities": {"requests": 1}}])
    got = _one(tmp_path, doc)
    assert [(r["region"], r["regionFrom"]) for r in (_row(got, n) for n in ("assets", "db-prod", "cdn"))] == [
        ("ap-northeast-1", "node"), ("ap-northeast-1", "group"), ("us-east-1", "defaults")]
    got = _one(tmp_path / "2", _scenario(loads=[{"node": "cdn", "quantities": {"requests": 1}}]))
    assert (_row(got, "cdn")["region"], _row(got, "cdn")["regionFrom"]) == ("", "")


def test_region_resolved_follows_the_groups_up_to_a_logical_one():
    doc = {"version": 0, "groups": [{"id": "acct", "kind": "account", "provider": "aws"},
                                    {"id": "r", "kind": "region", "region": "eu-west-1", "parent": "acct"},
                                    {"id": "net", "kind": "network", "parent": "r"},
                                    {"id": "prod", "kind": "logical", "parent": "r"}],
           "nodes": [{"id": "a", "category": "cache", "group": "net"}, {"id": "b", "category": "cache", "group": "net", "region": "eu-north-1"},
                     {"id": "c", "category": "cache", "group": "prod"}, {"id": "d", "category": "cache"}]}
    model, problems = M.merge([("m.json", json.dumps(doc).encode())])
    assert M.errors(problems) == []
    assert {n["id"]: n["regionResolved"] for n in model["nodes"]} == {"a": "eu-west-1", "b": "eu-north-1", "c": "", "d": ""}


# ---------------------------------------------------------------- the pricing rules' registry

def test_the_most_specific_rule_wins_and_a_rule_is_replaced_by_its_id():
    saved = list(RULES.REGISTRY)
    try:
        node = {"category": "compute.function", "providerResolved": "aws", "service": "lambda.edge"}
        assert RULES.lookup(node).id == "generic/compute.function"
        RULES.register(Rule(id="aws/functions", category="compute.function", provider="aws", reads=("requests",)))
        assert RULES.lookup(node).id == "aws/functions"
        RULES.register(Rule(id="aws/lambda", category="compute.function", provider="aws", service="lambda", reads=("requests",)))
        assert RULES.lookup(node).id == "aws/lambda"           # "lambda" is the head of "lambda.edge"
        RULES.register(Rule(id="aws/lambda", category="compute.function", provider="aws", service="lambda", reads=()))
        assert [r.id for r in RULES.REGISTRY].count("aws/lambda") == 1 and RULES.lookup(node).reads == ()
        assert RULES.lookup({"category": "no.such"}) is None
    finally:
        RULES.REGISTRY[:] = saved


# ---------------------------------------------------------------- the price files

PRICE = {"provider": "aws", "service": "s3", "sku": "get", "region": "ap-northeast-1", "unit": "request",
         "price_usd": 0.0004, "effective": "2026-10-01", "source": "manual"}


@pytest.mark.parametrize("change,why", [
    ({"tiers": [{"from": 0, "price_usd": 1}]}, "exactly one of price_usd and tiers"),
    ({"price_usd": None}, "exactly one"),
    ({"price_usd": None, "tiers": [{"from": 1, "price_usd": 1}]}, "does not start at 0"),
    ({"price_usd": None, "tiers": [{"from": 0, "to": 10, "price_usd": 1}, {"from": 11, "price_usd": 1}]}, "does not start where"),
    ({"price_usd": None, "tiers": [{"from": 0, "price_usd": 1}, {"from": 10, "price_usd": 1}]}, "no end but is not the last"),
    ({"price_usd": None, "tiers": [{"from": 0, "to": 10, "price_usd": 1}, {"from": 10, "to": 5, "price_usd": 1}]}, "ends at or before"),
    ({"effective": "2026-02-30"}, "not a date"),
])
def test_a_price_row_that_cannot_be_used_is_left_out_with_a_warning(tmp_path, change, why):
    row = {k: v for k, v in {**PRICE, **change}.items() if v is not None}
    got = P.read(_room(tmp_path, prices={"p.json": {"version": 0, "prices": [row, dict(PRICE, sku="put")]}}))
    assert [r["sku"] for r in got["prices"]] == ["put"]
    p = got["problems"][0]
    assert p["code"] == "prices.row" and p["severity"] == "warning" and why in p["message"]


def test_prices_trace_their_row_a_duplicate_is_dropped_and_a_bad_file_is_out_whole(tmp_path):
    got = P.read(_room(tmp_path, prices={"a.json": {"version": 0, "prices": [PRICE, dict(PRICE, price_usd=1)]},
                                         "b.json": {"version": 0, "prices": [dict(PRICE, unit="furlong")]},
                                         "c.json": {"version": 0, "prices": [dict(PRICE, note="AKIAABCDEFGHIJKLMNOP")]}}))
    assert [(r["file"], r["index"], r["price_usd"], r["per_units"]) for r in got["prices"]] == [("a.json", 0, 0.0004, 1)]
    assert sorted(_codes(got)) == ["prices.duplicate", "schema", "secret.access_key"] and got["files"] == ["a.json"]


# ---------------------------------------------------------------- the folders

def test_the_folders_follow_infra_dir_or_their_own_settings(tmp_path):
    a = tmp_path / "a"
    (a).mkdir()
    (a / "jui.config.json").write_text(json.dumps({"infra": {"dir": "infra/model"}}))
    assert (R.side_dir(a, "load_dir"), R.side_dir(a, "prices_dir")) == ("infra/model/load", "infra/model/prices")
    (a / "jui.config.json").write_text(json.dumps({"infra": {"load_dir": "sim/load", "prices_dir": "sim/prices"}}))
    assert (R.side_dir(a, "load_dir"), R.side_dir(a, "prices_dir")) == ("sim/load", "sim/prices")
    for bad in ("../x", "/abs", "https://x", ""):
        (a / "jui.config.json").write_text(json.dumps({"infra": {"load_dir": bad}}))
        with pytest.raises(R.Refused):
            R.side_dir(a, "load_dir")
    root = _room(tmp_path, {"s.json": _scenario()}, config={"infra": {"load_dir": "sim/load"}})
    assert L.read(root)["files"] == ["s.json"]
    (root / "jui.config.json").write_text(json.dumps({"infra": {"load_dir": "../out"}}))
    assert L.read(root)["reason"] == "bad_config"


# ---------------------------------------------------------------- check builtin:infra-load

def _decl(gate=False):
    return SimpleNamespace(name="load", type="builtin:infra-load", gate=gate)


def test_check_says_ok_undefined_and_missing(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(loads=[{"node": "cdn", "quantities": {"requests": 1}},
                                                       {"node": "gone", "quantities": {"requests": 1}}])})
    rep = C.run_infra_load(_decl(), root)
    by = {r.target: r for r in rep.results}
    assert by["load/s/cdn"].status == "ok"
    assert by["load/s/gone"].status == "warning" and "does not have" in by["load/s/gone"].message
    assert by["load/s/assets"].status == "warning" and "undefined" in by["load/s/assets"].message   # billed by use
    assert by["load/s/db-prod"].status == "ok" and "the model's count" in by["load/s/db-prod"].message   # by the hour
    assert by["load/s/stripe"].status == "skipped"
    assert "load/s/api-stg" not in by                       # another environment
    gated = {r.target: r.status for r in C.run_infra_load(_decl(gate=True), root).results}
    assert gated["load/s/gone"] == "missing_in_impl" and gated["load/s/assets"] == "missing_in_doc"
    assert report_path_for("infra", "infra-load", root) == root / "docs/infra/load/.check-report.infra-load.json"


def test_check_refuses_load_definitions_with_errors(tmp_path):
    with pytest.raises(C.InfraCheckError):
        C.run_infra_load(_decl(), _room(tmp_path, {"s.json": "{"}))


# ---------------------------------------------------------------- the commands

def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", *args], cwd=TOOLS, capture_output=True, text=True)


def test_the_validate_commands_exit_0_1_2(tmp_path):
    assert _cli("validate", "infra-load", str(FIX / "aws-three-tier")).returncode == 0
    assert _cli("validate", "infra-prices", str(FIX / "aws-three-tier")).returncode == 0
    bad = _cli("validate", "infra-load", str(_room(tmp_path, {"s.json": _scenario(month="x")})))
    assert bad.returncode == 1 and "[schema" in bad.stdout
    assert _cli("validate", "infra-load", str(tmp_path / "nothing")).returncode == 2
    out = json.loads(_cli("validate", "infra-load", "--json", str(FIX / "aws-three-tier")).stdout)
    assert [s["hours"] for s in out["scenarios"]] == [720, 720]


# ---------------------------------------------------------------- seed keeps the declared ids

TF = '''provider "google" {}
resource "google_redis_instance" "cache" {
  name = "cache"
  region = "asia-northeast1"
}
resource "google_sql_database_instance" "db" {
  name = "db"
  region = "asia-northeast1"
}
resource "google_storage_bucket" "redis" {
  name = "assets"
  location = "ASIA"
}
'''


def _seeded(root: Path) -> dict:
    doc, _rep = S.draft(root)
    return {tuple(n.get("iac") or []): n for n in doc["nodes"]}


def test_a_name_drafted_first_never_takes_a_declared_id():
    """サポート7's verification of L-A: another node named "web" drafted before the declared one does not take its id."""
    d = S.Draft(Path("."), declared=[("aws_instance.b", "web")])
    assert d.new_id("web") == "web-2"
    assert d.declared_id("aws_instance.b") == "web"
    assert d.declared_id("aws_instance.b") is None          # taken now: a second resource at the address gets a new one


def test_seed_keeps_a_declared_nodes_id_and_reads_its_region(tmp_path):
    root = tmp_path / "p"
    (root / "infra").mkdir(parents=True)
    (root / "infra" / "main.tf").write_text(TF)
    first = _seeded(root)
    cache = next(n for k, n in first.items() if "google_redis_instance.cache" in k)
    assert cache["region"] == "asia-northeast1"
    assert "region" not in next(n for k, n in first.items() if "google_storage_bucket.redis" in k)   # "ASIA" is no region
    # the room declares the cache under the id seed gave the bucket: the cache keeps it, the bucket takes another
    taken = next(n for k, n in first.items() if "google_storage_bucket.redis" in k)["id"]
    decl = {"version": 0, "nodes": [{"id": taken, "category": "cache", "provider": "gcp",
                                     "iac": ["google_redis_instance.cache"]}]}
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "m.json").write_text(json.dumps(decl))
    again = _seeded(root)
    assert next(n for k, n in again.items() if "google_redis_instance.cache" in k)["id"] == taken
    assert next(n for k, n in again.items() if "google_storage_bucket.redis" in k)["id"] != taken
    assert M.errors(M.check_file("draft.json", json.dumps(S.draft(root)[0]).encode())[1]) == []
