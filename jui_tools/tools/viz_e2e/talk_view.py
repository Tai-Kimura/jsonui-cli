"""The talk view's server side, end to end (ticket 2026-10-20-jui-viz-talk-view). Runs with `--only talk`.

The real `jui viz serve` in a throwaway HOME on a free port (PATH cut to /usr/bin:/bin and --no-agents-poll: no
`claude` runs), with ~/.claude/sessions entries and transcripts this suite writes: SendMessage pairs matched by
msg_id, one written twice on both sides, a parent's send to its subagent and the subagent's to main; later an
undelivered send to a name outside the machine and a new message. config.json sets talkGraceSec short.

The screen (the chat icon, the list, the detail) is not here: it is driven from the page's side through WebSockets
the suite opens in the page (the page's own origin and token, as the screen will), so it does not wait for the UI.
Every wait is on page state (waits.until, every animation frame); the grace's end is waited on as the remove op.

Checked: on connect talk.badges, then talk.list for a robot (the duplicate counted once, the subagent's talk in it);
talk.messages; a new message gives an update and a badge; talk.seen clears the unread and a second socket gets the
badge; an undelivered send shows its peer as external (alive false, no robot to switch to); a session whose entry
goes is shown ended, kept, then removed by a remove op; every talk frame conforms to talk_contract.json; no body
and no path in the snapshot, the slices, the events or the demo export; no console error; nothing outside the server.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import DESKTOP, ISOLATE, LAUNCH_ARGS, Watch, dump, new_page, ready
from waits import until

JT = pathlib.Path(__file__).resolve().parents[2]
if str(JT) not in sys.path:
    sys.path.insert(0, str(JT))
from jui_cli.viz import talk_contract as C  # noqa: E402

A = "e2e7a1c0-0000-4000-8000-0000000000a1"
B = "e2e7a1c0-0000-4000-8000-0000000000b2"
D = "e2e7a1c0-0000-4000-8000-0000000000d4"
CHILD = "a0e2e7a1c0000c1d"
NAMES = {A: "talk-e2e-a", B: "talk-e2e-b", D: "talk-e2e-d"}
PIDS = {A: 64001, B: 64002, D: 64004}
GRACE_SEC = 30
CWD = "/work/talk-e2e"
BODY = "e2e-body"        # every body starts with it: none may show outside the talk frames

PROBE = """() => {
  if (window.__talkProbe) return true;
  const token = (document.querySelector('meta[name="jui-viz-token"]') || {}).content;
  const probes = {};
  window.__talkProbe = {
    open(name) {
      const p = probes[name] = { frames: [], other: [], ready: false };
      const ws = p.ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onmessage = (e) => {
        const f = JSON.parse(e.data);
        if (f.type === 'hello') { ws.send(JSON.stringify({ type: 'auth', token })); return; }
        if (f.type === 'snapshot') p.ready = true;
        (typeof f.type === 'string' && (f.type.startsWith('talk.') || f.type === 'ack') ? p.frames : p.other).push(f);
      };
      return true;
    },
    send(name, msg) { probes[name].ws.send(JSON.stringify(msg)); return true; },
    frames(name) { return probes[name] ? probes[name].frames : []; },
    other(name) { return probes[name] ? probes[name].other : []; },
    ready(name) { return !!(probes[name] && probes[name].ready); },
    state() { return Object.fromEntries(Object.entries(probes).map(([k, p]) => [k, p.frames.map((f) => f.type + (f.ops ? ':' + f.ops.map((o) => o.op).join('+') : ''))])); },
  };
  return true;
}"""
WHY = "() => window.__talkProbe && window.__talkProbe.state()"


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


class Files:
    def __init__(self, home: pathlib.Path):
        self.folder = home / ".claude" / "projects" / "-work-talk-e2e"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = {sid: self.folder / f"{sid}.jsonl" for sid in (A, B, D)}
        self.child = self.folder / A / "subagents" / f"agent-{CHILD}.jsonl"
        self.child.parent.mkdir(parents=True, exist_ok=True)
        for p in (*self.path.values(), self.child):
            p.touch()
        self.n = 0

    def uid(self):
        self.n += 1
        return f"e2e00000-0000-4000-8000-{self.n:012d}"

    @staticmethod
    def write(path, *recs):
        with path.open("a", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def send(self, use_id, to, text, at, sub=None):
        rec = {"type": "assistant", "timestamp": iso(at), "uuid": self.uid(),
               "message": {"id": f"msg_{use_id}", "content": [{"type": "tool_use", "id": use_id, "name": "SendMessage",
                                                               "input": {"to": to, "message": text, "summary": text[:20]}}]}}
        if sub:
            rec["agentId"] = sub
        return rec

    def result(self, use_id, at, msg_id=None, text=None):
        tur = {"success": True, "message": text or "ok", **({"msg_id": msg_id} if msg_id else {})}
        return {"type": "user", "timestamp": iso(at), "uuid": self.uid(), "toolUseResult": tur,
                "message": {"content": [{"type": "tool_result", "tool_use_id": use_id, "content": text or json.dumps(tur)}]}}

    def read(self, sender, msg_id, text, at, uuid=None, queued=False):
        origin = {"kind": "peer", "from": f"uds:/tmp/e2e-socks/{PIDS[sender]}.sock", "verifiedPeerPid": PIDS[sender],
                  "msg_id": msg_id, "name": NAMES[sender], "fromMode": "prompting", "body": text}
        if queued:
            return {"type": "attachment", "timestamp": iso(at), "uuid": uuid or self.uid(),
                    "attachment": {"type": "queued_command", "prompt": "x", "source_uuid": self.uid(), "isMeta": True, "origin": origin}}
        return {"type": "user", "isMeta": True, "timestamp": iso(at), "uuid": uuid or self.uid(), "origin": origin,
                "message": {"content": f"<cross-session-message>\n{text}\n</cross-session-message>"}}


def session_entry(home, sid):
    p = home / ".claude" / "sessions" / f"{PIDS[sid]}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def run_talk(pw, out, failures):
    from run import free_port
    out = pathlib.Path(out) / "talk"
    out.mkdir(parents=True, exist_ok=True)
    home = out / "home"
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps({"talkGraceSec": GRACE_SEC}))
    now = int(time.time() * 1000)
    for sid in (A, B, D):
        session_entry(home, sid).write_text(json.dumps({"pid": PIDS[sid], "sessionId": sid, "cwd": CWD, "kind": "interactive",
                                                        "entrypoint": "cli", "status": "idle", "name": NAMES[sid],
                                                        "messagingSocketPath": f"/tmp/e2e-socks/{PIDS[sid]}.sock", "startedAt": now - 600_000}))
    f = Files(home)
    t = now - 120_000
    # matched by msg_id; the second one's tool_use and its read both written twice (the read: the same uuid)
    f.write(f.path[A], f.send("toolu_e1", NAMES[B], f"{BODY}-ab-1", t), f.result("toolu_e1", t + 100, "e2e-m1"))
    f.write(f.path[B], f.read(A, "e2e-m1", f"{BODY}-ab-1", t + 900))
    twice = f.send("toolu_e2", NAMES[B], f"{BODY}-ab-2", t + 2_000)
    f.write(f.path[A], twice, f.result("toolu_e2", t + 2_100, "e2e-m2"), twice)
    read2 = f.read(A, "e2e-m2", f"{BODY}-ab-2", t + 3_000, uuid="e2e-read-twice", queued=True)
    f.write(f.path[B], read2, read2)
    f.write(f.path[A], f.send("toolu_e3", NAMES[D], f"{BODY}-ad-1", t + 4_000), f.result("toolu_e3", t + 4_100, "e2e-m3"))
    f.write(f.path[D], f.read(A, "e2e-m3", f"{BODY}-ad-1", t + 4_800))
    # the subagent: the parent's send (to its id) and the subagent's to main
    f.write(f.path[A], f.send("toolu_e4", CHILD, f"{BODY}-child-1", t + 5_000), f.result("toolu_e4", t + 5_050, text="Message queued for delivery"))
    f.write(f.child, {"type": "attachment", "timestamp": iso(t + 5_500), "uuid": f.uid(), "agentId": CHILD,
                      "attachment": {"type": "queued_command", "prompt": f"{BODY}-child-1", "source_uuid": f.uid(), "isMeta": True,
                                     "origin": {"kind": "coordinator"}}},
            f.send("toolu_e5", "main", f"{BODY}-child-2", t + 6_000, sub=CHILD), f.result("toolu_e5", t + 6_050))
    f.write(f.path[A], {"type": "user", "isMeta": True, "timestamp": iso(t + 6_400), "uuid": f.uid(),
                        "origin": {"kind": "peer", "from": CHILD, "senderTaskId": CHILD, "name": "worker", "body": f"{BODY}-child-2"},
                        "message": {"content": "<agent-message>x</agent-message>"}})

    port = free_port()
    url = f"http://127.0.0.1:{port}"
    env = dict({k: v for k, v in os.environ.items() if k not in ISOLATE + ("PYTHONPATH", "CLAUDE_CONFIG_DIR")},
               HOME=str(home), JUI_VIZ_E2E="1", PATH="/usr/bin:/bin")
    log = open(out / "serve.log", "w")
    srv = subprocess.Popen([sys.executable, str(JT / "bin" / "jui"), "viz", "serve", "--port", str(port), "--no-agents-poll"],
                           stdout=log, stderr=subprocess.STDOUT, env=env)
    res: dict = {}
    talk_frames: list = []

    def check(cond, text):
        if not cond:
            failures.append(f"talk: {text}")

    async def frames(page, name):
        got = await page.evaluate("(n) => window.__talkProbe.frames(n)", name)
        for fr in got:
            if fr["type"].startswith("talk.") and fr not in talk_frames:
                talk_frames.append(fr)
        return got

    async def wait_frame(page, name, js_pred, label, timeout=30000):
        """The first talk frame on socket `name` for which `js_pred(frame)` holds (checked every frame)."""
        await until(page, f"(n) => window.__talkProbe.frames(n).some({js_pred})", label, arg=name, timeout=timeout, why=WHY)
        await frames(page, name)
        return await page.evaluate(f"(n) => window.__talkProbe.frames(n).find({js_pred})", name)

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
                if srv.poll() is not None:
                    break
                time.sleep(0.1)
        page = await new_page(browser, watch, "talk", **DESKTOP)
        await page.goto(url + "/")
        await ready(page)
        await page.evaluate(PROBE)

        # ---- on connect: talk.badges; then talk.list for A
        await page.evaluate("() => window.__talkProbe.open('s1')")
        badges0 = await wait_frame(page, "s1", "(f) => f.type === 'talk.badges'", "talk.badges on connect")
        res["badgesOnConnect"] = badges0
        check(badges0["counts"] == {}, f"the past is not badged: {badges0}")
        # the index reads the transcripts a moment after the server starts: open A, and wait until its three talks are
        # known, from the list or from the updates that follow it; then ask for the list again
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.open", "reqId": 100, "agentId": A})
        await until(page, """() => {
          const keys = new Set();
          for (const f of window.__talkProbe.frames('s1')) {
            if (f.type === 'talk.list') f.items.forEach((c) => keys.add(c.peer.key));
            if (f.type === 'talk.update') f.ops.forEach((o) => o.op === 'conv' && keys.add(o.conv.peer.key));
          }
          return keys.size >= 3;
        }""", "A's three talks known", why=WHY)
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.open", "reqId": 101, "agentId": A})
        listing = await wait_frame(page, "s1", "(f) => f.reqId === 101", "A's talk.list")
        res["list"] = listing
        by_peer = {c["peer"]["key"]: c for c in listing.get("items", [])}
        check(set(by_peer) == {B, D, CHILD}, f"A's talks: {sorted(by_peer)}")
        check(by_peer.get(B, {}).get("count") == 2, f"the duplicate counted once: {by_peer.get(B)}")
        check(by_peer.get(CHILD, {}).get("peer", {}).get("kind") == "subagent" and by_peer.get(CHILD, {}).get("count") == 2,
              f"the subagent's talk: {by_peer.get(CHILD)}")
        check(by_peer.get(B, {}).get("peer", {}).get("agentId") == B and by_peer.get(B, {}).get("peer", {}).get("name") == NAMES[B],
              f"the peer can be switched to, by its name: {by_peer.get(B, {}).get('peer')}")
        cid_b, cid_d = by_peer[B]["id"], by_peer[D]["id"]
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.get", "reqId": 200, "agentId": A, "convId": cid_b})
        detail = await wait_frame(page, "s1", "(f) => f.reqId === 200", "talk.messages")
        res["detail"] = [(m["id"], m["state"], m["seen"]) for m in detail.get("items", [])]
        check(res["detail"] == [("m-e2e-m1", "read", "both"), ("m-e2e-m2", "read", "both")], f"the messages, once each, matched: {res['detail']}")

        # ---- a new message (B -> A): an update and a badge
        n1 = int(time.time() * 1000)
        f.write(f.path[B], f.send("toolu_e6", NAMES[A], f"{BODY}-ba-new", n1), f.result("toolu_e6", n1 + 50, "e2e-m6"))
        upd = await wait_frame(page, "s1", "(f) => f.type === 'talk.update' && f.ops.some((o) => o.op === 'message' && o.message.id === 'm-e2e-m6')",
                               "the new message's update")
        op = next(o for o in upd["ops"] if o["op"] == "message")
        check(op["message"]["dir"] == "in" and op["message"]["state"] == "delivered", f"the new message as A sees it: {op['message']}")
        badge = await wait_frame(page, "s1", f"(f) => f.type === 'talk.badges' && f.counts['{A}'] === 1", "A's badge 1")
        res["badgeAfterNew"] = badge["counts"]

        # ---- talk.seen clears it, and a second socket (not watching A) gets the badge
        await page.evaluate("() => window.__talkProbe.open('s2')")
        await until(page, "() => window.__talkProbe.frames('s2').some((f) => f.type === 'talk.badges')", "s2's badges on connect", why=WHY)
        first2 = (await frames(page, "s2"))[0]
        check(first2["type"] == "talk.badges" and first2["counts"].get(A) == 1, f"s2 connects to A's badge: {first2}")
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.seen", "reqId": 300, "agentId": A, "convId": cid_b, "upTo": op["message"]["at"]})
        ack = await wait_frame(page, "s1", "(f) => f.reqId === 300", "talk.seen's ack")
        check(ack == {"type": "ack", "reqId": 300, "ok": True}, f"talk.seen: {ack}")
        cleared = await wait_frame(page, "s2", f"(f) => f.type === 'talk.badges' && !('{A}' in f.counts)", "s2 sees A's badge cleared")
        res["badgeAfterSeen"] = cleared["counts"]
        conv_seen = await wait_frame(page, "s1", f"(f) => f.type === 'talk.update' && f.ops.some((o) => o.op === 'conv' && o.conv.id === '{cid_b}' && o.conv.unread === 0)",
                                     "A's talk with B at 0 unread")
        check(not [fr for fr in await frames(page, "s2") if fr["type"] == "talk.update"], "s2 opened nothing: no talk.update for it")

        # ---- an undelivered send: the peer outside the machine
        n2 = int(time.time() * 1000)
        f.write(f.path[A], f.send("toolu_e7", "nobody-e2e", f"{BODY}-ext", n2),
                f.result("toolu_e7", n2 + 50, text='No agent named "nobody-e2e" is reachable.'))
        ext = await wait_frame(page, "s1", "(f) => f.type === 'talk.update' && f.ops.some((o) => o.op === 'conv' && o.conv.peer.kind === 'external' && !o.conv.peer.alive)",
                               "the external peer's talk")
        econv = next(o["conv"] for o in ext["ops"] if o["op"] == "conv" and o["conv"]["peer"]["kind"] == "external")
        res["external"] = econv["peer"]
        check(econv["peer"]["agentId"] is None and econv["peer"]["sessionId"] is None and econv["peer"]["name"] == "nobody-e2e",
              f"external: no robot to switch to: {econv['peer']}")
        emsg = [o["message"] for fr in await frames(page, "s1") if fr["type"] == "talk.update" for o in fr["ops"]
                if o["op"] == "message" and o["message"]["id"] == "u-toolu_e7"]
        check(emsg and emsg[-1]["state"] == "undelivered", f"the undelivered send: {emsg[-1:] }")

        # ---- D ends: shown ended, kept within the grace, removed after it (waited on as the remove op)
        session_entry(home, D).unlink()
        gone = await wait_frame(page, "s1", f"(f) => f.type === 'talk.update' && f.ops.some((o) => o.op === 'conv' && o.conv.id === '{cid_d}' && !o.conv.peer.alive)",
                                "D shown ended")
        gconv = next(o["conv"] for o in gone["ops"] if o["op"] == "conv" and o["conv"]["id"] == cid_d)
        res["gone"] = gconv["peer"]
        check(gconv["peer"]["removeAt"] - gconv["peer"]["goneAt"] == GRACE_SEC * 1000, f"removeAt = goneAt + the grace: {gconv['peer']}")
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.open", "reqId": 400, "agentId": A})
        kept = await wait_frame(page, "s1", "(f) => f.reqId === 400", "the list within the grace")
        check(any(c["id"] == cid_d and not c["peer"]["alive"] for c in kept.get("items", [])), "kept within the grace")
        check(not any(o["op"] == "remove" and o["convId"] == cid_d for fr in await frames(page, "s1") if fr["type"] == "talk.update" for o in fr["ops"]),
              "not removed when it was shown ended")
        removed = await wait_frame(page, "s1", f"(f) => f.type === 'talk.update' && f.ops.some((o) => o.op === 'remove' && o.convId === '{cid_d}')",
                                   "D's talk removed after the grace", timeout=(GRACE_SEC + 60) * 1000)
        res["removed"] = next(o for o in removed["ops"] if o["op"] == "remove" and o["convId"] == cid_d)
        check(res["removed"]["reason"] == "peer-ended", f"the reason: {res['removed']}")
        await page.evaluate("(m) => window.__talkProbe.send('s1', m)", {"type": "talk.open", "reqId": 500, "agentId": A})
        after = await wait_frame(page, "s1", "(f) => f.reqId === 500", "the list after the grace")
        check(not any(c["id"] == cid_d for c in after.get("items", [])), "D's talk is gone from the list")
        check(any(c["id"] == cid_b for c in after.get("items", [])), "B's talk (alive) is still there")

        # ---- every talk frame to the contract; nothing of a body or a path anywhere else
        await frames(page, "s1")
        await frames(page, "s2")
        bad = [(fr["type"], p) for fr in talk_frames for p in C.validate(fr)]
        check(not bad, f"frames against the contract: {bad[:3]}")
        res["talkFrames"] = len(talk_frames)
        other = json.dumps(await page.evaluate("() => [window.__talkProbe.other('s1'), window.__talkProbe.other('s2')]"), ensure_ascii=False)
        import http.client
        token = json.loads((state / "server.json").read_text())["token"]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/snapshot", headers={"X-Jui-Viz-Token": token})
        snap = conn.getresponse().read().decode()
        conn.close()
        for label, text in (("the snapshot", snap), ("the slices and events", other)):
            check(BODY not in text, f"{label} carries a body")
            check(str(home) not in text and ".jsonl" not in text and "talk.db" not in text, f"{label} carries a path")
        export = out / "export"
        if export.exists():
            import shutil
            shutil.rmtree(export)
        subprocess.run([sys.executable, str(JT / "bin" / "jui"), "viz", "export-demo", "--out", str(export)], env=env,
                       capture_output=True, check=True)
        leaked = [str(p.relative_to(export)) for p in export.rglob("*") if p.is_file() and BODY.encode() in p.read_bytes()]
        check(not leaked, f"the demo export carries a body: {leaked}")
        db = state / "talk.db"
        check(db.exists() and (db.stat().st_mode & 0o777) == 0o600, "talk.db under the state home, 0600")
        await page.screenshot(path=str(out / "page.png"))
        await page.close()
    except Exception as e:  # noqa: BLE001 - one FAIL line with what was missing
        failures.append(f"talk: {type(e).__name__}: {str(e)[:1500]}")
    finally:
        await browser.close()
        if srv.poll() is None:
            srv.terminate()        # our own child
            try:
                srv.wait(timeout=15)
            except subprocess.TimeoutExpired:
                srv.kill()
        log.close()
        (out / "results.json").write_text(dump(res) + "\n")
        print(f"  talk: {time.monotonic() - t0:.0f}s", flush=True)
    for line in watch.console:
        failures.append(f"talk: console: {line}")
    for u in watch.foreign:
        failures.append(f"talk: request outside the server: {u}")
    for c in watch.csp:
        failures.append(f"talk: CSP violation: {c}")
