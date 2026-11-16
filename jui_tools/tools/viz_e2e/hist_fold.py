"""A fold in the 応答の履歴 closes on a click in its opened body (2.3.6; requester 10-20: 「長い分の折りたたみの開閉は
テキスト部分クリックでできるようにして、そうしないと開くと閉じづらい」; ticket 2026-10-20-jui-viz-history-fold-toggle-by-text).

On the stage of hist_wide.py (A's transcript: a long message from another session, the harness's long note, Bash
with a very long command, a tool with a long name), in A's 応答の履歴:

  - body click: the long message opened, the pane scrolled so its head is above the top, a click on its text closes
    it and the head is back in view; the same for the harness's note and for a tool's IN code (its text, not its
    scroll bar);
  - a selection keeps it open: text dragged over, a word double-clicked, a selection extended with Shift + click
    (one click, no drag: only the selection says it is not a closing click);
  - something with its own action keeps it open: a link and a picture's thumbnail (planted in the opened body: the
    rows that fold carry neither today), a table that scrolls sideways (planted too), the whole-text tag (the real
    one, over a cut tool name);
  - a row that does not fold (the assistant's answer) is unaffected: no fold changes, the pane does not move;
  - the keyboard: Enter on the summary still opens and closes it;
  - the pane's focus from the click shows no whole-text tag over the pointer (ticket
    2026-10-20-jui-viz-fulltext-tag-pops-on-mouse-focus: the tag took the click).

A negative arm (it stays open) waits on the page's own clock past the double-click window (HIST_DBL_MS) with
waits.until, never on the wall clock of the test. Screenshots (light and dark) are for the eye.
"""

from __future__ import annotations

import pathlib
import time

from common import dump
from hist_wide import Stage, check as _check
from waits import until

SUITE = "hist-fold"
PANE = "[data-rb-hist]"
PEER, HARNESS, TOOL = f"{PANE} details.h-peer", f"{PANE} details.h-harness", f"{PANE} details.h-tool"
OPEN = "(sel) => { const d = document.querySelector(sel); return !!d && d.open; }"
CLOSED = "(sel) => { const d = document.querySelector(sel); return !!d && !d.open; }"
# the head (summary) inside the pane's visible box?
HEAD_IN_VIEW = """(sel) => { const d = document.querySelector(sel), pane = document.querySelector('[data-rb-hist]');
  const s = d.querySelector('summary').getBoundingClientRect(), p = pane.getBoundingClientRect();
  return { top: Math.round(s.top), paneTop: Math.round(p.top), inView: s.top >= p.top - 1 && s.bottom <= p.bottom + 1 }; }"""
# put the head above the pane's top, the body still in view
HEAD_ABOVE = """(sel) => { const d = document.querySelector(sel), pane = document.querySelector('[data-rb-hist]');
  const s = d.querySelector('summary');
  pane.scrollTop += s.getBoundingClientRect().top - pane.getBoundingClientRect().top + s.offsetHeight + 2;   // just above
  return Math.round(s.getBoundingClientRect().top - pane.getBoundingClientRect().top); }"""
PAST = "(t) => performance.now() > t"   # the page's own clock


def check(failures, cond, text):
    _check(failures, cond, text, SUITE)


async def opened(page, sel):
    if not await page.evaluate(OPEN, sel):
        await page.evaluate("(sel) => document.querySelector(sel).querySelector('summary').scrollIntoView({ block: 'center' })", sel)
        await page.click(f"{sel} > summary")
    await until(page, OPEN, f"{sel} open", arg=sel)


async def still_open(page, sel, name):
    """Past the double-click window (and a frame), is it still open?"""
    t = await page.evaluate("() => performance.now() + 600")
    await until(page, PAST, f"{name}: the window passes", arg=t)
    return await page.evaluate(OPEN, sel)


async def body_click(page, sel, inner, failures, name):
    await opened(page, sel)
    above = await page.evaluate(HEAD_ABOVE, sel)
    box = await page.locator(f"{sel} {inner}").first.bounding_box()
    pane = await page.locator(PANE).bounding_box()
    top, bottom = max(box["y"], pane["y"]), min(box["y"] + box["height"], pane["y"] + pane["height"])
    check(failures, bottom - top > 4, f"{name}: its body is in view to click: {box} in {pane}")
    await page.mouse.click(box["x"] + min(40, box["width"] / 3), (top + bottom) / 2)
    tag = await page.evaluate("() => { const t = document.getElementById('fulltext'); return !!t && !t.hidden; }")
    check(failures, not tag, f"{name}: no whole-text tag pops up over the click (the pane's mouse focus)")
    await until(page, CLOSED, f"{name}: closed by a click in its body", arg=sel, why=f"() => document.querySelector('{sel}').open")
    head = await page.evaluate(HEAD_IN_VIEW, sel)
    check(failures, above < 0 and head["inView"], f"{name}: the head was above ({above}), after closing it is in view: {head}")
    return head


async def run_hist_fold(pw, out, failures):
    t0 = time.monotonic()
    st = Stage()
    res: dict = {}
    try:
        await st.start(pw, out, SUITE)
        out = st.out
        for scheme in ("light", "dark"):
            r = res[scheme] = {}
            page = await st.page(f"{SUITE}-{scheme}", color_scheme=scheme, viewport={"width": 1440, "height": 900})
            await st.open_a(page)

            # a click in the body closes it, the head back in view
            r["peer"] = await body_click(page, PEER, ".h-plain", failures, f"{scheme}: another session's message")
            r["harness"] = await body_click(page, HARNESS, ".h-plain", failures, f"{scheme}: the harness's note")
            tool = f"{PANE} details.h-tool:has(pre.h-code)"
            r["tool"] = await body_click(page, tool, "pre.h-code", failures, f"{scheme}: a tool's IN")

            # a selection keeps it open: a drag over the text, a double-click on a word
            await opened(page, PEER)
            await page.evaluate("(sel) => document.querySelector(sel).querySelector('.h-plain').scrollIntoView({ block: 'start' })", PEER)
            b = await page.locator(f"{PEER} .h-plain").bounding_box()
            pane = await page.locator(PANE).bounding_box()
            y0 = max(b["y"], pane["y"]) + 12
            await page.mouse.move(b["x"] + 20, y0)
            await page.mouse.down()
            await page.mouse.move(b["x"] + 220, y0 + 22, steps=8)
            await page.mouse.up()
            sel_text = await page.evaluate("() => String(window.getSelection()).length")
            r["dragSelect"] = {"selected": sel_text, "open": await still_open(page, PEER, f"{scheme}: drag")}
            check(failures, sel_text > 0 and r["dragSelect"]["open"], f"{scheme}: selecting by a drag keeps it open: {r['dragSelect']}")
            await page.evaluate("() => window.getSelection().removeAllRanges()")
            await page.mouse.dblclick(b["x"] + 60, y0)
            dbl = await page.evaluate("() => String(window.getSelection()).length")
            r["dblSelect"] = {"selected": dbl, "open": await still_open(page, PEER, f"{scheme}: double-click")}
            check(failures, dbl > 0 and r["dblSelect"]["open"], f"{scheme}: a double-click on a word keeps it open: {r['dblSelect']}")
            # a selection extended with Shift + click (no drag, one click): the click lands with text selected
            await page.evaluate("() => window.getSelection().removeAllRanges()")
            await page.mouse.click(b["x"] + 20, y0)
            await until(page, CLOSED, f"{scheme}: a plain click closes it (before the Shift arm)", arg=PEER)
            await opened(page, PEER)
            await page.evaluate("(sel) => document.querySelector(sel).querySelector('.h-plain').scrollIntoView({ block: 'start' })", PEER)
            b = await page.locator(f"{PEER} .h-plain").bounding_box()
            pane = await page.locator(PANE).bounding_box()
            y0 = max(b["y"], pane["y"]) + 12
            await page.evaluate("""(sel) => { const p = document.querySelector(sel).querySelector('.h-plain'), r = document.createRange();
              r.setStart(p.firstChild, 2); r.setEnd(p.firstChild, 4); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""", PEER)
            await page.keyboard.down("Shift")
            await page.mouse.click(b["x"] + 160, y0)
            await page.keyboard.up("Shift")
            shift = await page.evaluate("() => String(window.getSelection()).length")
            r["shiftSelect"] = {"selected": shift, "open": await still_open(page, PEER, f"{scheme}: shift-click")}
            check(failures, shift > 0 and r["shiftSelect"]["open"], f"{scheme}: extending a selection with Shift + click keeps it open: {r['shiftSelect']}")
            await page.evaluate("() => window.getSelection().removeAllRanges()")

            # things with their own action keep it open (planted in the opened body: no folded row carries them today)
            await page.evaluate("""(sel) => { const d = document.querySelector(sel);
              const a = document.createElement('a'); a.href = '#e2e-link'; a.id = 'e2e-link'; a.textContent = 'a link';
              a.addEventListener('click', (e) => e.preventDefault());
              const t = document.createElement('button'); t.type = 'button'; t.className = 'h-thumb'; t.id = 'e2e-thumb';
              const img = document.createElement('img'); img.alt = 'thumb'; img.width = 40; img.height = 30; t.appendChild(img);
              const w = document.createElement('div'); w.className = 'h-tablewrap'; w.id = 'e2e-table';
              w.innerHTML = '<table class="h-table"><tr>' + '<td>wide cell</td>'.repeat(40) + '</tr></table>';
              d.append(a, t, w); }""", PEER)
            for what, target in (("link", "#e2e-link"), ("thumbnail", "#e2e-thumb"), ("sideways table", "#e2e-table td")):
                where = await page.evaluate("""(q) => { const e = document.querySelector(q); if (!e) return null;
                  e.scrollIntoView({ block: 'center' }); const r = e.getBoundingClientRect();
                  return { x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2, hit: document.elementFromPoint(r.left + Math.min(20, r.width / 2), r.top + r.height / 2) === e || e.contains(document.elementFromPoint(r.left + Math.min(20, r.width / 2), r.top + r.height / 2)) }; }""", target)
                check(failures, where and where["hit"], f"{scheme}: the planted {what} is there to click: {where}")
                if where:
                    await page.mouse.click(where["x"], where["y"])
                kept = r[f"keep-{what}"] = await still_open(page, PEER, f"{scheme}: {what}")
                check(failures, kept, f"{scheme}: a click on a {what} keeps it open")
            # the whole-text tag: the real one, over the cut name of the long tool (its fold opened first)
            mcp = f"{PANE} details.h-tool:has(.h-err)"
            await opened(page, mcp)
            name = page.locator(f"{mcp} > summary > b")
            await name.scroll_into_view_if_needed()
            await name.hover()
            await until(page, "() => { const t = document.getElementById('fulltext'); return !!t && !t.hidden; }", f"{scheme}: the whole-text tag")
            await page.locator("#fulltext").click()
            r["keep-fulltext"] = {"peer": await still_open(page, PEER, f"{scheme}: fulltext"), "tool": await page.evaluate(OPEN, mcp)}
            check(failures, r["keep-fulltext"]["peer"] and r["keep-fulltext"]["tool"], f"{scheme}: a click on the whole-text tag closes nothing: {r['keep-fulltext']}")
            await page.screenshot(path=str(out / f"fold-open-{scheme}.png"))

            # a row that does not fold: nothing changes
            folds = "() => [...document.querySelectorAll('[data-rb-hist] details')].map((d) => d.open)"
            before = await page.evaluate(folds)
            asst = page.locator(f"{PANE} .h-asst").first
            await asst.scroll_into_view_if_needed()
            top0 = await page.evaluate("() => document.querySelector('[data-rb-hist]').scrollTop")
            await asst.click()
            await still_open(page, PEER, f"{scheme}: a plain row")
            after, top1 = await page.evaluate(folds), await page.evaluate("() => document.querySelector('[data-rb-hist]').scrollTop")
            r["plainRow"] = {"same": before == after, "scroll": [top0, top1]}
            check(failures, before == after and abs(top1 - top0) < 2, f"{scheme}: a click on a row that does not fold changes nothing: {r['plainRow']}")

            # the keyboard: Enter on the summary opens and closes
            await page.focus(f"{HARNESS} > summary")
            was = await page.evaluate(OPEN, HARNESS)
            await page.keyboard.press("Enter")
            await until(page, OPEN if not was else CLOSED, f"{scheme}: Enter toggles", arg=HARNESS)
            await page.keyboard.press("Enter")
            await until(page, CLOSED if not was else OPEN, f"{scheme}: Enter toggles back", arg=HARNESS)
            await page.close()
    except Exception as e:
        failures.append(f"{SUITE}: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, SUITE)
        print(f"  {SUITE}: {time.monotonic() - t0:.0f}s", flush=True)
        if hasattr(st, "out"):
            (pathlib.Path(st.out) / f"{SUITE}-results.json").write_text(dump(res) + "\n")
