"""Pictures in the 応答の履歴, end to end (2.3.4, requester 10-19: "画像ファイルが履歴にある場合はサムネイル表示とクリックで
拡大表示を実装してほしい").

The same stage as hist_wide.py (two sessions; A's transcript has two real PNGs and a note naming a picture file that is
gone). Arms: no picture is asked for before the tab opens; the two thumbnails load once in view and are the
transcript's pictures (their natural sizes); 「元の画像ファイルは消えている」; a press opens the large view (a dialog,
labelled, the focus inside), → goes to the other picture and does not switch the robot, Esc / the backdrop / 閉じる
close it and put the focus back on the thumbnail while the card stays open; 390 px. No console error (a refused
picture would log one), nothing requested outside the server. Screenshots (light and dark, 1440 and 390).
"""

from __future__ import annotations

import pathlib
import time

from common import PHONE, dump
import json

from hist_wide import A, GONE, Stage, check as _check, png, wait

LIGHT = """() => { const d = [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].find((x) => x.offsetWidth);
  if (!d) return null; const i = d.querySelector('img');
  return { count: (d.querySelector('.h-light-count') || {}).textContent || '', w: i ? i.naturalWidth : 0, h: i ? i.naturalHeight : 0,
    labelled: !!(d.getAttribute('aria-labelledby') && document.getElementById(d.getAttribute('aria-labelledby'))), focusInside: d.contains(document.activeElement) }; }"""
LIGHT_READY = "() => { const d = [...document.querySelectorAll('[role=\"dialog\"][aria-modal=\"true\"]')].find((x) => x.offsetWidth); return !!(d && d.querySelector('img') && d.querySelector('img').naturalWidth); }"
THUMBS = """() => [...document.querySelectorAll('[data-rb-hist] .h-thumb')].map((b) => { const i = b.querySelector('img');
  return { key: b.dataset.hImg, w: i ? i.naturalWidth : 0, h: i ? i.naturalHeight : 0 }; })"""
INTO_VIEW = "() => { const t = document.querySelector('[data-rb-hist] .h-thumb, [data-rb-hist] .h-mark'); if (t) t.scrollIntoView({ block: 'center' }); }"
FOCUS_KEY = "() => document.activeElement ? (document.activeElement.dataset.hImg || document.activeElement.tagName) : null"


def check(failures, cond, text):
    _check(failures, cond, text, "hist-images")


async def run_hist_images(pw, out, failures):
    t0 = time.monotonic()
    st = Stage()
    res: dict = {}
    try:
        await st.start(pw, out, "hist-images")
        out = st.out
        page = await st.page("hist-images")
        asked = []
        page.on("request", lambda r: asked.append(r.url) if "/api/history-image" in r.url else None)
        rid = await page.evaluate("() => window.__dbg.robots[0].def.id")
        await page.evaluate("(id) => window.__dbg.openRobot(id)", rid)
        await wait(page, "() => !document.getElementById('rb').hidden", label="the card")
        await page.wait_for_timeout(800)
        res["askedBeforeTab"] = len(asked)
        check(failures, not asked, f"no picture is asked for before the tab opens: {asked}")
        await st.open_a(page)
        await page.evaluate(INTO_VIEW)
        try:
            await wait(page, "() => [...document.querySelectorAll('[data-rb-hist] .h-thumb img')].filter((i) => i.naturalWidth > 0).length >= 2", timeout=10000, label="two thumbnails")
        except RuntimeError as e:
            check(failures, False, f"two thumbnails load: {e}")
        th = res["thumbs"] = await page.evaluate(THUMBS)
        res["asked"] = len(asked)
        check(failures, [(t["w"], t["h"]) for t in th] == [(320, 200), (200, 300)], f"two thumbnails, the transcript's pictures: {th}")
        text = await page.evaluate("() => document.querySelector('[data-rb-hist]').textContent")
        check(failures, f"元の画像ファイルは消えている: {GONE}" in text, "the picture file that is gone says so")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(out / f"thumbs-1440-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        if th:
            title0 = await page.evaluate("() => document.getElementById('rb-title').textContent")
            await page.click("[data-rb-hist] .h-thumb >> nth=0")
            await wait(page, LIGHT_READY, label="the large view")
            lv = res["light1"] = await page.evaluate(LIGHT)
            check(failures, lv and lv["count"] == "1 / 2" and (lv["w"], lv["h"]) == (320, 200) and lv["labelled"] and lv["focusInside"],
                  f"the large view opens on the first picture, labelled, the focus inside: {lv}")
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                await page.wait_for_timeout(500)
                await page.screenshot(path=str(out / f"large-1440-{scheme}.png"))
            await page.emulate_media(color_scheme="light")
            await page.keyboard.press("ArrowRight")
            try:
                await wait(page, "() => { const d = document.querySelector('.h-light [role=\"dialog\"]'); return !!d && d.querySelector('.h-light-count').textContent === '2 / 2' && d.querySelector('img').naturalWidth === 200; }",
                           timeout=8000, label="→ the second picture")
                stepped = True
            except RuntimeError:
                stepped = False
            res["lightStep"] = [stepped, await page.evaluate("() => document.getElementById('rb-title').textContent")]
            check(failures, stepped and res["lightStep"][1] == title0, f"→ shows the second picture and does not switch the robot: {res['lightStep']} (was {title0!r})")
            closes = res["lightClose"] = {}
            for how in ("Escape", "backdrop", "close"):
                if how != "Escape":
                    await page.click("[data-rb-hist] .h-thumb >> nth=0")
                    await wait(page, LIGHT_READY, label="opened again")
                was = await page.evaluate(LIGHT) is not None
                if how == "Escape":
                    await page.keyboard.press("Escape")
                elif how == "backdrop":
                    await page.mouse.click(6, 300)
                else:
                    await page.click(".h-light [data-h-light-close]")
                await page.wait_for_timeout(250)
                closes[how] = {"closed": was and await page.evaluate(LIGHT) is None, "focus": await page.evaluate(FOCUS_KEY),
                               "card": await page.evaluate("() => !document.getElementById('rb').hidden")}
                check(failures, closes[how]["closed"] and closes[how]["focus"] == th[0]["key"] and closes[how]["card"],
                      f"{how} closes the large view, the focus back on the thumbnail, the card open: {closes[how]}")
        # files the session sent with SendUserFile (ticket 2026-10-20-jui-viz-history-senduserfile-image-no-thumb): the
        # transcript holds only their paths, as measured; a picture is a thumbnail read from its file, opening the same
        # large view; a file no picture is its name; a file no longer there says 消えました and shows no picture
        sent_dir = pathlib.Path(st.out) / "sent"
        sent_dir.mkdir(exist_ok=True)
        (sent_dir / "sample.png").write_bytes(png(240, 160, (60, 160, 90)))
        (sent_dir / "notes.md").write_text("# notes\n")
        files = [str(sent_dir / "sample.png"), str(sent_dir / "notes.md"), str(sent_dir / "gone.png")]
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {
                "id": "m-sent", "role": "assistant", "content": [{"type": "tool_use", "id": "tu-sent", "name": "SendUserFile",
                                                               "input": {"files": files, "caption": "送った見本", "status": "normal", "display": "render"}}]}},
                               ensure_ascii=False) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu-sent", "content": "3 files delivered to user."}]}}, ensure_ascii=False) + "\n")
        SENT = """() => { const b = document.querySelector('[data-rb-hist] .h-sent'); if (!b) return null;
          return { thumbs: [...b.querySelectorAll('.h-thumb')].map((t) => { const i = t.querySelector('img');
            return { w: i.naturalWidth, src: !!i.getAttribute('src'), bad: t.classList.contains('h-thumb-bad'), note: t.querySelector('.h-thumb-note').textContent }; }),
            caption: (b.querySelector('.h-sent-caption') || {}).textContent || '', files: [...b.querySelectorAll('.h-sent-file')].map((x) => x.textContent) }; }"""
        await wait(page, "() => !!document.querySelector('[data-rb-hist] .h-sent')", timeout=20000, label="the SendUserFile row")
        await page.evaluate("() => document.querySelector('[data-rb-hist] .h-sent').scrollIntoView({ block: 'center' })")
        await wait(page, f"() => {{ const g = ({SENT})(); return g && g.thumbs.length === 2 && g.thumbs[0].w > 0 && g.thumbs[1].bad; }}", timeout=15000, label="the sent thumbnails")
        sent = res["sent"] = await page.evaluate(SENT)
        check(failures, sent["thumbs"][0]["w"] == 240 and sent["caption"] == "送った見本" and sent["files"] == ["📎 notes.md"],
              f"the sent picture is a thumbnail of its file, the caption under it, a file no picture by its name: {sent}")
        check(failures, sent["thumbs"][1] == {"w": 0, "src": False, "bad": True, "note": "消えました"}, f"a sent file no longer there: 消えました, no picture: {sent['thumbs'][1]}")
        await page.click("[data-rb-hist] .h-sent .h-thumb >> nth=0")
        await wait(page, "() => { const d = document.querySelector('.h-light'); return !!d && d.querySelector('img').naturalWidth === 240; }", label="the sent picture large")
        res["sentLarge"] = await page.evaluate(LIGHT)
        await page.screenshot(path=str(out / "sent-large.png"))
        await page.keyboard.press("Escape")
        await page.close()
        for scheme in ("light", "dark"):
            ph = await st.page(f"hist-images-phone-{scheme}", **dict(PHONE, color_scheme=scheme))
            await st.open_a(ph)
            await ph.evaluate(INTO_VIEW)
            await ph.wait_for_timeout(1200)
            await ph.screenshot(path=str(out / f"thumbs-390-{scheme}.png"))
            if await ph.locator("[data-rb-hist] .h-thumb").count():
                await ph.click("[data-rb-hist] .h-thumb >> nth=0")
                await wait(ph, LIGHT_READY, label="the large view (phone)")
                lv = res[f"phone-{scheme}"] = await ph.evaluate(LIGHT)
                fits = await ph.evaluate("() => { const i = document.querySelector('.h-light img').getBoundingClientRect(); return i.left >= 0 && i.right <= innerWidth && document.documentElement.scrollWidth <= innerWidth; }")
                check(failures, lv and lv["w"] == 320 and fits, f"390 px {scheme}: the large view fits: {lv} {fits}")
                await ph.screenshot(path=str(out / f"large-390-{scheme}.png"))
            else:
                check(failures, False, f"390 px {scheme}: thumbnails")
            await ph.close()
    except Exception as e:
        failures.append(f"hist-images: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, "hist-images")
        print(f"  hist-images: {time.monotonic() - t0:.0f}s", flush=True)
        if hasattr(st, "out"):
            (pathlib.Path(st.out) / "hist-images-results.json").write_text(dump(res) + "\n")
