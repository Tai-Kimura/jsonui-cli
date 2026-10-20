"""The cost simulator's screens (infra/cost/view.py, plan L-C): the shapes the page draws, from engine.simulate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import pricebook as PB
from jsonui_doc_cli.infra.cost import view as V

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"
BUNDLED = PB.Book(bundled=PB.bundled_rows())


def _example(name: str):
    root = FIX / "aws-three-tier"
    model = R.read(root)
    book, _w = PB.load(root, {"JUI_VIZ_HOME": "/nonexistent"})
    sc = next(s for s in L.read(root)["scenarios"] if s["id"] == name)
    return E.simulate(sc, model, book), model


def _run(nodes, loads, **extra):
    doc = {"version": 0, "nodes": nodes}
    model, problems = M.merge([("m.json", json.dumps(doc).encode())])
    assert M.errors(problems) == []
    scenario, _p = L.normalize("t.json", {"version": 0, "id": "t", "month": "2026-11", "loads": loads, **extra}, model)
    return E.simulate(scenario, model, BUNDLED), model


def test_the_month_by_provider_adds_up_to_the_totals():
    result, model = _example("ordinary")
    mv = V.month_view(result, model)
    totals = E.month_totals(result)
    assert len(mv["days"]) == 30 and mv["usd"] == pytest.approx(totals["usd"])
    assert [k["key"] for k in mv["keys"]] == ["aws", "sendgrid"]
    for d, t in zip(mv["days"], totals["days"]):
        assert sum(d["stack"].values()) == pytest.approx(t["usd"]) == pytest.approx(d["usd"])
    assert mv["noRule"] == ["stripe", "api-role", "api-5xx"] and len(mv["noPrice"]) == 1


def test_the_month_by_node_keeps_the_top_and_the_rest():
    result, model = _example("ordinary")
    mv = V.month_view(result, model, by="node", top=2)
    assert [k["key"] for k in mv["keys"]][:2] == ["cdn", "db-prod"] and mv["keys"][2]["key"] == V.OTHERS
    assert mv["keys"][0]["label"] == "CloudFront"
    cdn = next(r for r in result.nodes if r.node == "cdn")
    for d in mv["days"]:
        assert sum(d["stack"].values()) == pytest.approx(d["usd"])
        own = sum(V.node_hour_usd(cdn, k) for k in V.day_hours(result, d["date"]))
        assert d["stack"]["cdn"] == pytest.approx(own) and own > 0          # a top node is its own part of the stack


def test_days_with_an_hour_over_capacity_or_at_the_top_are_marked():
    result, model = _example("sale")
    days = {d["date"]: d for d in V.month_view(result, model)["days"]}
    assert days["2026-11-27"]["overflowHours"] > 0 and days["2026-11-27"]["atMaxHours"] > 0
    assert days["2026-11-01"]["overflowHours"] == 0


def test_a_day_is_its_top_nodes_hour_by_hour_and_the_rest():
    result, model = _example("ordinary")
    dv = V.day_view(result, model, "2026-11-02", top=3)
    assert dv["hours"] == list(range(24)) and len(dv["nodes"]) == 3 and dv["others"]["count"] > 0
    whole = sum(E.node_usd(r, k) or 0 for r in result.nodes for k in V.day_hours(result, "2026-11-02"))
    shown = sum(h["usd"] for n in dv["nodes"] for h in n["hours"]) + sum(dv["others"]["usd"])
    assert dv["usd"] == pytest.approx(whole) == pytest.approx(shown)
    cdn = next(n for n in dv["nodes"] if n["node"] == "cdn")["hours"][12]
    seg = next(s for s in cdn["segments"] if s["meter"] == "requests-japan")
    assert seg["label"] == "リクエスト" and seg["rate"]["per"] == "second" and seg["price"]["layer"] == "bundled"


def test_a_bar_says_its_instances_range_overflow_and_a_step_change():
    nodes = [{"id": "api", "category": "compute.container", "provider": "aws", "service": "ecs", "region": "us-east-1"},
             {"id": "db", "category": "database.relational", "provider": "aws", "service": "rds.mysql", "region": "us-east-1"}]
    ladder = [{"sku": "db.r6g.large", "amount": 100}, {"sku": "db.r6g.xlarge", "amount": 400}]
    loads = [{"node": "api", "quantities": {"requests": {"amount": 300, "per": "second"}, "vcpu": 1},
              "autoscale": {"min": 1, "max": 2, "per_instance": {"quantity": "requests", "amount": 100, "per": "second"}}},
             {"node": "db", "profile": "p", "quantities": {"requests": {"amount": 1, "per": "second"}},
              "vertical": {"quantity": "requests", "per": "second", "ladder": ladder, "change_delay_min": 0,
                           "order": "vertical_first"}}]
    hourly = [0.5] * 12 + [3.0] * 12
    result, model = _run(nodes, loads, profiles={"p": {"hourly": [x * 100 for x in hourly]}})
    dv = V.day_view(result, model, "2026-11-02")
    api = next(n for n in dv["nodes"] if n["node"] == "api")["hours"][0]
    assert api["range"] == [1, 2] and api["atMax"] is True and api["running"] == 2
    assert api["load"] == {"quantity": "requests", "label": "リクエスト", "per": "second", "unit": "request",
                           "demand": pytest.approx(300), "served": pytest.approx(200), "capacity": pytest.approx(200),
                           "overflow": pytest.approx(100)}
    db = next(n for n in dv["nodes"] if n["node"] == "db")["hours"]
    assert db[11]["sku"] == "db.r6g.large" and db[12]["sku"] == "db.r6g.xlarge"
    assert db[12].get("stepChanged") is True and not db[11].get("stepChanged")
    inst = next(s for s in db[12]["segments"] if s["meter"] == "instance")
    assert inst["label"] == "稼働" and "rate" not in inst


def test_a_node_with_a_note_is_kept_with_it():
    result, model = _example("sale")
    dv = V.day_view(result, model, "2026-11-02", top=50)
    notes = {n["node"]: n["note"] for n in dv["nodes"] if n["note"]}
    assert notes["stripe"] == "no rule" and notes["assets"] == "load undefined"
