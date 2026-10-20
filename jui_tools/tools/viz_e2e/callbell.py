"""The call bell (2.3.5, ticket 2026-10-19-jui-viz-call-a-robot-button).

The real `jui viz serve` in a throwaway HOME on a free port, the real forward.py, a session in a folder whose name holds
quotes, a dollar and a bang (neutral names), and a managed-settings file of this run's own (JUI_VIZ_MANAGED_SETTINGS).
On the floor: no bell. In the room up close: the bell stands in the room; a real click on it opens the dialog; a name
makes the line; the line, run in zsh and in bash with a shell function in place of the CLI, hands over exactly the
project's folder and four arguments, and runs nothing it was given; copy puts that line on the clipboard; an empty name
or a NUL leaves nothing to copy; only the latest answer shows; the settings decide the channels flag; Esc closes and the
focus goes back; the header's 呼び出し opens it from the keyboard; the server starts no process. Light and dark.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, desk_pins_js, dump, new_page, ready
from waits import settled, until

DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
SID = "ca110000-0000-4000-8000-0000000000b1"
# The robot's desk, in the floor-view room's coordinates: clear of the bell's line of sight from the usual view (ticket
# 2026-10-20-jui-viz-e2e-callbell-dialog-wait-flaky; the drawn desk depended on --out, and one put the robot in front
# of the bell — 2026-10-20-jui-viz-callbell-bell-hidden-behind-a-desk is the product's side).
DESK = [6.4, 4.6]
# Where the drawn desk hid the bell (2.3.8's full e2e: floor-view room coordinates [1.71, 1.68], up close (-4.87, -4.97),
# the bell at (-5.5, -6.3)): the robot stands in front of the bell from the usual view. A press on the bell there must
# still open the dialog (ticket 2026-10-20-jui-viz-callbell-bell-hidden-behind-a-desk); before the fix it opened the
# robot's card.
DESK_HIDING = [1.71, 1.68]
# The server's own pollers (jui_cli/viz/sources/processes.py, agents_cli.py, gitbox.py), not processes it was asked for.
POLLERS = re.compile(r"^(\S*/)?ps -A -o |^(\S*/)?ps -o |\bagents --json\b|^(\S*/)?git -C ")
# The press to the dialog: measured within 0.1 s at 6x, 20x and 40x CPU throttling (openCall runs in the pointerup);
# the cap is for a press that opened nothing, so it says so instead of the run waiting on.
OPENED_MS = 10000


def check(failures, cond, text):
    if not cond:
        failures.append(f"callbell: {text}")


def sh_word(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def run_line(shell: str, line: str, scratch: pathlib.Path) -> list[str]:
    """The pasted line with a shell function in place of the CLI: $PWD and the arguments, NUL-separated."""
    out = scratch / "argv.bin"
    if out.exists():
        out.unlink()
    defs = f"claude() {{ printf '%s\\0' \"$PWD\" \"$@\" > {sh_word(str(out))}; }}"
    base = [shell, "-f"] if shell.endswith("zsh") else [shell, "--norc", "--noprofile"]
    subprocess.run(base + ["-i"], input=(defs + "\n" + line + "\nexit\n").encode(), cwd=scratch,
                   env={"PATH": "/usr/bin:/bin", "HOME": str(scratch)}, capture_output=True, timeout=20)
    return out.read_bytes().decode("utf-8").split("\0")[:-1] if out.exists() else ["(did not run)"]


async def run_callbell(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "callbell"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    scratch = out / "scratch"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    folder = out / "call app's \"q\" $(touch PWNED) !x"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    settings = out / "managed-settings.json"
    settings.write_text(json.dumps({"channelsEnabled": True, "allowedChannelPlugins": ["jui-viz@jsonui"]}))
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1", JUI_VIZ_MANAGED_SETTINGS=str(settings))
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(payload):
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps({"session_id": SID, "cwd": str(folder), **payload}).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def kids():
        """The server's children, less its own pollers (sources/: ps for the process list, `claude agents --json`
        every 3 s, git for the git box): one of those caught at a sample made the check red (1 run in 5 at 6x CPU
        throttling, 10-20). Anything else it started — a shell, the pasted line — is still counted."""
        got = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True).stdout.splitlines()
        rows = [ln.split(None, 2) for ln in got]
        return sorted(f"{r[0]} {r[2]}" for r in rows if len(r) == 3 and r[1] == str(srv.pid) and not POLLERS.search(r[2]))

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.request
        for _ in range(150):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        hook({"hook_event_name": "SessionStart", "source": "startup"})
        watch = Watch(origin=url)
        page = await new_page(browser, watch, "callbell", **DESKTOP)
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        await page.add_init_script(desk_pins_js([(folder, SID, DESK)]))
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => Object.keys(window.__dbg.robotState()).length >= 1", "the robot", timeout=30000)
        kids0 = kids()

        # the floor: no bell, no header button
        floor = res["floor"] = await page.evaluate("() => ({ bell: window.__dbg.bell(), call: !document.getElementById('room-solo').hidden && !document.getElementById('room-call').hidden })")
        check(failures, not floor["bell"]["built"] and not floor["call"], f"on the floor: no bell, no 呼び出し: {floor}")

        # the room up close: the bell stands in the room, in sight
        await page.click("#scope-top")
        await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].find((x) => x.textContent.includes('call app')).click()")
        await until(page, "() => window.__dbg.bell().built", "the bell in the room up close", timeout=20000)
        await settled(page, "seated in the room up close")
        seat = res["seat"] = await page.evaluate("() => window.__dbg.seats().ca")
        check(failures, seat and [seat.get("dx"), seat.get("dz")] == DESK, f"the desk is where the arm put it {DESK}: {seat}")
        await page.wait_for_timeout(800)
        b = res["bell"] = await page.evaluate("() => window.__dbg.bell()")
        room = await page.evaluate("(id) => { const r = window.__dbg.room(id); return [r.x0, r.x1, r.z0, r.z1]; }", b["room"])
        rect = b["place"]["rect"]
        check(failures, b["inView"] and room[0] <= rect[0] and rect[1] <= room[1] and room[2] <= rect[2] and rect[3] <= room[3],
              f"the bell stands in the room, in sight: {b} room {room}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(1200)
            await page.screenshot(path=str(out / f"room-{scheme}.png"))
        await page.emulate_media(color_scheme="light")
        await page.wait_for_timeout(800)

        # a real click on the bell opens the dialog, the name field focused, nothing to copy yet
        await settled(page, "the room before the press on the bell")
        await until(page, "() => !window.__dbg.view().tween", "the camera still before the press on the bell", timeout=20000)
        b = await page.evaluate("() => window.__dbg.bell()")
        await page.mouse.click(*b["screen"])
        await until(page, "() => !document.getElementById('call').hidden", "the dialog from the bell", timeout=OPENED_MS,
                    why="() => ({ bell: window.__dbg.bell(), view: window.__dbg.view() })")
        st = res["opened"] = await page.evaluate("() => ({ focus: document.activeElement && document.activeElement.id, copy: document.getElementById('call-copy').disabled, cmd: document.getElementById('call-cmd').value, why: document.getElementById('call-why').textContent })")
        check(failures, st["focus"] == "call-name" and st["copy"] and not st["cmd"], f"opened: the name field focused, nothing to copy: {st}")

        # a name and a role make the line; run in zsh and bash it hands over the folder and four arguments, and runs nothing
        name, role = "x'; touch PWNED; '", "役割: $(touch PWNED)\n`touch PWNED` ; && | !! \\ 🤖"
        await page.fill("#call-name", name)
        await page.fill("#call-role", role)
        await until(page, "() => !document.getElementById('call-copy').disabled", "the line", timeout=20000)
        line = res["line"] = await page.evaluate("() => document.getElementById('call-cmd').value")
        for shell in [s for s in ("/bin/zsh", "/bin/bash") if os.path.exists(s)]:
            got = run_line(shell, line, scratch)
            res.setdefault("argv", {})[shell] = got
            check(failures, len(got) == 5 and got[0] == os.path.realpath(folder) and got[1:4] == ["--channels", "plugin:jui-viz@jsonui", f"--name={name}"]
                  and got[4].endswith(f"セッション名: {name}\n{role}"), f"{shell}: the folder and four arguments: {got}")
        check(failures, not list(out.rglob("PWNED")), "a name, a role or the folder ran a command")

        # copy: the clipboard holds that line
        await page.click("#call-copy")
        clip = res["clipboard"] = await page.evaluate("() => navigator.clipboard.readText()")
        check(failures, clip == line, f"the clipboard holds the line: {clip!r}")
        for scheme in ("light", "dark"):
            await page.emulate_media(color_scheme=scheme)
            await page.wait_for_timeout(600)
            await page.screenshot(path=str(out / f"dialog-{scheme}.png"))
        await page.emulate_media(color_scheme="light")

        # the clipboard refuses: the line is selected for a manual copy, and the dialog says so
        await page.evaluate("() => { window.__clipWrite = navigator.clipboard.writeText; navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); }")
        await page.click("#call-copy")
        sel = res["copyRefused"] = await page.evaluate("""() => { const t = document.getElementById('call-cmd');
          return { focus: document.activeElement === t, all: t.selectionStart === 0 && t.selectionEnd === t.value.length && t.value.length > 0,
                   why: document.getElementById('call-why').textContent }; }""")
        await page.evaluate("() => { navigator.clipboard.writeText = window.__clipWrite; }")
        check(failures, sel["focus"] and sel["all"] and "できなかった" in sel["why"], f"a refused copy selects the line and says so: {sel}")

        # nothing to copy: an empty name, a NUL
        await page.fill("#call-name", "")
        await until(page, "() => document.getElementById('call-copy').disabled && !document.getElementById('call-cmd').value", "empty name: nothing to copy", timeout=20000)
        await page.evaluate("() => { const e = document.getElementById('call-name'); e.value = 'a\\u0000b'; e.dispatchEvent(new Event('input')); }")
        await until(page, "() => document.getElementById('call-why').textContent.includes('NUL')", "NUL: refused", timeout=20000)
        nul = res["nul"] = await page.evaluate("() => ({ copy: document.getElementById('call-copy').disabled, cmd: document.getElementById('call-cmd').value })")
        check(failures, nul["copy"] and not nul["cmd"], f"a NUL leaves nothing to copy: {nul}")

        # only the latest answer: the answer for "slow" is held back (the network route) until "fast" has been answered;
        # the late, older answer must not replace the line for what is typed now
        import asyncio

        async def hold_slow(route):
            if '"name": "slow"' in (route.request.post_data or "") or '"name":"slow"' in (route.request.post_data or ""):
                await asyncio.sleep(1.5)
            await route.continue_()
        await page.route("**/api/call-command", hold_slow)
        await page.fill("#call-name", "slow")
        await page.wait_for_timeout(400)   # past the 150 ms pause: the request for "slow" is out (and held)
        await page.fill("#call-name", "fast")
        await page.wait_for_timeout(2500)  # the held answer arrives after the newer one
        await page.unroute("**/api/call-command", hold_slow)
        got = run_line("/bin/zsh", await page.evaluate("() => document.getElementById('call-cmd').value"), scratch)
        res["latest"] = got[3:4]
        check(failures, len(got) == 5 and got[3] == "--name=fast", f"only the latest answer shows (a late older one does not replace it): {got[3:4]}")

        # the settings decide the flag (read each time)
        settings.write_text(json.dumps({"channelsEnabled": False}))
        await page.fill("#call-name", "dev-flag")
        await until(page, "() => document.getElementById('call-cmd').value.includes('--dangerously-load-development-channels')", "the development flag", timeout=20000)
        res["devWhy"] = await page.evaluate("() => document.getElementById('call-why').textContent")
        check(failures, "警告" in res["devWhy"], f"the development flag says its warning: {res['devWhy']}")

        # Esc closes; the header's 呼び出し opens it from the keyboard and gets the focus back
        await page.keyboard.press("Escape")
        await until(page, "() => document.getElementById('call').hidden", "Esc closes", timeout=20000)
        await page.focus("#room-call")
        await page.keyboard.press("Enter")
        await until(page, "() => !document.getElementById('call').hidden && document.activeElement.id === 'call-name'", "opened from the header", timeout=20000)
        await page.keyboard.press("Escape")
        await until(page, "() => document.getElementById('call').hidden && document.activeElement.id === 'room-call'", "the focus back on 呼び出し", timeout=20000)

        res["kids"] = [kids0, kids()]
        check(failures, kids() == kids0, f"the server started no process: {res['kids']}")

        # the robot's desk in front of the bell (a fresh page, its own desk memory): the press still opens the dialog
        await page.close()
        page = await new_page(browser, watch, "callbell-hidden", **DESKTOP)
        await page.add_init_script(desk_pins_js([(folder, SID, DESK_HIDING)]))
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => Object.keys(window.__dbg.robotState()).length >= 1", "the robot (desk in front of the bell)", timeout=30000)
        await page.click("#scope-top")
        await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].find((x) => x.textContent.includes('call app')).click()")
        await until(page, "() => window.__dbg.bell().built", "the bell (desk in front of it)", timeout=20000)
        await settled(page, "seated, the desk in front of the bell")
        await until(page, "() => !window.__dbg.view().tween", "the camera still, the desk in front of the bell", timeout=20000)
        seat = res["hiddenSeat"] = await page.evaluate("() => window.__dbg.seats().ca")
        check(failures, seat and [seat.get("dx"), seat.get("dz")] == DESK_HIDING, f"the desk is where the arm put it {DESK_HIDING}: {seat}")
        b = res["hiddenBell"] = await page.evaluate("() => window.__dbg.bell()")
        # the robot is in front of the bell at that point (the arm is about a hidden bell, not a free one); __dbg.under came with the fix
        under = res["hiddenUnder"] = await page.evaluate("(p) => window.__dbg.under ? window.__dbg.under(p) : 'no __dbg.under'", b["screen"])
        if isinstance(under, list):
            check(failures, under[:1] == ["robot:ca"] and "bell" in under, f"the robot stands in front of the bell at its point: {under}")
        await page.screenshot(path=str(out / "hidden-room-light.png"))
        await page.mouse.click(*b["screen"])
        await until(page, "() => !document.getElementById('call').hidden", "the dialog from the bell behind the robot", timeout=OPENED_MS,
                    why="() => ({ bell: window.__dbg.bell(), view: window.__dbg.view() })")
        card = res["hiddenCard"] = await page.evaluate("() => window.__dbg.view().card")
        check(failures, not card, f"the press on the bell opened no robot's card: {card}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  callbell/bell: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "callbell-results.json").write_text(dump(res) + "\n")
