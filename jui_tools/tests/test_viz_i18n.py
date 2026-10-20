"""The view's words (jui_cli/viz/i18n.py, web/i18n/, web/js/05-i18n.js; ticket 2026-10-21-jui-viz-language-switch-ja-en).

The gate: the bundled languages hold the same keys with the same slots, every key the code asks for is there and every
key there is asked for, and a file moved to the table has no Japanese left in its code. Then the person's own words:
whatever cannot be used is left out with a problem, never a stopped server.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

from jui_cli.cli import main
from jui_cli.viz import bundle, i18n, paths
from jui_cli.viz.config import load_config

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "viz_i18n"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import finder  # noqa: E402

VIZ = Path(resources.files("jui_cli.viz"))
WEB_JS = VIZ / "web" / "js"
JA = re.compile(r"[぀-ヿ㐀-鿿！-｠]")

#: Files whose words are all in the table: no Japanese outside their comments. Closed: a file joins when it is moved.
MOVED = {"05-i18n.js", "10-robot-core.js", "25-net.js", "52-data-docs.js", "53-waits.js", "54-bills.js", "57-fulltext.js",
         "58-talk.js", "80-dbg.js"}
#: Content written once per language (not words of the table): each set checked where it is made.
PER_LANGUAGE = {"31-talk-demo-data.js": "the demo's talks, one set per language (tests/test_viz_talk_demo_data.py)"}
#: Not moved yet (the ticket's stages 2–3). Each is counted, not held: the count is what is left to move. 60-log.js
#: and 70-main.js keep one word each that another file says too: the demo's event kind 'spec 更新' (30-source-demo.js)
#: and the hook chip's title (index.html); they move with those files.
NOT_YET = {
    "20-core.js", "30-source-demo.js", "30-source-live.js", "40-scene.js", "50-panel.js", "51-denials.js",
    "53-devices.js", "55-history.js", "56-server-room.js", "60-log.js", "70-main.js",
}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("JUI_VIZ_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv(i18n.LANGUAGE_ENV, raising=False)
    paths.viz_home().mkdir(parents=True)
    return tmp_path


def write_config(data: dict) -> None:
    paths.config_json().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def own_words(data, name="mine.json") -> str:
    path = paths.viz_home() / name
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return name


# ---- the bundled tables ------------------------------------------------------------------------------------------

def test_the_bundled_languages_hold_the_same_keys():
    en, ja = i18n.bundled("en"), i18n.bundled("ja")
    assert set(en) - set(ja) == set(), "keys only in en.json"
    assert set(ja) - set(en) == set(), "keys only in ja.json"


def test_each_key_has_the_same_slots_and_shape_in_both():
    en, ja = i18n.bundled("en"), i18n.bundled("ja")
    wrong = {k: i18n.shape_problem(ja[k], en[k]) for k in en if k in ja}
    assert {k: why for k, why in wrong.items() if why} == {}


def code_texts() -> dict[str, str]:
    """Every part of the page and every .py of the server, by name."""
    out = {f"web/js/{p.name}": p.read_text(encoding="utf-8") for p in sorted(WEB_JS.glob("*.js"))}
    out.update({str(p.relative_to(VIZ)): p.read_text(encoding="utf-8") for p in sorted(VIZ.rglob("*.py"))})
    return out


def test_every_key_asked_for_is_in_the_table():
    en = i18n.bundled("en")
    asked = {(name, key) for name, text in code_texts().items() for key in re.findall(r"""\btl\(\s*['"]([^'"]+)['"]""", text)}
    assert sorted((name, key) for name, key in asked if key not in en) == []


WEB = VIZ / "web"
MARKED = ("index.html", "app.css")


def marked_keys() -> set:
    return {k for name in MARKED for k, *_ in finder.marks(name, (WEB / name).read_text(encoding="utf-8"))}


def test_every_key_in_the_table_is_asked_for():
    """A key is used when its name stands in the code as a quoted literal (tl('k') or a table of keys like BADGES),
    or in a mark of index.html or app.css."""
    texts, marked = "\n".join(code_texts().values()), marked_keys()
    assert sorted(k for k in i18n.bundled("en") if f"'{k}'" not in texts and f'"{k}"' not in texts and k not in marked) == []


def test_the_page_and_css_marks_say_the_japanese_words_letter_for_letter():
    """index.html's {{tl:key}}…{{/tl}} and app.css's var(--tl-name, '…') keep the words for a table without the key:
    those words are the Japanese table's, as HTML or CSS writes them, and the key is in the table."""
    ja, en = i18n.bundled("ja"), i18n.bundled("en")
    assert [p for name in MARKED for p in finder.mark_problems(name, (WEB / name).read_text(encoding="utf-8"), ja, en)] == []


def js_code_japanese(text: str) -> list[str]:
    """The Japanese outside comments (tools/viz_i18n/finder.py, shared with the mover)."""
    return finder.chars("part.js", text)


def test_a_moved_file_has_no_japanese_in_its_code():
    left = {name: "".join(js_code_japanese((WEB_JS / name).read_text(encoding="utf-8")))[:40] for name in sorted(MOVED)}
    assert {k: v for k, v in left.items() if v} == {}


def test_the_files_lists_are_closed():
    """Every part is moved or not yet (a new part says which); 80-dbg.js only runs under the browser tests."""
    on_disk = {p.name for p in WEB_JS.glob("*.js")}
    lists = (MOVED, set(PER_LANGUAGE), NOT_YET)
    assert sum(len(x) for x in lists) == len(set().union(*lists)), "a part in two lists"
    assert on_disk - set().union(*lists) == set(), "a part neither moved nor listed as not yet"
    assert set().union(*lists) - on_disk == set(), "a listed part that is gone"


def test_the_finder_sees_japanese_in_code_and_not_in_comments():
    sample = ("// 日本語\n/* 日本語 */ const a = '待機'; const b = `作業${x}中`; const c = /^添付/; const d = 'http://x'; // 後\n"
              "const e = /[\"']/; // 注\nconst f = `複\n行`;\n")
    assert "".join(js_code_japanese(sample)) == "待機作業中添付複行"
    assert "".join(js_code_japanese("const r = /[/']待/; // 注\nx = a / b; // 割\n")) == "待"


# ---- the person's words ------------------------------------------------------------------------------------------

def test_japanese_when_no_language_is_set(home):
    """2.3.12 ships Japanese by default: the page is not all in the table yet, and an English page with Japanese left in
    it is not shipped. Turned to English (and this arm with it) once the rest has moved."""
    assert i18n.DEFAULT_LANGUAGE == "ja" and load_config().language == ""
    words = i18n.from_config(load_config())
    assert (words.language, words.locale, words.problems) == ("ja", "ja-JP", [])
    assert i18n.lookup(words, "status.idle") == "待機"
    write_config({"askWaitSec": 60})
    assert i18n.from_config(load_config()).language == "ja"


def test_english_when_set(home):
    write_config({"language": "en"})
    words = i18n.from_config(load_config())
    assert (words.language, words.locale, words.problems) == ("en", "en-US", [])
    assert i18n.lookup(words, "status.idle") == "Idle"


def test_the_configured_language(home):
    write_config({"language": "ja"})
    words = i18n.from_config(load_config())
    assert (words.language, words.locale) == ("ja", "ja-JP")
    assert i18n.lookup(words, "status.idle") == "待機"


def test_the_environment_comes_before_config(home, monkeypatch):
    write_config({"language": "en"})
    monkeypatch.setenv(i18n.LANGUAGE_ENV, "ja")
    assert i18n.from_config(load_config()).language == "ja"
    assert i18n.load("en", use_env=False).language == "en"


def test_an_unknown_language_is_the_default_with_a_problem(home):
    write_config({"language": "fr"})
    words = i18n.from_config(load_config())
    assert words.language == i18n.DEFAULT_LANGUAGE
    assert words.problems == [f'language "fr" is not one of en, ja; using {i18n.DEFAULT_LANGUAGE}']


def test_a_language_of_the_wrong_type_is_the_default(home, capsys):
    write_config({"language": 1})
    assert i18n.from_config(load_config()).language == i18n.DEFAULT_LANGUAGE
    assert "language" in capsys.readouterr().err


def test_own_words_over_the_language_then_english(home):
    write_config({"language": "ja", "strings": own_words({"status.idle": "ひま"})})
    words = i18n.from_config(load_config())
    assert i18n.lookup(words, "status.idle") == "ひま"
    assert i18n.lookup(words, "status.busy") == "作業中"
    assert (words.own_used, words.problems) == (1, [])
    assert words.own_path == str(paths.viz_home() / "mine.json")


def test_own_words_by_an_absolute_path(home, tmp_path):
    path = tmp_path / "elsewhere.json"
    path.write_text(json.dumps({"status.idle": "Resting"}), encoding="utf-8")
    write_config({"strings": str(path)})
    assert i18n.lookup(i18n.from_config(load_config()), "status.idle") == "Resting"


def test_an_unknown_key_is_left_out_with_a_problem(home):
    write_config({"strings": own_words({"status.idel": "Resting", "status.idle": "Resting"})})
    words = i18n.from_config(load_config())
    assert words.problems == ['strings file: unknown key "status.idel" left out']
    assert (i18n.lookup(words, "status.idle"), words.own_used) == ("Resting", 1)


@pytest.mark.parametrize("value, why", [
    (3, "is not a string"),
    ({"one": "x", "other": "y"}, "is not a string"),
])
def test_a_value_of_the_wrong_shape_is_left_out(home, value, why):
    write_config({"language": "en", "strings": own_words({"status.idle": value})})
    words = i18n.from_config(load_config())
    assert words.problems == [f'strings file: "status.idle" {why}; left out']
    assert i18n.lookup(words, "status.idle") == "Idle"


@pytest.mark.parametrize("text", ["not json", "[1, 2]"])
def test_a_broken_file_is_not_used_and_the_language_stands(home, text):
    write_config({"language": "ja", "strings": own_words(text)})
    words = i18n.from_config(load_config())
    assert len(words.problems) == 1 and words.problems[0].startswith(f"strings file {paths.viz_home() / 'mine.json'} is not used")
    assert i18n.lookup(words, "status.idle") == "待機"


def test_a_missing_file_is_a_problem(home):
    write_config({"strings": "nowhere.json"})
    words = i18n.from_config(load_config())
    assert len(words.problems) == 1 and "nowhere.json is not used" in words.problems[0]


def test_slots_that_differ_are_left_out():
    like = "{n} robots"
    assert i18n.shape_problem("{count} robots", like) == "slots differ from the bundled words (they use {n})"
    assert i18n.shape_problem("robots", like) == "slots differ from the bundled words (they use {n})"
    assert i18n.shape_problem("{n} bots", like) is None


def test_plural_words():
    like = {"one": "{n} robot", "other": "{n} robots"}
    assert i18n.shape_problem({"one": "{n} bot", "other": "{n} bots"}, like) is None
    assert i18n.shape_problem({"other": "{n} 体"}, like) is None
    assert i18n.shape_problem("{n} bots", like) == 'needs {"one": ..., "other": ...} (a count changes these words)'
    assert i18n.shape_problem({"one": "{n} bot"}, like) == 'needs {"one": ..., "other": ...} (a count changes these words)'
    en = i18n.Strings(language="en", table={"k": like})
    ja = i18n.Strings(language="ja", table={"k": {"other": "{n} 体"}})
    assert [i18n.lookup(en, "k", {"n": n}) for n in (1, 2, 0)] == ["1 robot", "2 robots", "0 robots"]
    assert i18n.lookup(ja, "k", {"n": 1}) == "1 体"


def test_a_key_the_table_lacks_comes_back_as_itself():
    assert i18n.lookup(i18n.Strings(), "no.such.key") == "no.such.key"


# ---- the page ----------------------------------------------------------------------------------------------------

def test_the_page_gets_its_language_and_words(home):
    write_config({"language": "ja", "strings": own_words({"status.idle": "</script><b>"})})
    html = i18n.page_html('<html lang="__JUI_VIZ_LANG__"><script type="application/json" id="jui-viz-strings">'
                          '__JUI_VIZ_STRINGS__</script>', i18n.from_config(load_config()))
    assert html.startswith('<html lang="ja">')
    body = re.search(r'id="jui-viz-strings">(.*)</script>$', html, re.S).group(1)
    assert "</script>" not in body
    data = json.loads(body)
    assert (data["language"], data["locale"]) == ("ja", "ja-JP")
    assert data["strings"]["status.idle"] == "</script><b>" and data["strings"]["status.busy"] == "作業中"


def run_tl(table: dict, locale: str, calls: list, fn: str = "tl") -> list:
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    script = (WEB_JS / "05-i18n.js").read_text(encoding="utf-8")
    blob = json.dumps({"language": locale[:2], "locale": locale, "strings": table})
    prelude = f"globalThis.document = {{ getElementById: () => ({{ textContent: {json.dumps(blob)} }}) }};\n"
    out = subprocess.run([node, "-e", prelude + script + f"\nprocess.stdout.write(JSON.stringify({json.dumps(calls)}"
                          f".map(([k, p]) => {fn}(k, p))));"], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_tl_fills_slots_and_picks_plurals():
    table = {"k": {"one": "{n} robot", "other": "{n} robots"}, "s": "{who} is {what}"}
    assert run_tl(table, "en-US", [["k", {"n": 1}], ["k", {"n": 3}], ["s", {"who": "a1", "what": "idle"}],
                                   ["s", {"who": "a1"}], ["missing", None]]) \
        == ["1 robot", "3 robots", "a1 is idle", "a1 is {what}", "missing"]
    assert run_tl({"k": {"other": "{n} 体"}}, "ja-JP", [["k", {"n": 1}]]) == ["1 体"]


def test_tlhtml_escapes_the_words_and_every_slot_and_draws_only_code():
    """Words that hold markup (a <code> in a sentence): the table's words and the slots are text; `…` in the words is
    the one mark they can make, and a slot's backtick makes none."""
    table = {"k": "use `{cmd}` <b>now</b> & {what}"}
    assert run_tl(table, "en-US", [["k", {"cmd": "jui <x>", "what": "`a` \"q\" 'q'"}]], fn="tlHTML") == [
        "use <code>jui &lt;x&gt;</code> &lt;b&gt;now&lt;/b&gt; &amp; &#96;a&#96; &quot;q&quot; &#39;q&#39;"]
    assert run_tl({"p": {"one": "`{n}` robot", "other": "`{n}` robots"}}, "en-US", [["p", {"n": 2}]], fn="tlHTML") == ["<code>2</code> robots"]


def test_the_page_reads_its_words_first():
    for mode in bundle.MODES:
        assert bundle.parts(mode, e2e=False)[0] == "05-i18n.js"


def test_export_demo_writes_the_words_of_its_language(tmp_path, capsys):
    assert main(["viz", "export-demo", "--out", str(tmp_path / "en"), "--lang", "en"]) == 0
    assert main(["viz", "export-demo", "--out", str(tmp_path / "ja"), "--lang", "ja"]) == 0
    assert main(["viz", "export-demo", "--out", str(tmp_path / "default")]) == 0
    assert f'<html lang="{i18n.DEFAULT_LANGUAGE}">' in (tmp_path / "default" / "index.html").read_text()
    en, ja = ((tmp_path / d / "index.html").read_text() for d in ("en", "ja"))
    assert '<html lang="en">' in en and '"status.idle":"Idle"' in en
    assert '<html lang="ja">' in ja and '"status.idle":"待機"' in ja
    assert "__JUI_VIZ_" not in en + ja


# ---- doctor ------------------------------------------------------------------------------------------------------

def doctor_language(capsys) -> str:
    main(["viz", "doctor", "--json"])
    checks = json.loads(capsys.readouterr().out)["checks"]
    row = next(c for c in checks if c["name"] == "language")
    assert row["ok"] is True   # a warning, never a failure
    return row["detail"]


def test_doctor_names_the_language(home, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert doctor_language(capsys).startswith(f"{i18n.DEFAULT_LANGUAGE}. Read when the server starts")
    write_config({"language": "ja", "strings": own_words({"status.idle": "ひま"})})
    assert doctor_language(capsys).startswith(f"ja, own words: {paths.viz_home() / 'mine.json'} (1 keys used). ")


def test_doctor_warns_of_each_problem(home, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")
    write_config({"language": "fr", "strings": own_words({"nope": "x"})})
    detail = doctor_language(capsys)
    assert f'2 warning(s): language "fr" is not one of en, ja; using {i18n.DEFAULT_LANGUAGE}; strings file: unknown key "nope" left out' in detail
    monkeypatch.setenv(i18n.LANGUAGE_ENV, "ja")
    assert "(from JUI_VIZ_LANGUAGE)" in doctor_language(capsys)


# ---- the session's badge compares kinds, not words ----------------------------------------------------------------

def panel_part(*starts: str) -> str:
    """Declarations of 50-panel.js, each from its first line to the first line that closes it at the left edge."""
    lines = (WEB_JS / "50-panel.js").read_text(encoding="utf-8").splitlines()
    out = []
    for start in starts:
        i = next(k for k, line in enumerate(lines) if line.startswith(start))
        j = i if lines[i].rstrip().endswith(";") else next(k for k in range(i, len(lines)) if re.match(r"^[}\]]", lines[k]))
        out.extend(lines[i:j + 1])
    return "\n".join(out)


@pytest.mark.parametrize("locale, table", [("en-US", "en"), ("ja-JP", "ja")])
def test_a_session_badge_is_the_same_in_every_language(locale, table):
    """2.3.11 picked 作業中 over 考え中 by comparing the words: in English neither matched and a working session read
    待機. The kinds decide now, whatever the words."""
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    words = i18n.bundled(table)
    code = panel_part("const BADGES", "function robotBadgeKind", "const badgeOf", "const robotBadge", "function sessionBadge")
    blob = json.dumps({"language": locale[:2], "locale": locale, "strings": words})
    prelude = f"globalThis.document = {{ getElementById: () => ({{ textContent: {json.dumps(blob)} }}) }};\n"
    robots = {"t": {"state": "thinking"}, "b": {"state": "busy"}, "d": {"state": "done"}, "q": {"state": "waiting", "asking": True},
              "w": {"state": "waiting"}, "g": {"state": "background"}}
    cases = [["t", "b"], ["t"], ["d"], ["g", "t"], ["q", "b"], ["q", "w"], ["g", "d"]]
    script = (prelude + (WEB_JS / "05-i18n.js").read_text(encoding="utf-8") + f"\nconst robotState = {json.dumps(robots)};\n" + code
              + f"\nprocess.stdout.write(JSON.stringify({json.dumps(cases)}.map((r) => sessionBadge({{ robots: r }}))));")
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    w = words
    assert json.loads(out.stdout) == [
        ["st-busy", w["status.busy"]], ["st-busy", w["status.thinking"]], ["st-idle", w["status.idle"]],
        ["st-busy", w["status.thinking"]], ["st-asking", w["status.asking"]], ["st-waiting", w["status.waiting"]],
        ["st-bg", w["status.background"]],
    ]


# ---- index.html's marks (filled by the server) and app.css's (CSS variables from 05-i18n.js) -----------------------

def test_a_mark_takes_the_tables_words_html_escaped():
    words = i18n.Strings(language="en", table={"a.t": 'Say "hi" & <b>', "a.c": "run `jui viz` now"})
    page = '<p title="{{tl:a.t}}題{{/tl}}">{{tl:a.t}}本文{{/tl}} {{tlhtml:a.c}}x{{/tl}}</p>'
    assert i18n.fill_words(page, words) == ('<p title="Say &quot;hi&quot; &amp; &lt;b&gt;">Say &quot;hi&quot; &amp; '
                                            '&lt;b&gt; run <code>jui viz</code> now</p>')


def test_a_key_the_table_lacks_keeps_the_words_as_written():
    words = i18n.Strings(language="en", table={})
    assert i18n.fill_words('<p title="{{tl:no.key}}題 &amp; 名{{/tl}}">{{tl:no.key}}元の文{{/tl}}</p>', words) \
        == '<p title="題 &amp; 名">元の文</p>'


def test_a_persons_words_cannot_break_out_of_a_mark(home):
    """A person's file may say anything: it lands escaped, and a {{/tl}} in it ends nothing."""
    write_config({"language": "en", "strings": own_words({"status.idle": "{{/tl}}</p><script>x</script>"})})
    page = i18n.page_html('<p>{{tl:status.idle}}待機{{/tl}} {{tl:status.busy}}作業中{{/tl}}</p>', i18n.from_config(load_config()))
    assert page == "<p>{{/tl}}&lt;/p&gt;&lt;script&gt;x&lt;/script&gt; Working</p>"


def css_vars(table: dict) -> dict:
    node = shutil.which("node")
    assert node, "node is needed (the jui_tools job has it)"
    blob = json.dumps({"language": "en", "locale": "en-US", "strings": table})
    prelude = ("const set = {};\nglobalThis.document = { getElementById: () => ({ textContent: " + json.dumps(blob) + " }),"
               " documentElement: { style: { setProperty: (k, v) => { set[k] = v; } } } };\n")
    out = subprocess.run([node, "-e", prelude + (WEB_JS / "05-i18n.js").read_text(encoding="utf-8")
                          + "\nprocess.stdout.write(JSON.stringify(set));"], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_css_words_are_set_as_css_strings():
    got = css_vars({"css.hist.loading": "Loading…", "css.q": 'say "hi" \\ back\nnext', "status.idle": "Idle",
                    "css.n": {"one": "{n} x", "other": "{n} xs"}})
    assert got == {"--tl-hist-loading": '"Loading…"', "--tl-q": '"say \\"hi\\" \\\\ back\\A next"'}
