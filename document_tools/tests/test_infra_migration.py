"""A room's server migration plans (migration.py; ticket 2026-10-22-viz-infra-migration-plan): old + changes - removals
= new, by the five rules (replace, add, remove, an edge taken along with its end, a replaced node's edges kept), one
node a step, every code a plan's problem can have, the old room's output unchanged when it has no plan, and the
cost of a plan as the engine prices the old model and the new one each on its own. Everything under tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import migration as MG
from jsonui_doc_cli.infra import model as M
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra.cost import diff as D
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import pricebook as PB

FIX = Path(__file__).resolve().parent / "fixtures" / "infra"
OLD = {"version": 0,
       "groups": [{"id": "vpc", "kind": "network", "provider": "aws"}],
       "nodes": [{"id": "lb", "category": "load_balancer", "group": "vpc"},
                 {"id": "api", "category": "compute.container", "group": "vpc"},
                 {"id": "db", "category": "database.relational", "group": "vpc", "engine": "mysql 8"},
                 {"id": "mail", "category": "mail"},
                 {"id": "old-cache", "category": "cache", "group": "vpc"}],
       "edges": [{"from": "lb", "to": "api"}, {"from": "api", "to": "db"}, {"from": "api", "to": "mail"},
                 {"id": "warm", "from": "api", "to": "old-cache"}, {"from": "lb", "to": "db"}]}


def _room(tmp_path, changes=None, removals=None, plan="move", model=OLD, config=None) -> Path:
    root = tmp_path / "room"
    (root / "docs/infra").mkdir(parents=True, exist_ok=True)
    (root / "docs/infra/main.json").write_text(json.dumps(model))
    if config is not None:
        (root / "jui.config.json").write_text(json.dumps(config))
    if changes is not None or removals is not None:
        mig = root / ((config or {}).get("infra", {}).get("migrations_dir") or "docs/infra/migrations") / plan
        mig.mkdir(parents=True)
        if changes is not None:
            (mig / "changes.json").write_text(changes if isinstance(changes, str) else json.dumps(changes))
        if removals is not None:
            (mig / "removals.json").write_text(removals if isinstance(removals, str) else json.dumps(removals))
    return root


def _plan(root, name="move") -> dict:
    got = R.read(root, plans=True)
    assert got["ok"], got
    return next(m for m in got["migrations"] if m["name"] == name)


def _keys(model: dict) -> set[str]:
    return {MG.edge_key(e) for e in model["edges"]}


def _ids(model: dict) -> dict:
    return {n["id"]: n for n in model["nodes"]}


# ---------------------------------------------------------------- the five rules

def test_a_node_with_an_id_the_old_model_has_takes_its_place(tmp_path):
    m = _plan(_room(tmp_path, {"version": 0, "nodes": [{"id": "db", "category": "database.relational", "group": "vpc",
                                                        "engine": "aurora mysql 3"}]}))
    assert m["ok"] and _ids(m["model"])["db"]["engine"] == "aurora mysql 3"
    assert [s["kind"] for s in m["steps"]] == ["replace"] and len(m["model"]["nodes"]) == len(OLD["nodes"])


def test_a_node_with_a_new_id_is_added(tmp_path):
    m = _plan(_room(tmp_path, {"version": 0, "nodes": [{"id": "cache", "category": "cache", "group": "vpc"}],
                               "edges": [{"from": "api", "to": "cache"}]}))
    assert m["ok"] and "cache" in _ids(m["model"]) and "api->cache" in _keys(m["model"])
    assert m["steps"] == [{"index": 1, "node": "cache", "kind": "add", "edgesRemoved": [], "edgesAdded": ["api->cache"]}]


def test_a_node_removals_names_goes(tmp_path):
    m = _plan(_room(tmp_path, removals={"version": 0, "nodes": ["mail"]}))
    assert m["ok"] and "mail" not in _ids(m["model"]) and [s["kind"] for s in m["steps"]] == ["remove"]


def test_an_edge_goes_with_the_node_it_ends_at(tmp_path):
    m = _plan(_room(tmp_path, removals={"version": 0, "nodes": ["old-cache"]}))
    assert "warm" not in _keys(m["model"]) and m["steps"][0]["edgesRemoved"] == ["warm"]
    assert not [p for p in m["problems"] if p["code"] == "edge.missing"]


def test_a_replaced_nodes_edges_are_kept_unless_the_plan_names_them(tmp_path):
    changes = {"version": 0, "nodes": [{"id": "db", "category": "database.relational", "group": "vpc"}],
               "edges": [{"from": "lb", "to": "db", "protocol": "mysql"}]}
    m = _plan(_room(tmp_path, changes, {"version": 0, "edges": [{"from": "api", "to": "mail"}]}))
    assert {"api->db", "lb->db"} <= _keys(m["model"]) and "api->mail" not in _keys(m["model"])
    assert next(e for e in m["model"]["edges"] if MG.edge_key(e) == "lb->db")["protocol"] == "mysql"   # named: replaced
    assert m["steps"][0]["edgesRemoved"] == ["lb->db"] and m["steps"][0]["edgesAdded"] == ["lb->db"]
    assert m["steps"][1] == {"index": 2, "node": None, "kind": "edges", "edgesRemoved": ["api->mail"], "edgesAdded": []}


# ---------------------------------------------------------------- the steps

def test_the_steps_follow_order_then_changes_then_removals_and_each_model_holds_together(tmp_path):
    changes = {"version": 0, "order": ["mail", "cache"],
               "nodes": [{"id": "db", "category": "database.relational", "group": "vpc"},
                         {"id": "cache", "category": "cache", "group": "vpc"}],
               "edges": [{"from": "db", "to": "cache"}]}
    root = _room(tmp_path, changes, {"version": 0, "nodes": ["mail", "old-cache"]})
    m = _plan(root)
    assert [(s["node"], s["kind"]) for s in m["steps"]] == [("mail", "remove"), ("cache", "add"), ("db", "replace"),
                                                             ("old-cache", "remove")]
    assert m["steps"][2]["edgesAdded"] == ["db->cache"]          # the later of its two ends
    files, _p = R.read_json_folder(root, "docs/infra")
    plan, _p = MG.read_plan(root, "docs/infra/migrations", "move", files)
    old = R.read(root)
    for k in range(plan.last + 1):
        model, problems = plan.model_at(k)
        assert not M.errors(problems), (k, problems)
    first, last = plan.model_at(0)[0], plan.model_at(plan.last)[0]
    assert (first["nodes"], first["edges"]) == (old["nodes"], old["edges"])
    assert (last["nodes"], last["edges"]) == (m["model"]["nodes"], m["model"]["edges"])


# ---------------------------------------------------------------- a plan's problems

CASES = {
    "migration.remove_missing": ({"version": 0}, {"version": 0, "nodes": ["nowhere"]}, "move/removals.json", "/nodes/0"),
    "migration.duplicate": ({"version": 0, "nodes": [{"id": "x", "category": "cache"}, {"id": "x", "category": "cache"}]},
                            None, "move/changes.json", "/nodes/1/id"),
    "migration.both": ({"version": 0, "nodes": [{"id": "db", "category": "database.relational"}]},
                       {"version": 0, "nodes": ["db"]}, "move/removals.json", "/nodes/0"),
    "migration.order_unknown": ({"version": 0, "order": ["api"], "nodes": [{"id": "db", "category": "database.relational"}]},
                                None, "move/changes.json", "/order/0"),
    "migration.edge_end": ({"version": 0, "edges": [{"from": "api", "to": "mail"}]}, {"version": 0, "nodes": ["mail"]},
                           "move/changes.json", "/edges/0"),
}


@pytest.mark.parametrize("code", sorted(CASES))
def test_each_code_says_its_file_and_place_in_words(tmp_path, code):
    changes, removals, file, path = CASES[code]
    m = _plan(_room(tmp_path, changes, removals))
    mine = [p for p in m["problems"] if p["code"] == code]
    assert len(mine) == 1 and not m["ok"], m["problems"]
    assert (mine[0]["file"], mine[0]["path"]) == (file, path)
    assert mine[0]["short"] == f"docs/infra/migrations/{file}: {path} {R.MIGRATION_JA[code]}（{code}）"


def test_every_code_has_a_case_and_words():
    assert set(CASES) | {"migration.no_plan"} == set(MG.CODES) == set(R.MIGRATION_JA)


def test_the_new_model_is_checked_as_the_room_is(tmp_path):
    """A plan's file with an error is left out whole; the new model's problems the old one has not are the plan's."""
    m = _plan(_room(tmp_path, {"version": 0, "nodes": [{"id": "x", "category": "nope"}]}))
    assert not m["ok"] and m["steps"] == [] and m["problems"][0]["code"] == "schema"
    m = _plan(_room(tmp_path / "b", None, {"version": 0, "groups": ["vpc"]}))
    assert not m["ok"] and {p["code"] for p in m["problems"]} == {"group.missing"}
    m = _plan(_room(tmp_path / "c", {"version": 0, "nodes": [{"id": "k", "category": "cache", "label": "AKIA" + "IOSFODNN7EXAMPLE"}]}))
    assert not m["ok"] and m["problems"][0]["code"].startswith("secret.")


def test_a_plan_named_that_the_room_has_not(tmp_path):
    got = R.read(_room(tmp_path, {"version": 0}), plans="other")["migrations"]
    assert [(m["name"], m["ok"], m["problems"][0]["code"]) for m in got] == [("other", False, "migration.no_plan")]


def test_the_migrations_folder_is_the_configs(tmp_path):
    root = _room(tmp_path, {"version": 0, "nodes": [{"id": "c", "category": "cache"}]},
                 config={"infra": {"migrations_dir": "ops/plans"}})
    assert _plan(root)["dir"] == "ops/plans/move"
    bad = R.read(_room(tmp_path / "b", config={"infra": {"migrations_dir": "../x"}}), plans=True)["migrations"]
    assert bad[0]["problems"][0]["code"] == "config.migrations_dir"


# ---------------------------------------------------------------- no plan: the output as it was

def _cli(*args) -> tuple[int, str]:
    tools = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", *args], cwd=tools, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    return r.returncode, r.stdout + r.stderr


@pytest.mark.parametrize("room", sorted(p.name for p in FIX.iterdir() if (p / "docs" / "infra").is_dir()))
def test_a_room_with_no_plan_reads_as_before(room):
    """No "migrations" key at all, not []: validate infra's text and --json are the old ones (the room read with
    plans as without)."""
    root = FIX / room
    a, b = R.read(root, plans=True), R.read(root)
    a.pop("readMs", None), b.pop("readMs", None)
    assert "migrations" not in a and a == b


def test_validate_infra_names_each_plan_and_fails_on_its_errors(tmp_path):
    root = _room(tmp_path, {"version": 0, "nodes": [{"id": "c", "category": "cache"}]})
    rc, out = _cli("validate", "infra", str(root))
    assert rc == 0 and "migration move: docs/infra/migrations/move: 1 step(s), 1 added" in out
    bad = _room(tmp_path / "b", None, {"version": 0, "nodes": ["nowhere"]})
    rc, out = _cli("validate", "infra", str(bad), "--migration", "move", "--json")
    got = json.loads(out)
    assert rc == 1 and got["migrations"][0]["problems"][0]["code"] == "migration.remove_missing"
    rc, _out = _cli("validate", "infra", str(root), "--migration", "nope")
    assert rc == 1


# ---------------------------------------------------------------- the cost of a plan

def _priced_room(tmp_path) -> Path:
    root = tmp_path / "room"
    shutil.copytree(FIX / "aws-three-tier", root)
    mig = root / "docs/infra/migrations/move"
    mig.mkdir(parents=True)
    (mig / "changes.json").write_text(json.dumps({"version": 0, "order": ["db-prod"], "nodes": [
        {"id": "db-prod", "category": "database.relational", "service": "rds.mysql", "group": "private-prod",
         "environments": ["production"], "spec": [{"key": "instance_class", "value": "db.r6g.xlarge"}]},
        {"id": "cache-prod", "category": "cache", "service": "elasticache.redis", "group": "private-prod",
         "environments": ["production"]}], "edges": [{"from": "api-prod", "to": "cache-prod"}]}))
    (mig / "removals.json").write_text(json.dumps({"version": 0, "nodes": ["mailer"]}))
    return root


def test_the_difference_is_the_engines_months_of_the_old_and_the_new_each_on_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = _priced_room(tmp_path)
    code, out = D.reply(root, "move")
    assert code == 0 and out["ok"], out
    scenario = L.read(root)["scenarios"][0]
    book, _w = PB.load(root)
    alone = {}
    for name, model in (("old", R.read(root)), ("new", _plan(root)["model"])):
        t = E.month_totals(E.simulate(scenario, model, book))
        alone[name] = t
    assert out["old"]["usd"] == alone["old"]["usd"] and out["new"]["usd"] == alone["new"]["usd"]
    assert out["diff"]["usd"] == alone["new"]["usd"] - alone["old"]["usd"] and out["diff"]["usd"] != 0
    per = {r["node"]: r for r in out["byNode"]}
    for name in ("old", "new"):
        by_node: dict = {}
        for d in alone[name]["days"]:
            for n, v in d["byNode"].items():
                by_node[n] = by_node.get(n, 0.0) + v
        assert {n: r[name] for n, r in per.items() if r[name]} == pytest.approx(by_node)
    assert per["db-prod"]["change"] == "replaced" and per["mailer"]["change"] == "removed" and per["cache-prod"]["change"] == "added"
    assert out["steps"][-1]["usd"] == out["new"]["usd"]
    assert sum(s["diff"] for s in out["steps"]) == pytest.approx(out["diff"]["usd"])
    # each step's total is the engine's month of the model after that step, priced alone (not a sum that only adds up)
    files, _p = R.read_json_folder(root, "docs/infra")
    plan, _p = MG.read_plan(root, "docs/infra/migrations", "move", files)
    each = [E.month_totals(E.simulate(scenario, plan.model_at(k)[0], book))["usd"] for k in range(plan.last + 1)]
    assert [s["usd"] for s in out["steps"]] == pytest.approx(each[1:]) and each[0] != each[1]   # the first step moves it
    assert sum(r["diff"] for r in out["byProvider"]) == pytest.approx(out["diff"]["usd"])
    # a step's difference is what moved in it, node by node; summed over the steps, a node's is its row's
    for s in out["steps"]:
        assert sum(m["diff"] for m in s["moved"]) == pytest.approx(s["diff"], abs=0.01)
    by_steps: dict = {}
    for s in out["steps"]:
        for mv in s["moved"]:
            by_steps[mv["node"]] = by_steps.get(mv["node"], 0.0) + mv["diff"]
    assert {r["node"]: r["diff"] for r in out["byNode"] if abs(r["diff"]) >= 0.005} == pytest.approx(by_steps, abs=0.01)


def test_a_plan_with_an_error_or_no_such_plan_is_not_priced(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = _priced_room(tmp_path)
    (root / "docs/infra/migrations/move/removals.json").write_text(json.dumps({"version": 0, "nodes": ["nowhere"]}))
    assert D.reply(root, "move")[1]["reason"] == "bad_plan" and D.reply(root, "move")[0] == 2
    assert D.reply(root, "none")[1]["reason"] == "no_plan"
    rc, out = _cli("cost", "infra", str(root), "--migration", "none", "--json")
    assert rc == 2 and json.loads(out)["reason"] == "no_plan"


def test_a_load_row_for_a_node_the_plan_adds_counts_once_it_is_there(tmp_path, monkeypatch):
    """The scenario's rows are read against each step's model: a row for the added node prices it in the new month (and
    the step that adds it), and is no warning of the room's own load definitions while a plan adds that node."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = _priced_room(tmp_path)
    load_dir = root / "docs/infra/load"
    for f in load_dir.glob("*.json"):
        doc = json.loads(f.read_text())
        doc["loads"].append({"node": "cache-prod", "quantities": {"ecpu": {"amount": 1000, "per": "second"}, "storage_gb": 1}})
        f.write_text(json.dumps(doc))
    base = _priced_room(tmp_path / "b")
    _c, without = D.reply(base, "move")
    code, out = D.reply(root, "move")
    assert code == 0 and not [p for p in L.read(root)["problems"] if p["code"] == "load.node_missing"]
    added = next(r for r in out["byNode"] if r["node"] == "cache-prod")
    assert added["old"] == 0 and added["new"] > 0 and "cache-prod" not in out["unpricedChanged"]
    assert out["new"]["usd"] > without["new"]["usd"] and out["old"]["usd"] == without["old"]["usd"]
    # with no plan adding it, the same row is the warning it was
    (root / "docs/infra/migrations/move/changes.json").write_text(json.dumps({"version": 0}))
    assert [p["node"] for p in L.read(root)["problems"] if p["code"] == "load.node_missing"] == ["cache-prod"] * 2


def test_a_changed_node_with_no_price_is_named(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _c, out = D.reply(_priced_room(tmp_path), "move")
    unpriced = {r["node"] for r in out["byNode"] if r["unpriced"]}
    assert "cache-prod" in out["unpricedChanged"] and set(out["unpricedChanged"]) <= unpriced
    assert set(out["unpricedChanged"]) <= {s for k in ("noRule", "loadUndefined", "noPrice") for s in out["old"][k] + out["new"][k]}


def test_a_steps_difference_is_all_that_moved_in_it(tmp_path, monkeypatch):
    """Removing db-prod takes its edge's transfer (the load's edge api-prod>db-prod) with it: the step moves two rows,
    and its difference is both (the video: a step's −$150.12 against the node's −$155.52 — a neighbour moved)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = _priced_room(tmp_path)
    (root / "docs/infra/migrations/move/changes.json").write_text(json.dumps({"version": 0}))
    (root / "docs/infra/migrations/move/removals.json").write_text(json.dumps({"version": 0, "nodes": ["db-prod"]}))
    _c, out = D.reply(root, "move")
    step = out["steps"][0]
    rows = {m["node"] for m in step["moved"]}
    assert {"db-prod", "api-prod>db-prod"} <= rows
    assert step["diff"] == pytest.approx(sum(m["diff"] for m in step["moved"]))
    assert abs(step["diff"] - next(m["diff"] for m in step["moved"] if m["node"] == "db-prod")) > 0.5



def test_the_japanese_words_of_a_migration_say_step_not_ho():
    """A plan's problems in Japanese say ステップ, never 歩 (requester 10-23: 「12歩じゃなくて12ステップね歩ごとにのところも
    ステップごとにに変えといて」), every code."""
    assert set(R.MIGRATION_JA) >= {c for c in MG.CODES if c.startswith("migration.")}
    for code in R.MIGRATION_JA:
        assert "歩" not in R.MIGRATION_JA[code], code
        assert "歩" not in R.DEFAULT_WORDS.migration("x", "docs/infra/migrations/p/changes.json", code), code
