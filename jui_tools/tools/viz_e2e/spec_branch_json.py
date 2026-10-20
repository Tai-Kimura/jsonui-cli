"""分岐's condition and result as formatted JSON (ticket 2026-10-20-jui-viz-spec-branch-json-formatted; requester
10-20: 「分岐テストはjson formatterでフォーマットした感じに表示できない？」).

fake_server.py with one spec whose branches carry when / then the way sheet.build_doc sends them (an object or an
array as the spec wrote it, anything else as text). At 1440 px and at 390 px:

  - an object is a pre whose text is JSON.stringify(v, null, 2) exactly (its lines and their leading spaces);
  - keys, strings, numbers and true / false / null each have their own class (and colour);
  - a value holding `<img src=x onerror=…>` is text: no img in the section, nothing ran;
  - a long line scrolls inside its block (the block's scrollWidth > clientWidth), the sheet never sideways;
  - over 12 lines the block is folded (shorter than its text) with a toggle that opens it (all of it shown);
  - a value that is not JSON (text, a number) stays the line of text it was: no pre, the text unchanged, one line at 1440 px.

Pictures of the 分岐 section at both widths.
"""

from __future__ import annotations

import json
import pathlib
import time

import scenarios as S
from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready
from live import step

W0 = {"data.noteText": "香りが開いた", "api.addNote": "default", "count": 3, "rate": -2.5, "ok": True, "gone": None}
T0 = {"toast": "保存しました", "dismiss": True}
W1 = {"data.noteText": "<img src=x onerror=\"window.__pwned=1\">"}
T2 = {"items": list(range(20))}
W3 = {"path": "/" + "very-long-segment-" * 30}
BRANCHES = [["onSave", W0, T0], ["onSave", W1, "テキストだけの結果"], ["onLoad", "空のとき", T2], ["onOpen", W3, "3"], ["onSave", "note", "通信が切れたとき"]]


def pretty(v) -> str:
    return json.dumps(v, indent=2, ensure_ascii=False)


def scenario(before=False):
    sheet = S.sheet_for("branch")
    # before: what the server sent until this change — every when / then as one line of JSON text (sheet._t)
    as_text = lambda v: v if isinstance(v, str) else " ".join(json.dumps(v, ensure_ascii=False).split())  # noqa: E731
    sheet["branches"] = [[m, as_text(w), as_text(t)] for m, w, t in BRANCHES] if before else BRANCHES
    P = [S.project("p-shop", "shop-app", 0)]
    sess = [S.session(S.S_A0, "a0", "p-shop", "shop-app", status="idle")]
    A = [S.agent(S.S_A0, "a0", S.S_A0, state="idle", act="待機")]
    specs = [S.spec("branch", items=[5, 6, 3, 4, 2, 2, 5])]
    return [{"sheets": {specs[0]["id"]: sheet}}, {"mark": "start"},
            S.slices(0, projects=P, sessions=sess, agents=A, specs=specs, server=S.server_slice()), {"mark": "end"}]


STATE_JS = """() => { const sec = document.getElementById('wb-sec-6'), sheet = document.getElementById('wb-code');
  const lines = (el) => { const rg = document.createRange(); rg.selectNodeContents(el); return new Set([...rg.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.top))).size; };
  const rows = [...sec.querySelectorAll('tbody tr')].map((tr) => [...tr.querySelectorAll('td')].slice(2).map((td) => {
    const pre = td.querySelector('pre'), box = td.querySelector('.bj'), btn = td.querySelector('.bj-more');
    return pre ? { pre: true, text: pre.textContent, classes: [...new Set([...pre.querySelectorAll('span')].map((s) => s.className))].sort(),
      sw: pre.scrollWidth, cw: pre.clientWidth, sh: pre.scrollHeight, ch: pre.clientHeight, folded: !!(box && box.classList.contains('bj-fold')), btn: btn ? btn.textContent : null }
      : { pre: false, text: td.textContent, lines: lines(td) }; }));
  return { rows, imgs: sec.querySelectorAll('img').length, elements: sec.querySelectorAll('.bj-pre *:not(span)').length, pwned: window.__pwned === undefined ? null : window.__pwned,
    sw: sheet.scrollWidth, cw: sheet.clientWidth, docSW: document.documentElement.scrollWidth, docCW: document.documentElement.clientWidth }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-branch-json: {text}")


def judge(failures, key, st):
    rows = st["rows"]
    check(failures, len(rows) == len(BRANCHES), f"{key}: a row per branch: {len(rows)}")
    if len(rows) != len(BRANCHES):
        return
    (w0, t0), (w1, t1), (w2, t2), (w3, t3), (n0, n1) = rows
    for name, got, v in (("W0", w0, W0), ("T0", t0, T0), ("W1", w1, W1), ("T2", t2, T2), ("W3", w3, W3)):
        check(failures, got["pre"] and got["text"] == pretty(v), f"{key}: {name} is JSON.stringify(v, null, 2) in a pre (lines and indentation): {got.get('text', '')[:120]!r}")
    check(failures, w0["pre"] and w0["classes"] == ["bj-key", "bj-lit", "bj-num", "bj-str"], f"{key}: keys, strings, numbers, true / false / null each their own class: {w0.get('classes')}")
    check(failures, st["imgs"] == 0 and st["elements"] == 0 and st["pwned"] is None, f"{key}: <img onerror> is text: imgs {st['imgs']} elements {st['elements']} ran {st['pwned']}")
    check(failures, w3["pre"] and w3["sw"] > w3["cw"], f"{key}: a long line scrolls inside its block: {w3.get('sw')} > {w3.get('cw')}")
    check(failures, st["sw"] <= st["cw"] and st["docSW"] <= st["docCW"], f"{key}: the sheet never sideways: {st['sw']} {st['cw']} {st['docSW']} {st['docCW']}")
    check(failures, t2["pre"] and t2["folded"] and t2["ch"] < t2["sh"] and t2["btn"] and "全部を見る" in t2["btn"], f"{key}: 22 lines folded with a toggle: {t2}")
    check(failures, w0["pre"] and not w0["folded"] and w0["btn"] is None, f"{key}: 8 lines not folded: {w0.get('folded')} {w0.get('btn')}")
    # not JSON: the plain text it was (no block, nothing added); one line where the column is wide enough (at 390 px a
    # narrow column wraps a sentence as it always did)
    for name, got, text in (("T1", t1, "テキストだけの結果"), ("W2", w2, "空のとき"), ("T3", t3, "3"), ("note", n1, "通信が切れたとき")):
        check(failures, not got["pre"] and got["text"] == text and (key != "1440" or got["lines"] == 1), f"{key}: {name}, not JSON, stays the one line of text: {got}")


async def run_spec_branch_json(pw, out, failures, Server, before=False):
    name = "spec-branch-json-before" if before else "spec-branch-json"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    path = S.write(scenario(before), out / "spec-branch-json.jsonl")
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
            await page.wait_for_function("(n) => document.querySelectorAll('#wb-code section.sc').length === 8 && document.querySelectorAll('#wb-sec-6 tbody tr').length === n", arg=len(BRANCHES), timeout=20000)
            await page.wait_for_timeout(700)
            await page.evaluate("() => document.getElementById('wb-sec-6').scrollIntoView({ block: 'start' })")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(out / f"{'before' if before else 'after'}-branches-{width}.png"))
            if not before:
                st = res[width] = await page.evaluate(STATE_JS)
                judge(failures, width, st)
                await page.click("#wb-sec-6 .bj-more")
                await page.wait_for_timeout(300)
                opened = res[f"{width}-open"] = await page.evaluate(STATE_JS)
                t2 = opened["rows"][2][1] if len(opened["rows"]) > 2 else {}
                check(failures, t2.get("pre") and t2["ch"] >= t2["sh"] and t2["btn"] == "畳む", f"{width}: the toggle opens all of it: {t2}")
            await page.close()
        if not before:
            check(failures, not watch.console and not watch.foreign, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
    except Exception as e:
        failures.append(f"spec-branch-json: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.stop()
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
