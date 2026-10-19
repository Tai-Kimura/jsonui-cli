"""The talk view's WebSocket contract (jui_cli/viz/talk_contract.json, TALK_CONTRACT.md): sample frames and
requests conform, and each kind of break is caught (so the validator both sides test against has arms).

The samples are the reference both sides build to: ``SAMPLES`` is importable (the page's side can feed its own
fixtures through ``talk_contract.validate`` the same way).
"""
from __future__ import annotations

import copy

import pytest

from jui_cli.viz import talk_contract as C

CONV = "t-0123456789abcdef"
PEER = {"key": "s-peer", "agentId": "s-peer", "sessionId": "s-peer", "name": "jsonui-agents-for-claude-dd",
        "kind": "session", "alive": True, "goneAt": None, "removeAt": None}
MSG_OUT = {"id": "m-0b7c1f2a-1111-4222-8333-444455556666", "msgId": "0b7c1f2a-1111-4222-8333-444455556666",
           "convId": CONV, "dir": "out", "fromName": "jsonui-agents-for-claude-cd", "toName": "jsonui-agents-for-claude-dd",
           "at": 1_760_900_000_000, "deliveredAt": 1_760_900_000_800, "readAt": 1_760_900_001_600, "state": "read",
           "text": "2.3.6 の配信を始めます。\n\n- 版の表は後で", "cut": False, "summary": "2.3.6 の配信", "seen": "both",
           "via": "session", "merged": False}
MSG_UNDELIVERED = {**MSG_OUT, "id": "u-toolu_01ABC", "msgId": None, "deliveredAt": None, "readAt": None,
                   "state": "undelivered", "seen": "sender", "via": "external"}
MSG_SUB = {**MSG_OUT, "id": "u-toolu_02DEF", "msgId": None, "dir": "in", "state": "read", "via": "parent",
           "fromName": "a1b2c3d4e5f6a7b8", "toName": "main"}
CONVERSATION = {"id": CONV, "owner": "s-owner", "peer": PEER, "lastAt": 1_760_900_000_000,
                "preview": "2.3.6 の配信を始めます。", "lastDir": "out", "unread": 0, "count": 3}
GONE = {**CONVERSATION, "peer": {**PEER, "alive": False, "goneAt": 1_760_900_100_000, "removeAt": 1_760_903_700_000}}

SAMPLES = {
    "talk.open": {"type": "talk.open", "reqId": 7, "agentId": "s-owner"},
    "talk.close": {"type": "talk.close"},
    "talk.get": {"type": "talk.get", "reqId": "r8", "agentId": "s-owner", "convId": CONV, "before": MSG_OUT["id"], "limit": 50},
    "talk.seen": {"type": "talk.seen", "reqId": 9, "agentId": "s-owner", "convId": CONV, "upTo": 1_760_900_000_000},
    "talk.list": {"type": "talk.list", "reqId": 7, "agentId": "s-owner", "items": [CONVERSATION, GONE], "more": False},
    "talk.messages": {"type": "talk.messages", "reqId": "r8", "agentId": "s-owner", "convId": CONV,
                      "items": [MSG_UNDELIVERED, MSG_SUB, MSG_OUT], "more": True},
    "talk.badges": {"type": "talk.badges", "counts": {"s-owner": 2, "a1b2c3d4e5f6a7b8": 1}},
    "talk.update": {"type": "talk.update", "agentId": "s-owner", "ops": [
        {"op": "message", "convId": CONV, "message": MSG_OUT},
        {"op": "conv", "conv": GONE},
        {"op": "remove", "convId": CONV, "reason": "peer-ended"}]},
}


@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_each_sample_conforms(kind):
    assert C.validate(SAMPLES[kind]) == []


def test_every_frame_and_request_of_the_contract_has_a_sample():
    root = C.load()
    assert set(SAMPLES) == set(root["frames"]) | set(root["requests"])


def _broken(kind, change):
    frame = copy.deepcopy(SAMPLES[kind])
    change(frame)
    return C.validate(frame)


@pytest.mark.parametrize("kind,change,expect", [
    ("talk.list", lambda f: f["items"][0].pop("unread"), "missing 'unread'"),
    ("talk.list", lambda f: f["items"][0].__setitem__("extra", 1), "unexpected key 'extra'"),
    ("talk.list", lambda f: f["items"][0].__setitem__("id", "t-XYZ"), "does not match"),
    ("talk.list", lambda f: f["items"][0]["peer"].__setitem__("kind", "robot"), "is not one of"),
    ("talk.list", lambda f: f["items"][0].__setitem__("preview", "x" * 121), "longer than 120"),
    ("talk.list", lambda f: f.__setitem__("items", [CONVERSATION] * 201), "more than 200"),
    ("talk.messages", lambda f: f["items"][0].__setitem__("text", "x" * 20_001), "longer than 20000"),
    ("talk.messages", lambda f: f["items"][0].__setitem__("state", "lost"), "is not one of"),
    ("talk.messages", lambda f: f["items"][0].__setitem__("at", True), "is not integer"),
    ("talk.messages", lambda f: f["items"][0].__setitem__("id", "x-1"), "does not match"),
    ("talk.messages", lambda f: f["items"][0].__setitem__("path", "/tmp/a.jsonl"), "unexpected key 'path'"),
    ("talk.update", lambda f: f["ops"][0].__setitem__("op", "replace"), "of oneOf"),
    ("talk.update", lambda f: f["ops"][2].__setitem__("reason", "gone"), "of oneOf"),
    ("talk.update", lambda f: f.__setitem__("ops", []), "fewer than 1"),
    ("talk.get", lambda f: f.__setitem__("limit", 101), "> 100"),
    ("talk.badges", lambda f: f["counts"].__setitem__("s-zero", 0), "< 1"),
    ("talk.badges", lambda f: f["counts"].__setitem__("bad id/../x", 1), "(a key)"),
    ("talk.badges", lambda f: f["counts"].__setitem__("s-text", "3"), "is not integer"),
    ("talk.badges", lambda f: f.__setitem__("preview", "本文"), "unexpected key 'preview'"),
    ("talk.badges", lambda f: f.__setitem__("counts", {f"s-{i}": 1 for i in range(501)}), "more than 500 keys"),
    ("talk.open", lambda f: f.pop("agentId"), "missing 'agentId'"),
    ("talk.seen", lambda f: f.__setitem__("upTo", -1), "< 0"),
])
def test_a_break_is_caught(kind, change, expect):
    problems = _broken(kind, change)
    assert any(expect in p for p in problems), problems


def test_an_unknown_type_is_refused():
    assert C.validate({"type": "talk.send", "text": "hi"}) == ["type 'talk.send' is not a talk frame or request"]


def test_there_is_no_send_request_in_the_contract():
    """依頼者の確定（10-20）: トークから送らない。送る口は約束に無い。"""
    root = C.load()
    assert not any("send" in k or "post" in k for k in root["requests"])
    assert not any("text" in s.get("properties", {}) for s in root["requests"].values())


def test_badges_carry_counts_only():
    """The badge frame has no place for a body, a summary, a name or a path: only robot ids and numbers."""
    schema = C.load()["frames"]["talk.badges"]
    assert set(schema["properties"]) == {"type", "counts"}
    assert schema["properties"]["counts"]["additionalProperties"] == {"type": "integer", "minimum": 1}


def test_limits_match_the_schema():
    lim, root = C.limits(), C.load()
    assert root["$defs"]["message"]["properties"]["text"]["maxLength"] == lim["textMax"]
    assert root["$defs"]["conversation"]["properties"]["preview"]["maxLength"] == lim["previewMax"]
    assert root["frames"]["talk.list"]["properties"]["items"]["maxItems"] == lim["listMax"]
    assert root["frames"]["talk.messages"]["properties"]["items"]["maxItems"] == lim["pageMax"]
    assert root["frames"]["talk.update"]["properties"]["ops"]["maxItems"] == lim["opsMax"]
    assert root["requests"]["talk.get"]["properties"]["limit"]["maximum"] == lim["pageMax"]
    assert lim["graceSecDefault"] == 3600
