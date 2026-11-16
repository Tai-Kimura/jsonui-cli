"""上限で停止 (ticket 2026-10-29-viz-limit-stopped-robot-dazed; requester: 「リミットで止まったセッションがわかるようにしたい」
「ステータス表示ついかと頭の周りに星がくるくる回って気絶してる見た目にしたい」). Runs with `--only limit-dazed`.

The real `jui viz serve` in a throwaway HOME; the hooks are replayed through forward.py. Two sessions in one room: one
whose turn ends with StopFailure error rate_limit (Claude Code's own field, claude 2.1.312), and one whose turn ends with
StopFailure error server_error (the control: stopped, not dazed). Checked: the dazed robot's state, lamp and × eyes
(face 'dizzy'); five stars on the page around its head, moving; the session list's badge 上限で停止 and its own filter chip (not
counted as 動いている); the card's state and words with the limit's own message; the control robot not dazed; the next
prompt brings the robot back (no stars, not limited). Light and dark; a video of the whole for the requester."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import DESKTOP, ISOLATE, LAUNCH_ARGS, T, Watch, dump, ready  # noqa: E402

S_LIMIT = "1d1e0000-0000-4000-8000-0000000000d1"
S_ERROR = "1d1e0000-0000-4000-8000-0000000000d2"
LIMIT_WORDS = "You've hit your monthly spend limit · your weekly limit resets Oct 30 at 2pm (Asia/Tokyo)"


def check(failures, cond, text):
    if not cond:
        failures.append(f"limit-dazed: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


async def run_limit_dazed(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "limit-dazed"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT,
                           env=dict(base_env, HOME=str(home), JUI_VIZ_E2E="1"))
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": "/work/dazed-app", "transcript_path": "/work/home/t.jsonl", "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(), capture_output=True,
                       env=dict(base_env, HOME=str(home)), timeout=10)

    def label_of(sid):
        import http.client
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            conn.request("GET", "/api/snapshot", headers={"X-Jui-Viz-Token": token})
            snap = json.loads(conn.getresponse().read())
        finally:
            conn.close()
        return next(s["label"] for s in snap["slices"]["sessions"] if s["id"] == sid)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    watch = Watch(origin=url)
    ctx = None
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(400):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        for sid in (S_LIMIT, S_ERROR):
            hook(sid, hook_event_name="SessionStart", source="startup")
            hook(sid, hook_event_name="UserPromptSubmit", prompt="続きをお願い")
        lim, err = label_of(S_LIMIT), label_of(S_ERROR)
        ctx = await browser.new_context(**DESKTOP, record_video_dir=str(out / "video"), record_video_size={"width": DESKTOP["viewport"]["width"], "height": DESKTOP["viewport"]["height"]})
        page = await ctx.new_page()
        watch.attach(page, "limit-dazed")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "(ids) => ids.every((id) => window.__dbg.dazed(id))", arg=[lim, err], timeout=30000, label="the two robots")
        await page.wait_for_timeout(1500)

        hook(S_LIMIT, hook_event_name="StopFailure", error="rate_limit", last_assistant_message=LIMIT_WORDS)
        hook(S_ERROR, hook_event_name="StopFailure", error="server_error", last_assistant_message="API Error: 500")
        await wait(page, "(id) => (window.__dbg.dazed(id) || {}).stars.length === 5", arg=lim, label="the stars over the limited robot")
        await page.wait_for_timeout(1200)   # the state's blend is over
        a = res["dazed"] = await page.evaluate("(id) => window.__dbg.dazed(id)", lim)
        await page.wait_for_timeout(400)
        b = await page.evaluate("(id) => window.__dbg.dazed(id)", lim)
        hx, hy = a["head"]
        near = all(abs(x - hx) < 260 and -260 < y - hy < 120 for x, y in a["stars"])
        moved = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(a["stars"], b["stars"]))
        res["moved"] = moved
        check(failures, a["state"] == "limited" and a["face"] == "dizzy" and a["lamp"] == "limited", f"the limited robot: state, × eyes, pink lamp: {a}")
        check(failures, len(a["stars"]) == 5 and near, f"five stars on the page around its head: {a}")
        check(failures, moved > 20, f"the stars go round: moved {moved}px in 0.4 s")
        c = res["control"] = await page.evaluate("(id) => window.__dbg.dazed(id)", err)
        check(failures, c["state"] != "limited" and c["stars"] == [] and c["face"] != "dizzy", f"a server_error stop is not dazed: {c}")
        await page.screenshot(path=str(out / "room-dazed.png"))

        # the session list: its badge, its own filter chip, not counted as 動いている
        badge = await page.evaluate("(id) => (document.querySelector(`[data-sst=\"${id}\"]`) || {}).textContent || ''", lim)
        chips = await page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#sess-filter [data-sf]')].map((b) => [b.dataset.sf, b.lastElementChild.textContent]))")
        res["list"] = {"badge": badge, "chips": chips}
        check(failures, badge == T("status.limited"), f"the session list's badge: {badge!r}")
        check(failures, chips.get("limited") == "1" and chips.get("active") == "0", f"the filter chips: 上限で停止 1, 動いている 0: {chips}")
        await page.click("#sess-filter [data-sf='limited']")
        await page.wait_for_timeout(300)
        listed = await page.evaluate("() => [...document.querySelectorAll('#sessions [data-sst]')].map((n) => n.dataset.sst)")
        check(failures, listed == [lim], f"the chip shows only the limited session: {listed}")
        await page.screenshot(path=str(out / "list-filter.png"))
        await page.click("#sess-filter [data-sf='all']")

        # its card: the state and the words, with the limit's own message
        await page.evaluate("(id) => window.__dbg.openRobot(id)", lim)
        await wait(page, "(id) => (document.querySelector('#rb .rb-badge') || {}).textContent === id", arg=lim, label="the limited robot's card")
        await page.wait_for_timeout(2500)
        card = res["card"] = await page.evaluate("() => ({ state: (document.querySelector('#rb [data-rb-state]') || {}).textContent || '', text: document.getElementById('rb').textContent })")
        check(failures, card["state"] == T("status.limited") and T("act.limited") in card["text"] and "resets Oct 30" in card["text"],
              f"the card says 上限で停止, what it means and the limit's own words: {card['state']!r}")
        await page.screenshot(path=str(out / "card-dazed-light.png"))
        hx, hy = (await page.evaluate("(id) => window.__dbg.dazed(id)", lim))["head"]   # close up: the × eyes and the stars
        await page.screenshot(path=str(out / "face-close.png"), clip={"x": max(0, hx - 180), "y": max(0, hy - 230), "width": 360, "height": 360})
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(out / "card-dazed-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(1500)

        # the next prompt: back to work, no stars
        hook(S_LIMIT, hook_event_name="UserPromptSubmit", prompt="上限が戻ったので続けて")
        await wait(page, "(id) => { const d = window.__dbg.dazed(id); return d && d.state !== 'limited' && !d.stars.length; }", arg=lim, label="the robot back")
        await page.wait_for_timeout(1500)
        back = res["back"] = await page.evaluate("(id) => window.__dbg.dazed(id)", lim)
        state_now = await page.evaluate("() => (document.querySelector('#rb [data-rb-state]') || {}).textContent || ''")
        check(failures, back["face"] != "dizzy" and back["lamp"] != "limited" and state_now != T("status.limited"), f"back after the next prompt: {back} {state_now!r}")
        await page.screenshot(path=str(out / "card-back.png"))
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(out / "room-back.png"))
        await page.close()
    finally:
        (out / "limit-dazed-results.json").write_text(dump(res) + "\n")
        if ctx is not None:
            await ctx.close()   # the video is written on close
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  limit-dazed: {time.monotonic() - t0:.0f}s", flush=True)
    from run import check_watch
    check_watch(watch, "limit-dazed", failures)
