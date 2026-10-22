"""The cost view's day rows (the requester 10-23: 「長い文章だと棒グラフの中に入り切らずに...になってる / 全文見るために広げるのボタンが
欲しい」「文字とグラフは縦並びにして / 文字が多いとグラフの領域が狭すぎてわかりづらい」), end to end.

The real `jui viz serve` in a throwaway HOME on a free port, a room of two nodes: one with eleven meters (a model's tokens
by sku, the shape that was cut with "…"), one under a cent. A day: each row's bar on top across the column with no words
in it, the meters' words under it — two lines, cut, with ▼ on their lower edge; pressed (the key, the words themselves)
all of them, ▲ to fold; an hour moved keeps it open; ▼ for every row in the day's header. Not cut: no button, the words
press nothing. An amount under a cent says < $0.01. At 390 wide nothing goes past the page (the server room was 629
wide there). Pictures: folded, open, the phone.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, PHONE, T, Watch, new_page, ready
from waits import until

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SKUS_IN = ["claude-haiku-5-5", "claude-haiku-5-5-cache-read", "claude-haiku-5-5-cache-write", "claude-sonnet-5-5",
           "claude-sonnet-5-5-cache-read", "claude-sonnet-5-5-cache-write", "claude-haiku-5-5-batch"]
SKUS_OUT = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-haiku-5-5-batch"]
DAY = "2027-06-11"
ROW = "(id) => { const r = document.querySelector(`#sr-cost [data-src-node='${id}']`); if (!r) return null;" \
      " const p = r.querySelector('[data-src-parts]'), b = r.querySelector('button[data-src-more]'), bar = r.querySelector('.src-bar');" \
      " return { usd: r.querySelector('.src-usd').textContent, barWords: bar.textContent, barW: bar.getBoundingClientRect().width," \
      " barBottom: bar.getBoundingClientRect().bottom, partsTop: p ? p.getBoundingClientRect().top : null," \
      " cut: p ? p.scrollHeight > p.clientHeight + 1 : null, h: p ? p.clientHeight : null, line: p ? parseFloat(getComputedStyle(p).lineHeight) : null," \
      " words: p ? p.textContent : '', button: b && !b.hidden ? b.textContent : null, expanded: b ? b.getAttribute('aria-expanded') : null," \
      " focused: !!b && document.activeElement === b, right: r.getBoundingClientRect().right," \
      " usdRight: r.querySelector('.src-usd').getBoundingClientRect().right }; }"


def check(failures, cond, text):
    if not cond:
        failures.append(f"cost-rows: {text}")


def _room(root: pathlib.Path):
    infra = root / "docs" / "infra"
    for d in (infra / "load", infra / "prices", root / ".git"):
        d.mkdir(parents=True, exist_ok=True)
    model = {"version": 0, "environments": [{"id": "production", "label": "本番"}],
             "groups": [{"id": "providers", "label": "LLM の提供元", "kind": "logical"}],
             "nodes": [{"id": "llm", "category": "external.saas", "label": "Anthropic（1 番目・夜間は Batch API）", "provider": "anthropic",
                        "service": "messages", "group": "providers", "managed_by": "external", "environments": ["production"]},
                       {"id": "mail", "category": "external.saas", "label": "メール", "provider": "acme", "service": "mail",
                        "group": "providers", "managed_by": "external", "environments": ["production"]}],
             "edges": [{"id": "e1", "from": "llm", "to": "mail", "protocol": "https", "port": 443}]}
    row = {"service": "messages", "region": "global", "unit": "token", "per_units": 1000000, "effective": "2026-10-22", "source": "manual"}
    prices = [dict(row, provider="anthropic", sku=f"{s}:input-tokens", price_usd=1.0 + i / 10) for i, s in enumerate(SKUS_IN)]
    prices += [dict(row, provider="anthropic", sku=f"{s}:output-tokens", price_usd=5.0) for s in SKUS_OUT]
    prices += [{"provider": "acme", "service": "mail", "sku": "requests", "region": "global", "unit": "request", "per_units": 1000,
                "price_usd": 0.0001, "effective": "2026-10-22", "source": "manual"}]
    # a long label: the header's select made the server room 629 wide on 390
    load = {"version": 0, "id": "month", "label": "メディアに載った月（steady の月の 6/11 に 8 倍、その後 3 倍・2 倍・1.3 倍。数はすべて仮定）",
            "environment": "production", "month": "2027-06", "timezone": "Asia/Tokyo",
            "currency": "USD", "profiles": {"flat": {"label": "平ら", "hourly": [1] * 24}},
            "week": {d: "flat" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
            "loads": [{"node": "llm", "quantities": {"requests": {"amount": 51780, "per": "day"},
                                                     "input_tokens": {"by_sku": {s: 50000000 + i * 1000000 for i, s in enumerate(SKUS_IN)}, "per": "day"},
                                                     "output_tokens": {"by_sku": {s: 15000000 for s in SKUS_OUT}, "per": "day"}}},
                      {"node": "mail", "quantities": {"requests": {"amount": 500, "per": "day"}}}]}
    (infra / "main.json").write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    (infra / "prices" / "mine.json").write_text(json.dumps({"version": 0, "id": "mine", "prices": prices}, ensure_ascii=False), encoding="utf-8")
    (infra / "load" / "month.json").write_text(json.dumps(load, ensure_ascii=False), encoding="utf-8")


async def _open_day(page, url):
    await page.goto(url + "/")
    await ready(page)
    await until(page, "() => window.__dbg.robots.length >= 1 && window.__dbg.robots.every((R) => !R.path.length)", "the robot seated", timeout=60000)
    pid = await page.evaluate("() => window.__dbg.robots[0].def.room")
    await page.click(f".tag.room[data-set-project='{pid}']")
    await until(page, "() => window.__dbg.sr().built && window.__dbg.sr().door", "the server room's door", timeout=30000)
    await until(page, "() => window.__dbg.robots.every((R) => !R.path.length)", "settled up close", timeout=30000)
    for tries in range(3):   # the camera may still be easing onto the room: the door is read again for each press
        at = (await page.evaluate("() => window.__dbg.sr()"))["door"]
        await page.mouse.click(at[0], at[1])
        try:
            await until(page, "() => !document.getElementById('sr').hidden", "the server room", timeout=10000)
            break
        except Exception:
            if tries == 2:
                raise
    await page.click("#sr-mode-cost")
    await until(page, "() => { const c = window.__dbg.srCost(); return c.month && c.month.bars === c.month.days; }", "the month", timeout=30000)
    await page.click(f"#sr-cost [data-src-date='{DAY}']")
    await until(page, "() => { const d = window.__dbg.srCost().day; return d && d.rows >= 2; }", "the day", timeout=30000)


async def run_cost_rows(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "cost-rows"
    out.mkdir(parents=True, exist_ok=True)
    home, room = out / "home", out / "room"
    home.mkdir(exist_ok=True)
    _room(room)
    jt = pathlib.Path(__file__).resolve().parents[2]
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
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
        body = {"session_id": "c0570000-0000-4000-8000-000000000001", "cwd": str(room), "permission_mode": "default",
                "hook_event_name": "SessionStart", "source": "startup"}
        subprocess.run([sys.executable, "-I", "-S", str(jt / "jui_cli" / "viz" / "forward.py")], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "cost-rows", **DESKTOP)
        await page.emulate_media(color_scheme="dark", reduced_motion="no-preference")
        await _open_day(page, url)

        # 1. folded: the bar has no words, the words under it are two lines and cut, ▼ on their edge
        llm, mail = await page.evaluate(ROW, "llm"), await page.evaluate(ROW, "mail")
        res["folded"] = {"llm": llm, "mail": mail}
        check(failures, llm["barWords"] == "", f"the bar holds no words: {llm['barWords']!r}")
        check(failures, llm["barW"] >= 600, f"the bar has the column's width at 1440: {llm['barW']}")
        check(failures, llm["partsTop"] >= llm["barBottom"] - 0.5, f"the words are under the bar: {llm['partsTop']} / {llm['barBottom']}")
        check(failures, llm["cut"] and llm["h"] <= 2 * llm["line"] + 5, f"folded, the words are two lines (and their 2 px padding), cut: {llm}")
        check(failures, llm["button"] == T("cost.more") and llm["expanded"] == "false", f"▼ on the cut words: {llm['button']!r}")
        check(failures, mail["button"] is None and not mail["cut"], f"words that fit have no button: {mail}")
        check(failures, mail["usd"] == "< $0.01", f"an amount under a cent says so: {mail['usd']!r}")
        check(failures, all(m in llm["words"] for m in ("claude-haiku-5-5-batch", "claude-sonnet-5-5-cache-write")), "every meter is in the words")
        await page.screenshot(path=str(out / "folded.png"))

        # 2. the key opens the row whole (the focus stays on its button), an hour moved keeps it open, the key folds it
        await page.focus("#sr-cost [data-src-node='llm'] button[data-src-more]")
        await page.keyboard.press("Enter")
        llm = await until(page, f"(id) => {{ const x = ({ROW})(id); return x && x.expanded === 'true' ? x : null; }}", "opened by the key", arg="llm")
        res["open"] = llm
        check(failures, not llm["cut"] and llm["h"] > 2 * llm["line"] + 5, f"open, every word shows: {llm}")
        check(failures, llm["button"] == T("cost.less") and llm["focused"], f"▲ to fold, the focus kept: {llm['button']!r} {llm['focused']}")
        await page.screenshot(path=str(out / "open.png"))
        await page.evaluate("() => { const s = document.getElementById('src-hour'); s.value = '5'; s.dispatchEvent(new Event('input', { bubbles: true })); }")
        hour = await until(page, f"() => window.__dbg.srCost().day.hour === 5 && ({ROW})('llm')", "the hour moved")
        check(failures, hour["expanded"] == "true" and not hour["cut"], f"an hour moved keeps the row open: {hour}")
        await page.focus("#sr-cost [data-src-node='llm'] button[data-src-more]")
        await page.keyboard.press(" ")
        llm = await until(page, f"(id) => {{ const x = ({ROW})(id); return x && x.expanded === 'false' ? x : null; }}", "folded by the key", arg="llm")
        check(failures, llm["cut"], "folded again, cut")

        # 3. the words themselves press; the words that fit press nothing
        await page.click("#sr-cost [data-src-node='llm'] [data-src-parts]")
        check(failures, (await page.evaluate(ROW, "llm"))["expanded"] == "true", "the cut words open on a press")
        await page.click("#sr-cost [data-src-node='mail'] [data-src-parts]")
        check(failures, (await page.evaluate(ROW, "mail"))["button"] is None, "words that fit stay without a button when pressed")
        await page.click("#sr-cost [data-src-node='llm'] button[data-src-more]")

        # 4. every row at once from the day's header
        allb = "#sr-cost [data-src-act='more-all']"
        check(failures, (await page.text_content(allb)) == T("cost.more.all"), "▼ every row in the day's header")
        await page.click(allb)
        await until(page, f"() => document.querySelector(\"{allb}\").getAttribute('aria-expanded') === 'true'", "every row open")
        check(failures, (await page.evaluate(ROW, "llm"))["expanded"] == "true" and (await page.text_content(allb)) == T("cost.less.all"), "every row open, ▲ to fold them")
        await page.click(allb)
        check(failures, (await page.evaluate(ROW, "llm"))["expanded"] == "false", "every row folded")
        check(failures, not watch.console and not watch.foreign, f"no console error: {watch.console[:3]}")
        await page.close()

        # 5. a phone: nothing past 390, the amount on the page, the bar the page's width
        phone = await new_page(browser, watch, "cost-rows-phone", **PHONE)
        await phone.emulate_media(color_scheme="dark")
        await _open_day(phone, url)
        llm = await phone.evaluate(ROW, "llm")
        wide = await phone.evaluate("() => [document.documentElement.scrollWidth, document.getElementById('sr').scrollWidth, document.getElementById('sr-cost').getBoundingClientRect().width]")
        res["phone"] = {"llm": llm, "wide": wide}
        check(failures, wide[0] <= 390 and wide[1] <= 390 and wide[2] <= 390, f"nothing goes past 390: {wide}")
        check(failures, llm["usdRight"] <= 390 and llm["right"] <= 390, f"the amount on the page: {llm['usdRight']}")
        check(failures, llm["barW"] >= 300, f"the bar takes the row's width: {llm['barW']}")
        await phone.screenshot(path=str(out / "phone.png"))
        await phone.close()
    except Exception as e:
        failures.append(f"cost-rows: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  cost-rows: {time.monotonic() - t0:.0f}s", flush=True)
