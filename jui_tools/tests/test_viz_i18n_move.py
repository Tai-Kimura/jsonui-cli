"""The mover (tools/viz_i18n/move.py): a part's words into the table, one part a commit, with the Japanese words kept
letter for letter (ticket 2026-10-21-jui-viz-language-switch-ja-en).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "viz_i18n"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import finder  # noqa: E402
import move  # noqa: E402

OLD = """// 待機 in a comment is not a word
const a = '待機';
const b = `未読 ${n} 件`;
const c = '一行目\\n二行目';
const d = `<p>出典: <code>${esc(src)}</code> を見る</p>`;
"""
NEW = """// 待機 in a comment is not a word
const a = tl('x.idle');
const b = tl('x.unread', { n });
const c = tl('x.two');
const d = `<p>${tlHTML('x.src', { src })}</p>`;
"""
JA = {"x.idle": "待機", "x.unread": {"other": "未読 {n} 件"}, "x.two": "一行目\n二行目", "x.src": "出典: `{src}` を見る"}
EN = {"x.idle": "Idle", "x.unread": {"one": "{n} unread", "other": "{n} unread"}, "x.two": "one\ntwo",
      "x.src": "Source: `{src}`, see it"}


def test_a_move_that_keeps_every_word_passes():
    assert move.check("js/x.js", OLD, NEW, JA, EN) == []


@pytest.mark.parametrize("key, words, why", [
    ("x.idle", "待機中", "'待機中' is not in js/x.js as it was"),
    ("x.unread", {"other": "未読 {n}件"}, "'未読 {n}件' is not in js/x.js as it was"),   # a space next to a slot
    ("x.unread", {"other": "未読{n} 件"}, "'未読{n} 件' is not in js/x.js as it was"),
    ("x.two", "一行目\n二行め", "'一行目\\n二行め' is not in js/x.js as it was"),
    ("x.src", "出典：`{src}` を見る", "'出典：`{src}` を見る' is not in js/x.js as it was"),   # a full-width colon
    ("x.src", "出典: `{src}`を見る", "'出典: `{src}`を見る' is not in js/x.js as it was"),
])
def test_a_word_changed_in_the_move_is_red(key, words, why):
    """Both ways say so when the run is gone too: the changed key, then each old run no Japanese words say."""
    ja = dict(JA, **{key: words})
    problems = move.check("js/x.js", OLD, NEW, ja, EN)
    assert problems[0] == f"{key}: {why}"
    assert all("is gone and no Japanese words say it" in p for p in problems[1:])


def test_a_word_dropped_with_no_key_to_say_it_is_red():
    new = NEW.replace("tl('x.two')", "'one'")
    ja = {k: v for k, v in JA.items() if k != "x.two"}
    assert move.check("js/x.js", OLD, new, ja, EN) == ["js/x.js: '一行目' is gone and no Japanese words say it",
                                                       "js/x.js: '二行目' is gone and no Japanese words say it"]


def test_a_key_with_no_english_or_other_slots_is_red():
    assert move.check("js/x.js", OLD, NEW, JA, {k: v for k, v in EN.items() if k != "x.idle"}) == ["x.idle: no English words"]
    en = dict(EN, **{"x.src": "Source: `{source}`"})
    assert move.check("js/x.js", OLD, NEW, JA, en) == [
        "x.src: Japanese slots differ from the bundled words (they use {source})"]


def test_a_word_already_in_the_table_may_say_a_moved_run():
    """A moved word that an older key already says (status.waiting) needs no new key."""
    new = NEW.replace("tl('x.idle')", "tl('status.idle')")
    ja = dict({k: v for k, v in JA.items() if k != "x.idle"}, **{"status.idle": "待機"})
    assert move.check("js/x.js", OLD.replace("'待機'", "'待機'"), new.replace("'status.idle'", "'status.idle'"), ja,
                      dict(EN, **{"status.idle": "Idle"})) == []


def test_the_reviewed_exceptions_are_closed_and_name_real_parts():
    web = Path(move.WEB)
    for (part, _), why in move.KNOWN.items():
        assert (web / part).is_file(), part
        assert why.strip()


def test_the_finder_by_kind():
    assert "".join(finder.chars("a.html", '<!-- 注 --><p title="題">本文</p>')) == "題本文"
    assert "".join(finder.chars("a.css", "/* 注 */ .x::after { content: '読み込み中…'; }")) == "読み込み中"
    assert finder.runs("a.js", "const a = '待機'; const b = `作業${x}中`; // 注") == ["待機", "作業", "中"]
    assert finder.lines("a.js", "x\nconst a = '待機';\n// 注\n") == [(2, "const a = '待機';")]
    with pytest.raises(ValueError):
        finder.positions("a.py", "")


# ---- apply: written only when every check passes -----------------------------------------------------------------

@pytest.fixture()
def web(tmp_path, monkeypatch):
    (tmp_path / "js").mkdir()
    (tmp_path / "i18n").mkdir()
    (tmp_path / "js" / "x.js").write_text(OLD, encoding="utf-8")
    for lang in ("en", "ja"):
        (tmp_path / "i18n" / f"{lang}.json").write_text(json.dumps({"status.idle": "Idle" if lang == "en" else "待機"}), encoding="utf-8")
    monkeypatch.setattr(move, "WEB", tmp_path)
    return tmp_path


def spec(tmp_path, edits, keys) -> str:
    path = tmp_path / "spec.py"
    path.write_text(f"PART = 'js/x.js'\nEDITS = {edits!r}\nKEYS = {keys!r}\n", encoding="utf-8")
    return str(path)


EDITS = [("'待機'", "tl('x.idle')"), ("`未読 ${n} 件`", "tl('x.unread', { n })")]
KEYS = {"x.idle": ("Idle", "待機"), "x.unread": ({"one": "{n} unread", "other": "{n} unread"}, {"other": "未読 {n} 件"})}


def snapshot(web: Path) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in web.rglob("*.js*")}


def test_apply_writes_the_part_and_both_tables(web, capsys):
    assert move.main(["apply", spec(web, EDITS, KEYS)]) == 0
    assert "tl('x.idle')" in (web / "js" / "x.js").read_text()
    ja = json.loads((web / "i18n" / "ja.json").read_text())
    assert ja == {"status.idle": "待機", "x.idle": "待機", "x.unread": {"other": "未読 {n} 件"}}
    assert json.loads((web / "i18n" / "en.json").read_text())["x.idle"] == "Idle"
    assert "kept letter for letter" in capsys.readouterr().out


@pytest.mark.parametrize("edits, keys, why", [
    ([("'待機'", "tl('x.idle')"), ("'待機'", "x")], KEYS, "0 matches"),
    ([("const", "let")], {}, "matches for 'const'"),
    (EDITS, dict(KEYS, **{"status.idle": ("Resting", "待機")}), "status.idle: already in en.json with other words"),
    (EDITS, dict(KEYS, **{"x.spare": ("Spare", "予備")}), "x.spare: not used in js/x.js"),
    (EDITS, dict(KEYS, **{"x.idle": ("Idle", "待機中")}), "x.idle: '待機中' is not in js/x.js as it was"),
    (EDITS, dict(KEYS, **{"x.unread": ({"one": "{n} unread", "other": "{n} unread"}, {"other": "未読 {n}件"})}),
     "x.unread: '未読 {n}件' is not in js/x.js as it was"),
])
def test_apply_writes_nothing_when_a_check_fails(web, capsys, edits, keys, why):
    before = snapshot(web)
    assert move.main(["apply", spec(web, edits, keys)]) == 1
    assert why in capsys.readouterr().err
    assert snapshot(web) == before


def test_scan_lists_the_lines_left(web, capsys):
    assert move.main(["scan", "js/x.js"]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines()[0].strip().startswith("2: const a = '待機';")
    assert "js/x.js: 4 lines" in out.err
