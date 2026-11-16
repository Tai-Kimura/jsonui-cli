"""jui viz: × on an answered card under the history, and 下を広げる (ticket 2026-10-21-jui-viz-hist-answered-card-dismiss-and-expand).

Requester: 「この答えた札邪魔だからxでこっちから消せるようにしたい。あとスクロールしないと質問と送信ボタン全部見えないから
見え流用に広げるボタンが欲しい。」 The page's own functions, cut out of its source and run in node: the × only on a card
of the history's box that nobody waits on, a card taken off there stays off (kept in this browser, the newest
HIST_OFF_MAX), and a card that waits again is never hidden. The browser half (the panel keeps the card, a reload,
the heights of 下を広げる) is the e2e suite hist-cards.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

from tests.test_viz_bundle import _match, web_text


def _cut(file: str, name: str) -> str:
    src = web_text("js", file)
    m = re.search(rf"(?:^|\n)((?:const {name} = |let {name} = |function {name}\())", src)
    assert m, f"{name} in {file}"
    start = m.start(1)
    if m.group(1).startswith("function"):
        return src[start:_match(src, src.index("{", start)) + 1]
    return src[start:src.index(";\n", start) + 1]


def _node(parts: list, expr: str):
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    out = subprocess.run([node, "-"], input="\n".join(parts) + f"\nprocess.stdout.write(JSON.stringify({expr}));",
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# localStorage as the page sees it, and readPref / writePref as the page has them
STORE = "const STORE = {}; globalThis.localStorage = { getItem: (k) => (k in STORE ? STORE[k] : null), setItem: (k, v) => { STORE[k] = String(v); } };"


def _pref_parts():
    return [STORE, _cut("20-core.js", "readPref"), _cut("20-core.js", "writePref")]


def test_the_cross_is_on_a_history_card_nobody_waits_on_and_nowhere_else():
    got = _node(["const tl = (k) => k;", _cut("20-core.js", "esc"), _cut("50-panel.js", "histOffHTML")],
                "[histOffHTML('h', 'q', 'a1', true), histOffHTML('h', 'q', 'a1', false), histOffHTML('', 'q', 'a1', true),"
                " histOffHTML('b', 'd', 'a1', true), histOffHTML('h', 'd', '<x\"', true)]")
    assert 'data-h-off="q:a1"' in got[0] and ">×</button>" in got[0]
    assert got[1:4] == ["", "", ""], "a waiting card, the panel's and the board's: no ×"
    assert 'data-h-off="d:&lt;x&quot;"' in got[4], "the id is escaped"


def test_a_card_taken_off_is_kept_in_this_browser_the_newest_only():
    parts = _pref_parts() + ["let painted = 0; function histCardsPaint() { painted += 1; }",
                             _cut("55-history.js", "HIST_OFF_PREF"), _cut("55-history.js", "HIST_OFF"), _cut("55-history.js", "histOff")]
    got = _node(parts, "(() => { histOff('q:a'); histOff('q:a'); for (let i = 0; i < HIST_OFF_MAX + 5; i += 1) histOff(`d:${i}`);"
                       " const kept = JSON.parse(STORE['agent-view:hist-cards-off']);"
                       " return { n: kept.length, first: kept[0], last: kept[kept.length - 1], hasA: kept.includes('q:a'), painted }; })()")
    assert got == {"n": 300, "first": "d:5", "last": "d:304", "hasA": False, "painted": 306}


def test_a_kept_list_is_read_back_and_a_broken_one_is_none():
    head = _pref_parts()
    tail = [_cut("55-history.js", "HIST_OFF_PREF"), _cut("55-history.js", "HIST_OFF")]
    got = _node(head + ["STORE['agent-view:hist-cards-off'] = JSON.stringify(['q:1', 7, 'd:2']);"] + tail, "HIST_OFF")
    assert got == ["q:1", "d:2"]
    assert _node(head + ["STORE['agent-view:hist-cards-off'] = '{nope';"] + tail, "HIST_OFF") == []


def test_the_history_box_leaves_out_a_card_taken_off_but_never_one_that_waits():
    stubs = """
const HIST = { tab: 'history', compose: { _for: 'm1' } };
const SESSION_OF = { m1: 's', s1: 's' };
const NAMES = { rev: 0 }, DEN = { asking: null };
const Q_SHOW_MS = 30000, DEN_SHOW_MS = 60000, NOW = Date.now();
const latestModel = { pending: [] };
const QUESTIONS = [{ id: 'qa', who: 's1', status: 'answered', doneAt: NOW }, { id: 'qp', who: 's1', status: 'pending' },
                   { id: 'qs', who: 's1', status: 'sent' }];
const DENIALS = [{ id: 'da', who: 'm1', status: 'dismissed', doneAt: NOW }, { id: 'dp', who: 'm1', status: 'pending' }];
let shown = null;
const box = { hidden: false, classList: { toggle() {} } };
function histCardsBox() { return box; }
const permSig = () => '', questionsSig = (x) => x.map((q) => q.id), denialsSig = (x) => x.map((d) => d.id);
function keyed(el, sig, build) { shown = JSON.parse(sig); }
function histLowBtn() { return {}; }   // the box's handle (its own row on the box's top edge): not what these arms look at
"""
    parts = _pref_parts() + [stubs, _cut("55-history.js", "HIST_OFF_PREF"), _cut("55-history.js", "HIST_OFF"),
                             _cut("55-history.js", "HIST_FOLD"), _cut("55-history.js", "histFoldKeys"), _cut("55-history.js", "histFoldState"),
                             _cut("55-history.js", "histCardsPaint")]
    got = _node(parts, "(() => { histCardsPaint(); const before = shown;"
                       " HIST_OFF.push('q:qa', 'q:qs', 'q:qp', 'd:da', 'd:dp'); histCardsPaint(); return [before, shown]; })()")
    before, after = got
    assert before[4:6] == [["qa", "qp", "qs"], ["da", "dp"]], "the control: all of them before"
    assert after[4:6] == [["qp"], ["dp"]], "off: the answered ones; a waiting card is never left out"


def test_a_cross_takes_off_its_own_card_only_not_the_others_of_its_kind():
    stubs = """
const HIST = { tab: 'history', compose: { _for: 'm1' } };
const SESSION_OF = { m1: 's' };
const NAMES = { rev: 0 }, DEN = { asking: null };
const Q_SHOW_MS = 30000, DEN_SHOW_MS = 60000, NOW = Date.now();
const latestModel = { pending: [] };
const QUESTIONS = [{ id: 'q1', who: 'm1', status: 'answered', doneAt: NOW }, { id: 'q2', who: 'm1', status: 'answered', doneAt: NOW }];
const DENIALS = [{ id: 'd1', who: 'm1', status: 'dismissed', doneAt: NOW }, { id: 'd2', who: 'm1', status: 'sent', doneAt: NOW }];
let shown = null;
function histCardsBox() { return { hidden: false, classList: { toggle() {} } }; }
const permSig = () => '', questionsSig = (x) => x.map((q) => q.id), denialsSig = (x) => x.map((d) => d.id);
function keyed(el, sig, build) { shown = JSON.parse(sig); }
function histLowBtn() { return {}; }   // the box's handle (its own row on the box's top edge): not what these arms look at
"""
    parts = _pref_parts() + [stubs, _cut("55-history.js", "HIST_OFF_PREF"), _cut("55-history.js", "HIST_OFF"),
                             _cut("55-history.js", "histOff"), _cut("55-history.js", "HIST_FOLD"), _cut("55-history.js", "histFoldKeys"), _cut("55-history.js", "histFoldState"),
                             _cut("55-history.js", "histCardsPaint")]
    got = _node(parts, "(() => { histCardsPaint(); const before = shown; histOff('q:q1'); histOff('d:d2'); return [before, shown]; })()")
    assert got[0][4:6] == [["q1", "q2"], ["d1", "d2"]], "the control: both of each kind before"
    assert got[1][4:6] == [["q2"], ["d1"]], "one × takes off that card only; the other answered card of its kind stays"


def test_permissions_start_open_and_a_chosen_fold_survives_sent():
    """Requester 10-29: 「許可の応答の履歴での表示は初期表示は開いた状態で閉じる押したら１行にして」 (#64's folded start, reversed):
    a permission comes open; 閉じる folds it to one line, and that fold stays through pending → sent; opened again it
    stays open; when nothing waits the fold is forgotten and the next permission comes open again."""
    parts = [_cut('55-history.js', n) for n in ('HIST_FOLD', 'histFoldKeys', 'histFoldState')]
    got = _node(parts, """(() => {
      const p = {id:'p1',status:'pending'};
      const initial = histFoldState('robot',[p],[],[]);
      HIST_FOLD.set('robot',{seen:new Set(),fresh:false,init:true});
      const closed = histFoldState('robot',[p],[],[]);
      p.status='sent'; const sent = histFoldState('robot',[p],[],[]);
      HIST_FOLD.set('robot',{opened:true});
      const opened = histFoldState('robot',[p],[],[]);
      const rebuild = histFoldState('robot',[p],[],[]);
      histFoldState('robot',[],[],[]);
      const next = histFoldState('robot',[{id:'p2',status:'pending'}],[],[]);
      return [initial.folded,initial.n,closed.folded,sent.folded,sent.n,opened.folded,rebuild.folded,next.folded];
    })()""")
    assert got == [False, 1, True, True, 1, False, False, False]
