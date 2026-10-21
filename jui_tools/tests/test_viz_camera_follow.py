"""The open card's robot moved to another room (ticket 2026-10-21-jui-viz-camera-does-not-follow-robot-walking-rooms).

rbFollow and rbFollowTo are cut out of 50-panel.js and run in node with the page's state stood in: what each way the
robot's room changes does — the view follows (selectRobot and a toast), the card is marked, or nothing. The e2e
(tools/viz_e2e) moves a real robot.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import _match, web_text

STAND_IN = """
const SOURCE = { mode: 'live' }, PROJECT = { A: { name: 'alpha' }, B: { name: 'beta' }, C: { name: 'gamma' } };
const ROOM = { r1: 'A' }, rbState = { id: null, seen: null, moved: null }, latestModel = {};
const FOLLOW = { busy: false, handAt: 0 }, FOLLOW_HAND_MS = 3000;
let inView = ['A'], log = [];
const projectOfRobot = (id) => ROOM[id];
const roomsInView = () => inView;
const renderRobot = () => log.push('render');
const showToast = (t) => log.push(`toast:${t}`);
const selectRobot = (id) => log.push(`select:${id}:${FOLLOW.busy}`);
function open(id) { rbState.id = id; rbState.seen = { id, room: ROOM[id] || null, name: (PROJECT[ROOM[id]] || {}).name || '' }; rbState.moved = null; }
function step(change) { log = []; change(); rbFollow(); return { log, moved: rbState.moved }; }
"""


def _run(cases: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    src = web_text("js", "50-panel.js")
    parts = []
    for name in ("rbFollow", "rbFollowTo"):
        start = re.search(rf"\nfunction {name}\(", src).start() + 1
        parts.append(src[start:_match(src, src.index("{", start)) + 1])
    ja = web_text("i18n", "ja.json")   # the words in Japanese, as the page says them under ja
    tl = f"const JA = {ja};\nconst tl = (k, p = {{}}) => JA[k].replace(/\\{{(\\w+)\\}}/g, (m, n) => (n in p ? String(p[n]) : m));\n"
    out = subprocess.run([node, "-e", tl + STAND_IN + "\n".join(parts) + f"\nprocess.stdout.write(JSON.stringify({cases}));"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_room_out_of_the_view_is_followed_with_a_toast():
    got = _run("[open('r1'), step(() => { ROOM.r1 = 'B'; })][1]")
    assert got == {"log": ["select:r1:true", "toast:r1 を追って beta へ移りました"], "moved": None}


def test_a_room_in_the_view_only_repaints_the_card_the_camera_follows_each_frame():
    got = _run("[open('r1'), step(() => { inView = ['A', 'B']; ROOM.r1 = 'B'; })][1]")
    assert got == {"log": ["render"], "moved": None}


def test_right_after_a_switch_by_hand_the_card_is_marked_and_nothing_moves():
    got = _run("[open('r1'), step(() => { FOLLOW.handAt = Date.now() - 1000; ROOM.r1 = 'B'; })][1]")
    assert got == {"log": ["render"], "moved": {"room": "B"}}
    later = _run("[open('r1'), step(() => { FOLLOW.handAt = Date.now() - 3500; ROOM.r1 = 'B'; })][1]")
    assert later["log"][0] == "select:r1:true"


def test_its_room_closed_keeps_the_card_and_says_so_once():
    # the project gone with the session's id unchanged, and with none; the next layout says nothing again
    got = _run("[open('r1'), step(() => { delete PROJECT.A; }), step(() => {})].slice(1)")
    assert got == [{"log": ["render", "toast:r1 の部屋（alpha）が閉じました"], "moved": {"closed": "alpha"}},
                   {"log": [], "moved": {"closed": "alpha"}}]
    none = _run("[open('r1'), step(() => { delete ROOM.r1; })][1]")
    assert none == {"log": ["render", "toast:r1 の部屋（alpha）が閉じました"], "moved": {"closed": "alpha"}}


def test_no_change_another_robot_no_card_or_the_demo_do_nothing():
    got = _run("""[
      (open('r1'), step(() => {})),
      (open('r1'), step(() => { rbState.id = 'r2'; ROOM.r2 = 'C'; })),
      (open('r1'), step(() => { rbState.id = null; ROOM.r1 = 'B'; })),
      (open('r1'), step(() => { SOURCE.mode = 'demo'; ROOM.r1 = 'C'; })),
    ]""")
    assert [g["log"] for g in got] == [[], [], [], []]
    assert got[1]["moved"] is None


def test_a_switch_by_hand_is_recorded_and_the_follow_s_own_is_not():
    src = web_text("js", "50-panel.js")
    body = src[src.index("function setProject("):]
    head = body[:body.index("\n", body.index("UI.project === id) return;")) + 200]
    assert "if (!FOLLOW.busy) FOLLOW.handAt = Date.now();" in head
    assert "queueMicrotask(rbFollow);" in web_text("js", "40-scene.js")
