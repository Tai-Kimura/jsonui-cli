"""イベント and 操作 as one table (ticket 2026-10-20-jui-viz-spec-events-as-table; requester 10-20: 「イベントも見づらい
テーブルふうにして」, 「操作も見づらいからテーブルふうにして」).

fake_server.py with two specs. 予定: three events (one with the long description of the requester's form, its
arguments written only in the text) and two actions without a destination. 地図: two actions, one with a
destination (userAction.destination, the spec's own field). At 1440 px and at 390 px:

  - each event is one row of the table, its name cell and its description cell the spec's; the columns are
    イベント・説明 — no column the spec has no field for (an argument column read out of the text would be one);
  - each action is one row, 操作・結果, and 行き先 only on the spec that writes a destination;
  - the events and the actions are the same table (the same classes, the same cell classes), the look of the
    variables' table above (.vt);
  - an event's name is on one line;
  - wide: name and description side by side; narrow: the description under the name, nothing sideways
    (scrollWidth ≤ clientWidth).

Pictures of 状態 and 操作 at both widths.
"""

from __future__ import annotations

import json
import pathlib
import time

import scenarios as S
from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready
from live import step

EVENTS = [["onDateChange", "日付の変更（SelectBox の onValueChange。引数 fieldId: String, value: String）。VM の onDateChange(value:) に value を渡す。"
           "選んだ日付が今日より後なら、保存ボタンを押せない状態にして、理由を入力欄の下に出す。"],
          ["onRatingChange", "評価の変更"], ["onSaveTapWithAVeryLongEventHandlerNameForTheTest", "保存"]]
ACTIONS_PLAIN = [["保存ボタンを押す", "入力を確かめてから保存する。失敗したら入力欄の下に理由を出す", ""], ["戻る", "破棄の確認を出す", ""]]
ACTIONS_DEST = [["地図を開く", "座標があれば座標で、なければ住所で地図アプリを開く", "地図アプリ"], ["閉じる", "前の画面に戻る", ""]]


def scenario():
    a = S.sheet_for("plan")
    a["eventHandlers"], a["userActions"] = EVENTS, ACTIONS_PLAIN
    b = S.sheet_for("map")
    b["eventHandlers"], b["userActions"] = [["onOpen", "開く"]], ACTIONS_DEST
    P = [S.project("p-shop", "shop-app", 0)]
    sess = [S.session(S.S_A0, "a0", "p-shop", "shop-app", status="idle")]
    A = [S.agent(S.S_A0, "a0", S.S_A0, state="idle", act="待機")]
    specs = [S.spec("plan", items=[5, 6, 6, 4, 2, 2, 3]), S.spec("map", items=[5, 6, 4, 4, 2, 2, 3])]
    return [{"sheets": {specs[0]["id"]: a, specs[1]["id"]: b}}, {"mark": "start"},
            S.slices(0, projects=P, sessions=sess, agents=A, specs=specs, server=S.server_slice()), {"mark": "end"}]


TABLE_JS = """(sel) => { const t = document.querySelector(sel); if (!t) return null;
  const R = (el) => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; };
  const lines = (el) => { const rg = document.createRange(); rg.selectNodeContents(el); return new Set([...rg.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.top))).size; };
  return { cls: t.className, heads: [...t.querySelectorAll('thead th')].map((th) => th.textContent).filter((x) => x !== '状態'),
    rows: [...t.querySelectorAll('tbody tr')].map((tr) => { const tds = [...tr.children].filter((td) => !td.classList.contains('mk'));
      return { cells: tds.map((td) => td.textContent), cls: tds.map((td) => td.className), rects: tds.map(R), nameLines: tds[0] ? lines(tds[0]) : 0 }; }) }; }"""
SHEET_JS = "() => { const s = document.getElementById('wb-code'); return { sw: s.scrollWidth, cw: s.clientWidth, docSW: document.documentElement.scrollWidth, docCW: document.documentElement.clientWidth }; }"


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-tables: {text}")


def judge(failures, key, ev, ac, events, actions, heads, narrow):
    check(failures, ev is not None and ac is not None, f"{key}: an events table and an actions table: {ev is not None} {ac is not None}")
    if ev is None or ac is None:
        return
    check(failures, ev["heads"] == ["イベント", "説明"], f"{key}: the events' columns are the spec's fields, イベント・説明: {ev['heads']}")
    check(failures, [r["cells"] for r in ev["rows"]] == [list(e) for e in events], f"{key}: one row per event, its name and its description: {[r['cells'] for r in ev['rows']]}")
    check(failures, ac["heads"] == heads, f"{key}: the actions' columns are the spec's fields: {ac['heads']} (want {heads})")
    want = [list(a[:2]) + ([a[2]] if len(heads) == 3 else []) for a in actions]
    check(failures, [r["cells"] for r in ac["rows"]] == want, f"{key}: one row per action: {[r['cells'] for r in ac['rows']]}")
    check(failures, ev["cls"] == ac["cls"] and "vt" in ev["cls"].split() and ev["rows"] and all(r["cls"][1:] == ["nt-desc"] * (len(r["cls"]) - 1) for r in ev["rows"] + ac["rows"]),
          f"{key}: events and actions are one table component (the variables' .vt): {ev['cls']!r} {ac['cls']!r} {[r['cls'] for r in ev['rows'] + ac['rows']]}")
    check(failures, all(r["nameLines"] == 1 for r in ev["rows"]), f"{key}: an event's name on one line: {[r['nameLines'] for r in ev['rows']]}")
    pairs = [(r["rects"][0], r["rects"][1]) for r in ev["rows"]]
    if narrow:
        check(failures, all(d["t"] >= n["b"] - 0.5 for n, d in pairs), f"{key}: narrow, the description under the name: {pairs[:1]}")
    else:
        check(failures, all(d["l"] >= n["r"] - 0.5 and abs(d["t"] - n["t"]) < 4 for n, d in pairs), f"{key}: wide, name and description side by side: {pairs[:1]}")


async def run_spec_tables(pw, out, failures, Server, before=False):
    name = "spec-tables-before" if before else "spec-tables"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    path = S.write(scenario(), out / "spec-tables.jsonl")
    srv = Server(scenario=path)
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    res: dict = {}
    t0 = time.monotonic()
    try:
        step(srv, "start")
        for width, opts in (("1440", DESKTOP), ("390", PHONE)):
            for spec_name in ("plan", "map"):
                page = await new_page(browser, watch, f"{name}-{spec_name}-{width}", color_scheme="light", **opts)
                await page.goto(srv.url + "/")
                await ready(page)
                await page.wait_for_function("() => window.__dbg.model().specs.length === 2", timeout=20000)
                await page.evaluate("() => window.scrollTo(0, 0)")
                await page.click("#btn-specboard")
                await page.wait_for_function("() => { const el = document.getElementById('wb'); return !el.hidden && el.classList.contains('show'); }")
                idx = await page.evaluate("(n) => window.__dbg.model().specs.findIndex((x) => x.name === n)", spec_name.capitalize())
                await page.click(f'.ov-card[data-idx="{idx}"]')
                await page.wait_for_function("(n) => document.querySelectorAll('#wb-code section.sc').length === 8 && document.getElementById('wb-title').textContent.includes(n)",
                                             arg=spec_name.capitalize(), timeout=20000)
                await page.wait_for_timeout(700)
                for sec in (2, 4):
                    await page.evaluate("(k) => document.getElementById('wb-sec-' + k).scrollIntoView({ block: 'start' })", sec)
                    await page.wait_for_timeout(250)
                    await page.screenshot(path=str(out / f"{'before' if before else 'after'}-{spec_name}-sec{sec}-{width}.png"))
                if not before:
                    r = res[f"{spec_name}-{width}"] = {"events": await page.evaluate(TABLE_JS, "#wb-sec-2 table.nt"),
                                                        "actions": await page.evaluate(TABLE_JS, "#wb-sec-4 table.nt"), "sheet": await page.evaluate(SHEET_JS)}
                    events = EVENTS if spec_name == "plan" else [["onOpen", "開く"]]
                    actions, heads = (ACTIONS_PLAIN, ["操作", "結果"]) if spec_name == "plan" else (ACTIONS_DEST, ["操作", "結果", "行き先"])
                    judge(failures, f"{spec_name}-{width}", r["events"], r["actions"], events, actions, heads, width == "390")
                    sh = r["sheet"]
                    check(failures, sh["sw"] <= sh["cw"] and sh["docSW"] <= sh["docCW"], f"{spec_name}-{width}: nothing sideways: {sh}")
                await page.close()
        if not before:
            check(failures, not watch.console and not watch.foreign, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
    except Exception as e:
        failures.append(f"spec-tables: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.stop()
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
