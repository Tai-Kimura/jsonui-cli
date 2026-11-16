"""A prompt too long for POST /api/prompt goes as a file (ticket 2026-11-04-viz-long-prompt-goes-as-a-file).

The server's part: the body's limit stays, the file is an attachment like any other, the event log says the person's own
words, and the history reads the text back (read_text, POST /api/attach-text). The page's part is in
tools/viz_e2e/attach.py; here only what a reading of its source can hold. Nothing here starts claude.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from jui_cli.viz import attachments as att
from jui_cli.viz import server
from jui_cli.viz.attachments import Attachments, Refused
from jui_cli.viz.ingest import World
from jui_cli.viz.state import VizState
from tests.test_viz_send_prompt import S_NEW, _started_right, _taken, viz  # noqa: F401 — viz is the fixture

SID = "e2e00000-0000-4000-8000-00000000b101"
WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"
HISTORY = (WEB / "js" / "55-history.js").read_text(encoding="utf-8")
LINE = re.search(r"const LONG_PROMPT_LINE = '([^']+)';", HISTORY).group(1)


@pytest.fixture()
def store(tmp_path):
    return Attachments(home=tmp_path / "viz-home")


def _keep(store, text: str) -> dict:
    return store.save(SID, "prompt.md", "text/markdown", text.encode("utf-8"))


def _attach(v, data: bytes):
    h = v.page_headers(**{"Content-Type": "application/octet-stream", "X-Jui-Viz-Session": S_NEW,
                          "X-Jui-Viz-Name": "prompt.md", "X-Jui-Viz-Media": "text/markdown"})
    status, text = v.raw("POST", "/api/attach", h, data)
    return status, (json.loads(text) if status == 200 else text)


def _read(v, body: dict, **over):
    return v.raw("POST", "/api/attach-text", v.page_headers(**over), json.dumps(body).encode())


# ---------------------------------------------------------------- read_text


def test_a_long_prompt_is_kept_and_read_back_byte_for_byte(store):
    text = "日本語😀の長い文\n" * 2000
    rec = _keep(store, text)
    assert rec["media"] == "text/markdown" and rec["path"].endswith(f"{rec['id']}.md") and rec["name"] == "prompt.md"
    assert Path(rec["path"]).read_bytes() == text.encode("utf-8")
    assert store.read_text(SID, rec["id"]) == {"text": text, "size": len(text.encode("utf-8")), "cut": False}


def test_what_the_history_gets_stops_at_the_view_limit_on_a_whole_character(store, monkeypatch):
    monkeypatch.setattr(att, "TEXT_VIEW_MAX", 10)
    rec = _keep(store, "あいうえお")   # 15 bytes: 10 cuts the 4th character in two
    assert store.read_text(SID, rec["id"]) == {"text": "あいう", "size": 15, "cut": True}


def test_a_gone_file_a_symlink_another_kind_of_file_and_another_folder_read_as_gone(store, tmp_path):
    rec = _keep(store, "x")
    os.unlink(rec["path"])
    secret = tmp_path / "secret.md"
    secret.write_text("secret")
    link = _keep(store, "y")
    os.unlink(link["path"])
    os.symlink(secret, link["path"])
    notes = store.save(SID, "notes.txt", "text/plain", b"notes")
    for sid, fid in ((SID, rec["id"]), (SID, link["id"]), (SID, notes["id"]), ("../..", "0" * 16)):
        with pytest.raises(Refused) as e:
            store.read_text(sid, fid)
        assert e.value.status == 404, (sid, fid)


@pytest.mark.parametrize("fid", ["../../etc/passwd", "abc", "0" * 15, "G" * 16, 7, None])
def test_an_id_that_is_not_one_is_refused(store, fid):
    with pytest.raises(Refused) as e:
        store.read_text(SID, fid)
    assert e.value.status == 400


# ---------------------------------------------------------------- the routes


def test_the_body_limit_of_the_prompt_stays(viz):
    assert server.PROMPT_MAX_BODY == 8192
    empty = len(json.dumps({"sessionId": S_NEW, "text": ""}).encode())
    fits = json.dumps({"sessionId": S_NEW, "text": "x" * (8192 - empty)}).encode()
    assert len(fits) == 8192 and viz.prompt(body=fits)[0] == 200
    over = json.dumps({"sessionId": S_NEW, "text": "x" * (8193 - empty)}).encode()
    assert viz.prompt(body=over)[0] == 413


def test_a_long_prompt_reaches_the_channel_as_the_line_and_the_file(viz):
    text = "依頼の本文😀\n" * 3000
    status, up = _attach(viz, text.encode("utf-8"))
    assert status == 200, up
    body = json.dumps({"sessionId": S_NEW, "text": LINE, "attachments": [up["id"]], "shown": "依頼の本文😀"}, ensure_ascii=False).encode()
    status, said = viz.prompt(body=body)
    assert status == 200, said
    lines = _taken(viz, "new")[0]["text"].split("\n")
    path = viz.state / "uploads" / S_NEW / f"{up['id']}.md"
    assert lines[0] == LINE and len(lines) == 2
    assert lines[1].startswith(f"attached: {path} (prompt.md, text/markdown, ")
    assert path.read_bytes() == text.encode("utf-8")


def test_a_file_at_the_limit_is_kept_and_one_byte_over_is_refused(viz):
    assert _attach(viz, b"x" * att.FILE_MAX)[0] == 200
    assert _attach(viz, b"x" * (att.FILE_MAX + 1))[0] == 413


def test_attach_text_has_the_checks_of_the_prompt_and_gives_the_text(viz):
    _, up = _attach(viz, "全文\n".encode("utf-8"))
    body = {"sessionId": S_NEW, "id": up["id"]}
    assert _read(viz, body, **{"X-Jui-Viz-Token": None})[0] == 401
    assert _read(viz, body, Origin="http://evil.example")[0] == 403
    assert _read(viz, body, Origin=None)[0] == 403
    assert _read(viz, body, **{"Content-Type": "text/plain"})[0] == 415
    assert viz.raw("GET", "/api/attach-text", viz.page_headers())[0] == 405
    status, raw = _read(viz, body)
    assert status == 200 and json.loads(raw) == {"text": "全文\n", "size": 7, "cut": False}
    (viz.state / "uploads" / S_NEW / f"{up['id']}.md").unlink()
    status, raw = _read(viz, body)
    assert status == 200 and json.loads(raw) == {"gone": True}
    assert _read(viz, {"sessionId": S_NEW, "id": "nope"})[0] == 400


def test_the_event_log_says_the_persons_words_not_the_fixed_line():
    state = VizState()
    world = World(state)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work/a"}, 1)
    channel_id = world.channel_hello(None, None, "s1", 2, ["prompt"])
    _started_right(world, "s1")
    world.publish()
    kept = {"path": "/p/x.md", "name": "prompt.md", "media": "text/markdown", "size": 9000}
    assert world.send_prompt("s1", LINE, 3, [kept], "依頼の頭") is None
    world.publish()
    (event,) = [e for e in state.events if e["kind"] == "PromptSent"]
    assert "依頼の頭" in event["text"] and "whole prompt" not in event["text"]
    assert world.perms.take_prompts(channel_id)[0]["text"].startswith(LINE + "\nattached: /p/x.md ")


# ---------------------------------------------------------------- the page's source


def test_every_typed_text_goes_through_the_one_sender():
    js = "".join(p.read_text(encoding="utf-8") for p in sorted((WEB / "js").glob("*.js")) if p.name != "30-source-live.js")
    assert js.count("SOURCE.sendPrompt(") == 2, "only promptSend calls it: the plain text, and the line with the file"
    assert re.search(r"async function promptSend[\s\S]*?SOURCE\.sendPrompt\(label, text, ids\)[\s\S]*?SOURCE\.sendPrompt\(label, LONG_PROMPT_LINE,", js)
    assert "promptSend(id, text," in HISTORY
    assert "promptSend(s.robot.label, text, [])" in (WEB / "js" / "57-slack-room.js").read_text(encoding="utf-8")


def test_the_page_and_the_server_have_the_same_limits():
    assert re.search(r"const PROMPT_MAX_BYTES = (\d+);", HISTORY).group(1) == str(server.PROMPT_MAX_BODY)
    assert "ATTACH_MAX = 10, ATTACH_FILE_MAX = 20 * 1024 * 1024" in HISTORY
    assert att.PER_PROMPT_MAX == 10 and att.FILE_MAX == 20 * 1024 * 1024
    assert "'prompt.md'" in HISTORY and att.EXTENSIONS["md"] == "text/markdown"


def test_every_word_is_in_both_languages():
    ja, en = (json.loads((WEB / "i18n" / f"{lang}.json").read_text(encoding="utf-8")) for lang in ("ja", "en"))
    for key in ("hist.state.asfile", "hist.state.asfile.big", "hist.state.asfile.many", "hist.confirm.asfile", "hist.long.note", "hist.long.more", "hist.long.less",
                "hist.long.cut", "hist.long.gone", "hist.long.failed"):
        assert ja[key] and en[key] and ja[key] != en[key], key
