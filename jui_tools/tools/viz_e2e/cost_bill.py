"""The bill over a robot (2.3.6, ticket 2026-10-19-jui-viz-cost-bill-over-robot), end to end.

The real `jui viz serve` in a throwaway HOME on a free port; two sessions in one room and a subagent through the real
forward.py, their transcripts under the throwaway ~/.claude/projects, appended to as Claude Code writes them (one
message on three lines with the same usage, measured 10-19). Each response shows a banknote and its estimated cost over
the robot that made it — the subagent's over its own — above its name tag and on no tag; it goes after a few seconds;
two responses close together are one sum. A model with no price: ? and the tokens, never an amount, and the top bar
says so; the chip opens the 単価 sheet, where the price is added (the next response is priced, no restart), changed,
removed and put back; `jui viz prices` changes it too, and a broken row in the user's table is left out alone, said on
the sheet. 設定 › お札 off: no bill. Reduced motion: no rise. A write without the token is refused. Light and dark
pictures (`--jt` takes the before pictures from another tree).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

from common import DESKTOP, LAUNCH_ARGS, Watch, new_page, ready
from waits import settled, until

CWD = "/work/bill-app"
ISOLATE = ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_TEST_PROGRESS_DIR", "JSONUI_TEST_RESULTS_DIR")
SID = "e2e00000-0000-4000-8000-0000000005{:02x}"
SUB = "a5ub0000000000e2"
USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 2252, "cache_read_input_tokens": 67349, "output_tokens": 936,
         "output_tokens_details": {"thinking_tokens": 247}, "service_tier": "standard",
         "cache_creation": {"ephemeral_1h_input_tokens": 2252, "ephemeral_5m_input_tokens": 0},
         "inference_geo": "global", "speed": "standard"}
TOKENS = 2 + 2252 + 67349 + 936
# opus 5.5: 2×4 + 2252×8 + 67349×0.2 + 936×20 per million = $0.0502 (counted three times: $0.15; no cache reads: $0.04)
OPUS_TEXT = "≈ $0.05"
FAKE = "claude-zzz-9"
FAKE_ROW = {"input": 1, "cache_write_5m": 1.25, "cache_write_1h": 2, "cache_read": 0.1, "output": 50}
# with FAKE_ROW: 2×1 + 2252×2 + 67349×0.1 + 936×50 per million = $0.0581
FAKE_TEXT = "≈ $0.06"

BILLS_JS = """() => window.__dbg.robots.map((R) => { const b = R.bill, box = (el) => { const r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; };
  const shown = !!b && !b.hidden && getComputedStyle(b).visibility !== 'hidden';
  return { id: R.def.id, kind: R.def.kind, sid: R.def.sessionId || '', shown, text: shown ? b.textContent : '', unknown: !!b && b.classList.contains('unknown'),
    rise: !!b && b.firstElementChild.classList.contains('rise'), anim: b ? getComputedStyle(b.firstElementChild).animationName : '',
    n: b ? Number(b.dataset.n || 0) : 0, bill: shown ? box(b.firstElementChild) : null,
    tag: getComputedStyle(R.tag).visibility !== 'hidden' && R.robot.root.visible ? box(R.tag) : null, title: b ? b.title : '' }; })"""


# Two tags stacked: the lower one (the nearer robot, which keeps its spot) and one just above it that was moved up, over
# the lower one's middle, where its bill goes.
STACK_JS = """() => { const L = window.__dbg.robots.filter((R) => R.tag.style.visibility !== 'hidden' && R.robot.root.visible)
    .map((R) => ({ id: R.def.id, t: R.tagTarget || 0, r: R.tag.getBoundingClientRect() }));
  for (const a of L) for (const b of L) { const cx = (a.r.left + a.r.right) / 2;   // the bill stands over the tag's middle
    if (a !== b && a.t < 0.5 && b.t > 0.5 && b.r.left < cx - 30 && b.r.right > cx + 30
      && b.r.bottom <= a.r.top + 1 && a.r.top - b.r.bottom < 12) return { low: a.id, high: b.id }; }
  return null; }"""


def check(failures, cond, text):
    if not cond:
        failures.append(f"cost-bill: {text}")


def _iso(at):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(at)) + ".000Z"


def _rec(mid, model="claude-opus-5-5", block="text", usage=None):
    return {"type": "assistant", "timestamp": _iso(time.time()), "sessionId": "x", "uuid": f"u-{mid}-{block}",
            "message": {"id": mid, "model": model, "role": "assistant", "content": [{"type": block, "text": "…"}],
                        "usage": usage or USAGE}}


def _append(path, *recs):
    with open(path, "a") as h:
        for r in recs:
            h.write(json.dumps(r) + "\n")


def _overlaps(a, b):
    return a["l"] < b["r"] - 0.5 and b["l"] < a["r"] - 0.5 and a["t"] < b["b"] - 0.5 and b["t"] < a["b"] - 0.5


async def run_cost_bill(pw, out, failures, jt=None, shots_only=False):
    from run import free_port
    name = "cost-bill-before" if shots_only else "cost-bill"
    out = pathlib.Path(out) / name
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    home.mkdir(exist_ok=True)
    jt = pathlib.Path(jt) if jt else pathlib.Path(__file__).resolve().parents[2]
    forward = jt / "jui_cli" / "viz" / "forward.py"
    port = free_port()
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    proj = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", CWD)
    (proj / SID.format(0) / "subagents").mkdir(parents=True, exist_ok=True)
    tr = {i: proj / f"{SID.format(i)}.jsonl" for i in range(2)}
    sub_tr = proj / SID.format(0) / "subagents" / f"agent-{SUB}.jsonl"
    for p in [*tr.values(), sub_tr]:
        p.write_text(json.dumps({"type": "user", "timestamp": _iso(time.time()), "message": {"role": "user", "content": "hi"}}) + "\n")
    base_env = {k: v for k, v in os.environ.items() if k not in ISOLATE}
    env = dict(base_env, HOME=str(home), JUI_VIZ_E2E="1")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(jt / "bin" / "jui"), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                           stdout=log, stderr=subprocess.STDOUT, env=env)
    url = f"http://127.0.0.1:{port}"
    res: dict = {}

    def hook(sid, **payload):
        body = {"session_id": sid, "cwd": CWD, "permission_mode": "default", "transcript_path": str(tr[int(sid[-2:], 16) - 0]), **payload}
        subprocess.run([sys.executable, "-I", "-S", str(forward)], input=json.dumps(body).encode(),
                       capture_output=True, env=dict(base_env, HOME=str(home)), timeout=10)

    def cli(*args):
        return subprocess.run([sys.executable, str(jt / "bin" / "jui"), "viz", "prices", *args], capture_output=True, text=True,
                              env=dict(base_env, HOME=str(home)), timeout=30)

    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    t0 = time.monotonic()
    try:
        import urllib.error
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)
        watch = Watch(origin=url)
        page = await new_page(browser, watch, name, **DESKTOP)
        await page.emulate_media(color_scheme="light", reduced_motion="no-preference")
        await page.goto(url + "/")
        await ready(page)
        await until(page, "() => document.querySelector('.chip.demo').dataset.net === 'connected'", "connected")
        for i in range(2):
            hook(SID.format(i), hook_event_name="SessionStart", source="startup")
            hook(SID.format(i), hook_event_name="PreToolUse", tool_name="Read", tool_use_id=f"r{i}",
                 tool_input={"file_path": f"{CWD}/docs/screens/json/screen-{i}.spec.json"})
        hook(SID.format(0), hook_event_name="SubagentStart", agent_id=SUB, agent_type="Explore", agent_transcript_path=str(sub_tr))
        hook(SID.format(0), hook_event_name="PreToolUse", agent_id=SUB, agent_type="Explore", agent_transcript_path=str(sub_tr),
             tool_name="Grep", tool_use_id="g1", tool_input={"pattern": "x"})
        await until(page, "() => window.__dbg.robots.length >= 3", "three robots", timeout=30000)
        await settled(page, "seated")
        labels = await page.evaluate("() => Object.fromEntries(window.__dbg.robots.map((R) => [R.def.kind === 'sub' ? 'sub' : R.def.sessionId, R.def.id]))")
        main, other, sub = labels[SID.format(0)], labels[SID.format(1)], labels["sub"]
        res["labels"] = labels
        time.sleep(2.5)    # the server's usage poll (every 2 s) has seen each transcript once: what follows is new

        async def bills():
            return {b["id"]: b for b in await page.evaluate(BILLS_JS)}

        async def wait_bill(label, what, js_cond="b.shown"):
            return await until(page, f"(id) => {{ const b = ({BILLS_JS})().find((x) => x.id === id); return b && ({js_cond}) ? b : null; }}",
                               what, arg=label, timeout=20000, why=BILLS_JS)

        async def shots(tag):
            for scheme in ("light", "dark"):
                await page.emulate_media(color_scheme=scheme)
                _append(tr[0], _rec(f"shot-{tag}-{scheme}-a"))
                _append(sub_tr, _rec(f"shot-{tag}-{scheme}-s", model="claude-haiku-5-5"))
                _append(tr[1], _rec(f"shot-{tag}-{scheme}-b", model=FAKE if tag == "after" else "claude-opus-5-5"))
                if tag == "after":
                    await wait_bill(main, f"a bill for the picture ({scheme})")
                    await page.wait_for_timeout(700)
                else:
                    await page.wait_for_timeout(3000)
                await page.screenshot(path=str(out / f"{tag}-{scheme}.png"))
                await page.wait_for_timeout(4500)
            await page.emulate_media(color_scheme="light")

        if shots_only:
            await shots("before")
            return

        # 1. one message on three lines: one bill, its amount by the table (opus 5.5), over the robot that made it
        _append(tr[0], _rec("msg_a1", block="thinking"), _rec("msg_a1", block="text"), _rec("msg_a1", block="tool_use"))
        b = await wait_bill(main, "the main robot's bill")
        await page.wait_for_timeout(2600)            # a second poll: the same lines read again must not add
        b = (await bills())[main]
        res["first"] = b
        check(failures, b["text"] == OPUS_TEXT and b["n"] == 1 and not b["unknown"],
              f"one response, written on three lines, is one bill of {OPUS_TEXT} (the four kinds at opus 5.5's prices): {b}")
        check(failures, "概算" in b["title"] and "サブスクリプション" in b["title"], f"the bill says it is an estimate: {b['title']!r}")
        others = await bills()
        check(failures, not others[other]["shown"] and not others[sub]["shown"], f"only the robot that responded shows a bill: {others}")

        # 2. above its own tag, on no tag (every robot's, same room)
        all_b = await bills()
        mine = all_b[main]
        check(failures, mine["bill"] and mine["tag"] and mine["bill"]["b"] <= mine["tag"]["t"] + 0.5,
              f"the bill sits above its robot's tag: {mine['bill']} / {mine['tag']}")
        for x in all_b.values():
            if x["tag"] and mine["bill"]:
                check(failures, not _overlaps(mine["bill"], x["tag"]), f"the bill covers {x['id']}'s tag: {mine['bill']} / {x['tag']}")

        # 3. it goes after a few seconds; two responses close together are one sum
        await until(page, f"() => !({BILLS_JS})().find((x) => x.id === '{main}').shown", "the bill goes", timeout=15000, why=BILLS_JS)
        _append(tr[0], _rec("msg_a2"))
        await wait_bill(main, "the next response's bill")
        _append(tr[0], _rec("msg_a3"))
        b = await wait_bill(main, "two responses summed", "b.n === 2")
        res["sum"] = b
        check(failures, b["text"] == "≈ $0.10", f"two responses while one shows: their sum on one bill: {b}")

        # 4. the subagent's response over its own robot (haiku 5.5: under a cent)
        _append(sub_tr, _rec("msg_s1", model="claude-haiku-5-5"))
        b = await wait_bill(sub, "the subagent's bill")
        res["sub"] = b
        check(failures, b["text"] == "< $0.01" and b["kind"] == "sub", f"a subagent's response is billed over its own robot: {b}")

        # 5. a model with no price: ? and the tokens, never an amount; the top bar says so
        _append(tr[1], _rec("msg_x1", model=FAKE))
        b = await wait_bill(other, "the unpriced bill")
        res["unpriced"] = b
        check(failures, b["unknown"] and b["text"].startswith("? ") and "$" not in b["text"] and "70.5k" in b["text"],
              f"a model not in the table: ? and its tokens, no amount: {b}")
        chip = await until(page, "() => { const c = document.getElementById('chip-price'); return !c.hidden && c.textContent; }", "the chip")
        check(failures, "1" in chip, f"the top bar tells of the unpriced model: {chip!r}")

        # 6. the chip opens the sheet on that model; the price added there applies to the next response, no restart
        await page.click("#chip-price")
        await until(page, "() => !document.getElementById('pr').hidden && document.querySelector('[data-pr-in=\"model\"]')", "the sheet with its form")
        got_model = await page.input_value("[data-pr-in='model']")
        check(failures, got_model == FAKE, f"the form starts on the unpriced model: {got_model!r}")
        for k, v in FAKE_ROW.items():
            await page.fill(f"[data-pr-in='{k}']", str(v))
        await page.screenshot(path=str(out / "sheet-form-light.png"))
        await page.click(".pr-save")
        await until(page, f"() => (document.querySelector('.pr-msg') || {{}}).textContent && document.querySelector('[data-pr-row=\"{FAKE}\"]')", "saved and listed", timeout=15000)
        saved = json.loads((state / "prices.json").read_text())["models"]
        check(failures, saved.get(FAKE) == {k: float(v) for k, v in FAKE_ROW.items()}, f"the sheet wrote the user's table: {saved}")
        await until(page, "() => document.getElementById('chip-price').hidden", "the chip goes once priced", timeout=15000)
        await page.click("#pr-close")
        await until(page, "() => document.getElementById('pr').hidden", "sheet closed")
        await until(page, f"() => !({BILLS_JS})().find((x) => x.id === '{other}').shown", "the old bill goes", timeout=15000, why=BILLS_JS)
        _append(tr[1], _rec("msg_x2", model=FAKE))
        b = await wait_bill(other, "the newly priced bill")
        check(failures, b["text"] == FAKE_TEXT and not b["unknown"], f"the price added on the page applies to the next response: {b}")
        check(failures, "単価: あなたの表" in b["title"], f"the bill says the price is the user's own: {b['title']!r}")

        # 7. change, remove, reset on the page (a shipped model), each in the user's table
        await page.click("#prices-open")
        await until(page, "() => !document.getElementById('pr').hidden", "sheet open")
        await page.click("[data-pr-edit='claude-opus-5-5']")
        await page.fill("[data-pr-in='output']", "40")
        await page.click(".pr-save")
        await until(page, "() => (document.querySelector('[data-pr-row=\"claude-opus-5-5\"] .pr-origin') || {}).textContent === '変更'", "changed", timeout=15000)
        check(failures, json.loads((state / "prices.json").read_text())["models"]["claude-opus-5-5"]["output"] == 40.0, "変更 wrote the new price")
        await page.click("[data-pr-op='remove'][data-pr-model='claude-opus-5-5']")
        await until(page, "() => (document.querySelector('[data-pr-row=\"claude-opus-5-5\"] .pr-origin') || {}).textContent === '削除'", "removed", timeout=15000)
        check(failures, json.loads((state / "prices.json").read_text())["models"]["claude-opus-5-5"] is None, "削除 took the shipped model out (null)")
        await page.click("[data-pr-op='reset'][data-pr-model='claude-opus-5-5']")
        await until(page, "() => (document.querySelector('[data-pr-row=\"claude-opus-5-5\"] .pr-origin') || {}).textContent === '既定'", "reset", timeout=15000)
        check(failures, "claude-opus-5-5" not in json.loads((state / "prices.json").read_text())["models"], "既定に戻す took the model's line out")
        await page.click(f"[data-pr-op='remove'][data-pr-model='{FAKE}']")
        await until(page, f"() => !document.querySelector('[data-pr-row=\"{FAKE}\"]')", "the user's model removed", timeout=15000)

        # 8. the command changes it too, and a broken row is left out alone, said on the sheet
        r = cli("set", FAKE, "--input", "1", "--cache-write-5m", "1.25", "--cache-write-1h", "2", "--cache-read", "0.1", "--output", "50")
        check(failures, r.returncode == 0, f"jui viz prices set: {r.returncode} {r.stderr}")
        await until(page, f"() => !!document.querySelector('[data-pr-row=\"{FAKE}\"]')", "the command's price on the sheet", timeout=15000)
        data = json.loads((state / "prices.json").read_text())
        data["models"]["claude-broken-1"] = {"input": "cheap"}
        (state / "prices.json").write_text(json.dumps(data))
        err = await until(page, "() => { const e = document.querySelector('.pr-errors'); return e && e.textContent; }", "the broken row said", timeout=15000)
        check(failures, "claude-broken-1" in err, f"the sheet names the row left out: {err!r}")
        check(failures, await page.evaluate(f"() => !!document.querySelector('[data-pr-row=\"{FAKE}\"]')"), "the other rows still apply")
        await page.screenshot(path=str(out / "sheet-light.png"))
        await page.emulate_media(color_scheme="dark")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(out / "sheet-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.click("#pr-close")

        # 9. a write without the token is refused (the page's own route checks)
        own = f"127.0.0.1:{port}"
        for headers, want in (({"Host": own, "Origin": f"http://{own}"}, 401),
                              ({"Host": own, "Origin": "http://evil.example", "X-Jui-Viz-Token": await page.evaluate("() => document.querySelector('meta[name=jui-viz-token]').content")}, 403)):
            req = urllib.request.Request(f"{url}/api/prices", method="POST", data=json.dumps({"op": "remove", "model": "claude-opus-5-5"}).encode(),
                                         headers={"Content-Type": "application/json", **headers})
            try:
                st = urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as e:
                st = e.code
            check(failures, st == want, f"a write {headers.get('Origin')} {'with' if 'X-Jui-Viz-Token' in headers else 'without'} the token: {st}, want {want}")
        check(failures, "claude-opus-5-5" not in json.loads((state / "prices.json").read_text())["models"], "a refused write changed nothing")

        await shots("after")

        # 10. 設定 › お札 off: no bill (the response still arrives)
        await page.click("#bill-switch")
        check(failures, await page.get_attribute("#bill-switch", "aria-checked") == "false", "the switch turns off")
        _append(tr[0], _rec("msg_off"))
        await until(page, "() => window.__dbg.billSeen().some((k) => k.endsWith('|msg_off'))", "the response arrived", timeout=15000)
        await page.wait_for_timeout(500)
        check(failures, not (await bills())[main]["shown"], "off: no bill")
        await page.click("#bill-switch")

        # 10b. tags crowded (the camera far out, so the tags stack): the bill keeps its room in the stack — the tag put
        # above its robot's (the farther robot's) sits above the bill, not on it
        canvas = await page.locator("canvas").first.bounding_box()
        await page.mouse.move(canvas["x"] + canvas["width"] / 2, canvas["y"] + canvas["height"] / 2)
        pair, wheels = None, 0
        while pair is None and wheels < 30:
            await page.mouse.wheel(0, 300)
            wheels += 1
            await page.wait_for_timeout(250)
            await settled(page, f"zoomed out ({wheels})")
            pair = await page.evaluate(STACK_JS)
        res["stack"] = {"pair": pair, "wheels": wheels}
        check(failures, pair is not None, "zoomed out, two tags stack (the arm needs them)")
        if pair:
            file = {main: tr[0], other: tr[1], sub: sub_tr}[pair["low"]]
            _append(file, _rec("msg_stack", model="claude-haiku-5-5" if pair["low"] == sub else "claude-opus-5-5"))
            await wait_bill(pair["low"], "a bill under a stacked tag")
            await settled(page, "the stack makes room")
            all_b = await bills()
            lo = all_b[pair["low"]]
            res["stack"]["bills"] = all_b
            for x in all_b.values():
                if x["tag"] and lo["bill"]:
                    check(failures, not _overlaps(lo["bill"], x["tag"]), f"crowded: the bill covers {x['id']}'s tag: {lo['bill']} / {x['tag']}")
            await page.screenshot(path=str(out / "crowded-light.png"))
            await until(page, f"() => !({BILLS_JS})().find((x) => x.id === '{pair['low']}').shown", "the crowded bill goes", timeout=15000, why=BILLS_JS)
        for _ in range(wheels):
            await page.mouse.wheel(0, -300)
            await page.wait_for_timeout(100)

        # 11. reduced motion: shown and gone, no rise
        rm = await new_page(browser, watch, name + "-rm", **DESKTOP)
        await rm.emulate_media(reduced_motion="reduce")
        await rm.goto(url + "/")
        await ready(rm)
        await until(rm, "() => window.__dbg.robots.length >= 3", "robots (reduced motion)", timeout=30000)
        await rm.wait_for_timeout(2500)
        _append(tr[0], _rec("msg_rm"))
        b = await until(rm, f"(id) => {{ const b = ({BILLS_JS})().find((x) => x.id === id); return b && b.shown ? b : null; }}", "reduced motion bill", arg=main, timeout=20000)
        check(failures, not b["rise"] and b["anim"] in ("none", ""), f"reduced motion: no rise: {b}")
        await rm.close()

        check(failures, not watch.console and not watch.foreign and not watch.csp, f"no console error, nothing outside the server: {watch.console[:3]} {watch.foreign[:3]}")
        await page.close()
    except Exception as e:
        failures.append(f"cost-bill: {type(e).__name__}: {str(e).splitlines()[0]}")
    finally:
        await browser.close()
        srv.terminate()  # our own child (started above)
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
        (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"  {name}: {time.monotonic() - t0:.0f}s", flush=True)
