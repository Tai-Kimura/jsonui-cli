"""The room's robot list put in order (requester 10-23: 「ロボットの一覧に並べ替え機能追加できる？左右キーで移動するのもその
順番に」): the person's own order (a drop or Alt+↑↓; remembered per room, a new session at the end), by name, by state
(waiting first), most recently active; the card's ‹ › and ← → go in the list's order and skip the robots it hides.
53-roster.js's functions and 50-panel.js's robotCycle / stepRobot are cut out and run in node with the page's state
stood in; dragging and the keys on the page itself are tools/viz_e2e/room_roster.py's."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import web_text

STAND_IN = r"""
const PREF = {};
const readPref = (k, d) => (k in PREF ? PREF[k] : d), writePref = (k, v) => { PREF[k] = v; };
const STATES = { idle: { lamp: 'idle' }, typing: { lamp: 'busy' }, waiting: { lamp: 'waiting' }, done: { lamp: 'done' } };
const mk = (id, room, extra = {}) => ({ def: { id, room, kind: 'main', sessionId: `S-${id}`, title: extra.title || id, ...extra } });
const robots = [mk('10', 'r', { title: 'うし' }), mk('20', 'r', { title: 'いぬ' }), mk('30', 'r', { title: 'あひる' }), mk('40', 'other'),
                { def: { id: 'ag', room: 'r', kind: 'sub', mainLabel: '20', realId: 'agent-ag' } },
                { def: { id: 'ab', room: 'r', kind: 'sub', mainLabel: '20', realId: 'agent-ab' } }];
const DEF = Object.fromEntries(robots.map((R) => [R.def.id, R.def]));
const robotState = { 10: { state: 'idle', since: 300 }, 20: { state: 'typing', since: 100 }, 30: { state: 'done', since: 200 }, ag: { state: 'typing', since: 900 } };
let WAITS = {};
const waitKindOf = (id) => WAITS[id] || null;
const keys = (room = 'r') => rosterRows(room).map((r) => r.id);
"""


def _cut(src: str, name: str) -> str:
    start = re.search(rf"\nfunction {name}\(", src).start() + 1
    return src[start:src.index("\n}", start) + 2]


def _const(src: str, name: str) -> str:
    return re.search(rf"\nconst {name} = [^\n]*", src).group(0)


def _node(code: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it; a skip would hide the arm)"
    out = subprocess.run([node, "-"], input=code, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _roster() -> str:
    src = web_text("js", "53-roster.js")
    consts = "\n".join(_const(src, n) for n in ("ROSTER", "ROSTER_SORTS", "rosterMainDef", "rosterKeyOf", "rosterSort", "rosterById", "rosterRank"))
    return consts + "\n" + "\n".join(_cut(src, n) for n in ("rosterOff", "rosterOrder", "rosterRows", "rosterArrange", "rosterMove", "rosterCycle"))


def test_each_order_puts_the_rows_as_it_says():
    got = _node(STAND_IN + _roster() + r"""
const out = { own: keys() };
for (const how of ['name', 'state', 'recent']) { PREF['roster-sort:r'] = how; out[how] = keys(); }
WAITS = { 10: 'permission' }; PREF['roster-sort:r'] = 'state'; out.stateWaiting = keys();
WAITS = { ab: 'question' }; out.subWaiting = keys();
PREF['roster-sort:r'] = 'nonsense'; out.unknown = keys();
process.stdout.write(JSON.stringify(out));""")
    assert got == {
        "own": ["10", "20", "30"],             # nothing put yet: by number
        "name": ["30", "20", "10"],            # あひる いぬ うし
        "state": ["20", "10", "30"],           # at work, free, done
        "recent": ["20", "10", "30"],          # 20's subagent moved last (900), then 10 (300), 30 (200)
        "stateWaiting": ["10", "20", "30"],    # waiting on the person: first
        "subWaiting": ["20", "10", "30"],      # a subagent waiting lifts its main's row
        "unknown": ["10", "20", "30"],
    }


def test_a_row_moved_is_remembered_per_room_and_a_new_session_comes_last():
    got = _node(STAND_IN + _roster() + r"""
PREF['roster-sort:r'] = 'name';
rosterMove('r', 'S-10', 0);                                    // moved while by name shows: the person's own from that
const fromName = [keys(), PREF['roster-sort:r'], JSON.parse(PREF['roster-order:r'])];
rosterMove('r', 'S-20', 3);                                    // to the end (Alt+↓ from the last but one)
const toEnd = keys();
ROSTER.order.clear();                                          // the page loaded again: from the pref
const again = keys();
robots.push(mk('05', 'r'));
const withNew = keys();
const otherRoom = keys('other');
robots.splice(robots.findIndex((R) => R.def.id === '30'), 1);  // 30 left the room: kept in the order to come back to
rosterMove('r', 'S-05', 0);
const kept = JSON.parse(PREF['roster-order:r']);
process.stdout.write(JSON.stringify({ fromName, toEnd, again, withNew, otherRoom, kept }));""")
    assert got == {
        "fromName": [["10", "30", "20"], "own", ["S-10", "S-30", "S-20"]],
        "toEnd": ["10", "30", "20"],
        "again": ["10", "30", "20"],
        "withNew": ["10", "30", "20", "05"],
        "otherRoom": ["40"],
        "kept": ["S-05", "S-10", "S-20", "S-30"],
    }


def test_the_cards_steps_go_in_the_lists_order_and_skip_the_hidden():
    panel = web_text("js", "50-panel.js")
    got = _node(STAND_IN + _roster() + r"""
const SOURCE = { mode: 'live' }, LIVE = { leaving: {} };
let SOLO = 'r';
const liveSolo = () => SOLO;
const ROBOT_DEFS = robots.map((R) => R.def), roomsInView = () => ['r', 'other'], projectOfRobot = (id) => DEF[id].room;
const rbState = { id: '10' };
const goRobot = (id) => { rbState.id = id; };
""" + _cut(panel, "robotCycle") + _cut(panel, "stepRobot") + r"""
PREF['roster-order:r'] = JSON.stringify(['S-30', 'S-10', 'S-20']);
const cycle = robotCycle();
const walk = []; for (let i = 0; i < 5; i++) { stepRobot(1); walk.push(rbState.id); }
rbState.id = '30'; stepRobot(-1); const back = rbState.id;
rosterOff('r').add('S-10');
const hidden = robotCycle();
rbState.id = '10'; stepRobot(1); const fromHidden = rbState.id;
rbState.id = '10'; stepRobot(-1); const fromHiddenBack = rbState.id;
LIVE.leaving.ab = true; const leaving = robotCycle();
SOLO = null; const building = robotCycle();
process.stdout.write(JSON.stringify({ cycle, walk, back, hidden, fromHidden, fromHiddenBack, leaving, building }));""")
    assert got == {
        "cycle": ["30", "10", "20", "ab", "ag"],
        "walk": ["20", "ab", "ag", "30", "10"],
        "back": "ag",
        "hidden": ["30", "20", "ab", "ag"],
        "fromHidden": "30",
        "fromHiddenBack": "ag",
        "leaving": ["30", "20", "ag"],
        "building": ["10", "20", "30", "ag", "40"],   # not in a room's view: rooms, then numbers, as before (ab leaving)
    }
