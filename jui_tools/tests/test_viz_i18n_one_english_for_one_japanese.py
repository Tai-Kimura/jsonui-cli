"""Words the Japanese table says one way, the English table says one way (ticket
2026-10-21-jui-viz-en-strings-two-names-for-one-button: the same button was "Expand the bottom" in the history and
"Enlarge the bottom" on the card; one list was "Actions auto mode stopped" and "Calls denied by auto mode").

Every key of the table is grouped by its Japanese words; a group whose English words differ (letter case aside — a
word that starts a label is capitalised, one inside a sentence is not) is red unless SPLIT says why its Japanese
words are two things in English. SPLIT is closed: a group it names that no longer splits is red too, so it never
hides a new one.
"""
from __future__ import annotations

import json

from tests.test_viz_bundle import web_text

#: Japanese words that are more than one thing in English, and why. Closed (see the module's doc).
SPLIT = {
    "許可待ち": "the status (Waiting for permission) and the short word on a robot's note and the floor's sign (Waiting)",
    "作業中": "a robot's state (Working) and the kanban column (Doing, beside To do and Done)",
    "まだ無い": "no test run yet (None yet) and a file not written yet (Not there yet)",
    "セッション": "one (Session) and the list's heading (Sessions)",
    "サブエージェント": "one (Subagent) and the card's list of them (Subagents)",
    "入力": "a price's kind (Input tokens) and a robot typing (Typing)",
    "変更": "a price changed (Changed) and the button to change it (Change)",
    "削除": "a price removed, the button, a file deleted (Removed, Remove, Deleted)",
    "やめる": "a dialog's Cancel and a flow's Stop",
    '{"other": "{n} 件"}': "the counter word is the thing counted in English (tables, tasks)",
    "仕様書": "the paper on a desk (Spec) and the tabs of them (Specs)",
    "テスト": "the log's category (Tests) and one run (Test)",
    "全体を見る": "the server room's zoom to fit (Fit all) and the work list's whole (See all)",
    "時刻": "a column (Time) and a robot's run times (Times)",
    "0 件": "the log's count (0 events) and a spec with nothing (None)",
    "拒否": "what was sent (denied) and the button (Deny)",
    "許可": "what was sent (allowed), the button (Allow) and the card's tab (Permission)",
    "未着手": "a spec's status (Not started) and the kanban column (To do)",
    "すべてのプロジェクトを表示": "the button (Show all projects) and the state it is in (Showing all projects)",
    "添付": "the list (Attachments) and one with no name (Attachment)",
    "操作": "a section (Actions) and a table's column (Action)",
}


def _groups(ja: dict, en: dict) -> dict[str, set]:
    by_ja: dict[str, set] = {}
    for key, words in ja.items():
        jw = words if isinstance(words, str) else json.dumps(words, ensure_ascii=False, sort_keys=True)
        ew = en.get(key)
        by_ja.setdefault(jw, set()).add((json.dumps(ew, ensure_ascii=False, sort_keys=True) if not isinstance(ew, str) else ew).casefold())
    return {jw: ens for jw, ens in by_ja.items() if len(ens) > 1}


def _tables():
    return json.loads(web_text("i18n", "ja.json")), json.loads(web_text("i18n", "en.json"))


def test_one_japanese_words_is_one_english_words_unless_said_why():
    split = _groups(*_tables())
    assert {jw: sorted(ens) for jw, ens in split.items() if jw not in SPLIT} == {}


def test_every_split_named_still_splits():
    split = _groups(*_tables())
    assert sorted(jw for jw in SPLIT if jw not in split) == []


def test_the_two_the_ticket_names_are_found():
    """The arm reads the way the ticket's pairs were: each is a group of two English words."""
    ja = {"hist.low.on": "下を広げる", "panel.rb.low": "下を広げる", "page.denied.aria": "自動モードが止めた操作",
          "deny.strip.title": "自動モードが止めた操作", "talk.unknown": "不明", "dev.unknown": "不明"}
    en = {"hist.low.on": "Expand the bottom", "panel.rb.low": "Enlarge the bottom",
          "page.denied.aria": "Actions auto mode stopped", "deny.strip.title": "Calls denied by auto mode",
          "talk.unknown": "unknown", "dev.unknown": "Unknown"}
    assert set(_groups(ja, en)) == {"下を広げる", "自動モードが止めた操作"}           # letter case alone is one words
