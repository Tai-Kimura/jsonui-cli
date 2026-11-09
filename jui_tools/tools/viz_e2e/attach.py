"""Files attached to a prompt from the robot card's 応答の履歴 tab, end to end (ticket 2026-10-20 prompt-attach). Runs with
`--only attach`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, and a stand-in for
channel.py (hello and poll, as send_prompt.py). One session whose channel can deliver.

Checked: a file chosen with the 添付… button (the file chooser it opens), a file dropped on the box and an image pasted
into the text with Ctrl/⌘+V each go up and show as a chip; the confirmation lists them; the channel gets the text and
one line per file with its absolute path under <viz home>/uploads/<session>/, and each file is there with the same
bytes, 0600; a file over 20 MB is refused on the page and nothing is kept; × takes one off and the server removes it;
the receiver's Read of an attachment asks permission (measured 10-20 10:39) and that request is on the permission board
with the path; the history's line of the prompt shows the files as marks, the pasted image with its thumbnail. A text
too long for /api/prompt: at 8,192 bytes as text, a byte over as prompt.md with the same bytes (many-byte characters too),
its head and whole text in the history, a failure keeps the text, ten attached or over 20 MB stops it with the reason,
the file gone says so. Dark and 390 px; no console error; nothing outside the server.
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

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, T_pattern, Watch, dump, new_page, ready, stamp
from stand_in_channel import StandInChannel

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
    channels: list = []   # our stand-in channels (stand_in_channel.py), closed in finally
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
        # its channel polls on until the suite ends (stand_in_channel.py): one that only said hello was dropped after 60 s
        channels.append(channel := StandInChannel(port, json.loads((state / "server.json").read_text())["token"], S_OK).open())
        check(channel.status == 200, f"hello: {channel.status}")
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
        check(got[3]["err"] and T("hist.attach.big") in got[3]["meta"], f"over 20 MB is refused on the page: {got[3]}")
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
        check(len(T_pattern("hist.confirm.file").findall(preview)) == 3 and preview.startswith("この 3 つを見て"), f"the confirmation lists the files: {preview!r}")
        await page.wait_for_timeout(500)
        await page.click("[data-h-go]")
        await wait(page, f"() => new RegExp({json.dumps('^' + T_pattern('hist.state.sending').pattern)}).test(document.querySelector('[data-h-compose] [data-h-state]').textContent)", label="送信中")
        check(await page.evaluate(CHIPS) == [], "the chips go once sent")
        inbox = channel.take_prompts(timeout=30)
        text = inbox[0]["text"] if inbox else ""
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
        await wait(page, f"() => new RegExp({json.dumps('^' + T_pattern('hist.state.arrived').pattern)}).test(document.querySelector('[data-h-compose] [data-h-state]').textContent)", timeout=15000, label="届いた")
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
        check(res["goneMark"] == {"note": T("hist.img.err.gone"), "src": False}, f"a gone image: 消えました, no picture: {res['goneMark']}")
        await page.click(THUMB)
        await wait(page, f"() => {{ const g = ({LIGHT_IMG})(); return g && g.note === {json.dumps(T('hist.img.err.gone'))}; }}", label="the large view says 消えました")
        res["goneLight"] = await page.evaluate(LIGHT_IMG)
        check(not res["goneLight"]["src"], f"the large view shows no broken picture: {res['goneLight']}")
        await page.screenshot(path=str(out / "attach-gone.png"))
        await page.keyboard.press("Escape")
        # A text too long for /api/prompt goes as a file (ticket 2026-11-04-viz-long-prompt-goes-as-a-file)
        STATE = "() => { const s = document.querySelector('[data-h-compose] [data-h-state]'); return { phase: s.dataset.hPhase, text: s.textContent, err: s.classList.contains('h-compose-err'), send: document.querySelector('[data-h-send]').disabled }; }"
        AREA = "() => document.querySelector('[data-h-text]').value"
        async def put(p, text):
            await p.evaluate("(t) => { const a = document.querySelector('[data-h-text]'); a.value = t; a.dispatchEvent(new Event('input', { bubbles: true })); }", text)
        async def phase_is(p, want, label):
            await wait(p, "(w) => document.querySelector('[data-h-compose] [data-h-state]').dataset.hPhase === w", arg=want, label=label)
        async def press_send(p):
            await p.click("[data-h-send]")
            await p.wait_for_timeout(500)   # the confirmation takes no click in its first moment
            await p.click("[data-h-go]")
        def take():
            got = channel.take_prompts(timeout=30)
            return got[0]["text"] if got else ""
        def kept_md():
            return sorted(uploads.glob("*.md"))
        await page.evaluate("() => document.querySelectorAll('[data-h-attach] .h-attach-x').forEach((b) => b.click())")
        await wait(page, f"() => ({CHIPS})().length === 0", label="no chips before the long text")
        room = 8192 - len(json.dumps({"sessionId": S_OK, "text": "", "attachments": []}, separators=(",", ":")).encode())
        # just under: the plain way, the box as it was
        before = kept_md()
        under = "x" * room
        await put(page, under)
        await page.wait_for_timeout(300)
        r = res["longUnder"] = await page.evaluate(STATE)
        check(r["phase"] != "asfile" and not r["send"], f"at 8,192 bytes the text goes as text: {r}")
        await press_send(page)
        await wait(page, "() => document.querySelector('[data-h-text]').value === ''", label="the text at the limit sent")
        check(take() == under and kept_md() == before, "at 8,192 bytes the channel gets the text itself and nothing is kept")
        # just over: a file, with the same bytes
        over = "x" * (room + 1)
        await put(page, over)
        await phase_is(page, "asfile", "a text one byte over says it goes as a file")
        r = res["longOver"] = await page.evaluate(STATE)
        check(not r["send"] and not r["err"] and T_pattern("hist.state.asfile").search(r["text"]), f"one byte over: not stopped, not an error, says so: {r}")
        await page.click("[data-h-send]")
        preview = await page.evaluate("() => document.querySelector('[data-h-preview]').textContent")
        res["longPreview"] = preview
        check(T_pattern("hist.confirm.asfile").search(preview), f"the confirmation says it goes as a file: {preview[-200:]!r}")
        await page.screenshot(path=str(out / "long-confirm.png"))
        await page.wait_for_timeout(500)
        await page.click("[data-h-go]")
        await wait(page, "() => document.querySelector('[data-h-text]').value === ''", label="the long text sent")
        lines = take().split("\n")
        m = LINE_RE.match(lines[1]) if len(lines) == 2 else None
        LONG = re.search(r"const LONG_PROMPT_LINE = '([^']+)';", (jt / "jui_cli" / "viz" / "web" / "js" / "55-history.js").read_text(encoding="utf-8")).group(1)
        check(lines[0] == LONG and m and m.group(4) == "prompt.md" and m.group(5) == "text/markdown", f"the channel gets the fixed line and the file: {lines}")
        check(m and pathlib.Path(m.group(1)).read_bytes() == over.encode(), "one byte over: the file has the text's bytes")
        # only many-byte characters, cut nowhere
        wide = "日本語の依頼😀\n" * 2000
        await put(page, wide)
        await phase_is(page, "asfile", "the wide text goes as a file")
        await press_send(page)
        await wait(page, "() => document.querySelector('[data-h-text]').value === ''", label="the wide text sent")
        sent_long = take()
        lines = sent_long.split("\n")
        m = LINE_RE.match(lines[1]) if len(lines) == 2 else None
        check(m and pathlib.Path(m.group(1)).read_bytes() == wide.encode("utf-8"), "many-byte characters only: the file has the text's bytes exactly")
        wide_path = pathlib.Path(m.group(1)) if m else None
        await wait(page, "() => document.getElementById('ticker').textContent.includes('日本語の依頼😀')", label="the event log says the person's words")
        check(LONG not in await page.evaluate("() => document.getElementById('ticker').textContent"), "the event log does not say the fixed line")
        # the history: the person's words, not the fixed line; the whole text behind a press; arrived
        with open(transcript, "a") as f:
            f.write(json.dumps({"type": "user", "isMeta": True, "promptSource": "system", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "origin": {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}, "userType": "external", "entrypoint": "cli",
                                "message": {"role": "user", "content": f'<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">\n{sent_long}\n</channel>'}},
                               ensure_ascii=False) + "\n")
        LONGBOX = "[data-rb-hist] .h-long"
        await wait(page, f"() => {{ const h = document.querySelector('{LONGBOX} .h-long-head'); return h && h.textContent.startsWith('日本語の依頼'); }}", timeout=15000, label="the long prompt's head in the history")
        await wait(page, "(l) => new RegExp(l).test(document.querySelector('[data-h-compose] [data-h-state]').textContent)", arg="^" + T_pattern("hist.state.arrived").pattern, timeout=15000, label="the long prompt arrived")
        r = res["longHistory"] = await page.evaluate(f"() => ({{ line: document.querySelector('[data-rb-hist]').textContent.includes({json.dumps(LONG)}), head: document.querySelector('{LONGBOX} .h-long-head').textContent.length, marks: [...document.querySelectorAll('[data-rb-hist] .h-attach-sent li .h-attach-name')].map((x) => x.textContent) }})")
        check(not r["line"] and r["head"] == 301 and any("prompt.md" in x for x in r["marks"]), f"the history shows the head, not the fixed line, and the file's mark: {r}")
        await page.screenshot(path=str(out / "long-history.png"))
        await page.click(f"{LONGBOX} .h-long-more")
        whole = await page.evaluate(f"() => document.querySelector('{LONGBOX} .h-long-head').textContent")
        check(whole == wide, f"a press shows the whole text: {len(whole)} of {len(wide)}")
        await page.screenshot(path=str(out / "long-history-open.png"))
        # a failure keeps the text: the file refused, then the prompt refused (and its file taken back)
        kept = "失敗しても消えない文" * 400
        said_before = len(watch.console)
        await page.route("**/api/attach", lambda route: route.fulfill(status=500, body="no room"))
        await put(page, kept)
        await phase_is(page, "asfile", "the text for the failures")
        await press_send(page)
        await phase_is(page, "error", "the file refused")
        check(await page.evaluate(AREA) == kept, "the file refused: the text is still in the box")
        await page.unroute("**/api/attach")
        before = kept_md()
        await page.route("**/api/prompt", lambda route: route.fulfill(status=500, body="no room"))
        await press_send(page)
        await wait(page, "() => document.querySelector('[data-h-compose] [data-h-state]').textContent.includes('no room') && !!document.querySelector('[data-h-confirm]').hidden", label="the prompt refused")
        check(await page.evaluate(AREA) == kept, "the prompt refused: the text is still in the box")
        for _ in range(50):
            if kept_md() == before:
                break
            time.sleep(0.1)
        check(kept_md() == before, "the prompt refused: the file that went up is taken back")
        await page.unroute("**/api/prompt")
        watch.console[said_before:] = [c for c in watch.console[said_before:] if "status of 500" not in c]   # the two refused here on purpose
        await phase_is(page, "error", "the failure stays while the text is the one that failed")
        await put(page, kept + "。")
        await phase_is(page, "asfile", "a changed text: the line says what this one will do")
        # ten attached: the long text would be the eleventh
        await page.evaluate("""() => {
          const box = document.querySelector('[data-h-compose]'), dt = new DataTransfer();
          for (let i = 0; i < 10; i += 1) dt.items.add(new File(['x'], `n${i}.txt`, { type: 'text/plain' }));
          box.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
        }""")
        await chips_ready(page, 10, "ten chips")
        await phase_is(page, "many", "the long text with ten attached")
        r = res["longMany"] = await page.evaluate(STATE)
        check(r["send"] and r["err"] and T_pattern("hist.state.asfile.many").search(r["text"]), f"the eleventh: stopped, says why: {r}")
        await page.click("[data-h-attach] li:nth-child(1) .h-attach-x")
        await phase_is(page, "asfile", "one taken off")
        await page.evaluate("() => document.querySelectorAll('[data-h-attach] .h-attach-x').forEach((b) => b.click())")
        await wait(page, f"() => ({CHIPS})().length === 0", label="no chips after the ten")
        # over the receiver's Read limit (256 KB) it still goes, and says what that means first
        await put(page, "x" * (256 * 1024))
        await phase_is(page, "asfile", "256 KB: nothing more to say")
        await put(page, "x" * (256 * 1024 + 1))
        await phase_is(page, "asfile-big", "a byte over 256 KB")
        r = res["longOverRead"] = await page.evaluate(STATE)
        check(not r["send"] and not r["err"] and T_pattern("hist.state.asfile.big").search(r["text"]), f"over 256 KB: not stopped, says the receiver may not read all of it: {r}")
        await page.screenshot(path=str(out / "long-over-read.png"))
        # at the file's limit it can go; a byte over it is stopped and the text stays
        await page.evaluate("() => { const a = document.querySelector('[data-h-text]'); a.value = 'x'.repeat(20 * 1024 * 1024); a.dispatchEvent(new Event('input', { bubbles: true })); }")
        await phase_is(page, "asfile-big", "20 MB goes as a file, and says the receiver may not read all of it")
        await page.evaluate("() => { const a = document.querySelector('[data-h-text]'); a.value = 'x'.repeat(20 * 1024 * 1024 + 1); a.dispatchEvent(new Event('input', { bubbles: true })); }")
        await phase_is(page, "long", "a byte over 20 MB")
        r = res["longBig"] = await page.evaluate(STATE)
        check(r["send"] and r["err"] and T_pattern("hist.state.long").search(r["text"]), f"over 20 MB: stopped, says why: {r}")
        check(await page.evaluate("() => document.querySelector('[data-h-text]').value.length") == 20 * 1024 * 1024 + 1, "over 20 MB: the text stays")
        await page.screenshot(path=str(out / "long-too-big.png"))
        await put(page, "")
        # the file gone (an hour after its session ended): the history says so
        if wide_path:
            wide_path.unlink()
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 1", label="the session after the reload")
        await open_robot(page)
        await wait(page, f"(g) => {{ const h = document.querySelector('{LONGBOX} .h-long-head'); return h && h.textContent === g; }}", arg=T("hist.long.gone"), timeout=15000, label="the gone long prompt says so")
        await page.emulate_media(color_scheme="dark")
        await page.set_input_files("[data-h-file]", str(files / "仕様メモ.md"))
        await chips_ready(page, 1, "a chip in dark")
        await page.screenshot(path=str(out / "chips-dark.png"))
        phone = await new_page(browser, watch, "attach-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 1", label="the phone's session")
        await open_robot(phone)
        await put(phone, "x" * 9000)
        await phase_is(phone, "asfile", "the phone's state line for a long text")
        res["phoneLong"] = await phone.evaluate("() => { const s = document.querySelector('[data-h-compose] [data-h-state]').getBoundingClientRect(); return { left: s.left, right: s.right, width: innerWidth, h: s.height }; }")
        check(res["phoneLong"]["left"] >= 0 and res["phoneLong"]["right"] <= res["phoneLong"]["width"] and res["phoneLong"]["h"] > 0, f"390 px: the long text's state line is inside the screen: {res['phoneLong']}")
        await phone.screenshot(path=str(out / "phone-long.png"))
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
        for channel in channels:
            channel.close()
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
