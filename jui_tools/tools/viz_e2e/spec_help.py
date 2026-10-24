"""「spec の進み具合」 explained in a dialog, end to end (2.3.4, requester 10-19: "specの進み具合の説明をボードから消して
その代わりに？ボタンおいて押したらモーダルで説明出して", both places alike: "同じで").

The demo page (fake_server.py, frozen at 27 s, where the specs are in every state), at 1440 px and 390 px, light and
dark. Arms:

  - the explanation and the legend are gone from the panel's 「spec の進み具合」 and from the 「ボードで全部見る」
    overview (none of their sentences, no colour swatch) — the filter chips, the rows and the cards stay;
  - each place has a 「?」 button whose accessible name is 「spec の進み具合の説明」;
  - each opens a dialog (role dialog, aria-modal, labelled by a heading) holding the explanation and the five colour
    swatches, with the focus inside; the two dialogs are the same, text and markup;
  - Esc, a press on the backdrop and the close button each close it and put the focus back on the 「?」 that opened
    it; Esc on the overview closes only the dialog, not the board; Tab and Shift+Tab stay inside;
  - at 390 px the dialog fits (no horizontal scroll).

It runs against an older page too and says what that page lacks (the screenshots of both are for the eye).
"""

from __future__ import annotations

import json
import pathlib
import time

from common import DESKTOP, PHONE, T, Watch, freeze, new_page, ready, shown


# read in the run's language when a check runs (run.py sets it after this module is imported)
def NAME() -> str:
    return T("page.spec.help")


def GONE() -> list[str]:
    """The explanation's three paragraphs: gone from the panel and the overview."""
    return [T("panel.help.watch"), T("panel.help.bar"), T("panel.help.open")]


def MUST() -> list[str]:
    """The dialog: the three paragraphs and the five swatches' names."""
    return GONE() + [T(f"panel.sw.{k}") for k in ("writing", "written", "impl", "tested", "empty")]


HELP = "[data-spec-help]"

# what a place shows outside the dialog: its text and how many colour swatches are visible
PLACE = """(sel) => { const el = document.querySelector(sel); if (!el) return null;
  const vis = (x) => !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
  return { text: el.innerText, swatches: [...el.querySelectorAll('.sw')].filter((x) => vis(x) && !x.closest('#spec-help')).length }; }"""
DIALOG = """() => { const d = [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].find((x) => x.offsetWidth || x.offsetHeight);
  if (!d) return null;
  const lab = d.getAttribute('aria-labelledby'), title = lab && document.getElementById(lab);
  const body = d.querySelector('.sh-body') || d;
  return { title: title ? title.textContent : null, text: body.innerText, html: body.innerHTML, swatches: d.querySelectorAll('.sw').length,
    focusInside: d.contains(document.activeElement), id: d.closest('#spec-help') ? 'spec-help' : d.id,
    box: d.getBoundingClientRect().toJSON(), sw: document.documentElement.scrollWidth }; }"""
FOCUS = "() => { const a = document.activeElement; return a ? (a.id || a.getAttribute('aria-label') || a.tagName) : null; }"


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-help: {text}")


async def run_spec_help(pw, out, failures, Server):
    from common import LAUNCH_ARGS
    out = pathlib.Path(out) / "spec-help"
    out.mkdir(parents=True, exist_ok=True)
    srv = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    res: dict = {}
    watch = Watch(origin=srv.url)
    try:
        for width, opts in (("1440", DESKTOP), ("390", PHONE)):
            for scheme in ("light", "dark"):
                key = f"{width}-{scheme}"
                r = res[key] = {}
                page = await new_page(browser, watch, f"spec-help-{key}", color_scheme=scheme, **opts)
                await page.goto(f"{srv.url}/?demo=1")
                await ready(page)
                await freeze(page, 27)
                # the panel: gone, a 「?」 with its name
                await page.evaluate("() => document.getElementById('h-spec').scrollIntoView({ block: 'start' })")
                await page.wait_for_timeout(300)
                panel = r["panel"] = await page.evaluate(PLACE, "section[aria-labelledby='h-spec']")
                check(failures, panel and not [g for g in GONE() if g in panel["text"]] and panel["swatches"] == 0,
                      f"{key}: the panel's explanation and legend are gone: {[g for g in GONE() if panel and g in panel['text']]}, swatches {panel and panel['swatches']}")
                rows = await page.evaluate("() => document.querySelectorAll('#spec-list .spec-row').length + ':' + document.querySelectorAll('#spec-filter button').length")
                r["rowsChips"] = rows
                check(failures, rows.split(":")[0] != "0" and rows.split(":")[1] != "0", f"{key}: the rows and the chips stay: {rows}")
                await page.screenshot(path=str(out / f"panel-{key}.png"))
                pbtn = page.locator(f"section[aria-labelledby='h-spec'] {HELP}")
                named = await page.get_by_role("button", name=NAME(), exact=True).count()
                r["namedButtons"] = named
                check(failures, await pbtn.count() == 1, f"{key}: a 「?」 next to the panel's heading")
                dialogs = r.setdefault("dialogs", {})
                if await pbtn.count() == 1:
                    check(failures, (await pbtn.get_attribute("aria-label")) == NAME(), f"{key}: the panel's 「?」 is named {NAME()}")
                    # open, read, close with Esc
                    await pbtn.click()
                    await page.wait_for_timeout(250)
                    d = dialogs["panel"] = await page.evaluate(DIALOG)
                    await page.screenshot(path=str(out / f"panel-modal-{key}.png"))
                    await close_three_ways(page, pbtn, "panel", key, r, failures)
                # the overview: gone, a 「?」, the same dialog; Esc closes the dialog, not the board
                await page.evaluate("() => window.scrollTo(0, 0)")
                await page.click("#btn-specboard")
                await shown(page, "wb")
                await page.wait_for_timeout(400)
                ov = r["overview"] = await page.evaluate(PLACE, "#wb")
                cards = await page.evaluate("() => document.querySelectorAll('.ov-card').length")
                r["cards"] = cards
                check(failures, ov and not [g for g in GONE() if g in ov["text"]] and ov["swatches"] == 0,
                      f"{key}: the overview's legend is gone: {[g for g in GONE() if ov and g in ov['text']]}, swatches {ov and ov['swatches']}")
                check(failures, cards > 0, f"{key}: the overview's cards stay: {cards}")
                await page.screenshot(path=str(out / f"overview-{key}.png"))
                obtn = page.locator(f"#wb {HELP}")
                check(failures, await obtn.count() == 1 and await obtn.is_visible(), f"{key}: a 「?」 on the overview")
                if await obtn.count() == 1 and await obtn.is_visible():
                    check(failures, (await obtn.get_attribute("aria-label")) == NAME(), f"{key}: the overview's 「?」 is named {NAME()}")
                    await obtn.click()
                    await page.wait_for_timeout(250)
                    dialogs["overview"] = await page.evaluate(DIALOG)
                    await page.screenshot(path=str(out / f"overview-modal-{key}.png"))
                    await close_three_ways(page, obtn, "overview", key, r, failures)
                    board = await page.evaluate("() => !document.getElementById('wb').hidden")
                    r["boardStaysOpen"] = board
                    check(failures, board, f"{key}: Esc on the dialog leaves the board open")
                    # an open spec keeps its own legend and has no 「?」
                    await page.click('.ov-card[data-idx="1"]')
                    await page.wait_for_timeout(900)
                    sheet = r["sheet"] = await page.evaluate("() => ({ help: !!document.querySelector('#wb [data-spec-help]') && document.querySelector('#wb [data-spec-help]').offsetWidth > 0, legend: document.getElementById('wb-legend').innerText })")
                    check(failures, not sheet["help"] and T("panel.lg.writing") in sheet["legend"], f"{key}: an open spec keeps its own legend, no 「?」: {sheet}")
                # the two dialogs are one: the same text and markup, and all of it is there
                for where, d in dialogs.items():
                    check(failures, d is not None, f"{key}: the {where} 「?」 opens a dialog (role dialog, aria-modal)")
                    if d:
                        missing = [m for m in MUST() if m not in d["text"]]
                        check(failures, not missing and d["swatches"] == 5 and d["title"], f"{key}: the {where} dialog has the explanation, a title and five swatches: missing {missing}, swatches {d['swatches']}, title {d['title']!r}")
                        check(failures, d["focusInside"], f"{key}: the focus is inside the {where} dialog")
                        if width == "390":
                            check(failures, d["sw"] <= 390 and d["box"]["right"] <= 390 and d["box"]["left"] >= 0, f"{key}: the {where} dialog fits 390 px: {d['box']} sw {d['sw']}")
                p, o = dialogs.get("panel"), dialogs.get("overview")
                same = bool(p and o and p["text"] == o["text"] and p["html"] == o["html"])
                r["same"] = same
                check(failures, same, f"{key}: both 「?」 open the same content")
                r["named"] = named
                check(failures, named == 1, f"{key}: one button found by its name while the board is closed: {named}")
                await page.close()
        for line in watch.console:
            failures.append(f"spec-help: console: {line}")
        for u in watch.foreign:
            failures.append(f"spec-help: request outside the server: {u}")
        for c in watch.csp:
            failures.append(f"spec-help: CSP violation: {c}")
    except Exception as e:
        failures.append(f"spec-help: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.stop()
    import json
    (out / "spec-help-results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    print(f"  spec-help: {time.monotonic() - t0:.0f}s", flush=True)


async def close_three_ways(page, btn, where, key, r, failures):
    """The dialog is open: Tab stays inside, then Esc closes it; open again, the backdrop; again, the close button.
    Each time the focus is back on the 「?」."""
    want = await btn.get_attribute("id")
    trap = []
    for k in ("Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab"):
        await page.keyboard.press(k)
        trap.append(bool((await page.evaluate(DIALOG) or {}).get("focusInside")))
    r[f"{where}Trap"] = trap
    check(failures, all(trap), f"{key}: Tab and Shift+Tab stay inside the {where} dialog: {trap}")
    ways = {}
    for how in ("Escape", "backdrop", "close"):
        if how != "Escape":
            await btn.click()
            await page.wait_for_timeout(250)
        was_open = await page.evaluate(DIALOG) is not None
        if how == "Escape":
            await page.keyboard.press("Escape")
        elif how == "backdrop":
            await page.mouse.click(4, 300)
        else:
            close = page.locator(f"#spec-help [data-sh-close], [role='dialog'][aria-modal='true']:visible button:has-text({json.dumps(T('panel.close'))})").first
            if await close.count():
                await close.click()
        await page.wait_for_timeout(250)
        gone = was_open and await page.evaluate(DIALOG) is None
        back = await page.evaluate(FOCUS)
        ways[how] = {"closed": gone, "focus": back}
        check(failures, gone and back == want, f"{key}: {how} closes the {where} dialog and the focus is back on its 「?」: {ways[how]} (want {want})")
    r[f"{where}Close"] = ways
