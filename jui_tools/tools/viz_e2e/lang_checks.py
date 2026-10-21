"""The page as its reader sees it, in the run's language (ticket 2026-10-21-viz-english-screen-checks §2b, §2d).

On the demo: the main view, a robot's card, its talk list, and the phone's main view. At each, common.shot keeps a
picture and screen_check's report (<out>/lang-checks/shots/), and a key of the table drawn as itself is a failure — in
Japanese and in English. Run it twice (JUI_VIZ_LANGUAGE=ja, then en) and lang_sheet.py lays the two side by side.
A key the code asks for and the table lacks is a console warning (tl in 05-i18n.js), which this suite fails on too.
"""
from __future__ import annotations

import pathlib
import time

from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready, shot
from talk_ui import open_card, open_talk
from waits import WaitTimeout

LABEL = "a1"


async def run_lang_checks(pw, out, failures, Server):
    out = pathlib.Path(out) / "lang-checks"
    out.mkdir(parents=True, exist_ok=True)
    srv = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=srv.url)
    t0 = time.monotonic()
    try:
        page = await new_page(browser, watch, "lang-checks", **DESKTOP)
        await page.goto(f"{srv.url}/?demo=1")
        await ready(page)
        await page.wait_for_timeout(1500)
        await shot(page, "main", out, failures)
        try:
            await open_card(page, LABEL)
            await shot(page, "card", out, failures)
            await open_talk(page)
            await shot(page, "talk", out, failures)
        except WaitTimeout as e:
            failures.append(f"lang-checks: card / talk: {e}")
        await page.close()
        phone = await new_page(browser, watch, "lang-checks phone", **PHONE)
        await phone.goto(f"{srv.url}/?demo=1")
        await ready(phone)
        await phone.wait_for_timeout(1500)
        await shot(phone, "phone-main", out, failures)
        await phone.close()
    finally:
        await browser.close()
        srv.stop()
    for line in watch.console:
        failures.append(f"lang-checks: console: {line}")
    for u in watch.foreign:
        failures.append(f"lang-checks: request outside the server: {u}")
    print(f"  lang-checks: {time.monotonic() - t0:.0f}s", flush=True)
