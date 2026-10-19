"""jui viz: the estimated cost of each response over its robot (2.3.6, ticket 2026-10-19-jui-viz-cost-bill-over-robot).

prices.cost prices one response's four kinds of tokens by the model's row; a model not in the table, or a usage the
row cannot price, gets no amount (never 0, never a guessed price). World bills each message id once (Claude Code
writes one message once per content block, with the same usage) over the robot whose transcript it is — a subagent's
over its own. The shipped table is overridden and added to by the user's (<viz home>/prices.json), read again when
it changes with no restart and off the calling thread; a broken row is left out alone, with its reason. The CLI and
POST /api/prices (under /api/prompt's checks) change it: set, remove, reset. Everything under tmp_path.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import prices
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources import transcripts
from jui_cli.viz.state import VizState

SID = "0a0a0a0a-1111-4111-8111-aaaaaaaaaaaa"
SUB = "a5ub000000000001"
CWD = "/work/shop"
T = 1_792_300_000_000
TOKEN = "t" * 43
# measured 10-19 in a real transcript: one response's usage (opus 5.5)
USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 2252, "cache_read_input_tokens": 67349, "output_tokens": 936,
         "output_tokens_details": {"thinking_tokens": 247}, "service_tier": "standard",
         "cache_creation": {"ephemeral_1h_input_tokens": 2252, "ephemeral_5m_input_tokens": 0},
         "inference_geo": "global", "speed": "standard"}
OPUS = {"input": 4, "cache_write_5m": 5, "cache_write_1h": 8, "cache_read": 0.2, "output": 20}


def _iso(at):
    return datetime.fromtimestamp(at / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def _rec(mid, model="claude-opus-5-5", usage=None, at=T, block="text"):
    return {"type": "assistant", "timestamp": _iso(at), "sessionId": SID,
            "message": {"id": mid, "model": model, "role": "assistant", "content": [{"type": block, "text": "x"}],
                        "usage": usage or USAGE}}


def _append(f, *recs):
    with open(f, "a") as h:
        for r in recs:
            h.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------- the price of one response

def test_the_four_kinds_are_priced_by_the_models_row():
    table = prices.load_default()["models"]
    usd, why = prices.cost(table, "claude-opus-5-5", USAGE)
    want = (2 * 4 + 0 * 5 + 2252 * 8 + 67349 * 0.2 + 936 * 20) / 1e6
    assert why is None and usd == pytest.approx(want, abs=1e-12)
    # each kind on its own, so a kind dropped or priced as another shows
    for key, n, price in (("input_tokens", 1000, 4), ("cache_read_input_tokens", 1000, 0.2), ("output_tokens", 1000, 20)):
        u = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0, key: n}
        assert prices.cost(table, "claude-opus-5-5", u)[0] == pytest.approx(n * price / 1e6), key
    for split, price in (("ephemeral_5m_input_tokens", 5), ("ephemeral_1h_input_tokens", 8)):
        u = {"input_tokens": 0, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 0, "output_tokens": 0,
             "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0, split: 1000}}
        assert prices.cost(table, "claude-opus-5-5", u)[0] == pytest.approx(1000 * price / 1e6), split


@pytest.mark.parametrize("model", ["claude-zzz-9", "sonnet", "", None, 3])
def test_a_model_not_in_the_table_gets_no_amount(model):
    usd, why = prices.cost(prices.load_default()["models"], model, USAGE)
    assert usd is None and why == "model not in the table"


def test_what_the_row_cannot_price_gets_no_amount():
    table = prices.load_default()["models"]
    no_split = {k: v for k, v in USAGE.items() if k != "cache_creation"}
    assert prices.cost(table, "claude-opus-5-5", no_split)[0] is None                # which cache write? not guessed
    assert prices.cost(table, "claude-opus-5-5", {**no_split, "cache_creation_input_tokens": 0})[0] is not None
    assert prices.cost(table, "claude-opus-5-5", {**USAGE, "speed": "turbo"})[0] is None
    assert prices.cost(table, "claude-opus-4-7", {**USAGE, "speed": "fast"})[0] is None   # no fast price on its row
    assert prices.cost(table, "claude-opus-5-5", {**USAGE, "inference_geo": "eu"})[0] is None
    assert prices.cost(table, "claude-sonnet-4-5-20250929", {**USAGE, "inference_geo": "us"})[0] is None
    assert prices.cost(table, "claude-opus-5-5", {**USAGE, "output_tokens": -1})[0] is None


def test_the_modifiers_the_source_gives():
    table = prices.load_default()["models"]
    base = prices.cost(table, "claude-opus-5-5", USAGE)[0]
    assert prices.cost(table, "claude-opus-5-5", {**USAGE, "inference_geo": "us"})[0] == pytest.approx(base * 1.1)
    assert prices.cost(table, "claude-opus-5-5", {**USAGE, "speed": "fast"})[0] == pytest.approx(base * 2)   # 8/40 = 2x every kind
    small = {"input_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1000}
    big = {**small, "cache_read_input_tokens": 100_000}     # prompt over 100,000 counts the cache reads
    assert prices.cost(table, "claude-haiku-5-5", small)[0] == pytest.approx((1000 * 0.1 + 1000 * 0.5) / 1e6)
    assert prices.cost(table, "claude-haiku-5-5", big)[0] == pytest.approx((1000 * 0.5 + 100_000 * 0.05 + 1000 * 2.5) / 1e6)


def test_the_shipped_table_says_where_its_prices_come_from_and_every_row_is_whole():
    d = json.loads(prices.DEFAULT_PATH.read_text())
    assert d["source"] == "https://platform.claude.com/docs/en/about-claude/pricing" and d["checked"] == "2026-10-19"
    for model, row in d["models"].items():
        assert prices.MODEL_RE.fullmatch(model) and prices.check_row(row) is None, model
        assert row["cache_read"] < row["input"] < row["cache_write_5m"] < row["cache_write_1h"] < row["output"], model


# ---------------------------------------------------------------- the bills (World)

def _world(tmp_path, user=None):
    projects = tmp_path / "projects"
    d = projects / transcripts.project_dir_name(CWD)
    d.mkdir(parents=True)
    main = d / f"{SID}.jsonl"
    main.write_text("")
    sub = d / SID / "subagents" / f"agent-{SUB}.jsonl"
    sub.parent.mkdir(parents=True)
    sub.write_text("")
    world = World(VizState(), session_start=transcripts.session_start(projects))
    world.transcript_path = transcripts.transcript_path(projects)
    world.prices = prices.PriceBook(user=user or tmp_path / "home" / "prices.json")
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "source": "startup",
                      "transcript_path": str(main)}, T)
    world.apply_hook({"hook_event_name": "SubagentStart", "session_id": SID, "cwd": CWD, "agent_id": SUB, "agent_type": "Explore"}, T)
    world.poll_usage(T)            # first sight: from the end
    return world, main, sub


def _bills(world, at):
    world.poll_usage(at)
    world.publish()
    return world.state.slices.get("bills", [])


def test_a_message_written_on_several_lines_is_billed_once(tmp_path):
    world, main, _sub = _world(tmp_path)
    _append(main, _rec("msg_1", block="thinking"), _rec("msg_1", block="text"), _rec("msg_1", block="tool_use"))
    got = _bills(world, T + 2000)
    assert len(got) == 1 and got[0]["id"] == "msg_1" and got[0]["agentId"] == SID
    assert got[0]["usd"] == pytest.approx(prices.cost(world.prices.table, "claude-opus-5-5", USAGE)[0], abs=1e-6)
    assert got[0]["tokens"] == 2 + 2252 + 67349 + 936
    assert got[0]["priceFrom"] == "default"
    _append(main, _rec("msg_1"))                       # the same usage again later: not billed again
    assert len(_bills(world, T + 4000)) == 1
    # a long response: its last block written after its bill has gone (BILL_KEEP_MS) is still the same message
    assert _bills(world, T + 40_000) == []
    _append(main, _rec("msg_1", block="text"))
    assert _bills(world, T + 42_000) == []


def test_each_response_is_a_bill_and_old_ones_go(tmp_path):
    world, main, _sub = _world(tmp_path)
    _append(main, _rec("msg_1"))
    assert [b["id"] for b in _bills(world, T + 2000)] == ["msg_1"]
    _append(main, _rec("msg_2"))
    assert [b["id"] for b in _bills(world, T + 4000)] == ["msg_1", "msg_2"]
    assert [b["id"] for b in _bills(world, T + 4000 + 30_000)] == []


def test_a_subagents_responses_go_over_its_own_robot(tmp_path):
    world, main, sub = _world(tmp_path)
    _append(sub, _rec("msg_s", model="claude-haiku-5-5"))
    _append(main, _rec("msg_m"))
    got = {b["id"]: b for b in _bills(world, T + 2000)}
    assert got["msg_s"]["agentId"] == SUB and got["msg_m"]["agentId"] == SID
    assert got["msg_s"]["usd"] is not None


def test_a_model_not_in_the_table_is_a_bill_with_no_amount_and_is_told(tmp_path):
    world, main, _sub = _world(tmp_path)
    _append(main, _rec("msg_x", model="claude-zzz-9"), _rec("msg_syn", model="<synthetic>"))
    got = _bills(world, T + 2000)
    assert len(got) == 1 and got[0]["usd"] is None and got[0]["tokens"] > 0 and got[0]["why"] == "model not in the table"
    assert world.state.slices["prices"]["unpriced"] == ["claude-zzz-9"]


# ---------------------------------------------------------------- the user's table

def _wait_poll(world, until, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        world.prices._checked = 0.0
        world.poll_prices()
        world.publish()
        if until():
            return True
        time.sleep(0.02)
    return False


def test_the_users_table_overrides_and_adds_and_a_rewrite_applies_with_no_restart(tmp_path):
    user = tmp_path / "home" / "prices.json"
    world, main, _sub = _world(tmp_path, user)
    _append(main, _rec("msg_x", model="claude-zzz-9"))
    _bills(world, T + 2000)
    user.parent.mkdir(parents=True)
    user.write_text(json.dumps({"models": {"claude-zzz-9": {**OPUS, "output": 40}, "claude-opus-5-5": {**OPUS, "input": 400}}}))
    assert _wait_poll(world, lambda: "claude-zzz-9" in world.prices.table)
    assert world.state.slices["prices"]["unpriced"] == []           # priced now: no longer told
    _append(main, _rec("msg_y", model="claude-zzz-9"), _rec("msg_o"))
    got = {b["id"]: b for b in _bills(world, T + 4000)}
    assert got["msg_y"]["usd"] == pytest.approx((2 * 4 + 2252 * 8 + 67349 * 0.2 + 936 * 40) / 1e6, abs=1e-6)
    assert got["msg_o"]["usd"] == pytest.approx((2 * 400 + 2252 * 8 + 67349 * 0.2 + 936 * 20) / 1e6, abs=1e-6)
    assert got["msg_y"]["priceFrom"] == got["msg_o"]["priceFrom"] == "user"
    rows = {r["model"]: r for r in world.state.slices["prices"]["rows"]}
    assert rows["claude-zzz-9"]["origin"] == "user" and rows["claude-opus-5-5"]["origin"] == "changed"
    # rewritten again (same size, the same second): the next response uses it
    user.write_text(json.dumps({"models": {"claude-zzz-9": {**OPUS, "output": 80}, "claude-opus-5-5": {**OPUS, "input": 400}}}))
    assert _wait_poll(world, lambda: world.prices.table["claude-zzz-9"]["output"] == 80)
    user.write_text(json.dumps({"models": {"claude-opus-5-5": None}}))
    assert _wait_poll(world, lambda: "claude-opus-5-5" not in world.prices.table)
    _append(main, _rec("msg_z"))
    assert {b["id"]: b for b in _bills(world, T + 6000)}["msg_z"]["usd"] is None


def test_the_read_is_never_on_the_calling_thread(tmp_path, monkeypatch):
    user = tmp_path / "prices.json"
    user.write_text(json.dumps({"models": {"m-1": OPUS}}))
    book = prices.PriceBook(user=user)
    seen = []
    real = prices._read_user
    monkeypatch.setattr(prices, "_read_user", lambda p: (seen.append(threading.current_thread().name), real(p))[1])
    with ThreadPoolExecutor(1, thread_name_prefix="price-worker") as pool:
        book.poll(pool)
        assert seen == [] or seen[0].startswith("price-worker")
        end = time.monotonic() + 5
        while "m-1" not in book.table and time.monotonic() < end:
            book._checked = 0.0
            book.poll(pool)
            assert book.table is not None and ("m-1" in book.table) == ("m-1" in book.user_rows)
            time.sleep(0.01)
    assert "m-1" in book.table and seen and all(n.startswith("price-worker") for n in seen)


def test_a_broken_row_is_left_out_alone_with_its_reason(tmp_path):
    user = tmp_path / "prices.json"
    user.write_text(json.dumps({"models": {"good-1": OPUS, "no-output": {k: v for k, v in OPUS.items() if k != "output"},
                                           "negative": {**OPUS, "input": -1}, "text": {**OPUS, "input": "4"},
                                           "bad name!": OPUS, "claude-opus-5-5": [1, 2]}}))
    book = prices.PriceBook(user=user)
    book.read_now()
    assert "good-1" in book.table and book.table["claude-opus-5-5"]["input"] == 4     # the shipped row stays
    assert {"no-output", "negative", "text"}.isdisjoint(book.table)
    assert len(book.errors) == 5 and any("no-output: output is missing" in e for e in book.errors)


@pytest.mark.parametrize("content", ["{not json", json.dumps([1, 2]), json.dumps({"models": 3})])
def test_a_table_that_is_not_one_leaves_the_shipped_prices(tmp_path, content):
    user = tmp_path / "prices.json"
    user.write_text(content)
    book = prices.PriceBook(user=user)
    book.read_now()
    assert book.table == prices.merge(book.default, {}) and len(book.errors) == 1


def test_a_fifo_or_a_symlink_never_holds_or_leads_the_read(tmp_path):
    user = tmp_path / "prices.json"
    os.mkfifo(user)
    book = prices.PriceBook(user=user)
    t = threading.Thread(target=book.read_now, daemon=True)
    t.start()
    t.join(3)
    assert not t.is_alive() and book.errors and "not a regular file" in book.errors[0]
    user.unlink()
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"models": {"m-1": OPUS}}))
    user.symlink_to(target)
    book.read_now()
    assert "m-1" not in book.table


# ---------------------------------------------------------------- set / remove / reset (the CLI and the page)

def test_the_four_operations(tmp_path):
    user = tmp_path / "prices.json"
    default = prices.load_default()

    def table():
        b = prices.PriceBook(user=user)
        b.read_now()
        return b.table
    assert prices.apply_op(user, "set", "claude-new-1", OPUS, default)[0]                       # add
    assert table()["claude-new-1"]["output"] == 20
    assert prices.apply_op(user, "set", "claude-opus-5-5", {**OPUS, "output": 99}, default)[0]  # change a shipped one
    assert table()["claude-opus-5-5"]["output"] == 99
    assert prices.apply_op(user, "reset", "claude-opus-5-5", None, default)[0]                  # back to the shipped
    assert table()["claude-opus-5-5"] == default["models"]["claude-opus-5-5"]
    assert prices.apply_op(user, "remove", "claude-opus-5-5", None, default)[0]                 # a shipped one: null
    assert "claude-opus-5-5" not in table() and json.loads(user.read_text())["models"]["claude-opus-5-5"] is None
    assert prices.apply_op(user, "remove", "claude-new-1", None, default)[0]                    # one of the user's
    assert "claude-new-1" not in json.loads(user.read_text())["models"]
    assert oct(user.stat().st_mode & 0o777) == "0o600"
    for op, model, row in (("set", "m", {**OPUS, "input": -1}), ("set", "bad name", OPUS), ("drop", "m", None),
                           ("remove", "nowhere-1", None), ("reset", "nowhere-1", None)):
        assert not prices.apply_op(user, op, model, row, default)[0], (op, model)


def test_a_broken_table_is_not_overwritten(tmp_path):
    user = tmp_path / "prices.json"
    user.write_text("{my notes")
    ok, msg = prices.apply_op(user, "set", "m-1", OPUS)
    assert not ok and "not JSON" in msg and user.read_text() == "{my notes"


def test_the_cli(tmp_path, monkeypatch, capsys):
    from jui_cli.cli import main
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path))
    flags = ["--input", "1", "--cache-write-5m", "1.25", "--cache-write-1h", "2", "--cache-read", "0.1", "--output", "5"]
    assert main(["viz", "prices", "set", "claude-new-1", *flags]) == 0
    assert main(["viz", "prices", "set", "claude-new-2", "--input", "1"]) == 1
    assert main(["viz", "prices", "remove", "claude-opus-5-5"]) == 0
    assert main(["viz", "prices", "list", "--json"]) == 0
    out = capsys.readouterr().out
    rows = {r["model"]: r for r in json.loads(out[out.index("{"):])["rows"]}
    assert rows["claude-new-1"]["origin"] == "user" and rows["claude-opus-5-5"]["origin"] == "removed"
    assert main(["viz", "prices", "reset", "claude-opus-5-5"]) == 0
    assert json.loads((tmp_path / "prices.json").read_text())["models"] == {"claude-new-1": {**{k: float(v) for k, v in zip(prices.KINDS, (1, 1.25, 2, 0.1, 5))}}}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_page_writes_under_the_prompt_checks(tmp_path):
    user = tmp_path / "home" / "prices.json"
    world, _main, _sub = _world(tmp_path, user)
    port = _free_port()
    own = f"127.0.0.1:{port}"
    ok = {"Host": own, "Origin": f"http://{own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
    good = json.dumps({"op": "set", "model": "claude-new-1", "row": OPUS})
    calls = [("POST", {**ok, "Origin": "http://evil.example"}, good),
             ("POST", {k: v for k, v in ok.items() if k != "Origin"}, good),
             ("POST", {**ok, "X-Jui-Viz-Token": "x" * 43}, good),
             ("POST", {**ok, "Host": f"localhost:{port}"}, good),
             ("GET", ok, None),
             ("POST", {**ok, "Content-Type": "text/plain"}, good),
             ("POST", ok, "x" * 9000),
             ("POST", ok, json.dumps({"op": "set", "model": "claude-new-1", "row": {**OPUS, "input": "free"}})),
             ("POST", ok, good),
             ("POST", ok, json.dumps({"op": "remove", "model": "claude-opus-5-5"})),
             ("POST", ok, json.dumps({"op": "reset", "model": "claude-opus-5-5"}))]

    async def run():
        ctx = ServerContext(config=VizConfig(pushIntervalMs=50), port=port, token=TOKEN, state=world.state, world=world, publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        out = []
        try:
            for method, headers, body in calls:
                r = await client.request(method, "/api/prices", headers=headers, data=body)
                out.append(r.status)
                if len(out) == 7:
                    assert not user.exists()                    # nothing refused wrote anything
        finally:
            await client.close()
        return out
    status = asyncio.run(run())
    assert status == [403, 403, 401, 403, 405, 415, 413, 400, 200, 200, 200], status
    assert json.loads(user.read_text())["models"] == {"claude-new-1": {k: float(v) for k, v in OPUS.items()}}
    assert _wait_poll(world, lambda: "claude-new-1" in world.prices.table)


# ---------------------------------------------------------------- the ledger and the watch's probe

def _cc_watch():
    import sys
    from pathlib import Path
    tools = Path(__file__).resolve().parents[1] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from cc_watch import ledger as L, probes as P
    return L, P


def test_the_ledger_decides_the_bills_files_and_is_red_without_them():
    L, _P = _cc_watch()
    ledger = L.load()
    entry = next(e for e in ledger["entries"] if e["id"] == "model-prices")
    assert entry["probe"] == "price_table_models"
    mine = {"jui_tools/jui_cli/viz/prices.py", "jui_tools/jui_cli/viz/prices.json", "jui_tools/jui_cli/viz/web/js/54-bills.js"}
    assert mine <= set(entry["files"])
    assert L.check(L.M.repo_root(), ledger) == []
    entry["files"] = [f for f in entry["files"] if f not in mine]
    red = L.check(L.M.repo_root(), ledger)
    assert {r.split(":")[0] for r in red} >= mine, red


def test_the_probe_is_red_for_a_model_the_table_has_no_price_for(tmp_path):
    _L, P = _cc_watch()
    cfg = tmp_path / "cfg"
    (cfg / "projects" / "p" / "s" / "subagents").mkdir(parents=True)
    (cfg / "projects" / "p" / "s.jsonl").write_text(json.dumps(_rec("m1")) + "\n" + json.dumps(_rec("m0", model="<synthetic>")) + "\n")
    ctx = P.Context(run=lambda argv: (0, ""), session=P.Session(config_dir=cfg))
    table = prices.merge(prices.load_default(), {})
    green = P.price_table_models(ctx, table)
    assert green == {"responses": True, "unpriced": []}
    (cfg / "projects" / "p" / "s" / "subagents" / "agent-a.jsonl").write_text(json.dumps(_rec("m2", model="claude-fake-9")) + "\n")
    red = P.price_table_models(ctx, table)
    assert red == {"responses": True, "unpriced": ["claude-fake-9"]} and red != green      # the watch compares: red
    # priced in the user's table: green again (the probe judges by both tables together)
    user = tmp_path / "prices.json"
    prices.apply_op(user, "set", "claude-fake-9", OPUS)
    book = prices.PriceBook(user=user)
    book.read_now()
    assert P.price_table_models(ctx, book.table) == green
    assert P.price_table_models(P.Context(run=lambda argv: (0, "")))["skipped"]


def test_the_probe_reads_the_users_table_by_default(tmp_path, monkeypatch):
    _L, P = _cc_watch()
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))
    cfg = tmp_path / "cfg"
    (cfg / "projects" / "p").mkdir(parents=True)
    (cfg / "projects" / "p" / "s.jsonl").write_text(json.dumps(_rec("m1", model="claude-fake-9")) + "\n")
    ctx = P.Context(run=lambda argv: (0, ""), session=P.Session(config_dir=cfg))
    assert P.price_table_models(ctx)["unpriced"] == ["claude-fake-9"]
    prices.apply_op(prices.user_path(), "set", "claude-fake-9", OPUS)
    assert P.price_table_models(ctx)["unpriced"] == []
