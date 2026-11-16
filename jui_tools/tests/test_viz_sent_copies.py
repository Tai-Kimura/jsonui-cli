"""Pictures a session sent with SendUserFile, copied when the call is made (ticket 2026-10-23-viz-sent-pictures-gone-
when-the-file-moves; requester: 「画像見えない / claude codeのアプリからなら見えるからバグだと思う」).

The history read a sent picture from its path when its thumbnail came into view: a file moved after it was sent showed
消えました while the app still showed it. Now its hook (PreToolUse / PostToolUse of SendUserFile) copies each picture into
<viz home>/sent/, and the history shows that copy; a call seen without a hook is copied the first time it is read. A
fake projects folder, files and a viz home under tmp_path; nothing reads or writes the real home.
"""
from __future__ import annotations

import json
import os
import time

from jui_cli.viz import sent_copies as SC
from jui_cli.viz.ingest import World
from jui_cli.viz.sent_copies import SentCopies
from jui_cli.viz.sources import history as H
from jui_cli.viz.state import VizState
from tests.test_viz_history_images import GIF, PNG, _line_starts, _ok_headers, _path, _write, png
from tests.test_viz_history_sent_files import CWD, SID, _send, _serve


def _store(tmp_path):
    return SentCopies(home=tmp_path / "viz-home")


def _pics(tmp_path):
    d = tmp_path / "pics"
    d.mkdir()
    (d / "a.png").write_bytes(PNG)
    (d / "b.gif").write_bytes(GIF)
    (d / "notes.md").write_text("# notes")
    (d / "fake.png").write_bytes(b"<html>not a png</html>")
    os.symlink(d / "a.png", d / "link.png")
    return d


def test_a_picture_is_copied_when_sent_and_read_back_after_the_file_moved(tmp_path):
    d, st = _pics(tmp_path), _store(tmp_path)
    got = st.take("toolu_01A", [str(d / "a.png"), str(d / "notes.md"), str(d / "b.gif")], CWD)
    assert got == ["copied", "skipped", "copied"]                    # notes.md: no picture by its name, left alone
    os.rename(d / "a.png", d / "moved.png")
    (d / "b.gif").unlink()
    assert st.read("toolu_01A", 0) == (200, ("image/png", PNG))
    assert st.read("toolu_01A", 2) == (200, ("image/gif", GIF))
    assert st.read("toolu_01A", 1) == (404, "")
    folder = tmp_path / "viz-home" / "sent"
    assert sorted(p.name for p in folder.iterdir()) == ["toolu_01A-0.png", "toolu_01A-2.gif"]
    assert oct(folder.stat().st_mode & 0o777) == "0o700" and oct((folder / "toolu_01A-0.png").stat().st_mode & 0o777) == "0o600"
    assert oct(folder.parent.stat().st_mode & 0o777) == "0o700"     # the viz home it made: people's pictures, this user's only


def test_a_copy_over_the_cap_in_the_folder_is_not_read(tmp_path, monkeypatch):
    """What sent/ holds under a copy's name is read only up to SENT_FILE_MAX, as the history reads a file."""
    d, st = _pics(tmp_path), _store(tmp_path)
    assert st.take("toolu_01F", [str(d / "a.png")], CWD) == ["copied"]
    (tmp_path / "viz-home" / "sent" / "toolu_01F-0.png").write_bytes(PNG + b"\0" * 64)   # grown after it was written
    monkeypatch.setattr(SC, "SENT_FILE_MAX", len(PNG) + 32)
    assert st.read("toolu_01F", 0) == (404, "unreadable")
    monkeypatch.setattr(SC, "SENT_FILE_MAX", len(PNG) + 64)
    assert st.read("toolu_01F", 0)[0] == 200                         # the control: at the cap it is read


def test_the_copy_is_what_was_sent_and_is_taken_once(tmp_path):
    d, st = _pics(tmp_path), _store(tmp_path)
    assert st.take("toolu_01B", [str(d / "a.png")], CWD) == ["copied"]
    other = png(9, 9, (1, 2, 3))
    (d / "a.png").write_bytes(other)                                 # overwritten after it was sent
    assert st.take("toolu_01B", [str(d / "a.png")], CWD) == ["kept"]   # PostToolUse after PreToolUse: not again
    assert st.read("toolu_01B", 0) == (200, ("image/png", PNG))


def test_a_picture_not_copied_leaves_why(tmp_path, monkeypatch):
    d, st = _pics(tmp_path), _store(tmp_path)
    monkeypatch.setattr(H, "SENT_FILE_MAX", len(PNG) - 1)
    got = st.take("toolu_01C", [str(d / "a.png"), str(d / "fake.png"), str(d / "gone.png"), str(d / "link.png"), f"{d}/../pics/b.gif", "pics/b.gif"], None)
    assert got == ["too-large", "not-picture", "gone", "unreadable", "unreadable", "gone"]   # the last: relative, no cwd to read it from
    assert [st.read("toolu_01C", i) for i in range(6)] == [(404, w) for w in got]


def test_a_relative_path_is_copied_from_the_hooks_cwd(tmp_path):
    _pics(tmp_path)
    st = _store(tmp_path)
    assert st.take("toolu_01D", ["pics/a.png"], str(tmp_path)) == ["copied"]
    assert st.read("toolu_01D", 0) == (200, ("image/png", PNG))


def test_names_that_are_not_a_call_id_are_refused(tmp_path):
    d, st = _pics(tmp_path), _store(tmp_path)
    assert st.take("../x", [str(d / "a.png")], CWD) == ["skipped"]
    assert st.take("toolu_01E", [str(d / "a.png")] * 101, CWD).count("copied") == 100   # places 0..99 only
    assert st.read("../x", 0) == (404, "") and st.read("toolu_01E", 100) == (404, "") and st.read("toolu_01E", True) == (404, "")


def test_the_oldest_go_first_past_the_cap_and_the_age(tmp_path, monkeypatch):
    d, st = _pics(tmp_path), _store(tmp_path)
    folder = tmp_path / "viz-home" / "sent"
    now = time.time()
    for k in range(4):
        st.take(f"toolu_cap{k}", [str(d / "a.png")], CWD, now_s=now)
        os.utime(folder / f"toolu_cap{k}-0.png", (now - 100 + k, now - 100 + k))
    monkeypatch.setattr(SC, "STORE_MAX", 2 * len(PNG))
    gone = st.prune(now)
    assert sorted(gone) == ["toolu_cap0-0.png", "toolu_cap1-0.png"]      # the two oldest
    os.utime(folder / "toolu_cap3-0.png", (now - SC.AGE_MAX_S - 1, now - SC.AGE_MAX_S - 1))
    assert st.prune(now) == ["toolu_cap3-0.png"]
    assert sorted(p.name for p in folder.iterdir()) == ["toolu_cap2-0.png"]


def _transcript(tmp_path, files, use="tu-moved"):
    rec = _send(files)
    rec["message"]["content"][0]["id"] = use
    p = _write(_path(tmp_path, SID, CWD), [rec])
    return p, _line_starts(p)


def _world(tmp_path, p, copies=True):
    world = World(VizState())
    world.history_reader = H.reader(tmp_path / ".claude" / "projects")
    if copies:
        world.sent_copies = _store(tmp_path)
    world.apply_hook({"hook_event_name": "SessionStart", "session_id": SID, "cwd": CWD, "transcript_path": str(p)}, 1)
    return world


def _until(cond, s=5.0):
    end = time.monotonic() + s
    while time.monotonic() < end and not cond():
        time.sleep(0.02)
    return cond()


def test_the_hook_copies_and_the_history_shows_the_copy_after_the_file_moved(tmp_path):
    """The requester's case: a picture sent, then moved; the history still shows it."""
    d = _pics(tmp_path)
    p, s = _transcript(tmp_path, [str(d / "a.png")])
    world = _world(tmp_path, p)
    world.apply_hook({"hook_event_name": "PreToolUse", "session_id": SID, "cwd": CWD, "tool_name": "SendUserFile", "tool_use_id": "tu-moved",
                      "tool_input": {"files": [str(d / "a.png")], "status": "normal"}}, 2)
    assert _until(lambda: (tmp_path / "viz-home" / "sent" / "tu-moved-0.png").exists())
    os.rename(d / "a.png", d / "elsewhere.png")
    assert world.history_file(SID, s[0], 0) == (200, ("image/png", PNG))


def test_a_call_seen_without_a_hook_is_copied_when_first_read(tmp_path):
    d = _pics(tmp_path)
    p, s = _transcript(tmp_path, [str(d / "a.png")])
    world = _world(tmp_path, p)
    assert world.history_file(SID, s[0], 0) == (200, ("image/png", PNG))
    (d / "a.png").unlink()
    assert world.history_file(SID, s[0], 0) == (200, ("image/png", PNG))


def test_gone_with_no_copy_says_why_and_without_a_record_says_gone(tmp_path, monkeypatch):
    d = _pics(tmp_path)
    p, s = _transcript(tmp_path, [str(d / "a.png"), str(d / "b.gif")])
    world = _world(tmp_path, p)
    monkeypatch.setattr(H, "SENT_FILE_MAX", len(PNG) - 1)
    world.sent_copies.take("tu-moved", [str(d / "a.png")], CWD)       # a.png too large then; b.gif has no hook record
    (d / "a.png").unlink()
    (d / "b.gif").unlink()
    assert world.history_file(SID, s[0], 0) == (404, "gone:too-large")
    assert world.history_file(SID, s[0], 1) == (404, "gone")

    def calls(own):
        return [("POST", _ok_headers(own), json.dumps({"agentId": SID, "off": s[0], "n": n})) for n in (0, 1)]
    got = _serve(world, calls)
    assert [json.loads(g[2]) for g in got] == [{"gone": True, "why": "too-large"}, {"gone": True}]


def test_a_world_made_in_a_test_copies_nothing(tmp_path):
    d = _pics(tmp_path)
    p, s = _transcript(tmp_path, [str(d / "a.png")])
    world = _world(tmp_path, p, copies=False)
    world.apply_hook({"hook_event_name": "PreToolUse", "session_id": SID, "cwd": CWD, "tool_name": "SendUserFile", "tool_use_id": "tu-moved",
                      "tool_input": {"files": [str(d / "a.png")]}}, 2)
    assert world.history_file(SID, s[0], 0) == (200, ("image/png", PNG))
    time.sleep(0.2)
    assert not (tmp_path / "viz-home").exists()
