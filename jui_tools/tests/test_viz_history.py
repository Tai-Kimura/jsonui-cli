"""The 応答の履歴 tab's server side (jui_cli/viz/sources/history.py, World.history, history.get; 10-18).

A fake projects folder under tmp_path; every transcript is written here. Nothing reads the real ~/.claude, and the
end-to-end arm runs on a free port with JUI_VIZ_HOME / XDG_STATE_HOME taken out of the environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket

from aiohttp.test_utils import TestClient, TestServer

from jui_cli.viz import export_demo
from jui_cli.viz.config import VizConfig
from jui_cli.viz.ingest import World
from jui_cli.viz.server import ServerContext, make_app
from jui_cli.viz.sources import history as H
from jui_cli.viz.sources.transcripts import project_dir_name
from jui_cli.viz.state import VizState

SID = "11111111-2222-4333-8444-555555555555"
CWD = "/work/hist-app"
TOKEN = "t" * 43
MARK = "HISTORY-BODY-MARK-7f3a"


def _user(text, ts="2026-10-18T09:00:00Z", **extra):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}, **extra}


def _asst(blocks, mid="m1", ts="2026-10-18T09:00:01Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"id": mid, "role": "assistant", "content": blocks}}


def _result(use_id, text, error=False):
    return {"type": "user", "timestamp": "2026-10-18T09:00:02Z",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": text, "is_error": error}]}}


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return path


def _projects(tmp_path):
    return tmp_path / ".claude" / "projects"


def _main_path(tmp_path):
    return _projects(tmp_path) / project_dir_name(CWD) / f"{SID}.jsonl"


CONVERSATION = [
    _user("テストの結果が見えない件を直して"),
    _user("Another Claude session sent a message:\n<cross-session-message from=\"uds:/tmp/x.sock\" from-name=\"jsonui-5b\">\n票を振りました\n</cross-session-message>"),
    _user("<system-reminder>\nnote from the harness\n</system-reminder>", isMeta=True),
    _user("[Subagent hand-back] The text below is the final report"),
    _asst([{"type": "thinking", "thinking": "THINK-SECRET-TEXT", "signature": "x"}], mid="m1"),
    _asst([{"type": "text", "text": "## 直しました\n- **太字** と `code`"}], mid="m1"),
    _asst([{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls -la", "description": "一覧を見る"}}], mid="m2"),
    _result("toolu_1", "total 0"),
    {"type": "api-request-blob", "message": {"role": "user", "content": [{"type": "text", "text": "API-BLOB-TEXT"}]}},
    {"type": "attachment", "attachment": {"type": "hook_success"}},
    _user([{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}]),
]


def test_the_conversation_as_the_tab_shows_it(tmp_path):
    path = _write(_main_path(tmp_path), CONVERSATION)
    got = H.reader(_projects(tmp_path))(SID, CWD, str(path))
    kinds = [(i["kind"], i.get("text") or i.get("name") or i.get("label") or "") for i in got["items"]]
    assert kinds == [
        ("user", "テストの結果が見えない件を直して"),
        ("peer", "票を振りました"),
        ("harness", "<system-reminder>\nnote from the harness\n</system-reminder>"),
        ("harness", "[Subagent hand-back] The text below is the final report"),
        ("thought", ""),
        ("assistant", "## 直しました\n- **太字** と `code`"),
        ("tool", "Bash"),
        ("image", ""),
    ], kinds
    peer = got["items"][1]
    assert peer["from"] == "jsonui-5b"
    assert [i["label"] for i in got["items"] if i["kind"] == "harness"] == ["システムの注記", "サブエージェントの報告"]
    tool = got["items"][6]
    assert tool["description"] == "一覧を見る" and tool["in"] == "ls -la" and tool["out"] == "total 0" and tool["error"] is False
    raw = json.dumps(got, ensure_ascii=False)
    assert "THINK-SECRET-TEXT" not in raw and "API-BLOB-TEXT" not in raw and "AAAA" not in raw


def test_only_the_last_items_max_and_every_text_cut(tmp_path):
    records = [_user(f"指示 {n}") for n in range(H.ITEMS_MAX + 60)]
    records.append(_asst([{"type": "text", "text": "x" * (H.TEXT_MAX + 500)}], mid="big"))
    path = _write(_main_path(tmp_path), records)
    got = H.reader(_projects(tmp_path))(SID, CWD, str(path))
    assert len(got["items"]) == H.ITEMS_MAX and got["more"] is True
    assert got["items"][0]["text"] == f"指示 {60 + 1}" and got["items"][-1]["kind"] == "assistant"
    assert len(got["items"][-1]["text"]) == H.TEXT_MAX and got["items"][-1]["cut"] is True


def test_it_reads_from_the_end_not_the_whole_file(tmp_path):
    filler = [{"type": "progress", "pad": "p" * 1000}] * 20_000              # about 20 MB before the conversation
    path = _write(_main_path(tmp_path), filler + [_user(f"最近の指示 {n}") for n in range(10)])
    size = path.stat().st_size
    got = H.reader(_projects(tmp_path))(SID, CWD, str(path))
    assert size > 15 * 1_048_576
    assert got["bytes"] <= H.BYTES_MAX < size                               # the cap: never the whole file
    assert [i["text"] for i in got["items"]] == [f"最近の指示 {n}" for n in range(10)]
    # enough items near the end: it stops after a chunk or two
    path2 = _write(_projects(tmp_path) / project_dir_name(CWD) / "22222222-2222-4333-8444-555555555555.jsonl",
                   filler + [_user(f"指示 {n}") for n in range(200)])
    got2 = H.reader(_projects(tmp_path))("22222222-2222-4333-8444-555555555555", CWD, str(path2))
    assert len(got2["items"]) == H.ITEMS_MAX and got2["bytes"] <= 2 * H.CHUNK, got2["bytes"]


def test_a_line_too_long_is_skipped_and_the_rest_still_reads(tmp_path):
    huge = _result("toolu_9", "y" * (H.LINE_MAX + 10))
    path = _write(_main_path(tmp_path), [_user("前"), huge, _user("後")])
    got = H.reader(_projects(tmp_path))(SID, CWD, str(path))
    assert [i["text"] for i in got["items"]] == ["前", "後"]


def test_a_second_read_of_an_unchanged_file_is_not_read_again(tmp_path):
    path = _write(_main_path(tmp_path), CONVERSATION)
    read = H.reader(_projects(tmp_path))
    assert read(SID, CWD, str(path))["cached"] is False
    assert read(SID, CWD, str(path))["cached"] is True
    with open(path, "a") as f:
        f.write(json.dumps(_user("新しい指示")) + "\n")
    again = read(SID, CWD, str(path))
    assert again["cached"] is False and again["items"][-1]["text"] == "新しい指示"


# ---------------------------------------------------------------- where it may read


def test_only_regular_jsonl_files_under_the_projects_folder_and_never_through_a_symlink(tmp_path):
    projects = _projects(tmp_path)
    read = H.reader(projects)
    outside = _write(tmp_path / "elsewhere" / f"{SID}.jsonl", [_user("外の秘密")])
    assert read(SID, None, str(outside)) is None                                       # outside the folder
    link_dir = projects / "linked"
    link_dir.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(outside.parent, link_dir)
    assert read(SID, None, str(link_dir / f"{SID}.jsonl")) is None                     # a symlinked folder
    real = _write(projects / "p" / "real.jsonl", [_user("本物")])
    os.symlink(outside, projects / "p" / "link.jsonl")
    assert read(SID, None, str(projects / "p" / "link.jsonl")) is None                 # a symlinked file
    not_jsonl = _write(projects / "p" / f"{SID}.txt", [_user("拡張子違い")])
    assert read(SID, None, str(not_jsonl)) is None
    assert read(SID, None, str(real))["items"][0]["text"] == "本物"                    # the control: it does read
    # a subagent's path from the hook goes through the same check
    assert read(SID, None, str(real), "a1", str(outside)) is None


def test_a_subagent_reads_its_own_transcript(tmp_path):
    main = _write(_main_path(tmp_path), [_user("メインの指示")])
    sub = _write(main.parent / SID / "subagents" / "agent-a6c4699452.jsonl", [_user("サブへの指示")])
    read = H.reader(_projects(tmp_path))
    assert read(SID, CWD, str(main), "a6c4699452")["items"][0]["text"] == "サブへの指示"          # the folder's rule
    assert read(SID, CWD, str(main), "zzz", str(sub))["items"][0]["text"] == "サブへの指示"       # the hook's path
    assert read(SID, CWD, str(main), "../../x") is None


# ---------------------------------------------------------------- the world and the wire


def _world(tmp_path):
    world = World(VizState())
    world.history_reader = H.reader(_projects(tmp_path))
    return world


def test_the_world_reads_the_robot_asked_for_and_nothing_goes_into_a_slice(tmp_path):
    path = _write(_main_path(tmp_path), [_user(f"{MARK} 指示"), _asst([{"type": "text", "text": f"{MARK} 応答"}])])
    world = _world(tmp_path)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(path)}, 1)
    sub = _write(path.parent / SID / "subagents" / "agent-sub1.jsonl", [_user("サブ")])
    world.apply_hook({"hook_event_name": "SubagentStop", "session_id": SID, "cwd": CWD, "agent_id": "sub1",
                      "agent_type": "Explore", "agent_transcript_path": str(sub)}, 2)
    assert [i["kind"] for i in world.history(SID)["items"]] == ["user", "assistant"]
    assert world.history("sub1")["items"][0]["text"] == "サブ"
    assert world.history("nobody") is None
    world.publish()
    assert MARK not in json.dumps(world.state.snapshot(), ensure_ascii=False)


def test_a_turn_the_harness_wrote_is_tagged_with_the_same_predicate():
    world = World(VizState())
    world.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": SID, "cwd": CWD,
                      "prompt": "[Subagent hand-back] The text below is the final report"}, 1)
    world.apply_hook({"hook_event_name": "Stop", "session_id": SID, "cwd": CWD}, 2)
    world.apply_hook({"hook_event_name": "UserPromptSubmit", "session_id": SID, "cwd": CWD, "prompt": "直して"}, 3)
    turns = sorted((t for t in world.tasks.tasks.values() if t.get("source") == "turn"), key=lambda t: t["turn"])
    assert [t.get("harness") for t in turns] == ["サブエージェントの報告", None]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_history_get_answers_one_robot_over_the_socket(tmp_path):
    path = _write(_main_path(tmp_path), [_user(f"{MARK} 指示")])
    world = _world(tmp_path)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(path)}, 1)
    port = _free_port()

    async def run():
        ctx = ServerContext(config=VizConfig(pushIntervalMs=20), port=port, token=TOKEN, state=world.state, world=world,
                            publish=world.publish)
        client = TestClient(TestServer(make_app(ctx), host="127.0.0.1", port=port))
        await client.start_server()
        try:
            ws = await client.ws_connect("/ws", headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"})
            await ws.receive_json()
            await ws.send_json({"type": "auth", "token": TOKEN})
            first = [await ws.receive_json(), await ws.receive_json()]
            await ws.send_json({"type": "history.get", "reqId": "h1", "agentId": SID})
            got = await ws.receive_json()
            await ws.send_json({"type": "history.get", "reqId": "h2", "agentId": "nobody"})
            refused = await ws.receive_json()
            await ws.close()
            return first, got, refused
        finally:
            await client.close()
    first, got, refused = asyncio.run(run())
    assert MARK not in json.dumps(first, ensure_ascii=False)                    # not in the hello / snapshot
    assert got["type"] == "history" and got["reqId"] == "h1" and got["items"][0]["text"] == f"{MARK} 指示"
    assert "path" not in json.dumps(got) or str(tmp_path) not in json.dumps(got)  # where it lives is not sent
    assert refused == {"type": "ack", "reqId": "h2", "ok": False, "error": "no transcript for this robot"}


def test_the_export_carries_no_history(tmp_path):
    _write(_main_path(tmp_path), [_user(f"{MARK} 指示")])
    world = _world(tmp_path)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(_main_path(tmp_path))}, 1)
    assert world.history(SID)["items"]                                           # a history is there to leak
    out = tmp_path / "export"
    export_demo.export(out)
    hits = [p for p in out.rglob("*") if p.is_file() and MARK.encode() in p.read_bytes()]
    assert hits == []
