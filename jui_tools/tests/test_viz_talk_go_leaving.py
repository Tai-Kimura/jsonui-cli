"""jui viz: the talk list's ロボット一覧 and ロボットへ移る leave out a robot that is leaving (ticket
2026-10-21-jui-viz-talk-panel-tabs-and-robot-list).

The page's own talkGoable / talkRobots / talkGo, cut out of 58-talk.js and run in node. Live, a robot whose session
ended is still on the page while it walks out (LIVE.leaving): it is not a robot to go to, so it is not on the
ロボット一覧, and a press on its ロボットへ移る (a row drawn just before it left) says it is not here and picks nothing.
The browser half (the tabs, the rows, the camera on the robot) is the e2e suite talk-ui.
"""

from __future__ import annotations

from tests.test_viz_hist_card_off import _cut, _node

WORLD = """
const DEF = { a1: {}, a2: {}, a3: {}, b1: {} };
const ROBOT_DEFS = [{ id: 'a1' }, { id: 'a2' }, { id: 'a3' }, { id: 'b1' }];
const ROOMS = [{ id: 'pa' }, { id: 'pb' }];
const projectOfRobot = (id) => (id[0] === 'a' ? 'pa' : 'pb');
const SOURCE = { mode: 'live', talkLabel: (agentId) => agentId };
const LIVE = { leaving: {} };
const TALK = { owner: 'a1', on: true, conv: 'c1', note: '', list: [{ peer: { agentId: 'a3' } }] };
const tl = (key) => key;
const calls = { toast: [], picked: [] };
const showToast = (t) => calls.toast.push(t);
const selectRobot = (id) => calls.picked.push(id);
"""


def _parts():
    return [WORLD] + [_cut("58-talk.js", n) for n in ("talkGoable", "talkRobots", "talkGo")]


def test_the_robot_list_holds_the_robots_with_no_talk_and_not_the_cards_own():
    assert _node(_parts(), "talkRobots()") == ["a2", "b1"]


def test_a_leaving_robot_is_not_on_the_robot_list():
    assert _node(_parts(), "(() => { LIVE.leaving.a2 = true; return [talkGoable('a2'), talkRobots()]; })()") == [False, ["b1"]]


def test_a_press_on_a_leaving_robots_go_says_it_is_not_here_and_picks_nothing():
    got = _node(_parts(), "(() => { LIVE.leaving.b1 = true; talkGo('b1'); return [calls, TALK.on]; })()")
    assert got == [{"toast": ["talk.go.absent"], "picked": []}, True]


def test_a_press_on_a_robot_still_here_closes_the_talk_and_picks_it():
    got = _node(_parts(), "(() => { talkGo('b1'); return [calls, TALK.on, TALK.conv]; })()")
    assert got == [{"toast": [], "picked": ["b1"]}, False, None]
