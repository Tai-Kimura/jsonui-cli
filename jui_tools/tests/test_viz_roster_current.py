"""The room's robot list highlights the robot selected now (requester 10-23: 「今選択されてるロボットがチェックの方でも
ハイライトされるようにしてほしい」): its card open (rbState.id), a subagent's being its main session's row, none when none
is selected; the row brought into the list's view once per robot selected. rosterCurrentKey, rosterRowHTML and
rosterShowCurrent are cut out of 53-roster.js and run in node with the page's state stood in; the page itself is
tools/viz_e2e/room_roster.py's (select, move, a subagent, none)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import web_text

STAND_IN = r"""
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const tl = (k, p = {}) => `${k}:${p.name || ''}`;
const pill = (id) => `<b>${id}</b>`;
const LAMP = { idle: '#999' }, LAMP_TEXT = { idle: 'idle' }, WAIT = { name: {} };
const DEF = { a1: { id: 'a1', kind: 'main', sessionId: 'S-A' }, b2: { id: 'b2', kind: 'main', sessionId: 'S-B' },
              s9: { id: 's9', kind: 'sub', mainLabel: 'b2', realId: 'agent-s9' } };
const rbState = { id: null };
const ROSTER = { shownFor: null };
const rowsOf = () => [{ key: 'S-A', id: 'a1', role: 'main', name: 'A', lamp: 'idle', wait: null, on: true },
                      { key: 'S-B', id: 'b2', role: 'main', name: 'B', lamp: 'idle', wait: null, on: true }];
const marked = () => rowsOf().filter((r) => rosterRowHTML(r, rosterCurrentKey()).includes('aria-current="true"')).map((r) => r.id);
const pick = (id) => { rbState.id = id; return marked(); };
"""


def _cut(src: str, name: str) -> str:
    start = re.search(rf"\nfunction {name}\(", src).start() + 1
    return src[start:src.index("\n}", start) + 2]


def _node(code: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    out = subprocess.run([node, "-"], input=code, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _src() -> str:
    src = web_text("js", "53-roster.js")
    consts = "\n".join(re.search(rf"\nconst {n} = [^\n]*", src).group(0) for n in ("rosterMainDef", "rosterKeyOf"))
    return consts + "\n" + "\n".join(_cut(src, n) for n in ("rosterCurrentKey", "rosterRowHTML", "rosterShowCurrent"))


def test_the_selected_robots_row_and_only_it_is_highlighted_and_moves_with_the_selection():
    got = _node(STAND_IN + _src() + """
process.stdout.write(JSON.stringify({ none: pick(null), picked: pick('a1'), moved: pick('b2'), sub: pick('s9'), unknown: pick('zz'), off: pick(null) }));""")
    assert got == {"none": [], "picked": ["a1"], "moved": ["b2"], "sub": ["b2"], "unknown": [], "off": []}


def test_the_highlighted_row_is_brought_into_view_once_per_robot_selected():
    got = _node(STAND_IN + _src() + r"""
let rowTop = 900;
const row = { offsetParent: {}, getBoundingClientRect: () => ({ top: rowTop, bottom: rowTop + 30 }) };
const list = { scrollTop: 0, querySelector: () => row, getBoundingClientRect: () => ({ top: 100, bottom: 500 }) };
const document = { getElementById: () => list };
rosterShowCurrent('S-A'); const below = list.scrollTop;
rowTop = 20; rosterShowCurrent('S-A'); const same = list.scrollTop;     // the same robot: the reader's scroll stays
rosterShowCurrent('S-B'); const above = list.scrollTop;
rosterShowCurrent(null); const none = [list.scrollTop, ROSTER.shownFor];
process.stdout.write(JSON.stringify({ below, same, above, none }));""".replace("const ROSTER = { shownFor: null };", ""))
    assert got == {"below": 434, "same": 434, "above": 350, "none": [350, None]}


def test_the_list_is_drawn_again_when_the_selection_changes():
    """The list is written again only when its signature changes: the selected row is part of it."""
    sync = _cut(web_text("js", "53-roster.js"), "rosterSync")
    assert "current = rosterCurrentKey()" in sync and "${solo}|${current}|" in sync
    assert "rows.map((r) => rosterRowHTML(r, current))" in sync
    assert sync.count("rosterShowCurrent(current)") == 2   # drawn again, or the same rows with a selection to show
