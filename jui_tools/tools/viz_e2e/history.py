"""The 応答の履歴 tab, end to end (requester, 10-18).

The real `jui viz serve` in a throwaway HOME (its own ~/.claude/projects holds a fake transcript) on a free port, the
real forward.py for the session's hooks. The robot card's 応答の履歴 tab shows the conversation: Markdown answers,
folded tool calls with IN / OUT, another session's message apart from the requester's words, the harness's text
folded, marks for thinking and images. Every hostile sample stays text — no element, attribute or handler comes from
the transcript, and a link gets an href only for http(s). A line appended to the transcript shows while the tab is
open. Dark mode and 390 px, no console error, nothing requested outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import ISOLATE, DESKTOP, LAUNCH_ARGS, PHONE, Watch, dump, new_page, ready

SID = "e2e00000-0000-4000-8000-0000000000b7"
CWD = "/work/hist-app"
HOSTILE = [
    '<img src=x onerror="window.__pwned=1">',
    '</script><script>window.__pwned=2</script>',
    '[js](javascript:window.__pwned=3)',
    '[JS](JaVaScRiPt:window.__pwned=4)',
    '[ent](&#106;avascript:window.__pwned=5)',
    '[q](https://a" onmouseover="window.__pwned=6)',
]
ANSWER = "\n".join([
    "## 見出しの応答",
    "- **太字** と `インライン <b>コード</b>`",
    "- [安全なリンク](https://example.invalid/page)",
    "",
    "| 列 | 値 |",
    "|---|---|",
    "| a | 1 |",
    "",
    "```",
    "**太字** <b>コードの中</b>",
    "```",
    "",
    "![画像の説明](https://example.invalid/x.png)",
    "",
    *HOSTILE,
])


def records():
    def user(text, **extra):
        return {"type": "user", "timestamp": "2026-10-18T09:00:00Z", "message": {"role": "user", "content": text}, **extra}

    return [
        user("履歴を見せて " + HOSTILE[0]),
        user('Another Claude session sent a message:\n<cross-session-message from="uds:/tmp/x.sock" from-name="jsonui-5b">\n票を振りました\n</cross-session-message>'),
        user("<system-reminder>\nharness note\n</system-reminder>", isMeta=True),
        {"type": "assistant", "timestamp": "2026-10-18T09:00:01Z",
         "message": {"id": "m1", "role": "assistant", "content": [{"type": "thinking", "thinking": "THINK-SECRET", "signature": "s"}]}},
        {"type": "assistant", "timestamp": "2026-10-18T09:00:02Z",
         "message": {"id": "m2", "role": "assistant", "content": [{"type": "tool_use", "id": "toolu_e2e", "name": "Bash",
                                                                    "input": {"command": "ls -la " + HOSTILE[1], "description": "一覧を見る"}}]}},
        {"type": "user", "timestamp": "2026-10-18T09:00:03Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_e2e", "content": "total 0 " + HOSTILE[0]}]}},
        {"type": "assistant", "timestamp": "2026-10-18T09:00:04Z",
         "message": {"id": "m3", "role": "assistant", "content": [{"type": "text", "text": ANSWER}]}},
        user([{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}]),
    ]


def check(failures, cond, text):
    if not cond:
        failures.append(f"history: {text}")


async def wait(page, js, timeout=20000, label=""):
    try:
        await page.wait_for_function(js, timeout=timeout, polling=200)
    except Exception as e:
        raise RuntimeError(f"waiting for {label or js[:90]}: {str(e).splitlines()[0]}") from None


INSPECT = """() => {
  const pane = document.querySelector('[data-rb-hist]');
  const all = [...pane.querySelectorAll('*')];
  const attrs = all.flatMap((n) => [...n.attributes].map((a) => a.name));
  return {
    shown: !pane.hidden, nowHidden: document.querySelector('#rb .rb-body:not([data-rb-hist])').hidden,
    tags: [...new Set(all.map((n) => n.tagName.toLowerCase()))].sort(),
    handlers: attrs.filter((a) => a.startsWith('on')),
    hrefs: [...pane.querySelectorAll('a')].map((a) => a.getAttribute('href')),
    linkAttrs: [...pane.querySelectorAll('a')].map((a) => [a.getAttribute('target'), a.getAttribute('rel')]),
    pwned: window.__pwned || 0,
    text: pane.textContent,
    kinds: [...pane.querySelectorAll('.h-item')].map((n) => n.className.replace('h-item ', '')),
    heading: (pane.querySelector('.h-asst .h-h') || {}).textContent || '',
    fromText: [...pane.querySelectorAll('.h-md *, .h-plain *, pre *')].map((n) => n.tagName.toLowerCase()).filter((t) => !['p', 'br', 'strong', 'em', 'code', 'a', 'ul', 'ol', 'li', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'h4', 'h5', 'h6', 'hr', 'pre', 'blockquote'].includes(t)),
    strong: [...pane.querySelectorAll('.h-asst strong')].map((n) => n.textContent),
    codeBlock: (pane.querySelector('.h-asst pre code') || {}).textContent || '',
    codeChildren: pane.querySelector('.h-asst pre code') ? pane.querySelector('.h-asst pre code').children.length : -1,
    inline: [...pane.querySelectorAll('.h-asst p code, .h-asst li code')].map((n) => n.textContent),
    cells: [...pane.querySelectorAll('.h-asst td')].map((n) => n.textContent),
    peer: (pane.querySelector('.h-peer summary') || {}).textContent || '',
    peerOpen: !!(pane.querySelector('.h-peer') || {}).open,
    harness: (pane.querySelector('.h-harness summary') || {}).textContent || '',
    harnessOpen: !!(pane.querySelector('.h-harness') || {}).open,
    tool: (pane.querySelector('.h-tool summary') || {}).textContent || '',
    io: [...pane.querySelectorAll('.h-tool .h-io pre')].map((n) => n.textContent),
    marks: [...pane.querySelectorAll('.h-mark')].map((n) => n.textContent),
  };
}"""


async def run_history(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "history"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    (home / ".local" / "state" / "jui-viz").mkdir(parents=True, exist_ok=True)
    transcript = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD) / f"{SID}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records()))
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}
    base = {"session_id": SID, "cwd": CWD, "transcript_path": str(transcript), "permission_mode": "default"}

    def hook(payload):
        p = subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(payload).encode(),
                           capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)
        return p.returncode

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
        page = await new_page(browser, watch, "history", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await wait(page, "() => document.querySelector('.chip.demo').textContent === '接続中'", label="connected")
        hook(dict(base, hook_event_name="SessionStart", source="startup"))
        await wait(page, "() => !!document.querySelector('#sessions [data-robot-open]')", label="the session's robot")
        await page.click("#sessions [data-robot-open]")
        await wait(page, "() => !!document.querySelector('#rb [data-rb-tab=\"history\"]')", label="the robot card's tabs")
        res["before"] = await page.evaluate("() => ({ hist: document.querySelector('[data-rb-hist]').hidden, now: document.querySelector('#rb .rb-body:not([data-rb-hist])').hidden })")
        check(failures, res["before"] == {"hist": True, "now": False}, f"the card opens on 今の様子: {res['before']}")
        await page.click('#rb [data-rb-tab="history"]')
        await wait(page, "() => document.querySelectorAll('[data-rb-hist] .h-item').length >= 7", label="the history")
        r = res["shown"] = await page.evaluate(INSPECT)
        # what is there
        check(failures, r["shown"] and r["nowHidden"], f"the tab fills the card: {r['shown']}, {r['nowHidden']}")
        check(failures, r["kinds"][:3] == ["h-user", "h-peer", "h-harness"] and "h-tool" in r["kinds"] and "h-asst" in r["kinds"],
              f"the items in order: {r['kinds']}")
        check(failures, r["heading"] == "見出しの応答" and "太字" in r["strong"] and r["cells"] == ["a", "1"],
              f"the answer is Markdown: {r['heading']!r} {r['strong']} {r['cells']}")
        check(failures, r["codeBlock"] == "**太字** <b>コードの中</b>" and r["codeChildren"] == 0, f"a code block is left as written: {r['codeBlock']!r} children {r['codeChildren']}")
        check(failures, "インライン <b>コード</b>" in r["inline"], f"inline code is left as written: {r['inline']}")
        check(failures, r["peer"].startswith("jsonui-5b から") and not r["peerOpen"], f"another session's message is apart and folded: {r['peer']!r}")
        check(failures, r["harness"].startswith("システムの注記") and not r["harnessOpen"], f"the harness's text is folded: {r['harness']!r}")
        check(failures, r["tool"].startswith("Bash一覧を見る") and r["io"][0].startswith("ls -la ") and r["io"][1].startswith("total 0"),
              f"a tool call: its description folded, IN and OUT inside: {r['tool']!r} {r['io']}")
        check(failures, r["marks"] == ["考えた", "画像 1 枚"] and "THINK-SECRET" not in r["text"], f"thinking and images are marks: {r['marks']}")
        # what must not be there
        check(failures, r["handlers"] == [] and r["pwned"] == 0, f"no handler from the transcript: {r['handlers']} pwned {r['pwned']}")
        check(failures, not ({"img", "script", "iframe"} & set(r["tags"])) and r["fromText"] == [], f"no element from the transcript: {r['tags']} {r['fromText']}")
        check(failures, r["hrefs"] == ["https://example.invalid/page"] and r["linkAttrs"] == [["_blank", "noopener noreferrer"]],
              f"only the http(s) link has an href: {r['hrefs']} {r['linkAttrs']}")
        for sample in HOSTILE[2:5]:
            check(failures, sample in r["text"], f"a link that is not http(s) stays text: {sample}")
        check(failures, "画像: 画像の説明" in r["text"], "an image in Markdown is a mark (not fetched)")
        await page.screenshot(path=str(out / "history.png"))
        # the tool call opens to IN and OUT
        await page.click("[data-rb-hist] .h-tool summary")
        res["toolOpen"] = await page.evaluate("() => document.querySelector('[data-rb-hist] .h-tool').open")
        check(failures, res["toolOpen"] is True, "the tool call opens")

        # a new line while the tab is open: it shows (and an open fold stays open)
        with open(transcript, "a") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-18T09:01:00Z",
                                "message": {"id": "m9", "role": "assistant", "content": [{"type": "text", "text": "追記された応答"}]}}, ensure_ascii=False) + "\n")
        t1 = time.monotonic()
        await wait(page, "() => document.querySelector('[data-rb-hist]').textContent.includes('追記された応答')", timeout=10000, label="the appended answer")
        res["follow"] = round(time.monotonic() - t1, 1)
        check(failures, res["follow"] < 8, f"the open tab follows the transcript: {res['follow']} s")

        # dark and 390 px
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(out / "history-dark.png"))
        phone = await new_page(browser, watch, "history-phone", **PHONE)
        await phone.goto(url + "/")
        await ready(phone)
        await wait(phone, "() => !!document.querySelector('#sessions [data-robot-open]')", label="the phone's robot")
        await phone.evaluate("() => document.querySelector('#sessions [data-robot-open]').click()")
        await wait(phone, "() => !!document.querySelector('#rb [data-rb-tab=\"history\"]')", label="the phone's card")
        await phone.click('#rb [data-rb-tab="history"]')
        await wait(phone, "() => document.querySelectorAll('[data-rb-hist] .h-item').length >= 7", label="the phone's history")
        res["phone"] = await phone.evaluate("() => ({ hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth })")
        await phone.screenshot(path=str(out / "history-phone.png"))
        check(failures, res["phone"] == {"hscroll": False}, f"390 px: no horizontal scroll: {res['phone']}")
        await phone.close()
        await page.close()
        for line in watch.console:
            failures.append(f"history: console: {line}")
        for u in watch.foreign:
            failures.append(f"history: request outside the server: {u}")
        res["console"] = len(watch.console)
    except Exception as e:
        failures.append(f"history: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        await browser.close()
    print(f"  history/tab: {time.monotonic() - t0:.0f}s", flush=True)
    (out / "history-results.json").write_text(dump(res) + "\n")
