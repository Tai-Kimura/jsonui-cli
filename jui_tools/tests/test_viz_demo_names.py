"""The page `jui viz` ships names nothing but its own: the demo's rooms are fictional folders, and no working
session's name is in the comments of the page's code and styles, or in its page.

The demo page is public sample data (the docsite's screenshots, every `jui viz export-demo` folder), and its bundle
carries its comments. Until 2.3.22 two of the demo's three rooms were a real checkout's folders under the
requester's home layout (ticket 2026-10-24-viz-demo-talk-data-carries-a-real-session-name, its count of the export).
The talk demo's peers are checked in test_viz_talk_demo_data.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from jui_cli.viz import bundle

WEB = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web"
DEMO = WEB / "js" / "30-source-demo.js"
ROOM = re.compile(r"\{ id: '(\w+)', name: '([^']+)', path: '([^']+)'")

#: A working session's name as the comments used to write it: a support lane and its number, a triage lane, or a short session id
#: before a particle or a possessive ("cd の裁定", "dd's check"). Role words (依頼者, orchestrator) are not names.
SESSION = re.compile(r"サポート\s?\d|triage|\b(?:cd|dd|b8|c2)\b(?=\s*(?:の|が|は|に|と|へ|で|、|'s|’s|\)|）))", re.I)


def test_the_demo_rooms_are_fictional_folders():
    rooms = ROOM.findall(DEMO.read_text(encoding="utf-8"))
    assert len(rooms) == 3, f"the scan found {len(rooms)} rooms, not the demo's three: {rooms}"
    for _id, name, path in rooms:
        assert path.startswith("~/work/") and name == path.rsplit("/", 1)[1] + "/", (name, path)


def test_the_session_pattern_sees_the_names_it_is_about():
    """Positive control: were the pattern blind, the arm below would pass on anything."""
    lane = "サポー" + "ト"   # written split, so this file holds no session's name itself
    for text in (f"({lane}6 の測り)", f"triage {lane}2", "cd の裁定", "dd's check", "（dd）"):
        assert SESSION.search(text), text
    for text in ("the requester's words", "the orchestrator's ruling", "cd ~/work && ls", "a dd-mm date"):
        assert not SESSION.search(text), text


#: The comments of the shipped code (`/* */`, `//` at a line's start or after code, `<!-- -->`). The code itself is not
#: read: a variable may be called `dd`.
COMMENT = re.compile(r"/\*.*?\*/|(?:^|[\s;{}(,])//[^\n]*|<!--.*?-->", re.S)


def comments(text: str) -> str:
    return "\n".join(COMMENT.findall(text))


def test_the_comment_scan_reads_the_comments():
    """Positive control: a name in a comment is read, a variable named like one is not."""
    lane = "サポー" + "ト3"
    text = f"const dd = 1; f(dd);\n/* (cd の裁定) */\n  x(); // dd's check\n<!-- {lane} -->"
    assert sorted(m.group(0) for m in SESSION.finditer(comments(text))) == ["cd", "dd", lane]


def test_no_session_name_in_what_the_page_ships():
    shipped = {
        "demo bundle": comments(bundle.build("demo", e2e=False)),
        "live bundle": comments(bundle.build("live", e2e=False)),
        "app.css": comments((WEB / "app.css").read_text(encoding="utf-8")),
        "index.html": (WEB / "index.html").read_text(encoding="utf-8"),
    }
    found = {where: sorted({m.group(0) for m in SESSION.finditer(text)}) for where, text in shipped.items()}
    assert not any(found.values()), f"a working session's name in the shipped page: {found}"
