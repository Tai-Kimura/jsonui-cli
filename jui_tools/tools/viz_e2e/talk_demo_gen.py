"""Writes jui_cli/viz/web/js/31-talk-demo-data.js, the talk view's demo data (frames per talk_contract.json).

    python3 tools/viz_e2e/talk_demo_gen.py            # writes the file
    python3 tools/viz_e2e/talk_demo_gen.py OUT        # writes OUT instead (tests/test_viz_talk_demo_data.py compares)

Robot ids are the demo's own (30-source-demo.js): a0 (with its subagent a3), b4, d8, 4f; one peer outside the machine.
"""
import json
import pathlib
import sys

JT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JT))
DEFAULT_OUT = JT / "jui_cli" / "viz" / "web" / "js" / "31-talk-demo-data.js"
from jui_cli.viz.talk import conv_id, external_key
from jui_cli.viz import talk_contract as C
BASE = 1_792_300_000_000           # the demo's "now" at t=0 (ms); the page shifts every time by (its clock - base)
M = 60_000
NAMES = {"a0": "shop-app-main", "b4": "shop-app-signup",
         "4f": "jsonui-agents-for-claude-4f-library-orchestrator-for-the-2.3.7-train",
         "d8": "shop-app-payment", "a3": "サブエージェント a3（jsonui-define）"}
EXT = external_key("cloud-reviewer")
NAMES[EXT] = "cloud-reviewer"
KIND = {"a0": "session", "b4": "session", "4f": "session", "d8": "session", "a3": "subagent", EXT: "external"}
SID = {"a0": "a07c0000-0000-4000-8000-0000000000a0", "b4": "b47e0000-0000-4000-8000-0000000000b4",
       "4f": "4f2b0000-0000-4000-8000-00000000004f", "d8": "d8a50000-0000-4000-8000-0000000000d8"}
SID["a3"] = SID["a0"]
LONG = ("会員登録の画面を仕上げました。確認してほしい点は次のとおりです。\n\n"
        "1. **メールアドレス**の入力欄は、確認用の欄と一致しないとき `送信` を押せないようにしました。\n"
        "2. パスワードは 8 文字以上、英字と数字を含むこと。弱いときは赤い文で理由を出します。\n"
        "3. 利用規約のリンクは別画面で開きます（戻ると入力は残ります）。\n\n"
        "テスト: `jsonui-test run tests/screens/signup` で 14 件すべて通りました。\n"
        "iOS と Android のスクリーンショットは docs/screens/signup/ に置いてあります。\n"
        "<script>alert(1)</script> のような文字列も、そのまま文字として出ること（escape の見本）。\n"
        "残り: 住所の自動入力は次の列車で。")
msgs = []   # (convPeerPair, sender, receiver, t_min, text, state, extra)
def mk(i, s, r, t, text, state="read", summary=None, via="session", delivered=True, read=True, msg_id=True):
    mid = f"m-demo-{i:04d}-0000-4000-8000-000000000000" if msg_id else f"u-toolu_demo_{i:04d}"
    at = BASE + t * M
    return {"id": mid, "msgId": mid[2:] if msg_id else None, "s": s, "r": r, "at": at,
            "deliveredAt": at + 800 if delivered else None, "readAt": at + 1_600 if read and state == "read" else None,
            "state": state, "text": text, "summary": summary, "via": via}
msgs += [
 mk(1, "a0", "b4", -42, "会員登録の画面、進み具合はどう？", summary="会員登録の進み具合"),
 mk(2, "b4", "a0", -40, "いま入力の検証を書いています。30 分ほどで出せます。"),
 mk(3, "b4", "a0", -12, LONG, summary="会員登録の画面を仕上げた"),
 mk(4, "a0", "b4", -10, "ありがとう。住所の自動入力は次の列車で大丈夫です。", state="delivered", read=False),
 mk(5, "a0", "a3", -30, "signup.spec.json の項目を 3 つ足して、検証を通してください。", via="subagent", msg_id=False),
 mk(6, "a3", "a0", -25, "足しました。doc_validate_spec は緑です。", via="parent", msg_id=False),
 mk(7, "a0", EXT, -20, "レビューをお願いします（クラウドの相手へ）", state="undelivered", via="external", delivered=False, read=False, msg_id=False),
 mk(8, "4f", "a0", -8, "2.3.7 の列車の範囲を決めました。トークの画面が入ります。", summary="2.3.7 の範囲"),
 mk(9, "a0", "d8", -50, "決済の画面のテスト、止まっていますか？"),
 mk(10, "d8", "a0", -48, "シミュレーターを待っています。空いたら流します。"),
]
SEEN = {("a0", "b4"): BASE - 13 * M, ("a0", "4f"): BASE - 9 * M}   # a0 saw b4 up to before #3 → 1 unread; 4f: 1 unread
def message(m, owner):
    peer = m["r"] if m["s"] == owner else m["s"]
    return {"id": m["id"], "msgId": m["msgId"], "convId": conv_id(owner, peer), "dir": "out" if m["s"] == owner else "in",
            "fromName": NAMES[m["s"]], "toName": NAMES[m["r"]], "at": m["at"], "deliveredAt": m["deliveredAt"], "readAt": m["readAt"],
            "state": m["state"], "text": m["text"], "cut": False, "summary": m["summary"],
            "seen": "sender" if m["via"] == "external" else "both", "via": m["via"], "merged": False}
def peer(key, gone=None):
    ext = KIND[key] == "external"
    return {"key": key, "agentId": None if ext else key, "sessionId": None if ext else SID[key], "name": NAMES[key], "kind": KIND[key],
            "alive": gone is None and not ext, "goneAt": gone, "removeAt": gone + 3_600_000 if gone is not None else None}
GONE = {"d8": BASE - 5 * M}
for k in (EXT,):
    GONE[k] = max(m["at"] for m in msgs if k in (m["s"], m["r"]))
def conv(owner, other, upto=None):
    mine = [m for m in msgs if {m["s"], m["r"]} == {owner, other}]
    last = max(mine, key=lambda m: m["at"])
    upto = SEEN.get((owner, other), BASE)
    unread = sum(1 for m in mine if m["r"] == owner and m["at"] > upto)
    return {"id": conv_id(owner, other), "owner": owner, "peer": peer(other, GONE.get(other)), "lastAt": last["at"],
            "preview": next(l.strip() for l in last["text"].splitlines() if l.strip())[:120],
            "lastDir": "out" if last["s"] == owner else "in", "unread": unread, "count": len(mine)}
owners = {"a0": ["b4", "a3", EXT, "4f", "d8"], "b4": ["a0"], "a3": ["a0"], "4f": ["a0"], "d8": ["a0"]}
lists, details = {}, {}
for owner, peers in owners.items():
    items = sorted((conv(owner, p) for p in peers), key=lambda c: -c["lastAt"])
    lists[owner] = {"type": "talk.list", "agentId": owner, "items": items, "more": False}
    for p in peers:
        mine = sorted((message(m, owner) for m in msgs if {m["s"], m["r"]} == {owner, p}), key=lambda x: (x["at"], x["id"]))
        details[f"{owner} {conv_id(owner, p)}"] = {"type": "talk.messages", "reqId": 0, "agentId": owner, "convId": conv_id(owner, p), "items": mine, "more": False}
badges = {"type": "talk.badges", "counts": {o: n for o in owners if (n := sum(c["unread"] for c in lists[o]["items"]))}}
# the script: what arrives while the demo runs (t in seconds of the demo's clock)
new = mk(11, "b4", "a0", 0, "スクリーンショットを差し替えました。もう一度見てください。", summary="差し替え")
new["at"] = BASE + 20_000; new["deliveredAt"] = new["at"] + 700; new["readAt"] = None; new["state"] = "delivered"
msgs.append(new)
c_new = conv("a0", "b4")
read4 = dict(message(msgs[3], "a0")); read4.update(state="read", readAt=BASE + 30_000)
msgs_d8 = conv_id("a0", "d8")
script = [
 {"t": 20, "frame": {"type": "talk.update", "agentId": "a0", "ops": [{"op": "message", "convId": c_new["id"], "message": message(new, "a0")}, {"op": "conv", "conv": c_new}]}},
 {"t": 20, "frame": {"type": "talk.badges", "counts": {**badges["counts"], "a0": badges["counts"].get("a0", 0) + 1}}},
 {"t": 30, "frame": {"type": "talk.update", "agentId": "a0", "ops": [{"op": "message", "convId": read4["convId"], "message": read4}]}},
 {"t": 45, "frame": {"type": "talk.update", "agentId": "a0", "ops": [{"op": "remove", "convId": msgs_d8, "reason": "peer-ended"}]}},
]
data = {"about": "The talk view's demo data (frames as talk_contract.json says), for the demo page only. Times are ms around base; "
                  "the page moves them by its own clock (now - base). script: frames that arrive t seconds into the demo.",
        "contractVersion": C.load()["version"], "base": BASE, "badges": badges, "lists": lists, "messages": details, "script": script}
for f in [badges, *lists.values(), *details.values(), *(s["frame"] for s in script)]:
    assert C.validate(f) == [], C.validate(f)
body = json.dumps(data, ensure_ascii=False, indent=1)
out = ("// The talk view's demo data: frames as jui_cli/viz/talk_contract.json says (data only, no code). Read by the demo\n"
       "// source in place of the server's talk.* frames. Checked by tests/test_viz_talk_demo_data.py.\n"
       "// eslint-disable-next-line no-unused-vars\n"
       f"const TALK_DEMO = {body};\n")
pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT).write_text(out, encoding="utf-8")
