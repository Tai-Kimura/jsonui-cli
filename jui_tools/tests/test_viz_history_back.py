"""The 応答の履歴 further back (2.3.12, ticket 2026-10-21-jui-viz-hist-tab-cannot-scroll-back; the requester's ruling of
10-21: keep the 40, add 「もっと前を読む」, and keep a call stopped by auto mode on its row).

sources/history.read_tail: ``end`` gives the 40 before a byte the server gave (``from``), ``stop`` everything from a
byte to the end; ``from`` is where the oldest line given starts (a line whole or not at all); ``results`` the tool
results read whose call was not given. A tool_result that is auto mode's denial marks its row ``denied`` with the
reason, read from the transcript (not the board's card, which goes a minute after it is answered).
"""
from __future__ import annotations

import json
import os

from jui_cli.viz.denials import DENIED_PREFIX
from jui_cli.viz.sources import history as H
from tests.test_viz_history import _asst, _result, _user, _write


def _starts(path):
    out, o = [], 0
    for line in path.read_bytes().split(b"\n")[:-1]:
        out.append(o)
        o += len(line) + 1
    return out


def _read(path, **kw):
    fd = os.open(path, os.O_RDONLY)
    try:
        return H.read_tail(fd, **kw)
    finally:
        os.close(fd)


def _texts(got):
    return [i.get("text") for i in got["items"]]


def test_forty_at_a_time_back_to_the_start_joined_with_nothing_lost_or_twice(tmp_path):
    p = _write(tmp_path / "t.jsonl", [_user(f"指示 {n}") for n in range(100)])
    starts = _starts(p)
    newest = _read(p)
    assert _texts(newest) == [f"指示 {n}" for n in range(60, 100)] and newest["from"] == starts[60] and newest["more"] is True
    back1 = _read(p, end=newest["from"])
    assert _texts(back1) == [f"指示 {n}" for n in range(20, 60)] and back1["from"] == starts[20] and back1["more"] is True
    back2 = _read(p, end=back1["from"])
    assert _texts(back2) == [f"指示 {n}" for n in range(0, 20)] and back2["from"] == 0 and back2["more"] is False
    # the newest part read down to where the reader went back: everything from there to the end
    with open(p, "a") as f:
        f.write(json.dumps(_user("新しい指示"), ensure_ascii=False) + "\n")
    tail = _read(p, stop=newest["from"])
    assert _texts(tail) == [f"指示 {n}" for n in range(60, 100)] + ["新しい指示"] and tail["from"] == starts[60]


def test_an_end_that_is_not_where_a_line_starts_gives_nothing(tmp_path):
    p = _write(tmp_path / "t.jsonl", [_user(f"指示 {n}") for n in range(5)])
    starts = _starts(p)
    assert _read(p, end=starts[3] + 2)["items"] == []
    assert _read(p, end=10 ** 9)["items"] != []                   # past the end: from the end, as without one
    assert _texts(_read(p, end=starts[3])) == ["指示 0", "指示 1", "指示 2"]


def test_a_line_is_given_whole_so_the_next_page_loses_none_of_it(tmp_path):
    """One assistant record with three texts at the cut: the record goes whole to the older page."""
    records = [_user(f"指示 {n}") for n in range(10)]
    records.append(_asst([{"type": "text", "text": f"答え {k}"} for k in range(3)], mid="m-three"))
    records += [_user(f"後の指示 {n}") for n in range(H.ITEMS_MAX - 1)]
    p = _write(tmp_path / "t.jsonl", records)
    newest = _read(p)
    assert "答え 0" not in _texts(newest) and "答え 2" not in _texts(newest)   # cut inside that record: all three go back
    back = _read(p, end=newest["from"])
    assert _texts(back)[-3:] == ["答え 0", "答え 1", "答え 2"]
    assert len(newest["items"]) + len(back["items"]) == 10 + 3 + H.ITEMS_MAX - 1


def test_a_result_whose_call_is_older_comes_back_for_the_page_to_join(tmp_path):
    records = [_user(f"指示 {n}") for n in range(5)]
    records.append(_asst([{"type": "tool_use", "id": "tu-old", "name": "Bash", "input": {"command": "ls"}}], mid="m-old"))
    records += [_user(f"後の指示 {n}") for n in range(H.ITEMS_MAX)]
    records.append(_result("tu-old", "a.txt"))                         # a result long after its call (one run in the background)
    p = _write(tmp_path / "t.jsonl", records)
    newest = _read(p)
    assert "tu-old" in newest["results"] and newest["results"]["tu-old"]["out"] == "a.txt"
    back = _read(p, end=newest["from"])
    call = next(i for i in back["items"] if i["kind"] == "tool")
    assert call["id"] == "tu-old" and "out" not in call                # the page puts the result in
    assert "tu-old" not in back["results"]


def test_a_call_stopped_by_auto_mode_is_marked_on_its_row_with_the_reason(tmp_path):
    text = f"{DENIED_PREFIX} Reason: [Git Destructive]. If you have other tasks that don't depend on this action, continue."
    records = [_asst([{"type": "tool_use", "id": "tu-d", "name": "Bash", "input": {"command": "git filter-branch"}}], mid="m-d"),
               _result("tu-d", text, error=True),
               _asst([{"type": "tool_use", "id": "tu-e", "name": "Bash", "input": {"command": "false"}}], mid="m-e"),
               _result("tu-e", "exit 1", error=True),
               _asst([{"type": "tool_use", "id": "tu-q", "name": "Bash", "input": {"command": "echo"}}], mid="m-q"),
               _result("tu-q", f"{DENIED_PREFIX} (a file's text, read back by cat)", error=False)]
    p = _write(tmp_path / "t.jsonl", records)
    tools = {i["id"]: i for i in _read(p)["items"] if i["kind"] == "tool"}
    assert tools["tu-d"]["denied"] == "[Git Destructive]" and tools["tu-d"]["error"] is True
    assert "denied" not in tools["tu-e"] and "denied" not in tools["tu-q"]   # an error that is no denial; the same words leading a result that is no error
