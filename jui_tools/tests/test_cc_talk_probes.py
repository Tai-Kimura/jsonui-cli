"""The talk view's probes (tools/cc_watch/probes.py: talk_send_input, talk_msg_id, talk_origin, talk_envelope).

They read the machine's own transcripts (the watcher passes the config folder's projects/ with --live). Here a
folder written in the measured shapes gives the green shape; each shape the talk code reads, renamed, changes the
probe's value (the watcher's red); without a folder they report skipped, like the session probes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from cc_watch import probes as P  # noqa: E402
from cc_watch import watch as W  # noqa: E402

GREEN = {
    "talk_send_input": {"to": "all", "message": "all", "summary": "seen"},
    "talk_msg_id": {"result_has_msg_id": True, "origin_has_msg_id": True, "uuid_like": "all", "both_sides": True},
    "talk_origin": {"peer": {k: "all" for k in P.PEER_ORIGIN_KEYS}, "child": {k: "all" for k in P.CHILD_ORIGIN_KEYS},
                    "coordinator": "seen", "queued_command": "all"},
    "talk_envelope": {"cross_session": "all", "closed": "all", "agent_message": "seen"},
}
MID = "0b7c1f2a-1111-4222-8333-444455556666"


def records():
    return {
        "send": {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "SendMessage",
                                                               "input": {"to": "peer-b", "message": "本文", "summary": "要約"}}]}},
        "result": {"type": "user", "toolUseResult": {"success": True, "msg_id": MID},
                   "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]}},
        "peer": {"type": "user", "isMeta": True, "origin": {"kind": "peer", "msg_id": MID, "from": "uds:/tmp/s/1.sock",
                                                              "verifiedPeerPid": 1, "name": "peer-a", "body": "本文"}},
        "queued": {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "x",
                                                        "origin": {"kind": "peer", "msg_id": MID, "from": "uds:/tmp/s/1.sock",
                                                                   "verifiedPeerPid": 1, "name": "peer-a", "body": "本文"}}},
        "child": {"type": "user", "isMeta": True, "origin": {"kind": "peer", "senderTaskId": "a1b2c3", "from": "a1b2c3", "body": "報告"}},
        "coord": {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "指示", "origin": {"kind": "coordinator"}}},
        "enqueue": {"type": "queue-operation", "operation": "enqueue",
                    "content": '<cross-session-message from="uds:/tmp/s/1.sock" from-name="peer-a">\n本文\n</cross-session-message>'},
        "agent_msg": {"type": "queue-operation", "operation": "enqueue", "content": '<agent-message from="a1b2c3">\n報告\n</agent-message>'},
    }


def folder(tmp_path, recs) -> Path:
    projects = tmp_path / "projects"
    (projects / "-work").mkdir(parents=True)
    (projects / "-work" / "s.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs.values()))
    return projects


def shapes(projects):
    ctx = P.Context(run=lambda argv: (0, ""), transcripts=projects)
    return {name: P.PROBES[name](ctx) for name in GREEN}


def test_the_measured_shapes_are_green(tmp_path):
    assert shapes(folder(tmp_path, records())) == GREEN


def test_without_a_folder_the_talk_probes_are_skipped():
    ctx = P.Context(run=lambda argv: (0, ""))
    for name in GREEN:
        assert P.PROBES[name](ctx) == {"skipped": "no transcripts folder (run with --live)"}


def _rename(recs, kind, path, new):
    rec = recs[kind]
    *head, last = path
    for k in head:
        rec = rec[k]
    rec[new] = rec.pop(last)
    return recs


@pytest.mark.parametrize("kind,path,probe", [
    ("send", ["message", "content", 0, "input", "to"], "talk_send_input"),
    ("result", ["toolUseResult", "msg_id"], "talk_msg_id"),
    ("peer", ["origin", "msg_id"], "talk_origin"),
    ("peer", ["origin", "verifiedPeerPid"], "talk_origin"),
    ("peer", ["origin", "body"], "talk_origin"),
    ("child", ["origin", "senderTaskId"], "talk_origin"),
])
def test_a_renamed_field_changes_its_probe(tmp_path, kind, path, probe):
    recs = _rename(records(), kind, path, "renamed")
    assert shapes(folder(tmp_path, recs))[probe] != GREEN[probe]


def test_a_changed_envelope_changes_its_probe(tmp_path):
    recs = records()
    recs["enqueue"]["content"] = '<cross-session-message from="uds:/tmp/s/1.sock" sender="peer-a">本文</cross-session-message>'
    assert shapes(folder(tmp_path, recs))["talk_envelope"] != GREEN["talk_envelope"]


def test_msg_ids_that_stop_matching_change_the_probe(tmp_path):
    recs = records()
    recs["peer"]["origin"]["msg_id"] = recs["queued"]["attachment"]["origin"]["msg_id"] = "ffffffff-1111-4222-8333-444455556666"
    assert shapes(folder(tmp_path, recs))["talk_msg_id"]["both_sides"] is False


def test_the_watcher_hands_the_folder_to_the_probes_only_when_live(tmp_path):
    seen = []
    real = P.talk_send_input

    def spy(ctx):
        seen.append(ctx.transcripts)
        return real(ctx)

    P.PROBES["talk_send_input"] = spy
    try:
        projects = folder(tmp_path, records())
        fake = lambda argv: (0, "2.1.300 (Claude Code)" if argv == ["--version"] else "")  # noqa: E731
        W.run(tmp_path / "repo", tmp_path / "state", live=False, runner=fake, fetch=lambda url: "{}", notify=lambda t: [])
        W.run(tmp_path / "repo", tmp_path / "state2", live=True, runner=fake, fetch=lambda url: "{}", notify=lambda t: [],
              session_maker=lambda cli, work: P.Session(config_dir=work), transcripts=lambda: projects)
    finally:
        P.PROBES["talk_send_input"] = real
    assert seen == [None, projects]


# ---- the window (ticket 2026-10-22-cc-dependency-watch-red: two reds of the window, not of Claude Code) -------------
DENIED = "Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Merge Without Review]"


def _denial(text: str) -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_9", "is_error": True,
                                                     "content": text}]}}


def _files(tmp_path, by_age: list[list[dict]]) -> Path:
    """One transcript per list, the first the oldest (an hour apart, all within the window)."""
    import os
    import time
    projects = tmp_path / "projects"
    (projects / "-work").mkdir(parents=True)
    now = time.time()
    for i, recs in enumerate(by_age):
        f = projects / "-work" / f"s{i}.jsonl"
        f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
        os.utime(f, (now - (len(by_age) - i) * 3600, now - (len(by_age) - i) * 3600))
    return projects


def _ctx(projects):
    return P.Context(run=lambda argv: (0, ""), transcripts=projects)


def test_a_denial_in_a_large_files_head_is_seen(tmp_path, monkeypatch):
    """The day before's denials sat in a 61 MB file's head, past the 16 MB tail read: the shape said unseen. The
    denials are read from every file of the window, whole."""
    monkeypatch.setattr(P, "TALK_FILE_BYTES", 4096)
    filler = [{"type": "user", "message": {"content": "x" * 200}} for _ in range(100)]   # ~30 KB after the denial
    projects = _files(tmp_path, [[_denial(DENIED)] + filler])
    assert P.auto_mode_denial(_ctx(projects)) == {"known": "all", "reason": "all", "no_verdict": "unseen"}


def test_a_commands_own_output_quoting_auto_mode_is_not_a_denial(tmp_path):
    quoted = "Exit code 2\nREFUSE: not an additive conflict:\n  POST /api/denial    a card of a call stopped by auto mode"
    projects = _files(tmp_path, [[_denial(DENIED), _denial(quoted)]])
    assert P.auto_mode_denial(_ctx(projects))["known"] == "all"


def test_the_newest_records_are_kept_not_the_oldest(tmp_path, monkeypatch):
    """The window kept the last TALK_KEEP appended, and the newest file is read first: it kept the oldest files'
    records. An old form (no verifiedPeerPid) in the oldest file decides nothing once newer records fill the keep."""
    monkeypatch.setattr(P, "TALK_KEEP", 2)
    peer = records()["peer"]
    old = json.loads(json.dumps(peer))
    del old["origin"]["verifiedPeerPid"]
    projects = _files(tmp_path, [[old], [peer, peer]])
    assert P.talk_origin(_ctx(projects))["peer"]["verifiedPeerPid"] == "all"
    projects2 = _files(tmp_path / "b", [[peer, peer], [old]])                   # the old form is the newest: seen
    assert P.talk_origin(_ctx(projects2))["peer"]["verifiedPeerPid"] == "some"


def test_the_two_sides_pair_on_every_msg_id_of_the_window(tmp_path, monkeypatch):
    """The newest TALK_KEEP sent and the newest received are mostly other messages (the other side of a send is in
    another session's file): the pairing reads every msg_id the window read."""
    monkeypatch.setattr(P, "TALK_KEEP", 1)
    r = records()
    other = json.loads(json.dumps(r["peer"]))
    other["origin"]["msg_id"] = "ffffffff-1111-4222-8333-444455556666"
    # the matching receipt between two others: neither the oldest kept nor the newest kept is it
    projects = _files(tmp_path, [[other], [r["send"], r["result"]], [r["peer"]], [other]])
    assert P.talk_msg_id(_ctx(projects))["both_sides"] is True
