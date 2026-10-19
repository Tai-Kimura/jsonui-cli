"""The question window (2.3.6, ticket 2026-10-19-jui-viz-question-window-too-short): how long the AskUserQuestion hook
waits for an answer from the page, who it waits for, and why it stopped.

In process (aiohttp TestServer, a real World): the hook is POST /hook/ask as forward.py --ask sends it; the page's
presence is ctx.present_until (the socket's "presence") and POST /api/notify-presence. Windows are shortened through
the config, never waited out at their real length."""
from __future__ import annotations

import asyncio
import json
import socket
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import config as config_mod
from jui_cli.viz import paths
from jui_cli.viz.config import ASK_WAIT_CHOICES, VizConfig, load_config
from jui_cli.viz.ingest import World
from jui_cli.viz.server import NEVER_MS, ServerContext, ask_window, make_app
from jui_cli.viz.state import VizState, now_ms

TOKEN = "t" * 43
SID = "0a000000-0000-4000-8000-0000000000a1"
Q = {"questions": [{"question": "どちらにしますか", "header": "選択", "multiSelect": False,
                    "options": [{"label": "左", "description": "左にする"}, {"label": "右", "description": "右にする"}]}]}


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _hook(event: str, **more) -> dict:
    return {"session_id": SID, "cwd": "/work/qwin", "transcript_path": "/work/t.jsonl", "permission_mode": "default",
            "hook_event_name": event, **more}


class Rig:
    """A world with one session, the app on a free port, and the page's headers."""

    def __init__(self, cfg: VizConfig):
        self.world = World(VizState())
        self.world.apply_hook(_hook("SessionStart", source="startup"), now_ms())
        self.port = _port()
        self.own = f"127.0.0.1:{self.port}"
        self.ctx = ServerContext(config=cfg, port=self.port, token=TOKEN, state=self.world.state, world=self.world,
                                 publish=self.world.publish)
        self.client = TestClient(TestServer(make_app(self.ctx), host="127.0.0.1", port=self.port))

    def page(self, **over) -> dict:
        h = {"Host": self.own, "Origin": f"http://{self.own}", "X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"}
        h.update(over)
        return {k: v for k, v in h.items() if v is not None}

    async def ask(self, use_id: str):
        """POST /hook/ask as forward.py --ask: (seconds it took, the answer)."""
        t = time.monotonic()
        r = await self.client.post("/hook/ask", headers={"X-Jui-Viz-Token": TOKEN, "Content-Type": "application/json"},
                                   data=json.dumps(_hook("PreToolUse", tool_name="AskUserQuestion", tool_use_id=use_id, tool_input=Q)))
        return time.monotonic() - t, await r.json()

    def card(self) -> dict:
        self.world.publish()
        return self.world.state.snapshot()["slices"]["questions"][-1]


def _run(cfg: VizConfig, body):
    async def main():
        rig = Rig(cfg)
        await rig.client.start_server()
        try:
            return await body(rig)
        finally:
            await rig.client.close()
    return asyncio.run(main())


# ---- the window and its choices ----

def test_the_default_window_is_three_minutes_and_the_choices_are_the_rulings():
    assert VizConfig().askWaitSec == 180
    assert ASK_WAIT_CHOICES == (20, 60, 180, 600, 1800, 0)


def test_a_long_window_is_not_cut_at_askmaxsec_and_until_answered_never_runs_out():
    start = 1_000_000
    assert ask_window(VizConfig(askWaitSec=600, askMaxSec=300), start) == (start + 600_000, start + 600_000)
    assert ask_window(VizConfig(askWaitSec=60, askMaxSec=300), start) == (start + 60_000, start + 300_000)
    assert ask_window(VizConfig(askWaitSec=0, askMaxSec=300), start) == (NEVER_MS, NEVER_MS)


# ---- who it waits for ----

def test_no_page_at_all_the_hook_returns_at_once_and_nothing_is_recorded():
    async def body(rig):
        took, answer = await rig.ask("u1")
        return took, answer, rig.card()
    took, answer, card = _run(VizConfig(askWaitSec=5), body)
    assert took < 1.0 and answer == {} and not card.get("waitEnded") and "waitEndReason" not in card


def test_a_hidden_page_without_notifications_does_not_hold_the_question():
    async def body(rig):
        rig.ctx.present_until = 0   # hidden (the socket said visible: false)
        took, _ = await rig.ask("u2")
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=5), body)
    assert took < 1.0 and not card.get("waitEnded")


def test_a_visible_page_holds_it_for_the_window_then_says_timeout():
    async def body(rig):
        rig.ctx.present_until = now_ms() + 60_000
        took, _ = await rig.ask("u3")
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=1.0), body)
    assert 0.9 <= took < 3.0, took
    assert card["waitEnded"] and card["waitEndReason"] == "timeout" and card["waitEndedAt"] > card["createdAt"]


def test_a_hidden_page_with_question_notifications_on_waits_the_window():
    async def body(rig):
        r = await rig.client.post("/api/notify-presence", headers=rig.page(), data=json.dumps({"ask": True}))
        assert r.status == 200
        rig.ctx.present_until = 0
        took, _ = await rig.ask("u4")
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=1.0, notifyPresenceSec=30), body)
    assert 0.9 <= took < 3.0, took
    assert card["waitEndReason"] == "timeout"


def test_when_the_notifying_page_goes_the_wait_ends_within_its_presence():
    """A tab closed (or a browser gone) says nothing more: notifyPresenceSec after its last word, the question goes back."""
    async def body(rig):
        await rig.client.post("/api/notify-presence", headers=rig.page(), data=json.dumps({"ask": True}))
        took, _ = await rig.ask("u5")
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=30, notifyPresenceSec=0.8), body)
    assert 0.6 <= took < 2.5, took
    assert card["waitEndReason"] == "hidden"


def test_notifications_said_off_end_it_at_once():
    async def body(rig):
        await rig.client.post("/api/notify-presence", headers=rig.page(), data=json.dumps({"ask": True}))
        task = asyncio.ensure_future(rig.ask("u6"))
        await asyncio.sleep(0.4)
        await rig.client.post("/api/notify-presence", headers=rig.page(), data=json.dumps({"ask": False}))
        took, _ = await task
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=30, notifyPresenceSec=30), body)
    assert took < 2.0 and card["waitEndReason"] == "hidden"


def test_a_page_that_goes_hidden_without_notifications_ends_it():
    async def body(rig):
        rig.ctx.present_until = now_ms() + 60_000
        task = asyncio.ensure_future(rig.ask("u7"))
        await asyncio.sleep(0.4)
        rig.ctx.present_until = 0
        took, _ = await task
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=30), body)
    assert took < 2.0 and card["waitEndReason"] == "hidden"


# ---- until answered, and the ways out ----

def test_until_answered_waits_past_askmaxsec_and_the_terminal_button_ends_it():
    async def body(rig):
        rig.ctx.present_until = now_ms() + 60_000
        task = asyncio.ensure_future(rig.ask("u8"))
        await asyncio.sleep(1.2)   # past askMaxSec (0.5)
        still = not task.done() and rig.card()["hookWaiting"]
        assert rig.world.release_question(rig.card()["id"], now_ms()) is None
        took, answer = await task
        return still, took, answer, rig.card()
    still, took, answer, card = _run(VizConfig(askWaitSec=0, askMaxSec=0.5), body)
    assert still and took >= 1.2 and answer == {}
    assert card["released"] and card["waitEndReason"] == "released"


def test_until_answered_ends_when_the_session_ends():
    async def body(rig):
        rig.ctx.present_until = now_ms() + 60_000
        task = asyncio.ensure_future(rig.ask("u9"))
        await asyncio.sleep(0.4)
        rig.world.apply_hook(_hook("SessionEnd", reason="exit"), now_ms())
        took, _ = await task
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=0), body)
    assert took < 2.0 and card["waitEndReason"] == "session"


def test_until_answered_ends_when_every_page_is_gone():
    async def body(rig):
        await rig.client.post("/api/notify-presence", headers=rig.page(), data=json.dumps({"ask": True}))
        took, _ = await rig.ask("u10")
        return took, rig.card()
    took, card = _run(VizConfig(askWaitSec=0, notifyPresenceSec=0.8), body)
    assert 0.6 <= took < 2.5 and card["waitEndReason"] == "hidden"


def test_an_answer_from_the_page_is_recorded_as_answered():
    async def body(rig):
        rig.ctx.present_until = now_ms() + 60_000
        task = asyncio.ensure_future(rig.ask("u11"))
        await asyncio.sleep(0.4)
        assert rig.world.answer_question(rig.card()["id"], {"どちらにしますか": {"labels": ["左"], "other": ""}}, now_ms()) is None
        took, answer = await task
        return answer, rig.card()
    answer, card = _run(VizConfig(askWaitSec=30), body)
    assert answer["hookSpecificOutput"]["updatedInput"]["answers"] == {"どちらにしますか": "左"}
    assert card["waitEndReason"] == "answered"


# ---- the two routes ----

@pytest.mark.parametrize("route, ok_body", [("/api/notify-presence", {"ask": True}), ("/api/ask-wait", {"sec": 60})])
def test_every_check_of_the_page_routes_refuses(route, ok_body, tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))

    async def body(rig):
        data = json.dumps(ok_body)
        out = {}
        out["token"] = (await rig.client.post(route, headers=rig.page(**{"X-Jui-Viz-Token": "x" * 43}), data=data)).status
        out["no-token"] = (await rig.client.post(route, headers=rig.page(**{"X-Jui-Viz-Token": None}), data=data)).status
        out["origin"] = (await rig.client.post(route, headers=rig.page(Origin="http://evil.example"), data=data)).status
        out["no-origin"] = (await rig.client.post(route, headers=rig.page(Origin=None), data=data)).status
        out["host"] = (await rig.client.post(route, headers=rig.page(Host=f"localhost:{rig.port}"), data=data)).status
        out["get"] = (await rig.client.get(route, headers=rig.page())).status
        out["text"] = (await rig.client.post(route, headers=rig.page(**{"Content-Type": "text/plain"}), data=data)).status
        out["big"] = (await rig.client.post(route, headers=rig.page(), data=json.dumps({**ok_body, "pad": "x" * 400}))).status
        out["ok"] = (await rig.client.post(route, headers=rig.page(), data=data)).status
        return out
    got = _run(VizConfig(), body)
    assert got == {"token": 401, "no-token": 401, "origin": 403, "no-origin": 403, "host": 403, "get": 405, "text": 415,
                   "big": 413, "ok": 200}, got


@pytest.mark.parametrize("bad", [45, -1, "60", True, None, 60.5])
def test_only_the_choices_are_taken(bad, tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))

    async def body(rig):
        return (await rig.client.post("/api/ask-wait", headers=rig.page(), data=json.dumps({"sec": bad}))).status, rig.ctx.config.askWaitSec
    status, now = _run(VizConfig(), body)
    assert status == 400 and now == 180


def test_the_choice_is_saved_kept_after_a_restart_and_used_by_the_next_question(tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    paths.config_json().write_text(json.dumps({"port": 7790}))

    async def body(rig):
        r = await rig.client.post("/api/ask-wait", headers=rig.page(), data=json.dumps({"sec": 20}))
        rig.world.publish()
        return r.status, rig.world.state.snapshot()["slices"]["settings"], rig.ctx.config.askWaitSec
    status, settings, now = _run(load_config(), body)
    assert status == 200 and now == 20 and settings["askWaitSec"] == 20 and settings["askWaitText"] == "20 秒"
    saved = json.loads(paths.config_json().read_text())
    assert saved == {"port": 7790, "askWaitSec": 20}          # the person's other keys kept
    assert load_config().askWaitSec == 20                      # a restart reads it back

    async def next_question(rig):
        rig.ctx.present_until = now_ms() + 60_000
        rig.ctx.config.askWaitSec = 1.0   # stands for the saved 20 s, shortened (never waited out)
        took, _ = await rig.ask("u12")
        return took
    assert _run(load_config(), next_question) < 3.0


def test_a_broken_config_json_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    paths.config_json().write_text("[not, an, object]")

    async def body(rig):
        return (await rig.client.post("/api/ask-wait", headers=rig.page(), data=json.dumps({"sec": 600}))).status
    assert _run(VizConfig(), body) == 500
    assert paths.config_json().read_text() == "[not, an, object]"


def test_save_setting_keeps_the_other_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path / "home"))
    config_mod.save_setting("askWaitSec", 600)
    config_mod.save_setting("port", 7791)
    assert json.loads(paths.config_json().read_text()) == {"askWaitSec": 600, "port": 7791}
