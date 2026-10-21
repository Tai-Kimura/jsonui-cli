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
