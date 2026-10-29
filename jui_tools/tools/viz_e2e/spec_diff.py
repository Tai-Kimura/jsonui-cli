"""A worktree's spec beside the spec it started from (2.3.23, ticket 2026-10-24-viz-worktree-spec-diff-against-base).

The real `jui viz serve` in a throwaway HOME on a free port, two real git repositories made here:

- room/ on main: ログイン (variables, an event, an action, a Layout), プロフィール and 退会; a worktree outside the
  room on feat/x: ログイン with rows added, removed and rewritten (its description, a variable retyped, a Label
  renamed, a variable / an event / an action / a button added), プロフィール untouched, 退会 deleted, 注文 new
  (uncommitted). main moves on after the branch (the base stays where the branch left).
- room2/ with a worktree on feat/y whose parent then checks out an unrelated history: no merge-base.

At 1440 and 390 px, light and dark, the pictures the requester asked for before the integration:
  list-before / list-after   the worktree's list, the 「ベースとの差分」 button pressed: marks, and the deleted card
  diff-changed               ログイン: added, removed and rewritten rows beside each other
  diff-none                  プロフィール: 差はありません
  diff-new                   注文: the base has no such spec
  diff-deleted               退会 (from its faint card): the left all removed
  diff-unavailable           room2's spec: the base could not be read, and why
Checks: the counts and the rows' states as spec_diff.py pairs them, the reason said, the button on a worktree's spec
only, Esc closes and gives the focus back, no horizontal scroll at 390, no console error, nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, PHONE, Watch, new_page, ready

ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID_ROOM = "e2e00000-0000-4000-8000-000000000d01"
SID_WT = "e2e00000-0000-4000-8000-000000000d02"
SID_ROOM2 = "e2e00000-0000-4000-8000-000000000d03"
SID_WT2 = "e2e00000-0000-4000-8000-000000000d04"


def check(failures, cond, text):
    if not cond:
        failures.append(f"spec-diff: {text}")


async def wait(page, js, timeout=20000, label="", arg=None):
    try:
        await page.wait_for_function(js, arg=arg, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


def git(cwd, *args, home):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "e2e", "GIT_AUTHOR_EMAIL": "e2e@e2e", "GIT_COMMITTER_NAME": "e2e",
                        "GIT_COMMITTER_EMAIL": "e2e@e2e", "HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")})


def write(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def login(worktree: bool) -> dict:
    variables = [{"name": "email", "type": "String", "initialValue": '""'},
                 {"name": "password", "type": "String", "initialValue": '""'},
                 {"name": "isLoading", "type": "Bool", "initialValue": "false"}]
    events = [{"name": "onLoginTap", "description": "ログインを押した"}]
    actions = [{"action": "ログインを押す", "processing": "認証 API を呼ぶ", "destination": "ホーム"}]
    if worktree:
        variables[2]["type"] = "LoadState"
        variables[1:2] = []
        variables.append({"name": "rememberMe", "type": "Bool", "initialValue": "true"})
        events.append({"name": "onForgotTap", "description": "パスワードを忘れたを押した"})
        actions.append({"action": "パスワードを忘れたを押す", "processing": "再設定のメールを送る", "destination": "再設定"})
    return {"type": "screen_spec",
            "metadata": {"name": "Login", "displayName": "ログイン", "platforms": ["ios", "android"], "layoutFile": "login",
                         "description": "メールかSMSでログインする" if worktree else "メールとパスワードでログインする"},
            "stateManagement": {"uiVariables": variables, "eventHandlers": events}, "userActions": actions}


def login_layout(worktree: bool) -> dict:
    kids = [{"type": "Label", "id": "heading" if worktree else "title"}, {"type": "TextField", "id": "emailField"},
            {"type": "TextField", "id": "passwordField"}, {"type": "Button", "id": "loginButton"}]
    if worktree:
        kids.append({"type": "Button", "id": "forgotButton"})
    return {"type": "View", "id": "root", "child": kids}


def long_list(worktree: bool) -> dict:
    """A spec of 60 variables, v30's type changed in the worktree, and four event handlers no one changed: the folding
    (ticket 2026-10-29-viz-spec-diff-fold-unchanged) has a long run on each side of the change and a section to fold."""
    variables = [{"name": f"v{i:02d}", "type": "String", "initialValue": '""'} for i in range(60)]
    if worktree:
        variables[30]["type"] = "Int"
    events = [{"name": f"onTap{i}", "description": f"{i} を押した"} for i in range(4)]
    return {"type": "screen_spec", "metadata": {"name": "LongList", "displayName": "長い一覧", "description": "d", "platforms": ["ios"]},
            "stateManagement": {"uiVariables": variables, "eventHandlers": events}}


def simple(name, display, description="d"):
    return {"type": "screen_spec", "metadata": {"name": name, "displayName": display, "description": description, "platforms": ["ios"]}}


def make_rooms(home: pathlib.Path) -> dict:
    room = home / "work" / "room"
    specs, layouts = room / "docs" / "screens" / "json", room / "docs" / "screens" / "layouts"
    write(room / "jui.config.json", {"spec_directory": "docs/screens/json"})
    write(specs / "login.spec.json", login(False))
    write(layouts / "login.json", login_layout(False))
    write(specs / "profile.spec.json", simple("Profile", "プロフィール", "名前とアイコンを変える"))
    write(specs / "withdraw.spec.json", simple("Withdraw", "退会", "アカウントを消す"))
    write(specs / "long_list.spec.json", long_list(False))
    git(room, "init", "-q", "-b", "main", home=home)
    git(room, "add", "-A", home=home)
    git(room, "commit", "-q", "-m", "init", home=home)
    wt = home / "scratch" / "wt"
    git(room, "worktree", "add", "-q", "-b", "feat/x", str(wt), home=home)
    wspecs = wt / "docs" / "screens" / "json"
    write(wspecs / "login.spec.json", login(True))
    write(wt / "docs" / "screens" / "layouts" / "login.json", login_layout(True))
    (wspecs / "withdraw.spec.json").unlink()
    write(wspecs / "long_list.spec.json", long_list(True))
    git(wt, "add", "-A", home=home)
    git(wt, "commit", "-q", "-m", "login: remember me, forgot password; withdraw goes", home=home)
    write(wspecs / "orders.spec.json", simple("Orders", "注文", "カートの中身を注文する"))   # new, not committed
    write(specs / "later.spec.json", simple("Later", "あとから main に足した画面"))   # main after the branch
    git(room, "add", "-A", home=home)
    git(room, "commit", "-q", "-m", "later", home=home)

    room2 = home / "work" / "room2"
    write(room2 / "jui.config.json", {"spec_directory": "docs/screens/json"})
    write(room2 / "docs" / "screens" / "json" / "settings.spec.json", simple("Settings", "設定"))
    git(room2, "init", "-q", "-b", "main", home=home)
    git(room2, "add", "-A", home=home)
    git(room2, "commit", "-q", "-m", "init", home=home)
    wt2 = home / "scratch" / "wt2"
    git(room2, "worktree", "add", "-q", "-b", "feat/y", str(wt2), home=home)
    write(wt2 / "docs" / "screens" / "json" / "settings.spec.json", simple("Settings", "設定", "通知の設定を足した"))
    git(room2, "checkout", "-q", "--orphan", "unrelated", home=home)   # the parent now has no history in common
    git(room2, "commit", "-q", "-m", "unrelated", home=home)
    return {"room": room, "wt": wt, "room2": room2, "wt2": wt2}


# 長い一覧's diff as the page shows it: the variables shown, each gap's words and buttons, the event handlers' head
FOLD_JS = """() => { const sec = (k) => document.querySelector(`#sd-body [data-sd-sec='${k}']`).closest('.sd-sec');
  const v = sec('uiVariables'), e = sec('eventHandlers'), a = document.activeElement;
  return { vars: [...v.querySelectorAll('.sd-row')].map((r) => r.children[1].querySelector('.sd-t').textContent.split(':')[0]),
    chg: [...v.querySelectorAll('.sd-row.sd-chg')].map((r) => r.children[1].querySelector('.sd-t').textContent.split(':')[0]),
    gaps: [...v.querySelectorAll('.sd-gap')].map((g) => [g.querySelector('.sd-gap-n').textContent, [...g.querySelectorAll('button')].map((b) => b.textContent)]),
    varsHead: v.querySelector('[data-sd-sec]').getAttribute('aria-expanded'),
    events: { expanded: e.querySelector('[data-sd-sec]').getAttribute('aria-expanded'), rows: e.querySelectorAll('.sd-row').length,
              tag: (e.querySelector('h3 small') || {}).textContent || '' },
    focus: a && a.dataset && a.dataset.fk ? a.dataset.fk : null }; }"""

# a spec's index in the page's model: by its name and the app it is read from
IDX_JS = """([name, app]) => window.__dbg.sdIdx(name, app)"""
OPEN_JS = """(i) => window.__dbg.sdOpen(i)"""
SD_JS = """() => ({ open: !document.getElementById('sd').hidden, title: document.getElementById('sd-title').textContent,
  counts: document.getElementById('sd-counts').textContent, sides: document.getElementById('sd-sides').textContent,
  band: [...document.querySelectorAll('#sd-body .sd-band')].map((b) => b.textContent),
  notes: [...document.querySelectorAll('#sd-body .sd-note')].map((b) => b.textContent),
  rows: [...document.querySelectorAll('#sd-body .sd-sec')].map((sec) => ({ h: sec.querySelector('h3').firstChild.textContent,
    rows: [...sec.querySelectorAll('.sd-row')].map((r) => [r.className.replace('sd-row ', ''), r.children[0].textContent.slice(1), r.children[1].textContent.slice(1),
      [...r.children].map((c) => [...c.querySelectorAll('mark.sd-x')].map((m) => m.textContent))]) })),
  hscroll: document.scrollingElement.scrollWidth > window.innerWidth + 1 })"""


async def run_spec_diff(pw, out, failures, jt=None):
    from run import free_port
    name = "spec-diff"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    where = make_rooms(home)

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
        first = True
        for size, opts in (("1440", DESKTOP), ("390", PHONE)):
            for scheme in ("light", "dark"):
                tag = f"{size}-{scheme}"
                watch = Watch(origin=url)
                page = await new_page(browser, watch, f"{name}-{tag}", **opts)
                await page.emulate_media(color_scheme=scheme)
                await page.goto(url + "/")
                await ready(page)
                await wait(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", label="connected")
                if first:
                    for sid, cwd in ((SID_ROOM, where["room"]), (SID_WT, where["wt"]), (SID_ROOM2, where["room2"]), (SID_WT2, where["wt2"])):
                        hook(sid, cwd, hook_event_name="SessionStart", source="startup")
                    first = False
                await wait(page, "() => window.__dbg.sdWorktreeRows() >= 4", timeout=30000,
                           label="the two worktrees' specs")
                shot = lambda n: page.screenshot(path=str(out / f"{n}-{tag}.png"))   # noqa: E731
                r = res.setdefault(tag, {})

                # the worktree's list, before and after 「ベースとの差分」
                idx = await page.evaluate(IDX_JS, ["プロフィール", "@feat/x"])
                await page.evaluate(OPEN_JS, idx)
                await wait(page, "() => !document.getElementById('wb').hidden && document.getElementById('wb-title').textContent === 'プロフィール'", label="a sheet")
                await page.evaluate("() => window.__dbg.sdOpen(-1, '@feat/x')")
                await wait(page, "() => !document.getElementById('wb-diff').hidden && document.querySelectorAll('#wb-code .ov-card[data-idx]').length === 4",
                           label="the worktree's list with its button")
                await page.wait_for_timeout(500)
                await shot("list-before")
                await page.click("#wb-diff")
                await wait(page, "() => document.querySelectorAll('#wb-code .sd-gone').length === 1 && document.querySelectorAll('#wb-code .sd-mark').length >= 5",
                           label="the marks and the deleted card")
                await page.wait_for_timeout(300)
                r["list"] = await page.evaluate("""() => ({ marks: Object.fromEntries([...document.querySelectorAll('#wb-code .ov-card[data-idx]')].map((c) =>
                    [[...c.querySelector('strong').childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim(), (c.querySelector('.sd-mark') || {}).textContent || ''])),
                    gone: [...document.querySelectorAll('#wb-code .sd-gone strong')].map((s) => s.textContent),
                    button: document.getElementById('wb-diff').textContent })""")
                await shot("list-after")

                # one spec at a time
                async def diff(display, app, label, opener=None):
                    if opener is None:
                        i = await page.evaluate(IDX_JS, [display, app])
                        await page.evaluate(OPEN_JS, i)
                        await wait(page, f"() => document.getElementById('wb-title').textContent === {json.dumps(display)} && !document.getElementById('wb-diff').hidden",
                                   label=f"{display}'s sheet with the button")
                        await page.click("#wb-diff")
                    else:
                        await page.click(opener)
                    await wait(page, "() => !document.getElementById('sd').hidden && !document.querySelector('#sd-body').textContent.includes('…')",
                               label=f"{display}'s diff")
                    await page.wait_for_timeout(300)
                    got = r[label] = await page.evaluate(SD_JS)
                    await shot(label)
                    await page.keyboard.press("Escape")
                    await wait(page, "() => document.getElementById('sd').hidden", label="Esc closes")
                    return got

                async def fold_arm(page, r, shot, tag):
                    """Unchanged rows folded as GitHub folds (ticket 2026-10-29-viz-spec-diff-fold-unchanged): 長い一覧's variables
                    show v27..v33 (3 on each side of v30), the 27 rows before and the 26 after are one line each; ↑ / ↓ open 20 at a
                    time from the change's side, 全部 the rest; the event handlers, unchanged, are a folded head that opens."""
                    i = await page.evaluate(IDX_JS, ["長い一覧", "@feat/x"])
                    await page.evaluate(OPEN_JS, i)
                    await wait(page, "() => document.getElementById('wb-title').textContent === '長い一覧' && !document.getElementById('wb-diff').hidden",
                               label="長い一覧's sheet with the button")
                    await page.click("#wb-diff")
                    await wait(page, "() => !document.getElementById('sd').hidden && document.querySelector('#sd-body .sd-gap')", label="長い一覧's diff, folded")
                    await page.wait_for_timeout(300)
                    f = r["fold"] = await page.evaluate(FOLD_JS)
                    await shot("fold-folded")
                    check(failures, f["vars"] == [f"v{k}" for k in range(27, 34)] and f["gaps"] == [["⋯ 変わらない 27 行", ["↑ 上へ 20 行", "全部（27 行）"]], ["⋯ 変わらない 26 行", ["↓ 下へ 20 行", "全部（26 行）"]]],
                          f"{tag}: folded: v27..v33 shown (3 rows each side of v30), 27 and 26 unchanged rows one line each: {f}")
                    check(failures, f["events"] == {"expanded": "false", "rows": 0, "tag": "変更なし · 4 行"},
                          f"{tag}: the event handlers, unchanged, are a folded head: {f['events']}")
                    check(failures, f["chg"] == ["v30"], f"{tag}: the changed row is never folded: {f['chg']}")
                    await page.click("#sd-body .sd-gap >> nth=0 >> text=↑ 上へ 20 行")
                    f = r["fold-up"] = await page.evaluate(FOLD_JS)
                    check(failures, f["vars"] == [f"v{k:02d}" for k in range(7, 34)] and f["gaps"][0][0] == "⋯ 変わらない 7 行" and f["gaps"][0][1] == ["7 行を表示"],
                          f"{tag}: ↑ opens the 20 rows next to the change (v07..v26), 7 left with one button: {f['vars'][:3]} {f['gaps']}")
                    check(failures, f["focus"] is not None and f["focus"].startswith("sd-gap"), f"{tag}: the focus stays on the gap: {f['focus']}")
                    await page.click("#sd-body .sd-gap >> nth=1 >> text=↓ 下へ 20 行")
                    f = r["fold-down"] = await page.evaluate(FOLD_JS)
                    check(failures, f["vars"][-1] == "v53" and f["gaps"][-1][0] == "⋯ 変わらない 6 行",
                          f"{tag}: ↓ opens the 20 rows after the change (to v53), 6 left: {f['vars'][-3:]} {f['gaps']}")
                    await page.click("#sd-body .sd-gap >> nth=1 >> text=6 行を表示")
                    await page.click("#sd-body .sd-gap >> nth=0 >> text=7 行を表示")
                    f = r["fold-all"] = await page.evaluate(FOLD_JS)
                    check(failures, f["vars"] == [f"v{k:02d}" for k in range(60)] and f["gaps"] == [],
                          f"{tag}: every row shown once each gap is opened: {len(f['vars'])} {f['gaps']}")
                    await page.click("#sd-body [data-sd-sec='eventHandlers']")
                    f = r["fold-events"] = await page.evaluate(FOLD_JS)
                    check(failures, f["events"]["expanded"] == "true" and f["events"]["rows"] == 4 and f["focus"] == "sd-sec-eventHandlers",
                          f"{tag}: the unchanged section opens from its head, which keeps the focus: {f['events']} {f['focus']}")
                    await page.evaluate("() => { const b = document.getElementById('sd-body'); b.scrollTop = b.scrollHeight; }")
                    await page.wait_for_timeout(200)
                    await shot("fold-open")
                    await page.click("#sd-body [data-sd-sec='uiVariables']")
                    f = r["fold-sec"] = await page.evaluate(FOLD_JS)
                    check(failures, f["vars"] == [] and f["varsHead"] == "false", f"{tag}: a changed section folds from its head too: {f['varsHead']}")
                    await page.keyboard.press("Escape")
                    await wait(page, "() => document.getElementById('sd').hidden", label="Esc closes")
                    # opened again: folded as at first
                    await page.click("#wb-diff")
                    await wait(page, "() => !document.getElementById('sd').hidden && document.querySelector('#sd-body .sd-gap')", label="長い一覧's diff again")
                    f = r["fold-again"] = await page.evaluate(FOLD_JS)
                    check(failures, f["vars"] == [f"v{k}" for k in range(27, 34)] and f["events"]["expanded"] == "false",
                          f"{tag}: opened again, it is folded as at first: {f['vars']} {f['events']}")
                    await page.keyboard.press("Escape")
                    await wait(page, "() => document.getElementById('sd').hidden", label="Esc closes")

                await page.evaluate("() => window.__dbg.sdOpen(-1, 'all')")
                got = await diff("ログイン", "@feat/x", "diff-changed")
                r["focus-back"] = await page.evaluate("() => document.activeElement && document.activeElement.id")
                await diff("プロフィール", "@feat/x", "diff-none")
                await diff("注文", "@feat/x", "diff-new")
                await page.evaluate("() => window.__dbg.sdOpen(-1, '@feat/x')")
                await wait(page, "() => document.querySelectorAll('#wb-code .sd-gone').length === 1", label="the deleted card again")
                await diff("退会", "@feat/x", "diff-deleted", opener="#wb-code .sd-gone")
                await page.evaluate("() => window.__dbg.sdOpen(-1, 'all')")
                await diff("設定", "@feat/y", "diff-unavailable")
                await fold_arm(page, r, shot, tag)
                # the room's own spec has no button
                i = await page.evaluate(IDX_JS, ["ログイン", ""])
                await page.evaluate(OPEN_JS, i)
                await wait(page, "() => document.getElementById('wb-title').textContent === 'ログイン'", label="the room's ログイン")
                await page.wait_for_timeout(300)
                r["room-button"] = await page.evaluate("() => document.getElementById('wb-diff').hidden")
                check(failures, not watch.console and not watch.foreign and not watch.csp,
                      f"{tag}: no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
                await page.close()

        for tag, r in res.items():
            ch = r.get("diff-changed", {})
            check(failures, ch.get("counts") == "+5−2~2",
                  f"{tag}: ログイン's counts (added heading, forgotButton, rememberMe, onForgotTap, an action; removed title, password; rewritten the description and isLoading): {ch.get('counts')!r}")
            sections = {s["h"]: s["rows"] for s in ch.get("rows", [])}
            variables = [(st, l or rr) for st, l, rr, _m in next((v for k, v in sections.items() if "変数" in k), [])]
            # the changed column only, on both sides: isLoading's type, the description's text (not its name)
            marks = {(l or rr).split(":")[0]: m for _h, rows in sections.items() for st, l, rr, m in rows if st == "sd-chg"}
            check(failures, marks.get("isLoading") == [["Bool"], ["LoadState"]],
                  f"{tag}: isLoading: the type is marked on both sides, the name is not: {marks.get('isLoading')}")
            check(failures, marks.get("description") == [["メールとパスワードでログインする"], ["メールかSMSでログインする"]],
                  f"{tag}: the description: its text is marked on both sides, its name is not: {marks.get('description')}")
            check(failures, [st for st, _ in variables] == ["sd-same", "sd-del", "sd-chg", "sd-add"],
                  f"{tag}: the variables: email same, password removed, isLoading rewritten, rememberMe added: {variables}")
            check(failures, r.get("focus-back") == "wb-diff", f"{tag}: Esc gives the focus back to the button: {r.get('focus-back')!r}")
            check(failures, any("差はありません" in b for b in r.get("diff-none", {}).get("band", [])), f"{tag}: プロフィール says no difference: {r.get('diff-none', {}).get('band')}")
            check(failures, any("新しいファイル" in n for n in r.get("diff-new", {}).get("notes", [])), f"{tag}: 注文 is new: {r.get('diff-new', {}).get('notes')}")
            dl = r.get("diff-deleted", {})
            check(failures, any("消した" in n for n in dl.get("notes", [])) and "~0" in dl.get("counts", "") and "+0" in dl.get("counts", ""),
                  f"{tag}: 退会 is deleted, its left all removed: {dl.get('notes')} {dl.get('counts')!r}")
            un = r.get("diff-unavailable", {})
            check(failures, any("元が取れません" in b and "分かれた所が見つからない" in b for b in un.get("band", [])),
                  f"{tag}: room2's base cannot be read, and why: {un.get('band')}")
            lst = r.get("list", {})
            check(failures, lst.get("gone") == ["退会"] and lst.get("marks", {}).get("注文") == "新規" and lst.get("marks", {}).get("プロフィール") == "差なし"
                  and lst.get("marks", {}).get("ログイン") == "+5−2~2", f"{tag}: the list's marks and the deleted card: {lst}")
            check(failures, r.get("room-button") is True, f"{tag}: the room's own spec has no button")
            if tag.startswith("390"):
                check(failures, not any(v.get("hscroll") for v in r.values() if isinstance(v, dict) and "hscroll" in v),
                      f"{tag}: no horizontal scroll at 390 px")
    except Exception as e:
        failures.append(f"spec-diff: {type(e).__name__}: {str(e).splitlines()[0]}")
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
