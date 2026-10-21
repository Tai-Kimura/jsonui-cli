"""`jsonui-doc cost infra` (infra/cost/run.py; ticket 2026-10-21-agents-skills-mcp-for-server-room §3a-1): the cost
simulator's month or day without jui viz — the same simulation and the same shapes as viz's /api/infra-cost, and
exit 0 (simulated), 1 (simulated, a load definition has an error), 2 (nothing could be simulated)."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from jsonui_doc_cli.infra import load as L
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra.cost import engine as E
from jsonui_doc_cli.infra.cost import pricebook as PB
from jsonui_doc_cli.infra.cost import run as RUN
from jsonui_doc_cli.infra.cost import view as V
from test_infra_load import FIX, TOOLS, _room, _scenario

ROOM = FIX / "aws-three-tier"
NO_CACHE = {"JUI_VIZ_HOME": "/nonexistent"}


def _cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "jsonui_doc_cli.cli", "cost", "infra", *args], cwd=TOOLS,
                          capture_output=True, text=True, env={**os.environ, **NO_CACHE})


def _engine(scenario_id: str):
    model = R.read(ROOM)
    book, _w = PB.load(ROOM, NO_CACHE)
    sc = next(s for s in L.read(ROOM)["scenarios"] if s["id"] == scenario_id)
    return E.simulate(sc, model, book), model


def test_the_month_is_the_engine_s_month_as_viz_shapes_it():
    code, out = RUN.reply(ROOM, env=NO_CACHE)
    result, model = _engine("ordinary")
    assert code == 0 and out["ok"] and out["scenario"] == "ordinary"
    assert out["month"] == V.month_view(result, model, "provider")
    assert [s["id"] for s in out["scenarios"]] == ["ordinary", "sale"]
    assert sum(t["usd"] for t in out["topNodes"]) <= out["month"]["usd"] + 1e-9
    assert out["topNodes"][0]["usd"] == max(t["usd"] for t in out["topNodes"])


def test_a_scenario_by_node_and_a_day():
    code, out = RUN.reply(ROOM, "sale", by="node", env=NO_CACHE)
    result, model = _engine("sale")
    assert code == 0 and out["month"] == V.month_view(result, model, "node")
    code, out = RUN.reply(ROOM, None, "2026-11-03", env=NO_CACHE)
    result, model = _engine("ordinary")
    assert code == 0 and "month" not in out and out["day"] == V.day_view(result, model, "2026-11-03")


@pytest.mark.parametrize("kw, reason", [
    ({"scenario": "nope"}, "no_scenario"),
    ({"date": "2026-12-01"}, "bad_request"),
    ({"date": "11/03"}, "bad_request"),
    ({"by": "region"}, "bad_request"),
])
def test_what_cannot_be_simulated_is_2_with_why(kw, reason):
    code, out = RUN.reply(ROOM, env=NO_CACHE, **kw)
    assert code == 2 and out == {"ok": False, "reason": reason, "message": out["message"]} and out["message"]


def test_no_room_and_no_load_are_2(tmp_path):
    assert RUN.reply(tmp_path / "nothing", env=NO_CACHE)[1]["reason"] in ("no_infra", "not_a_room")
    code, out = RUN.reply(_room(tmp_path, {}), env=NO_CACHE)
    assert code == 2 and out["reason"] == "no_load"


def test_a_load_file_with_an_error_is_left_out_and_the_month_is_1(tmp_path):
    root = _room(tmp_path, {"a.json": _scenario(id="a", loads=[{"node": "api-prod", "quantities": {}}]),
                            "b.json": _scenario(id="b", month="x")})
    code, out = RUN.reply(root, env=NO_CACHE)
    assert code == 1 and out["ok"] and [s["id"] for s in out["scenarios"]] == ["a"]
    assert out["problems"]["errors"] >= 1 and any(p["file"] == "b.json" for p in out["problems"]["first"])


def test_the_command_prints_json_and_exits_as_reply():
    got = _cli(str(ROOM), "--json")
    assert got.returncode == 0 and json.loads(got.stdout) == json.loads(json.dumps(RUN.reply(ROOM, env=NO_CACHE)[1]))
    text = _cli(str(ROOM))
    assert text.returncode == 0 and "scenario ordinary (2026-11, production); other scenarios: sale" in text.stdout
    assert "a month (USD, on demand" in text.stdout and "no rule (2): stripe, api-role" in text.stdout
    day = _cli(str(ROOM), "--date", "2026-11-03")
    assert day.returncode == 0 and "2026-11-03: $" in day.stdout
    bad = _cli(str(ROOM), "--scenario", "nope")
    assert bad.returncode == 2 and "no scenario 'nope'; there are: ordinary, sale" in bad.stderr and bad.stdout == ""


def test_warnings_alone_are_0_and_still_counted(tmp_path):
    root = _room(tmp_path, {"a.json": _scenario(id="a", loads=[{"node": "api-prod", "quantities": {"requests": 1}},
                                                               {"node": "api-prod", "quantities": {"requests": 2}}])})
    code, out = RUN.reply(root, env=NO_CACHE)
    assert code == 0 and out["problems"]["errors"] == 0 and out["problems"]["count"] >= 1
    assert {p["code"] for p in out["problems"]["first"]} == {"load.overlap"}
