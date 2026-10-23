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
# The words of the demo's talks, by language (ticket 2026-10-21-jui-viz-language-switch-ja-en): the page shows the
# set of its language (I18N.language, web/js/05-i18n.js), English when it has none.
WORDS = {
 "ja": {
  "a3": "サブエージェント a3（jsonui-define）",
  "long": ("会員登録の画面を仕上げました。確認してほしい点は次のとおりです。\n\n"
           "1. **メールアドレス**の入力欄は、確認用の欄と一致しないとき `送信` を押せないようにしました。\n"
           "2. パスワードは 8 文字以上、英字と数字を含むこと。弱いときは赤い文で理由を出します。\n"
           "3. 利用規約のリンクは別画面で開きます（戻ると入力は残ります）。\n\n"
           "テスト: `jsonui-test run tests/screens/signup` で 14 件すべて通りました。\n"
           "iOS と Android のスクリーンショットは docs/screens/signup/ に置いてあります。\n"
           "<script>alert(1)</script> のような文字列も、そのまま文字として出ること（escape の見本）。\n"
           "残り: 住所の自動入力は次のリリースで。"),
  1: ("会員登録の画面、進み具合はどう？", "会員登録の進み具合"),
  2: ("いま入力の検証を書いています。30 分ほどで出せます。", None),
  3: (None, "会員登録の画面を仕上げた"),
  4: ("ありがとう。住所の自動入力は次のリリースで大丈夫です。", None),
  5: ("signup.spec.json の項目を 3 つ足して、検証を通してください。", None),
  6: ("足しました。doc_validate_spec は緑です。", None),
  7: ("レビューをお願いします（クラウドの相手へ）", None),
  8: ("春のセールの範囲を決めました。注文履歴の画面が入ります。", "春のセールの範囲"),
  9: ("決済の画面のテスト、止まっていますか？", None),
  10: ("シミュレーターを待っています。空いたら流します。", None),
  11: ("スクリーンショットを差し替えました。もう一度見てください。", "差し替え"),
 },
 "en": {
  "a3": "subagent a3 (jsonui-define)",
  "long": ("The sign-up screen is done. Here is what to check:\n\n"
           "1. The **email** field cannot be sent (`Send` stays off) until it matches the confirmation field.\n"
           "2. Passwords need 8 characters or more, with letters and digits. A weak one says why in red.\n"
           "3. The terms link opens on its own screen (coming back keeps what was typed).\n\n"
           "Tests: all 14 pass with `jsonui-test run tests/screens/signup`.\n"
           "The iOS and Android screenshots are in docs/screens/signup/.\n"
           "A string like <script>alert(1)</script> shows as plain text (the escaping example).\n"
           "Left: address autofill goes in the next release."),
  1: ("How is the sign-up screen going?", "Sign-up progress"),
  2: ("Writing the input checks now. About 30 minutes to go.", None),
  3: (None, "The sign-up screen is done"),
  4: ("Thanks. Address autofill in the next release is fine.", None),
  5: ("Add three fields to signup.spec.json and get it through validation, please.", None),
  6: ("Added. doc_validate_spec is green.", None),
  7: ("Please review this (to the cloud peer)", None),
  8: ("The spring sale's scope is set. The order history screen is in.", "Spring sale scope"),
  9: ("Is the payment screen's test stuck?", None),
  10: ("Waiting for the simulator. It runs as soon as one is free.", None),
  11: ("The screenshots are replaced. Please take another look.", "Replaced"),
 },
}


def build(lang: str) -> dict:
    W = WORDS[lang]
    NAMES = {"a0": "shop-app-main", "b4": "shop-app-signup",
             "4f": "shop-app-release-coordinator-for-the-spring-catalog-and-checkout-update",
             "d8": "shop-app-payment", "a3": W["a3"]}
    EXT = external_key("cloud-reviewer")
    NAMES[EXT] = "cloud-reviewer"
    KIND = {"a0": "session", "b4": "session", "4f": "session", "d8": "session", "a3": "subagent", EXT: "external"}
    SID = {"a0": "a07c0000-0000-4000-8000-0000000000a0", "b4": "b47e0000-0000-4000-8000-0000000000b4",
           "4f": "4f2b0000-0000-4000-8000-00000000004f", "d8": "d8a50000-0000-4000-8000-0000000000d8"}
    SID["a3"] = SID["a0"]
    LONG = W["long"]
    msgs = []   # (convPeerPair, sender, receiver, t_min, text, state, extra)
    def mk(i, s, r, t, text, state="read", summary=None, via="session", delivered=True, read=True, msg_id=True):
        mid = f"m-demo-{i:04d}-0000-4000-8000-000000000000" if msg_id else f"u-toolu_demo_{i:04d}"
        at = BASE + t * M
        return {"id": mid, "msgId": mid[2:] if msg_id else None, "s": s, "r": r, "at": at,
                "deliveredAt": at + 800 if delivered else None, "readAt": at + 1_600 if read and state == "read" else None,
                "state": state, "text": text, "summary": summary, "via": via}
    msgs += [
     mk(1, "a0", "b4", -42, W[1][0], summary=W[1][1]),
     mk(2, "b4", "a0", -40, W[2][0], summary=W[2][1]),
     mk(3, "b4", "a0", -12, LONG, summary=W[3][1]),
     mk(4, "a0", "b4", -10, W[4][0], summary=W[4][1], state="delivered", read=False),
     mk(5, "a0", "a3", -30, W[5][0], summary=W[5][1], via="subagent", msg_id=False),
     mk(6, "a3", "a0", -25, W[6][0], summary=W[6][1], via="parent", msg_id=False),
     mk(7, "a0", EXT, -20, W[7][0], summary=W[7][1], state="undelivered", via="external", delivered=False, read=False, msg_id=False),
     mk(8, "4f", "a0", -8, W[8][0], summary=W[8][1]),
     mk(9, "a0", "d8", -50, W[9][0], summary=W[9][1]),
     mk(10, "d8", "a0", -48, W[10][0], summary=W[10][1]),
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
    new = mk(11, "b4", "a0", 0, W[11][0], summary=W[11][1])
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
    return data


data_by_lang = {lang: build(lang) for lang in ("en", "ja")}
body = json.dumps(data_by_lang, ensure_ascii=False, indent=1)
out = ("// The talk view's demo data: frames as jui_cli/viz/talk_contract.json says (data only, no code), one set per\n"
       "// language. Read by the demo source in place of the server's talk.* frames. Checked by\n"
       "// tests/test_viz_talk_demo_data.py.\n"
       "// eslint-disable-next-line no-unused-vars\n"
       f"const TALK_DEMO_BY_LANGUAGE = {body};\n"
       "// eslint-disable-next-line no-unused-vars\n"
       "const TALK_DEMO = TALK_DEMO_BY_LANGUAGE[typeof I18N === 'object' ? I18N.language : 'en'] || TALK_DEMO_BY_LANGUAGE.en;\n")
pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT).write_text(out, encoding="utf-8")
