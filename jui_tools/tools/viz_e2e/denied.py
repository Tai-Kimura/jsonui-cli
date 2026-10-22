"""A tool call stopped by auto mode, and 「実行してよいと伝える」 from the page, end to end (ticket
2026-10-20-jui-viz-auto-mode-denial-approve-from-page). Runs with `--only denied`.

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py for the hooks, a stand-in for
channel.py (hello and poll, as send_prompt.py), and notify.py's stand-ins for Notification and AudioContext.

Checked: one call reported by the PermissionDenied hook and by its transcript makes one card; a call only the
transcript reports makes its own; each card rings one notification and one chime; the 止められた chip counts them;
「実行してよいと伝える…」 opens a confirmation with the exact words and the note that the receiver may ask in the
terminal, やめる sends nothing, 送る puts those words on that
session's channel once and the card says so; a session whose channel cannot take a prompt gets the reason and no
button, and そのまま closes its card. Dark and 390 px; no console error; nothing outside the server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, PHONE, T, T_pattern, Watch, dump, new_page, ready, stamp
from notify import CHIMES, SHOWN, STUB

S_OK = "e2e00000-0000-4000-8000-0000000000f1"
S_NO = "e2e00000-0000-4000-8000-0000000000f2"
CWDS = {S_OK: "/work/denied-ok", S_NO: "/work/denied-no"}
DEV = "--dangerously-load-development-channels"
CMD1 = "gh pr merge 242 --squash --delete-branch"
CMD2 = "git push --force origin main"
PREFIX = "Permission for this action was denied by the Claude Code auto mode classifier."
WHY1, WHY2 = "[Unrequested Commit in a Connected App]", "[Irreversible Remote Destruction]"


# The orchestrator's ruling (10-20 15:30): what is claimed is the words reaching the receiver with the card's call and reason as
# they are — not that it goes on (that is the requester's one real check)
def words(cmd: str, why: str) -> str:
    """The words a card sends, as viz/denials.py words them in the run's language: where they come from, the call,
    the reason, then the two lines that say it was judged fine and how to answer if not."""
    return "\n".join([T("srv.denial.source"), T("srv.denial.what", what=f"Bash: {cmd}"), T("srv.denial.why", why=why),
                      T("srv.denial.judged"), T("srv.denial.again")])
# The strips on top folded or wide (ticket 2026-10-22-viz-taskboard-top-strips-hide-the-columns): what the board shows of each.
FOLD = """() => { const kb = document.querySelector('#tb .kb-body'), btn = document.getElementById('tb-wide'), heads = [...document.querySelectorAll('#kanban .kcol .ktab')];
  return { fold: kb.classList.contains('tb-fold'), wide: kb.classList.contains('tb-wide'), btn: btn.textContent, pressed: btn.getAttribute('aria-pressed'),
           lines: [...document.querySelectorAll('#denied-strip .ps-line')].map((l) => l.dataset.psGo),
           cards: [...document.querySelectorAll('#denied-strip [data-dcard]')].filter((c) => c.offsetParent).length, heads: heads.length,
           headsIn: heads.filter((h) => { const r = h.getBoundingClientRect(); return r.height > 0 && r.top >= 0 && r.bottom <= innerHeight; }).length,
           headsBottom: Math.round(Math.max(0, ...heads.map((h) => h.getBoundingClientRect().bottom))),
           kbH: Math.round(document.getElementById('kanban').getBoundingClientRect().height),
           // the handle hangs from the strips' bottom edge (the requester on the first look: what grows is said where it grows)
           handleGap: (() => { const last = ['perm-strip', 'denied-strip', 'q-strip'].map((id) => document.getElementById(id)).find((e) => !e.hidden);
             return last ? Math.round(btn.getBoundingClientRect().top - last.getBoundingClientRect().bottom) : null; })() }; }"""
REPLY = "チャンネルから来た破壊的な依頼なので、端末で直接確認してください。"
CARDS = """(where) => [...document.querySelectorAll(`${where} [data-dcard]`)].map((c) => ({ id: c.dataset.dcard, text: c.textContent,
  ask: !!c.querySelector('[data-dask]'), go: !!c.querySelector('[data-dgo]'), dismiss: !!c.querySelector('[data-ddismiss]'),
  prompt: (c.querySelector('[data-dprompt]') || {}).textContent || '' }))"""


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_denied(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "denied"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    transcripts = {}
    for sid, cwd in CWDS.items():
        t = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{sid}.jsonl"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-20T09:00:00Z"), "message": {"role": "user", "content": "PR を取り込んで"}}, ensure_ascii=False) + "\n")
        transcripts[sid] = t
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"denied: {text}")

    def hook(sid, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": sid, "cwd": CWDS[sid], "transcript_path": str(transcripts[sid]), "permission_mode": "auto", **payload}).encode())

    def append(sid, *recs):
        with open(transcripts[sid], "a") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def use(use_id, cmd, mid):
        return {"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"id": mid, "model": "claude-sonnet-5-5", "role": "assistant", "usage": {"input_tokens": 10, "output_tokens": 5},
                            "content": [{"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": cmd}}]}}

    def denial(use_id, rule):
        return {"type": "user", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "is_error": True,
                                                         "content": f"{PREFIX} Reason: {rule}. If you have other tasks that don't depend on this action, continue working on those."}]}}

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

    def snap():
        return local("GET", "/api/snapshot")[1]["slices"]

    def until(cond, what, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return
            time.sleep(0.2)
        raise RuntimeError(f"timed out: {what}")

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
        for sid in CWDS:
            hook(sid, hook_event_name="SessionStart", source="startup")
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", DEV, "plugin:jui-viz@jsonui"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": S_OK, "cwd": CWDS[S_OK], "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
        status, hello = local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": S_OK, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        check(status == 200, f"hello: {status}")
        channel = hello["channelId"]
        until(lambda: any(s["id"] == S_OK and s.get("launch") == "dev" for s in snap()["sessions"]), "the channel's launch")
        # the server reads S_OK's transcript from now on: a response it bills shows that the tail is live
        # (the server reads a transcript from the end it has when first seen: a line written before is not read)
        warm = iter(range(200))

        def billed():
            append(S_OK, use(f"toolu_warm{next(warm)}", "true", f"m-warm-{time.time_ns()}"))
            return any(str(b.get("id", "")).startswith("m-warm") for b in snap().get("bills") or [])
        until(billed, "the transcript read (a bill)", timeout=30)

        ctx = await browser.new_context(**DESKTOP)
        await ctx.add_init_script("try { localStorage.setItem('e2e-perm', 'granted'); } catch (e) {}")
        await ctx.add_init_script(STUB)
        page = await ctx.new_page()
        watch = Watch(origin=url)
        watch.attach(page, "denied")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 2", label="two sessions")
        await page.mouse.click(5, 880)   # a press: the page may sound from now on (the browser's rule)
        await wait(page, "() => window.__dbg.notifyAudio() === 'running'", label="the sound woken")

        # one call, from the hook and from the transcript: one card. Another call, from the transcript only: its own.
        append(S_OK, use("toolu_d1", CMD1, "m-d1"))
        hook(S_OK, hook_event_name="PermissionDenied", tool_name="Bash", tool_input={"command": CMD1}, tool_use_id="toolu_d1",
             reason="[Unrequested Commit in a Connected App]")
        append(S_OK, denial("toolu_d1", "[Unrequested Commit in a Connected App]"))
        until(lambda: any(set(c["via"]) == {"hook", "transcript"} for c in snap().get("denials") or []), "the hook and the transcript on one card")
        append(S_OK, use("toolu_d2", CMD2, "m-d2"), denial("toolu_d2", "[Irreversible Remote Destruction]"))
        until(lambda: len(snap().get("denials") or []) == 2, "the transcript-only card")
        cards = res["slice"] = snap()["denials"]
        check(len(cards) == 2 and [c["prompt"] for c in cards] == [words(CMD1, WHY1), words(CMD2, WHY2)], f"two cards, one per call, with the words: {cards}")
        await wait(page, f"() => document.getElementById('chip-denied').textContent === {json.dumps(T('deny.chip', n=2))} && !document.getElementById('chip-denied').hidden", label="the chip")
        await wait(page, "() => document.querySelectorAll('#denied [data-dcard]').length === 2", label="the panel's cards")
        await wait(page, "() => JSON.parse(localStorage.getItem('e2e-shown') || '[]').length >= 2", label="two notifications")
        await page.wait_for_timeout(1500)   # a third would come within this
        shown = res["shown"] = await page.evaluate(SHOWN)
        check(len(shown) == 2 and all(T_pattern("deny.notify", tool="Bash").search(s["body"]) for s in shown), f"one notification per card: {shown}")
        res["chimes"] = await page.evaluate(CHIMES)
        check(res["chimes"] == 2, f"one chime per card: {res['chimes']}")
        await page.screenshot(path=str(out / "cards.png"))

        # the board's strip, from the chip
        await page.click("#chip-denied")
        await wait(page, "() => document.querySelectorAll('#denied-strip [data-dcard]').length === 2", label="the board's strip")
        # folded on open: each strip its count and one line per card, the four columns' heads in sight; 広げる shows the cards
        # and hides the columns (ticket 2026-10-22-viz-taskboard-top-strips-hide-the-columns)
        await wait(page, "() => { const tb = document.getElementById('tb'); return tb.classList.contains('show') && document.querySelectorAll('#denied-strip .ps-line').length === 2; }", label="the folded strip")
        await page.wait_for_timeout(600)
        got = res["fold1"] = await page.evaluate(FOLD)
        check(got["fold"] and not got["wide"] and got["cards"] == 0 and len(got["lines"]) == 2 and got["heads"] == 4 and got["headsIn"] == 4
              and got["btn"] == T("panel.tb.wide", what=T("panel.tb.wide.d", n=2)) and got["pressed"] == "false" and -8 <= got["handleGap"] <= 2,
              f"the board opens folded, one line per card, the columns' heads in sight, the handle on the strips' edge naming what waits: {got}")
        await page.click("#tb-wide[aria-pressed='false']")
        got = res["wide1"] = await page.evaluate(FOLD)
        check(got["wide"] and not got["fold"] and got["cards"] == 2 and got["headsIn"] == 0 and got["btn"] == T("panel.tb.fold") and got["pressed"] == "true",
              f"広げる: the cards whole, the columns hidden: {got}")
        # the strip has its own row above the columns, and its buttons are hit at their centre (not under a column's head),
        # once the board has finished opening (its zoom): waited for as a state
        HITS = """() => {
          const strip = document.getElementById('denied-strip').getBoundingClientRect(), kb = document.getElementById('kanban').getBoundingClientRect();
          const hits = [...document.querySelectorAll('#denied-strip [data-dask]')].map((b) => {
            const r = b.getBoundingClientRect(), at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return at === b || (!!at && b.contains(at)) ? 'ok' : at ? at.tagName.toLowerCase() + '.' + String(at.className).split(' ')[0] : 'none';
          });
          return { above: kb.height === 0 || strip.bottom <= kb.top + 1, hits };   // wide: no columns at all
        }"""
        try:
            await wait(page, f"() => {{ const l = ({HITS})(); return l.above && l.hits.length === 2 && l.hits.every((h) => h === 'ok'); }}",
                       timeout=8000, label="the strip's buttons")
        except RuntimeError:
            pass   # what was hit is recorded and checked below; the rest of the suite goes on
        res["layout"] = lay = await page.evaluate(HITS)
        check(lay["above"] and lay["hits"] == ["ok", "ok"], f"the strip above the columns, its buttons hit at their centre: {lay}")
        d1 = next(c["id"] for c in cards if c["toolUseId"] == "toolu_d1")
        d2 = next(c["id"] for c in cards if c["toolUseId"] == "toolu_d2")
        # 実行してよいと伝える… → the confirmation shows the words and the note; やめる sends nothing
        await page.click(f"#denied-strip [data-dask='{d1}']")
        got = res["confirm"] = next(c for c in await page.evaluate(CARDS, "#denied-strip") if c["id"] == d1)
        check(got["go"] and got["prompt"] == words(CMD1, WHY1) and T("deny.may") in got["text"],
              f"the confirmation shows the exact words and that the receiver may ask in the terminal: {got}")
        await page.screenshot(path=str(out / "confirm.png"))
        await page.wait_for_timeout(400)
        await page.click(f"#denied-strip [data-dback='{d1}']")
        got = next(c for c in await page.evaluate(CARDS, "#denied-strip") if c["id"] == d1)
        check(got["ask"] and not got["go"], f"やめる closes the confirmation: {got}")
        check(all(c["status"] == "pending" for c in snap()["denials"]), "やめる sent nothing (both cards wait)")
        # 送る: the words on that session's channel, once
        await page.click(f"#denied-strip [data-dask='{d1}']")
        await page.wait_for_timeout(400)
        await page.click(f"#denied-strip [data-dgo='{d1}']")
        until(lambda: next(c for c in snap()["denials"] if c["id"] == d1)["status"] == "sent", "the card sent")
        _, polled = local("GET", f"/channel/poll?channelId={channel}", timeout=30)
        res["inbox"] = polled["prompts"]
        check(polled["prompts"] == [{"text": words(CMD1, WHY1)}], f"the channel got the card's words, once: {polled['prompts']}")
        got_text = polled["prompts"][0]["text"] if polled["prompts"] else ""
        check(got_text.startswith(T("srv.denial.source") + "\n") and T("srv.denial.what", what=f"Bash: {CMD1}") + "\n" in got_text
              and T("srv.denial.why", why=WHY1) + "\n" in got_text,
              f"the words start with where they come from and hold the card's call and reason as they are: {got_text!r}")
        await wait(page, f"() => [...document.querySelectorAll('#denied-strip [data-dcard=\"{d1}\"]')].some((c) => c.textContent.includes({json.dumps(T('deny.done.sent'))}) && c.querySelector('[data-dreply-wait]'))", label="the card says 伝えた and waits for the response")
        # the receiver's next response (here: it asks for the terminal — a right answer too) shows under the card
        append(S_OK, {"type": "assistant", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 2)),
                      "message": {"id": "m-reply", "model": "claude-sonnet-5-5", "role": "assistant", "usage": {"input_tokens": 1, "output_tokens": 1},
                                  "content": [{"type": "text", "text": REPLY}]}})
        await wait(page, f"(r) => {{ const e = document.querySelector('#denied-strip [data-dreply=\"{d1}\"]'); return e && e.textContent.includes(r); }}", arg=REPLY, label="the receiver's next response under the card")
        await page.screenshot(path=str(out / "reply.png"))
        check(next(c for c in snap()["denials"] if c["id"] == d2)["status"] == "pending", "the other card still waits")

        # a session whose channel cannot take a prompt: the reason, no button; そのまま closes it
        hook(S_NO, hook_event_name="PermissionDenied", tool_name="Bash", tool_input={"command": "rm -rf build"}, tool_use_id="toolu_n1",
             reason="[Irreversible Local Destruction]")
        await wait(page, "() => document.querySelectorAll('#denied-strip [data-dcard]').length === 3", label="the third card")
        n1 = next(c["id"] for c in snap()["denials"] if c["toolUseId"] == "toolu_n1")
        got = res["noChannel"] = next(c for c in await page.evaluate(CARDS, "#denied-strip") if c["id"] == n1)
        check(not got["ask"] and got["dismiss"] and T_pattern("deny.why.terminal").search(got["text"]), f"no channel: the reason, no button: {got}")
        await page.screenshot(path=str(out / "no-channel.png"))
        await page.click(f"#denied-strip [data-ddismiss='{n1}']")
        until(lambda: next(c for c in snap()["denials"] if c["id"] == n1)["status"] == "dismissed", "そのまま")
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(out / "board-dark.png"))
        # the requester's case: the 1080 screen, three strips, a card with its reply. Wide: no columns; たたむ: the heads in sight
        # again; a card's line opens the strips wide at that card
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.wait_for_timeout(800)
        got = res["wide2"] = await page.evaluate(FOLD)
        check(got["wide"] and got["cards"] == 3 and got["headsIn"] == 0, f"1080, wide: three cards, no columns: {got}")
        await page.screenshot(path=str(out / "strips-wide.png"))
        await page.click("#tb-wide[aria-pressed='true']")
        await page.wait_for_timeout(400)
        got = res["fold2"] = await page.evaluate(FOLD)
        check(got["fold"] and not got["wide"] and got["cards"] == 0 and len(got["lines"]) == 3 and got["heads"] == 4 and got["headsIn"] == 4 and got["kbH"] >= 400
              and got["btn"] == T("panel.tb.wide", what=T("panel.tb.wide.d", n=1)) and got["pressed"] == "false" and -8 <= got["handleGap"] <= 2,
              f"1080, たたむ: one line per card, the four columns' heads in sight and 400 px of them, the handle on the strips' edge: {got}")
        await page.screenshot(path=str(out / "strips-fold.png"))
        await page.click(f"#denied-strip [data-ps-go='d:{d2}']")
        await wait(page, f"() => {{ const a = document.activeElement; return document.querySelector('#tb .kb-body').classList.contains('tb-wide') && !!a && !!a.closest('#denied-strip [data-dcard=\"{d2}\"]'); }}",
                   timeout=5000, label="a card's line: wide at that card, the focus in it")
        await page.click("#tb-wide[aria-pressed='true']")
        await page.wait_for_timeout(400)
        got = res["fold3"] = await page.evaluate(FOLD)
        check(got == res["fold2"], f"たたむ again: as it was: {got} vs {res['fold2']}")
        # the same board drawn by the rules before the fold (the new rules undone by a style of the run's own), for the requester
        await page.evaluate("""() => { const s = document.createElement('style'); s.id = 'e2e-before'; s.textContent = `
          .kb-body.kb-body { overflow-y: visible; } .kb-body.kb-body > .kanban { display: grid; } .ps-fold.ps-fold { display: none; }
          .kb-body.kb-body > .perm-strip { gap: 8px; max-height: 42vh; padding: 10px 12px; overflow-y: auto; box-shadow: none; }
          .kb-body.kb-body > .perm-strip > .qcard { display: grid; } .kb-body.kb-body > .perm-strip > .ps-list { display: grid; } .kb-body.kb-body > .perm-strip > .ps-none { display: block; }
          .kb-body.kb-body .ps-title { flex-wrap: wrap; } .kb-body.kb-body .ps-title small { overflow: visible; white-space: normal; }
          .kb-body.kb-body.kb-body .perm-strip.perm-strip .ps-title b { padding: 0 8px; background: var(--wb-amber); color: var(--wb-card); font-size: 12.5px; animation: none; }`; document.head.append(s); }""")
        await page.wait_for_timeout(300)
        res["before"] = await page.evaluate(FOLD)
        check(res["before"]["kbH"] < 400, f"the 400 px arm reads the board before the fold as short of it: {res['before']}")
        await page.screenshot(path=str(out / "strips-before.png"))
        await page.evaluate("() => document.getElementById('e2e-before').remove()")
        phone = await new_page(browser, watch, "denied-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => document.querySelectorAll('#denied [data-dcard]').length >= 1", label="the phone's cards")
        r = res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth })")
        await phone.screenshot(path=str(out / "phone.png"))
        check(r == {"hscroll": False}, f"390 px: no horizontal scroll: {r}")
        await phone.click("#chip-denied")
        await wait(phone, "() => { const tb = document.getElementById('tb'); return tb.classList.contains('show') && document.querySelectorAll('#denied-strip .ps-line').length >= 1; }", label="the phone's folded board")
        await phone.wait_for_timeout(600)
        r = res["phoneBoard"] = await phone.evaluate("""() => { const st = document.getElementById('denied-strip'), fold = st.querySelector('.ps-fold');
          return { fold: document.querySelector('#tb .kb-body').classList.contains('tb-fold'), hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                   strip: st.scrollWidth > st.clientWidth + 1, lines: fold.scrollWidth > fold.clientWidth + 1 }; }""")
        await phone.screenshot(path=str(out / "phone-board.png"))
        check(r == {"fold": True, "hscroll": False, "strip": False, "lines": False}, f"390 px, the folded board: no line runs off sideways: {r}")
        await phone.close()
        await page.close()
        await ctx.close()
        for line in watch.console:
            failures.append(f"denied: console: {line}")
        for u in watch.foreign:
            failures.append(f"denied: request outside the server: {u}")
    except Exception as e:
        failures.append(f"denied: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for p in stand_ins:
            p.kill()
            p.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  denied: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "denied-results.json").write_text(dump(res) + "\n")
