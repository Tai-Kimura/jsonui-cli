"""The server room (ticket 2026-10-20-jui-viz-server-room, part B).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py, and rooms made of the boundary's
examples (document_tools' make_examples.py, written into this run's folder) plus rooms that cannot be read: one
broken JSON, one against the schema, one with a secret-shaped value. Waits are on the page's state (waits.until),
never on time; the server's reply is held back by the network route where an arm needs the read to take a while.

  * a room opened up close has its door; nothing is read (no POST /api/infra-docs) until the door is pressed
  * pressed (a real click on the door): while the reply is held the keypad's * grow and the bubble says it reads;
    then the server room opens, the model drawn (nodes, cables, floors)
  * Esc while it reads: the bubble goes, and the reply that comes later opens nothing
  * a room that cannot be read (broken JSON, the schema, a secret-shaped value): the keypad turns red, the bubble
    names the file and what is wrong — never a value — and the room stays
  * the large example (2,000 nodes, 5,000 edges, four providers): drawn, its frame times kept for the ticket; zoomed
    out the top groups become boxes and the labels thin out, zoomed in they come back
  * provider-crossing cables drawn apart (dashed); the environments switch (never overlaid); the folded ones out
    until asked for; the room's icons on their nodes; Esc back to the room
  * with reduced motion the * stand still and the bubble still shows
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, T, T_pattern, Watch, dump, new_page, ready
from lang_checks import doc_words_shot
from waits import until


def say(mark: str, node: str, action: str) -> str:
    """A flow step's toast head as 59-sr-flows.js words it (sr.flow.say: the mark, the node, the action's verb)."""
    return T("sr.flow.say", mark=mark, node=node, verb=T(f"sr.flow.action.{action}"))

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SR = "() => window.__dbg.sr()"
SPEC_SECRET = "postgres://orders@db-prod.internal:5432/orders"
MARKUP = '<b>x</b><img src=x onerror="window.__srMarkup=1">' 
#: a frame of the large model must come within this (ms; the slowest tenth of the frames, software GL)
FRAME_P90_MAX_MS = 250
#: the same arms in 2D (ticket 2026-10-23-viz-server-room-2d-mode, requester: 「機能は3Dと一緒」): every room opened from straight
#: above (the page's own choice per project, '*' for all); an arm the 2D cannot share says so where it is skipped
FLAT = {"on": False}
SR_FLAT_INIT = "try { localStorage.setItem('agent-view:srView', JSON.stringify({ '*': '2d' })); } catch (e) {}"


def _examples(jt: pathlib.Path) -> dict:
    spec = importlib.util.spec_from_file_location("infra_make_examples", jt.parent / "document_tools" / "tests" / "fixtures" / "infra" / "make_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.all_examples()


def _with_loop(examples: dict) -> dict:
    """The multi-provider room with one edge more, web -> kv: a triangle with api (web -> api -> kv), so a reach every step
    on holds an edge between two nodes already reached (the arm for the loop's closing edge; the example is a tree)."""
    doc = examples["multi-provider/docs/infra/system.json"]
    if not any(e["from"] == "web" and e["to"] == "kv" for e in doc["edges"]):
        doc["edges"].append({"from": "web", "to": "kv", "protocol": "https"})
    return examples


def _write(base: pathlib.Path, examples: dict, name: str, dest: str) -> pathlib.Path:
    for rel, data in examples.items():
        if rel.split("/")[0] != name:
            continue
        path = base / dest / rel.split("/", 1)[1]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (base / dest / ".git").mkdir(parents=True, exist_ok=True)
    return base / dest


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(v):
    """'#rrggbb' or 'rgb(r, g, b)' → (r, g, b)."""
    if v.startswith("#"):
        return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(float(x) for x in v[v.index("(") + 1:v.index(")")].split(",")[:3])


def _rgba(v):
    nums = [float(x) for x in v[v.index("(") + 1:v.index(")")].replace("/", ",").split(",")]
    return (*nums[:3], nums[3] if len(nums) > 3 else 1.0)


def _over(rgba, ground):
    g = _rgb(ground)
    a = rgba[3]
    return tuple(rgba[i] * a + g[i] * (1 - a) for i in range(3))


def _lum(v):
    r, g, b = _rgb(v) if isinstance(v, str) else v
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check(failures, cond, text):
    if not cond:
        failures.append(f"{'server-room-2d' if FLAT['on'] else 'server-room'}: {text}")


FLOW = "() => window.__dbg.srFlow()"


DRAWN = "() => window.__dbg.srFlowDrawn()"
# the nodes 検索する names (its branch's two ways and its two lanes)
SEARCH_NODES = {"browser", "web", "api", "kv", "d1", "queue", "r2"}


def _moves(f, lengths):
    """Each move of a flow played to its end: [from, to, length, ms], a depart paired with the first arrival at its end after it."""
    out, used = [], set()
    for frm, to, t0 in f["departs"]:
        k = next((i for i, (at, t1) in enumerate(f["reached"]) if i not in used and at == to and t1 >= t0), None)
        if k is None:
            continue
        used.add(k)
        out.append([frm, to, lengths.get(f"{frm}>{to}", lengths.get(f"{to}>{frm}")), f["reached"][k][1] - t0])
    return out


def _rests(f):
    """How long the light stayed before each move: at a node (from the last arrival before it) or at a branch (from the
    choice, when one came between)."""
    node, branch = [], []
    for frm, to, t0 in f["departs"][1:]:
        last = max((t for _, t in f["reached"] if t <= t0), default=None)
        chose = [t for _, _, t in f["chose"] if (last is None or t >= last) and t <= t0]
        if chose:
            branch.append(t0 - chose[-1])
        elif last is not None:
            node.append(t0 - last)
    return node, branch


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0


async def _play_search(page, speed, way="miss"):
    """検索する played to its end at `speed`, `way` chosen at its branch by a press."""
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.evaluate("(s) => window.__dbg.srFlowSpeed(s)", speed)
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", f"search at {speed}: its branch",
                timeout=60000, why=FLOW)
    await page.click(f"#sr-choices [data-sr-choice='{way}']")
    return await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", f"search at {speed}: the end", timeout=90000, why=FLOW)


async def run_flow_pace(page, out, failures, res):
    """The flows' pace and what is shown while one plays (ticket 2026-10-23-viz-sr-flow-replay-pace-and-focus; requester
    10-23: 「距離/sで設定して / スピード調整が欲しい。0.5-3.0くらいで / 各喉についた時にそれぞれ少し留まって欲しい。 / 再生中は
    関係ないノードは消して欲しい」), on the multi-provider room's 検索する: its moves go from a cable inside one cloud to one
    across to GCP, so their lengths differ."""
    fp = res["flowPace"] = {}
    await page.click("#sr-fit")
    fp["default"] = (await page.evaluate(FLOW))["show"]
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    fp["speeds"] = await page.evaluate("() => [...document.querySelectorAll(\"#sr-player [data-sr-fp='speed'] option\")].map((o) => [Number(o.value), o.textContent, o.selected])")
    check(failures, fp["default"] == "flow", f"a room not chosen for yet shows the nodes the flow names: {fp['default']}")
    check(failures, [v for v, _, _ in fp["speeds"]] == [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
          and [t for _, t, _ in fp["speeds"]][:3] == ["0.5×", "0.75×", "1.0×"],
          f"the speed is 0.5 to 3.0 by 0.25: {fp['speeds']}")
    # the pace: each move's time is its cable's length at one speed (world units a second), at 1.0 and at 3.0
    lengths = (await page.evaluate(FLOW))["lengths"]
    pace, rests = {}, {}
    for speed in (1.0, 3.0):
        f = await _play_search(page, speed)
        mv = _moves(f, lengths)
        pace[speed] = [[a, b, ln, round(ms), round(ln / ms * 1000, 2) if ln and ms > 0 else None] for a, b, ln, ms in mv]
        rests[speed] = _rests(f)
    fp["pace"] = pace
    fp["rests"] = {k: [[round(x) for x in v] for v in r] for k, r in rests.items()}
    u1 = [m[4] for m in pace[1.0] if m[4]]
    lens = [m[2] for m in pace[1.0] if m[2]]
    med1, med3 = _median(u1), _median([m[4] for m in pace[3.0] if m[4]])
    fp["perSec"] = {"1.0": med1, "3.0": med3, "lengthSpread": round(max(lens) / min(lens), 2) if lens else 0}
    check(failures, len(u1) >= 7 and fp["perSec"]["lengthSpread"] >= 1.5,
          f"検索する's moves are timed, and their cables differ in length (else the next arm proves nothing): {fp['perSec']} {pace[1.0]}")
    check(failures, u1 and all(0.75 * med1 <= u <= 1.3 * med1 for u in u1) and 7 <= med1 <= 13,
          f"at 1.0 every move goes the same distance a second (~10 units), a long cable taking longer: {pace[1.0]}")
    check(failures, med1 and 2.4 <= med3 / med1 <= 3.6, f"at 3.0 the light goes three times as far a second: {fp['perSec']}")
    node1, branch1 = rests[1.0]
    node3, _ = rests[3.0]
    fp["restMed"] = {"node1": round(_median(node1)), "branch1": [round(x) for x in branch1], "node3": round(_median(node3))}
    check(failures, len(node1) >= 5 and all(300 <= x <= 700 for x in node1),
          f"at 1.0 the light rests at each node it reaches (~400 ms) before it goes on: {fp['rests'][1.0]}")
    check(failures, len(branch1) == 1 and 650 <= branch1[0] <= 1300 and branch1[0] >= 1.6 * _median(node1),
          f"at a branch, once chosen, it rests twice as long as at a node: {fp['restMed']}")
    check(failures, _median(node3) and 2.2 <= _median(node1) / _median(node3) <= 3.8, f"the rests go by the speed too: {fp['restMed']}")

    # what is shown: at the branch, each of the four, read from the 3D (the nodes at their size, their tags, models and
    # cables); the floors faint while any node is hidden
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.evaluate("() => window.__dbg.srFlowSpeed(1)")
    every = await page.evaluate(DRAWN)
    fp["stopped"] = {"nodes": every["nodes"] == every["all"], "floors": [x["toGround"] for x in every["floors"]]}
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "search: its branch for the four",
                timeout=60000, why=FLOW)
    want = {"flow": SEARCH_NODES, "now": {"api", "kv", "d1"}, "seen": {"browser", "web", "api", "kv", "d1"}, "all": set(every["all"])}
    shown = fp["shown"] = {}
    for how in ("now", "seen", "all", "flow"):
        await page.click(f"#sr-player [data-sr-fp-show='{how}']")
        await page.wait_for_timeout(300)          # the tags are placed again on the next frames (srPlaceLabels)
        d = await page.evaluate(DRAWN)
        pressed = await page.evaluate("() => [...document.querySelectorAll('#sr-player [data-sr-fp-show]')].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.srFpShow)")
        cables_want = sorted(c for c in every["cables"] if set(c.split(">")) <= want[how])
        shown[how] = {"nodes": d["nodes"], "cables": d["cables"], "cablesWant": cables_want, "tags": d["tags"], "models": d["models"], "pressed": pressed,
                      "floors": sorted({x["toGround"] for x in d["floors"]}),
                      "floorsSized": [x["scale"] for x in d["floors"]] == [x["scale"] for x in every["floors"]]}
        check(failures, d["nodes"] == sorted(want[how]) and d["cables"] == cables_want and set(d["tags"]) <= want[how] and set(d["models"]) <= want[how]
              and pressed == [how],
              f"{how}: the nodes drawn are {sorted(want[how])}, their cables only, no other tag or model: {shown[how]}")
        if how == "now":   # a node chosen while it plays: its strong cables only to the nodes shown
            await page.evaluate("() => window.__dbg.srSelect('api')")
            focus_want = len([c for c in every["cables"] if "api" in c.split(">") and set(c.split(">")) <= want[how]])
            shown[how]["focus"] = [(await page.evaluate(DRAWN))["focus"], focus_want]
            check(failures, focus_want >= 1 and shown[how]["focus"][0] == focus_want,
                  f"now: a node chosen while it plays draws strong only its cables to the nodes shown: {shown[how]['focus']}")
        faint = shown[how]["floors"]
        if how == "all":
            check(failures, all(abs(g) < 0.02 for g in faint), f"all: the floors as built: {shown[how]['floors']}")
        else:
            check(failures, faint and all(0.5 <= g <= 0.7 for g in faint) and shown[how]["floorsSized"],
                  f"{how}: every floor still drawn, faint, as a map: {shown[how]['floors']}")
    await page.screenshot(path=str(out / "flow-show-flow.png"))
    fp["kept"] = await page.evaluate("() => { try { return Object.values(JSON.parse(localStorage.getItem('agent-view:srFlow')) || {}); } catch (e) { return null; } }")
    check(failures, fp["kept"] and fp["kept"][0].get("show") == "flow" and fp["kept"][0].get("speed") == 1,
          f"the nodes shown and the speed are kept for the room: {fp['kept']}")
    # and chosen on the player's bar (its speed list, its buttons), they come back with the room built again
    await page.select_option("#sr-player [data-sr-fp='speed']", "1.5")
    await page.click("#sr-player [data-sr-fp-show='seen']")
    await page.evaluate("() => window.__dbg.srRebuildHere()")
    await until(page, "() => window.__dbg.sr().built && !window.__dbg.srFlow().playing", "rebuilt with a speed and a choice chosen", timeout=20000)
    after = await page.evaluate(FLOW)
    fp["keptRebuilt"] = {"speed": after["speed"], "show": after["show"]}
    check(failures, fp["keptRebuilt"] == {"speed": 1.5, "show": "seen"},
          f"the speed and the nodes shown chosen on the player's bar come back with the room built again: {fp['keptRebuilt']}")
    await page.evaluate("() => { window.__dbg.srFlowSpeed(1); window.__dbg.srFlowShow('flow'); }")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "search: its branch again after the rebuild",
                timeout=60000, why=FLOW)
    await page.click("#sr-player [data-sr-fp='stop']")
    back = await until(page, f"() => {{ const d = ({DRAWN})(); return d.nodes.length === d.all.length ? d : null; }}", "stopped: every node again", timeout=5000, why=DRAWN)
    fp["back"] = {"nodes": back["nodes"] == back["all"], "cables": back["cables"] == every["cables"], "floors": sorted({x["toGround"] for x in back["floors"]})}
    check(failures, fp["back"]["nodes"] and fp["back"]["cables"] and all(abs(g) < 0.02 for g in fp["back"]["floors"]),
          f"stopped: every node, cable and floor as before: {fp['back']}")

    # the camera: the whole room in view, it never moves — pulled back from fit and moved over until the flow's start is
    # near the page's edge, past where a light would be followed, the whole room still in view (at fit the flow's nodes
    # sit well inside: nothing would be followed anyway); up close on api, it goes after the light as it leaves the page
    # (the flow started and paused first: the side bar it opens takes its column from the room)
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.evaluate("() => window.__dbg.srFlowSpeed(3)")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await page.click("#sr-player [data-sr-fp='toggle']")
    await page.click("#sr-fit")
    await page.wait_for_timeout(400)
    await page.evaluate("() => window.__dbg.srZoom(1.6)")
    for _ in range(200):
        await page.evaluate("() => window.__dbg.srPanFrom('browser', 0.4)")
        d = await page.evaluate(DRAWN)
        if not d["whole"]:
            await page.evaluate("() => window.__dbg.srPanFrom('browser', -0.4)")
            break
        if d["ndc"]["browser"] > 0.9:
            break
    snug = await page.evaluate(DRAWN)
    cam0 = snug["cam"]
    await page.click("#sr-player [data-sr-fp='toggle']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "search, whole: its branch", timeout=60000, why=FLOW)
    await page.click("#sr-choices [data-sr-choice='hit']")
    whole = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "search, whole: the end", timeout=90000, why=FLOW)
    cam1 = (await page.evaluate(DRAWN))["cam"]
    fp["whole"] = {"follows": whole["follows"], "moved": round(sum((a - b) ** 2 for a, b in zip(cam0, cam1)) ** 0.5, 3), "whole": snug["whole"],
                   "browserNdc": snug["ndc"]["browser"]}
    check(failures, fp["whole"]["whole"] and fp["whole"]["browserNdc"] > 0.85,
          f"the whole room in view, the flow's start near the page's edge (else the next arm proves nothing): {fp['whole']}")
    check(failures, fp["whole"]["follows"] == 0 and fp["whole"]["moved"] < 0.05,
          f"the whole room in view: the camera stays where it is while it plays: {fp['whole']}")
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.evaluate("() => window.__dbg.srSelect('api')")
    await page.click("#sr-board [data-sr-act='focus']")
    await page.wait_for_timeout(600)
    cam0 = (await page.evaluate(DRAWN))["cam"]
    near = await _play_search(page, 1.0, "hit")
    cam1 = (await page.evaluate(DRAWN))["cam"]
    fp["near"] = {"follows": near["follows"], "moved": round(sum((a - b) ** 2 for a, b in zip(cam0, cam1)) ** 0.5, 3)}
    check(failures, fp["near"]["follows"] > 0 and fp["near"]["moved"] > 1,
          f"up close, a light leaving the page is followed: {fp['near']}")
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.click("#sr-fit")


# the side bar's rows read in the page: each row's arrow sits between the row before and its own step, the current row's
# edge colour against the others', and whether the current row is in the side bar's view
ROUTE_GEOM = """() => { const rows = [...document.querySelectorAll('#sr-route-list > .sr-rt')], R = document.getElementById('sr-route').getBoundingClientRect();
  const between = rows.slice(1).map((li, i) => { const a = li.querySelector(':scope > .sr-rt-arrow'), prev = rows[i].querySelector('.sr-rt-step').getBoundingClientRect(),
    own = li.querySelector('.sr-rt-step').getBoundingClientRect(); if (!a) return false; const r = a.getBoundingClientRect(); return r.height > 0 && r.top >= prev.bottom - 1 && r.bottom <= own.top + 1; });
  const cur = rows.find((li) => li.querySelector('.sr-rt-step').getAttribute('aria-current') === 'true');
  const edge = (li) => getComputedStyle(li.querySelector('.sr-rt-step')).borderLeftColor;
  const c = cur && cur.querySelector('.sr-rt-step').getBoundingClientRect();
  const ch = document.getElementById('sr-choices'), q = !ch.hidden && ch.getBoundingClientRect(), box = document.getElementById('sr-route');
  return { between, curEdge: cur ? edge(cur) : null, otherEdges: [...new Set(rows.filter((li) => li !== cur).map(edge))],
           curInView: !!c && c.top >= R.top - 1 && c.bottom <= R.bottom + 1, overflows: box.scrollHeight > box.clientHeight + 4,
           choicesInView: q ? q.top >= R.top - 1 && q.bottom <= R.bottom + 1 : null }; }"""
# the top bar: 範囲で寄る just left of 環境, both on one line, and what each part of the page covers
BAR_ORDER = """() => { const head = document.querySelector('#sr .sr-head'), kids = [...head.children], bz = document.getElementById('sr-boxzoom'),
  env = document.getElementById('sr-env').closest('label'), a = bz.getBoundingClientRect(), b = env.getBoundingClientRect();
  return { order: kids.indexOf(env) - kids.indexOf(bz), leftOf: a.right <= b.left + 1, oneLine: Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2) < 6,
           beforeGrow: kids.indexOf(bz) < kids.indexOf(head.querySelector('.grow')) }; }"""
OVERLAP = """() => { const box = (el) => { if (!el || el.hidden || !el.getClientRects().length) return null; const r = el.getBoundingClientRect(); return r.width && r.height ? r : null; };
  const route = box(document.getElementById('sr-route')), hit = (o) => !!(route && o && route.left < o.right - 1 && o.left < route.right - 1 && route.top < o.bottom - 1 && o.top < route.bottom - 1);
  return { route: !!route, board: hit(box(document.getElementById('sr-board'))), player: hit(box(document.getElementById('sr-player'))), roster: hit(box(document.getElementById('roster'))) }; }"""


async def run_flow_route(page, out, failures, res):
    """The route's words in a side bar (the requester 10-24: 「3d/2dのオブジェクト上に文字が出るのみづらいからサイドに光に合わせて
    順番に履歴として出てそれが下矢印で繋がっていく感じにしようか / 選択肢を選ぶのもそのサイドバーで選ぶ / あとは範囲を絞るの
    メニューは右すぎて気づきづらいから環境絞り込みの左に移動させて残りをずらして」): nothing written over the room, a row
    per step in the light's order joined by down arrows, the current one set apart, a branch chosen there (自動 too), a
    row pressed choosing its node, and 範囲で寄る left of 環境."""
    rt = res["flowRoute"] = {}
    rt["bar"] = await page.evaluate(BAR_ORDER)
    check(failures, rt["bar"] == {"order": 1, "leftOf": True, "oneLine": True, "beforeGrow": True},
          f"範囲で寄る sits just left of 環境 on the top bar, the rest after it: {rt['bar']}")
    # the room seen whole when a flow starts, on a page narrow enough that the side bar's column would cut it from the
    # camera as it was: it is fitted again, and seen whole beside the side bar
    size = page.viewport_size
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    await page.set_viewport_size({"width": 900, "height": 760})
    await page.wait_for_timeout(300)
    await page.click("#sr-fit")
    await page.wait_for_timeout(300)
    cam0 = await page.evaluate("() => window.__dbg.srCamNow()")
    whole0 = (await page.evaluate(DRAWN))["whole"]
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await page.click("#sr-player [data-sr-fp='toggle']")
    await page.wait_for_timeout(300)
    fit = await page.evaluate("() => window.__dbg.srFlowRoomFit()")
    cv, bar = fit["canvas"], fit["bar"]
    seen_h = (min(cv[3], bar[1]) if bar and bar[1] > cv[1] else cv[3]) - cv[1]    # the canvas above the player's bar
    out_of_view = [[r["id"], r["kind"]] for r in fit["rects"] if r["behind"] or r["box"][0] < 0 or r["box"][1] < 0 or r["box"][2] > cv[2] - cv[0] or r["box"][3] > seen_h]
    fit = {"n": len(fit["rects"]), "out": out_of_view, "seen": [cv[2] - cv[0], seen_h]}
    rt["wholeWithBar"] = {"before": whole0, "keptWouldBe": await page.evaluate("(c) => window.__dbg.srWholeFrom(c)", cam0), "now": (await page.evaluate(DRAWN))["whole"],
                          "out": fit["out"], "rects": fit["n"], "seen": fit["seen"]}
    check(failures, rt["wholeWithBar"]["before"] is True and rt["wholeWithBar"]["keptWouldBe"] is False,
          f"the room seen whole, and the side bar's column would cut it from the camera as it was (else the next arm proves nothing): {rt['wholeWithBar']}")
    # every node's shape and tag inside the room's part of the page (not under the board, the side bar or the player's bar)
    check(failures, rt["wholeWithBar"]["now"] is True and fit["n"] > 0 and fit["out"] == [],
          f"the room seen whole before the side bar opened has every shape and tag in view beside it, above the player's bar: {rt['wholeWithBar']}")
    await page.screenshot(path=str(out / "flow-route-narrow.png"))
    await page.click("#sr-player [data-sr-fp='stop']")
    # and on a wide, low page, where the room's height decides its frame: nothing under the player's bar
    await page.set_viewport_size({"width": 1280, "height": 520})
    await page.wait_for_timeout(300)
    await page.click("#sr-fit")
    await page.wait_for_timeout(300)
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await page.click("#sr-player [data-sr-fp='toggle']")
    await page.wait_for_timeout(300)
    low = await page.evaluate("() => window.__dbg.srFlowRoomFit()")
    cv, bar = low["canvas"], low["bar"]
    seen_h = (min(cv[3], bar[1]) if bar and bar[1] > cv[1] else cv[3]) - cv[1]
    rt["lowPage"] = {"barCovers": bool(bar and cv[1] < bar[1] < cv[3]), "seen": [cv[2] - cv[0], seen_h], "rects": len(low["rects"]),
                     "out": [[r["id"], r["kind"]] for r in low["rects"] if r["behind"] or r["box"][0] < 0 or r["box"][1] < 0 or r["box"][2] > cv[2] - cv[0] or r["box"][3] > seen_h]}
    check(failures, rt["lowPage"]["barCovers"], f"on a low page the player's bar covers part of the room (else the next arm proves nothing): {rt['lowPage']}")
    check(failures, rt["lowPage"]["rects"] > 0 and rt["lowPage"]["out"] == [], f"on a low page every shape and tag is in view above the player's bar: {rt['lowPage']}")
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.set_viewport_size(size)
    await page.wait_for_timeout(300)
    await page.evaluate("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='stop']\"); if (b) b.click(); }")
    # a short page, so the side bar runs longer than it shows and must turn to its newest row (and to the branch's ways)
    size = page.viewport_size
    await page.set_viewport_size({"width": size["width"], "height": 520})
    await page.click("#sr-fit")
    await page.evaluate("() => window.__dbg.srFlowSpeed(1)")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    over = []      # the words over the room, read on every arrival
    first = await until(page, f"() => {{ const f = ({FLOW})(); return f.arrivals.length >= 1 ? f : null; }}", "route: the first arrival", timeout=30000, why=FLOW)
    over.append(first["toasts"])

    at = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "route: its branch", timeout=60000, why=FLOW)
    over.append(at["toasts"])
    rt["atBranch"] = {"rows": at["rows"], "route": at["route"], "geom": await page.evaluate(ROUTE_GEOM), "overlap": await page.evaluate(OVERLAP)}
    check(failures, at["route"] and at["route"]["choicesIn"] and at["choices"] == ["hit", "miss"] and rt["atBranch"]["geom"]["choicesInView"] is True,
          f"at the branch its ways are in the side bar, in its view, none over the room: {rt['atBranch']['route']} {at['choices']} {rt['atBranch']['geom']}")
    check(failures, rt["atBranch"]["overlap"] == {"route": True, "board": False, "player": False, "roster": False},
          f"the side bar covers neither the board, the player's bar nor the robot list: {rt['atBranch']['overlap']}")
    await page.screenshot(path=str(out / "flow-route-branch.png"))
    # 自動 turned on and off while it waits: the default's mark says so at once (read in the same task, before a frame
    # could take the default)
    rt["autoMark"] = await page.evaluate("""() => { const cb = document.querySelector("#sr-player [data-sr-fp='auto']"), mark = () => document.querySelector('#sr-choices [data-default] small').textContent;
      cb.click(); const on = mark(); cb.click(); return [on, mark()]; }""")
    check(failures, rt["autoMark"] == [T("sr.flow.choice.auto"), T("sr.flow.choice.default")],
          f"自動 turned on and off at a branch changes its default's mark in the side bar: {rt['autoMark']}")
    await page.click("#sr-route #sr-choices [data-sr-choice='miss']")
    done = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "route: the end", timeout=90000, why=FLOW)
    over.append(done["toasts"])
    geom = await page.evaluate(ROUTE_GEOM)
    rows = done["rows"]
    arrivals = [r for r in rows[1:-1] if " → " not in r["text"]]
    rt["done"] = {"rows": [[r["text"], r["node"], r["arrow"], r["current"]] for r in rows], "reached": [t for t, _ in done["reached"]], "geom": geom, "over": over}
    check(failures, all(not o for o in over), f"nothing of the route is written over the room while it plays: {over}")
    check(failures, done["chosen"] == ["KV に結果が有る？ → 無い"] and say("📖", "d1", "read") in [r["text"] for r in rows],
          f"the way chosen in the side bar is the way played: {done['chosen']}")
    check(failures, len(rows) == 1 + len(done["reached"]) + len(done["chose"]) + 1 and [r["node"] for r in arrivals] == rt["done"]["reached"]
          and rows[0]["text"] == "👤 検索する" and rows[-1]["text"] == T("sr.flow.end") and [r["text"] for r in rows] == done["log"],
          f"a row per step in the light's order: the start, each node reached, the way chosen, the end: {rt['done']['rows']} / {rt['done']['reached']}")
    check(failures, [r["arrow"] for r in rows] == [False] + [True] * (len(rows) - 1) and all(geom["between"]) and len(geom["between"]) == len(rows) - 1,
          f"each row joined to the one before by a down arrow between them: {geom['between']}")
    check(failures, [r["current"] for r in rows] == [False] * (len(rows) - 1) + [True] and geom["curEdge"] not in geom["otherEdges"],
          f"the newest row is the current one, set apart: {geom}")
    check(failures, geom["overflows"] and geom["curInView"], f"the side bar runs longer than it shows and is turned to its newest row: {geom}")
    await page.set_viewport_size(size)
    # one step back from the end: the side bar back to the rows it had then, the last of them current
    before = len(rows)
    await page.click("#sr-player [data-sr-fp='back']")
    back = await page.evaluate(FLOW)
    rt["back"] = {"before": before, "rows": len(back["rows"]), "log": len(back["log"]), "current": [r["current"] for r in back["rows"]]}
    check(failures, rt["back"]["rows"] < before and rt["back"]["rows"] == rt["back"]["log"] and rt["back"]["current"] == [False] * (rt["back"]["rows"] - 1) + [True],
          f"a step back takes the side bar back to its rows then, the last current: {rt['back']}")
    # a row pressed: its node chosen on the board
    await page.click("#sr-route-list [data-sr-rt='d1']")
    rt["pressed"] = await page.evaluate("() => { const dt = [...document.querySelectorAll('#sr-board dt')].find((d) => d.textContent === 'id'); return dt ? dt.nextElementSibling.textContent : null; }")
    check(failures, rt["pressed"] == "d1", f"a row pressed chooses its node: {rt['pressed']}")
    # 自動 in the side bar: the default says it is taken by itself, and is
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await page.check("#sr-player [data-sr-fp='auto']")
    shown = await until(page, "() => { const b = document.querySelector('#sr-route #sr-choices:not([hidden]) [data-default] small'); return b ? b.textContent : null; }",
                        "route: 自動's mark at the branch", timeout=60000, why=FLOW)
    auto = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "route, 自動: the end", timeout=90000, why=FLOW)
    rt["auto"] = {"mark": shown, "chosen": auto["chosen"]}
    check(failures, shown == T("sr.flow.choice.auto") and auto["chosen"] == ["KV に結果が有る？ → 有る"],
          f"自動: the side bar's default marked as taken by itself, and taken: {rt['auto']}")
    await page.uncheck("#sr-player [data-sr-fp='auto']")
    await page.click("#sr-player [data-sr-fp='stop']")
    rt["closed"] = await page.evaluate("() => document.getElementById('sr-route').hidden")
    check(failures, rt["closed"] is True, f"stopped: the side bar goes: {rt['closed']}")


async def run_flows(page, out, failures, res):
    """Flows played (the server room ticket's item 7) on the multi-provider room's two: 検索する (browser, a branch with a
    default, lanes side by side) and 毎晩の写し (r2, a schedule)."""
    fl = res["flows"] = {}
    await page.evaluate("() => window.__dbg.srSelect(null)")
    fl["starts"] = sorted((await page.evaluate(FLOW))["starts"])
    check(failures, fl["starts"] == ["browser", "r2"], f"a cone over each node that starts a flow, and only there: {fl['starts']}")
    await page.evaluate("() => window.__dbg.srSelect('dns')")
    fl["dnsList"] = await page.evaluate("() => document.querySelectorAll('#sr-board [data-sr-flow]').length")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    fl["browserList"] = await page.evaluate("() => [...document.querySelectorAll('#sr-board [data-sr-flow]')].map((b) => [b.dataset.srFlow, b.textContent])")
    check(failures, fl["dnsList"] == 0 and fl["browserList"] == [["search", "👤 検索する"]],
          f"a node with no flow lists none; the browser lists its flow with the trigger's mark: {fl['dnsList']} {fl['browserList']}")
    # a node with many rows (the ticket 2026-10-21-jui-viz-flow-chosen-path-list-has-no-separator): its flows right under what
    # was chosen, and the board turned there (from its top, where 構成 and 凡例 fill it), so the button is pressable where it
    # shows — on a page too short for the board
    size = page.viewport_size
    await page.set_viewport_size({"width": size["width"], "height": 460})
    await page.evaluate("() => window.__dbg.srSelect('r2')")
    await page.evaluate("() => { const B = document.getElementById('sr-board'); B.scrollTop = 0; }")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    fl["boardInView"] = await page.evaluate("""() => { const B = document.getElementById('sr-board'), b = B.querySelector('[data-sr-flow]');
      const e = B.querySelector('.sr-edges'), r = b.getBoundingClientRect(), R = B.getBoundingClientRect();
      return { overflows: B.scrollHeight > B.clientHeight, inView: r.top >= R.top && r.bottom <= R.bottom,
               beforeEdges: !!(e && (b.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING)) }; }""")
    # and only then: the board read back up to its top with the same node chosen, a board drawn again (the same node chosen
    # again, as a slice's push draws it) stays where it was read to — its heading is below, so a turn would move it
    fl["boardKept"] = await page.evaluate("""() => { const B = document.getElementById('sr-board'); B.scrollTop = 0;
      const below = B.querySelector('[data-sr-sel-head]').getBoundingClientRect().top - B.getBoundingClientRect().top > 20;
      window.__dbg.srSelect('browser'); return { below, top: Math.round(B.scrollTop) }; }""")
    await page.set_viewport_size(size)
    check(failures, fl["boardKept"] == {"below": True, "top": 0},
          f"a board drawn again with the same node chosen is left where it was read to (its top, the heading below): {fl['boardKept']}")
    check(failures, fl["boardInView"] == {"overflows": True, "inView": True, "beforeEdges": True},
          f"a chosen node's flows sit under its rows and the board turns to them: pressable without a scroll: {fl['boardInView']}")

    # played step by step: the side bar's rows, the branch's choices and the edges ahead
    await page.click("#sr-board [data-sr-flow='search']")
    at_branch = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' ? f : null; }}", "search: at its branch",
                            timeout=30000, why=FLOW)
    fl["atBranch"] = {k: at_branch[k] for k in ("log", "choices", "hints", "pos", "history")}
    check(failures, at_branch["log"][:3] == ["👤 検索する", say("→", "web", "request"), say("→", "api", "request")] and at_branch["choices"] == ["hit", "miss"]
          and at_branch["hints"] == 2 and at_branch["pos"] == "api",
          f"the start's row, a verb's row per move, then the branch stops with its choices and their first edges: {fl['atBranch']}")
    await page.click("#sr-choices [data-sr-choice='miss']")
    lanes = await until(page, f"() => {{ const f = ({FLOW})(); return f.lights >= 2 ? f : null; }}", "search: the two lanes at once",
                        timeout=30000, why=FLOW)
    done = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "search: the end", timeout=40000, why=FLOW)
    when = {}
    for frm, to, t in done["departs"]:
        when.setdefault(f"{frm}>{to}", t)
    lane_gap = abs(when.get("api>queue", 0) - when.get("api>r2", 1e9))
    fl["miss"] = {"chosen": done["chosen"], "log": done["log"], "lanes": lanes["lights"], "laneStartGapMs": round(lane_gap)}
    # the lanes start at once (each then takes its own cable's length: run_flow_pace); one after the other, the second
    # would start after the first one's move and rest
    check(failures, lane_gap < 100, f"lanes side by side start together, not one after the other: {fl['miss']['laneStartGapMs']} ms")
    check(failures, done["chosen"] == ["KV に結果が有る？ → 無い"] and say("📖", "d1", "read") in done["log"] and say("📖", "kv", "read") not in done["log"]
          and {say("📥", "queue", "enqueue"), say("💾", "r2", "write")} <= set(done["log"]) and done["log"][-2:] == [say("←", "ブラウザ", "response"), T("sr.flow.end")],
          f"the choice taken is the way played, the other not; the lanes and the way back: {fl['miss']}")
    await page.screenshot(path=str(out / "flow-light.png"))
    fl["chosenRows"] = await page.evaluate("""() => { const ol = document.querySelector('#sr-player .sr-fp-chosen'); if (!ol) return null;
      const cs = getComputedStyle(ol), w = ol.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      return [...ol.children].map((li) => [Math.round(li.getBoundingClientRect().width), Math.round(w)]); }""")
    check(failures, fl["chosenRows"] and all(lw >= w - 2 for lw, w in fl["chosenRows"]),
          f"each choice taken is a line of its own on the player's bar (none run on after another): {fl['chosenRows']}")
    # back to the branch (each step back undoes one), choose again
    for _ in range(done["history"] - at_branch["history"] + 1):
        await page.click("#sr-player [data-sr-fp='back']")
    await page.click("#sr-player [data-sr-fp='step']")
    again = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "back at the branch",
                        timeout=10000, why=FLOW)
    await page.click("#sr-choices [data-sr-choice='hit']")          # a choice plays on
    redone = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "search again: the end", timeout=40000, why=FLOW)
    fl["back"] = {"chosen": redone["chosen"], "kv": say("📖", "kv", "read") in redone["log"], "atBranchAgain": again["pos"]}
    check(failures, again["pos"] == "api" and redone["chosen"] == ["KV に結果が有る？ → 有る"] and fl["back"]["kv"],
          f"back to the branch and the other way chosen: {fl['back']}")

    # the speed: the time between the first two arrivals at 1.0 and at 2.0; 自動 takes the default
    gaps = {}
    for speed in (1.0, 2.0):
        await page.click("#sr-player [data-sr-fp='stop']")
        await page.evaluate("(s) => window.__dbg.srFlowSpeed(s)", speed)
        await page.click("#sr-board [data-sr-flow='search']")
        f = await until(page, f"() => {{ const f = ({FLOW})(); return f.arrivals.length >= 2 ? f : null; }}", f"two arrivals at {speed}", timeout=30000, why=FLOW)
        gaps[speed] = f["arrivals"][1] - f["arrivals"][0]
    fl["gaps"] = gaps
    ratio = gaps[1.0] / gaps[2.0] if gaps[2.0] else 0
    check(failures, 1.5 <= ratio <= 2.6, f"twice the speed, half the time between two steps: {gaps} (ratio {ratio:.2f})")
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.evaluate("() => window.__dbg.srFlowSpeed(3)")
    await page.click("#sr-board [data-sr-flow='search']")
    await page.check("#sr-player [data-sr-fp='auto']")
    auto = await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'done' ? f : null; }}", "自動: the end", timeout=40000, why=FLOW)
    fl["auto"] = auto["chosen"]
    check(failures, auto["chosen"] == ["KV に結果が有る？ → 有る"], f"自動: the default taken without a press: {auto['chosen']}")
    await page.uncheck("#sr-player [data-sr-fp='auto']")
    # pulled back over the room, the light keeps a radius you can see (7 px at the least)
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.evaluate("() => window.__dbg.srFlowSpeed(1)")
    await page.evaluate("() => window.__dbg.srZoom(8)")
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    far = await until(page, f"() => {{ const f = ({FLOW})(); return f.lightPx !== null ? f : null; }}", "search: a light moving, far", timeout=30000, why=FLOW)
    fl["lightPxFar"] = far["lightPx"]
    check(failures, far["lightPx"] >= 6.5, f"pulled back, a moving light is drawn at least 7 px in radius: {far['lightPx']}")
    # the light is in the cable, not a ball on it (ticket 2026-10-22-viz-server-room-palette-and-light-flow): no sphere in the
    # flow's layer, each light the cable's two shader layers, and its head going along its cable while it plays: seen part
    # way (between 0.1 and 0.6 of it), then past 0.6 — a head held near its start, or one that jumps to the end, is not a
    # light that flows
    mid = await until(page, f"() => {{ const f = ({FLOW})(); return f.lightHead !== null && f.lightHead > 0.1 && f.lightHead < 0.6 ? f : null; }}",
                      "search: the head part way along its cable", timeout=10000, why=FLOW)
    later = await until(page, f"(h) => {{ const f = ({FLOW})(); return f.lightHead !== null && f.lightHead >= 0.6 && f.lightHead > h ? f : null; }}",
                        "search: the head past 0.6 of its cable", arg=mid["lightHead"], timeout=10000, why=FLOW)
    fl["cableLight"] = {"spheres": (far["spheres"], later["spheres"]), "materials": sorted(set(later["lightMaterials"])), "head": (mid["lightHead"], later["lightHead"])}
    check(failures, fl["cableLight"]["spheres"] == (0, 0) and fl["cableLight"]["materials"] == ["ShaderMaterial:uHead+ShaderMaterial:uHead"]
          and 0.1 < mid["lightHead"] < 0.6 <= later["lightHead"] <= 1,
          f"the flow's light runs through its cable (a head in the cable's shader), no ball travels: {fl['cableLight']}")
    check(failures, mid["lightOnPath"] is True and later["lightOnPath"] is True, f"the flow's light runs along its cable's path, over what it rises over: {mid['lightOnPath']} {later['lightOnPath']}")
    await page.evaluate("() => window.__dbg.srZoom(1 / 8)")
    # a schedule's flow: its mark and its schedule as written
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.evaluate("() => window.__dbg.srSelect('r2')")
    await page.click("#sr-board [data-sr-flow='nightly-copy']")
    night = await until(page, f"() => {{ const f = ({FLOW})(); return f.rows.length ? f : null; }}", "毎晩の写し: its first row", timeout=10000, why=FLOW)
    fl["schedule"] = [night["rows"][0]["text"], night["rows"][0]["sub"]]
    check(failures, fl["schedule"] == ["⏰ 毎晩の写し", "cron(0 3 * * ? *)"], f"a schedule's flow starts with ⏰ and its schedule: {night['rows']}")
    await page.click("#sr-player [data-sr-fp='stop']")
    await page.evaluate("() => window.__dbg.srFlowSpeed(1)")

    # the 3D rebuilt while it plays (the theme turned): the flow stops, its light and side bar gone, nothing plays on
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.arrivals.length >= 1 && f.state === 'play' ? f : null; }}", "search: playing",
                timeout=30000, why=FLOW)
    dark = await page.evaluate("() => window.__dbg.srTheme().dark")
    await page.emulate_media(color_scheme="light" if dark else "dark")
    await until(page, f"(d) => window.__dbg.sr().built && window.__dbg.srTheme().dark === d", "rebuilt in the other theme", arg=not dark)
    rebuilt = await page.evaluate(FLOW)
    await page.wait_for_timeout(1500)                    # at 1.0 that is past the next step: a player left alive would have said it
    later = await page.evaluate(FLOW)
    fl["rebuilt"] = {k: (rebuilt[k], later[k]) for k in ("playing", "rows", "lights", "choices")}
    fl["rebuilt"]["dom"] = await page.evaluate("() => [document.querySelectorAll('#sr-route-list > li').length, document.getElementById('sr-choices').hidden, document.getElementById('sr-route').hidden]")
    check(failures, all(r["playing"] is None and not r["rows"] and r["lights"] == 0 and not r["choices"] for r in (rebuilt, later))
          and fl["rebuilt"]["dom"] == [0, True, True],
          f"a rebuild while it plays stops the flow, its light and side bar gone, nothing played on: {fl['rebuilt']}")
    await page.emulate_media(color_scheme="dark" if dark else "light")
    await until(page, f"(d) => window.__dbg.sr().built && window.__dbg.srTheme().dark === d", "the theme back", arg=dark)
    # and while it waits at a branch, its choices shown: the rebuild takes them away too
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "search: at its branch again",
                timeout=30000, why=FLOW)
    await page.emulate_media(color_scheme="light" if dark else "dark")
    await until(page, f"(d) => window.__dbg.sr().built && window.__dbg.srTheme().dark === d", "rebuilt at the branch", arg=not dark)
    at_branch = await page.evaluate(FLOW)
    fl["rebuiltAtBranch"] = {"playing": at_branch["playing"], "choices": at_branch["choices"],
                             "hidden": await page.evaluate("() => document.getElementById('sr-choices').hidden")}
    check(failures, at_branch["playing"] is None and not at_branch["choices"] and fl["rebuiltAtBranch"]["hidden"] is True,
          f"a rebuild while it waits at a branch takes its choices away: {fl['rebuiltAtBranch']}")
    await page.emulate_media(color_scheme="dark" if dark else "light")
    await until(page, f"(d) => window.__dbg.sr().built && window.__dbg.srTheme().dark === d", "the theme back again", arg=dark)
    # コスト while a flow waits at its branch (ticket 2026-10-21-jui-viz-cost-view-box-zoom-takes-the-clicks): the flow is
    # the 3D's, so it stops, and the cost page is over the flow's layers (this room has no load definition: its words)
    await page.evaluate("() => window.__dbg.srSelect('browser')")
    await page.click("#sr-board [data-sr-flow='search']")
    await until(page, f"() => {{ const f = ({FLOW})(); return f.state === 'branch' && f.choices.length ? f : null; }}", "search: at its branch for コスト",
                timeout=30000, why=FLOW)
    await page.click("#sr-mode-cost")
    await until(page, "() => window.__dbg.srCost().mode === 'cost'", "コスト over the flow")
    f = await page.evaluate(FLOW)
    fl["cost"] = {"playing": f["playing"], "choicesHidden": await page.evaluate("() => document.getElementById('sr-choices').hidden"),
                  "z": await page.evaluate("() => ['sr-cost', 'sr-player', 'sr-choices', 'sr-toasts'].map((id) => Number(getComputedStyle(document.getElementById(id)).zIndex) || 0)")}
    check(failures, f["playing"] is None and fl["cost"]["choicesHidden"] and fl["cost"]["z"][0] > max(fl["cost"]["z"][1:]),
          f"コスト stops the flow and is drawn over its player, choices and the migration's tags: {fl['cost']}")
    await page.click("#sr-mode-3d")
    await until(page, "() => { const c = window.__dbg.srCost(); return c.mode === '3d' && !c.paused; }", "the 3D after コスト")


def _routes_ok(failures, where, r):
    """Every cable on its nodes' sides (on the outline as drawn, at a height within the node), flat when nothing stands on
    its straight line, rising over what does (above its top at its middle) — and at least one of the first kind."""
    if FLAT["on"]:   # 2D (srCableRoutesFlat): one height; around what is on the way with square corners, never through it
        check(failures, r["cables"] > 0 and r["ends"] == 2 * r["cables"] and r["offOutline"] == 0 and r["offHeight"] == 0,
              f"{where}: every cable ends on its tiles' outlines, all at one height: {r}")
        check(failures, r["flat"] > 0 and r["notFlat"] == 0, f"{where}: a cable with nothing on its way is straight: {r}")
        check(failures, r["crossing"] == 0 and r["notSquare"] == 0, f"{where}: a bent cable turns square corners and runs through no tile: {r}")
        check(failures, r["blocked"] <= max(1, r["cables"] // 50), f"{where}: a cable left straight across a tile (no clear route) is rare: {r}")
        check(failures, r["bundlesOff"] == 0, f"{where}: the far view's bundles run from box side to box side: {r['bundles']} bundles, {r['bundlesOff']} ends off")
        return
    check(failures, r["cables"] > 0 and r["ends"] == 2 * r["cables"] and r["offOutline"] == 0 and r["offHeight"] == 0,
          f"{where}: every cable ends on its nodes' sides, at a height within them: {r}")
    check(failures, r["flat"] > 0 and r["notFlat"] == 0, f"{where}: a cable with nothing on its way is flat: {r}")
    check(failures, r["notRising"] == 0 and r["under"] == 0, f"{where}: a cable with something on its way rises over it: {r}")
    check(failures, r["offSide"] == 0, f"{where}: every end 0.3 above its node's foot (half its height at most): {r['offSide']} off")
    check(failures, r["lowOver"] == 0, f"{where}: a rising cable passes 0.25 over what it crosses: {r['lowOver']} lower")
    check(failures, r["bundlesOff"] == 0, f"{where}: the far view's bundles run from box side to box side: {r['bundles']} bundles, {r['bundlesOff']} ends off")


def _reach_walk(edges, start, hops):
    """The nodes joined to start by an edge either way, hops steps on (None: until nothing new) — the arms' own walk."""
    seen, front, d = {start}, [start], 0
    while front and (hops is None or d < hops):
        nxt = []
        for x in front:
            for a, b in edges:
                for y in ((b,) if a == x else ()) + ((a,) if b == x else ()):
                    if y not in seen:
                        seen.add(y)
                        nxt.append(y)
        front, d = nxt, d + 1
    return seen


async def run_cables_and_reach(page, out, failures, res):
    """The cables' width on the page and つながっている物を全部見せる (ticket 2026-10-22-viz-sr-cables-too-thin-and-no-show-neighbours)."""
    await page.click("#sr-fit")
    base = await page.evaluate("() => window.__dbg.srReach()")
    edges = [tuple(e) for e in base["edgesAll"]]
    drawn = {i for i, _ in base["drawn"]}
    # a node whose every-step reach is larger than its one-step reach, else "all" proves nothing
    pick = max(sorted(drawn), key=lambda i: (len(_reach_walk(edges, i, None)) > len(_reach_walk(edges, i, 1)), len(_reach_walk(edges, i, 1))))
    one, every = _reach_walk(edges, pick, 1), _reach_walk(edges, pick, None)
    res["reachPick"] = {"node": pick, "one": sorted(one), "all": sorted(every)}
    check(failures, len(every) > len(one) > 1, f"the room has a node with neighbours and neighbours' neighbours: {res['reachPick']}")
    # 1. the cables (ticket 2026-10-23-viz-sr-cables-thinner-and-end-at-node-edges): thin when not chosen, the strong layer a
    # little thinner than 2.3.20's, each layer measured in drawn pixels alone (srLayerWidth); low over the floors, from
    # one node's footprint edge to the other's, and not drawn over a node (its shapes, its model up close)
    widths = await page.evaluate("() => window.__dbg.srLines().px")
    routes = res["cableRoutes"] = await page.evaluate("() => window.__dbg.srCableRoutes({ side: 0.3, clear: 0.25, cross: 0.06 })")
    plain_fit = res["plainFit"] = await page.evaluate("() => window.__dbg.srLayerWidth('plainLines')")
    # the cables of a node all of whose cables are flat (one rising over a node is drawn over it, as asked), alone, seen
    # from straight above: their pixels stop at the nodes' outlines — pulled back, with the simple shapes, up close with
    # the models (a strip's rounded end against an outline, and the nodes' tops leaning out in perspective, share a few pixels:
    # 7-10% measured; a cable into a node's middle lies on it for the node's radius)
    flat_nodes = routes["flatNodes"]
    check(failures, len(flat_nodes) > 0, f"a node whose cables are all flat (else the next arms prove nothing): {routes}")
    if flat_nodes:
        await page.evaluate("(id) => window.__dbg.srSelect(id)", flat_nodes[0])
        await page.select_option("#sr-lines", "focus")
        over_fit = res["overFit"] = await page.evaluate("() => window.__dbg.srCablesOverNodes(true)")
        await page.evaluate("() => window.__dbg.srDetail({ enter: 0, leave: 0 })")   # the simple shapes, however few are in view
        await page.wait_for_timeout(300)
        over_simple = res["overSimple"] = await page.evaluate("() => window.__dbg.srCablesOverNodes(true)")
        await page.evaluate("() => window.__dbg.srDetail({ enter: 30, leave: 40 })")
        await page.click("#sr-board [data-sr-act='focus']")
        over_models = res["overModels"] = await until(page, "() => { const o = window.__dbg.srCablesOverNodes(true); return o && o.detail ? o : null; }", "up close, the models", timeout=5000)
        await page.screenshot(path=str(out / "cables-models.png"))
        for name, o in (("pulled back", over_fit), ("the simple shapes", over_simple), ("up close, the models", over_models)):
            check(failures, o["cable"] > 30 and o["share"] <= 0.15, f"{name}: a node's flat cables are not drawn over the nodes, seen from above: {o}")
        await page.click("#sr-fit")
    await page.evaluate("(id) => window.__dbg.srSelect(id)", pick)
    await page.select_option("#sr-lines", "focus")
    focus_fit = res["focusFit"] = await page.evaluate("() => window.__dbg.srLayerWidth('focusLines')")
    ink = res["cableInk"] = await page.evaluate("() => window.__dbg.srCableInk()")
    await page.evaluate("() => window.__dbg.srZoom(1.5)")
    focus_back = res["focusBack"] = await page.evaluate("() => ({ ...window.__dbg.srLayerWidth('focusLines'), lod: window.__dbg.sr().lod })")
    await page.screenshot(path=str(out / "cables-focus.png"))
    # up close (これに寄る on the node): the models stand; wider than pulled back, 0.06 units up to 5 px; closer, never past 5
    await page.click("#sr-board [data-sr-act='focus']")
    await page.wait_for_timeout(400)
    ink_near = res["cableInkNear"] = await page.evaluate("() => ({ ...window.__dbg.srCableInk(), lod: window.__dbg.sr().lod, cellPx: window.__dbg.sr().cellPx })")
    focus_near = res["focusNear"] = await page.evaluate("() => window.__dbg.srLayerWidth('focusLines')")
    await page.select_option("#sr-lines", "all")
    plain_near = res["plainNear"] = await page.evaluate("() => window.__dbg.srLayerWidth('plainLines')")
    await page.select_option("#sr-lines", "focus")
    await page.evaluate("() => window.__dbg.srZoom(0.4)")
    focus_closer = res["focusCloser"] = await page.evaluate("() => ({ ...window.__dbg.srLayerWidth('focusLines'), cellPx: window.__dbg.sr().cellPx })")
    # a cable with one end behind the camera (put a third of the way along it, looking at its far end), and one with an end
    # in the camera's own plane (right under it, looking level along the cable: the end's page position divides by 0):
    # cut at the near plane, still drawn, as wide as a cable
    # (2D has no such camera: it looks straight down from far above everything, so no cable is ever behind it or in its plane)
    if not FLAT["on"]:
        near_end, far_end = ink_near["ends"]
        up = lambda v: [v[0], v[1] + 0.5, v[2]]
        at = [near_end[c] + (far_end[c] - near_end[c]) * 0.35 + (0.5 if c == 1 else 0) for c in range(3)]
        ink_cut = res["cableInkCut"] = await page.evaluate("([p, t]) => window.__dbg.srCamInk(p, t)", [at, far_end])
        ink_on = res["cableInkOn"] = await page.evaluate("([p, t]) => window.__dbg.srCamInk(p, t)", [up(near_end), up(far_end)])
    await page.select_option("#sr-lines", "all")
    await page.click("#sr-fit")
    res["cableWidths"] = widths
    check(failures, widths["plain"] <= 1.2 and widths["bundle"] <= 1.2 and widths["plain"] < widths["cross"] <= 1.5 and 2.5 <= widths["focus"] <= 3.5,
          f"not chosen, a cable is about 1 px (across clouds a little wider); chosen, 3: {widths}")
    check(failures, plain_fit["cables"] >= 1 and plain_fit["len"] > 50 and 0.2 < plain_fit["width"] <= 1.5, f"a cable not chosen is drawn thin: {plain_fit}")
    check(failures, focus_fit["len"] > 50 and 2.2 <= focus_fit["width"] <= 3.8, f"the strong cables are drawn about 3 px: {focus_fit}")
    check(failures, focus_back["lod"] == "near" and 2.2 <= focus_back["width"] <= 3.8, f"pulled back, still about 3 px: {focus_back}")
    check(failures, focus_near["len"] > 50 and focus_near["width"] >= focus_fit["width"] * 1.25 and focus_near["width"] <= 5.5,
          f"up close the strong cables are wider than pulled back, up to 5 px: {focus_near} vs {focus_fit}")
    check(failures, focus_closer["len"] > 50 and focus_closer["width"] <= 5.5, f"closer still, no wider than 5 px: {focus_closer}")
    check(failures, plain_near["len"] > 50 and plain_near["width"] <= 2.2, f"up close a cable not chosen stays thin (at most 1.8 px): {plain_near}")
    _routes_ok(failures, "the multi-cloud room", routes)
    check(failures, routes["bundles"] > 0, f"the multi-cloud room has far bundles (else that arm proves nothing): {routes['bundles']}")
    if not FLAT["on"]:
        check(failures, 300 < ink_cut["ink"] < ink_cut["page"] * 0.2 and ink_cut["width"] <= 5.5, f"a cable running behind the camera is still drawn, as wide as a cable: {ink_cut}")
        check(failures, 300 < ink_on["ink"] < ink_on["page"] * 0.2 and (ink_on["width"] or 99) <= 5.5, f"a cable with an end in the camera's plane is still drawn, as wide as a cable: {ink_on}")
    # 2. one step: the node and what an edge joins it to, either way; the rest faint; the camera on all of them
    await page.evaluate("(id) => window.__dbg.srSelect(id)", pick)
    before = (await page.evaluate("() => window.__dbg.srReach()"))["cam"]
    await page.evaluate("() => window.__dbg.srReachHopsSet('1')")
    await page.evaluate("() => window.__dbg.srReachPress()")
    r1 = res["reach1"] = await page.evaluate("() => window.__dbg.srReach()")
    await page.screenshot(path=str(out / "reach-one.png"))
    faint_names = {name for i, name in base["drawn"] if i not in one}
    check(failures, r1["on"] and r1["pressed"] == "true" and set(r1["ids"]) == one, f"one step: the node and every node joined to it, in and out: {r1['ids']} want {sorted(one)}")
    check(failures, set(r1["faint"]) == drawn - one and one <= set(r1["full"]), f"one step: the rest faint, what it holds as drawn: faint {sorted(r1['faint'])}")
    check(failures, r1["focus"] == sum(1 for a, b in edges if pick in (a, b)), f"one step: its cables strong: {r1['focus']}")
    check(failures, r1["cam"] != before and set(r1["inView"]) == one, f"one step: the camera moved until all of it is in view: {r1['inView']}")
    tagged = {t.split(" · ")[0].split(" ×")[0] for t in r1["labels"]}   # up close a tag is "name · service · spec"
    check(failures, not (tagged & (faint_names - {n for i, n in base["drawn"] if i in one})), f"one step: no tag on a faint node: {r1['labels']}")
    check(failures, r1["plainOpacity"] <= 0.06, f"one step: the other cables fainter still: {r1['plainOpacity']}")
    # 3. every step on
    await page.evaluate("() => window.__dbg.srReachHopsSet('all')")
    ra = res["reachAll"] = await page.evaluate("() => window.__dbg.srReach()")
    await page.screenshot(path=str(out / "reach-all.png"))
    check(failures, ra["on"] and ra["hops"] == "all" and set(ra["ids"]) == every and set(ra["faint"]) == drawn - every and set(ra["inView"]) == every,
          f"every step: all it reaches, the rest faint, all in view: {sorted(ra['ids'])} want {sorted(every)}")
    # every edge between the nodes it reached is strong, a loop's closing edge too (one between two nodes already reached)
    inner = sum(1 for a, b in edges if a in every and b in every)
    check(failures, inner > len(every) - 1, f"the room's reach has a loop (else the next arm proves nothing): {inner} edges, {len(every)} nodes")
    check(failures, ra["focus"] == inner, f"every step: every edge among what it reached drawn strong: {ra['focus']} want {inner}")
    # 4. Esc: as it was, the camera too; the room stays
    await page.keyboard.press("Escape")
    re_ = res["reachEsc"] = await page.evaluate("() => ({ ...window.__dbg.srReach(), open: window.__dbg.sr().open })")
    check(failures, re_["open"] and not re_["on"] and re_["faint"] == [] and re_["pressed"] == "false" and re_["plainOpacity"] > 0.06
          and all(abs(a - b) < 1e-3 for a, b in zip(re_["cam"], before)), f"Esc: nothing faint, the camera where it was, the room open: {re_}")
    # 5. pressed again does the same; another node chosen ends it where the camera is
    await page.evaluate("() => window.__dbg.srReachPress()")
    await page.evaluate("() => window.__dbg.srReachPress()")
    rt = res["reachToggle"] = await page.evaluate("() => window.__dbg.srReach()")
    check(failures, not rt["on"] and rt["faint"] == [] and all(abs(a - b) < 1e-3 for a, b in zip(rt["cam"], before)), f"pressed again: as it was: {rt}")
    await page.evaluate("() => window.__dbg.srReachPress()")
    shown_cam = (await page.evaluate("() => window.__dbg.srReach()"))["cam"]
    other = next(i for i in sorted(drawn) if i != pick)
    await page.evaluate("(id) => window.__dbg.srSelect(id)", other)
    ro = res["reachOther"] = await page.evaluate("() => window.__dbg.srReach()")
    check(failures, not ro["on"] and ro["faint"] == [] and ro["cam"] == shown_cam, f"another node chosen: nothing faint, the camera stays: {ro}")
    await page.evaluate("() => window.__dbg.srSelect(null)")
    await page.click("#sr-fit")


async def run_server_room(pw, out, failures, flat=False):
    from run import free_port
    FLAT["on"] = flat
    out = pathlib.Path(out) / ("server-room-2d" if flat else "server-room")
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    ex = _with_loop(_examples(jt))
    # a spec value with markup in it (the schema takes it: only a page's esc keeps it text — the independent check's SE1)
    for n in ex["aws-three-tier/docs/infra/main.json"]["nodes"]:
        if n["id"] == "db-prod":
            n["spec"] = n["spec"] + [{"key": "note", "value": MARKUP}]
    work = home / "work"
    rooms = {
        "three": _write(work, ex, "aws-three-tier", "sr-three"),
        "multi": _write(work, ex, "multi-provider", "sr-multi"),
        "large": _write(work, ex, "large-multi-provider", "sr-large"),
        "icons": _write(work, ex, "compose-and-cloud", "sr-icons"),
    }
    # a room with no infra folder: no door (E13, the independent verification); six rooms stay one floor
    (work / "sr-none" / ".git").mkdir(parents=True, exist_ok=True)
    rooms["none"] = work / "sr-none"
    # the icons room: a category icon too for the node the service icon names, so the stronger key must win (E5)
    icfg_path = rooms["icons"] / "jui.config.json"
    icfg = json.loads(icfg_path.read_text())
    folder = rooms["icons"] / icfg["infra"]["dir"]
    svc_node = None
    for f in sorted(folder.glob("*.json")):
        for n in json.loads(f.read_text()).get("nodes", []):
            if n.get("service") == "run" and svc_node is None:
                svc_node = n
    svc_key = next(k for k in icfg["infra"]["icons"] if k.startswith("service:"))
    icfg["infra"]["icons"][f"category:{svc_node['category']}"] = icfg["infra"]["icons"][svc_key]
    icfg_path.write_text(json.dumps(icfg, ensure_ascii=False))
    # one room for the three that cannot be read (seven rooms would turn the floor into the building): its prod.json is
    # written before each press
    secret_doc = ex["invalid/single/secret-connection-string.json"]
    BAD = {"broken": '{\n  "version": 0,\n  "nodes": [ {"id": "a" \n',
           "schema": json.dumps({"version": 0, "nodes": [{"id": "a", "category": "no.such.category"}]}),
           "secret": secret_doc if isinstance(secret_doc, str) else json.dumps(secret_doc),
           # a spec value with a secret's shape (§4): the file is refused as any other, the value shown nowhere
           "specSecret": json.dumps({"version": 0, "nodes": [{"id": "db", "category": "database.relational", "spec": [
               {"key": "instance_class", "value": "db.r6g.large"}, {"key": "endpoint", "value": SPEC_SECRET}]}]})}
    bad = work / "sr-bad"
    (bad / "docs" / "infra").mkdir(parents=True, exist_ok=True)
    (bad / ".git").mkdir(exist_ok=True)
    (bad / "docs" / "infra" / "prod.json").write_text(BAD["broken"], encoding="utf-8")
    rooms["bad"] = bad
    secret_values = [v for v in json.dumps(ex["invalid/single/secret-connection-string.json"]).split('"') if "://" in v or "@" in v]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": str(cwd), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        sids = {}
        for i, (name, root) in enumerate(rooms.items()):
            sids[name] = f"5e000000-0000-4000-8000-{i:012d}"
            hook(sids[name], root, hook_event_name="SessionStart", source="startup")
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "server-room-2d" if flat else "server-room", **DESKTOP)
        if flat:
            await page.add_init_script(SR_FLAT_INIT)
        asked: list = []
        page.on("request", lambda r: asked.append(r.url) if "/api/infra-docs" in r.url else None)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, f"() => window.__dbg.robots.length >= {len(rooms)} && window.__dbg.robots.every((R) => !R.path.length)", "every room's robot seated", timeout=60000)
        pid = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.sessionId, R.def.room]))")
        pid = {name: pid[sid] for name, sid in sids.items()}

        async def up_close(name):
            if await page.evaluate("() => !!window.__dbg.solo()"):
                await page.click("#room-back")
                await until(page, "() => window.__dbg.solo() === null", "back to the floor")
            await page.click(f".tag.room[data-set-project='{pid[name]}']")
            await until(page, f"() => window.__dbg.solo() === '{pid[name]}'", f"{name} up close")
            await until(page, "() => window.__dbg.sr().built && window.__dbg.sr().door", f"{name}'s server room door", timeout=20000)
            await until(page, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled up close", timeout=30000)

        async def press_door():
            at = (await page.evaluate(SR))["door"]
            await page.mouse.click(at[0], at[1])

        # 1. up close: the door, and nothing read
        await up_close("three")
        res["door"] = await page.evaluate(SR)
        check(failures, res["door"]["built"] and not asked, f"a room up close has its door, and nothing is read before it is pressed: {len(asked)} reads")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await until(page, "() => window.__dbg.sr().built", f"the door, {scheme}")
            await page.screenshot(path=str(out / f"door-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await until(page, "() => window.__dbg.sr().built", "the door again")

        # 2. pressed, the reply held: the * grow, the bubble reads; then the server room
        held = {"n": 0}

        async def hold(route):
            held["n"] += 1
            await page.wait_for_timeout(2500)
            await route.continue_()
        await page.route("**/api/infra-docs", hold)
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'loading'", "reading")
        stars = []
        for _ in range(6):
            s = await page.evaluate(SR)
            stars.append(s["stars"])
            await until(page, f"(n) => window.__dbg.sr().stars !== n || window.__dbg.sr().phase !== 'loading'", "the next *", arg=s["stars"], timeout=3000)
        res["stars"] = stars
        res["readingBubble"] = (await page.evaluate(SR))["bubble"]
        await page.screenshot(path=str(out / "keypad-light.png"))
        check(failures, len(set(stars)) >= 3, f"the keypad's * grow while it reads: {stars}")
        check(failures, (res["readingBubble"] or {}).get("text") == T("sr.loading"), f"the bubble while it reads: {res['readingBubble']}")
        await until(page, "() => window.__dbg.sr().open", "the server room", timeout=15000)
        await page.unroute("**/api/infra-docs", hold)
        s = res["opened"] = await page.evaluate(SR)
        check(failures, s["bubble"] is None and (s["shown"] or {}).get("nodes", 0) > 0 and s["stats"]["edges"] > 0, f"open: the model drawn, the bubble gone: {s['shown']}")
        check(failures, s["lod"] == "near" and s["layers"] == {"near": True, "far": False}, f"open up close: the floors and shapes, not the far boxes over them: {s['lod']} {s['layers']}")
        if FLAT["on"]:   # a small room at fit: its cells large, every cable shown
            check(failures, s["lines"]["plain"] and not s["lines"]["sparse"], f"2D, a small room opened: every cable: {s['lines']}")
        # one cloud, one colour (ticket 2026-10-22-viz-server-room-palette-and-light-flow §1): the legend's chip of each cloud is
        # the colour its nodes are drawn in (the cost's key is held to the same below)
        colors = res["colors"] = await page.evaluate("() => window.__dbg.srColors()")
        node_of = {}
        for _id, (prov, hexc) in colors["nodes"].items():
            if prov:
                node_of.setdefault(prov, set()).add(hexc)
        chip_hex = {prov: "#%02x%02x%02x" % tuple(round(x) for x in _rgb(c)) for prov, c in colors["chips"].items()}
        check(failures, node_of and all(len(v) == 1 for v in node_of.values()) and all(chip_hex.get(p_) in v for p_, v in node_of.items()),
              f"each cloud's nodes are one colour and its legend chip is that colour: nodes {node_of} chips {chip_hex}")
        # up close in a small room (ticket 2026-10-22-viz-server-room-palette-and-light-flow §3): every node in view stands as
        # its kind's model, the shapes by service under them still pickable but not drawn
        await page.evaluate("() => window.__dbg.srZoom(0.8)")
        if FLAT["on"]:   # 2D: no models — every node in view is its kind's flat tile (the kinds the models have) in its colour
            md = await until(page, "() => { const d = window.__dbg.srDetail(); return d && d.inViewIds.length >= 5 ? d : null; }", "the small room up close (2D)", timeout=10000)
            mcol = await page.evaluate("() => window.__dbg.srColors()")
            res["tiles"] = {"inView": md["inViewIds"], "tiles": {i: md["simple"].get(i) for i in md["inViewIds"]}, "kinds": md["kinds"], "models": md["models"],
                            "picks": sorted(set(md["picks"]))}
            check(failures, all(md["simple"].get(i) == f"flat:{k}" for i, k in md["kinds"].items()) and len(set(md["kinds"].values())) >= 5
                  and md["models"] == {} and all(x.startswith("flat:") for x in res["tiles"]["picks"])
                  and all(mcol["nodes"][i][1] == colors["nodes"][i][1] for i in md["inViewIds"]),
                  f"2D up close: every node in view is its kind's flat tile in its cloud's colour, no model: {res['tiles']}")
            # a node's tag sits above its own tile on the page, never on it: its bottom above the tile's top edge
            # (the tags are placed each tenth of a second: waited for, up to 5 s, then read as they are)
            try:
                tags = await until(page, "() => { const t = window.__dbg.srTagsOnTiles(); return t && t.tags >= 3 && !t.on.length ? t : null; }", "2D: the tags above their tiles", timeout=5000)
            except Exception:
                tags = await page.evaluate("() => window.__dbg.srTagsOnTiles()")
            res["tagsOffTiles"] = tags
            check(failures, tags and tags["tags"] >= 3 and not tags["on"], f"2D: each node's tag above its tile, not on it: {tags}")
            md = None
            # 2D or 3D is remembered per project (the requester's 「2D」 beside 3D and コスト): 3D pressed, the room closed and
            # opened again opens in 3D, the choice kept under that project; 2D pressed, 2D again
            proj = await page.evaluate("() => window.__dbg.sr().project")
            pref = "(p) => { try { return JSON.parse(localStorage.getItem('agent-view:srView') || '{}')[p] || null; } catch (e) { return 'err'; } }"
            await page.click("#sr-mode-3d")
            await until(page, "() => window.__dbg.sr().built !== undefined && window.__dbg.srCam() && window.__dbg.srCam().flat === false", "3D pressed")
            mem = {"after3d": await page.evaluate(pref, proj)}
            await page.keyboard.press("Escape")
            await until(page, "() => !window.__dbg.sr().open", "closed")
            await page.evaluate("(p) => window.__dbg.srEnter(p)", proj)
            await until(page, "() => window.__dbg.sr().open && window.__dbg.srCam()", "opened again", timeout=15000)
            mem["reopened"] = (await page.evaluate("() => window.__dbg.srCam()"))["flat"]
            mem["pressed"] = await page.evaluate("() => ['sr-mode-3d', 'sr-mode-2d', 'sr-mode-cost'].map((id) => document.getElementById(id).getAttribute('aria-pressed'))")
            await page.click("#sr-mode-2d")
            await until(page, "() => window.__dbg.srCam() && window.__dbg.srCam().flat === true", "2D pressed again")
            mem["after2d"] = await page.evaluate(pref, proj)
            res["viewPref"] = mem
            check(failures, mem == {"after3d": "3d", "reopened": False, "pressed": ["true", "false", "false"], "after2d": "2d"},
                  f"2D / 3D is remembered per project: reopened as last chosen, one button pressed: {mem}")
        else:
          md = await until(page, "() => { const d = window.__dbg.srDetail(); return d && d.detail && d.inViewIds.length && d.inViewIds.every((i) => d.models[i]) ? d : null; }",
                         "the small room up close: a model per node in view", timeout=10000,
                         why="() => { const d = window.__dbg.srDetail(); return d && [d.detail, d.inViewIds, d.models]; }")
          mcol = await page.evaluate("() => window.__dbg.srColors()")
          res["models"] = {"inView": md["inViewIds"], "models": md["models"], "kinds": md["kinds"], "drawn": md["detailDrawn"], "picks": sorted(set(md["picks"])),
                           "colors": {i: (mcol["models"].get(i), mcol["nodes"][i][1]) for i in md["inViewIds"]}}
          check(failures, {i: md["models"][i] for i in md["inViewIds"]} == md["kinds"] and len(set(md["kinds"].values())) >= 5
                and not any(md["detailDrawn"]) and md["picks"] and len(md["models"]) <= md["modelMax"]
                and all(a_ == b_ for a_, b_ in res["models"]["colors"].values()),
                f"a small room up close: every node in view is its kind's model in its node's colour, the shapes under them pick but are not drawn: {res['models']}")
        await page.click("#sr-fit")

        # 2c. the cost simulator (plan L-C): 3D / コスト, the scenarios, the month, a day played, its breakdown and the red
        COST = "() => window.__dbg.srCost()"
        await page.click("#sr-mode-cost")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.month && c.month.bars === c.month.days; }", "the month drawn", timeout=20000)
        c = res["costMonth"] = await page.evaluate(COST)
        chips = dict(c["month"]["chips"])
        # the month by cloud: each cloud's key in the cost is the colour its nodes are drawn in (one cloud, one colour)
        keys = await page.evaluate("() => [...document.querySelectorAll('#sr-cost .src-key')].filter((k) => k.querySelector('i')).map((k) => [k.textContent.trim(), getComputedStyle(k.querySelector('i')).backgroundColor])")
        key_hex = {label: "#%02x%02x%02x" % tuple(round(x) for x in _rgb(bg)) for label, bg in keys}
        res["costKeyColors"] = {p_: (key_hex.get(p_), sorted(v)) for p_, v in node_of.items()}
        check(failures, c["month"]["by"] == "provider" and any(p_ in key_hex for p_ in node_of)
              and all(key_hex[p_] in v for p_, v in node_of.items() if p_ in key_hex),
              f"the cost by cloud: each cloud's key is its nodes' colour: {res['costKeyColors']}")
        check(failures, c["paused"] and not c["raf"] and c["month"]["days"] == 30 and c["month"]["total"].startswith("$"),
              f"コスト: the 3D paused, the month's 30 days and its sum: {c}")
        # the box is the 3D's (ticket 2026-10-21-jui-viz-cost-view-box-zoom-takes-the-clicks): 範囲で寄る off, an Option + drag
        # over the month draws nothing, and a day pressed after it still opens (checked with the sale's day below)
        bz = await page.evaluate("() => ({ disabled: document.getElementById('sr-boxzoom').disabled, ...window.__dbg.srBox() })")
        sbox = await page.evaluate("() => { const r = document.getElementById('sr-cost').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
        await page.keyboard.down("Alt")
        await page.mouse.move(sbox[0] - 60, sbox[1] - 40)
        await page.mouse.down()
        await page.mouse.move(sbox[0] + 60, sbox[1] + 40, steps=4)
        mid = await page.evaluate("() => window.__dbg.srBox()")
        await page.mouse.up()
        await page.keyboard.up("Alt")
        res["costBox"] = {"before": bz, "during": mid, "after": await page.evaluate("() => window.__dbg.srBox()")}
        if (await page.evaluate(COST))["day"]:   # the release over a bar is that bar's press: back to the month
            await page.click("#sr-cost [data-src-act='month']")
        check(failures, bz["disabled"] and not bz["armed"] and not mid["drawing"] and not mid["shown"] and not res["costBox"]["after"]["armed"],
              f"コスト: 範囲で寄る off and an Option + drag draws no box: {res['costBox']}")
        check(failures, chips.get("noRule") == 1 and chips.get("noPrice") == 2 and "loadUndefined" in chips, f"what is not priced is counted on the page: {chips}")
        await page.select_option("#sr-scn", "sale")
        await until(page, "(u) => { const c = window.__dbg.srCost(); return c.scenario === 'sale' && c.month && c.month.usd !== u; }",
                    "another scenario's month", arg=c["month"]["usd"], timeout=20000)
        sale = res["costSale"] = await page.evaluate(COST)
        ord_w = chips.get("warnings")   # the ordinary month's own
        check(failures, sale["month"]["overDays"] >= 1, f"the sale's day over capacity is marked: {sale['month']}")
        check(failures, sale["month"]["free"] == "", f"no free amount used: no note on how it is taken: {sale['month']['free']}")
        # the engine's cost.free_per_scenario (infra cost stage B; its shape) put in the server's reply: 計算の注意 counts
        # it and the note under the total says the free amount is taken per environment
        free_w = {"fn": "simulate", "code": "cost.free_per_scenario", "message": "free amounts are taken once per scenario",
                  "rows": ["aws lambda compute (us-east-1)", "aws lambda requests (us-east-1)"]}

        async def with_free(route):
            got = await route.fetch()
            body = await got.json()
            if body.get("ok") and body.get("month"):
                body["month"]["warnings"] = body["month"]["warnings"] + [free_w]
                body["month"]["warningCount"] += 1
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        await page.route("**/api/infra-cost", with_free)
        await page.select_option("#sr-scn", "ordinary")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.scenario === 'ordinary' && c.month && c.month.free !== ''; }",
                    "the free amount's note", timeout=20000)
        fm = res["costFree"] = (await page.evaluate(COST))["month"]
        fchips = dict(fm["chips"])
        check(failures, T("cost.free") in fm["free"] and T("cost.free.rows", n=2).strip() in fm["free"] and fchips.get("warnings") == ord_w + 1,
              f"cost.free_per_scenario: its note under the total and one more in 計算の注意: {fm['free']} {fchips} (was {ord_w})")
        await page.unroute("**/api/infra-cost", with_free)
        await page.select_option("#sr-scn", "sale")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.scenario === 'sale' && c.month && c.month.free === ''; }",
                    "the sale again, no note", timeout=20000)
        await page.click("#sr-cost [data-src-date='2026-11-27']")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.day && c.day.date === '2026-11-27' && c.day.rows > 0; }", "the day", timeout=20000)
        await page.evaluate("() => { const r = document.getElementById('src-hour'); r.value = '1'; r.dispatchEvent(new Event('input', { bubbles: true })); }")
        d = res["costDay"] = (await page.evaluate(COST))["day"]
        await doc_words_shot(page, "sr-cost-day", out, failures)   # the meters' names (lang_checks.py)
        check(failures, d["hour"] == 1 and d["clock"] == "01:00" and d["red"] and T("cost.load.served").strip() in d["red"][0],
              f"over capacity in red as served / demand: {d['red']}")
        check(failures, any(T("srv.cost.q.requests") in x and "/sec" in x and "$" in x for x in d["segments"]), f"a meter says its rate and charge: {d['segments'][:6]}")
        await page.evaluate("() => window.__dbg.srCostPlayMs(120)")
        await page.click("#sr-cost [data-src-act='play']")
        await until(page, "() => window.__dbg.srCost().day.hour >= 5", "played on", timeout=10000)
        played = (await page.evaluate(COST))["day"]
        check(failures, played["hour"] >= 5, f"再生 moves the hour on: {played['hour']}")
        # it stops at 23:00 on its own, the button says 再生 again, and the hour stays 23 (it never wraps to 0)
        await until(page, "() => !window.__dbg.srCost().day.playing", "played to the end", timeout=15000)
        end = (await page.evaluate(COST))["day"]
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 600", "a while after the end", arg=t)
        still = (await page.evaluate(COST))["day"]
        play_btn = await page.evaluate("() => !!document.querySelector(\"#sr-cost [data-src-act='play']\")")
        res["costPlayEnd"] = {"end": end["hour"], "later": still["hour"], "clock": still["clock"], "playButton": play_btn}
        check(failures, end["hour"] == 23 and still["hour"] == 23 and still["clock"] == "23:00" and play_btn and not still["playing"],
              f"再生 stops at 23:00 and the button says 再生 again: {res['costPlayEnd']}")
        await page.click("#sr-cost [data-src-seg]")
        await until(page, "() => window.__dbg.srCost().day.price !== ''", "the price's trace")
        price = (await page.evaluate(COST))["day"]["price"]
        check(failures, T("cost.pick.from") in price and (T("cost.layer.bundled") in price or T("cost.layer.user") in price), f"a meter pressed shows its price's trace: {price[:200]}")
        await page.screenshot(path=str(out / "cost-day-light.png"))
        # the account (cd 10-21): offered only once each environment has a load definition; one total, by environment,
        # and then the default (the requester 10-21: 「合計で」) — この環境だけ is the other choice
        await page.click("#sr-cost [data-src-act='month']")
        check(failures, not (await page.evaluate(COST))["month"]["acctSwitch"], "no account switch while staging has no load definition")
        load_dir = rooms["three"] / "docs/infra/load"
        stg = json.loads((load_dir / "ordinary.json").read_text(encoding="utf-8"))
        stg.update(id="staging", label="ステージングの月", environment="staging")
        stg["loads"] = [dict(r, node=r["node"].replace("-prod", "-stg")) for r in stg["loads"] if "node" in r]
        (load_dir / "staging.json").write_text(json.dumps(stg, ensure_ascii=False), encoding="utf-8")
        await page.select_option("#sr-scn", "ordinary")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.scenario === 'ordinary' && c.month && c.month.acctSwitch; }",
                    "the account switch", timeout=20000)
        a = res["costAccount"] = {**(await page.evaluate(COST)), "pressed": await page.evaluate(
            "() => [...document.querySelectorAll('#sr-cost [data-src-act^=acct]')].map((b) => [b.dataset.srcAct, b.getAttribute('aria-pressed')])")}
        m = a["month"]
        check(failures, a["account"] and a["asked"] is None and m["by"] == "environment" and m["keys"] == ["production", "staging"]
              and a["pressed"] == [["acct-on", "true"], ["acct-off", "false"]]
              and "ふだんの月" in m["acct"] and "ステージングの月" in m["acct"] and m["bars"] == m["days"] == 30 and m["usd"] > c["month"]["usd"],
              f"アカウントの合計 by default, nothing pressed: both environments stacked and named, more than production alone: {a}")
        await page.click("#sr-cost [data-src-date='2026-11-02']")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.day && c.day.date === '2026-11-02'; }", "the account's day", timeout=20000)
        check(failures, T_pattern("cost.account.day").search((await page.evaluate(COST))["day"]["acct"]), "the account's day says it is priced within the account")
        await page.click("#sr-cost [data-src-act='month']")
        await page.click("#sr-cost [data-src-act='acct-off']")
        await until(page, "() => { const c = window.__dbg.srCost(); return !c.account && c.month && c.month.by === 'provider'; }",
                    "この環境だけ", timeout=20000)
        one = await page.evaluate(COST)
        check(failures, one["month"]["acct"] == "" and one["asked"] is False and one["month"]["usd"] == c["month"]["usd"],
              f"この環境だけ: production's own month again, no account's lines: {one['month']['usd']} {c['month']['usd']}")
        await page.click("#sr-cost [data-src-act='acct-on']")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.account && c.month && c.month.by === 'environment'; }",
                    "the account again", timeout=20000)
        (load_dir / "staging.json").unlink()
        await page.click("#sr-mode-3d")
        await until(page, "() => { const c = window.__dbg.srCost(); return !c.paused && c.raf; }", "the 3D again")
        check(failures, not await page.evaluate("() => document.getElementById('sr-boxzoom').disabled"), "3D: 範囲で寄る on again")
        # 範囲で寄る pressed, then コスト and back: nothing is left armed, so the next plain drag turns the 3D, no box
        await page.click("#sr-boxzoom")
        armed_before = (await page.evaluate("() => window.__dbg.srBox()"))["armed"]
        await page.click("#sr-mode-cost")
        await until(page, "() => window.__dbg.srCost().mode === 'cost'", "コスト after 範囲で寄る")
        await page.click("#sr-mode-3d")
        await until(page, "() => { const c = window.__dbg.srCost(); return c.mode === '3d' && !c.paused; }", "the 3D after コスト")
        cvr = await page.evaluate("() => { const r = document.getElementById('sr-canvas').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
        await page.mouse.move(cvr[0] - 50, cvr[1] - 30)
        await page.mouse.down()
        await page.mouse.move(cvr[0] + 50, cvr[1] + 30, steps=4)
        mid = await page.evaluate("() => ({ ...window.__dbg.srBox(), pressed: document.getElementById('sr-boxzoom').getAttribute('aria-pressed') })")
        await page.mouse.up()
        res["costBoxArmed"] = {"armedBefore": armed_before, "afterCost": mid}
        check(failures, armed_before and not mid["armed"] and mid["pressed"] == "false" and not mid["drawing"] and not mid["shown"],
              f"範囲で寄る, then コスト and 3D: nothing left armed, a plain drag draws no box: {res['costBoxArmed']}")
        # the room closed while コスト is shown, and opened again: 範囲で寄る can be pressed
        await page.click("#sr-mode-cost")
        await until(page, "() => window.__dbg.srCost().mode === 'cost'", "コスト before closing")
        await page.click("#sr-back")
        await until(page, "() => !window.__dbg.sr().open", "the room closed from コスト")
        await page.evaluate(f"() => window.__dbg.srEnter('{pid['three']}')")
        await until(page, "() => window.__dbg.sr().open", "the room open again", timeout=20000)
        reopened = await page.evaluate("() => ({ disabled: document.getElementById('sr-boxzoom').disabled, mode: window.__dbg.srCost().mode, paused: window.__dbg.srCost().paused })")
        res["costReopened"] = reopened
        check(failures, reopened == {"disabled": False, "mode": "3d", "paused": False},
              f"closed from コスト and opened again: the 3D, 範囲で寄る pressable: {reopened}")
        # the theme changing while it is open (D3) follows; dark is a dark ground with floors and labels that read (2.3.9, item 2)
        res["theme"] = {}
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await until(page, "(d) => window.__dbg.srTheme() && window.__dbg.srTheme().dark === d", f"the 3D in {scheme}", arg=scheme == "dark", timeout=10000)
            await page.evaluate("() => new Promise((r) => setTimeout(r, 300))")   # the labels given out again
            res["theme"][scheme] = await page.evaluate("() => window.__dbg.srTheme()")
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await until(page, "() => window.__dbg.srTheme().dark === false", "the 3D back in light", timeout=10000)
        th = res["theme"]["dark"]
        bg_l = _lum(th["bg"])
        low = [(f, round(_contrast(f, th["bg"]), 2)) for f in th["floors"] if _contrast(f, th["bg"]) < 3]
        ink, ground = th["label"] or [None, None]
        label_cr = round(_contrast(_rgb(ink), _over(_rgba(ground), th["bg"])), 2) if ink else None
        res["theme"]["measured"] = {"bgLum": round(bg_l, 4), "floorsUnder3": low, "label": label_cr}
        check(failures, res["theme"]["light"]["dark"] is False and th["dark"] is True and bg_l <= 0.03,
              f"opened in light, turned dark while open: the 3D's ground is dark: {res['theme']['measured']} {th['bg']}")
        check(failures, not low and label_cr is not None and label_cr >= 4.5, f"dark: every floor 3:1 on the ground, labels 4.5:1: {res['theme']['measured']}")

        # the environments switch, the folded ones come and go
        envs = await page.evaluate("() => [...document.querySelectorAll('#sr-env option')].map((o) => o.value)")
        res["envs"] = envs
        if len(envs) >= 2:
            before = (await page.evaluate(SR))["shown"]["nodes"]
            await page.select_option("#sr-env", envs[1])
            await until(page, f"(e) => window.__dbg.sr().env === e", "the other environment", arg=envs[1])
            res["envSwitch"] = [before, (await page.evaluate(SR))["shown"]["nodes"]]
        check(failures, len(envs) >= 2 and "envSwitch" in res, f"the environments are a switch: {envs}")
        if len(envs) >= 2:   # E1: never two environments at once — every node drawn is in the one chosen (or in all)
            drawn = await page.evaluate("() => window.__dbg.srNodeEnvs()")
            stray = [nid for nid, e in drawn if e and envs[1] not in e]
            res["envOnly"] = {"env": envs[1], "drawn": len(drawn), "stray": stray}
            check(failures, drawn and not stray, f"only the chosen environment is drawn: {res['envOnly']}")
        folded = (await page.evaluate(SR))["shown"]
        await page.check("#sr-fold")
        await until(page, f"(n) => window.__dbg.sr().shown.nodes > n", "the folded ones shown", arg=folded["nodes"])
        res["fold"] = [folded["nodes"], (await page.evaluate(SR))["shown"]["nodes"], folded["folded"]]
        check(failures, folded["folded"] > 0 and res["fold"][1] == folded["nodes"] + folded["folded"] or res["fold"][1] > folded["nodes"],
              f"the folded ones are out until asked for: {res['fold']}")
        # the zoom buttons, a group closed into one box and opened again, moving in on it; the room's own 3D not drawn meanwhile
        px0 = (await page.evaluate(SR))["cellPx"]
        await page.click("#sr-zin")
        await until(page, "(p) => window.__dbg.sr().cellPx > p * 1.2", "+ moves in", arg=px0)
        await page.click("#sr-zout")
        await page.click("#sr-zout")
        await until(page, "(p) => window.__dbg.sr().cellPx < p", "- moves out", arg=px0)
        groups = await page.evaluate("() => window.__dbg.srGroups()")
        g = max(groups, key=lambda x: (x["nodes"] if x["nodes"] >= 2 else -1))
        before = (await page.evaluate(SR))["shown"]
        check(failures, await page.evaluate("(id) => window.__dbg.srSelectGroup(id)", g["id"]), f"a group picked has its close button: {g}")
        await page.click("#sr-board [data-sr-act='toggle']")
        await until(page, "() => window.__dbg.sr().shown.closed === 1", "the group closed")
        closed = (await page.evaluate(SR))["shown"]
        px1 = (await page.evaluate(SR))["cellPx"]
        await page.click("#sr-board [data-sr-act='focus']")
        await until(page, "(p) => window.__dbg.sr().cellPx > p", "moved in on the group", arg=px1)
        m0 = await page.evaluate("() => window.__dbg.mainFrames()")
        await page.evaluate("() => new Promise((r) => { let n = 0; const f = () => (++n < 20 ? requestAnimationFrame(f) : r()); requestAnimationFrame(f); })")
        m1 = await page.evaluate("() => window.__dbg.mainFrames()")
        await page.click("#sr-board [data-sr-act='toggle']")
        await until(page, "() => window.__dbg.sr().shown.closed === 0", "the group opened")
        reopened = (await page.evaluate(SR))["shown"]
        res["group"] = {"group": g, "before": before, "closed": closed, "reopened": reopened, "zoom": [px0, px1], "mainFrames": [m0, m1]}
        check(failures, closed["nodes"] == before["nodes"] - g["nodes"] and closed["inClosed"] == g["nodes"] and reopened["nodes"] == before["nodes"],
              f"a closed group is one box, opened it is all there again: {res['group']}")
        check(failures, m0 == m1, f"the room's 3D is not drawn under the server room: {m0} → {m1}")
        # a node's spec (the ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §4) on the board, and up close
        # (§5) its tag: name · service · its main spec — db-prod is in production
        await page.select_option("#sr-env", envs[0])
        await until(page, "(e) => window.__dbg.sr().env === e", "production again", arg=envs[0])
        await page.evaluate("() => window.__dbg.srSelect('db-prod')")
        rows = await page.evaluate("() => [...document.querySelectorAll('#sr-board [data-sr-spec] tr')].map((tr) => [tr.querySelector('th').textContent, tr.querySelector('td').textContent, tr.querySelector('td').children.length])")
        ran = await page.evaluate("() => !!window.__srMarkup")
        await page.click("#sr-board [data-sr-act='focus']")
        dt = await until(page, "() => { const d = window.__dbg.srDetail(); return d && d.detail && d.tags.some((t) => t.startsWith('db-prod · ')) ? d : null; }",
                         "db-prod up close: its tag in detail", timeout=10000, why="() => window.__dbg.srDetail()")
        res["spec"] = {"rows": rows, "tag": [t for t in dt["tags"] if t.startswith("db-prod")], "inView": dt["inView"],
                       "sizeTag": await page.evaluate("() => window.__dbg.srTagOf('api-prod')")}
        check(failures, res["spec"]["sizeTag"] == "api-prod · ECS Fargate · memory 2048 ×3",
              f"a size (no instance type) says which it is, and the count stays: {res['spec']['sizeTag']}")
        check(failures, rows == [[f"{T('sr.spec.instance')} instance_class", "db.r6g.large", 0], [f"{T('sr.spec.storage_gb')} storage_gb", "200", 0], [f"{T('sr.spec.multi_az')} multi_az", "true", 0],
                                 ["note", MARKUP, 0]] and not ran,
              f"the chosen node's spec on the board, the known keys in words, a value with markup shown as its text (no element, nothing run): {rows} {ran}")
        check(failures, res["spec"]["tag"] == ["db-prod · RDS MySQL · db.r6g.large"], f"up close a tag says the service and the main spec: {res['spec']}")
        await page.screenshot(path=str(out / "spec-light.png"))
        await page.keyboard.press("Escape")
        await until(page, "() => !window.__dbg.sr().open && window.__dbg.sr().phase === 'idle'", "back to the room")
        check(failures, (await page.evaluate("() => window.__dbg.solo()")) == pid["three"], "Esc goes back to the room")
        check(failures, not await page.evaluate("() => window.__dbg.srAlive()"), "back in the room the server room's 3D is gone (its loop and GPU objects freed)")   # E9

        # 3. Esc while it reads: the late reply opens nothing
        import asyncio
        late = asyncio.Event()

        async def hold_late(route):
            await page.wait_for_timeout(2000)   # the reply held back (the network's stand-in), not a wait on state
            await route.continue_()
            late.set()
        await page.route("**/api/infra-docs", hold_late)
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'loading' && !!window.__dbg.sr().bubble", "reading again")
        await page.keyboard.press("Escape")
        await until(page, "() => window.__dbg.sr().phase === 'idle' && !window.__dbg.sr().bubble", "the press dropped")
        await asyncio.wait_for(late.wait(), timeout=10)
        await page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        res["afterEsc"] = await page.evaluate(SR)
        check(failures, late.is_set() and not res["afterEsc"]["open"] and res["afterEsc"]["phase"] == "idle", f"a reply after Esc opens nothing: {res['afterEsc']['phase']}, open {res['afterEsc']['open']}")
        await page.unroute("**/api/infra-docs", hold_late)

        # 3b. a read that comes back at once (answered here without waiting): only a flash of 解錠, not the whole 0.7 s (E3)
        model_box = {}

        async def instant(route):
            seq = json.loads(route.request.post_data or "{}").get("seq")
            if "model" not in model_box:
                got = await route.fetch()
                model_box["model"] = await got.json()
            await route.fulfill(status=200, content_type="application/json", body=json.dumps({**model_box["model"], "seq": seq}))
        await page.route("**/api/infra-docs", instant)
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "the server room (warm-up)", timeout=15000)
        await page.keyboard.press("Escape")
        await until(page, "() => !window.__dbg.sr().open", "back (warm-up)")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "the server room (instant reply)", timeout=15000)
        res["flash"] = await page.evaluate("() => window.__dbg.srTiming()")
        f = res["flash"]
        check(failures, f["took"] is not None and f["took"] < f["fastMs"] and f["waitMs"] <= 150, f"an instant read only flashes 解錠: {f}")
        await page.keyboard.press("Escape")
        await until(page, "() => !window.__dbg.sr().open", "back (instant reply)")
        await page.unroute("**/api/infra-docs", instant)

        # 3c. a robot in front of the door (D2, the independent verification): the press still takes the door, as the bell's and the rack's
        placed = await page.evaluate("() => window.__dbg.srRobotBeforeDoor()")
        rid = placed and placed["id"]
        await page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        at = (await page.evaluate(SR))["door"]
        under = res["doorUnder"] = await page.evaluate("(p) => window.__dbg.under(p)", at)
        check(failures, bool(rid) and isinstance(under, list) and under[:1] == [f"robot:{rid}"] and "door" in under,
              f"the robot stands in front of the door at its point: {under}")
        await page.mouse.click(at[0], at[1])
        await until(page, "() => window.__dbg.sr().phase !== 'idle' || !!window.__dbg.board().robot", "the press behind the robot", timeout=5000)
        res["doorBehindRobot"] = {"phase": (await page.evaluate(SR))["phase"], "card": await page.evaluate("() => window.__dbg.board().robot || null")}
        check(failures, res["doorBehindRobot"]["phase"] in ("loading", "ok", "open") and not res["doorBehindRobot"]["card"],
              f"the door behind a robot takes the press (no robot card): {res['doorBehindRobot']}")
        await until(page, "() => window.__dbg.sr().open || window.__dbg.sr().phase === 'idle'", "settled after the press", timeout=15000)
        if (await page.evaluate(SR))["open"]:
            await page.keyboard.press("Escape")
        await page.keyboard.press("Escape")

        # 4. rooms that cannot be read: red, the file named, the room stays, no value shown
        await up_close("bad")
        for name, want in (("broken", "prod.json"), ("schema", "prod.json"), ("secret", "prod.json"), ("specSecret", "/nodes/0/spec/1/value")):
            (bad / "docs" / "infra" / "prod.json").write_text(BAD[name], encoding="utf-8")
            await press_door()
            await until(page, "() => window.__dbg.sr().phase === 'failed'", f"{name}: failed")
            s = res[f"fail-{name}"] = await page.evaluate(SR)
            text = ((s["bubble"] or {}).get("text") or "") + "\n" + ((s["bubble"] or {}).get("full") or "")
            check(failures, s["keypad"] == "failed" and (s["bubble"] or {}).get("kind") == "error" and want in text and not s["open"],
                  f"{name}: the keypad red, the bubble names the file, the room stays: {s['keypad']} {s['bubble']}")
            check(failures, (await page.evaluate("() => window.__dbg.solo()")) == pid["bad"], f"{name}: still in the room")
            check(failures, want in ((s["bubble"] or {}).get("text") or ""), f"{name}: the bubble's own line (the short one) names the file: {s['bubble']}")   # E2
            if name in ("broken", "secret"):
                await doc_words_shot(page, f"sr-fail-{name}", out, failures)   # the bubble's line (lang_checks.py)
            if name == "secret":
                leaked = [v for v in secret_values if len(v) >= 6 and v in text]
                check(failures, not leaked, f"no secret-shaped value in the bubble or its whole text: {leaked}")
            if name == "specSecret":
                html = await page.content()
                check(failures, T("srv.room.secret.connection_string") in text and "db-prod.internal" not in html and SPEC_SECRET not in html,
                      f"a spec value with a secret's shape: refused by its place and kind, the value nowhere on the page: {s['bubble']}")
            if name == "broken":
                await page.hover("#sr-bubble")
                rect = (await page.evaluate(SR))["bubbleRect"]
                vw = await page.evaluate("() => window.innerWidth")
                check(failures, rect and rect[0] >= 0 and rect[1] >= 0 and rect[2] <= vw, f"the error bubble stays on the page: {rect} (width {vw})")
                await page.screenshot(path=str(out / "failed-light.png"))

        # 4b. away from the room after a failure: the bubble goes at once (D1, the independent verification; read from the page, not the
        # e2e hook). Staying: it goes after SR.failMs (9 s, E4)
        bubble_dom = "() => { const b = document.getElementById('sr-bubble'); return b.hidden ? null : b.querySelector('.sr-short').textContent; }"
        # → to the next room (the independent re-verification X1: the floor was the only way out an arm took)
        res["stepAfterFail"] = {"before": await page.evaluate(bubble_dom)}
        await page.keyboard.press("ArrowRight")
        await until(page, f"() => !!window.__dbg.solo() && window.__dbg.solo() !== '{pid['bad']}'", "the next room with →")
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 1500", "1.5 s in the next room", arg=t)
        res["stepAfterFail"].update({"after": await page.evaluate(bubble_dom), "room": await page.evaluate("() => window.__dbg.solo()"), "phase": (await page.evaluate(SR))["phase"]})
        check(failures, res["stepAfterFail"]["before"] and res["stepAfterFail"]["after"] is None and res["stepAfterFail"]["phase"] == "idle",
              f"the failure's bubble goes when → takes the view to the next room: {res['stepAfterFail']}")
        await up_close("bad")
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'failed'", "failed again (to leave for the floor)")
        res["leftAfterFail"] = {"before": await page.evaluate(bubble_dom)}
        await page.click("#room-back")
        await until(page, "() => window.__dbg.solo() === null", "the floor after a failure")
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 1500", "1.5 s on the floor", arg=t)
        res["leftAfterFail"]["after"] = await page.evaluate(bubble_dom)
        check(failures, res["leftAfterFail"]["before"] and res["leftAfterFail"]["after"] is None, f"the failure's bubble goes when the room is left: {res['leftAfterFail']}")
        await up_close("bad")
        await press_door()
        await until(page, "() => window.__dbg.sr().phase === 'failed'", "failed again (to stay)")
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 9500", "9.5 s in the room", arg=t, timeout=20000)
        res["failGone"] = {"bubble": await page.evaluate(bubble_dom), "phase": (await page.evaluate(SR))["phase"]}
        check(failures, res["failGone"] == {"bubble": None, "phase": "idle"}, f"the failure goes after 9 s in the room: {res['failGone']}")

        # 5. crossing cables; icons
        await up_close("multi")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "multi open", timeout=20000)
        s = res["multi"] = await page.evaluate("() => ({ ...window.__dbg.sr(), cross: window.__dbg.srCross() })")
        check(failures, s["shown"]["cross"] > 0 and s["cross"]["dashed"] and s["cross"]["drawn"] == s["shown"]["cross"],
              f"provider-crossing cables drawn apart, dashed: {s['shown']} {s['cross']}")
        check(failures, s["lod"] == "near" and s["layers"] == {"near": True, "far": False}, f"multi up close: no far box over the floors: {s['lod']} {s['layers']}")
        # fewer lines (2.3.9, item 1): faint by default; a chosen node's cables strong; the switch hides the rest
        ln = {"default": await page.evaluate("() => window.__dbg.srLines()")}
        node = await page.evaluate("() => { const ids = window.__dbg.srNodeEnvs().map((x) => x[0]); return ids.sort((a, b) => window.__dbg.srEdgesOf(b) - window.__dbg.srEdgesOf(a))[0]; }")
        want = await page.evaluate("(id) => window.__dbg.srEdgesOf(id)", node)
        await page.evaluate("(id) => window.__dbg.srSelect(id)", node)
        ln["chosen"] = {**(await page.evaluate("() => window.__dbg.srLines()")), "node": node, "edges": want}
        await page.screenshot(path=str(out / "lines-chosen-light.png"))
        for mode in ("cross", "focus"):
            await page.select_option("#sr-lines", mode)
            await until(page, "(m) => window.__dbg.srLines().mode === m", f"lines: {mode}", arg=mode)
            ln[mode] = await page.evaluate("() => window.__dbg.srLines()")
        await page.screenshot(path=str(out / "lines-focus-light.png"))
        await page.select_option("#sr-lines", "all")
        await page.evaluate("() => window.__dbg.srSelect(null)")
        res["lines"] = ln
        # filter by cloud (2.3.9, item 3): the legend's clouds toggle; only their nodes, no empty floor, 全部 back
        pv = {"all": await page.evaluate("() => window.__dbg.srProviders()")}
        prov_all = {i: p for i, p in pv["all"]["drawn"]}
        gcp_node = next(i for i, p in pv["all"]["drawn"] if p == "gcp")
        await page.evaluate("(id) => window.__dbg.srSelect(id)", gcp_node)   # chosen, then filtered out (the independent verification 4)
        await page.click("#sr-board [data-sr-prov='aws']")
        await until(page, "() => window.__dbg.srProviders().only.join() === 'aws'", "only aws")
        pv["aws"] = await page.evaluate("() => window.__dbg.srProviders()")
        sel_after = await page.evaluate("() => window.__dbg.srLines()")
        res["filterDropsChoice"] = {"node": gcp_node, "selected": sel_after["selected"], "board": sel_after["boardSelected"]}
        await page.click("#sr-board [data-sr-prov='aws']")   # pressed again: off (X2)
        await until(page, "() => window.__dbg.srProviders().only.length === 0", "aws pressed again")
        pv["awsOff"] = await page.evaluate("() => window.__dbg.srProviders()")
        # two clouds with cables between them (cloudflare's api to gcp's search and queue; X1)
        await page.click("#sr-board [data-sr-prov='cloudflare']")
        await page.click("#sr-board [data-sr-prov='gcp']")
        await until(page, "() => window.__dbg.srProviders().only.length === 2", "cloudflare and gcp")
        pv["cfGcp"] = await page.evaluate("() => window.__dbg.srProviders()")
        await page.screenshot(path=str(out / "filter-light.png"))
        await page.click("#sr-board [data-sr-prov='']")
        await until(page, "() => window.__dbg.srProviders().only.length === 0", "all clouds again")
        pv["back"] = await page.evaluate("() => window.__dbg.srProviders()")
        res["filter"] = {k: {"only": v["only"], "nodes": len(v["drawn"]), "providers": sorted({p for _, p in v["drawn"]}), "cross": len(v["cross"]), "groups": v["groups"],
                             "emptyFloors": v["emptyFloors"]} for k, v in pv.items()}
        f = res["filter"]
        prov_of = {i: p for i, p in pv["cfGcp"]["drawn"]}
        want_cross = [(a_, b_) for a_, b_ in pv["all"]["cross"] if {prov_all.get(a_), prov_all.get(b_)} <= {"cloudflare", "gcp"}]
        check(failures, f["aws"]["providers"] == ["aws"] and f["aws"]["nodes"] > 0 and f["aws"]["cross"] == 0 and not f["aws"]["emptyFloors"] and not f["cfGcp"]["emptyFloors"],
              f"one cloud chosen: its nodes only, no crossing cable, no empty floor: {f['aws']} (all {f['all']})")
        check(failures, res["filterDropsChoice"]["selected"] is None and not res["filterDropsChoice"]["board"], f"a choice filtered out is let go: {res['filterDropsChoice']}")
        check(failures, f["awsOff"]["only"] == [] and f["awsOff"]["nodes"] == f["all"]["nodes"], f"a chosen cloud pressed again is off: {f['awsOff']}")
        check(failures, set(f["cfGcp"]["providers"]) == {"cloudflare", "gcp"} and want_cross and len(pv["cfGcp"]["cross"]) == len(want_cross)
              and all({prov_of.get(a_), prov_of.get(b_)} <= {"cloudflare", "gcp"} for a_, b_ in pv["cfGcp"]["cross"]),
              f"two clouds chosen: both, and every crossing between them: {f['cfGcp']} (want {len(want_cross)})")
        check(failures, f["back"]["nodes"] == f["all"]["nodes"] and f["back"]["groups"] == f["all"]["groups"], f"全部 brings every node back: {f['back']} vs {f['all']}")
        # the lines switch holds through a rebuild (X3), and the far view's bundles follow it, faint (the independent verification 5)
        await page.select_option("#sr-lines", "cross")
        await page.check("#sr-fold")
        await until(page, "() => window.__dbg.srLines() && window.__dbg.srLines().mode === 'cross'", "rebuilt with crossing lines only")
        res["linesRebuilt"] = await page.evaluate("() => window.__dbg.srLines()")
        await page.evaluate("() => window.__dbg.srZoom(10)")
        await until(page, "() => window.__dbg.sr().lod === 'far'", "far, crossing lines only", timeout=5000)
        res["linesFar"] = (await page.evaluate("() => window.__dbg.srLines()"))["far"]
        await page.select_option("#sr-lines", "all")
        res["linesFarAll"] = (await page.evaluate("() => window.__dbg.srLines()"))["far"]
        # the chosen node's lines only: far, the crossing bundles go too (Z2, the independent check 20:30:51) — on a layer that
        # draws at least one, so that "not seen" is not an empty layer's
        await page.select_option("#sr-lines", "focus")
        await until(page, "() => window.__dbg.srLines().mode === 'focus'", "far, the chosen node's lines only")
        res["linesFarFocus"] = (await page.evaluate("() => window.__dbg.srLines()"))["far"]
        await page.select_option("#sr-lines", "all")
        await page.uncheck("#sr-fold")
        await page.click("#sr-fit")
        lr, lf, la = res["linesRebuilt"], res["linesFar"], res["linesFarAll"]
        check(failures, not lr["plainVisible"] and lr["crossVisible"], f"the lines switch holds through a rebuild: {lr}")
        if FLAT["on"]:   # 2D far: pulled back, so only the crossing bundles whatever the switch says (「引きでは跨ぐ線だけ」)
            check(failures, not lf["plainVisible"] and lf["crossVisible"] and not la["plainVisible"] and la["crossVisible"] and la["crossOpacity"] <= 0.6,
                  f"2D far: the crossing bundles only, faint, with the switch at all too: {lf} / {la}")
        else:
            check(failures, not lf["plainVisible"] and lf["crossVisible"] and la["plainVisible"] and la["plainOpacity"] <= 0.3 and la["crossOpacity"] <= 0.6,
                  f"far, the bundles are faint and follow the switch: {lf} / {la}")
        lff = res["linesFarFocus"]
        check(failures, la["crossCount"] >= 1 and la["crossVisible"], f"far, at least one crossing bundle drawn and seen with all lines (else the next arm proves nothing): {la}")
        check(failures, not lff["crossVisible"] and not lff["plainVisible"] and lff["crossCount"] == la["crossCount"],
              f"far, the chosen node's lines only: the crossing bundles hidden, not removed: {lff} / {la}")
        d, c = ln["default"], ln["chosen"]
        check(failures, d["plainOpacity"] <= 0.3 and d["focus"] == 0 and d["plainVisible"] and d["crossVisible"], f"lines faint by default, none strong: {d}")
        check(failures, want > 0 and c["focus"] == want, f"a chosen node's cables drawn strong, all of them: {c}")
        check(failures, not ln["cross"]["plainVisible"] and ln["cross"]["crossVisible"] and ln["cross"]["focus"] == want, f"crossing lines only: {ln['cross']}")
        check(failures, not ln["focus"]["plainVisible"] and not ln["focus"]["crossVisible"] and ln["focus"]["focus"] == want, f"the chosen node's lines only: {ln['focus']}")
        await page.screenshot(path=str(out / "multi-light.png"))
        await run_cables_and_reach(page, out, failures, res)
        await run_flows(page, out, failures, res)
        await run_flow_pace(page, out, failures, res)
        await run_flow_route(page, out, failures, res)
        await page.keyboard.press("Escape")
        await up_close("icons")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "icons open", timeout=20000)
        await until(page, "() => window.__dbg.sr().icons > 0", "the room's icons on their nodes", timeout=10000)
        res["icons"] = (await page.evaluate(SR))["icons"]
        node_env = (svc_node.get("environments") or [None])[0]
        if node_env and (await page.evaluate(SR))["env"] != node_env:   # the node is drawn in its own environment only
            await page.select_option("#sr-env", node_env)
            await until(page, "(e) => window.__dbg.sr().env === e", "the service node's environment", arg=node_env)
        await until(page, f"() => '{svc_node['id']}' in window.__dbg.srIconKeys()", "the service node's icon key", timeout=10000)
        keys = await page.evaluate("() => window.__dbg.srIconKeys()")
        res["iconKey"] = {"node": svc_node["id"], "key": keys.get(svc_node["id"]), "want": svc_key}
        check(failures, res["iconKey"]["key"] == svc_key, f"a node with a service icon and a category icon shows the service's: {res['iconKey']}")   # E5
        await page.keyboard.press("Escape")

        # 6. the large model: drawn, frames kept, far and near
        await up_close("large")
        await press_door()
        await until(page, "() => window.__dbg.sr().open", "large open", timeout=60000)
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Performance.enable")

        async def frames(where):
            await page.evaluate("() => window.__dbg.srFramesReset()")
            await until(page, "() => window.__dbg.sr().frames.length >= 60", f"60 frames drawn ({where})", timeout=60000)
            s = await page.evaluate(SR)
            fr = sorted(s["frames"])
            heap = {m["name"]: m["value"] for m in (await cdp.send("Performance.getMetrics"))["metrics"]}
            return s, {"lod": s["lod"], "cellPx": s["cellPx"], "frameMedian": round(statistics.median(fr), 1), "frameP90": round(fr[int(len(fr) * 0.9)], 1),
                       "labels": s["labels"], "gpu": s["gpu"], "jsHeapUsedMB": round(heap.get("JSHeapUsedSize", 0) / 1e6, 1)}
        s, first = await frames("fit")
        res["large"] = {"stats": s["stats"], "fit": first}
        check(failures, s["stats"]["nodes"] >= 1500 and first["frameP90"] < FRAME_P90_MAX_MS, f"the large model is drawn and does not stall: {res['large']}")
        # fit-all on the large room draws what it drew before the models (§3: 「引きになったら負荷が大きいので今の表示で」): the far
        # boxes only — 3 draw calls, 12 triangles, as on 2.3.19 — and no model is made
        fit_models = (await page.evaluate("() => window.__dbg.srDetail()"))["models"]
        res["large"]["fitModels"] = len(fit_models)
        if FLAT["on"]:   # 2D pulled back (the requester 10-23: 「引きでは跨ぐ線だけ」): the cables within a provider hidden, the crossing ones drawn
            res["large"]["fitLines"] = s["lines"]
            check(failures, s["lines"] == {"plain": False, "cross": True, "sparse": True} and first["cellPx"] < 18,
                  f"2D, the large room pulled back: only the cables crossing providers: {s['lines']} at {first['cellPx']} px a cell")
        if FLAT["on"]:   # 2D frames the room tighter (no slant): at fit a cell is past the far threshold, so the floors, tiles and
            # routed cables are drawn — no model, and the frame within the same p90 (checked above); the draw is recorded
            res["large"]["fitFlat"] = {"lod": first["lod"], "cellPx": first["cellPx"], "gpu": first["gpu"]}
            check(failures, fit_models == {} and first["gpu"]["calls"] <= 40, f"2D, the large room at fit-all: no model, a few dozen draws at most: {res['large']['fitFlat']}")
        else:
            check(failures, first["gpu"]["calls"] == 3 and first["gpu"]["triangles"] == 12 and fit_models == {},
                  f"the large room at fit-all: the far boxes alone, as before, and no model: {first['gpu']} models {len(fit_models)}")
        px_far = await page.evaluate("() => window.__dbg.srZoom(3)")
        await until(page, "() => window.__dbg.sr().lod === 'far'", "far", timeout=5000)
        await until(page, "() => window.__dbg.sr().labels > 0", "far labels", timeout=5000)
        far, res["large"]["far"] = await frames("far")
        await page.screenshot(path=str(out / "large-far-light.png"))
        px_near = await page.evaluate("() => window.__dbg.srZoom(0.05)")
        await until(page, "() => window.__dbg.sr().lod === 'near'", "near", timeout=5000)
        await until(page, "(n) => window.__dbg.sr().labels > n", "near labels", arg=far["labels"], timeout=5000)
        if FLAT["on"]:
            nl = res["large"]["nearLines"] = (await page.evaluate(SR))["lines"]
            check(failures, nl == {"plain": True, "cross": True, "sparse": False}, f"2D, the large room up close: every cable again: {nl}")
        lr = res["largeRoutes"] = await page.evaluate("() => window.__dbg.srCableRoutes({ side: 0.3, clear: 0.25, cross: 0.06 })")
        _routes_ok(failures, "the large room", lr)
        check(failures, lr["bent" if FLAT["on"] else "rising"] > 0, f"the large room: cables go round (2D) / rise over (3D) what stands on their way (else the arm proves nothing): {lr}")
        await page.screenshot(path=str(out / "large-routes.png"))
        near, res["large"]["near"] = await frames("near")
        rects = await page.evaluate("() => window.__dbg.srLabelRects()")
        overlaps = sum(1 for i, a_ in enumerate(rects) for b_ in rects[i + 1:] if a_[0] < b_[2] - 1 and b_[0] < a_[2] - 1 and a_[1] < b_[3] - 1 and b_[1] < a_[3] - 1)
        res["labelOverlaps"] = [len(rects), overlaps]
        check(failures, len(rects) > 10 and overlaps == 0, f"no label covers another up close: {res['labelOverlaps']}")   # E12
        check(failures, max(res["large"]["far"]["frameP90"], res["large"]["near"]["frameP90"]) < FRAME_P90_MAX_MS, f"far and near do not stall: {res['large']}")
        await page.screenshot(path=str(out / "large-near-light.png"))
        # up close (§5): many in view, the simple shapes; moved in on one Lambda, the shapes by service and tags with the
        # service; between the two thresholds it stays as it was; the whole view, simple again
        d0 = await page.evaluate("() => window.__dbg.srDetail()")
        res["largeModels"] = {"many": len(d0["models"])}
        check(failures, d0["models"] == {} and all(d0["detailDrawn"]), f"the large room, many in view: no model, the shapes as they were: {res['largeModels']}")
        fn = next(i for i, sh in d0["simple"].items() if sh == "flat:bolt") if FLAT["on"] else \
            next(i for i, sh in d0["byService"].items() if sh == "pillar" and d0["simple"].get(i) == "rack")
        await page.evaluate("(id) => window.__dbg.srSelect(id)", fn)
        await page.click("#sr-board [data-sr-act='focus']")
        d1 = await until(page, "() => { const d = window.__dbg.srDetail(); return d && d.detail ? d : null; }", "moved in on a Lambda: detail",
                         timeout=10000, why="() => { const d = window.__dbg.srDetail(); return d && [d.detail, d.inView]; }")
        await page.screenshot(path=str(out / "large-detail-light.png"))
        k = d1["inView"]
        # in: as many in view as leave is still in (<=, the independent check's SE3: each boundary at its exact count)
        await until(page, f"() => {{ const d = window.__dbg.srDetail({{ enter: {k - 1}, leave: {k} }}); return d.inView === {k} ? d : null; }}",
                    "past enter, at leave", timeout=5000)
        await page.evaluate("() => new Promise((r) => setTimeout(r, 300))")
        stay = await page.evaluate(f"() => window.__dbg.srDetail()")
        await page.evaluate(f"() => window.__dbg.srDetail({{ enter: {k - 1}, leave: {k - 1} }})")
        off = await until(page, "() => { const d = window.__dbg.srDetail(); return d.detail ? null : d; }", "past leave: simple", timeout=5000)
        await page.evaluate(f"() => window.__dbg.srDetail({{ enter: {k - 1}, leave: {k + 5} }})")
        await page.evaluate("() => new Promise((r) => setTimeout(r, 300))")
        still_off = await page.evaluate("() => window.__dbg.srDetail()")
        # out: as many in view as enter goes in (<=)
        await page.evaluate(f"() => window.__dbg.srDetail({{ enter: {k}, leave: {k + 5} }})")
        at_enter = await until(page, "() => { const d = window.__dbg.srDetail(); return d.detail ? d : null; }", "at enter: in", timeout=5000,
                               why="() => { const d = window.__dbg.srDetail(); return [d.detail, d.inView, d.enter]; }")
        await page.evaluate("() => window.__dbg.srDetail({ enter: 30, leave: 40 })")
        await until(page, "() => window.__dbg.srDetail().detail", "back in detail", timeout=5000)
        await page.click("#sr-fit")
        d2 = await until(page, "() => { const d = window.__dbg.srDetail(); return d.detail ? null : d; }", "the whole view: simple again", timeout=10000)
        res["largeModels"].update(close=[len(d1["models"]), sorted(set(d1["models"].values()))], whole=len(d2["models"]))
        if FLAT["on"]:   # 2D: the tiles say the kind at every distance; no model is ever made
            check(failures, d1["simple"].get(fn) == "flat:bolt" and all(d1["simple"].get(i) == f"flat:{d1['kinds'][i]}" for i in d1["inViewIds"]) and d1["models"] == {} and d2["models"] == {},
                  f"2D, the large room: moved in, each node in view its kind's tile (the Lambda a bolt), no model at any distance: {res['largeModels']}")
        else:
            check(failures, d1["models"].get(fn) == "bolt" and all(d1["models"].get(i) == d1["kinds"][i] for i in d1["inViewIds"]) and d2["models"] == {},
                  f"the large room: moved in, each node in view its model (the Lambda a bolt); the whole view again, none: {res['largeModels']}")
        await page.evaluate("() => window.__dbg.srSelect(null)")
        def svc_tags(d):
            return [t for t in d["tags"] if " · " in t]
        res["detail"] = {"many": [d0["detail"], d0["inView"]], "fn": fn, "close": [d1["detail"], d1["inView"], d1["byService"].get(fn), d1["simple"][fn],
                         sorted(set(d1["picks"])), svc_tags(d1)[:6]], "gap": [stay["detail"], off["detail"], still_off["detail"], at_enter["detail"], k],
                         "whole": [d2["detail"], d2["inView"], d2["shown"], sorted(set(d2["picks"])), svc_tags(d2)[:3]]}
        check(failures, not d0["detail"] and d0["inView"] > 40, f"many nodes in view: the simple shapes: {res['detail']['many']}")
        if FLAT["on"]:   # 2D: one set of tiles at every distance; up close the tags say the service
            check(failures, d1["detail"] and k <= 30 and d1["shown"]["simple"] and "flat:bolt" in d1["picks"]
                  and any(t.startswith(f"{fn} · Lambda") for t in d1["tags"]), f"2D, moved in on a Lambda: its tile, a tag with the service: {res['detail']['close']}")
        else:
            check(failures, d1["detail"] and k <= 30 and d1["shown"] == {"simple": False, "detail": True} and "pillar" in d1["picks"] and "rack" not in [d1["byService"][fn]]
                  and any(t.startswith(f"{fn} · Lambda") for t in d1["tags"]), f"moved in on a Lambda: its own shape, a tag with the service: {res['detail']['close']}")
        check(failures, stay["detail"] and not off["detail"] and not still_off["detail"] and at_enter["detail"],
              f"between entering and leaving the look stays as it was: (in at leave, out past leave, stays out, in at enter) {res['detail']['gap']}")
        check(failures, not d2["detail"] and d2["shown"] == {"simple": True, "detail": False} and not svc_tags(d2) and "pillar" not in d2["picks"],
              f"the whole view: the simple shapes and names only: {res['detail']['whole']}")
        res["lod"] = {"far": [px_far, far["labels"]], "near": [px_near, near["labels"]]}
        check(failures, far["lod"] == "far" and near["lod"] == "near" and far["labels"] < near["labels"],
              f"zoomed out the groups are boxes and the labels thin out: {res['lod']}")

        # 6a. a box drawn to move in on (2.3.11 item 6): Option + drag, or 範囲で寄る then a drag; Shift still pans, Esc stops
        # the box only, 全体を見る goes back
        async def frames_settled():
            await page.evaluate("() => new Promise((r) => { let n = 0; const f = () => (++n < 12 ? requestAnimationFrame(f) : r()); requestAnimationFrame(f); })")

        async def drag(x0, y0, x1, y1, mods=()):
            for m in mods:
                await page.keyboard.down(m)
            await page.mouse.move(x0, y0)
            await page.mouse.down()
            await page.mouse.move(x1, y1, steps=8)
            mid = await page.evaluate("() => window.__dbg.srBox()")
            await page.mouse.up()
            for m in mods:
                await page.keyboard.up(m)
            await frames_settled()
            return mid

        def on_page(xy, rect):
            return xy is not None and rect[0] <= xy[0] <= rect[2] and rect[1] <= xy[1] <= rect[3]

        def same_cam(a, b, tol=0.05):   # the controls' damping still drifts a pan's last thousandths
            return all(abs(x - y) <= tol for x, y in zip(a["target"] + a["pos"] + [a["dist"]], b["target"] + b["pos"] + [b["dist"]]))

        await page.click("#sr-fit")
        await frames_settled()
        fit_cam = await page.evaluate("() => window.__dbg.srCam()")
        await page.evaluate("() => window.__dbg.srZoom(0.3)")
        await until(page, "() => window.__dbg.sr().lod === 'near'", "near for the box", timeout=5000)
        await frames_settled()
        box_res = res["box"] = {}
        scr = await page.evaluate("() => window.__dbg.srScreen()")
        rect = scr["rect"]
        cw, ch = rect[2] - rect[0], rect[3] - rect[1]
        cx, cy = rect[0] + cw / 2, rect[1] + ch / 2
        for frac in (0.12, 0.2, 0.3):   # a box in the middle holding a few nodes
            bx = [cx - cw * frac / 2, cy - ch * frac / 2, cx + cw * frac / 2, cy + ch * frac / 2]
            inside = {i for i, xy in scr["nodes"] if on_page(xy, bx)}
            if len(inside) >= 3:
                break
        outside = {i for i, xy in scr["nodes"] if on_page(xy, rect)} - inside
        box_res["before"] = {"box": [round(v) for v in bx], "inside": len(inside), "outsideOnPage": len(outside)}
        # a plain drag still turns (the target stays); Shift + drag still pans (the target moves); neither draws a box
        c0 = await page.evaluate("() => window.__dbg.srCam()")
        mid = await drag(cx, cy, cx + 120, cy + 10)
        c1 = await page.evaluate("() => window.__dbg.srCam()")
        box_res["turn"] = {"mid": mid, "target": [c0["target"], c1["target"]], "moved": c0["pos"] != c1["pos"]}
        if FLAT["on"]:   # 2D turns nothing: a plain drag moves the floor under the camera (its target moves, the zoom stays), no box
            box_res["turn"]["zoom"] = [c0["zoom"], c1["zoom"]]
            check(failures, not mid["shown"] and c0["target"] != c1["target"] and abs(c0["zoom"] - c1["zoom"]) < 1e-6 and (await page.evaluate("() => window.__dbg.srBox()"))["last"] is None,
                  f"2D: a plain drag moves the view, no turn, no box: {box_res['turn']}")
        else:
            check(failures, not mid["shown"] and all(abs(x - y) <= 0.05 for x, y in zip(c0["target"], c1["target"])) and not same_cam(c0, c1), f"a plain drag still turns, no box: {box_res['turn']}")
            mid = await drag(cx, cy, cx + 120, cy + 60, ("Shift",))
            c2 = await page.evaluate("() => window.__dbg.srCam()")
            box_res["pan"] = {"mid": mid, "target": [c1["target"], c2["target"]], "last": (await page.evaluate("() => window.__dbg.srBox()"))["last"]}
            check(failures, not mid["shown"] and c1["target"] != c2["target"] and box_res["pan"]["last"] is None, f"Shift + drag still pans, no box: {box_res['pan']}")
        # the view the box is measured on: back to where the nodes were found
        await page.click("#sr-fit")
        await page.evaluate("() => window.__dbg.srZoom(0.3)")
        await frames_settled()
        scr = await page.evaluate("() => window.__dbg.srScreen()")
        # the box around the five nodes nearest the middle: it holds several, spread, so how it fills the page tells
        near5 = sorted((xy for _i, xy in scr["nodes"] if on_page(xy, rect)), key=lambda xy: (xy[0] - cx) ** 2 + (xy[1] - cy) ** 2)[:5]
        bx = [min(x for x, _ in near5) - 8, min(y for _, y in near5) - 8, max(x for x, _ in near5) + 8, max(y for _, y in near5) + 8]
        inside = {i for i, xy in scr["nodes"] if on_page(xy, bx)}
        outside = {i for i, xy in scr["nodes"] if on_page(xy, rect)} - inside
        mid = await drag(bx[0], bx[1], bx[2], bx[3], ("Alt",))
        after = await page.evaluate("() => window.__dbg.srScreen()")
        last = (await page.evaluate("() => window.__dbg.srBox()"))["last"]
        pos = dict((i, xy) for i, xy in after["nodes"])
        missing = sorted(i for i in inside if not on_page(pos.get(i), after["rect"]))
        gone = [i for i in outside if not on_page(pos.get(i), after["rect"])]
        box_res["alt"] = {"mid": mid, "inside": len(inside), "held": len(last["held"]) if last else None, "missing": missing[:10],
                          "outside": len(outside), "outsideGone": len(gone), "log": (await page.evaluate(SR))["log"][:1]}
        check(failures, mid["shown"] and inside and last and set(last["held"]) == inside and not missing,
              f"Option + drag: every node in the box is on the page after: {box_res['alt']}")
        check(failures, outside and len(gone) >= 0.8 * len(outside), f"Option + drag: most nodes outside the box leave the page: {box_res['alt']}")
        # how much of the page what the box held fills: its farthest node at SR.boxFit (0.92) of the half page
        ar = after["rect"]
        ndc = [max(abs((pos[i][0] - ar[0]) / (ar[2] - ar[0]) * 2 - 1), abs((pos[i][1] - ar[1]) / (ar[3] - ar[1]) * 2 - 1)) for i in inside if pos.get(i)]
        box_res["fill"] = {"held": len(inside), "farthest": round(max(ndc), 3) if ndc else None}
        check(failures, len(inside) >= 3 and ndc and 0.85 <= max(ndc) <= 0.95, f"Option + drag: what the box held fills the page to about 0.92: {box_res['fill']}")
        # Esc while drawing: the box goes, the room stays, the camera does not move
        await page.click("#sr-fit")
        await frames_settled()
        c3 = await page.evaluate("() => window.__dbg.srCam()")
        box_res["fit"] = [fit_cam, c3]
        check(failures, same_cam(c3, fit_cam), f"全体を見る goes back: {box_res['fit']}")
        await page.click("#sr-boxzoom")
        armed = await page.evaluate("() => window.__dbg.srBox()")
        await page.mouse.move(cx - 80, cy - 60)
        await page.mouse.down()
        await page.mouse.move(cx + 80, cy + 60, steps=6)
        drawing = await page.evaluate("() => window.__dbg.srBox()")
        await page.keyboard.press("Escape")
        await page.mouse.up()
        await frames_settled()
        esc = await page.evaluate("() => window.__dbg.srBox()")
        c4 = await page.evaluate("() => window.__dbg.srCam()")
        box_res["esc"] = {"armed": armed, "drawing": drawing, "after": esc, "open": (await page.evaluate(SR))["open"], "cam": [c3, c4]}
        check(failures, armed["armed"] and drawing["drawing"] and drawing["shown"] and not esc["drawing"] and not esc["shown"] and not esc["armed"]
              and box_res["esc"]["open"] and same_cam(c4, c3), f"Esc while drawing stops the box only: {box_res['esc']}")
        # 範囲で寄る: one plain drag draws the box, then the button is off again
        await page.click("#sr-boxzoom")
        mid = await drag(cx - cw * 0.1, cy - ch * 0.1, cx + cw * 0.1, cy + ch * 0.1)
        c5 = await page.evaluate("() => window.__dbg.srCam()")
        btn = await page.evaluate("() => window.__dbg.srBox()")
        box_res["button"] = {"mid": mid, "after": btn, "dist": [c3["dist"], c5["dist"]]}
        check(failures, mid["shown"] and not btn["armed"] and btn["last"] and c5["dist"] < c3["dist"] * 0.5,
              f"範囲で寄る then a plain drag moves in on the box, once: {box_res['button']}")
        # far: the box takes the top groups' boxes, and moves in on the one drawn around
        await page.click("#sr-fit")
        await page.evaluate("() => window.__dbg.srZoom(3)")
        await until(page, "() => window.__dbg.sr().lod === 'far'", "far for the box", timeout=5000)
        await frames_settled()
        far_scr = await page.evaluate("() => window.__dbg.srScreen()")
        tops = [(i, xy) for i, xy in far_scr["nodes"] if on_page(xy, rect)]
        gid, gxy = min(tops, key=lambda t: (t[1][0] - cx) ** 2 + (t[1][1] - cy) ** 2)
        px_far = (await page.evaluate(SR))["cellPx"]
        await drag(gxy[0] - 12, gxy[1] - 12, gxy[0] + 12, gxy[1] + 12, ("Alt",))
        last = (await page.evaluate("() => window.__dbg.srBox()"))["last"]
        box_res["far"] = {"group": gid, "last": last, "cellPx": [px_far, (await page.evaluate(SR))["cellPx"]]}
        check(failures, far_scr["lod"] == "far" and last and last["lod"] == "far" and last["held"] == [gid]
              and box_res["far"]["cellPx"][1] > px_far * 1.5, f"far: the box held the group drawn around and moved in on it: {box_res['far']}")
        await page.screenshot(path=str(out / "large-box.png"))
        await page.keyboard.press("Escape")

        # 6b. a room with no infra folder has no door (E13)
        await page.click("#room-back")
        await until(page, "() => window.__dbg.solo() === null", "the floor (no-door room)")
        await page.click(f".tag.room[data-set-project='{pid['none']}']")
        await until(page, f"() => window.__dbg.solo() === '{pid['none']}'", "the room without an infra folder")
        await until(page, f"() => window.__dbg.gitBox().room === '{pid['none']}'", "its things built", timeout=20000)
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 1000", "a second up close", arg=t)
        res["noDoor"] = (await page.evaluate(SR))["built"]
        check(failures, res["noDoor"] is False, f"a room without an infra folder has no door: built {res['noDoor']}")

        # 6c. the server room's button beside 呼び出し (2.3.21, requester: 「サーバールームに入るのボタンを呼び出しのメニューの横につけて
        # 欲しい / 今3Dクリックでしか入れないよね？」). In a room with no docs/infra it is there, not pressable, and says why; a press
        # reads nothing. In a room with one, Enter on it opens the server room as the door does (the door's own press: step 2).
        BTN = """() => { const b = document.getElementById('room-sr'), w = document.getElementById('room-sr-why'), c = document.getElementById('room-call');
          return b ? { shown: !b.hidden && b.getClientRects().length > 0, off: b.getAttribute('aria-disabled'), title: b.title, why: w ? w.textContent : null,
                       text: b.textContent, afterCall: !!c && c.nextElementSibling === b } : null; }"""
        await page.locator("#room-solo").screenshot(path=str(out / "room-bar-no-infra.png"))
        nb = res["srButtonNoInfra"] = await page.evaluate(BTN)
        before = len(asked)
        await page.focus("#room-sr")
        await page.keyboard.press("Enter")
        await page.click("#room-sr", force=True)   # a pointer's press on it (Playwright waits for aria-disabled to clear otherwise)
        t = await page.evaluate("() => performance.now()")
        await until(page, "(t) => performance.now() > t + 800", "a moment after the press", arg=t)
        nb["phase"] = (await page.evaluate(SR))["phase"]
        nb["reads"] = len(asked) - before
        check(failures, nb and nb["shown"] and nb["afterCall"] and nb["off"] == "true" and nb["title"] == T("page.room.sr.none")
              and nb["why"] == T("page.room.sr.none") and nb["phase"] == "idle" and nb["reads"] == 0,
              f"no docs/infra: the server room's button is beside 呼び出し, not pressable, says why, and a press reads nothing: {nb}")
        await up_close("three")
        await page.locator("#room-solo").screenshot(path=str(out / "room-bar.png"))
        yb = res["srButton"] = await page.evaluate(BTN)
        check(failures, yb and yb["shown"] and yb["afterCall"] and yb["off"] == "false" and yb["title"] == T("page.room.sr.title")
              and yb["text"] == T("page.room.sr"), f"a room with docs/infra: the button is pressable and names what it opens: {yb}")
        await page.focus("#room-sr")
        await page.keyboard.press("Enter")
        await until(page, "() => window.__dbg.sr().open", "the server room from its button", timeout=15000)
        res["srFromButton"] = (await page.evaluate(SR))["phase"]
        await page.screenshot(path=str(out / "sr-from-button.png"))
        await page.keyboard.press("Escape")
        await until(page, "() => !window.__dbg.sr().open && window.__dbg.sr().phase === 'idle'", "back to the room from the button's server room")

        # 7. reduced motion: the * stand still, the bubble shows
        ctx2 = await browser.new_context(**DESKTOP, reduced_motion="reduce")
        if flat:
            await ctx2.add_init_script(SR_FLAT_INIT)
        p2 = await ctx2.new_page()
        watch.attach(p2, "server-room-reduced")
        await p2.goto(url + "/")
        await ready(p2)
        await until(p2, f"() => window.__dbg.robots.length >= {len(rooms)}", "the robots (reduced motion)", timeout=60000)
        await p2.click(f".tag.room[data-set-project='{pid['three']}']")
        await until(p2, "() => window.__dbg.sr().built && window.__dbg.sr().door", "the door (reduced motion)", timeout=20000)
        await until(p2, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled (reduced motion)", timeout=30000)

        async def hold2(route):
            await p2.wait_for_timeout(1500)
            await route.continue_()
        await p2.route("**/api/infra-docs", hold2)
        at = (await p2.evaluate(SR))["door"]
        await p2.mouse.click(at[0], at[1])
        await until(p2, "() => window.__dbg.sr().phase === 'loading'", "reading (reduced motion)")
        a = await p2.evaluate("() => ({ ...window.__dbg.sr(), t: performance.now() })")
        await until(p2, "(t) => performance.now() > t + 600", "600 ms of the page's own clock", arg=a["t"])
        b = await p2.evaluate(SR)
        res["reduced"] = [a["stars"], b["stars"], (a["bubble"] or {}).get("text")]
        check(failures, a["stars"] == b["stars"] and (a["bubble"] or {}).get("text") == T("sr.loading"),
              f"reduced motion: the * stand still and the bubble shows: {res['reduced']}")
        await until(p2, "() => window.__dbg.sr().open", "open (reduced motion)", timeout=15000)
        # the cost's day under reduced motion: no play (the button disabled, pressing it moves nothing), the slider only
        await p2.click("#sr-mode-cost")
        await until(p2, "() => { const c = window.__dbg.srCost(); return c.month && c.month.bars === c.month.days; }", "the month (reduced motion)", timeout=20000)
        await p2.click("#sr-cost [data-src-date]")
        await until(p2, "() => { const c = window.__dbg.srCost(); return c.day && c.day.rows > 0; }", "a day (reduced motion)", timeout=20000)
        btn = await p2.evaluate("() => { const b = document.querySelector(\"#sr-cost [data-src-act='play']\"); return b ? { disabled: b.disabled } : null; }")
        h0 = (await p2.evaluate("() => window.__dbg.srCost()"))["day"]["hour"]
        await p2.evaluate("() => { window.__dbg.srCostPlayMs(100); const b = document.querySelector(\"#sr-cost [data-src-act='play']\"); b.disabled = false; b.click(); }")
        t = await p2.evaluate("() => performance.now()")
        await until(p2, "(t) => performance.now() > t + 700", "700 ms (reduced motion)", arg=t)
        d2 = (await p2.evaluate("() => window.__dbg.srCost()"))["day"]
        res["costReduced"] = {"button": btn, "hour": [h0, d2["hour"]], "playing": d2["playing"]}
        check(failures, btn and btn["disabled"] and d2["hour"] == h0 and not d2["playing"],
              f"reduced motion: the day does not play (the button disabled, a press moves no hour): {res['costReduced']}")
        await ctx2.close()

        # 8. the demo (and so export-demo): shop-app/'s door opens the made-up layout, the IAM role and the alarm folded
        ctx3 = await browser.new_context(**DESKTOP)
        if flat:
            await ctx3.add_init_script(SR_FLAT_INIT)
        p3 = await ctx3.new_page()
        watch.attach(p3, "server-room-demo")
        await p3.goto(url + "/?demo=1")
        await ready(p3)
        await until(p3, "() => window.__dbg.sr().built && !!window.__dbg.sr().door", "the demo's door", timeout=30000)
        # a seated robot in front of the demo's door: the press still takes the door (the live office's rule, here too)
        placed = res["demoBeforeDoor"] = await p3.evaluate("() => window.__dbg.srRobotBeforeDoor()")
        await p3.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
        check(failures, bool(placed) and str(placed.get("first", "")).startswith("robot:"), f"the demo: a robot stands in front of the door: {placed}")
        demo_door = (await p3.evaluate(SR))["door"]
        await p3.mouse.click(demo_door[0], demo_door[1])
        try:
            await until(p3, "() => window.__dbg.sr().phase === 'loading' && window.__dbg.sr().stars > 0", "the demo reads", timeout=5000)
        except Exception:
            card = await p3.evaluate("() => (window.__dbg.board ? window.__dbg.board().robot : null) || null")
            check(failures, False, f"the demo's door behind a robot did not take the press (card {card})")
            raise
        await until(p3, "() => window.__dbg.sr().open", "the demo's server room", timeout=15000)
        s = res["demo"] = await p3.evaluate(SR)
        check(failures, s["shown"]["nodes"] > 0 and s["shown"]["folded"] == 2 and s["shown"]["cross"] > 0 and s["shown"]["external"] == 1
              and s["layers"] == {"near": True, "far": False}, f"the demo's made-up layout: {s['shown']} {s['layers']}")
        for scheme in ("light", "dark"):
            await p3.emulate_media(color_scheme=scheme)
            await p3.screenshot(path=str(out / f"demo-{scheme}.png"))
        # an edge only in staging, between two nodes in both: not in production, there in staging (the edge's own environments)
        prod_edges = await p3.evaluate("() => window.__dbg.srEdges()")
        await p3.select_option("#sr-env", "staging")
        await until(p3, "() => window.__dbg.sr().env === 'staging'", "the demo's staging")
        stg_edges = await p3.evaluate("() => window.__dbg.srEdges()")
        res["demoEdges"] = {"production": "worker>cache" in prod_edges, "staging": "worker>cache" in stg_edges}
        check(failures, res["demoEdges"] == {"production": False, "staging": True}, f"an edge is drawn in its own environments only: {res['demoEdges']}")
        await p3.keyboard.press("Escape")
        await until(p3, "() => !window.__dbg.sr().open", "the demo's office again")
        await ctx3.close()
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    import subprocess as _sp
    res["uptime"] = _sp.run(["uptime"], capture_output=True, text=True).stdout.strip()
    print(f"  server-room: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "server-room-results.json").write_text(dump(res) + "\n")
