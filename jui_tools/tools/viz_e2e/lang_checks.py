"""The page as its reader sees it, in the run's language (ticket 2026-10-21-viz-english-screen-checks §2b, §2d).

On the demo: the main view, a robot's card, its talk list, and the phone's main view. At each, common.shot keeps a
picture and screen_check's report (<out>/lang-checks/shots/), and a key of the table drawn as itself is a failure — in
Japanese and in English. Run it twice (JUI_VIZ_LANGUAGE=ja, then en) and lang_sheet.py lays the two side by side.
A key the code asks for and the table lacks is a console warning (tl in 05-i18n.js), which this suite fails on too.
Two boxes of words in one parent covering each other, and canvas words past their canvas or cut with "…", are
failures as well, in either language (the scene's hint ran into the demo clock on a phone in English): a sign or a board drawn in
the 3D has no scrollbar, and what does not fit is lost (the English run once had 8: Server room, the spec board's
statuses and names; the Japanese 1: サーバールーム).

The server room's words that come from document_tools (a room's problem lines, a cost meter's name) are its words on
English too (ticket 2026-10-22-viz-en-document-tools-words-stay-japanese): server_room.py shoots the failure's bubble and
the cost's day with doc_words_shot, and on the English page any of those words' Japanese is a failure. Japanese the
room wrote itself (a node's label, a scenario's) is the room's, and is left for the sheet.
"""
from __future__ import annotations

import json
import pathlib
import re
import time

from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready, shot
from talk_ui import open_card, open_talk
from waits import WaitTimeout

LABEL = "a0"   # the demo's main session (talk_ui opens it too)
JA_TABLE = pathlib.Path(__file__).resolve().parents[2] / "jui_cli" / "viz" / "web" / "i18n" / "ja.json"
#: the keys of the words viz says for document_tools (jui_cli/viz/infra_words.py)
DOC_WORDS = ("srv.cost.q.", "srv.cost.meter.", "srv.cost.model", "srv.room.")
JA = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff01-\uff60]")


def doc_words() -> list[str]:
    """The Japanese of document_tools' words, as they stand on a page: each value's parts between its slots that have
    a Japanese letter, longest first."""
    table = json.loads(JA_TABLE.read_text(encoding="utf-8"))
    parts = {p.strip(" :、。（）") for k, v in table.items() if k.startswith(DOC_WORDS) and isinstance(v, str)
             for p in re.split(r"\{\w+\}", v)}
    return sorted((p for p in parts if JA.search(p)), key=len, reverse=True)


def leftovers(report: dict, where: str, failures: list) -> None:
    """document_tools' Japanese on the English page (screen_check reports Japanese on English pages only). A word is
    found whole, not inside the room's own words (メール is a meter's name; メール配信 a node's label)."""
    found = [(w, re.compile(rf"(?<![\u3040-\u30ff\u3400-\u9fff]){re.escape(w)}(?![\u3040-\u30ff\u3400-\u9fff])"))
             for w in doc_words()]
    for line in report["japanese"]:
        hit = next((w for w, f in found if f.search(line)), None)
        if hit:
            failures.append(f"lang-checks: {where}: document_tools' Japanese on the English page ({hit!r}): {line}")


async def doc_words_shot(page, name: str, out, failures: list) -> dict:
    report = await shot(page, name, out, failures)
    leftovers(report, name, failures)
    return report


def cut(report: dict, where: str, failures: list) -> None:
    for o in report["overlap"]:
        failures.append(f"lang-checks: {where}: {o['a']} and {o['b']} cover each other ({o['w']}×{o['h']}px): {o['text']}")
    for c in report["canvas"]:
        how = "cut" if c["text"].endswith("…") else f"past the canvas ({c['left']}–{c['right']} of {c['canvas']}px)"
        failures.append(f"lang-checks: {where}: canvas words {how}: {c['text']!r} ({c['font']})")


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
        cut(await shot(page, "main", out, failures), "main", failures)
        try:
            await open_card(page, LABEL)
            cut(await shot(page, "card", out, failures), "card", failures)
            await open_talk(page)
            cut(await shot(page, "talk", out, failures), "talk", failures)
        except WaitTimeout as e:
            failures.append(f"lang-checks: card / talk: {e}")
        await page.close()
        phone = await new_page(browser, watch, "lang-checks phone", **PHONE)
        await phone.goto(f"{srv.url}/?demo=1")
        await ready(phone)
        await phone.wait_for_timeout(1500)
        cut(await shot(phone, "phone-main", out, failures), "phone-main", failures)
        await phone.close()
    finally:
        await browser.close()
        srv.stop()
    for line in watch.console:
        failures.append(f"lang-checks: console: {line}")
    for u in watch.foreign:
        failures.append(f"lang-checks: request outside the server: {u}")
    print(f"  lang-checks: {time.monotonic() - t0:.0f}s", flush=True)
