"""The spec sheet's colours, end to end (2.3.5, requester 10-19: "遷移のところの遷移先が白の太字見にくい 色少しつけてみやすく
してほしい。あと状態変数の型も型ごとに色分けできない？").

fake_server.py with one JsonUI project whose spec sheet has a transition of every kind (by its type / method, or by
the words of its destination) and a state variable of every type kind. In light and dark:

  - every transition kind and every type kind is on the sheet, each with its own colour (no two kinds alike), and the
    same type has the same colour wherever it appears;
  - every pairing is 4.5:1 or more, measured from the computed colours: a tag's text against its own ground; a type
    against the ground it is drawn on and against the highlighted rows' grounds;
  - the kind is in the tag as text, the type is the cell's text (never colour alone);
  - the 「?」 dialog's legend lists every kind and every type kind, in the very colours the sheet uses (one source),
    and passes the same contrast.
"""

from __future__ import annotations

import json
import pathlib
import time

import scenarios as S
from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from live import step

KINDS = ["none", "external", "back", "replace", "modal", "push", "screen", "other"]
TYPES = ["optional", "array", "string", "bool", "number", "color", "custom"]
TRANSITIONS = [["保存しない", "遷移なし（画面内）", ""], ["ヘルプ", "外部ブラウザ（https://example.invalid）", ""],
               ["戻るボタン", "前の画面に戻る（pop）", ""], ["ログアウト", "Login", "replace"], ["フィルタ", "FilterSheet", "sheet"],
               ["詳細を見る", "Detail", "push"], ["何か", "Somewhere", ""], ["閉じる", "Home", "dismiss"], ["地図を開く", "地図アプリ", ""],
               # the type decides over another kind's word in the destination (dd, from the requester's specs)
               ["店舗を編集", "StoreEditSheetView", "navigationDestination"], ["ホームへ", "HomeViewController（SS MAP表示）", "delegate(switchToHome)"],
               ["詳細を出す", "遷移なし（同画面上に詳細を sheet 表示）", "sheet"],
               # no kind written: a named screen is 画面へ; a destination that names nothing is grey (the ruling, 10-19)
               ["一覧から選ぶ", "AdminItemDetail（/admin/items/{id}）", ""], ["あとで決める", "未定", ""], ["空", "", ""], ["記号だけ", "?", ""]]
UI_VARIABLES = [["title", "String", '""'], ["subtitle", "string", '""'], ["isOn", "Bool", "false"], ["count", "Int", "0"],
                ["rate", "Double", "0"], ["tint", "Color", "#fff"], ["items", "[Item]", "[]"], ["error", "String?", "nil"],
                ["onTap", "(() -> Void)?", "nil"], ["mode", "Visibility", ".visible"]]
WANT_TYPE = {"String": "string", "string": "string", "Bool": "bool", "Int": "number", "Double": "number", "Color": "color",
             "[Item]": "array", "String?": "optional", "(() -> Void)?": "optional", "Visibility": "custom"}
WANT_KIND = ["none", "external", "back", "replace", "modal", "push", "screen", "back", "external", "push", "screen", "modal", "screen", "other", "other", "other"]


def scenario():
    sheet = S.sheet_for("colors")
    sheet["transitions"] = TRANSITIONS
    sheet["uiVariables"] = UI_VARIABLES
    P = [S.project("p-shop", "shop-app", 0)]
    sess = [S.session(S.S_A0, "a0", "p-shop", "shop-app", status="idle")]
    A = [S.agent(S.S_A0, "a0", S.S_A0, state="idle", act="待機")]
    specs = [S.spec("colors", items=[5, 6, 10, 4, 2, 9, 3])]
    return [{"sheets": {specs[0]["id"]: sheet}}, {"mark": "start"},
            S.slices(0, projects=P, sessions=sess, agents=A, specs=specs, server=S.server_slice()), {"mark": "end"}]


# The colour a person sees behind an element: its own ground, else the first opaque ground up the tree.
MEASURE = """(sel) => {
  const rgb = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const ground = (el) => { for (let e = el; e; e = e.parentElement) { const c = rgb(getComputedStyle(e).backgroundColor); if (c && c.a > 0.99) return c; } return { r: 255, g: 255, b: 255, a: 1 }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = (c) => '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
  const rowGrounds = ['--wb-violet-bg', '--wb-blue-bg', '--wb-green-bg', '--wb-card', '--panel'].map((v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim())
    .map((v) => { const d = document.createElement('span'); d.style.color = v; document.body.append(d); const c = rgb(getComputedStyle(d).color); d.remove(); return c; }).filter(Boolean);
  return [...document.querySelectorAll(sel)].map((el) => {
    const fg = rgb(getComputedStyle(el).color), bg = ground(el), kind = el.dataset.tk || el.dataset.ty;
    const label = el.querySelector('.tk-k') ? el.querySelector('.tk-k').textContent.trim() : null;
    const worst = el.dataset.ty ? Math.min(ratio(fg, bg), ...rowGrounds.map((g) => ratio(fg, g))) : ratio(fg, bg);
    return { kind, fg: hex(fg), bg: hex(bg), ratio: +ratio(fg, bg).toFixed(2), worst: +worst.toFixed(2), label, text: el.textContent.trim().slice(0, 40) };
  });
}"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-colors: {text}")


async def run_spec_colors(pw, out, failures, Server):
    out = pathlib.Path(out) / "spec-colors"
    out.mkdir(parents=True, exist_ok=True)
    path = S.write(scenario(), out / "spec-colors.jsonl")
    srv = Server(scenario=path)
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    res: dict = {}
    t0 = time.monotonic()
    try:
        step(srv, "start")
        for scheme in ("light", "dark"):
            r = res[scheme] = {}
            page = await new_page(browser, watch, f"spec-colors-{scheme}", color_scheme=scheme, **DESKTOP)
            await page.goto(srv.url + "/")
            await ready(page)
            await page.wait_for_function("() => window.__dbg.model().specs.length === 1", timeout=20000)
            await page.click("#btn-specboard")
            await page.wait_for_function("() => { const el = document.getElementById('wb'); return !el.hidden && el.classList.contains('show'); }")
            await page.click('.ov-card[data-idx="0"]')
            await page.wait_for_function("() => document.querySelectorAll('#wb-code section.sc').length === 8 && document.getElementById('wb-code').textContent.includes('Visibility')", timeout=20000)
            await page.wait_for_timeout(600)
            tags = r["tags"] = await page.evaluate(MEASURE, "#wb-code [data-tk]")
            types = r["types"] = await page.evaluate(MEASURE, "#wb-code [data-ty]")
            # kinds by row, as the spec said
            check(failures, [t["kind"] for t in tags] == WANT_KIND, f"{scheme}: each transition gets its kind: {[t['kind'] for t in tags]}")
            check(failures, [t["kind"] for t in types] == [WANT_TYPE[v[1]] for v in UI_VARIABLES], f"{scheme}: each type gets its kind: {[t['kind'] for t in types]}")
            # one colour per kind, no two kinds alike, the same type the same colour
            by_kind = {}
            for t in tags:
                by_kind.setdefault(t["kind"], set()).add((t["fg"], t["bg"]))
            check(failures, all(len(v) == 1 for v in by_kind.values()) and len({next(iter(v)) for v in by_kind.values()}) == len(KINDS),
                  f"{scheme}: one colour per transition kind, all {len(KINDS)} different: {by_kind}")
            by_type = {}
            for t in types:
                by_type.setdefault(t["kind"], set()).add(t["fg"])
            check(failures, all(len(v) == 1 for v in by_type.values()) and len({next(iter(v)) for v in by_type.values()}) == len(TYPES),
                  f"{scheme}: one colour per type kind (the same type alike), all {len(TYPES)} different: {by_type}")
            # contrast
            low = [t for t in tags + types if t["worst"] < 4.5]
            r["minRatio"] = min(t["worst"] for t in tags + types) if tags + types else None
            check(failures, not low, f"{scheme}: every colour 4.5:1 or more against its ground (types also against the highlighted rows): {low}")
            # the kind in text, the type as text
            check(failures, all(t["label"] for t in tags), f"{scheme}: each tag says its kind in text: {[t['label'] for t in tags]}")
            check(failures, [t["text"] for t in types] == [v[1] for v in UI_VARIABLES], f"{scheme}: each type cell is the type's text: {[t['text'] for t in types]}")
            await page.evaluate("() => document.getElementById('wb-sec-2').scrollIntoView({ block: 'start' })")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(out / f"sheet-state-{scheme}.png"))
            await page.evaluate("() => document.getElementById('wb-sec-5').scrollIntoView({ block: 'start' })")
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(out / f"sheet-transitions-{scheme}.png"))
            # the legend in the 「?」: every kind and type, the same colours, the same contrast
            await page.keyboard.press("Escape")
            await page.wait_for_function("() => document.getElementById('wb').hidden")
            await page.click("#spec-help-panel")
            await page.wait_for_function("() => !!document.querySelector('#spec-help [role=\"dialog\"]')")
            lk = r["legendKinds"] = await page.evaluate(MEASURE, "#spec-help [data-tk]")
            lt = r["legendTypes"] = await page.evaluate(MEASURE, "#spec-help [data-ty]")
            check(failures, [x["kind"] for x in lk] == KINDS and [x["kind"] for x in lt] == TYPES,
                  f"{scheme}: the legend lists every kind and type: {[x['kind'] for x in lk]} {[x['kind'] for x in lt]}")
            same = all(by_kind.get(x["kind"]) == {(x["fg"], x["bg"])} for x in lk) and all(by_type.get(x["kind"]) == {x["fg"]} for x in lt)
            r["legendSame"] = same
            check(failures, same, f"{scheme}: the legend shows the colours the sheet uses: {lk} {lt}")
            labels = {t["kind"]: t["label"] for t in tags}
            check(failures, all(labels.get(x["kind"]) == x["label"] for x in lk), f"{scheme}: the legend's kind words are the tags' words: {[(x['kind'], x['label']) for x in lk]}")
            low = [x for x in lk + lt if x["ratio"] < 4.5]
            check(failures, not low, f"{scheme}: the legend's colours 4.5:1 or more on the dialog: {low}")
            await page.screenshot(path=str(out / f"legend-{scheme}.png"))
            await page.close()
        for line in watch.console:
            failures.append(f"spec-colors: console: {line}")
        for u in watch.foreign:
            failures.append(f"spec-colors: request outside the server: {u}")
    except Exception as e:
        failures.append(f"spec-colors: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.stop()
    (out / "spec-colors-results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(f"  spec-colors: {time.monotonic() - t0:.0f}s", flush=True)
