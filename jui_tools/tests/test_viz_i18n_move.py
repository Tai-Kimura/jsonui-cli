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
    for (part, _), why in move.KNOWN.items():
        assert move.part_path(part).is_file(), part
        assert why.strip()


def test_the_finder_by_kind():
    assert "".join(finder.chars("a.html", '<!-- 注 --><p title="題">本文</p>')) == "題本文"
    assert "".join(finder.chars("a.css", "/* 注 */ .x::after { content: '読み込み中…'; }")) == "読み込み中"
    assert finder.runs("a.js", "const a = '待機'; const b = `作業${x}中`; // 注") == ["待機", "作業", "中"]
    assert finder.lines("a.js", "x\nconst a = '待機';\n// 注\n") == [(2, "const a = '待機';")]
    with pytest.raises(ValueError):
        finder.positions("a.rb", "")


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


# ---- index.html and app.css: words moved into marks ----------------------------------------------------------------

HTML_OLD = '<p title="題 &amp; 名">本文</p><button aria-label="閉じる">×</button>'
HTML_NEW = ('<p title="{{tl:x.title}}題 &amp; 名{{/tl}}">{{tl:x.body}}本文{{/tl}}</p>'
            '<button aria-label="{{tl:x.close}}閉じる{{/tl}}">×</button>')
HTML_JA = {"x.title": "題 & 名", "x.body": "本文", "x.close": "閉じる"}
HTML_EN = {"x.title": "Title & name", "x.body": "Body", "x.close": "Close"}


def test_an_html_move_into_marks_passes():
    assert move.check("index.html", HTML_OLD, HTML_NEW, HTML_JA, HTML_EN) == []
    assert finder.chars("index.html", HTML_NEW) == []


def test_an_html_mark_whose_words_differ_from_the_table_is_red():
    ja = dict(HTML_JA, **{"x.close": "閉じます"})
    problems = move.check("index.html", HTML_OLD, HTML_NEW, ja, HTML_EN)
    assert "index.html: x.close is written '閉じる', the Japanese words are '閉じます'" in problems
    assert "x.close: '閉じます' is not in index.html as it was" in problems


def test_an_html_mark_with_no_key_in_the_table_is_red():
    problems = move.check("index.html", HTML_OLD, HTML_NEW.replace("x.close", "x.shut"), HTML_JA, HTML_EN)
    assert "index.html: x.shut is not in the table" in problems


def test_a_css_move_into_a_variable_passes_and_a_changed_word_is_red():
    old = ".a::after { content: '読み込み中…'; }"
    new = ".a::after { content: var(--tl-hist-loading, '読み込み中…'); }"
    ja, en = {"css.hist.loading": "読み込み中…"}, {"css.hist.loading": "Loading…"}
    assert move.check("app.css", old, new, ja, en) == []
    assert move.check("app.css", old, new, {"css.hist.loading": "読込中…"}, en)[0] == (
        "app.css: css.hist.loading is written '読み込み中…', the Japanese words are '読込中…'")
    bad = new.replace("--tl-hist-loading", "--tl-Hist-Loading")
    assert any("a css key is css. and lower-case" in p for p in move.check(
        "app.css", old, bad, {"css.Hist.Loading": "読み込み中…"}, {"css.Hist.Loading": "Loading…"}))


# ---- the server's words: Python parts ------------------------------------------------------------------------------

PY_OLD = '''"""A docstring: 説明 is not a word."""
# 注: a comment
ACT = "待機"
def f(x):
    """Docstring 説明."""
    return f"出勤 {x['source']}"
'''
PY_NEW = '''"""A docstring: 説明 is not a word."""
# 注: a comment
ACT = tl("srv.idle")
def f(x):
    """Docstring 説明."""
    return tl("srv.clock_in", source=x['source'])
'''


def test_the_finder_reads_python_strings_not_docstrings_or_comments():
    assert finder.runs("viz/x.py", PY_OLD) == ["待機", "出勤"]
    assert finder.chars("viz/x.py", PY_NEW) == []


def test_a_python_move_with_an_f_string_slot_passes_and_a_changed_word_is_red():
    ja, en = {"srv.idle": "待機", "srv.clock_in": "出勤 {source}"}, {"srv.idle": "Idle", "srv.clock_in": "Clock in {source}"}
    assert move.check("viz/x.py", PY_OLD, PY_NEW, ja, en) == []
    bad = dict(ja, **{"srv.clock_in": "出勤{source}"})
    assert move.check("viz/x.py", PY_OLD, PY_NEW, bad, en)[0] == "srv.clock_in: '出勤{source}' is not in viz/x.py as it was"


def test_a_server_part_is_found_under_viz():
    assert move.part_path("viz/ingest.py") == move.WEB.parent / "ingest.py"
    assert move.part_path("js/58-talk.js") == move.WEB / "js" / "58-talk.js"
    assert move.repo_path("viz/sources/history.py") == "jui_tools/jui_cli/viz/sources/history.py"
    assert move.part_path("jui_cli/commands/viz_cmd.py") == move.JT / "jui_cli" / "commands" / "viz_cmd.py"
    assert move.repo_path("jui_cli/commands/viz_cmd.py") == "jui_tools/jui_cli/commands/viz_cmd.py"


def test_apply_takes_an_edit_meant_for_n_places(web, capsys):
    (web / "js" / "x.js").write_text(OLD + "const e = '待機';\n", encoding="utf-8")
    edits = [("'待機'", "tl('x.idle')", 2), ("`未読 ${n} 件`", "tl('x.unread', { n })")]
    assert move.main(["apply", spec(web, edits, KEYS)]) == 0
    assert (web / "js" / "x.js").read_text().count("tl('x.idle')") == 2
    (web / "js" / "x.js").write_text(OLD + "const e = '待機';\n", encoding="utf-8")
    assert move.main(["apply", spec(web, [("'待機'", "tl('x.idle')", 3)], KEYS)]) == 1
    assert "2 matches" in capsys.readouterr().err


def test_apply_counts_a_key_in_a_mark_as_used(web):
    """index.html's {{tl:key}} and app.css's var(--tl-name) name their keys unquoted (the first draft of index.html's
    move was refused key by key as unused)."""
    (web / "index.html").write_text('<p title="題">本文</p>', encoding="utf-8")
    path = web / "s.py"
    path.write_text("PART = 'index.html'\nEDITS = [('題', '{{tl:x.t}}題{{/tl}}'), ('本文', '{{tl:x.b}}本文{{/tl}}')]\n"
                    "KEYS = {'x.t': ('Title', '題'), 'x.b': ('Body', '本文')}\n", encoding="utf-8")
    assert move.main(["apply", str(path)]) == 0
    assert (web / "index.html").read_text() == '<p title="{{tl:x.t}}題{{/tl}}">{{tl:x.b}}本文{{/tl}}</p>'
