"""The cost simulator on viz's side (infra_cost.py → document_tools' infra.load / infra.cost; plan
docs/plans/2026-10-20-jui-viz-backend-load-and-cost-simulator.md, L-C): the route's checks (those of /api/prompt), the
month and a day as the page gets them, the refusals, and the two months kept so a day does not simulate again.
The room is document_tools' aws-three-tier example (with its scenarios and price file), written under tmp_path."""
from __future__ import annotations

import json

import pytest

from jui_cli.viz import infra_cost as C
from tests.test_viz_infra_docs import TOKEN, _room, _serve, _world


@pytest.fixture(autouse=True)
def _fresh():
    C.forget()
    yield
    C.forget()


def test_the_month_the_scenarios_and_a_day(tmp_path):
    root = _room(tmp_path, "aws-three-tier")
    status, got = C.read(root, seq=3)
    assert status == 200 and got["ok"] and got["seq"] == 3 and got["scenario"] == "ordinary"
    assert [s["id"] for s in got["scenarios"]] == ["ordinary", "sale"]
    month = got["month"]
    assert len(month["days"]) == 30 and month["usd"] > 0 and month["noRule"] == ["stripe", "api-role", "api-5xx"]
    status, day = C.read(root, seq=4, scenario="sale", date="2026-11-27")
    assert status == 200 and day["scenario"] == "sale" and day["day"]["date"] == "2026-11-27"
    api = next(n for n in day["day"]["nodes"] if n["node"] == "api-prod")
    assert any(h.get("load", {}).get("overflow", 0) > 0 for h in api["hours"])    # the sale's day goes over capacity
    by_node = C.read(root, seq=5, scenario="sale", by="node")[1]["month"]
    assert by_node["by"] == "node" and by_node["keys"][0]["key"] != "aws"


@pytest.mark.parametrize("kw,reason", [({"scenario": "../x"}, "bad_request"), ({"date": "2026-11-31x"}, "bad_request"),
                                       ({"by": "region"}, "bad_request"), ({"scenario": "nope"}, "no_scenario"),
                                       ({"scenario": "sale", "date": "2026-12-01"}, "bad_request")])
def test_what_is_refused(tmp_path, kw, reason):
    status, got = C.read(_room(tmp_path, "aws-three-tier"), seq=1, **kw)
    assert status in (400, 404) and got["ok"] is False and got["reason"] == reason and got["seq"] == 1


def test_a_room_without_load_definitions(tmp_path):
    root = _room(tmp_path, "multi-provider")
    status, got = C.read(root, seq=2)
    assert status == 404 and got["reason"] == "no_load" and got["seq"] == 2


def test_two_months_are_kept_and_a_changed_file_simulates_again(tmp_path, monkeypatch):
    root = _room(tmp_path, "aws-three-tier")
    calls = []
    mods = C._mods()
    real = mods["engine"].simulate
    monkeypatch.setattr(mods["engine"], "simulate", lambda *a: calls.append(a[0]["id"]) or real(*a))
    C.read(root)
    C.read(root, date="2026-11-02")
    C.read(root, scenario="sale")
    C.read(root, scenario="ordinary", date="2026-11-03")
    assert calls == ["ordinary", "sale"]                     # the day came from the kept month
    load = root / "docs" / "infra" / "load" / "ordinary.json"
    load.write_text(load.read_text().replace('"ふだんの月"', '"ふだんの月（改）"'))
    C.read(root)
    assert calls == ["ordinary", "sale", "ordinary"]         # a load file changed: again
    C.read(root, scenario="sale")                            # the folder changed for every scenario: again too
    C.read(root, scenario="ordinary")
    assert calls == ["ordinary", "sale", "ordinary", "sale"] and len(C._KEPT) == C.KEEP


@pytest.mark.parametrize("change", ["price", "cache", "config"])
def test_a_price_file_the_cache_or_the_config_changed_simulates_again(tmp_path, monkeypatch, change):
    """The kept month's key covers what the price book reads: the room's price files, the fetched prices' cache
    (<viz home>/cloud-prices) and jui.config.json — not the load definitions only."""
    root = _room(tmp_path, "aws-three-tier")
    home = tmp_path / "vizhome"
    monkeypatch.setenv("JUI_VIZ_HOME", str(home))
    (home / "cloud-prices" / "aws").mkdir(parents=True)
    cached = home / "cloud-prices" / "aws" / "s3.json"
    cached.write_text(json.dumps({"version": 0, "prices": []}))
    calls = []
    mods = C._mods()
    real = mods["engine"].simulate
    monkeypatch.setattr(mods["engine"], "simulate", lambda *a: calls.append(a[0]["id"]) or real(*a))
    C.read(root)
    C.read(root)
    assert calls == ["ordinary"]
    if change == "price":
        f = root / "docs" / "infra" / "prices" / "example.json"
        f.write_text(f.read_text().replace('"見本の値"', '"見本の値（改）"', 1))
    elif change == "cache":
        cached.write_text(json.dumps({"version": 0, "prices": [], "label": "refetched"}))
    else:
        (root / "jui.config.json").write_text(json.dumps({"infra": {"dir": "docs/infra"}}))
    C.read(root)
    assert calls == ["ordinary", "ordinary"]


def test_the_route_takes_the_page_checks(tmp_path):
    root = _room(tmp_path, "aws-three-tier")
    world, pid = _world(root)

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        body = json.dumps({"projectId": pid, "seq": 9})
        return [("POST", "/api/infra-cost", ok, body),
                ("POST", "/api/infra-cost", {**ok, "X-Jui-Viz-Token": "x" * 43}, body),
                ("POST", "/api/infra-cost", {**ok, "Origin": "http://evil.example"}, body),
                ("GET", "/api/infra-cost", ok, None),
                ("POST", "/api/infra-cost", {**ok, "Content-Type": "text/plain"}, body),
                ("POST", "/api/infra-cost", ok, json.dumps({"projectId": "nope"})),
                ("POST", "/api/infra-cost", ok, json.dumps({"projectId": pid, "seq": 10, "scenario": "sale", "date": "2026-11-27"})),
                ("POST", "/api/infra-cost", ok, json.dumps({"projectId": pid, "seq": 11, "date": "x"}))]
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 401, 403, 405, 415, 404, 200, 400]
    month = json.loads(got[0][2])
    assert month["ok"] and month["seq"] == 9 and got[0][3]["Cache-Control"] == "no-store"
    assert got[0][3]["X-Content-Type-Options"] == "nosniff"
    day = json.loads(got[6][2])
    assert day["seq"] == 10 and day["day"]["date"] == "2026-11-27"
