"""The labels of the 応答の履歴 stay on one line (2.3.4, requester 10-19: "時間の表示が崩れてる"; the screenshot: the time
as 「09」「:4」「7」, 「Bash」 one letter a line).

On the stage of hist_wide.py, A's transcript has every kind of label beside a long body: a message from another session
(a long sender, a long text), Bash with a very long command, a tool with a long name and an error, a Bash call still
running, the harness's long note, long instructions. In three layouts — the card's width (1440 px), the wide view and
390 px — light and dark, each KIND of label is measured on its own and must be present and one line (its box at most
one line high, and a Range over its text on one line):

  time (.h-at), tool (the tool's name), harness (its label), sender, err (エラー), run (結果待ち), who (依頼者 and time).

A long sender is cut with … rather than folded. A message from another session stacks its sender, its body and its
time top to bottom (issue #34), the body wrapping instead of cut to one line. Then the same in a squeezed pane (130 px wide), where the labels
together are wider than the row: without the guard on a kind, that kind folds there whatever the layout.
"""

from __future__ import annotations

import pathlib
import time

from common import PHONE, dump
from hist_wide import SETTLED, Stage, TO_END, check as _check, wait

KINDS = {"time": ".h-item .h-at", "tool": ".h-tool summary > b", "harness": ".h-harness summary > b", "sender": ".h-peer summary > b",
         "err": ".h-tool summary > .h-err", "run": ".h-tool summary > .h-run", "who": ".h-who"}
LABELS = """(kinds) => {
  const pane = document.querySelector('[data-rb-hist]');
  const out = {};
  for (const [kind, sel] of Object.entries(kinds)) {
    out[kind] = [...pane.querySelectorAll(sel)].filter((e) => e.textContent.trim()).map((e) => {
      const cs = getComputedStyle(e), r = document.createRange(); r.selectNodeContents(e);
      const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.5;
      // lines: a new line where a rect starts half a line below the last (a time in another font starts a pixel lower)
      const tops = [...r.getClientRects()].filter((x) => x.width > 0).map((x) => x.top).sort((a, b) => a - b);
      let lines = tops.length ? 1 : 0;
      for (let i = 1; i < tops.length; i++) if (tops[i] - tops[i - 1] > lh / 2) lines += 1;
      return { text: e.textContent.slice(0, 30), h: Math.round(e.getBoundingClientRect().height), lh: Math.round(lh), w: Math.round(e.getBoundingClientRect().width),
        lines, cut: e.scrollWidth > e.clientWidth + 1, ellipsis: cs.textOverflow === 'ellipsis' };
    });
  }
  return out;
}"""
PEER_STACK = """() => {
  const s = document.querySelector('[data-rb-hist] .h-peer summary');
  if (!s) return null;
  const box = (sel) => { const e = s.querySelector(sel); return e ? e.getBoundingClientRect() : null; };
  const who = box(':scope > b'), head = box(':scope > .h-head'), at = box(':scope > .h-at');
  const lh = parseFloat(getComputedStyle(s.querySelector(':scope > .h-head')).lineHeight) || 18;
  return who && head && at && { whoBottom: Math.round(who.bottom), headTop: Math.round(head.top), headBottom: Math.round(head.bottom),
    atTop: Math.round(at.top), headLines: Math.round(head.height / lh) };
}"""
SQUEEZE = "(on) => { const p = document.querySelector('[data-rb-hist]'); p.style.width = on ? '130px' : ''; p.style.justifySelf = on ? 'start' : ''; }"


def check(failures, cond, text):
    _check(failures, cond, text, "hist-labels")


def judge(failures, where, got):
    for kind in KINDS:
        items = got.get(kind) or []
        bad = [x for x in items if x["lines"] != 1 or x["h"] > x["lh"] * 1.3 + 1]
        check(failures, items and not bad, f"{where}: {kind} labels on one line ({len(items)} measured): {bad[:3] or items[:1]}")
        if kind == "sender":
            check(failures, all(not x["cut"] or x["ellipsis"] for x in items), f"{where}: a long sender is cut with …, not folded: {items[:2]}")


async def measure(page, failures, where, res):
    res[where] = got = await page.evaluate(LABELS, KINDS)
    judge(failures, where, got)
    res[f"{where}-peer"] = st = await page.evaluate(PEER_STACK)
    check(failures, st and st["whoBottom"] <= st["headTop"] + 1 and st["headBottom"] <= st["atTop"] + 1 and st["headLines"] >= 2,
          f"{where}: another session's message reads sender, body (wrapped), time top to bottom: {st}")
    await page.evaluate(SQUEEZE, True)
    await page.wait_for_timeout(150)
    res[f"{where}-squeezed"] = got = await page.evaluate(LABELS, KINDS)
    judge(failures, f"{where}, squeezed to 130 px", got)
    await page.evaluate(SQUEEZE, False)


async def shot(page, path):
    await page.evaluate("() => { const t = document.querySelector('[data-rb-hist] .h-peer'); if (t) t.scrollIntoView({ block: 'start' }); }")
    await page.wait_for_timeout(200)
    await page.screenshot(path=str(path))


async def run_hist_labels(pw, out, failures):
    t0 = time.monotonic()
    st = Stage()
    res: dict = {}
    try:
        await st.start(pw, out, "hist-labels")
        out = st.out
        page = await st.page("hist-labels")
        await st.open_a(page)
        await page.evaluate(TO_END)
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(400)
            await measure(page, failures, f"card width {scheme}", res)
            await shot(page, out / f"labels-card-{scheme}.png")
        await page.emulate_media(color_scheme="light")
        if await page.locator("#rb [data-rb-wide]").count():
            await page.click("#rb [data-rb-wide]")
            await wait(page, SETTLED, label="wide")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(400)
                await measure(page, failures, f"wide {scheme}", res)
                await shot(page, out / f"labels-wide-{scheme}.png")
            await page.keyboard.press("Escape")
        await page.close()
        for scheme in ("light", "dark"):
            ph = await st.page(f"hist-labels-phone-{scheme}", **dict(PHONE, color_scheme=scheme))
            await st.open_a(ph)
            await ph.wait_for_timeout(400)
            await measure(ph, failures, f"390 px {scheme}", res)
            await shot(ph, out / f"labels-390-{scheme}.png")
            await ph.close()
    except Exception as e:
        failures.append(f"hist-labels: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, "hist-labels")
        print(f"  hist-labels: {time.monotonic() - t0:.0f}s", flush=True)
        if hasattr(st, "out"):
            (pathlib.Path(st.out) / "hist-labels-results.json").write_text(dump(res) + "\n")
