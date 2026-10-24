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

import base64
import pathlib
import time

from common import PHONE, T, dump
import json

from hist_wide import A, CWD_A, GONE, Stage, check as _check, png, wait

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
        check(failures, T("hist.img.gone", path=str(GONE)) in text, "the picture file that is gone says so")
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
        files = [str(sent_dir / "sample.png"), str(sent_dir / "notes.md"), str(sent_dir / "gone.png"), str(sent_dir / "gone.md")]
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
        check(failures, sent["thumbs"][0]["w"] == 240 and sent["caption"] == "送った見本" and sent["files"] == ["📎 notes.md", "📎 gone.md"],
              f"the sent picture is a thumbnail of its file, the caption under it, a file no picture by its name: {sent}")
        check(failures, sent["thumbs"][1] == {"w": 0, "src": False, "bad": True, "note": T("hist.img.err.gone")}, f"a sent file no longer there: 消えました, no picture: {sent['thumbs'][1]}")
        await page.click("[data-rb-hist] .h-sent .h-thumb >> nth=0")
        await wait(page, "() => { const d = document.querySelector('.h-light'); return !!d && d.querySelector('img').naturalWidth === 240; }", label="the sent picture large")
        res["sentLarge"] = await page.evaluate(LIGHT)
        await page.screenshot(path=str(out / "sent-large.png"))
        await page.keyboard.press("Escape")
        await wait(page, "() => !document.querySelector('.h-light')", label="the sent picture closed")

        # ---- a closed tool row with a picture in its OUT (2.3.12, requester 10-21: 「閉じてる時でも画像があるってわかるように」;
        # ticket 2026-10-21-jui-viz-hist-tool-row-shows-no-image-when-closed): its head shows the first picture's small
        # thumbnail and 画像 N, read while the row stays closed; a press on it opens the large view, the row stays closed;
        # a press on the row's name opens the row; each picture once in the large view's count; a row with no picture
        # shows nothing; SendUserFile's row closed shows its pictures' count too
        pic3 = png(180, 120, (200, 160, 40))
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {
                "id": "m-read", "role": "assistant", "content": [{"type": "tool_use", "id": "tu-read", "name": "Read", "input": {"file_path": "/work/shot.png"}}]}}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu-read", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                                                                        "data": base64.b64encode(pic3).decode()}}]}]}}) + "\n")
        ROW = """(name) => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === name);
          if (!d) return null; const s = d.querySelector('summary'), mini = s.querySelector('.h-thumb-mini'), img = mini && mini.querySelector('img');
          return { open: d.open, mark: (s.querySelector('.h-imgmark') || {}).textContent || null, mini: !!mini, w: img ? img.naturalWidth : 0 }; }"""
        await wait(page, f"() => !!({ROW})('Read')", timeout=20000, label="the Read row")
        await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'Read').scrollIntoView({ block: 'center' })")
        await wait(page, f"() => {{ const r = ({ROW})('Read'); return r && r.w > 0; }}", timeout=15000, label="the closed row's small thumbnail read")
        r = res["readClosed"] = await page.evaluate(ROW, "Read")
        check(failures, r == {"open": False, "mark": T("hist.img.count", n=1), "mini": True, "w": 180}, f"a closed Read row with a picture: its thumbnail and 画像 1, still closed: {r}")
        plain = res["bashClosed"] = await page.evaluate(ROW, "Bash")
        check(failures, plain and plain["mark"] is None and not plain["mini"], f"a row with no picture shows no mark: {plain}")
        await page.click("[data-rb-hist] .h-tool summary .h-thumb-mini >> nth=-1")
        await wait(page, "() => { const d = document.querySelector('.h-light'); return !!d && d.querySelector('img').naturalWidth === 180; }", label="the closed row's picture large")
        lv = res["readLarge"] = await page.evaluate(LIGHT)
        keys = await page.evaluate("() => new Set([...document.querySelectorAll('[data-rb-hist] .h-thumb')].map((b) => b.dataset.hImg)).size")
        after = await page.evaluate(ROW, "Read")
        check(failures, lv and lv["w"] == 180 and lv["count"].endswith(f"/ {keys}") and not after["open"],
              f"the thumbnail opens the large view (each picture once: {keys}), the row stays closed: {lv} {after}")
        await page.keyboard.press("Escape")
        await wait(page, "() => !document.querySelector('.h-light')", label="closed")
        await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'Read').querySelector('summary .h-tname').click()")
        await wait(page, f"() => {{ const r = ({ROW})('Read'); return r && r.open; }}", label="the row opens from its name")
        opened = await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'Read').querySelectorAll('.h-io .h-thumb').length")
        check(failures, opened == 1, f"opened, the row shows its picture in the OUT: {opened}")
        await page.evaluate("() => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'SendUserFile'); d.open = false; }")
        sent_closed = res["sentClosed"] = await page.evaluate(ROW, "SendUserFile")
        file_mark = await page.evaluate("() => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'SendUserFile'); return (d.querySelector('summary .h-filemark') || {}).textContent || null; }")
        check(failures, sent_closed and sent_closed["mark"] == T("hist.img.count", n=2) and sent_closed["mini"] and file_mark == T("hist.file.count", n=2),
              f"SendUserFile's row closed: its thumbnail, 画像 2 and ファイル 2: {sent_closed} {file_mark!r}")
        # ---- a file that is no picture: its name a link, a press shows it in Finder (2.3.12, requester 10-21: 「画像以外はファイル名出して
        # リンクっぽくして、押したらfinderでそのファイル選択してウィンドウ開く」). The e2e's server writes the path it would show to
        # <viz home>/reveal.log instead of running open -R (no Finder on the screen); a file that is gone says so
        await page.evaluate("() => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'SendUserFile'); d.open = true; d.scrollIntoView({ block: 'center' }); }")
        reveal_log = pathlib.Path(st.home) / ".local" / "state" / "jui-viz" / "reveal.log"
        await page.click("[data-rb-hist] .h-sent .h-filelink >> text=notes.md")
        for _ in range(50):
            if reveal_log.exists() and reveal_log.read_text().strip():
                break
            await page.wait_for_timeout(100)
        shown = res["revealed"] = reveal_log.read_text().splitlines() if reveal_log.exists() else []
        check(failures, shown == [str(sent_dir / "notes.md")], f"a press on notes.md shows that file (the path the call holds): {shown}")
        await page.click("[data-rb-hist] .h-sent .h-filelink >> text=gone.md")
        await wait(page, f"() => [...document.querySelectorAll('[data-rb-hist] .h-sent .h-filelink')].some((b) => b.disabled && b.textContent === {json.dumps('📎 ' + T('hist.file.gone', name='gone.md'))})", label="gone.md says it is gone")
        check(failures, (reveal_log.read_text().splitlines() if reveal_log.exists() else []) == shown, "a file that is gone shows nothing in Finder")
        # ---- the file a Read / Edit / Write / NotebookEdit names (the ruling of 10-21): its name a link in the row's head, there with
        # the row closed; the server takes the path from that call (by its line and id), never from the page
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {
                "id": "m-write", "role": "assistant", "content": [{"type": "tool_use", "id": "tu-write", "name": "Write",
                                                                 "input": {"file_path": str(sent_dir / "notes.md"), "content": "# notes"}}]}}) + "\n")
        HEADFILE = """(name) => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === name);
          const b = d && d.querySelector('summary .h-head-file'); return b ? { open: d.open, text: b.textContent, disabled: b.disabled } : null; }"""
        await wait(page, f"() => !!({HEADFILE})('Write')", timeout=20000, label="the Write row's file link")
        await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-tool')].forEach((d) => { if (/^(Read|Write)$/.test(d.querySelector('summary .h-tname').textContent)) d.open = false; })")
        rl = res["readHeadFile"] = await page.evaluate(HEADFILE, "Read")
        check(failures, rl == {"open": False, "text": "📎 shot.png", "disabled": False}, f"the closed Read row's head names its file as a link: {rl}")
        await page.click("[data-rb-hist] .h-tool summary .h-head-file >> text=shot.png")
        await wait(page, f"() => {{ const r = ({HEADFILE})('Read'); return r && r.disabled; }}", label="shot.png is gone")
        rl2 = res["readHeadFileGone"] = await page.evaluate(HEADFILE, "Read")
        check(failures, rl2 == {"open": False, "text": "📎 " + T("hist.file.gone", name="shot.png"), "disabled": True}, f"a press on it: gone, the row stays closed: {rl2}")
        await page.click("[data-rb-hist] .h-tool summary .h-head-file >> text=notes.md")
        for _ in range(50):
            if reveal_log.exists() and len(reveal_log.read_text().splitlines()) > len(shown):
                break
            await page.wait_for_timeout(100)
        shown2 = res["revealedWrite"] = reveal_log.read_text().splitlines() if reveal_log.exists() else []
        wl = await page.evaluate(HEADFILE, "Write")
        check(failures, shown2 == shown + [str(sent_dir / "notes.md")] and wl and not wl["open"],
              f"a press on the Write row's notes.md shows that file, the row stays closed: {shown2} {wl}")
        await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'Read').scrollIntoView({ block: 'center' })")
        await page.screenshot(path=str(out / "closed-row-mark.png"))

        # ---- a picture sent, then moved (ticket 2026-10-23-viz-sent-pictures-gone-when-the-file-moves; requester: 「画像見えない /
        # claude codeのアプリからなら見えるからバグだと思う」): its hook copies it when the call is made, so after the file moved
        # the history still shows it, read from the copy in the viz home
        (sent_dir / "moved.png").write_bytes(png(200, 120, (40, 90, 200)))
        st.hook(A, CWD_A, hook_event_name="PreToolUse", tool_name="SendUserFile", tool_use_id="tu-moved",
                tool_input={"files": [str(sent_dir / "moved.png")], "caption": "動かした見本", "status": "normal"})
        copy = pathlib.Path(st.home) / ".local" / "state" / "jui-viz" / "sent" / "tu-moved-0.png"
        for _ in range(50):
            if copy.exists():
                break
            await page.wait_for_timeout(100)
        res["copyTaken"] = copy.exists()
        (sent_dir / "moved.png").rename(sent_dir / "moved-away.png")
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {
                "id": "m-moved", "role": "assistant", "content": [{"type": "tool_use", "id": "tu-moved", "name": "SendUserFile",
                                                                "input": {"files": [str(sent_dir / "moved.png")], "caption": "動かした見本", "status": "normal"}}]}},
                               ensure_ascii=False) + "\n")
        MOVED = """() => { const b = [...document.querySelectorAll('[data-rb-hist] .h-sent')].find((x) => (x.querySelector('.h-sent-caption') || {}).textContent === '動かした見本');
          if (!b) return null; const t = b.querySelector('.h-thumb'), i = t && t.querySelector('img');
          return t ? { w: i.naturalWidth, bad: t.classList.contains('h-thumb-bad'), note: (t.querySelector('.h-thumb-note') || {}).textContent || '' } : { none: true }; }"""
        await wait(page, f"() => !!({MOVED})()", timeout=20000, label="the moved picture's row")
        await page.evaluate("() => [...document.querySelectorAll('[data-rb-hist] .h-sent')].pop().scrollIntoView({ block: 'center' })")
        await wait(page, f"() => {{ const g = ({MOVED})(); return g && (g.w > 0 || g.bad); }}", timeout=15000, label="the moved picture's thumbnail")
        mv = res["moved"] = await page.evaluate(MOVED)
        await page.screenshot(path=str(out / "sent-moved.png"))
        check(failures, res["copyTaken"] and mv == {"w": 200, "bad": False, "note": mv.get("note", "")} and not (sent_dir / "moved.png").exists(),
              f"a picture moved after it was sent still shows, from the copy taken when it was sent: copy {res['copyTaken']} {mv}")

        # ---- the requester's row (10-23 01:52, 「なんか１文字づつ縦に表示されるんだけど、これ何？」; ticket 2026-10-23-viz-hist-io-value-
        # one-char-wide): SendUserFile with two pictures, a long caption and long paths. The pictures and the caption took the
        # IN label's column and pressed IN's value to one character a line. IN's value: half the row or more, 20 characters a
        # line or more, a long path wrapped inside it (no sideways scroll)
        long_dir = sent_dir / ("a-very-long-folder-name-with-no-break-" * 3)
        long_dir.mkdir(exist_ok=True)
        for k, rgb in enumerate(((200, 60, 60), (60, 60, 200))):
            (long_dir / f"still-{k}.png").write_bytes(png(160, 100, rgb))
        CAP = "タスクボードの上の欄の直し：前／たたんだ形（標準）／広げた形"
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "message": {
                "id": "m-long", "role": "assistant", "content": [{"type": "tool_use", "id": "tu-long", "name": "SendUserFile",
                                                               "input": {"files": [str(long_dir / "still-0.png"), str(long_dir / "still-1.png")], "caption": CAP}}]}},
                               ensure_ascii=False) + "\n")
        IO = """(cap) => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => (x.querySelector('.h-sent-caption') || {}).textContent === cap);
          if (!d) return null;
          const io = d.querySelector('.h-io'), pre = io.querySelector('.h-code'), probe = document.createElement('span');
          probe.className = 'h-code'; probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;padding:0'; probe.textContent = '0'.repeat(20);
          io.appendChild(probe); const ch = probe.getBoundingClientRect().width / 20; probe.remove();
          const cs = getComputedStyle(pre), inner = pre.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          const cols = getComputedStyle(io).gridTemplateColumns.split(' ').map(parseFloat), em = parseFloat(getComputedStyle(io).fontSize);
          return { preW: Math.round(pre.getBoundingClientRect().width), rowW: Math.round(d.getBoundingClientRect().width), perLine: Math.floor(inner / ch),
                   sideways: pre.scrollWidth > pre.clientWidth + 1, keyEm: Math.round(cols[0] / em * 10) / 10, valueW: Math.round(cols[1] || 0) }; }"""
        await wait(page, f"() => !!({IO})({json.dumps(CAP)})", timeout=20000, label="the long SendUserFile row")
        await page.evaluate("(c) => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => (x.querySelector('.h-sent-caption') || {}).textContent === c).scrollIntoView({ block: 'start' })", CAP)
        await page.wait_for_timeout(800)
        io = res["longIn"] = await page.evaluate(IO, CAP)
        await page.screenshot(path=str(out / "sent-long-in.png"))
        # and the label column is its labels' width (6em or less), the value column the rest (7 tenths of the row or more),
        # narrow and full-screen alike (the requester: 「履歴の量聞き広げてる時は問題ないね」 — the label column took 4 tenths there too)
        def io_ok(g, wide=False):   # full-screen keeps code unwrapped (.rb-wide .h-code): a long path scrolls inside its column there
            return g["preW"] * 2 >= g["rowW"] and g["perLine"] >= 20 and (wide or not g["sideways"]) and g["keyEm"] <= 6 and g["valueW"] * 10 >= g["rowW"] * 7
        check(failures, io_ok(io), f"SendUserFile with two pictures and a long caption, narrow: IN's value 7 tenths of the row, 20 characters a line or more, wrapped; the labels 6em or less: {io}")
        await page.click("#rb [data-rb-wide]")
        await page.wait_for_timeout(900)
        await page.evaluate("(c) => [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => (x.querySelector('.h-sent-caption') || {}).textContent === c).scrollIntoView({ block: 'start' })", CAP)
        await page.wait_for_timeout(400)
        iow = res["longInWide"] = await page.evaluate(IO, CAP)
        await page.screenshot(path=str(out / "sent-long-in-wide.png"))
        check(failures, io_ok(iow, wide=True), f"the same row with the card full-screen: the labels 6em or less, the value 7 tenths of the row: {iow}")
        await page.click("#rb [data-rb-wide]")
        await page.wait_for_timeout(600)
        # an OUT with a picture (the Read of an image above): its pictures span the two columns too, so the labels stay their
        # own width and the values keep the row
        OUTIMG = """() => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('summary .h-tname').textContent === 'Read' && x.querySelector('.h-io > .h-imgs'));
          if (!d) return null; d.open = true; d.scrollIntoView({ block: 'start' });
          const io = d.querySelector('.h-io'), cols = getComputedStyle(io).gridTemplateColumns.split(' ').map(parseFloat), em = parseFloat(getComputedStyle(io).fontSize);
          return { rowW: Math.round(d.getBoundingClientRect().width), keyEm: Math.round(cols[0] / em * 10) / 10, valueW: Math.round(cols[1] || 0), cols: cols.length }; }"""
        for wide in (False, True):
            if wide:
                await page.click("#rb [data-rb-wide]")
                await page.wait_for_timeout(900)
            await wait(page, f"() => !!({OUTIMG})()", timeout=10000, label="the Read row with its picture")
            await page.wait_for_timeout(300)
            oi = res["outImg" + ("Wide" if wide else "")] = await page.evaluate(OUTIMG)
            check(failures, oi["cols"] == 2 and oi["keyEm"] <= 6 and oi["valueW"] * 10 >= oi["rowW"] * 7,
                  f"{'full-screen' if wide else 'narrow'}: a Read whose OUT has a picture: the labels 6em or less, the value 7 tenths of the row: {oi}")
        await page.click("#rb [data-rb-wide]")
        await page.wait_for_timeout(600)

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

        # ---- further back (last: the 45 lines below push A's first words out of the 40 the other parts find A by)
        page = await st.page("hist-images-back")
        await st.open_a(page)
        # ---- further back (2.3.12, ticket 2026-10-21-jui-viz-hist-tab-cannot-scroll-back; the requester's ruling of 10-21):
        # a call stopped by auto mode, then 45 more lines: everything before them leaves the 40 shown. 「もっと前を読む」
        # brings the 40 before back above (the place kept), the stopped call's row says 止められた with the reason, no row
        # twice, and the next refresh keeps them
        denied = ("Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Git Destructive]. "
                  "If you have other tasks that don't depend on this action, continue working on those.")
        now = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())   # noqa: E731
        with open(st.paths[A], "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": now(), "message": {"id": "m-deny", "role": "assistant", "content": [
                {"type": "tool_use", "id": "tu-deny", "name": "Bash", "input": {"command": "git filter-branch --force HEAD", "description": "練習のリポジトリで歴史を書き換える"}}]}}) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": now(), "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu-deny", "content": denied, "is_error": True}]}}) + "\n")
            for k in range(45):
                f.write(json.dumps({"type": "user", "timestamp": now(), "message": {"role": "user", "content": f"後の指示 {k}"}}, ensure_ascii=False) + "\n")
        ROWS = """() => { const b = [...document.querySelectorAll('[data-rb-hist] .h-list-box > *')];
          return { n: b.length, older: !!document.querySelector('[data-rb-hist] [data-h-older]'),
            read: [...document.querySelectorAll('[data-rb-hist] .h-tool summary .h-tname')].filter((x) => x.textContent === 'Read').length,
            deny: [...document.querySelectorAll('[data-rb-hist] .h-tool')].filter((d) => d.querySelector('.h-denied')).map((d) => ({ mark: d.querySelector('.h-denied').textContent, title: d.querySelector('.h-denied').title })),
            last: (b.filter((x) => x.classList.contains('h-user')).pop() || {}).textContent || '' }; }"""
        await wait(page, f"() => ({ROWS})().last.includes('後の指示 44')", timeout=20000, label="the 45 lines")
        r0 = res["backBefore"] = await page.evaluate(ROWS)
        check(failures, r0["older"] and r0["read"] == 0 and not r0["deny"], f"the older rows left the 40 shown, 「もっと前を読む」 is there: {r0}")
        # The stopped call above also puts its card in the cards box under the history (pending: 「実行してよいと伝える」). That
        # box once covered the top of the short list: the pane ran past its grid row under the box, and a real press could
        # not reach the button (Playwright: the card's box "intercepts pointer events", 02:50; ticket 2026-10-21-jui-viz-
        # hist-answered-card-dismiss-and-expand). Pressed as a person presses it, and nothing over it where it is.
        res["olderCovered"] = await page.evaluate("""() => { const b = document.querySelector('[data-rb-hist] [data-h-older]'); b.scrollIntoView({ block: 'nearest' });
          const r = b.getBoundingClientRect(), top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return top && !b.contains(top) ? (top.closest('[data-h-cards]') ? 'the cards box' : top.tagName) : null; }""")
        check(failures, res["olderCovered"] is None, f"nothing over 「もっと前を読む」: {res['olderCovered']}")
        await page.click("[data-rb-hist] [data-h-older]", timeout=5000)
        await wait(page, f"() => ({ROWS})().read === 1", timeout=20000, label="the older rows back")
        r1 = res["backAfter"] = await page.evaluate(ROWS)
        check(failures, r1["n"] > r0["n"] and r1["read"] == 1 and r1["deny"] == [{"mark": T("hist.denied"), "title": T("hist.denied.title", why="[Git Destructive]")}],
              f"further back: the older rows above, each once, the stopped call marked with its reason: {r1}")
        await page.wait_for_timeout(2 * 3000 + 500)   # two refreshes (HIST_POLL_MS = 3000)
        r2 = res["backKept"] = await page.evaluate(ROWS)
        check(failures, r2["read"] == 1 and r2["deny"] == r1["deny"] and r2["n"] >= r1["n"], f"the next refreshes keep what was read further back: {r2}")
        await page.evaluate("() => { const d = [...document.querySelectorAll('[data-rb-hist] .h-tool')].find((x) => x.querySelector('.h-denied')); d.open = true; d.scrollIntoView({ block: 'center' }); }")
        why = await page.evaluate("() => (document.querySelector('[data-rb-hist] .h-denied-why') || {}).textContent || null")
        check(failures, why == "[Git Destructive]", f"opened, the row says why: {why!r}")
        await page.screenshot(path=str(out / "denied-row.png"))
        await page.close()
    except Exception as e:
        failures.append(f"hist-images: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        if getattr(st, "srv", None) is not None:
            await st.stop(failures, "hist-images")
        print(f"  hist-images: {time.monotonic() - t0:.0f}s", flush=True)
        if hasattr(st, "out"):
            (pathlib.Path(st.out) / "hist-images-results.json").write_text(dump(res) + "\n")
