"""tools/viz_e2e/words_to_keys.py (ticket 2026-10-21-viz-english-screen-checks §2c): a suite's Japanese words sorted
into the page's words (with their key, for T(key)) and the rest, from the Japanese table — the list a person moves a
suite to T(key) from. It writes nothing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"))
import words_to_keys as W  # noqa: E402

EXACT, SLOTTED = W.table()


def test_words_equal_to_a_keys_are_that_key():
    assert W.classify("ロボットへ移る", EXACT, SLOTTED) == {"kind": "key", "keys": ["talk.go"], "use": 'T("talk.go")'}


def test_words_with_slots_filled_name_the_slots_and_are_marked_to_look_at():
    got = W.classify("a1 のメインセッション", EXACT, SLOTTED)
    assert got["kind"] == "slots" and "talk.robot.main" in got["keys"] and "id='a1'" in got["use"]


def test_content_a_suite_gives_the_page_is_not_the_pages():
    assert W.classify("好きな果物は？ りんご", EXACT, SLOTTED)["kind"] in ("not the page's", "part")
    assert W.classify("ぬるぽ", EXACT, SLOTTED) == {"kind": "not the page's", "keys": [], "use": None}


def test_docstrings_and_comments_are_not_read(tmp_path):
    f = tmp_path / "s.py"
    f.write_text('"""ロボットへ移る"""\n# ロボットへ移る\nx = "ロボットへ移る"\ny = f"{x}ロボットへ移る"\n', encoding="utf-8")
    assert [n for n, _ in W.literals(f)] == [3, 4]
