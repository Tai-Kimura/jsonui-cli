"""The Slack intake, stage 1 (design 2026-11-02 §1-4, §7): fetch -> inbox -> filter adapter -> router adapter ->
projects/<id>/ | _unsorted/ | gone (chitchat). Nothing here reaches Slack, Anthropic, TypeSafe or claude: the
HTTP calls are replaced, and the connector's claude is a script of this test (run with a temporary HOME)."""
from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
import textwrap
import time
from pathlib import Path

import pytest

from jui_cli.viz.slack import config as C
from jui_cli.viz.slack import fetch as FE
from jui_cli.viz.slack import filters as FI
from jui_cli.viz.slack import intake as I
from jui_cli.viz.slack import routers as R
from jui_cli.viz.slack import store as S

J = "".join
AWS = J(["AK", "IA", "IOSFODNN7EXAMPLE"])


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)


def cfg_of(tmp_path, **over) -> dict:
    cfg = C._merge(C.DEFAULT, {
        "orchestrationDir": str(tmp_path / "orch"),
        "source": {"workspaces": [{"name": "acme", "token": "slk-tok-QQ7", "channels": ["C0123"]}]},
        "router": {"anthropicApiKey": "ant-key-QQ8", "typesafeApiKey": "tsf-key-QQ9",
                   "prompt": {"projects": {"shop": "在庫アプリ", "booking": "予約サイト"}}},
    })
    return C._merge(cfg, over)


def inbox(root: Path, ts: str, text: str, **message) -> Path:
    S.ensure(root)
    path = root / S.INBOX / S.file_name(ts, "acme", "C0123")
    S.write_json(path, {"workspace": "acme", "channel": "C0123", "ts": ts, "permalink": f"https://t/p{ts}",
                        "via": "api", "message": {"ts": ts, "user": "U1", "text": text, **message}})
    return path


def files_under(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.json") if ".state" not in p.parts)


class FakeRoute:
    def __init__(self, answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, message, router_cfg):
        self.seen.append(message)
        got = self.answers.pop(0)
        if isinstance(got, Exception):
            raise got
        return {"adapter": "haiku", **got}


# ---------------------------------------------------------------- routing: where each message ends up

def test_a_project_a_low_confidence_an_unknown_choice_and_chitchat(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    inbox(root, "1730000001.000100", "在庫の画面が落ちる " + AWS, files=[{"name": "log.txt"}])
    inbox(root, "1730000002.000100", "どっちの話かな")
    inbox(root, "1730000003.000100", "ほかの話")
    inbox(root, "1730000004.000100", "おつかれさまです！")
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}, {"choice": "booking", "confidence": 0.3},
                       {"choice": "nope", "confidence": 0.99}, {"choice": "chitchat", "confidence": 0.95}])
    got = I.process_inbox(cfg, root, route=route)
    assert got == {"projects": 1, "unsorted": 2, "chitchat": 1, "failed": 0, "waiting": 0, "followed": 0}
    assert files_under(root) == ["_unsorted/1730000002.000100-acme-C0123.json",
                                 "_unsorted/1730000003.000100-acme-C0123.json",
                                 "projects/shop/1730000001.000100-acme-C0123.json"]
    placed = json.loads((root / "projects/shop/1730000001.000100-acme-C0123.json").read_text())
    assert placed == {"workspace": "acme", "channel": "C0123", "user": "U1", "ts": "1730000001.000100",
                      "threadTs": "1730000001.000100", "replyCount": 0, "text": "在庫の画面が落ちる [REDACTED:aws-access-key]", "permalink": "https://t/p1730000001.000100",
                      "removedFiles": 1, "redactions": 1,
                      "router": {"adapter": "haiku", "choice": "shop", "confidence": 0.9}}
    # the router saw the filtered text only
    assert all(AWS not in m["text"] for m in route.seen) and "[REDACTED:aws-access-key]" in route.seen[0]["text"]
    # chitchat: no file anywhere, and nothing of it in the state
    state = "".join(p.read_text() for p in (root / S.STATE).glob("*.json"))
    assert "おつかれさま" not in state and "1730000004" not in state
    assert stat.S_IMODE(placed and (root / "projects/shop/1730000001.000100-acme-C0123.json").stat().st_mode) == 0o600


def test_a_router_failure_keeps_the_message_in_the_inbox_and_tries_again_later(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    kept = inbox(root, "1730000001.000100", "在庫")
    route = FakeRoute([R.RouterError("HTTP 529")])
    assert I.process_inbox(cfg, root, route=route, now=1000.0)["failed"] == 1
    assert kept.exists() and files_under(root) == ["inbox/1730000001.000100-acme-C0123.json"]
    assert I.process_inbox(cfg, root, route=route, now=1000.0 + 60)["waiting"] == 1     # not before RETRY_SEC
    route.answers = [{"choice": "shop", "confidence": 0.8}]
    assert I.process_inbox(cfg, root, route=route, now=1000.0 + I.RETRY_SEC + 1)["projects"] == 1
    assert not kept.exists()
    assert I.Status(root).data["failed"] == {}


# ---------------------------------------------------------------- filter adapters: a file of one's own, and one that fails

def adapter_file(tmp_path, body: str) -> Path:
    path = tmp_path / "adapters" / "my_filter.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(textwrap.dedent(body))
    return path


def test_a_filter_adapter_of_ones_own_is_used_in_place_of_the_builtin(tmp_path):
    path = adapter_file(tmp_path, """
        def filter_message(record):
            text = record["message"]["text"].replace("社外秘", "■■■")
            return {"text": text, "user": "someone", "permalink": ""}, {"removedFiles": 0, "redactions": 1}
    """)
    cfg = cfg_of(tmp_path, filter={"adapter": str(path)})
    root = C.orchestration_dir(cfg)
    inbox(root, "1730000001.000100", "社外秘の件 " + AWS)
    route = FakeRoute([{"choice": "booking", "confidence": 0.7}])
    assert I.process_inbox(cfg, root, route=route)["projects"] == 1
    placed = json.loads((root / "projects/booking/1730000001.000100-acme-C0123.json").read_text())
    # its own rule ran (■■■), the builtin did not (the AWS shape is left: the adapter replaces the builtin)
    assert placed["text"] == "■■■の件 " + AWS and placed["user"] == "someone" and placed["redactions"] == 1
    assert route.seen[0]["text"] == "■■■の件 " + AWS


@pytest.mark.parametrize("body,said", [
    ("def filter_message(record):\n    raise RuntimeError('boom')\n", "boom"),
    ("import sys\ndef filter_message(record):\n    sys.exit(3)\n", "failed"),
    ("import time\ndef filter_message(record):\n    time.sleep(30)\n", "did not answer"),
    ("def filter_message(record):\n    return {'text': 1}, {}\n", "no text string"),
    ("def filter_message(record):\n    return {'text': 'x'}, {'removedFiles': -1, 'redactions': 0}\n", "removedFiles"),
    ("def nothing():\n    pass\n", "failed"),
], ids=["raises", "exits", "hangs", "no-text", "bad-stats", "no-function"])
def test_a_failing_filter_adapter_keeps_the_message_home_and_routes_nothing(tmp_path, monkeypatch, body, said):
    monkeypatch.setattr(FI.adapters, "TIMEOUT_SEC", 2.0)
    monkeypatch.setattr(FI.apply, "__defaults__", (2.0,))
    path = adapter_file(tmp_path, body)
    cfg = cfg_of(tmp_path, filter={"adapter": str(path)})
    root = C.orchestration_dir(cfg)
    kept = inbox(root, "1730000001.000100", "社外秘 " + AWS)
    route = FakeRoute([])
    got = I.process_inbox(cfg, root, route=route)
    assert got["failed"] == 1 and route.seen == []                       # nothing reached the router
    assert kept.exists() and files_under(root) == ["inbox/1730000001.000100-acme-C0123.json"]  # not in _unsorted/ either
    failed = I.Status(root).data["failed"]["1730000001.000100-acme-C0123.json"]
    assert failed["stage"] == "filter" and said in failed["error"]
    snap = I.snapshot(cfg, None, False)
    assert snap["failed"][0]["stage"] == "filter" and said in snap["failed"][0]["error"]
    assert any(said in e["error"] for e in snap["errors"])
    # the same adapter is not run again on every pass...
    assert I.process_inbox(cfg, root, route=route)["waiting"] == 1
    # ...and a mended one is
    path.write_text("def filter_message(record):\n    return {'text': 'ok'}, {'removedFiles': 0, 'redactions': 0}\n")
    os.utime(path, (time.time() + 5, time.time() + 5))
    route.answers = [{"choice": "shop", "confidence": 0.9}]
    assert I.process_inbox(cfg, root, route=route)["projects"] == 1 and not kept.exists()


def test_a_broken_extra_pattern_keeps_the_message_home(tmp_path):
    cfg = cfg_of(tmp_path, filter={"adapter": "builtin", "extraPatterns": ["(unclosed"]})
    root = C.orchestration_dir(cfg)
    kept = inbox(root, "1730000001.000100", "x")
    route = FakeRoute([])
    assert I.process_inbox(cfg, root, route=route)["failed"] == 1 and route.seen == [] and kept.exists()


def test_a_relative_adapter_path_is_refused(tmp_path):
    with pytest.raises(FI.FilterError, match="absolute"):
        FI.apply({"message": {"text": "x"}}, {"adapter": "my_filter.py"})


# ---------------------------------------------------------------- router adapters: what each one sends

def test_haiku_sends_the_prompt_as_system_and_the_choices_as_an_enum(tmp_path, monkeypatch):
    sent = []

    def post(url, headers, body, timeout=0):
        sent.append((url, headers, body))
        return {"content": [{"type": "tool_use", "name": "route", "input": {"choice": "booking", "confidence": 0.8}}]}

    monkeypatch.setattr(R, "post", post)
    cfg = cfg_of(tmp_path, router={"prompt": {"instructions": "どのプロジェクトか決める", "chitchat": "あいさつ"}})
    got = R.route({"workspace": "acme", "channel": "C0123", "user": "U1", "ts": "1.1", "text": "予約が取れない",
                   "permalink": "https://t/x", "removedFiles": 0, "redactions": 0}, cfg["router"])
    assert got == {"adapter": "haiku", "choice": "booking", "confidence": 0.8}
    url, headers, body = sent[0]
    assert url == "https://api.anthropic.com/v1/messages" and headers["x-api-key"] == "ant-key-QQ8"
    assert body["model"] == R.HAIKU_MODEL and body["tool_choice"] == {"type": "tool", "name": "route"}
    assert body["tools"][0]["input_schema"]["properties"]["choice"]["enum"] == ["shop", "booking", "chitchat"]
    assert "どのプロジェクトか決める" in body["system"] and "- shop: 在庫アプリ" in body["system"] and "- chitchat: あいさつ" in body["system"]
    assert "予約が取れない" in body["messages"][0]["content"] and "https://t/x" not in json.dumps(body)


def test_jev_asks_one_choice_question_with_the_projects_and_chitchat_as_criteria(tmp_path, monkeypatch):
    sent = []

    def post(url, headers, body, timeout=0):
        sent.append((url, headers, body))
        return {"model": "jev-1.13.0", "answers": {"route": {"type": "choice", "choice": "chitchat", "confidence": 0.97,
                                                              "probabilities": {"shop": 0.01, "booking": 0.02, "chitchat": 0.97}}}}

    monkeypatch.setattr(R, "post", post)
    cfg = cfg_of(tmp_path, router={"adapter": "jev", "prompt": {"instructions": "振り分ける", "chitchat": "雑談"}})
    got = R.route({"workspace": "acme", "channel": "C0123", "user": "U1", "ts": "1.1", "text": "おつかれ"}, cfg["router"])
    assert got == {"adapter": "jev", "choice": "chitchat", "confidence": 0.97}
    url, headers, body = sent[0]
    assert url == "https://api.typesafe.ai/v1/systemone" and headers["Authorization"] == "Bearer tsf-key-QQ9"
    assert body["model"] == "jev-latest" and "おつかれ" in body["state"]
    assert body["questions"] == {"route": {"type": "choice", "instructions": "振り分ける",
                                           "criteria": {"shop": "在庫アプリ", "booking": "予約サイト", "chitchat": "雑談"}}}


def test_a_router_adapter_of_ones_own_and_the_answers_that_are_refused(tmp_path, monkeypatch):
    path = tmp_path / "my_router.py"
    path.write_text("def route(message, prompt):\n    return {'choice': sorted(prompt['projects'])[0], 'confidence': 2}\n")
    cfg = cfg_of(tmp_path, router={"adapter": str(path)})
    assert R.route({"text": "x"}, cfg["router"]) == {"adapter": "path", "choice": "booking", "confidence": 1.0}
    monkeypatch.setattr(R, "post", lambda *a, **k: {"content": [{"type": "text", "text": "booking"}]})
    with pytest.raises(R.RouterError):
        R.route({"text": "x"}, cfg_of(tmp_path)["router"])
    with pytest.raises(R.RouterError, match="anthropicApiKey"):
        R.route({"text": "x"}, cfg_of(tmp_path, router={"anthropicApiKey": ""})["router"])
    with pytest.raises(R.RouterError, match="255"):
        R.choices({"projects": {f"p{i}": "" for i in range(255)}})


# ---------------------------------------------------------------- fetch: api

class FakeSlack:
    def __init__(self, history, replies=None, fail=None):
        self.history, self.replies, self.fail, self.calls = history, replies or {}, fail, []

    def __call__(self, method, token, params):
        self.calls.append((method, token, dict(params)))
        if self.fail and self.fail(method, params):
            raise FE.FetchError(f"{method}: ratelimited")
        if method == "auth.test":
            return {"ok": True, "url": "https://acme.slack.com/"}
        if method == "conversations.history":
            pages = self.history
            i = int(params.get("cursor") or 0)
            return {"ok": True, "messages": pages[i], "has_more": i + 1 < len(pages),
                    "response_metadata": {"next_cursor": str(i + 1) if i + 1 < len(pages) else ""}}
        if method == "conversations.replies":
            return {"ok": True, "messages": self.replies.get(params["ts"], [])}
        raise AssertionError(method)


def test_the_api_fetch_pages_reads_threads_skips_notices_and_moves_the_cursor(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    slack = FakeSlack(
        history=[[{"ts": "1730000003.000100", "user": "U1", "text": "three", "files": [{"name": "a.png"}]},
                  {"ts": "1730000002.000100", "subtype": "channel_join", "user": "U9", "text": "joined"}],
                 [{"ts": "1730000001.000100", "user": "U2", "text": "one", "thread_ts": "1730000001.000100", "reply_count": 1}]],
        replies={"1730000001.000100": [{"ts": "1730000001.000100", "text": "one"},
                                        {"ts": "1730000005.000100", "user": "U3", "text": "reply", "thread_ts": "1730000001.000100"}]})
    got = FE.fetch(cfg, root, get=slack, now=1730000100.0)
    assert got == {"fetched": 3, "errors": []}
    assert sorted(p.name for p in S.inbox_files(root)) == [
        "1730000001.000100-acme-C0123.json", "1730000003.000100-acme-C0123.json", "1730000005.000100-acme-C0123.json"]
    raw = json.loads((root / S.INBOX / "1730000003.000100-acme-C0123.json").read_text())
    assert raw["message"]["files"] == [{"name": "a.png"}] and raw["via"] == "api"     # raw as fetched; the filter drops it
    assert raw["permalink"] == "https://acme.slack.com/archives/C0123/p1730000003000100"
    reply = json.loads((root / S.INBOX / "1730000005.000100-acme-C0123.json").read_text())
    assert reply["permalink"].endswith("?thread_ts=1730000001.000100&cid=C0123")
    first = [c for c in slack.calls if c[0] == "conversations.history"][0][2]
    assert first["oldest"] == f"{1730000100.0 - 14 * 86400:.6f}" and first["channel"] == "C0123"   # the thread watch
    assert S.Cursor(root).get("acme", "C0123") == "1730000003.000100"
    assert stat.S_IMODE((root / S.INBOX).stat().st_mode) == 0o700
    # the next fetch starts from the cursor, and a message already in the inbox is not written twice
    slack.calls.clear()
    assert FE.fetch(cfg, root, get=slack, now=1730000200.0)["fetched"] == 0
    assert [c for c in slack.calls if c[0] == "conversations.history"][0][2]["oldest"] == f"{1730000200.0 - 14 * 86400:.6f}"


def test_what_the_intake_is_doing_is_kept_for_the_robot_while_it_works_and_cleared_after(tmp_path):
    """(14) the sorting factory's robot shows the stage: fetch, then filter / route with done / total; counts only."""
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    seen = []

    class Watching(FakeSlack):
        def __call__(self, method, token, params):
            seen.append(("get", I.work()))
            return super().__call__(method, token, params)

    def watch_filter(record, filter_cfg):
        seen.append(("filter", I.work()))
        return FI.apply(record, filter_cfg)

    route = FakeRoute([{"choice": "shop", "confidence": 0.9}, {"choice": "chitchat", "confidence": 0.95}])

    def watch_route(message, router_cfg):
        seen.append(("route", I.work()))
        return route(message, router_cfg)

    slack = Watching(history=[[{"ts": "1730000002.000100", "user": "U1", "text": "two"},
                               {"ts": "1730000001.000100", "user": "U1", "text": "one"}]])
    I.run_once(cfg, root, "manual", get=slack, now=1730000100.0, route=watch_route, apply_filter=watch_filter)
    stages = [(where, w.get("stage"), w.get("done"), w.get("total")) for where, w in seen]
    assert stages[0] == ("get", "fetch", 0, 0)
    assert [x for x in stages if x[0] != "get"] == [("filter", "filter", 0, 2), ("route", "route", 0, 2),
                                                    ("filter", "filter", 1, 2), ("route", "route", 1, 2)]
    assert all(set(w) == {"stage", "done", "total", "since"} for _where, w in seen)     # no path, no text
    assert I.work() == {}                                                                # cleared after the pass


def test_a_stage_left_by_a_pass_that_raised_is_dropped_after_a_while(monkeypatch):
    I._work("route", 1, 3)
    assert I.work()["stage"] == "route"
    monkeypatch.setitem(I._WORK, "now", {**I._WORK["now"], "since": I.now_ms() - I.WORK_STALE_SEC * 1000 - 1})
    assert I.work() == {}
    I._work(None)


def test_a_failing_channel_leaves_its_cursor_and_the_others_go_on(tmp_path):
    cfg = cfg_of(tmp_path, source={"workspaces": [{"name": "acme", "token": "t-1", "channels": ["C0123", "C0456"]},
                                                  {"name": "other", "token": "", "channels": ["C1"]}]})
    root = C.orchestration_dir(cfg)
    slack = FakeSlack(history=[[{"ts": "1730000003.000100", "user": "U1", "text": "x"}]],
                      fail=lambda m, p: m == "conversations.history" and p["channel"] == "C0123")
    got = FE.fetch(cfg, root, get=slack, now=1730000100.0)
    assert got["fetched"] == 1 and got["errors"] == ["acme/C0123: conversations.history: ratelimited", "other: no token"]
    assert S.Cursor(root).get("acme", "C0123") is None and S.Cursor(root).get("acme", "C0456") == "1730000003.000100"


# ---------------------------------------------------------------- threads (design 追記: 1 メッセージ 1 タスクにしない)

P, R1, R2 = "1730000001.000100", "1730050000.000100", "1730090000.000100"


def test_a_new_reply_to_a_thread_started_before_the_last_fetch_is_taken_and_follows_its_thread(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    # day 1: the first message, no reply yet; it is routed to shop
    slack = FakeSlack(history=[[{"ts": P, "user": "U1", "text": "在庫の画面が落ちる"}]])
    assert FE.fetch(cfg, root, get=slack, now=1730000100.0)["fetched"] == 1
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}])
    assert I.process_inbox(cfg, root, route=route, now=1730060000.0)["projects"] == 1
    assert S.Cursor(root).get("acme", "C0123") == P
    # day 2: nothing new in the channel, but the thread got a reply (history from the watch shows latest_reply)
    slack.history = [[{"ts": P, "user": "U1", "text": "在庫の画面が落ちる", "thread_ts": P, "reply_count": 1, "latest_reply": R1}]]
    slack.replies = {P: [{"ts": P, "text": "在庫の画面が落ちる"}, {"ts": R1, "user": "U2", "text": "直りました " + AWS, "thread_ts": P}]}
    slack.calls.clear()
    assert FE.fetch(cfg, root, get=slack, now=1730060000.0) == {"fetched": 1, "errors": []}
    hist = [c[2] for c in slack.calls if c[0] == "conversations.history"][0]
    assert hist["oldest"] == f"{1730060000.0 - 14 * 86400:.6f}"                  # read from the watch, not the cursor
    assert [c[2]["oldest"] for c in slack.calls if c[0] == "conversations.replies"] == [P]
    assert [p.name for p in S.inbox_files(root)] == [f"{R1}-acme-C0123.json"]
    got = I.process_inbox(cfg, root, route=route, now=1730060000.0)
    assert got["projects"] == 1 and got["followed"] == 1 and len(route.seen) == 1   # the router was not asked again
    reply = json.loads((root / f"projects/shop/{R1}-acme-C0123.json").read_text())
    assert reply["threadTs"] == P and reply["router"] == {"adapter": "thread", "choice": "shop", "confidence": 0.9}
    assert reply["text"] == "直りました [REDACTED:aws-access-key]"                # filtered like any other
    parent = json.loads((root / f"projects/shop/{P}-acme-C0123.json").read_text())
    assert parent["threadTs"] == P
    routes = (root / S.STATE / "routes.json").read_text()
    assert "在庫" not in routes and "直りました" not in routes
    # day 3: the same latest_reply: no replies call, nothing taken twice
    slack.calls.clear()
    assert FE.fetch(cfg, root, get=slack, now=1730070000.0)["fetched"] == 0
    assert [c for c in slack.calls if c[0] == "conversations.replies"] == []
    # past threadWatchDays the thread is no longer watched or followed
    assert FE.fetch(cfg, root, get=FakeSlack(history=[[]]), now=float(P) + 15 * 86400)["fetched"] == 0
    assert json.loads((root / S.STATE / "threads.json").read_text()) == {}


def test_an_old_thread_never_watched_gives_only_its_replies_after_the_cursor(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    S.ensure(root)
    S.Cursor(root).set("acme", "C0123", "1730040000.000100")
    slack = FakeSlack(history=[[{"ts": P, "text": "old", "thread_ts": P, "reply_count": 2, "latest_reply": R1}]],
                      replies={P: [{"ts": P}, {"ts": "1730030000.000100", "text": "before the cursor"}, {"ts": R1, "text": "after"}]})
    assert FE.fetch(cfg, root, get=slack, now=1730060000.0)["fetched"] == 1
    assert [p.name for p in S.inbox_files(root)] == [f"{R1}-acme-C0123.json"]


def test_a_reply_to_a_chitchat_thread_is_routed_again_and_the_next_reply_follows_that(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    inbox(root, P, "おつかれさまです")
    route = FakeRoute([{"choice": "chitchat", "confidence": 0.95}])
    assert I.process_inbox(cfg, root, route=route, now=1730060000.0)["chitchat"] == 1
    routes = root / S.STATE / "routes.json"
    assert files_under(root) == [] and (not routes.exists() or P not in routes.read_text())   # no trace of the chitchat
    inbox(root, R1, "ところで予約の画面が出ません", thread_ts=P)
    route.answers = [{"choice": "booking", "confidence": 0.8}]
    got = I.process_inbox(cfg, root, route=route, now=1730060000.0)
    assert got["projects"] == 1 and got["followed"] == 0 and route.seen[-1]["text"] == "ところで予約の画面が出ません"
    placed = json.loads((root / f"projects/booking/{R1}-acme-C0123.json").read_text())
    assert placed["router"]["adapter"] == "haiku" and placed["threadTs"] == P
    inbox(root, R2, "再起動したら出ました", thread_ts=P)
    got = I.process_inbox(cfg, root, route=route, now=1730060000.0)
    assert got["followed"] == 1 and len(route.seen) == 2
    assert files_under(root) == [f"projects/booking/{R1}-acme-C0123.json", f"projects/booking/{R2}-acme-C0123.json"]


def test_a_reply_waits_while_its_threads_first_message_is_held_in_the_inbox(tmp_path, monkeypatch):
    path = tmp_path / "f.py"
    path.write_text("def filter_message(record):\n    raise RuntimeError('down')\n")
    cfg = cfg_of(tmp_path, filter={"adapter": str(path)})
    root = C.orchestration_dir(cfg)
    inbox(root, P, "親")
    inbox(root, R1, "返信", thread_ts=P)
    route = FakeRoute([])
    got = I.process_inbox(cfg, root, route=route)
    assert got["failed"] == 1 and got["waiting"] == 1 and route.seen == []
    assert sorted(p.name for p in S.inbox_files(root)) == [f"{P}-acme-C0123.json", f"{R1}-acme-C0123.json"]


def test_thread_watch_days_is_read_and_checked(tmp_path):
    assert C.DEFAULT["source"]["threadWatchDays"] == 14
    write_cfg({"source": {"threadWatchDays": -1}})
    with pytest.raises(C.ConfigError, match="threadWatchDays"):
        C.load()
    cfg = cfg_of(tmp_path, source={"threadWatchDays": 0})
    root = C.orchestration_dir(cfg)
    slack = FakeSlack(history=[[]])
    FE.fetch(cfg, root, get=slack, now=1730060000.0)
    assert slack.calls[1][2]["oldest"] == f"{1730060000.0 - 24 * 3600:.6f}"     # 0: no watch, from the cursor only


# ---------------------------------------------------------------- fetch: connector (a claude of this test)

def fake_claude(tmp_path, out: str, rc: int = 0) -> Path:
    path = tmp_path / "bin" / "claude"
    path.parent.mkdir(exist_ok=True)
    log = tmp_path / "claude-argv.json"
    path.write_text(f"#!{sys.executable} -I\nimport json, os, sys\n"
                    f"json.dump({{'argv': sys.argv[1:], 'cwd': os.getcwd(), 'home': os.environ.get('HOME')}}, open({str(log)!r}, 'w'))\n"
                    f"sys.stdout.write({out!r})\nsys.exit({rc})\n")
    path.chmod(0o755)
    return path


def test_the_connector_runs_claude_with_the_slack_tools_only_and_writes_what_it_printed(tmp_path):
    answer = json.dumps({"type": "result", "result": "```json\n" + json.dumps([
        {"workspace": "acme", "channel": "C0123", "ts": "1730000001.000100", "user": "U1", "text": "在庫 " + AWS,
         "permalink": "https://t/p1", "files": [{"name": "a.pdf"}]},
        {"workspace": "acme", "channel": "C9999", "ts": "1730000002.000100", "text": "not asked for"}]) + "\n```"})
    claude = fake_claude(tmp_path, answer)
    cfg = cfg_of(tmp_path, source={"mode": "connector", "claudeCommand": str(claude)})
    root = C.orchestration_dir(cfg)
    assert FE.fetch(cfg, root, now=1730000100.0) == {"fetched": 1, "errors": []}
    seen = json.loads((tmp_path / "claude-argv.json").read_text())
    assert seen["argv"][0] == "-p" and seen["argv"][2:] == ["--output-format", "json", "--allowedTools", "mcp__claude_ai_Slack",
                                                         "--model", "claude-haiku-5-5"]
    assert 'workspace "acme", channel C0123' in seen["argv"][1]
    assert Path(seen["cwd"]).resolve() == (root / S.STATE).resolve()
    assert seen["home"] == str(tmp_path / "home")        # the test's HOME, never the real one
    raw = json.loads((root / S.INBOX / "1730000001.000100-acme-C0123.json").read_text())
    assert raw["via"] == "connector" and raw["message"]["files"] == [{"name": "a.pdf"}]
    assert S.Cursor(root).get("acme", "C0123") == "1730000001.000100"
    # through the filter like any other
    got = I.process_inbox(cfg, root, route=FakeRoute([{"choice": "shop", "confidence": 0.9}]))
    assert got["projects"] == 1
    placed = json.loads((root / "projects/shop/1730000001.000100-acme-C0123.json").read_text())
    assert placed["removedFiles"] == 1 and AWS not in placed["text"]


@pytest.mark.parametrize("given,want", [
    (None, ["--model", "claude-haiku-5-5"]),        # not written: the light model, the router's haiku
    ("claude-sonnet-5-5", ["--model", "claude-sonnet-5-5"]),
    ("", []),                                       # empty: no --model, claude's own default
])
def test_the_connector_passes_its_model_unless_it_is_empty(tmp_path, given, want):
    source = {"mode": "connector", "claudeCommand": str(fake_claude(tmp_path, "[]"))}
    if given is not None:
        source["connectorModel"] = given
    cfg = cfg_of(tmp_path, source=source)
    C.validate(cfg)
    assert FE.fetch(cfg, C.orchestration_dir(cfg), now=1730000100.0) == {"fetched": 0, "errors": []}
    argv = json.loads((tmp_path / "claude-argv.json").read_text())["argv"]
    assert argv[2:] == ["--output-format", "json", "--allowedTools", "mcp__claude_ai_Slack"] + want
    assert argv.count("--model") == len(want) // 2


def test_the_connector_model_default_is_the_routers_haiku():
    assert C.DEFAULT["source"]["connectorModel"] == R.HAIKU_MODEL == "claude-haiku-5-5"


@pytest.mark.parametrize("bad", [None, 3, "has space", "-p", "--dangerously-skip-permissions"])
def test_a_connector_model_that_is_not_a_name_is_refused(tmp_path, bad):
    cfg = cfg_of(tmp_path, source={"connectorModel": bad})
    with pytest.raises(C.ConfigError, match="connectorModel"):
        C.validate(cfg)


@pytest.mark.parametrize("out,rc,said", [("not json at all", 0, "no JSON array"), ("[]", 1, "exited 1")])
def test_a_connector_that_fails_writes_nothing_and_says_why(tmp_path, out, rc, said):
    cfg = cfg_of(tmp_path, source={"mode": "connector", "claudeCommand": str(fake_claude(tmp_path, out, rc))})
    root = C.orchestration_dir(cfg)
    got = FE.fetch(cfg, root)
    assert got["fetched"] == 0 and said in got["errors"][0] and S.inbox_files(root) == []


def test_the_connector_mode_shows_its_warning_and_api_does_not(tmp_path):
    api = I.snapshot(cfg_of(tmp_path), None, False)
    con = I.snapshot(cfg_of(tmp_path, source={"mode": "connector"}), None, False)
    assert api["modeNote"] is None and con["modeNote"] == "With mode connector, the messages pass through Claude (Anthropic) before the filter"
    assert C.DEFAULT["source"]["_modeNote"] == con["modeNote"]


# ---------------------------------------------------------------- the config file

def write_cfg(cfg: dict, mode: int = 0o600) -> Path:
    path = C.path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg))
    path.chmod(mode)
    return path


def test_the_config_is_read_from_viz_home_and_refused_when_others_can_read_it(tmp_path):
    assert C.path() == tmp_path / "home" / ".local" / "state" / "jui-viz" / "slack.json"
    assert C.load() is None
    write_cfg({"orchestrationDir": str(tmp_path / "o"), "schedule": {"everyHours": 6}})
    got = C.load()
    assert got["schedule"] == {"everyHours": 6, "at": "09:00"} and got["router"]["adapter"] == "haiku"
    C.path().chmod(0o644)
    with pytest.raises(C.ConfigError, match="chmod 600"):
        C.load()
    C.path().unlink()
    os.symlink(tmp_path / "elsewhere.json", C.path())
    with pytest.raises(C.ConfigError, match="regular"):
        C.load()


@pytest.mark.parametrize("over,said", [
    ({"source": {"mode": "rss"}}, "source.mode"),
    ({"source": {"workspaces": [{"name": "../x"}]}}, "workspace name"),
    ({"source": {"workspaces": [{"name": "ok", "channels": ["C1/.."]}]}}, "channel"),
    ({"schedule": {"at": "9時"}}, "HH:MM"),
    ({"router": {"confidenceMin": 2}}, "confidenceMin"),
    ({"router": {"prompt": {"projects": {"chitchat": "x"}}}}, "reserved"),
    ({"router": {"prompt": {"projects": {"../etc": "x"}}}}, "project id"),
])
def test_a_config_that_would_write_outside_its_folders_is_refused(tmp_path, over, said):
    write_cfg(over)
    with pytest.raises(C.ConfigError, match=said):
        C.load()


def test_the_status_has_no_key_and_no_message_text(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    inbox(root, "1730000001.000100", "秘密の本文 " + AWS)
    I.process_inbox(cfg, root, route=FakeRoute([R.RouterError("down")]))
    flat = json.dumps(I.snapshot(cfg, None, False), ensure_ascii=False)
    flat += "".join(p.read_text() for p in (root / S.STATE).glob("*.json"))      # and the state files on disk
    for secret in ("slk-tok-QQ7", "ant-key-QQ8", "tsf-key-QQ9", "秘密の本文", AWS):
        assert secret not in flat
    assert C.public_view(cfg)["router"]["anthropicApiKey"] is True and C.public_view(cfg)["source"]["workspaces"][0]["token"] is True


# ---------------------------------------------------------------- the schedule

def at(h, m, day=2):
    import datetime as dt
    return dt.datetime(2026, 11, day, h, m).timestamp()


def test_the_schedule_is_slots_from_at_every_n_hours_and_a_missed_slot_is_due():
    daily = {"everyHours": 24, "at": "09:00"}
    assert I.next_run(None, at(8, 0), daily) == at(9, 0)
    assert I.next_run(None, at(10, 0), daily) == at(9, 0, 3)
    assert I.next_run(int(at(9, 0) * 1000), at(10, 0), daily) == at(9, 0, 3)
    assert I.next_run(int(at(9, 0, 1) * 1000), at(10, 0), daily) == at(9, 0)       # missed while down: due now
    six = {"everyHours": 6, "at": "09:00"}
    assert I.next_run(int(at(9, 30) * 1000), at(10, 0), six) == at(15, 0)
    assert I.next_run(int(at(4, 0) * 1000), at(5, 0), six) == at(9, 0)              # slots before `at` count too (03:00)
    assert I.next_run(int(at(2, 0) * 1000), at(5, 0), six) == at(3, 0)
    assert I.next_run(None, at(10, 0), {"everyHours": 0, "at": "09:00"}) is None


def test_the_service_fetches_when_a_slot_is_due_and_by_hand_once_at_a_time(tmp_path):
    cfg = cfg_of(tmp_path, schedule={"everyHours": 24, "at": "09:00"})
    root = C.orchestration_dir(cfg)
    recent = f"{int(time.time()) - 60}.000100"      # inside the first fetch's window (the last 24 h)
    slack = FakeSlack(history=[[{"ts": recent, "user": "U1", "text": "x"}]])
    route = FakeRoute([{"choice": "shop", "confidence": 0.9}])
    snaps = []

    def slow_route(message, router_cfg):
        # the inbox is sorted after lastRun is on disk, and the fetch runs until it is done: a sort that takes a while
        # (a loaded runner, run 42454156041) is still the scheduled fetch's, and a press then is refused (409)
        time.sleep(0.4)
        return route(message, router_cfg)

    svc = I.Service(snaps.append, watch_sec=0.05, loader=lambda: cfg,
                    work_kw={"get": slack, "route": slow_route})

    async def go():
        task = asyncio.create_task(svc.run())
        await asyncio.sleep(0.3)
        assert I.Status(root).data.get("since") and "lastRun" not in I.Status(root).data   # counting starts, nothing fetched
        st = I.Status(root)
        st.data["since"] = int((time.time() - 2 * 86400) * 1000)    # a slot passed since
        st.save()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if "lastRun" in I.Status(root).data and not svc.running:   # the scheduled fetch has ended, its sort too
                break
        assert I.Status(root).data["lastRun"]["trigger"] == "schedule" and not svc.running
        assert svc.start_fetch()[0] == 202
        assert svc.start_fetch() == (409, {"error": "a fetch is running"})
        await svc._task
        task.cancel()

    asyncio.run(go())
    assert files_under(root) == [f"projects/shop/{recent}-acme-C0123.json"]    # once: the manual fetch took nothing again
    last = snaps[-1]
    assert last["lastRun"]["trigger"] == "manual" and last["counts"] == {"inbox": 0, "projects": {"shop": 1}, "unsorted": 0}
    assert last["nextRun"] > time.time() * 1000 and last["running"] is False


def test_the_service_without_a_config_says_so_and_fetches_nothing(tmp_path):
    svc = I.Service(loader=lambda: None)
    assert svc.status()["configured"] is False
    assert asyncio.run(_start(svc))[0] == 409

    def bad():
        raise C.ConfigError("readable by others")
    assert I.Service(loader=bad).status() == {"configured": False, "error": "readable by others", "running": False,
                                             "configPath": str(C.path()).replace(str(Path.home()), "~", 1)}


def test_the_slack_slice_carries_no_path_under_the_home(tmp_path, monkeypatch):
    """Every slice writes a path from ~ (the talk e2e reads /api/snapshot for the home's path): the config's path,
    the orchestration folder and an error that names a file."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    err = I.snapshot(None, f"{tmp_path}/.local/state/jui-viz/slack.json is readable by others", False)
    assert err["configPath"] == "~/.local/state/jui-viz/slack.json" and err["error"].startswith("~/.local/")
    cfg = C._merge(C.DEFAULT, {"orchestrationDir": str(tmp_path / "orch")})
    snap = I.snapshot(cfg, None, False)
    assert snap["orchestrationDir"] == "~/orch" and str(tmp_path) not in json.dumps(snap)


async def _start(svc):
    return svc.start_fetch()


def test_a_key_shaped_word_in_an_error_never_reaches_the_slack_slice(tmp_path, monkeypatch):
    """The room shows the last fetch's first error as written (2026-11-02-viz-slack-fetch-errors-not-shown-in-room):
    a Slack or Anthropic key's shape in it is masked before the slice."""
    monkeypatch.setenv("HOME", str(tmp_path))
    slack_key = "xox" + "b-1234-5678-abcdef"
    anthropic_key = "sk-" + "ant-api03-abc_DEF-123"
    snap = I.snapshot(None, f"bad token {slack_key} and {anthropic_key}", False)
    assert slack_key not in json.dumps(snap) and anthropic_key not in json.dumps(snap)
    assert snap["error"] == "bad token … and …"


@pytest.mark.parametrize("raw, plain", [
    ("B&amp;S の件 &lt;急ぎ&gt;", "B&S の件 <急ぎ>"),
    ("<@U02HX> さん <#C1|general> で <!here>", "@U02HX さん #general で @here"),
    ("<@U1|taro> と <!subteam^S1|@devs>", "@taro と @devs"),
    ("<https://a.example/c?x=1&amp;y=2|設計書> と <https://a.example> と <mailto:a@b.example|a@b.example>",
     "設計書 (https://a.example/c?x=1&y=2) と https://a.example と a@b.example"),
    ("a < b and c &gt; d", "a < b and c > d"),
])
def test_slacks_marks_and_escapes_are_written_out(raw, plain):
    from jui_cli.viz.slack import filters
    assert filters.slack_plain(raw) == plain


def test_the_filter_router_and_robot_get_the_text_as_written():
    """2.4.0: the room showed B&amp;S: Slack's Web API sends & < > escaped; filters.apply writes them out first, so the
    redaction, the router and the projects/ file (the robot reads it) all see the text as written."""
    from jui_cli.viz.slack import filters
    record = {"workspace": "acme", "channel": "C1", "ts": "1730000001.000100", "permalink": "",
              "message": {"ts": "1730000001.000100", "user": "U1", "text": "B&amp;S の件 <@U2> &lt;b&gt;"}}
    got = filters.apply(record, {"adapter": "builtin", "extraPatterns": []})
    assert got["text"] == "B&S の件 @U2 <b>"
    assert record["message"]["text"] == "B&amp;S の件 <@U2> &lt;b&gt;"            # the inbox record is left as fetched


# ---------------------------------------------------------------- a fault never stops the intake

def test_a_router_that_throws_once_holds_only_its_own_message(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    a, b = "1730000001.000100", "1730000002.000100"
    inbox(root, a, "first")
    inbox(root, b, "second")
    route = FakeRoute([RuntimeError("boom"), {"choice": "shop", "confidence": 0.9}])
    got = I.process_inbox(cfg, root, route=route, now=1730060000.0)
    assert got["failed"] == 1 and got["projects"] == 1
    assert files_under(root) == [f"inbox/{a}-acme-C0123.json", f"projects/shop/{b}-acme-C0123.json"]
    st = I.Status(root).data
    assert st["failed"][f"{a}-acme-C0123.json"]["stage"] == "router"
    assert st["failed"][f"{a}-acme-C0123.json"]["error"] == "unexpected RuntimeError: boom"
    assert st["errors"][0]["error"] == f"router: {a}-acme-C0123.json: unexpected RuntimeError: boom"
    # retried like any router failure (here by hand)
    I.process_inbox(cfg, root, route=FakeRoute([{"choice": "booking", "confidence": 0.9}]), force=True, now=1730060000.0)
    assert files_under(root) == [f"projects/booking/{a}-acme-C0123.json", f"projects/shop/{b}-acme-C0123.json"]


def test_a_filter_that_throws_holds_only_its_own_message(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    a, b = "1730000001.000100", "1730000002.000100"
    inbox(root, a, "first")
    inbox(root, b, "second")

    def apply_filter(record, filter_cfg):
        if record["ts"] == a:
            raise KeyError("text")
        return FI.apply(record, filter_cfg)

    got = I.process_inbox(cfg, root, route=FakeRoute([{"choice": "shop", "confidence": 0.9}]), apply_filter=apply_filter)
    assert got["failed"] == 1 and got["projects"] == 1
    assert I.Status(root).data["failed"][f"{a}-acme-C0123.json"]["error"] == "unexpected KeyError: 'text'"


def test_a_fault_in_a_pass_is_written_counted_and_the_next_pass_runs(tmp_path, monkeypatch):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)
    I.start_schedule(root)
    ts = f"{int(time.time()) - 60}.000100"
    inbox(root, ts, "x")
    real, faults = I.process_inbox, []

    def flaky(*a, **k):
        if len(faults) < 3:
            faults.append(1)
            raise RuntimeError("disk said no")
        return real(*a, **k)

    monkeypatch.setattr(I, "process_inbox", flaky)
    svc = I.Service(watch_sec=0.05, loader=lambda: cfg, work_kw={"route": FakeRoute([{"choice": "shop", "confidence": 0.9}])})

    async def go():
        task = asyncio.create_task(svc.run())
        for _ in range(100):
            await asyncio.sleep(0.05)
            if (root / f"projects/shop/{ts}-acme-C0123.json").exists():
                break
        alive = not task.done()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return alive

    assert asyncio.run(go()) is True
    assert files_under(root) == [f"projects/shop/{ts}-acme-C0123.json"]
    errors = I.Status(root).data["errors"]
    same = [e for e in errors if e["error"] == "intake: unexpected RuntimeError: disk said no"]
    assert len(same) == 1 and same[0]["count"] == 3 and same[0]["firstAt"] <= same[0]["at"]
    assert svc.status()["errors"][0]["count"] == 3


def test_an_unexpected_fault_in_a_fetch_answers_500_and_is_written(tmp_path):
    cfg = cfg_of(tmp_path)
    root = C.orchestration_dir(cfg)

    def get(method, token, params):
        raise RuntimeError("socket closed")

    svc = I.Service(loader=lambda: cfg, work_kw={"get": get})
    code, body = asyncio.run(svc.fetch_now("manual"))
    assert code == 500 and body == {"error": "manual fetch: unexpected RuntimeError: socket closed"}
    assert svc.running is False
    assert I.Status(root).data["errors"][0]["error"] == "manual fetch: unexpected RuntimeError: socket closed"


def test_the_same_error_again_is_one_entry_counted_and_the_others_stay(tmp_path):
    root = tmp_path / "orch"
    S.ensure(root)
    st = I.Status(root)
    st.error("other: one")
    for _ in range(50):
        st.error("loop: same")
    st.error("other: two")
    errors = st.data["errors"]
    assert [e["error"] for e in errors] == ["other: two", "loop: same", "other: one"]
    assert errors[1]["count"] == 50 and errors[1]["firstAt"] <= errors[1]["at"] and errors[0]["count"] == 1
    for i in range(I.ERRORS_KEPT + 5):
        st.error(f"many: {i}")
    assert len(st.data["errors"]) == I.ERRORS_KEPT
