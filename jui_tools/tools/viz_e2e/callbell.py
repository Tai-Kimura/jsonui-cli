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
import shutil
import subprocess
import sys
import time

from common import ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready

DESKTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1}
SID = "ca110000-0000-4000-8000-0000000000b1"


def check(failures, cond, text):
    if not cond:
        failures.append(f"callbell: {text}")


async def wait(page, js, arg=None, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=100)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


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
        return sorted(subprocess.run(["pgrep", "-P", str(srv.pid)], capture_output=True, text=True).stdout.split())

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
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => Object.keys(window.__dbg.robotState()).length >= 1", timeout=30000, label="the robot")
        kids0 = kids()

        # the floor: no bell, no header button
        floor = res["floor"] = await page.evaluate("() => ({ bell: window.__dbg.bell(), call: !document.getElementById('room-solo').hidden && !document.getElementById('room-call').hidden })")
        check(failures, not floor["bell"]["built"] and not floor["call"], f"on the floor: no bell, no 呼び出し: {floor}")

        # the room up close: the bell stands in the room, in sight
        await page.click("#scope-top")
        await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].find((x) => x.textContent.includes('call app')).click()")
        await wait(page, "() => window.__dbg.bell().built", label="the bell in the room up close")
        await wait(page, "() => window.__dbg.robots.every((R) => !R.path.length)", timeout=30000, label="seated")
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
        b = await page.evaluate("() => window.__dbg.bell()")
        await page.mouse.click(*b["screen"])
        await wait(page, "() => !document.getElementById('call').hidden", label="the dialog from the bell")
        st = res["opened"] = await page.evaluate("() => ({ focus: document.activeElement && document.activeElement.id, copy: document.getElementById('call-copy').disabled, cmd: document.getElementById('call-cmd').value, why: document.getElementById('call-why').textContent })")
        check(failures, st["focus"] == "call-name" and st["copy"] and not st["cmd"], f"opened: the name field focused, nothing to copy: {st}")

        # a name and a role make the line; run in zsh and bash it hands over the folder and four arguments, and runs nothing
        name, role = "x'; touch PWNED; '", "役割: $(touch PWNED)\n`touch PWNED` ; && | !! \\ 🤖"
        await page.fill("#call-name", name)
        await page.fill("#call-role", role)
        await wait(page, "() => !document.getElementById('call-copy').disabled", label="the line")
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
        await wait(page, "() => document.getElementById('call-copy').disabled && !document.getElementById('call-cmd').value", label="empty name: nothing to copy")
        await page.evaluate("() => { const e = document.getElementById('call-name'); e.value = 'a\\u0000b'; e.dispatchEvent(new Event('input')); }")
        await wait(page, "() => document.getElementById('call-why').textContent.includes('NUL')", label="NUL: refused")
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
        await wait(page, "() => document.getElementById('call-cmd').value.includes('--dangerously-load-development-channels')", label="the development flag")
        res["devWhy"] = await page.evaluate("() => document.getElementById('call-why').textContent")
        check(failures, "警告" in res["devWhy"], f"the development flag says its warning: {res['devWhy']}")

        # Esc closes; the header's 呼び出し opens it from the keyboard and gets the focus back
        await page.keyboard.press("Escape")
        await wait(page, "() => document.getElementById('call').hidden", label="Esc closes")
        await page.focus("#room-call")
        await page.keyboard.press("Enter")
        await wait(page, "() => !document.getElementById('call').hidden && document.activeElement.id === 'call-name'", label="opened from the header")
        await page.keyboard.press("Escape")
        await wait(page, "() => document.getElementById('call').hidden && document.activeElement.id === 'room-call'", label="the focus back on 呼び出し")

        res["kids"] = [kids0, kids()]
        check(failures, kids() == kids0, f"the server started no process: {res['kids']}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  callbell/bell: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "callbell-results.json").write_text(dump(res) + "\n")
