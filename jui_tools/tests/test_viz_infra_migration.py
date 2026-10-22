"""A migration plan on viz's side (ticket 2026-10-22-viz-infra-migration-plan): the room's read carries its plans
(infra_docs → document_tools' infra.migration) with their lines in the page's language, and /api/infra-cost with
"migration" gives document_tools' cost diff — the same numbers `jsonui-doc cost infra --migration` prints — behind the
route's checks. The room is document_tools' aws-three-tier example with a plan written next to it, under tmp_path."""
from __future__ import annotations

import json

import pytest

from jui_cli.core.document_tools_import import load_document_tools_module
from jui_cli.viz import i18n, infra_cost, infra_docs
from tests.test_viz_infra_docs import TOKEN, _room, _serve, _world

diff = load_document_tools_module("infra.cost.diff")[0]
CHANGES = {"version": 0, "nodes": [{"id": "db-prod", "category": "database.relational", "service": "rds.mysql",
                                    "group": "private-prod", "environments": ["production"],
                                    "spec": [{"key": "instance_class", "value": "db.r6g.xlarge"}]}]}


def _plan(tmp_path, removals=None):
    root = _room(tmp_path, "aws-three-tier")
    mig = root / "docs" / "infra" / "migrations" / "move"
    mig.mkdir(parents=True)
    (mig / "changes.json").write_text(json.dumps(CHANGES))
    if removals is not None:
        (mig / "removals.json").write_text(json.dumps(removals))
    return root


def test_the_rooms_read_carries_its_plans_in_the_pages_language(tmp_path):
    root = _plan(tmp_path, {"version": 0, "nodes": ["nowhere"]})
    before = i18n.active()
    seen = set()
    try:
        for lang in ("ja", "en"):
            i18n.activate(i18n.load(lang, use_env=False))
            _status, got = infra_docs.read(root, seq=1)
            m = got["migrations"][0]
            assert m["name"] == "move" and not m["ok"] and m["problems"][0]["code"] == "migration.remove_missing"
            assert m["problems"][0]["short"] == i18n.tl("srv.room.migration", where="docs/infra/migrations/move/removals.json",
                                                         path="/nodes/0", why=i18n.tl("srv.room.migration.remove_missing"),
                                                         code="migration.remove_missing")
            seen.add(m["problems"][0]["short"])
    finally:
        i18n.activate(before)
    assert len(seen) == 2          # two languages, two lines


def test_a_room_with_no_plan_has_no_migrations_key(tmp_path):
    _status, got = infra_docs.read(_room(tmp_path, "aws-three-tier"), seq=1)
    assert got["ok"] and "migrations" not in got


def test_the_route_gives_the_engines_difference(tmp_path):
    root = _plan(tmp_path)
    world, pid = _world(root)

    def calls(own):
        ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        return [("POST", "/api/infra-cost", ok, json.dumps({"projectId": pid, "seq": 4, "migration": "move"})),
                ("POST", "/api/infra-cost", {**ok, "X-Jui-Viz-Token": "x" * 43}, json.dumps({"projectId": pid, "migration": "move"})),
                ("POST", "/api/infra-cost", ok, json.dumps({"projectId": pid, "migration": "../x"})),
                ("POST", "/api/infra-cost", ok, json.dumps({"projectId": pid, "migration": "nope"}))]
    got = _serve(world, calls)
    assert [g[0] for g in got] == [200, 401, 400, 404]
    page = json.loads(got[0][2])
    _code, cli = diff.reply(root, "move")
    assert page["seq"] == 4 and page["ok"] and page["diff"]["usd"] == cli["diff"]["usd"] != 0
    assert [s["usd"] for s in page["steps"]] == [s["usd"] for s in cli["steps"]]
    assert json.loads(got[3][2])["reason"] == "no_plan"


def test_the_account_is_chosen_as_the_cost_view_chooses_it(tmp_path):
    """document_tools' diff prices the account with the same scenarios viz's コスト picks."""
    from jui_cli.viz.infra_cost import account_scenarios as viz_pick
    load = load_document_tools_module("infra.load")[0]
    room = load_document_tools_module("infra.room")[0]
    root = _room(tmp_path, "aws-three-tier")
    scenarios, model = load.read(root)["scenarios"], room.read(root)
    for chosen in scenarios:
        assert viz_pick(scenarios, model, chosen) == diff.account_scenarios(scenarios, model, chosen)
    fake = [dict(s, environment=e) for s, e in zip(scenarios * 2, ["production", "staging"])]
    assert viz_pick(fake, model, fake[0]) == diff.account_scenarios(fake, model, fake[0]) and viz_pick(fake, model, fake[0])[0]


def test_migration_refuses_what_is_not_a_name(tmp_path):
    assert infra_cost.migration(tmp_path, 1, "../x")[1]["reason"] == "bad_request"
    assert infra_cost.migration(tmp_path, 1, "ok", scenario="../x")[1]["reason"] == "bad_request"


def test_the_japanese_words_of_a_migration_say_step_not_ho():
    """A migration's step is ステップ in Japanese, never 歩 (requester 10-23: 「12歩じゃなくて12ステップね歩ごとにのところも
    ステップごとにに変えといて」): every ja word the player, its log and the room's migration problems read."""
    import pathlib
    import re
    web = pathlib.Path(i18n.__file__).resolve().parent / "web"
    ja = json.loads((web / "i18n" / "ja.json").read_text(encoding="utf-8"))
    used = set(re.findall(r"tl\('([\w.]+)'", (web / "js" / "59-sr-migration.js").read_text(encoding="utf-8")))
    keys = used | {k for k in ja if k.startswith(("sr.mig.", "srv.room.migration"))}
    assert len(keys) >= 40 and "sr.mig.at" in keys and "sr.mig.step" in keys, sorted(keys)
    ho = {k: ja[k] for k in sorted(keys) if k in ja and "歩" in ja[k]}
    assert not ho, ho
    assert ja["sr.mig.at"].endswith("ステップ") and "ステップ" in ja["sr.mig.cost.step"] + ja["sr.mig.total.now"]


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_the_routes_lines_are_the_pages_language(tmp_path, lang):
    """The migration's cost reply says its refusals and its load problems in the page's language, as the cost
    view's reply does (short on each): no Japanese under en, the table's words under ja."""
    import re
    before = i18n.active()
    i18n.activate(i18n.load(lang, use_env=False))
    try:
        root = _plan(tmp_path)
        load = next((root / "docs/infra/load").glob("*.json"))
        doc = json.loads(load.read_text(encoding="utf-8"))
        doc["loads"].append({"node": "nowhere", "quantities": {"requests": {"amount": 1, "per": "second"}}})
        load.write_text(json.dumps(doc), encoding="utf-8")
        _s, got = infra_cost.migration(root, 1, "move")
        missing = [p for p in got["problems"]["first"] if p["code"] == "load.node_missing"]
        refusals = [infra_cost.migration(root, 1, "../x")[1], infra_cost.migration(root, 1, "nope")[1],
                    infra_cost.migration(root, 1, "move", scenario="nope")[1]]
        lines = [p["short"] for p in missing] + [r["short"] for r in refusals]
        assert missing and all(lines), (missing, refusals)
        ja = re.compile(r"[぀-ヿ一-鿿]")
        assert all(bool(ja.search(x)) == (lang == "ja") for x in lines), lines
    finally:
        i18n.activate(before)
