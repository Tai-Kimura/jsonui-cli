"""The spec board shows the worktrees sessions work in (ticket 2026-10-23-jui-viz-spec-board-shows-worktree-in-progress).

The real `jui viz serve` in a throwaway HOME on a free port. A real git repository made here (room/, a JsonUI app at
its root, ログイン committed on main) and a worktree of it outside the room (scratch/wt on feat/x: ログイン changed,
注文 new), one session in each. In the room (room/):

- the panel's list has ログイン twice (⎇ main and ⎇ feat/x) and 注文 once (⎇ feat/x): the spec in both checkouts is
  two rows, neither dropped; the worktree's own room (wt/) lists its two specs untagged;
- the whiteboard's list carries the same tags, its app filter names the worktree (⎇ feat/x), and an open
  worktree spec's head says its branch;
- a spec added to the room while the worktree's 注文 is open: the rows move, the sheet stays on 注文 (it is kept by
  its id, not its place in the list);
- the worktree's session ends: its rows leave the room, and the sheet open on one of them goes back to the overview.

Pictures: the room's list (both checkouts' ログイン, and 注文 of the worktree only) and the sheet of 注文.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID_MAIN = "e2e00000-0000-4000-8000-000000000a01"
SID_WT = "e2e00000-0000-4000-8000-000000000a02"

# the room's list, grouped by room: [{room, rows: [{name, tag, wt}]}]
LIST_JS = """() => { const out = []; let cur = null;
  for (const li of document.querySelectorAll('#spec-list > li')) {
    if (li.classList.contains('sl-group')) { cur = { room: li.firstChild.textContent.trim(), rows: [] }; out.push(cur); continue; }
    const b = li.querySelector('.spec-row'); if (!b) continue;
    if (!cur) { cur = { room: '', rows: [] }; out.push(cur); }
    const tag = b.querySelector('.co-tag');
    cur.rows.push({ name: b.querySelector('.nm').textContent.replace(tag ? tag.textContent : '', '').trim(),
      tag: tag ? tag.textContent.trim() : null, wt: !!(tag && tag.classList.contains('co-wt')) }); }
  return out; }"""
SIDE_JS = """() => ({ items: [...document.querySelectorAll('#wb-side-list .ws-item:not(.ws-all)')].map((b) => {
    const tag = b.querySelector('.co-tag'); return { name: b.querySelector('.nm').textContent.replace(tag ? tag.textContent : '', '').trim(), tag: tag ? tag.textContent.trim() : null }; }),
  apps: [...document.querySelectorAll('#wb-side-list .ws-apps button')].map((b) => b.firstChild.textContent.trim()),
  title: document.getElementById('wb-title').textContent, file: document.getElementById('wb-file').textContent })"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-worktrees: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def spec(name, display, description="d"):
    return {"type": "screen_spec", "metadata": {"name": name, "displayName": display, "description": description,
                                                "platforms": ["ios"]}}


def git(cwd, *args, home):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "e2e", "GIT_AUTHOR_EMAIL": "e2e@e2e", "GIT_COMMITTER_NAME": "e2e",
                        "GIT_COMMITTER_EMAIL": "e2e@e2e", "HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")})


def room_rows(groups, room):
    return next((g["rows"] for g in groups if g["room"].startswith(room)), [])


async def run_spec_worktrees(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "spec-worktrees-before" if shots_only else "spec-worktrees"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    room = home / "work" / "room"
    specs = room / "docs" / "screens" / "json"
    specs.mkdir(parents=True, exist_ok=True)
    (room / "jui.config.json").write_text(json.dumps({"spec_directory": "docs/screens/json"}))
    (specs / "login.spec.json").write_text(json.dumps(spec("Login", "ログイン"), ensure_ascii=False))
    git(room, "init", "-q", "-b", "main", home=home)
    git(room, "add", "-A", home=home)
    git(room, "commit", "-q", "-m", "init", home=home)
    wt = home / "scratch" / "wt"
    git(room, "worktree", "add", "-q", "-b", "feat/x", str(wt), home=home)
    wt_specs = wt / "docs" / "screens" / "json"
    (wt_specs / "login.spec.json").write_text(json.dumps(spec("Login", "ログイン", "worktree で直している途中"), ensure_ascii=False))
    (wt_specs / "orders.spec.json").write_text(json.dumps(spec("Orders", "注文"), ensure_ascii=False))

    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, cwd, **payload):
        body = {"session_id": sid, "cwd": str(cwd), "permission_mode": "default", **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

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
        watch = Watch(origin=url)
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light")
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
        hook(SID_MAIN, room, hook_event_name="SessionStart", source="startup")
        hook(SID_WT, wt, hook_event_name="SessionStart", source="startup")
        await page.click("#spec-filter [data-f='all']")
        await wait(page, "() => document.querySelectorAll('#spec-list .spec-row').length >= 5", timeout=30000,
                   label="the room's three rows and the worktree room's two")
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(out / (("before" if shots_only else "after") + "-list.png")))
        if shots_only:
            return
        groups = res["list"] = await page.evaluate(LIST_JS)
        mine = sorted((r["name"], r["tag"]) for r in room_rows(groups, "room/"))
        check(failures, mine == [("ログイン", "⎇ feat/x"), ("ログイン", "⎇ main"), ("注文", "⎇ feat/x")],
              f"the room lists ログイン in both checkouts and 注文 of the worktree, each tagged: {groups}")
        check(failures, [r["wt"] for r in room_rows(groups, "room/") if r["tag"] == "⎇ feat/x"] == [True, True],
              f"the worktree's rows are marked as a worktree's: {groups}")
        theirs = sorted((r["name"], r["tag"]) for r in room_rows(groups, "wt/"))
        check(failures, theirs == [("ログイン", None), ("注文", None)], f"the worktree's own room lists its two, untagged: {groups}")

        # the room's 注文 (the worktree's) on the whiteboard
        await page.click("#spec-list .sl-group:has-text('room/') ~ li .spec-row:has-text('注文')")
        await wait(page, "() => { const c = document.getElementById('wb-close'); return !!(c && c.offsetParent) && document.getElementById('wb-title').textContent === '注文'; }",
                   timeout=20000, label="注文's sheet shown")
        await page.wait_for_timeout(900)
        side = res["side"] = await page.evaluate(SIDE_JS)
        check(failures, side["file"] == "⎇ feat/x · docs/screens/json/orders.spec.json",
              f"the open sheet's head says its branch and the file from the worktree's folder: {side['file']!r}")
        check(failures, any(a.endswith("⎇ feat/x") for a in side["apps"]), f"the app filter names the worktree: {side['apps']}")
        check(failures, sorted((i["name"], i["tag"]) for i in side["items"] if i["tag"]) == [("ログイン", "⎇ feat/x"), ("ログイン", "⎇ main"), ("注文", "⎇ feat/x")],
              f"the whiteboard's list carries the tags: {side['items']}")
        await page.screenshot(path=str(out / "after-sheet.png"))

        # a spec added to the room: the rows move, the sheet stays on 注文
        (specs / "aaa.spec.json").write_text(json.dumps(spec("Aaa", "あとから足した画面"), ensure_ascii=False))
        await wait(page, "() => [...document.querySelectorAll('#wb-side-list .ws-item .nm')].some((n) => n.textContent.includes('あとから足した画面'))",
                   timeout=20000, label="the added spec listed")
        await page.wait_for_timeout(400)
        side = await page.evaluate(SIDE_JS)
        check(failures, side["title"] == "注文" and side["file"].startswith("⎇ feat/x · "),
              f"a row added before it: the sheet stays on the worktree's 注文: {side['title']!r} {side['file']!r}")

        # the worktree's session ends: its rows leave the room, the sheet goes back to the overview
        hook(SID_WT, wt, hook_event_name="SessionEnd", reason="other")
        await wait(page, "() => ![...document.querySelectorAll('#spec-list .spec-row .co-tag')].length", timeout=20000,
                   label="the worktree's rows gone")
        await page.wait_for_timeout(400)
        groups = await page.evaluate(LIST_JS)
        mine = sorted((r["name"], r["tag"]) for r in room_rows(groups, "room/"))
        check(failures, mine == [("あとから足した画面", None), ("ログイン", None)], f"the room's own rows, untagged: {groups}")
        side = await page.evaluate(SIDE_JS)
        check(failures, side["title"] != "注文", f"the sheet of a row gone shows no other spec: {side['title']!r}")

        check(failures, not watch.console and not watch.foreign and not watch.csp,
              f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"spec-worktrees: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    import argparse
    import asyncio

    from playwright.async_api import async_playwright

    import e2e_lock

    ap = argparse.ArgumentParser(description="the room's list from another checkout (the before picture)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jt", required=True, help="that checkout's jui_tools")
    ap.add_argument("--shots-only", action="store_true")
    a = ap.parse_args()
    # the page's words in Japanese, as run.py pins them (a picture beside run.py's is in one language)
    os.environ.setdefault("JUI_VIZ_LANGUAGE", "ja")
    e2e_lock.hold(only=["spec-worktrees"])
    fails: list = []

    async def go():
        async with async_playwright() as pw:
            await run_spec_worktrees(pw, a.out, fails, jt=a.jt, shots_only=a.shots_only)

    asyncio.run(go())
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)
