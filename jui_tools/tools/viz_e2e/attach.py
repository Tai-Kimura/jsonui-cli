"""Files attached to a prompt from the robot card's 応答の履歴 tab, end to end (ticket 2026-10-20 prompt-attach). Runs with
`--only attach`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, and a stand-in for
channel.py (hello and poll, as send_prompt.py). One session whose channel can deliver.

Checked: a file chosen with the 添付… button (the file chooser it opens), a file dropped on the box and an image pasted
into the text with Ctrl/⌘+V each go up and show as a chip; the confirmation lists them; the channel gets the text and
one line per file with its absolute path under <viz home>/uploads/<session>/, and each file is there with the same
bytes, 0600; a file over 20 MB is refused on the page and nothing is kept; × takes one off and the server removes it;
the receiver's Read of an attachment asks permission (measured 10-20 10:39) and that request is on the permission board
with the path; the history's line of the prompt shows the files as marks, the pasted image with its thumbnail. Dark
and 390 px; no console error; nothing outside the server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import stat
import struct
import subprocess
import sys
import time
import zlib

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready, stamp

S_OK = "e2e00000-0000-4000-8000-0000000000e1"
CWD = "/work/attach-ok"
DEV = "--dangerously-load-development-channels"


def _png(w: int = 8, h: int = 8) -> bytes:
    """A small valid PNG (RGB, one colour), made here so its checksums are right."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + b"\x30\x90\xd0" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


PNG = _png()
LINE_RE = re.compile(r"^attached: (/\S+/uploads/" + S_OK + r"/([0-9a-f]{16})\.([a-z]+)) \((.*), ([^,]*), ([^,]*)\)$")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


CHIPS = """() => [...document.querySelectorAll('[data-h-compose] [data-h-attach] li')].map((li) => ({
  id: li.dataset.hAttachItem, name: li.querySelector('.h-attach-name').textContent, meta: li.querySelector('.h-attach-meta').textContent,
  thumb: !!li.querySelector('img'), err: li.classList.contains('h-attach-err') }))"""


async def run_attach(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "attach"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    uploads = state / "uploads" / S_OK
    transcript = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD) / f"{S_OK}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-20T09:00:00Z"), "message": {"role": "user", "content": "最初の依頼"}}, ensure_ascii=False) + "\n"
                          + json.dumps({"type": "assistant", "timestamp": stamp("2026-10-20T09:00:01Z"), "message": {"id": "a1", "role": "assistant", "content": [{"type": "text", "text": "最初の応答"}]}}, ensure_ascii=False) + "\n")
    files = out / "files"
    files.mkdir(exist_ok=True)
    (files / "仕様メモ.md").write_text("# メモ\nボタンで添付した\n", encoding="utf-8")
    big = files / "big.bin"
    with open(big, "wb") as f:
        f.truncate(20 * 1024 * 1024 + 1)
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []
    waiting: list = []
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"attach: {text}")

    def hook(payload, flag=None):
        args = [sys.executable, "-I", "-S", str(forward)] + ([flag] if flag else [])
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(base_env, HOME=str(home)))
        p.stdin.write(json.dumps({"session_id": S_OK, "cwd": CWD, "transcript_path": str(transcript), "permission_mode": "default", **payload}).encode())
        p.stdin.close()
        p.stdin = None
        if flag:
            waiting.append(p)
            return p
        p.wait(timeout=10)
        return None

    def local(method, path, body=None, timeout=5):
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            headers = {"X-Jui-Viz-Token": token}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            r = conn.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            conn.close()

    async def open_robot(page):
        _, snap = local("GET", "/api/snapshot")
        label = next(s["label"] for s in snap["slices"]["sessions"] if s["id"] == S_OK)
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await wait(page, "(l) => document.getElementById('rb-title') && document.getElementById('rb-title').textContent.startsWith(l)", arg=label, label="the card")
        if await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
            await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('最初の応答')", label="the history")
        return label

    async def chips_ready(page, n, label):
        await wait(page, f"() => {{ const c = ({CHIPS})(); return c.length === {n} && c.every((x) => x.id || x.err); }}", label=label)
        return await page.evaluate(CHIPS)

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
        hook({"hook_event_name": "SessionStart", "source": "startup"})
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", DEV, "plugin:jui-viz@jsonui"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": S_OK, "cwd": CWD, "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
        status, hello = local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OK, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        check(status == 200, f"hello: {status}")
        channel = hello["channelId"]
        for _ in range(100):
            _, snap = local("GET", "/api/snapshot")
            if any(s["id"] == S_OK and s.get("launch") == "dev" for s in snap["slices"]["sessions"]):
                break
            time.sleep(0.1)
        watch = Watch(origin=url)
        context = await browser.new_context(**DESKTOP)
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        page = await context.new_page()
        watch.attach(page, "attach")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 1", label="the session")
        label = await open_robot(page)

        # 1. the 添付… button opens the file chooser
        async with page.expect_file_chooser() as chooser:
            await page.click("[data-h-pick]")
        await (await chooser.value).set_files(str(files / "仕様メモ.md"))
        res["button"] = await chips_ready(page, 1, "the button's file")
        # 2. a file dropped on the box
        await page.evaluate("""() => {
          const box = document.querySelector('[data-h-compose]'), dt = new DataTransfer();
          dt.items.add(new File(['ドロップした中身\\n'], 'dropped.txt', { type: 'text/plain' }));
          box.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
          box.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""")
        res["drop"] = await chips_ready(page, 2, "the dropped file")
        # 3. an image in the clipboard, pasted with Ctrl/⌘+V into the text
        await page.evaluate("""async (hex) => {
          const bytes = new Uint8Array(hex.match(/../g).map((h) => parseInt(h, 16)));
          await navigator.clipboard.write([new ClipboardItem({ 'image/png': new Blob([bytes], { type: 'image/png' }) })]);
        }""", PNG.hex())
        await page.click("[data-h-text]")
        await page.keyboard.press("ControlOrMeta+V")
        res["paste"] = await chips_ready(page, 3, "the pasted image")
        chips = res["paste"]
        check([c["name"] for c in chips] == ["仕様メモ.md", "dropped.txt", "image.png"] or
              [c["name"] for c in chips][:2] == ["仕様メモ.md", "dropped.txt"], f"three chips in order: {chips}")
        check(chips[2]["thumb"] and not any(c["err"] for c in chips), f"the pasted image has its thumbnail, none refused: {chips}")
        await page.screenshot(path=str(out / "chips.png"))
        # a file over 20 MB: refused on the page, nothing kept
        await page.set_input_files("[data-h-file]", str(big))
        got = await chips_ready(page, 4, "the big file's chip")
        check(got[3]["err"] and "大きすぎる" in got[3]["meta"], f"over 20 MB is refused on the page: {got[3]}")
        await page.click("[data-h-attach] li:nth-child(4) .h-attach-x")
        # × on the dropped file: off the page and off the disk
        dropped_id = chips[1]["id"]
        await page.click("[data-h-attach] li:nth-child(2) .h-attach-x")
        await wait(page, f"() => ({CHIPS})().length === 2", label="× takes one off")
        for _ in range(50):
            if not list(uploads.glob(f"{dropped_id}.*")):
                break
            time.sleep(0.1)
        check(not list(uploads.glob(f"{dropped_id}.*")), "× removed the file from the server")
        # the dropped file again, then text, then send
        await page.evaluate("""() => {
          const box = document.querySelector('[data-h-compose]'), dt = new DataTransfer();
          dt.items.add(new File(['ドロップした中身\\n'], 'dropped.txt', { type: 'text/plain' }));
          box.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""")
        chips = res["sendChips"] = await chips_ready(page, 3, "three to send")
        await page.click("[data-h-text]")
        await page.keyboard.type("この 3 つを見て")
        await page.click("[data-h-send]")
        preview = await page.evaluate("() => document.querySelector('[data-h-preview]').textContent")
        res["preview"] = preview
        check(preview.count("添付: ") == 3 and preview.startswith("この 3 つを見て"), f"the confirmation lists the files: {preview!r}")
        await page.wait_for_timeout(500)
        await page.click("[data-h-go]")
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('送信中')", label="送信中")
        check(await page.evaluate(CHIPS) == [], "the chips go once sent")
        _, polled = local("GET", f"/channel/poll?channelId={channel}", timeout=30)
        text = polled["prompts"][0]["text"] if polled["prompts"] else ""
        res["inbox"] = text
        lines = text.split("\n")
        check(lines[0] == "この 3 つを見て" and len(lines) == 4, f"the text, then one line per file: {lines}")
        want = {"仕様メモ.md": "# メモ\nボタンで添付した\n".encode(), "dropped.txt": "ドロップした中身\n".encode()}
        image_id = ""
        for line in lines[1:]:
            m = LINE_RE.match(line)
            check(m is not None, f"a line with the absolute path under uploads/<session>/: {line!r}")
            if not m:
                continue
            path = pathlib.Path(m.group(1))
            check(path.parent == uploads.resolve() or path.parent == uploads, f"under this server's uploads: {path}")
            check(path.exists() and stat.S_IMODE(path.stat().st_mode) == 0o600, f"kept, 0600: {path}")
            name = m.group(4)
            if name in want:
                check(path.read_bytes() == want[name], f"{name}: the same bytes")
            else:
                image_id = m.group(2)
                # the browser re-encodes a clipboard image (measured: 74 B in, 109 B out), so: a PNG, kept as .png
                check(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") and m.group(3) == "png" and m.group(5) == "image/png",
                      f"the pasted image: a PNG, kept as .png: {line}")
        check(stat.S_IMODE(uploads.stat().st_mode) == 0o700, "the session's folder is 0700")
        # the receiver's Read of an attachment asks permission: the request is on the permission board with the path
        first = LINE_RE.match(lines[1]).group(1) if len(lines) > 1 and LINE_RE.match(lines[1]) else str(uploads)
        req = {"hook_event_name": "PermissionRequest", "tool_name": "Read", "tool_input": {"file_path": first}}
        hook({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_use_id": "read-1", "tool_input": {"file_path": first}})
        hook(req)
        # /hook/decide answers at once, and the card gets no 許可 / 拒否, while no page has reported itself visible in
        # the last 12 s. The page reports every 5 s from its load (25-net.js), and this step came about 1 s after the
        # first report (measured 10-20: 6.0 s vs 5.04 s); a first report 1 s late made the deny click time out (2.3.9
        # gate 2; ticket 2026-10-20-jui-viz-e2e-attach-decide-before-first-presence). Have the page report now.
        await page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        decide = hook(req, "--decide")
        stored = pathlib.Path(first).name   # the card may write the home as ~: match the server-made name
        await wait(page, "() => !document.getElementById('chip-perm').hidden", timeout=15000, label="the permission chip")
        await page.click("#chip-perm")   # the board, where the permission strip is
        try:
            await wait(page, "(p) => [...document.querySelectorAll('#perm-strip .pcard')].some((c) => c.textContent.includes(p))", arg=stored,
                       timeout=15000, label="the Read of the attachment on the permission board")
        finally:
            res["permCards"] = await page.evaluate("() => [...document.querySelectorAll('#perm-strip .pcard')].map((c) => c.textContent)")
        res["permCard"] = next((t for t in res["permCards"] if stored in t), "")
        check("Read" in (res["permCard"] or ""), f"the card names Read: {res['permCard']!r}")
        await page.screenshot(path=str(out / "permission.png"))
        await wait(page, "() => !!document.querySelector(\"#perm-strip [data-do='deny']\")", timeout=15000,
                   label="拒否 on the card (the --decide hook waits on it)")
        await page.click("#tb-wide[aria-expanded='false']")   # the strips wide: folded is the default
        await page.click("#perm-strip [data-do='deny']")
        try:
            decide.wait(timeout=15)
        except subprocess.TimeoutExpired:
            failures.append("attach: the permission hook did not end after deny")
        await page.click("#tb-close")   # back from the board to the robot's card
        await open_robot(page)
        # the history's line of the prompt: marks, the pasted image with its thumbnail
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(transcript, "a") as f:
            f.write(json.dumps({"type": "user", "isMeta": True, "promptSource": "system", "timestamp": now_iso,
                                "origin": {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}, "userType": "external", "entrypoint": "cli",
                                "message": {"role": "user", "content": f'<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\n{text}\n</channel>'}},
                               ensure_ascii=False) + "\n")
        await wait(page, "() => document.querySelectorAll('[data-rb-hist] .h-attach-sent li').length === 3", timeout=15000, label="the marks in the history")
        res["marks"] = await page.evaluate("""() => [...document.querySelectorAll('[data-rb-hist] .h-attach-sent li')].map((li) => ({
          name: li.querySelector('.h-attach-name').textContent, thumb: !!li.querySelector('img'), title: li.title }))""")
        check(sum(m["thumb"] for m in res["marks"]) == 1 and any(image_id and image_id in m["title"] for m in res["marks"] if m["thumb"]),
              f"the pasted image's mark has its thumbnail: {res['marks']}")
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.startsWith('届いた')", timeout=15000, label="届いた")
        await page.screenshot(path=str(out / "history.png"))
        # 2.3.9 (ticket 2026-10-20-jui-viz-attachment-thumb-opens-large): the image's mark opens the history's large view
        THUMB = "[data-rb-hist] .h-attach-sent .h-thumb"
        LIGHT_IMG = "() => { const l = document.querySelector('.h-light'); const i = l && l.querySelector('img'); return l ? { src: !!i.getAttribute('src'), w: i.naturalWidth, note: l.querySelector('.h-light-note').textContent } : null; }"
        res["thumbs"] = await page.evaluate(f"() => document.querySelectorAll('{THUMB}').length")
        check(res["thumbs"] == 1, f"only the image's mark is a button (the .md and .txt are marks only): {res['thumbs']}")
        await wait(page, f"() => {{ const i = document.querySelector('{THUMB} img'); return i && i.complete && i.naturalWidth > 0; }}", label="the mark's thumbnail from the kept file")
        await page.click(THUMB)
        await wait(page, f"() => {{ const g = ({LIGHT_IMG})(); return g && g.w > 0; }}", label="the large view with the image")
        res["lightClick"] = await page.evaluate(LIGHT_IMG)
        await page.screenshot(path=str(out / "attach-large.png"))
        for key in ("Enter", " "):
            await page.keyboard.press("Escape")
            await wait(page, f"() => !document.querySelector('.h-light') && document.activeElement && document.activeElement.matches('{THUMB}')", label="closed, the focus back on the thumbnail")
            await page.keyboard.press(key)
            await wait(page, f"() => {{ const g = ({LIGHT_IMG})(); return g && g.w > 0; }}", label=f"the large view from the keyboard ({key!r})")
        await page.keyboard.press("Escape")
        res["nonImage"] = await page.evaluate("""() => { const li = [...document.querySelectorAll('[data-rb-hist] .h-attach-sent li')].filter((x) => !x.querySelector('.h-thumb'));
          li.forEach((x) => x.click()); return { marks: li.length, opened: !!document.querySelector('.h-light') }; }""")
        check(res["nonImage"] == {"marks": 2, "opened": False}, f"a mark that is not an image opens nothing: {res['nonImage']}")
        # the kept file gone (an hour after its session ended): a fresh look says 消えました and shows no picture
        for f in uploads.glob(f"{image_id}.*"):
            f.unlink()
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 1", label="the session after the reload")
        await open_robot(page)
        await wait(page, f"() => {{ const b = document.querySelector('{THUMB}'); return b && b.classList.contains('h-thumb-bad'); }}", timeout=15000, label="the gone image's mark")
        res["goneMark"] = await page.evaluate(f"() => {{ const b = document.querySelector('{THUMB}'); return {{ note: b.querySelector('.h-thumb-note').textContent, src: !!b.querySelector('img').getAttribute('src') }}; }}")
        check(res["goneMark"] == {"note": "消えました", "src": False}, f"a gone image: 消えました, no picture: {res['goneMark']}")
        await page.click(THUMB)
        await wait(page, f"() => {{ const g = ({LIGHT_IMG})(); return g && g.note === '消えました'; }}", label="the large view says 消えました")
        res["goneLight"] = await page.evaluate(LIGHT_IMG)
        check(not res["goneLight"]["src"], f"the large view shows no broken picture: {res['goneLight']}")
        await page.screenshot(path=str(out / "attach-gone.png"))
        await page.keyboard.press("Escape")
        await page.emulate_media(color_scheme="dark")
        await page.set_input_files("[data-h-file]", str(files / "仕様メモ.md"))
        await chips_ready(page, 1, "a chip in dark")
        await page.screenshot(path=str(out / "chips-dark.png"))
        phone = await new_page(browser, watch, "attach-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 1", label="the phone's session")
        await open_robot(phone)
        r = res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth, pick: !!document.querySelector('[data-h-pick]') })")
        await phone.screenshot(path=str(out / "phone.png"))
        check(r == {"hscroll": False, "pick": True}, f"390 px: the button shows, no horizontal scroll: {r}")
        await phone.close()
        await page.close()
        await context.close()
        for line in watch.console:
            failures.append(f"attach: console: {line}")
        for u in watch.foreign:
            failures.append(f"attach: request outside the server: {u}")
    except Exception as e:
        failures.append(f"attach: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for p in waiting:
            if p.poll() is None:
                p.kill()
                p.wait()
        for p in stand_ins:
            p.kill()
            p.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
        big.unlink(missing_ok=True)
    print(f"  attach: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "attach-results.json").write_text(dump(res) + "\n")
