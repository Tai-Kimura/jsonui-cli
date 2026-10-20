"""The spec sheet's 構造 shows the Layout's nesting (ticket 2026-10-20-jui-viz-spec-structure-shows-no-nesting).

The real `jui viz serve` in a throwaway HOME on a free port, one session in a real JsonUI project made here with
three specs: 項目の詳細 (the requester's item_detail shape: five levels, siblings at each, an id-less
View), 深い入れ子 (a chain twelve levels deep with a sibling at every level) and 一覧つき (structure.components listed,
nested by structure.layout). On each sheet's 構造:

- the list: each row indented by its depth (14 px a level), the depth the fixture's tree gives (worked out here from
  the fixture, not read back from the page), with its tree lines (├ for a later sibling, └ for the last, │ through);
- the phone frame: a box per row, each child's box inside its parent's box (the DOM and the rectangles), siblings
  apart, and the padding cap (6 px at depths 0–2, 2 px at 3–5, none from 6): no box set in further than the cap,
  the deepest box still wide enough to read.

Pictures of 項目の詳細's 構造 (light). `python spec_nest.py --out DIR --jt OTHER_CHECKOUT --shots-only` takes the
same picture from another checkout's jui_tools (the before picture), under the machine's e2e lock.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-000000000611"
STEP = 14                    # TREE_STEP in 50-panel.js
CAP = lambda depth: 6 if depth < 3 else 2 if depth < 6 else 0   # noqa: E731  WF_PAD in 50-panel.js


def _v(kind, ident=None, kids=None, key="child"):
    node = {"type": kind}
    if ident:
        node["id"] = ident
    if kids is not None:
        node[key] = kids
    return node


DETAIL = _v("SafeAreaView", "root_view", [
    _v("View", "loading_container", [_v("Indicator", "loading_indicator")]),
    _v("View", "empty_container", [_v("Label", "select_record_label")]),
    _v("View", "load_error_container", [_v("Label", "load_error_label"), _v("Button", "load_retry_button")]),
    _v("View", "content_container", [
        _v("View", "style_a_container"), _v("View", "style_b_container"),
        _v("View", "add_item_dock", _v("Button", "add_item_button")),
        _v("View", "promo_dock", [
            _v("View", None, [_v("Image", "promo_dock_lock_icon"), _v("Label", "promo_dock_label")], key="children"),
            _v("Button", "promo_dock_button")], key="children")])])


def _deep(level=0, last=11):
    kids = [_v("Label", f"note_{level}")]
    if level < last:
        kids.append(_deep(level + 1, last))
    return _v("View", f"box_{level}", kids)


DEEP = _deep()
LISTED = {"components": [{"type": "View", "id": "form_root", "description": "画面"}, {"type": "View", "id": "form", "description": "フォーム"},
                         {"type": "TextField", "id": "name_input", "description": "名前"}, {"type": "Label", "id": "hint", "description": "説明"},
                         {"type": "Button", "id": "save_button", "description": "保存"}],
          "layout": {"root": "form_root", "children": [{"id": "form", "children": ["name_input", "hint"]}, "save_button"]}}


def expected(tree) -> list[dict]:
    """The fixture's rows, depth-first: id (or type), depth, parent row, whether a later sibling follows."""
    rows: list[dict] = []

    def walk(node, depth, parent):
        me = len(rows)
        rows.append({"name": node.get("id") or node["type"], "depth": depth, "parent": parent, "later": False})
        kids = node.get("child", node.get("children"))
        kids = [kids] if isinstance(kids, dict) else (kids or [])
        idxs = []
        for k in kids:
            idxs.append(len(rows))
            walk(k, depth + 1, me)
        for i in idxs[:-1]:
            rows[i]["later"] = True

    walk(tree, 0, None)
    return rows


def expected_listed() -> list[dict]:
    rows = [{"name": "form_root", "depth": 0, "parent": None, "later": False}, {"name": "form", "depth": 1, "parent": 0, "later": True},
            {"name": "name_input", "depth": 2, "parent": 1, "later": True}, {"name": "hint", "depth": 2, "parent": 1, "later": False},
            {"name": "save_button", "depth": 1, "parent": 0, "later": False}]
    return rows


def spec(name, display, layout_file=None, structure=None):
    return {"type": "screen_spec", "version": "1.0",
            "metadata": {"name": name, "displayName": display, "description": "d", "platforms": ["ios"], **({"layoutFile": layout_file} if layout_file else {})},
            "structure": structure or {"components": [], "layout": {}}}


STATE_JS = """() => { const sec = document.getElementById('wb-sec-1'); if (!sec) return null;
  const R = (el) => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const rows = [...sec.querySelectorAll('ul.rows > li')].map((li) => {
    const tp = li.querySelector('.tp'), cells = [...li.querySelectorAll('.tg i')];
    return { id: (li.querySelector('.id') || {}).textContent || '', indent: tp && li.children[1] ? tp.getBoundingClientRect().left - li.children[1].getBoundingClientRect().left : null,
      cells: cells.map((i) => i.className.replace('g-', '')),
      drawn: cells.map((i) => { const b = getComputedStyle(i, '::before'), a = getComputedStyle(i, '::after');
        return [parseFloat(b.borderLeftWidth) || 0, b.content !== 'none' ? 1 : 0, parseFloat(a.borderTopWidth) || 0, a.content !== 'none' ? 1 : 0]; }) }; });
  const boxes = [...sec.querySelectorAll('.wf-phone [data-wf]')].map((el) => {
    const up = el.parentElement.closest('[data-wf]'), cs = getComputedStyle(el);
    return { idx: +el.dataset.wf, parent: up ? +up.dataset.wf : null, rect: R(el), padL: parseFloat(cs.paddingLeft), borderL: parseFloat(cs.borderLeftWidth),
      label: (el.querySelector(':scope > .wf-id') || {}).textContent || '' }; });
  const phone = sec.querySelector('.wf-phone');
  return { rows, boxes, phone: phone ? R(phone) : null }; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-nest: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def judge(failures, tag, st, exp, min_inner=None):
    """The arms on one sheet's 構造 against the fixture's tree."""
    rows, boxes = st["rows"], st["boxes"]
    check(failures, [r["id"] for r in rows] == [e["name"] if e["name"][0].islower() else "" for e in exp],
          f"{tag}: the rows are the tree depth-first: {[r['id'] for r in rows]}")
    if len(rows) != len(exp):
        return
    indents = [None if r["indent"] is None else round(r["indent"], 1) for r in rows]   # from the row's text cell
    want = [e["depth"] * STEP for e in exp]
    check(failures, all(a is not None and abs(a - b) <= 1 for a, b in zip(indents, want)),
          f"{tag}: the list's indent is {STEP} px a level of the fixture's depth: got {indents} want {want}")
    # tree lines: one cell a level above the row, its own ├ / └, │ through for an ancestor with a later sibling
    want_cells = []
    for i, e in enumerate(exp):
        cells, p = [], e["parent"]
        chain = []
        while p is not None:
            chain.append(p)
            p = exp[p]["parent"]
        chain.reverse()                         # root … parent
        for anc in chain[1:]:                   # levels 1 … depth-1: the ancestor at that level
            cells.append("v" if exp[anc]["later"] else "e")
        if e["depth"] > 0:
            cells.append("t" if e["later"] else "l")
        want_cells.append(cells)
    got_cells = [r["cells"] for r in rows]
    check(failures, got_cells == want_cells, f"{tag}: the tree lines: got {got_cells} want {want_cells}")
    drawn_ok = all((c in ("v", "t", "l")) <= (d[0] > 0 and d[1] == 1) and (c in ("t", "l")) <= (d[2] > 0 and d[3] == 1)
                   for r in rows for c, d in zip(r["cells"], r["drawn"]))
    check(failures, drawn_ok and any(r["cells"] for r in rows), f"{tag}: the tree lines are drawn (a border on │ ├ └, the ─ of ├ └): {[r['drawn'] for r in rows][:6]}")
    # the phone frame
    check(failures, sorted(b["idx"] for b in boxes) == list(range(len(exp))), f"{tag}: a box per row: {[b['idx'] for b in boxes]}")
    by = {b["idx"]: b for b in boxes}
    if len(by) != len(exp):
        return
    check(failures, [by[i]["parent"] for i in range(len(exp))] == [e["parent"] for e in exp],
          f"{tag}: each box sits in its parent's box (DOM): {[by[i]['parent'] for i in range(len(exp))]}")
    outside = []
    for i, e in enumerate(exp):
        c = by[i]["rect"]
        if e["parent"] is None:
            p = st["phone"]
        else:
            p = by[e["parent"]]["rect"]
        if not (c[0] >= p[0] + 0.5 and c[1] >= p[1] + 0.5 and c[2] <= p[2] - 0.5 and c[3] <= p[3] - 0.5):
            outside.append((e["name"], c, p))
    check(failures, not outside, f"{tag}: every box lies inside its parent's (rectangles): {outside[:3]}")
    overlap = []
    for i, a in enumerate(exp):
        for j in range(i + 1, len(exp)):
            if exp[j]["parent"] == a["parent"]:
                r1, r2 = by[i]["rect"], by[j]["rect"]
                if r1[0] < r2[2] and r2[0] < r1[2] and r1[1] < r2[3] and r2[1] < r1[3]:
                    overlap.append((a["name"], exp[j]["name"]))
    check(failures, not overlap, f"{tag}: siblings do not overlap: {overlap[:3]}")
    # the cap: a child set in from its parent's box by the parent's border and at most CAP(parent depth)
    over = []
    for i, e in enumerate(exp):
        if e["parent"] is None:
            continue
        p = by[e["parent"]]
        inset = by[i]["rect"][0] - p["rect"][0]
        if inset > p["borderL"] + CAP(exp[e["parent"]]["depth"]) + 0.5 or p["padL"] > CAP(exp[e["parent"]]["depth"]) + 0.01:
            over.append((e["name"], round(inset, 1), p["padL"], exp[e["parent"]]["depth"]))
    check(failures, not over, f"{tag}: no box set in further than the padding cap: {over[:4]}")
    if min_inner:
        deepest = max(range(len(exp)), key=lambda i: exp[i]["depth"])
        w = by[deepest]["rect"][2] - by[deepest]["rect"][0]
        check(failures, w >= min_inner, f"{tag}: the deepest box (depth {exp[deepest]['depth']}) is {w:.0f} px wide, at least {min_inner}")
    return indents


async def run_spec_nest(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "spec-nest-before" if shots_only else "spec-nest"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    proj = home / "work" / "nest-app"
    (proj / "docs" / "screens" / "json").mkdir(parents=True, exist_ok=True)
    (proj / "docs" / "screens" / "layouts").mkdir(parents=True, exist_ok=True)
    (proj / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts"}))
    for stem, sp, layout in (("detail", spec("Detail", "項目の詳細（入れ子の見本）", "detail"), DETAIL),
                             ("deep", spec("Deep", "深い入れ子", "deep"), DEEP),
                             ("listed", spec("Listed", "一覧つき", structure=LISTED), None)):
        (proj / "docs" / "screens" / "json" / f"{stem}.spec.json").write_text(json.dumps(sp, ensure_ascii=False))
        if layout:
            (proj / "docs" / "screens" / "layouts" / f"{stem}.json").write_text(json.dumps(layout, ensure_ascii=False))
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(**payload):
        body = {"session_id": SID, "cwd": str(proj), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

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
        watch = Watch(origin=url)
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(hook_event_name="SessionStart", source="startup")
        await page.click("#spec-filter [data-f='all']")
        await wait(page, "() => document.querySelectorAll('#spec-list .spec-row').length >= 3", timeout=30000, label="the three specs listed")
        await page.click("#spec-list .spec-row:has-text('項目の詳細')")
        detail = expected(DETAIL)
        await wait(page, "(n) => document.querySelectorAll('#wb-sec-1 ul.rows > li').length === n", arg=len(detail), timeout=30000, label="項目の詳細's 構造")
        await page.wait_for_timeout(800)
        await page.evaluate("() => document.getElementById('wb-sec-1').scrollIntoView({ block: 'start' })")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / (("before" if shots_only else "after") + "-structure.png")))
        if shots_only:
            return
        st = res["detail"] = await page.evaluate(STATE_JS)
        res["detailIndents"] = judge(failures, "項目の詳細", st, detail, min_inner=100)

        await page.click("#wb-side-list [data-idx]:has-text('深い入れ子')")
        deep = expected(DEEP)
        await wait(page, "(n) => document.querySelectorAll('#wb-sec-1 ul.rows > li').length === n", arg=len(deep), timeout=20000, label="深い入れ子's 構造")
        await page.wait_for_timeout(500)
        st = res["deep"] = await page.evaluate(STATE_JS)
        judge(failures, "深い入れ子", st, deep, min_inner=70)
        await page.evaluate("() => document.getElementById('wb-sec-1').scrollIntoView({ block: 'start' })")
        await page.screenshot(path=str(out / "after-structure-deep.png"))

        await page.click("#wb-side-list [data-idx]:has-text('一覧つき')")
        listed = expected_listed()
        await wait(page, "() => [...document.querySelectorAll('#wb-sec-1 ul.rows > li .id')].map((x) => x.textContent).join(',') === 'form_root,form,name_input,hint,save_button'",
                   timeout=20000, label="一覧つき's 構造")
        await page.wait_for_timeout(500)
        st = res["listed"] = await page.evaluate(STATE_JS)
        judge(failures, "一覧つき", st, listed)

        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"spec-nest: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    import argparse
    import asyncio

    from playwright.async_api import async_playwright

    import e2e_lock

    ap = argparse.ArgumentParser(description="the 構造 picture from another checkout (the before picture)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jt", required=True, help="that checkout's jui_tools")
    ap.add_argument("--shots-only", action="store_true")
    a = ap.parse_args()
    e2e_lock.hold()
    fails: list = []

    async def go():
        async with async_playwright() as pw:
            await run_spec_nest(pw, a.out, fails, jt=a.jt, shots_only=a.shots_only)

    asyncio.run(go())
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)
