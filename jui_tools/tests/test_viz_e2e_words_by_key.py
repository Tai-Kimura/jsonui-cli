"""tools/viz_e2e/common.T (ticket 2026-10-21-viz-english-screen-checks §2c): a browser test compares the page with the
table's words for a key in the run's language, so one suite reads the same in Japanese and in English."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "viz_e2e"))
import common  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(common, "_STRINGS", None)


def test_the_words_follow_the_run_s_language(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "ja")
    ja = common.T("talk.robot.main", id="a1")
    monkeypatch.setattr(common, "_STRINGS", None)
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    en = common.T("talk.robot.main", id="a1")
    assert ja == "a1 のメインセッション" and en == "a1's main session"


def test_a_count_picks_its_form(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    from jui_cli.viz import i18n
    plural = next(k for k, v in i18n.bundled("en").items() if isinstance(v, dict) and "one" in v and "{n}" in v["one"])
    assert common.T(plural, n=1) != common.T(plural, n=2)


def test_a_key_the_table_lacks_raises(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    with pytest.raises(KeyError, match="no words for 'panel.nope' in the en table"):
        common.T("panel.nope")


def test_a_pattern_fills_what_it_is_given_and_matches_the_rest(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    p = common.T_pattern("panel.nt.perm", tool="Bash")
    assert p.search("a0 is waiting for permission: Bash") and not p.search("a0 is waiting for permission: Edit")
    monkeypatch.setattr(common, "_STRINGS", None)
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "ja")
    p = common.T_pattern("panel.nt.done")
    assert p.fullmatch("a0（Login 画面を実装） が完了") and not p.search("a0 is done")


def test_a_pattern_takes_a_pattern_for_a_slot(monkeypatch):
    import re
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    p = common.T_pattern("live.usage.left.time", h="2", m=re.compile(r"1\d"))
    assert p.fullmatch("2:15 left") and not p.search("2:25 left")


def test_the_head_of_words_is_what_comes_before_the_slot(monkeypatch):
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "ja")
    assert common.T_head("panel.q.end.time", "at") == "ブラウザで答えられる時間が過ぎました"
    monkeypatch.setattr(common, "_STRINGS", None)
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    assert common.T_head("panel.q.end.time", "at") == "The time to answer in the browser is over"


def test_the_demo_talks_words_follow_the_language_and_the_generator_is_not_run(monkeypatch):
    data = Path(__file__).resolve().parents[1] / "jui_cli" / "viz" / "web" / "js" / "31-talk-demo-data.js"
    before = data.stat().st_mtime_ns
    monkeypatch.setattr(common, "_DEMO_TALK", None)
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "ja")
    assert common.demo_talk("a3") == "サブエージェント a3（jsonui-define）"
    monkeypatch.setenv("JUI_VIZ_LANGUAGE", "en")
    assert common.demo_talk("a3") == "subagent a3 (jsonui-define)" and common.demo_talk(11)[0].startswith("The screenshots")
    assert data.stat().st_mtime_ns == before                     # talk_demo_gen.py writes the file when it runs
