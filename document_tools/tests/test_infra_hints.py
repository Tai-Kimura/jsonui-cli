"""Hints where a writer's room silently means something else (ticket 2026-10-21-agents-skills-mcp-for-server-room §2,
§3a-4): rows that never count (load.overlap says one row applies to a node), Multi-AZ written where the cost does not
read it (spec.ha, load.sku.multi_az), and a room's price row that drops a bundled free amount (prices.free_dropped).
Each is a warning; each was in a consumer's draft."""
from __future__ import annotations

import json

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra.cost import pricebook as PB
from test_infra_load import FIX, _room, _scenario

NO_CACHE = {"JUI_VIZ_HOME": "/nonexistent"}


def _problems(result: dict, code: str) -> list[dict]:
    return [p for p in result["problems"] if p["code"] == code]


# ---------------------------------------------------------------- one row applies to a node

def test_a_second_row_for_a_node_says_the_first_counts_for_nothing(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(loads=[{"node": "api-prod", "quantities": {"requests": 1}},
                                                       {"node": "api-prod", "quantities": {"egress_gb": 1}}])})
    [p] = _problems(L.read(root), "load.overlap")
    assert p["severity"] == "warning" and "row 0 counts for nothing" in p["message"]
    assert "one row applies to a node: put all of the node's quantities in one row" in p["message"]


def test_a_selector_row_after_a_node_s_own_row_says_the_own_one_wins(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(loads=[{"node": "api-prod", "quantities": {"requests": 1}},
                                                       {"nodes": {"category": "compute.container"},
                                                        "quantities": {"requests": 2}}])})
    msgs = [p["message"] for p in _problems(L.read(root), "load.overlap")]
    assert msgs and all("one row applies to a node, and a node's own row beats a selector's" in m for m in msgs)


# ---------------------------------------------------------------- Multi-AZ where the cost reads it

def _node(**extra) -> dict:
    return {"id": "db", "category": "database.relational", "provider": "aws", "service": "rds", **extra}


def _spec_ha(**extra) -> list[dict]:
    _model, problems = M.merge([("m.json", json.dumps({"version": 0, "nodes": [_node(**extra)]}).encode())])
    return [p for p in problems if p["code"] == "spec.ha"]


@pytest.mark.parametrize("spec", [
    [{"key": "multi_az", "value": "有り"}],                       # the draft that came out single-AZ
    [{"key": "multiaz", "value": "true"}],
    [{"key": "deployment", "value": "マルチ AZ"}],
    [{"key": "deployment", "value": "Multi-AZ (2 instances)"}],
])
def test_a_spec_that_says_multi_az_without_ha_is_a_warning(spec):
    [p] = _spec_ha(spec=spec)
    assert p["severity"] == "warning" and "write ha: multi-az" in p["message"] and p["path"].startswith("/nodes/0/spec/")


@pytest.mark.parametrize("extra", [
    {"spec": [{"key": "multi_az", "value": "true"}], "ha": "multi-az"},   # said both ways: fine
    {"spec": [{"key": "multi_az", "value": "無し"}]},                      # says no
    {"spec": [{"key": "multi_az", "value": "false"}]},
    {"spec": [{"key": "instance_class", "value": "db.t3.small"}]},
])
def test_no_warning_when_ha_says_it_or_the_spec_says_no(extra):
    assert _spec_ha(**extra) == []


def test_the_example_room_says_it_both_ways_and_is_quiet():
    from jsonui_doc_cli.infra import room as R
    assert [p for p in R.read(FIX / "aws-three-tier")["problems"] if p["code"] == "spec.ha"] == []


@pytest.mark.parametrize("row, path", [
    ({"node": "db-prod", "sku": "db.t3.small:multi-az"}, "/loads/0/sku"),
    ({"node": "db-prod", "quantities": {"requests": {"amount": 10, "per": "second"}},
      "vertical": {"quantity": "requests", "ladder": [{"sku": "db.t3.small", "amount": 1},
                                                                         {"sku": "db.t3.medium:Multi-AZ", "amount": 2}]}},
     "/loads/0/vertical/ladder/1/sku"),
])
def test_a_sku_written_with_multi_az_is_a_warning(tmp_path, row, path):
    root = _room(tmp_path, {"s.json": _scenario(loads=[row])})
    [p] = _problems(L.read(root), "load.sku.multi_az")
    assert p["path"] == path and "write the plain sku and ha: multi-az" in p["message"]


def test_a_schedule_s_sku_with_multi_az_is_a_warning(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(
        schedules={"office": {"rules": [{"days": ["mon"], "from": "09:00", "to": "18:00", "count": 1,
                                         "sku": "db.t3.small:multi-az"}]}},
        loads=[{"node": "db-prod", "schedule": "office"}])})
    [p] = _problems(L.read(root), "load.sku.multi_az")
    assert p["path"] == "/schedules/<key>/rules/0/sku"           # a name the writer chose: kept out of the path


def test_a_plain_sku_is_quiet(tmp_path):
    root = _room(tmp_path, {"s.json": _scenario(loads=[{"node": "db-prod", "sku": "db.t3.small"}])})
    assert _problems(L.read(root), "load.sku.multi_az") == []


# ---------------------------------------------------------------- a room's price that drops a bundled free amount

EGRESS = {"provider": "aws", "service": "data-transfer", "sku": "egress", "region": "ap-northeast-1", "unit": "GB",
          "price_usd": 0.114, "effective": "2026-10-01", "source": "manual"}


def _book_warnings(tmp_path, *rows) -> list[str]:
    tmp_path = tmp_path / str(len(list(tmp_path.iterdir())))   # a room per call
    root = _room(tmp_path, prices={"p.json": {"version": 0, "id": "p", "prices": list(rows)}})
    return [w for w in PB.load(root, NO_CACHE)[1] if "prices.free_dropped" in w]


def test_an_egress_row_without_free_says_the_account_s_100_gb_is_not_taken(tmp_path):
    [w] = _book_warnings(tmp_path, EGRESS)
    assert w == ("p.json /prices/0: aws/data-transfer/egress には無料枠がありませんが、同梱の価格は、アカウントの枠 "
                 "aws:data-transfer-out から 1 か月に 100 GB を無料にします。この行が勝つので、無料枠は取りません（残すには、"
                 "この行に free を書いてください） [prices.free_dropped]")


def test_a_row_that_keeps_the_free_amount_or_has_none_bundled_is_quiet(tmp_path):
    kept = dict(EGRESS, free={"amount": 100, "period": "month", "pool": "aws:data-transfer-out"})
    assert _book_warnings(tmp_path, kept) == []
    assert _book_warnings(tmp_path, dict(EGRESS, service="ecs.fargate", sku="vcpu", unit="vCPU-hour")) == []


def test_the_example_room_drops_no_free_amount():
    assert [w for w in PB.load(FIX / "aws-three-tier", NO_CACHE)[1] if "prices.free_dropped" in w] == []


def test_one_warning_per_price_however_many_rows_drop_it(tmp_path):
    [w] = _book_warnings(tmp_path, EGRESS, dict(EGRESS, region="us-east-1"))
    assert w.startswith("p.json /prices/0: aws/data-transfer/egress には無料枠がありませんが")
