"""The note above the card's prompt box goes with its ×, end to end (2.3.7, requester 10-20). `--only card-note`.

"この注意書きの部分邪魔だから消せるようにしといて xボタンで消せて、消したら他でも表示されない" (ticket
2026-10-20-jui-viz-card-note-dismiss-and-wide-on-both-tabs). The real `jui viz serve` in a throwaway HOME, the real
forward.py, and sleeping stand-in processes whose argv carries the launch flags (as send_prompt.py): two sessions started
with `--channels plugin:jui-viz@jsonui` (the note shows) and one started without a flag (the box is disabled, the reason
shows). Arms: the × hides the note on this card and on the other --channels robot's card; the reason of the flagless
session still shows; a reload keeps it hidden (localStorage); 設定 › 「カードの説明をまた出す」 brings it back; with
localStorage throwing the page works, the note shows, and the × still hides it for the page view (and the reason stays).
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

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, new_page, ready, stamp

S_C1 = "e2e00000-0000-4000-8000-0000000000e1"
S_C2 = "e2e00000-0000-4000-8000-0000000000e2"
S_PLAIN = "e2e00000-0000-4000-8000-0000000000e3"
CWDS = {S_C1: "/work/note-one", S_C2: "/work/note-two", S_PLAIN: "/work/note-plain"}
NO_STORAGE = "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });"
COMPOSE = """() => {
  const b = document.querySelector('[data-h-compose]');
  if (!b) return null;
  const q = (k) => b.querySelector(`[data-${k}]`), x = q('h-note-x'), why = q('h-why');
  const seen = (e) => !!e && !e.hidden && e.getBoundingClientRect().height > 0;
  return { why: seen(why) ? why.textContent : '', note: seen(why) && why.classList.contains('h-compose-note'), x: seen(x),
    disabled: q('h-text').disabled,
    back: (() => { const e = document.getElementById('card-note-back'); return e ? { disabled: e.disabled, state: document.getElementById('card-note-state').textContent } : null; })() };
}"""


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_card_note(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "card-note"
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
        t.write_text(json.dumps({"type": "user", "timestamp": stamp("2026-10-19T09:00:00Z"), "message": {"role": "user", "content": "最初の依頼"}}, ensure_ascii=False) + "\n"
                     + json.dumps({"type": "assistant", "timestamp": stamp("2026-10-19T09:00:01Z"), "message": {"id": "a1", "role": "assistant", "content": [{"type": "text", "text": "最初の応答"}]}}, ensure_ascii=False) + "\n")
        transcripts[sid] = t
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    sessions_dir = home / ".claude" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    stand_ins: list = []

    def session_process(sid, *args):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stand_ins.append(proc)
        (sessions_dir / f"{proc.pid}.json").write_text(json.dumps({"pid": proc.pid, "sessionId": sid, "cwd": CWDS[sid], "kind": "interactive",
                                                                  "entrypoint": "cli", "status": "idle", "procStart": f"t{proc.pid}"}))
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def check(cond, text):
        if not cond:
            failures.append(f"card-note: {text}")

    def hook(sid, **payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], timeout=10, capture_output=True, env=dict(base_env, HOME=str(home)),
                       input=json.dumps({"session_id": sid, "cwd": CWDS[sid], "transcript_path": str(transcripts[sid]), "permission_mode": "default", **payload}).encode())

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

    async def open_robot(page, sid):
        _, snap = local("GET", "/api/snapshot")
        label = next(s["label"] for s in snap["slices"]["sessions"] if s["id"] == sid)
        await page.evaluate("(l) => document.querySelector(`#sessions [data-robot-open=\"${l}\"]`).click()", label)
        await wait(page, "(l) => document.getElementById('rb-title') && document.getElementById('rb-title').textContent.startsWith(l)", arg=label, label=f"the card of {label}")
        if await page.evaluate("() => document.querySelector('[data-rb-hist]').hidden"):
            await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('最初の応答')", label=f"{label}'s history")
        return await page.evaluate(COMPOSE)

    async def fresh(label, init=None):
        page = await new_page(browser, watch, label, **DESKTOP)
        if init:
            await page.add_init_script(init)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", label="three sessions")
        return page

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
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
        session_process(S_C1, "--channels", "plugin:jui-viz@jsonui")
        session_process(S_C2, "--channels", "plugin:jui-viz@jsonui")
        session_process(S_PLAIN)
        for sid in CWDS:
            local("POST", "/channel/hello", {"ppid": 1, "cwd": "/", "sessionId": sid, "version": "2", "accepts": ["prompt"], "via": "plugin"})
        launches = {}
        for _ in range(100):
            _, snap = local("GET", "/api/snapshot")
            launches = {s["id"]: s.get("launch") for s in snap["slices"]["sessions"]}
            if launches.get(S_C1) == "channels" and launches.get(S_C2) == "channels" and launches.get(S_PLAIN) == "no-flag":
                break
            time.sleep(0.1)
        res["launches"] = {CWDS[k].rsplit("-", 1)[1]: v for k, v in launches.items()}
        check(res["launches"] == {"one": "channels", "two": "channels", "plain": "no-flag"}, f"the launches: {res['launches']}")

        page = await fresh("card-note")
        r = res["before"] = await open_robot(page, S_C1)
        check(r["note"] and T("hist.launch.channels") in r["why"] and r["x"] and not r["disabled"] and r["back"] and r["back"]["disabled"],
              f"a --channels session: the note shows with its ×, 設定's way back has nothing to bring back: {r}")
        await page.screenshot(path=str(out / "note.png"))
        await page.click("[data-h-note-x]")
        r = res["dismissed"] = await page.evaluate(COMPOSE)
        check(not r["why"] and not r["x"], f"the × hides the note on this card: {r}")
        r = res["other"] = await open_robot(page, S_C2)
        check(not r["why"] and not r["x"], f"the other --channels robot's card shows no note either: {r}")
        r = res["plain"] = await open_robot(page, S_PLAIN)
        check(r["disabled"] and T("hist.launch.noflag") in r["why"] and not r["note"] and not r["x"],
              f"the flagless session's reason still shows after the dismissal (no × on it): {r}")
        await page.screenshot(path=str(out / "reason.png"))
        res["pref"] = await page.evaluate("() => localStorage.getItem('agent-view:cardNote')")
        check(res["pref"] == "off", f"the dismissal is kept in this browser: {res['pref']}")
        await page.reload()
        await ready(page)
        await wait(page, "() => document.querySelectorAll('#sessions [data-robot-open]').length >= 3", label="sessions after the reload")
        r = res["reloaded"] = await open_robot(page, S_C2)
        check(not r["why"] and not r["x"] and r["back"] and not r["back"]["disabled"] and T("hist.cardnote.off") in r["back"]["state"],
              f"after a reload the note stays hidden, and 設定 says so: {r}")
        await page.evaluate("() => document.getElementById('card-note-back').click()")
        r = res["back"] = await page.evaluate(COMPOSE)
        check(r["note"] and T("hist.launch.channels") in r["why"] and r["x"] and r["back"]["disabled"], f"設定 › カードの説明をまた出す brings the note back: {r}")
        r = res["backOther"] = await open_robot(page, S_C1)
        check(r["note"] and r["x"], f"... on the other card too: {r}")
        res["prefBack"] = await page.evaluate("() => localStorage.getItem('agent-view:cardNote')")
        check(res["prefBack"] != "off", f"the way back clears the kept dismissal: {res['prefBack']}")
        await page.close()

        # localStorage throwing: the page works, the note shows, the × hides it for this page view
        p2 = await fresh("card-note-nostorage", init=NO_STORAGE)
        r = res["ns-before"] = await open_robot(p2, S_C1)
        check(r["note"] and r["x"], f"no storage: the note shows with its ×: {r}")
        await p2.click("[data-h-note-x]")
        r = res["ns-dismissed"] = await p2.evaluate(COMPOSE)
        r2 = res["ns-other"] = await open_robot(p2, S_C2)
        r3 = res["ns-plain"] = await open_robot(p2, S_PLAIN)
        check(not r["why"] and not r2["why"] and not r2["x"], f"no storage: the × hides it on this card and the other: {r} {r2}")
        check(r3["disabled"] and T("hist.launch.noflag") in r3["why"], f"no storage: the flagless session's reason still shows: {r3}")
        await p2.evaluate("() => document.getElementById('card-note-back').click()")
        r = res["ns-back"] = await open_robot(p2, S_C1)
        check(r["note"] and r["x"], f"no storage: the way back works for the page view: {r}")
        await p2.close()
        for line in watch.console:
            failures.append(f"card-note: console: {line}")
        for u in watch.foreign:
            failures.append(f"card-note: request outside the server: {u}")
    except Exception as e:
        failures.append(f"card-note: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        for proc in stand_ins:   # the session stand-ins this suite started
            proc.kill()
            proc.wait()
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  card-note: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "card-note-results.json").write_text(dump(res) + "\n")
