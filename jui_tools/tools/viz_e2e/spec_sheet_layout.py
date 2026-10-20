"""The spec sheet stays inside its width (ticket 2026-10-20-jui-viz-spec-sheet-overflows-sideways; requester 10-20:
「specの表示崩れ」, then 「遷移と横並びじゃなくて縦並びで」).

fake_server.py with one spec whose sheet has long text everywhere 2.3.5 coloured or that sits on one line: a
transition of every kind with a 200-character destination (the requester's list screen had one of about 100), a type of
every kind 120 characters long, a long action, a long API path and method name, a long component id. At 1440 px and
at 390 px:

  - the sheet never scrolls sideways (scrollWidth ≤ clientWidth);
  - every section's rectangle lies inside the sheet's, one column: each section's left edge is the first one's, and
    no two sections share a row;
  - every transition tag lies inside its section, its kind label (遷移なし, push …) on one line (one line box);
  - every type cell lies inside its section.

Pictures of the 遷移 section at both widths.
"""

from __future__ import annotations

import json
import pathlib
import time

import scenarios as S
from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready
from live import step

LONG = "地図アプリ（座標あり → 座標に pin / 住所のみ → 住所で開く。両 OS とも選択 chooser 経由。開けなければ toast を出して一覧に戻る）"
LONG200 = (LONG * 3)[:200]
# one of every kind (spec_colors.TRANSITIONS's kinds: none, external, back, replace, modal, push, screen, other)
NEUTRAL = ("とても長い行き先の説明が続く。" * 20)[:200]   # no kind's words in it
TRANSITIONS = [["保存しない", "遷移なし（" + LONG200 + "）", ""], ["ヘルプ", "外部ブラウザ（https://example.invalid/" + "a" * 190 + "）", ""],
               ["戻るボタン", "前の画面に戻る（" + NEUTRAL + "）", ""], ["ログアウト", "Login" + "X" * 195, "replace"],
               ["フィルタ", "FilterSheet" + NEUTRAL, "sheet"], ["詳細を見る", "Detail" + "Y" * 194, "push"],
               ["何か", "Somewhere" + NEUTRAL, ""], ["あとで決める" + NEUTRAL, "？" * 200, ""]]
KINDS = ["none", "external", "back", "replace", "modal", "push", "screen", "other"]
TYPES = [["a", "String" * 20 + "?", "nil"], ["b", "[" + "Item" * 30 + "]", "[]"], ["c", "string", '""'], ["d", "Bool", "false"],
         ["e", "Int", "0"], ["f", "Color", "#fff"], ["g", "Visibility" + "Z" * 110, ".visible"]]


def scenario():
    sheet = S.sheet_for("layout")
    sheet["transitions"] = TRANSITIONS
    sheet["uiVariables"] = TYPES
    sheet["components"] = sheet["components"] + [["Label", "very_long_component_identifier_" * 6, "Label"]]
    sheet["userActions"] = [["送信を押す" + LONG200, "submit" + "Q" * 150 + "()"]]
    sheet["apis"] = [["operation" + "O" * 120, "POST", "/auth/" + "p" * 160]]
    sheet["vmMethods"] = ["load" + "L" * 150 + "()"]
    P = [S.project("p-shop", "shop-app", 0)]
    sess = [S.session(S.S_A0, "a0", "p-shop", "shop-app", status="idle")]
    A = [S.agent(S.S_A0, "a0", S.S_A0, state="idle", act="待機")]
    specs = [S.spec("layout", items=[5, 6, 7, 4, 1, 8, 3])]
    return [{"sheets": {specs[0]["id"]: sheet}}, {"mark": "start"},
            S.slices(0, projects=P, sessions=sess, agents=A, specs=specs, server=S.server_slice()), {"mark": "end"}]


STATE_JS = """() => { const sheet = document.getElementById('wb-code'), R = (el) => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; };
  const secs = [...sheet.querySelectorAll('section.sc')].map((s) => ({ id: s.id, ...R(s) }));
  const inSec = (el) => { const s = el.closest('section.sc'); return s ? R(s) : null; };
  const tags = [...sheet.querySelectorAll('[data-tk]')].map((el) => { const k = el.querySelector('.tk-k'); const kr = k ? k.getClientRects() : [];
    return { kind: el.dataset.tk, ...R(el), sec: inSec(el), labelBoxes: kr.length, labelH: k ? k.getBoundingClientRect().height : 0, labelLH: k ? parseFloat(getComputedStyle(k).lineHeight) : 0, label: k ? k.textContent : '' }; });
  const types = [...sheet.querySelectorAll('[data-ty]')].map((el) => ({ kind: el.dataset.ty, ...R(el), sec: inSec(el) }));
  return { sw: sheet.scrollWidth, cw: sheet.clientWidth, sheet: R(sheet), docSW: document.documentElement.scrollWidth, docCW: document.documentElement.clientWidth, secs, tags, types }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-sheet-layout: {text}")


def judge(failures, key, st):
    check(failures, st["sw"] <= st["cw"], f"{key}: the sheet does not scroll sideways: scrollWidth {st['sw']} clientWidth {st['cw']}")
    check(failures, st["docSW"] <= st["docCW"], f"{key}: the page does not scroll sideways: {st['docSW']} > {st['docCW']}")
    sh, secs = st["sheet"], st["secs"]
    check(failures, len(secs) == 8, f"{key}: eight sections: {len(secs)}")
    out = [s["id"] for s in secs if s["l"] < sh["l"] - 0.5 or s["r"] > sh["r"] + 0.5]
    check(failures, not out, f"{key}: every section lies inside the sheet (left and right): {out}")
    left = secs[0]["l"] if secs else 0
    check(failures, all(abs(s["l"] - left) <= 0.5 for s in secs), f"{key}: one column, every section's left edge the first one's: {[round(s['l'], 1) for s in secs]}")
    shared = [(a["id"], b["id"]) for i, a in enumerate(secs) for b in secs[i + 1:] if a["t"] < b["b"] - 0.5 and b["t"] < a["b"] - 0.5]
    check(failures, not shared, f"{key}: no two sections share a row: {shared}")
    tags = st["tags"]
    check(failures, sorted({t["kind"] for t in tags}) == sorted(KINDS), f"{key}: every transition kind on the sheet: {sorted({t['kind'] for t in tags})}")
    outside = [(t["kind"], round(t["r"]), round(t["sec"]["r"])) for t in tags if not t["sec"] or t["l"] < t["sec"]["l"] - 0.5 or t["r"] > t["sec"]["r"] + 0.5]
    check(failures, not outside, f"{key}: every transition tag lies inside its section: {outside}")
    broken = [(t["kind"], t["label"], t["labelBoxes"], round(t["labelH"], 1)) for t in tags if t["labelBoxes"] != 1 or t["labelH"] > t["labelLH"] * 1.3]
    check(failures, not broken, f"{key}: every kind label on one line: {broken}")
    outside = [(t["kind"], round(t["r"]), round(t["sec"]["r"])) for t in st["types"] if not t["sec"] or t["r"] > t["sec"]["r"] + 0.5]
    check(failures, len(st["types"]) == len(TYPES) and not outside, f"{key}: every type cell lies inside its section: {outside}")


async def run_spec_sheet_layout(pw, out, failures, Server, before=False):
    name = "spec-sheet-layout-before" if before else "spec-sheet-layout"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    path = S.write(scenario(), out / "spec-sheet-layout.jsonl")
    srv = Server(scenario=path)
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    res: dict = {}
    t0 = time.monotonic()
    try:
        step(srv, "start")
        for width, opts in (("1440", DESKTOP), ("390", PHONE)):
            page = await new_page(browser, watch, f"{name}-{width}", color_scheme="light", **opts)
            await page.goto(srv.url + "/")
            await ready(page)
            await page.wait_for_function("() => window.__dbg.model().specs.length === 1", timeout=20000)
            await page.evaluate("() => window.scrollTo(0, 0)")
            await page.click("#btn-specboard")
            await page.wait_for_function("() => { const el = document.getElementById('wb'); return !el.hidden && el.classList.contains('show'); }")
            await page.click('.ov-card[data-idx="0"]')
            await page.wait_for_function("() => document.querySelectorAll('#wb-code section.sc').length === 8 && document.querySelectorAll('#wb-code [data-tk]').length === 8", timeout=20000)
            await page.wait_for_timeout(700)
            await page.evaluate("() => document.getElementById('wb-sec-5').scrollIntoView({ block: 'start' })")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(out / f"{'before' if before else 'after'}-transitions-{width}.png"))
            if not before:
                st = res[width] = await page.evaluate(STATE_JS)
                judge(failures, width, st)
            await page.close()
        if not before:
            check(failures, not watch.console and not watch.foreign, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
    except Exception as e:
        failures.append(f"spec-sheet-layout: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.stop()
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
