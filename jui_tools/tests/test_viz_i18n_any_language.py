"""config.json's "language" is any language code (ticket 2026-10-24-viz-language-only-en-ja; the requester:
「好きな言語コードを書けるようにする」).

Until 2.3.22 only "en" and "ja" were taken: "fr" was a problem, and the page's dates, times, numbers and plural forms
were en-US for every language but Japanese. Now the code is the page's language and its Intl locale; the words are the
bundled table of its language (en, ja) or English, under the person's own file; Python's plural forms follow the code
(plural_rules.json, CLDR's rules for whole counts); `jui viz strings template --lang <code>` writes every key to start
the file from. The page side is read by running 05-i18n.js itself in node (its Intl), when node is there.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jui_cli.viz import i18n

VIZ = Path(i18n.__file__).resolve().parent
ENGLISH = i18n.bundled("en")
PLURAL_KEY = "bill.title.responses"   # {"one": "{n} response", "other": "{n} responses"}
NODE = shutil.which("node")


@pytest.fixture()
def fr_words(tmp_path):
    """A person's French file: two words, the plural key with French's forms."""
    path = tmp_path / "fr.json"
    path.write_text(json.dumps({"status.idle": "libre", PLURAL_KEY: {"one": "{n} réponse", "many": "{n} de réponses",
                                                                     "other": "{n} réponses"}}), encoding="utf-8")
    return path


def test_fr_with_its_own_file(fr_words):
    words = i18n.load("fr", str(fr_words), use_env=False)
    assert (words.language, words.words, words.locale, words.problems) == ("fr", "en", "fr", [])
    assert (words.own_keys, words.own_used) == (2, 2)
    # the person's words, and English where the file says nothing
    assert i18n.lookup(words, "status.idle") == "libre"
    assert i18n.lookup(words, "status.done") == ENGLISH["status.done"]
    # French's plural forms in Python: 0 and 1 are one, a million many
    assert [i18n.lookup(words, PLURAL_KEY, {"n": n}) for n in (0, 1, 2, 1_000_000)] == [
        "0 réponse", "1 réponse", "2 réponses", "1000000 de réponses"]
    # the page: <html lang> and the locale its Intl reads
    page = i18n.page_html(f'<html lang="{i18n.LANG_SLOT}"><script id="jui-viz-strings">{i18n.STRINGS_SLOT}</script>',
                          words)
    assert page.startswith('<html lang="fr">')
    blob = json.loads(page.split('<script id="jui-viz-strings">')[1].split("</script>")[0])
    assert (blob["language"], blob["words"], blob["locale"]) == ("fr", "en", "fr")


def test_a_code_in_any_case_with_a_region_and_the_bundled_words_of_its_language():
    assert [i18n.language_tag(t) for t in ("FR", "pt_br", "zh-hant-tw", "sr-Latn-RS", "de-1996")] == [
        "fr", "pt-BR", "zh-Hant-TW", "sr-Latn-RS", "de-1996"]
    words = i18n.load("ja-JP", use_env=False)
    assert (words.language, words.words, words.locale) == ("ja-JP", "ja", "ja-JP")
    assert words.table["status.idle"] == i18n.bundled("ja")["status.idle"]
    # en and ja keep the locales they always had
    assert (i18n.load("en", use_env=False).locale, i18n.load("ja", use_env=False).locale) == ("en-US", "ja-JP")


@pytest.mark.parametrize("given", ["french", "fr-", "12", "f", "en_US.UTF-8", "fr fr"])
def test_a_string_that_is_not_a_code_is_english_with_a_problem(given):
    words = i18n.load(given, use_env=False)
    assert (words.language, words.locale) == ("en", "en-US")
    assert words.problems == [f'language "{given}" is not a language code (BCP 47: fr, de, zh-TW, pt-BR …); using en']


def test_a_code_cldr_has_no_plural_rule_for_says_so():
    words = i18n.load("qq", use_env=False)
    assert (words.language, words.locale) == ("qq", "qq")
    assert words.problems == ["language \"qq\" has no plural rule in CLDR 48.0; counts read as English's (one, other)"]


def test_a_plural_form_the_language_does_not_use_is_left_out(tmp_path):
    path = tmp_path / "mine.json"
    path.write_text(json.dumps({PLURAL_KEY: {"one": "{n} réponse", "few": "{n} réponses", "other": "{n} réponses"}}),
                    encoding="utf-8")
    words = i18n.load("fr", str(path), use_env=False)
    assert words.own_used == 0 and words.table[PLURAL_KEY] == ENGLISH[PLURAL_KEY]
    assert words.problems == [f'strings file: "{PLURAL_KEY}" has plural form(s) few that fr does not use (it uses one, '
                              f'many, other); left out']
    path.write_text(json.dumps({PLURAL_KEY: {"one": "{n}件", "other": "{n}件"}}), encoding="utf-8")
    assert "that ja does not use (it uses other)" in i18n.load("ja", str(path), use_env=False).problems[0]


@pytest.mark.parametrize("language,forms", [("fr", ["one", "many", "other"]), ("ru", ["one", "few", "many", "other"]),
                                            ("ar", ["zero", "one", "two", "few", "many", "other"]), ("ja", ["other"]),
                                            ("de", ["one", "other"])])
def test_the_template_holds_every_key_with_the_languages_plural_forms(tmp_path, language, forms):
    t = i18n.template(language)
    assert list(t) == list(ENGLISH)
    for key, value in ENGLISH.items():
        if isinstance(value, dict):
            assert list(t[key]) == forms, key
            assert all(t[key][f] == (value["one"] if f == "one" else value["other"]) for f in forms), key
        else:
            assert t[key] == value, key
    # as the person's file, untouched, every key is taken and nothing is said
    path = tmp_path / f"{language}.json"
    path.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    words = i18n.load(language, str(path), use_env=False)
    assert (words.problems, words.own_used, words.own_keys) == ([], len(ENGLISH), len(ENGLISH))


def test_jui_viz_strings_template(capsys, monkeypatch, tmp_path):
    from jui_cli.commands import viz_cmd

    monkeypatch.setenv("JUI_VIZ_HOME", str(tmp_path))
    assert viz_cmd._cmd_strings(argparse.Namespace(strings_action="template", lang="fr")) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == i18n.template("fr")
    assert "plural forms for fr: one, many, other" in err
    assert viz_cmd._cmd_strings(argparse.Namespace(strings_action="template", lang="french")) == 1
    assert '"french" is not a language code' in capsys.readouterr().err


# ---- the page: 05-i18n.js itself, in node (its Intl is the browser's kind: the full ICU), with the table the server
# writes. A count's form and a number's shape come from the code.
PAGE_PROBE = r"""
const fs = require('fs');
const [file, blob] = process.argv.slice(2);
global.document = { getElementById: () => ({ textContent: blob }), documentElement: { style: { setProperty() {} } } };
eval(fs.readFileSync(file, 'utf8') + `
console.log(JSON.stringify({ locale: LOCALE, forms: [0, 1, 2, 1000000].map((n) => tl('bill.title.responses', { n })),
  num: fmtNum(1234567.5), idle: tl('status.idle') }));`);
"""


@pytest.mark.skipif(NODE is None, reason="node is not on PATH: the page's side is not read")
def test_the_page_counts_and_numbers_in_french(fr_words, tmp_path):
    words = i18n.load("fr", str(fr_words), use_env=False)
    page = i18n.page_html(i18n.STRINGS_SLOT, words)
    probe = tmp_path / "probe.js"
    probe.write_text(PAGE_PROBE, encoding="utf-8")
    run = subprocess.run([NODE, str(probe), str(VIZ / "web/js/05-i18n.js"), page], capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0, run.stderr
    got = json.loads(run.stdout)
    assert got["locale"] == "fr" and got["idle"] == "libre"
    assert got["forms"] == ["0 réponse", "1 réponse", "2 réponses", "1000000 de réponses"]
    assert got["num"] == "1 234 567,5", got["num"]   # French: a narrow space, a comma
    # the same page in English is English-shaped (the control)
    page = i18n.page_html(i18n.STRINGS_SLOT, i18n.load("en", use_env=False))
    run = subprocess.run([NODE, str(probe), str(VIZ / "web/js/05-i18n.js"), page], capture_output=True, text=True,
                         timeout=60)
    assert json.loads(run.stdout)["num"] == "1,234,567.5"


PLURAL_PROBE = r"""
const [tags, counts] = process.argv.slice(2).map((a) => JSON.parse(a));
console.log(JSON.stringify(Object.fromEntries(tags.map((t) => [t, counts.map((n) => new Intl.PluralRules(t).select(n))]))));
"""


@pytest.mark.skipif(NODE is None, reason="node is not on PATH: the table is not compared with Intl")
def test_the_plural_table_agrees_with_intl(tmp_path):
    """Every language of plural_rules.json, counts 0..320 and large ones, against node's Intl.PluralRules. A node whose
    ICU has other CLDR rules than the table's says so rather than failing on them."""
    data = json.loads((VIZ / "plural_rules.json").read_text(encoding="utf-8"))
    tags = [t for row in data["rows"] for t in row["languages"]]
    counts = list(range(321)) + [999, 1000, 1001, 10_000, 100_011, 999_999, 1_000_000, 2_000_000, 1_234_567, 10**9]
    probe = tmp_path / "plural.js"
    probe.write_text(PLURAL_PROBE, encoding="utf-8")
    run = subprocess.run([NODE, str(probe), json.dumps(tags), json.dumps(counts)], capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0, run.stderr
    intl = json.loads(run.stdout)
    cldr = subprocess.run([NODE, "-p", "process.versions.cldr"], capture_output=True, text=True).stdout.strip()
    if cldr != data["cldr"]:
        pytest.skip(f"node's CLDR is {cldr}, the table's {data['cldr']}: not compared")
    wrong = [(t, n, i18n.plural_form(n, t), want) for t in tags for n, want in zip(counts, intl[t])
             if i18n.plural_form(n, t) != want]
    assert not wrong, wrong[:20]
    cats = subprocess.run([NODE, "-e", f"console.log(JSON.stringify(Object.fromEntries({json.dumps(tags)}.map((t) => "
                           "[t, new Intl.PluralRules(t).resolvedOptions().pluralCategories]))))"],
                          capture_output=True, text=True).stdout
    order = ["zero", "one", "two", "few", "many", "other"]
    assert {t: i18n.plural_categories(t) for t in tags} == {t: sorted(c, key=order.index) for t, c in json.loads(cats).items()}


def test_a_spirits_words_by_a_code_then_its_language():
    from jui_cli.viz.spirits import words

    title = {"ja": "ねこ", "pt": "gato", "pt-BR": "gatinho"}
    assert [words(title, c) for c in ("pt-BR", "pt-PT", "fr")] == ["gatinho", "gato", "ねこ"]


@pytest.mark.skipif(NODE is None, reason="node is not on PATH: the page's side is not read")
def test_the_page_picks_its_bundled_words_sets_by_the_codes_language(tmp_path):
    """The talk demo's set and a spirit's words, on a page whose code has a region (ja-JP) or none bundled (pt-BR)."""
    probe = tmp_path / "pick.js"
    probe.write_text(r"""
const fs = require('fs');
const [talk, spirits, blob] = process.argv.slice(2);
const I18N = JSON.parse(blob);
eval(fs.readFileSync(talk, 'utf8') + fs.readFileSync(spirits, 'utf8').split('/* The list, asked')[0] + `
console.log(JSON.stringify({ talk: TALK_DEMO === TALK_DEMO_BY_LANGUAGE.ja ? 'ja' : TALK_DEMO === TALK_DEMO_BY_LANGUAGE.en ? 'en' : '?',
  spirit: spiritWords({ ja: 'ねこ', pt: 'gato' }) }));`);
""", encoding="utf-8")
    got = {}
    for code in ("ja-JP", "pt-BR"):
        s = i18n.load(code, use_env=False)
        blob = json.dumps({"language": s.language, "words": s.words, "locale": s.locale})
        run = subprocess.run([NODE, str(probe), str(VIZ / "web/js/31-talk-demo-data.js"), str(VIZ / "web/js/45-spirits.js"),
                              blob], capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        got[code] = json.loads(run.stdout)
    assert got == {"ja-JP": {"talk": "ja", "spirit": "ねこ"}, "pt-BR": {"talk": "en", "spirit": "gato"}}


# ---- not French only (the requester, 10-24: 「ドイツ語とかイタリア語とか韓国語とか中国語とか対応してほしい」 — the codes,
# no bundled words): each code is the page's lang and locale, its counts' forms and the template's are the language's,
# and the page writes dates and numbers its way. Italian is one / many / other in CLDR 48 (a whole million is many),
# as French is.
CODES = {   # code -> (plural forms, a million's form, 1234567.5 on the page, 24 October on the page)
    "fr": (["one", "many", "other"], "many", "1 234 567,5", "24 octobre"),
    "de": (["one", "other"], "other", "1.234.567,5", "24. Oktober"),
    "it": (["one", "many", "other"], "many", "1.234.567,5", "24 ottobre"),
    "ko": (["other"], "other", "1,234,567.5", "10월 24일"),
    "zh-CN": (["other"], "other", "1,234,567.5", "10月24日"),
    "zh-TW": (["other"], "other", "1,234,567.5", "10月24日"),
}
DATE_PROBE = r"""
const fs = require('fs');
const [file, blob] = process.argv.slice(2);
global.document = { getElementById: () => ({ textContent: blob }), documentElement: { style: { setProperty() {} } } };
eval(fs.readFileSync(file, 'utf8') + `
console.log(JSON.stringify({ locale: LOCALE, million: PLURAL.select(1000000), one: PLURAL.select(1), num: fmtNum(1234567.5),
  day: new Date(Date.UTC(2026, 9, 24, 3)).toLocaleDateString(LOCALE, { month: 'long', day: 'numeric', timeZone: 'UTC' }) }));`);
"""


@pytest.mark.parametrize("code", list(CODES))
def test_each_code_is_the_pages_language_with_its_forms(code, tmp_path):
    forms, million, num, day = CODES[code]
    words = i18n.load(code, use_env=False)
    assert (words.language, words.words, words.locale, words.problems) == (code, "en", code, [])
    assert i18n.plural_categories(code) == forms
    assert i18n.plural_form(1_000_000, code) == million
    assert i18n.plural_form(1, code) == ("one" if "one" in forms else "other")
    assert all(list(v) == forms for v in i18n.template(code).values() if isinstance(v, dict))
    page = i18n.page_html(f'<html lang="{i18n.LANG_SLOT}">{i18n.STRINGS_SLOT}', words)
    assert page.startswith(f'<html lang="{code}">')
    if NODE is None:
        pytest.skip("node is not on PATH: the page's dates and numbers are not read")
    probe = tmp_path / "date.js"
    probe.write_text(DATE_PROBE, encoding="utf-8")
    run = subprocess.run([NODE, str(probe), str(VIZ / "web/js/05-i18n.js"), page.split(">", 1)[1]], capture_output=True,
                         text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    got = json.loads(run.stdout)
    assert got == {"locale": code, "million": million, "one": "one" if "one" in forms else "other", "num": num, "day": day}


def test_a_numeric_region_is_a_region():
    """UN M.49 regions are three digits: es-419 (Spanish of Latin America) is a code, with Spanish's plural rule."""
    words = i18n.load("es-419", use_env=False)
    assert (words.language, words.locale, words.problems) == ("es-419", "es-419", [])
    assert i18n.plural_categories("es-419") == ["one", "many", "other"]
    assert i18n.language_tag("es-41") is None   # two digits: neither a region nor a variant (es-4190 is a variant)


@pytest.mark.parametrize("n", [1.5, 0.5, 2.25, "1", None])
def test_a_count_that_is_not_a_whole_number_is_other(n):
    """English's 1.5 is "1.5 responses", not "1.5 response" (Intl.PluralRules('en').select(1.5) is "other")."""
    assert i18n.plural_form(n, "en") == "other"
    assert i18n.lookup(i18n.load("en", use_env=False), PLURAL_KEY, {"n": n}) == f"{n} responses"
