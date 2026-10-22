"""The promo video's script for the viz chapters (plan 2026-10-21-promo-video-plan §2, §8.1; ticket
2026-10-21-viz-promo-replay-and-capture-tool).

Only the data is a sample: every event here becomes a real hook body sent through the real forward.py, a record in
a transcript or a test-progress file the real server reads, or a real press on the page. Times are seconds of the
video (the chapter's bounds come from jsonui-promo/src/timeline.json; CHAPTER_IDS below must match its ids). Each
chapter is captured on a server of its own: its `prelude` is fired before frame 0 (not captured) and builds the state
the chapter opens on; its `events` fire on the frame whose time passes `at`.

Every word a viewer reads that is not the viz's own UI comes from WORDS[lang] (session names, prompts, commands, the
question, the talk, the test cases). The rooms are fictional: demo-shop (a copy of the jsonui-demo-shop workdir) and
two small rooms. Nothing here names a real project.

An event is (at, kind, args). Kinds the driver (capture.py) knows:

  hooks      start / prompt / tool / tool_end / perm / ask / ask_answered / denied / idle / stop / sub_start /
             sub_stop: hook bodies through forward.py (ask: also `forward.py --ask`, which really waits for the page)
  records    talk (a SendMessage in one transcript and its read in the other) / tests_start / tests_case / tests_end
             (the runner's progress records and the Bash call that ran them)
  page       click / hover / wheel / dbg / select: the driver's mouse (a cursor drawn over the page, see capture.py)
             and window.__dbg calls; `ready` (a JS predicate) holds a press until the page offers it, `expect` (a JS
             predicate) is waited on after the event fired, before the next frame is taken
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FPS = 30
CHAPTER_IDS = ("hook", "2", "3", "4", "5", "6")   # 1a / 1b: term.py
TERM_CHAPTER_IDS = ("1a", "1b")
ALL = TERM_CHAPTER_IDS + CHAPTER_IDS
#: window segments inside a viz chapter, captured by term.py into a folder of their own: id -> (chapter, start, end,
#: the demo-shop file shown). The promo shows the segment over its seconds and the chapter's frames after it.
SEGMENTS = {"5-json": ("5", 74.0, 77.0, "docs/infra/load/weekend-campaign.json")}
#: a terminal chapter shown split: its terminal on the left half, the viz page beside it on the right half, captured
#: by capture.py into a folder of its own: id -> the chapter it sits beside. The promo frames both halves at the same
#: size (its SPLIT layout), so the terminal (term.py) and the board are both taken at SPLIT_VIEWPORT.
BOARDS = {"1b-board": "1b"}
SPLIT_VIEWPORT = {"width": 1125, "height": 1012}   # 900 x 810 in the video, 1.25 x
#: standalone clips, not chapters of the promo: id -> (start, end) of the clip's own clock (its Remotion composition
#: reads the same bounds). "mig": the server room's migration plan played (2.3.20, ticket
#: 2026-10-22-viz-infra-migration-plan), shown to the requester on its own before it joins the promo.
STANDALONE = {"mig": (0.0, 40.0)}
#: what run.py captures: the promo's chapters and the segments (a chapter brings its segments and board with it)
CAPTURE_IDS = ALL + tuple(SEGMENTS) + tuple(BOARDS) + tuple(STANDALONE)
#: the bounds the events below were written for; tests hold them to the promo's timeline.json
BOUNDS = {"hook": (0, 4), "1a": (4, 16), "1b": (16, 32), "2": (32, 44), "3": (44, 54), "4": (54, 74), "5": (74, 88), "6": (88, 96)}

ROOMS = ("demo-shop", "demo-admin", "demo-docs", "demo-api", "demo-mobile")

# (key, the first two hex digits of its session id — the label the view shows —, room). 30 robots: ten in demo-shop,
# five in each small room (a room of more than ten drops its decor, crowded_props.py; five rooms keep one floor).
SESSIONS = (
    ("s01", "a0", "demo-shop"), ("s02", "b4", "demo-shop"), ("s03", "c2", "demo-shop"), ("s04", "d8", "demo-shop"),
    ("s05", "e1", "demo-shop"), ("s06", "f3", "demo-shop"), ("s07", "1a", "demo-shop"), ("s08", "2b", "demo-shop"),
    ("s09", "3c", "demo-shop"),
    ("s10", "4d", "demo-admin"), ("s11", "5e", "demo-admin"), ("s12", "6f", "demo-admin"),
    ("s13", "7a", "demo-docs"), ("s14", "8b", "demo-docs"), ("s15", "9c", "demo-docs"),
    ("s16", "ab", "demo-shop"), ("s17", "bc", "demo-admin"), ("s18", "cd", "demo-admin"),
    ("s19", "de", "demo-docs"), ("s20", "ef", "demo-docs"),
    ("s21", "0f", "demo-api"), ("s22", "1e", "demo-api"), ("s23", "2d", "demo-api"), ("s24", "3b", "demo-api"), ("s25", "4a", "demo-api"),
    ("s26", "5c", "demo-mobile"), ("s27", "6d", "demo-mobile"), ("s28", "7e", "demo-mobile"), ("s29", "8f", "demo-mobile"),
    ("s30", "9a", "demo-mobile"),
)
SUBAGENT = ("a3f19c2e8b7d4a601", "jsonui-test")
#: the event kinds the driver knows (capture.Driver.fire)
KINDS = frozenset({"start", "prompt", "tool", "tool_end", "perm", "ask_pending", "ask", "ask_answered", "denied", "idle", "stop",
                   "sub_start", "sub_stop", "talk", "tests_start", "tests_case", "tests_end", "settle", "door", "dbg", "click",
                   "hover", "select", "wheel", "spec_reset", "spec_write", "dolly"})
#: the migration player's buttons (59-sr-migration.js) and the plan demo-shop carries
MIG_PLAN = "shop-to-managed"
MIG_BTN = "#sr-mplayer [data-sr-mp='{}']"
#: what a page event's target may name (capture.Driver.point)
TARGETS = frozenset({"css", "text", "room_tag", "bubble", "session_row", "talk_row", "robot", "cost_day", "door"})


def session_id(key: str) -> str:
    label = dict((k, lab) for k, lab, _ in SESSIONS)[key]
    n = int(key[1:])
    return f"{label}{n:06x}-7d00-4000-8000-{n:012x}"


def session_pid(key: str) -> int:
    return 61000 + int(key[1:])


WORDS = {
    "ja": {
        "names": {"s01": "仕様の担当", "s02": "テストの担当", "s03": "iOS の実装", "s04": "Android の実装", "s05": "Web の実装",
                  "s06": "API の担当", "s07": "文言の担当", "s08": "リリースの担当", "s09": "レビューの担当",
                  "s10": "管理画面の実装", "s11": "管理画面のテスト", "s12": "権限の担当",
                  "s13": "ドキュメントの担当", "s14": "翻訳の担当", "s15": "サイトの公開",
                  "s16": "アクセシビリティ", "s17": "管理画面の文言", "s18": "CSV の書き出し", "s19": "API の解説",
                  "s20": "スクリーンショット", "s21": "注文 API", "s22": "在庫 API", "s23": "認証の担当",
                  "s24": "API のテスト", "s25": "負荷の見積もり", "s26": "通知の実装", "s27": "オフライン対応",
                  "s28": "端末のテスト", "s29": "ストアの申請", "s30": "クラッシュの調査"},
        "prompts": {"spec": "カート画面の spec に数量の上限を足して", "tests": "カートのテストを通して", "ios": "カート画面を iOS で仕上げて",
                    "android": "商品詳細を Android で仕上げて", "web": "注文完了画面を Web で仕上げて", "api": "在庫なしの 409 を API に足して",
                    "strings": "英語の文言をそろえて", "release": "リリースの準備をして", "review": "今日の変更を見て",
                    "admin": "注文の一覧に絞り込みを足して", "admin_tests": "管理画面のテストを足して", "roles": "権限の表を見直して",
                    "docs": "はじめにのページを書いて", "translate": "ドキュメントを英語にして", "site": "サイトを公開して"},
        "perm_cmd": "jui build --ios-only",
        "perm_desc": "iOS のコードを生成",
        "question": {"question": "数量の上限はいくつにしますか？", "header": "上限",
                     "options": [{"label": "10 個", "description": "よくある上限"}, {"label": "99 個", "description": "まとめ買い向け"},
                                 {"label": "上限なし", "description": "在庫まで"}]},
        "answer": "10 個",
        "ask_short": {"question": "注文完了の画面に、おすすめを出しますか？", "header": "おすすめ",
                      "options": [{"label": "出す", "description": "3 件まで"}, {"label": "出さない", "description": "今は出さない"}]},
        "denied_cmd": "rm -rf build ios/build",
        "denied_reason": "自動モードは、まとめて消す操作を止めます",
        "talk": {"t1": "カートの spec を更新しました。数量の上限を足しています", "t2": "了解です。テストを生成し直します",
                 "t3": "ブランチのテストが 12 件とも通りました"},
        "cases": ["カートが空のとき", "1 個入れたとき", "上限まで入れたとき", "在庫なしのとき", "通信に失敗したとき", "合計の表示"],
        "files": {"spec": "docs/screens/json/cart.spec.json", "readme": "README.md"},
        "board_prompt": "カート画面の spec を書いて",
        "sub_done": "カートのテストを書き終えた",
        "room_readme": {"demo-admin": "demo-admin — 見本の管理画面（架空）\n", "demo-docs": "demo-docs — 見本のドキュメント（架空）\n",
                        "demo-api": "demo-api — 見本の API（架空）\n", "demo-mobile": "demo-mobile — 見本のスマホアプリ（架空）\n"},
        "prompts2": {"a11y": "読み上げのラベルを見直して", "admin_strings": "管理画面の文言をそろえて", "csv": "注文を CSV で書き出せるようにして",
                     "api_docs": "API の解説を書いて", "shots": "ストア用のスクリーンショットを撮って", "orders_api": "注文 API にページ送りを足して",
                     "stock_api": "在庫 API の 409 を直して", "auth": "ログインの期限を見直して", "api_tests": "API の契約テストを足して",
                     "load": "週末のキャンペーンの負荷を見積もって", "push": "発送の通知を足して", "offline": "オフラインでもカートを見られるようにして",
                     "device_tests": "小さい画面で崩れないか見て", "store": "ストアの申請を準備して", "crash": "起動時のクラッシュを調べて"},
    },
    "en": {
        "names": {"s01": "spec-owner", "s02": "test-runner", "s03": "ios-builder", "s04": "android-builder", "s05": "web-builder",
                  "s06": "api-owner", "s07": "strings-owner", "s08": "release-prep", "s09": "reviewer",
                  "s10": "admin-builder", "s11": "admin-tests", "s12": "roles-owner",
                  "s13": "docs-writer", "s14": "translator", "s15": "site-publisher",
                  "s16": "a11y-checker", "s17": "admin-strings", "s18": "csv-export", "s19": "api-docs",
                  "s20": "screenshots", "s21": "orders-api", "s22": "stock-api", "s23": "auth-owner",
                  "s24": "api-tests", "s25": "load-estimator", "s26": "push-notifications", "s27": "offline-mode",
                  "s28": "device-tests", "s29": "store-submission", "s30": "crash-triage"},
        "prompts": {"spec": "Add a quantity limit to the cart spec", "tests": "Get the cart tests passing", "ios": "Finish the cart screen on iOS",
                    "android": "Finish product detail on Android", "web": "Finish order complete on the web", "api": "Add the out-of-stock 409 to the API",
                    "strings": "Align the English strings", "release": "Prepare the release", "review": "Review today's changes",
                    "admin": "Add filters to the order list", "admin_tests": "Add tests for the admin screens", "roles": "Revisit the roles table",
                    "docs": "Write the getting-started page", "translate": "Translate the docs into English", "site": "Publish the site"},
        "perm_cmd": "jui build --ios-only",
        "perm_desc": "Generate the iOS code",
        "question": {"question": "What should the quantity limit be?", "header": "Limit",
                     "options": [{"label": "10 items", "description": "The usual limit"}, {"label": "99 items", "description": "For bulk buyers"},
                                 {"label": "No limit", "description": "Up to the stock"}]},
        "answer": "10 items",
        "ask_short": {"question": "Show recommendations on the order complete screen?", "header": "Picks",
                      "options": [{"label": "Show", "description": "Up to three"}, {"label": "Hide", "description": "Not for now"}]},
        "denied_cmd": "rm -rf build ios/build",
        "denied_reason": "Auto mode stops bulk deletes",
        "talk": {"t1": "I updated the cart spec: it has a quantity limit now", "t2": "Got it. Regenerating the tests",
                 "t3": "All 12 branch tests pass"},
        "cases": ["empty cart", "one item", "up to the limit", "out of stock", "network failure", "total shown"],
        "files": {"spec": "docs/screens/json/cart.spec.json", "readme": "README.md"},
        "board_prompt": "Write the cart screen's spec",
        "sub_done": "Finished writing the cart tests",
        "room_readme": {"demo-admin": "demo-admin: a sample admin console (fictional)\n", "demo-docs": "demo-docs: a sample docs site (fictional)\n",
                        "demo-api": "demo-api: a sample API (fictional)\n", "demo-mobile": "demo-mobile: a sample mobile app (fictional)\n"},
        "prompts2": {"a11y": "Review the screen reader labels", "admin_strings": "Align the admin strings", "csv": "Let orders export as CSV",
                     "api_docs": "Write the API guide", "shots": "Take the store screenshots", "orders_api": "Add paging to the orders API",
                     "stock_api": "Fix the stock API's 409", "auth": "Revisit the login expiry", "api_tests": "Add API contract tests",
                     "load": "Estimate the weekend campaign's load", "push": "Add the shipping notification", "offline": "Keep the cart readable offline",
                     "device_tests": "Check small screens for breakage", "store": "Prepare the store submission", "crash": "Look into the crash at launch"},
    },
}

# the prompt each session is working on (WORDS[lang]["prompts"] keys)
WORK = {"s01": "spec", "s02": "tests", "s03": "ios", "s04": "android", "s05": "web", "s06": "api", "s07": "strings",
        "s08": "release", "s09": "review", "s10": "admin", "s11": "admin_tests", "s12": "roles", "s13": "docs",
        "s14": "translate", "s15": "site", "s16": "a11y", "s17": "admin_strings", "s18": "csv", "s19": "api_docs",
        "s20": "shots", "s21": "orders_api", "s22": "stock_api", "s23": "auth", "s24": "api_tests", "s25": "load", "s26": "push",
        "s27": "offline", "s28": "device_tests", "s29": "store", "s30": "crash"}


@dataclass
class Event:
    at: float | None          # seconds of the video; None in a prelude (fired in order before frame 0)
    kind: str
    args: dict = field(default_factory=dict)


@dataclass
class Chapter:
    id: str
    start: float
    end: float
    prelude: list
    events: list
    needs: tuple = ()          # features the chapter needs from the tree (capture.FEATURES)
    viewport: dict | None = None   # the page's size when not the whole video's (a board: SPLIT_VIEWPORT)


def E(at, kind, **args) -> Event:
    return Event(at, kind, args)


def P(kind, **args) -> Event:
    return Event(None, kind, args)


# ---- the pieces the chapters share ----

def prompt(w: dict, key: str) -> str:
    return w["prompts"].get(WORK[key]) or w["prompts2"][WORK[key]]



def floor(w: dict) -> list:
    """Every session in, each on its prompt; most of them in a tool (typing at their desks)."""
    out = []
    for key, _, _ in SESSIONS:
        out.append(P("start", key=key))
        out.append(P("prompt", key=key, text=prompt(w, key)))
    tools = {"s01": ("Edit", {"file_path": "@demo-shop/" + w["files"]["spec"]}),
             "s03": ("Read", {"file_path": "@demo-shop/ios/ios/View/Cart/CartGeneratedView.swift"}),
             "s04": ("Edit", {"file_path": "@demo-shop/android/app/src/main/kotlin/com/example/demoshop/viewmodels/ProductDetailViewModel.kt"}),
             "s06": ("Read", {"file_path": "@demo-shop/docs/api/demo_shop.json"}),
             "s07": ("Edit", {"file_path": "@demo-shop/docs/screens/layouts/Resources/strings.json"}),
             "s09": ("Bash", {"command": "git log --oneline -5", "description": "log"}),
             "s10": ("Write", {"file_path": "@demo-admin/src/orders.ts", "content": "x"}),
             "s11": ("Read", {"file_path": "@demo-admin/README.md"}),
             "s13": ("Write", {"file_path": "@demo-docs/getting-started.md", "content": "x"}),
             "s14": ("Read", {"file_path": "@demo-docs/README.md"}),
             "s15": ("Bash", {"command": "git status", "description": "status"}),
             "s18": ("Write", {"file_path": "@demo-admin/src/export.ts", "content": "x"}),
             "s19": ("Edit", {"file_path": "@demo-docs/README.md"}),
             "s21": ("Edit", {"file_path": "@demo-api/README.md"}),
             "s22": ("Read", {"file_path": "@demo-api/README.md"}),
             "s24": ("Bash", {"command": "git diff --stat", "description": "diff"}),
             "s26": ("Write", {"file_path": "@demo-mobile/src/push.ts", "content": "x"}),
             "s27": ("Read", {"file_path": "@demo-mobile/README.md"}),
             "s30": ("Bash", {"command": "git log --oneline -3", "description": "log"})}
    for key, (tool, inp) in sorted(tools.items()):
        out.append(P("tool", key=key, tool=tool, input=inp))
    return out + [P("settle")]


def up_close(room: str) -> list:
    """The camera in on one room (a press on its tag, as a person would)."""
    return [P("click", target={"room_tag": room}, expect="solo:" + room), P("settle")]


def waits(w: dict) -> list:
    """The three waits on the floor: a permission, a question (not answered here), an idle prompt."""
    return [P("perm", key="s03", command=w["perm_cmd"], description=w["perm_desc"]),
            P("ask_pending", key="s05", question=w["ask_short"], use_id="toolu_e1ask0"),
            P("idle", key="s07")]


# ---- the chapters ----

#: the flow player's 1 歩戻る can be pressed and the second choice is still taken (one press undoes one step and
#: pauses; the press that undoes the branch itself takes its choice off the list, and the player waits, paused,
#: before the branch)
BACK_READY = ("() => { const b = document.querySelector(\"#sr-player [data-sr-fp='back']\"); "
              "return !!b && !b.disabled && window.__dbg.srFlow().chosen.length >= 2; }")
#: back before the branch, paused: ▶ plays on to it and its choices come again
PLAY_READY = ("() => { const f = window.__dbg.srFlow(); return f.state === 'pause' && f.chosen.length === 1 "
              "&& !!document.querySelector('#sr-choices[hidden]'); }")


def chapters(lang: str) -> dict:
    w = WORDS[lang]
    q = w["question"]
    out = {}

    # hook (0–4): the whole floor, busy; the camera comes in slowly (the wheel, as a person would)
    out["hook"] = Chapter("hook", 0, 4, floor(w) + waits(w), [
        E(0.4, "tool_end", key="s09"),
        E(0.5, "wheel", target={"css": "#scene-canvas"}, dy=-480, dur=3.2),
        E(1.2, "tool", key="s02", tool="Bash", input={"command": "cd web && npx vitest run tests/unit/generated", "description": "tests"}),
        E(2.0, "sub_start", key="s02"),
        E(2.8, "tool_end", key="s01"),
    ])

    # 2 (32–44): the robots show what each session is doing (requester 10-22: 「ロボットの動きで状況が理解できるのがメイン機能」
    # 「テスト中かどうかがわかったり」). In on the shop's room: robots typing, reading, thinking (a prompt and no tool yet);
    # one starts its tests, its card shows the run case by case (one fails), then one stops and waits for input.
    out["2"] = Chapter("2", 32, 44, floor(w), [
        E(32.8, "click", target={"room_tag": "demo-shop"}, expect="solo:demo-shop"),
        E(35.2, "tests_start", key="s02", run="r1", command="cd web && npx vitest run tests/unit/generated"),
        E(35.6, "click", target={"robot": "s02"}, expect="card:s02"),
        E(36.2, "tests_case", run="r1", case=0, status="passed"),
        E(36.7, "tests_case", run="r1", case=1, status="passed"),
        E(37.2, "tests_case", run="r1", case=2, status="passed"),
        E(37.7, "tests_case", run="r1", case=3, status="failed"),
        E(38.3, "tests_case", run="r1", case=4, status="passed"),
        E(38.8, "tests_case", run="r1", case=5, status="passed"),
        E(39.4, "tests_end", key="s02", run="r1"),
        E(40.6, "idle", key="s07"),
        E(41.4, "click", target={"session_row": "s07"}, expect="card:s07"),
    ], needs=("rooms",))

    # 3 (44–54): a permission answered in the browser, briefly (requester: 「許可の紹介はサラッとでいい」), then the
    # sessions' talk as a chat (2.3.14): the spec owner's card, its talk with the test runner, two messages arriving.
    talk_prelude = [P("talk", frm="s01", to="s02", text=w["talk"]["t1"], ago=90)]
    out["3"] = Chapter("3", 44, 54, floor(w) + talk_prelude + up_close("demo-shop"), [
        E(44.2, "perm", key="s03", command=w["perm_cmd"], description=w["perm_desc"]),
        E(44.8, "click", target={"bubble": "s03"}, expect="picked:s03"),
        E(46.0, "click", target={"css": ".pa-allow[data-do='allow']"}),
        E(47.2, "click", target={"robot": "s01"}, expect="card:s01"),
        E(47.9, "click", target={"css": "#rb [data-rb-talk]"}, expect="talk"),
        E(48.6, "click", target={"talk_row": "s02"}),
        E(49.4, "talk", frm="s02", to="s01", text=w["talk"]["t2"]),
        E(51.4, "talk", frm="s02", to="s01", text=w["talk"]["t3"]),
    ], needs=("rooms",))

    # 4 (54–74): the server room as 2.3.19 draws it, small to large (requester 10-22: start close, where the light's
    # way is easy to follow, then pull back to the large system). Close on the shop's group (its focus, then a little
    # nearer: its nodes stand as models), flow "order" at 0.5x among them, its first branch taken; at 1x its second;
    # then the camera pulls back steadily (eased, 6.8 x) until the whole system is in view, and flow "payment" runs
    # across the regions at 2x to the end.
    sr_prelude = up_close("demo-shop") + [P("door"), P("dbg", call="srSelectGroup", group="shop-core"),
                                          P("click", target={"css": "#sr-board [data-sr-act='focus']"}),
                                          P("dbg", call="srZoom", factor=0.82), P("settle")]
    # order: 1.8 s to its first branch, 3.6 s to its second, 5.4 s to its end (at 1x); payment: 4.5 s to its first
    choice = "(c) => !!document.querySelector(`#sr-choices:not([hidden]) [data-sr-choice=\"${c}\"]`)"
    out["4"] = Chapter("4", 54, 74, floor(w) + sr_prelude + [P("dbg", call="srFlowSpeed", speed=0.5)], [
        E(54.1, "dbg", call="srSelect", node="browser", expect="flowlist:order"),
        E(54.4, "click", target={"css": "#sr-board [data-sr-flow='order']"}, expect="flow:order"),
        E(58.0, "click", target={"css": "#sr-choices [data-sr-choice='hit']"}, ready=choice, arg="hit"),
        E(58.3, "dbg", call="srFlowSpeed", speed=1),
        E(61.9, "click", target={"css": "#sr-choices [data-sr-choice='in']"}, ready=choice, arg="in"),
        E(62.5, "dolly", factor=6.8, dur=7.5),
        E(70.2, "dbg", call="srSelect", node="api", expect="flowlist:payment"),
        E(70.4, "dbg", call="srFlowSpeed", speed=2),
        E(70.7, "click", target={"css": "#sr-board [data-sr-flow='payment']"}, expect="flow:payment"),
    ], needs=("rooms", "server_room", "flows"))

    # mig (standalone, 0–38): the long plan played through (requester 10-22: many migrations, smoothly). Its 12 steps
    # touch the AWS groups on the left (search, payments, analytics, admin) and the two Azure groups on the right, so
    # the camera frames the AWS account (its focus: every changed node in view; too many nodes for the models) and
    # comes in a little while it plays. ▶ once at 0.5x: each step 2.1 s, back to back, the month's cost counting and a
    # ±$ tag over each changed node; the Azure floors go at the end. Step 3 moves two nodes (two tags, and the bar
    # names both): the player is paused 1.7 s early in it, while the tags are at full strength (a pause holds the
    # step, the count and the tags), then played on. Then the cost view
    # (its total says the old month and the steps taken) and its old / new / difference tables.
    out["mig"] = Chapter("mig", 0, 40, floor(w) + up_close("demo-shop") + [
        P("door"),
        P("click", target={"css": f"#sr-board [data-sr-mig='{MIG_PLAN}']"}, expect="migopen"),
        P("dbg", call="srSelectGroup", group="aws"),
        P("click", target={"css": "#sr-board [data-sr-act='focus']"}),
        P("dbg", call="srSelect", node=None),
        P("dbg", call="srMigSpeed", speed=0.5), P("settle"),
        P("dbg", call="noop", expect="migcost"),
    ], [
        E(3.0, "click", target={"css": MIG_BTN.format("toggle")}),
        E(3.2, "dolly", factor=0.85, dur=26.0),
        E(7.8, "click", target={"css": MIG_BTN.format("toggle")}),
        E(9.5, "click", target={"css": MIG_BTN.format("toggle")}),
        E(31.4, "click", target={"css": "#sr-mode-cost"}, expect="migtable"),
    ], needs=("rooms", "server_room", "migration"))

    # 5 (74–88): the cost simulator. 74–77 is the load definition in the editor (term.py, captures/<lang>/5-json:
    # SEGMENTS); this capture covers the whole chapter, and its cost page starts after that window: the month, then
    # one day played (24 hours at 200 ms an hour)
    out["5"] = Chapter("5", 74, 88, floor(w) + up_close("demo-shop") + [P("door"), P("dbg", call="srCostPlayMs", ms=200)], [
        E(77.3, "click", target={"css": "#sr-mode-cost"}, expect="cost_month"),
        E(79.4, "select", target={"css": "#sr-scn"}, value="weekend-campaign", expect="cost_month"),
        E(81.6, "click", target={"cost_day": "busiest"}, expect="cost_day"),
        E(82.6, "click", target={"css": "#sr-cost [data-src-act='play']"}),
    ], needs=("rooms", "server_room", "cost"))

    # 1b-board (16–32, beside 1b's terminal): the cart screen's spec on the whiteboard, filling in as the spec owner
    # writes it. The file starts with its metadata only (spec_reset); each spec_write is a real Write of the real file
    # with one more section of the spec as demo-shop has it, which the server reads (the hook's file, and its watcher)
    # and the open sheet shows. The sections come in the order the sheet shows them while the terminal's gates run.
    spec = w["files"]["spec"]
    board_prelude = [P("start", key="s01"), P("prompt", key="s01", text=w["board_prompt"]),
                     P("spec_reset", room="demo-shop", rel=spec, keep=["type", "version", "metadata"]), P("settle"),
                     P("dbg", call="press", css="#btn-side"),   # the side panel closed: the sheet takes the page
                     P("dbg", call="openSpec", room="demo-shop", rel=spec, expect="board"), P("settle")]
    out["1b-board"] = Chapter("1b-board", 16, 32, board_prelude, [
        E(16.8, "spec_write", key="s01", room="demo-shop", rel=spec, add="structure"),
        E(19.0, "spec_write", key="s01", room="demo-shop", rel=spec, add="stateManagement"),
        E(21.4, "spec_write", key="s01", room="demo-shop", rel=spec, add="dataFlow"),
        E(23.8, "spec_write", key="s01", room="demo-shop", rel=spec, add="userActions"),
        E(25.8, "spec_write", key="s01", room="demo-shop", rel=spec, add="transitions"),
        E(27.8, "spec_write", key="s01", room="demo-shop", rel=spec, add="branchContracts"),
        E(30.4, "stop", key="s01"),
    ], needs=("rooms",), viewport=SPLIT_VIEWPORT)

    # 6 (88–96): back to the whole floor
    out["6"] = Chapter("6", 88, 96, floor(w) + waits(w) + up_close("demo-shop"), [
        E(88.6, "click", target={"css": "#room-back"}, expect="floor"),
        E(90.0, "wheel", target={"css": "#scene-canvas"}, dy=300, dur=4.0),
        E(91.0, "tool_end", key="s13"),
    ], needs=("rooms",))
    return out


# ---- the promo's timeline ----

def promo_timeline(promo: Path) -> dict:
    """{id: (start, end)} of jsonui-promo/src/timeline.json."""
    data = json.loads((Path(promo) / "src" / "timeline.json").read_text(encoding="utf-8"))
    return {c["id"]: (float(c["start"]), float(c["end"])) for c in data["chapters"]}


def check_bounds(promo: dict) -> list:
    """The chapters whose bounds in the promo's timeline.json differ from the ones the script was written for."""
    return [f"{c}: promo {promo.get(c)} != script {BOUNDS[c]}" for c in ALL if promo.get(c) != tuple(float(x) for x in BOUNDS[c])]


# ---- a flow's time (the server room's player, 59-sr-flows.js SR_FLOW) ----

MOVE_MS = 900    # a light along one edge, at 1x
NODE_MS = 450    # a step that only says something at a node, at 1x


def flow_segments(flow: dict, picks: list) -> list:
    """The ms of play (at 1x) between the flow's start, each branch it stops at and its end, taking `picks` (choice
    ids) at the branches in order: [to branch 1, branch 1 to branch 2, …, last branch to the end]. Lanes side by side
    take the longest lane's time; a lane's own branch takes its default (srFlowLane)."""
    segs, picks = [0], list(picks)

    def lane_ms(steps):
        ms = 0
        for s in steps:
            if s.get("branch"):
                b = s["branch"]
                c = next((x for x in b["choices"] if x["id"] == b.get("default")), b["choices"][0])
                ms += lane_ms(c.get("steps") or [])
            elif s.get("parallel"):
                ms += max(lane_ms(lane) for lane in s["parallel"])
            else:
                ms += MOVE_MS if s.get("from") and s.get("to") else NODE_MS
        return ms

    def walk(steps):
        for s in steps:
            if s.get("branch"):
                pick = picks.pop(0)
                c = next(x for x in s["branch"]["choices"] if x["id"] == pick)
                if c.get("goto") or c.get("join"):
                    raise ValueError(f"flow_segments: choice {pick} jumps (goto / join): not modelled")
                segs.append(0)
                walk(c.get("steps") or [])
            elif s.get("parallel"):
                segs[-1] += max(lane_ms(lane) for lane in s["parallel"])
            else:
                segs[-1] += MOVE_MS if s.get("from") and s.get("to") else NODE_MS
    walk(flow["steps"])
    return segs


def flow_budget(chapter: Chapter, flow: dict, min_gap: float = 0.6) -> dict:
    """When a flow pressed in `chapter` reaches its end, played as the script plays it: its press, the speed then in
    effect (the prelude's srFlowSpeed, then any speed chosen on the bar before the press), each choice pressed at its
    time or when its branch is reached, whichever is later (a press waits for its choices; never sooner than
    `min_gap` after the last), and the segments between at that speed. Returns {press, speed, choices: [(id, at)],
    end, seconds}."""
    speed = 1.0
    for ev in chapter.prelude:
        if ev.kind == "dbg" and ev.args.get("call") == "srFlowSpeed":
            speed = float(ev.args["speed"])
    flow_css = f"[data-sr-flow='{flow['id']}']"
    press = next(ev.at for ev in chapter.events if ev.kind == "click" and flow_css in ev.args["target"].get("css", ""))
    for ev in chapter.events:
        if ev.kind == "select" and "data-sr-fp='speed'" in ev.args["target"].get("css", "") and ev.at < press:
            speed = float(ev.args["value"])
    later = [ev for ev in chapter.events if ev.at > press]
    picks = []
    for ev in later:
        if ev.kind == "click" and "[data-sr-choice=" in ev.args["target"].get("css", ""):
            picks.append((ev.args["arg"], ev.at))
        elif ev.kind == "click" and "[data-sr-flow=" in ev.args["target"].get("css", ""):
            break   # another flow pressed: this one is over
    segs = flow_segments(flow, [p for p, _ in picks])
    t, last, chosen = press + segs[0] / 1000 / speed, press, []
    for (pick, at), seg in zip(picks, segs[1:]):
        fired = max(at, t, last + min_gap)
        chosen.append((pick, round(fired, 3)))
        last = fired
        t = fired + seg / 1000 / speed
    return {"press": press, "speed": speed, "choices": chosen, "end": round(t, 3), "seconds": round(t - press, 3)}


def frame_count(start: float, end: float) -> int:
    return int(round((end - start) * FPS))


def frame_time(start: float, i: int) -> float:
    """The video time of frame i of a chapter (frame 0 = the chapter's start)."""
    return start + i / FPS
