"""The view's words in one language (ticket 2026-10-21-jui-viz-language-switch-ja-en).

The requester's ruling (10-21): "言語の切り替えは設定ファイル読み込みでデフォルトは英語で自分で同じキーに文言当てて
好きに設定できるようにしたい". So:

- ``language`` in config.json is any BCP 47 language code (fr, de, zh-TW, pt-BR …; ticket 2026-10-24-viz-language-
  only-en-ja, the requester: 「好きな言語コードを書けるようにする」). The words are the bundled table of its language
  (web/i18n/<language>.json: en, ja) when there is one, else English; the person's ``strings`` file goes over them. The
  dates, times, numbers and plural forms follow the code itself (the page's Intl, ``locale``; Python's plural_form). A
  code that is not one is a problem, and English is used. DEFAULT_LANGUAGE when it says none.
  ``JUI_VIZ_LANGUAGE`` in the environment comes first (the browser tests pin "ja" with it: their checks wait on the
  Japanese words).
- ``strings`` in config.json names a file of the person's own words: the same flat ``{key: words}``, any part of it.
  A path that is not absolute is taken from the viz folder (paths.viz_home()).
- A key is looked up in the person's file, then the language, then English.
- Read once, when the server starts (config.json is read the same way). A mistake never stops the server: what cannot
  be used is left out, and ``problems`` says why (serve's log, ``jui viz doctor``).

A value is a string with ``{name}`` slots, or — for words that change with a count — ``{"one": …, "other": …}``
(Intl.PluralRules' categories; Japanese has "other" only, French one / many / other). ``jui viz strings template
--lang <code>`` writes every key with its English words, a plural key with the language's categories. The page gets
the merged table in index.html (``page_html``) and reads it with ``tl()`` (web/js/05-i18n.js); Python reads it with
``tl()`` here.

The person's file is checked against the English table, which holds every key: a key it does not know, a value of the
wrong shape, a plural form the language does not use, or slots that differ from the bundled words are each left out with
a problem.
"""
from __future__ import annotations

import html as html_mod
import json
import os
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import paths

#: the languages whose words are bundled (web/i18n/<language>.json); config.json's language may be any code
LANGUAGES = ("en", "ja")
#: The words when config.json names no language: English, as the requester ruled (Japanese until the page's words were
#: all in the table, 2.3.12 to the move window; "language": "ja" in config.json for Japanese).
DEFAULT_LANGUAGE = "en"
#: The table that holds every key: what a key missing from the others falls back to.
FALLBACK_LANGUAGE = "en"
LANGUAGE_ENV = "JUI_VIZ_LANGUAGE"
#: index.html's slots, filled by page_html
LANG_SLOT = "__JUI_VIZ_LANG__"
STRINGS_SLOT = "__JUI_VIZ_STRINGS__"
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
_SLOT = re.compile(r"\{(\w+)\}")
#: a BCP 47 language tag (RFC 5646's langtag, without extensions and private use): language, script, region, variants.
#: The language is two or three letters: the grammar's 5 to 8 are kept for registration and none is registered, so
#: "french" is a word, not a code.
_TAG = re.compile(r"^(?P<lang>[a-z]{2,3})(?:-(?P<script>[a-z]{4}))?(?:-(?P<region>[a-z]{2}|\d{3}))?"
                  r"(?P<variants>(?:-(?:[a-z\d]{5,8}|\d[a-z\d]{3}))*)$")
_LETTER_FORM = {"z": "zero", "o": "one", "t": "two", "f": "few", "m": "many", "x": "other"}


def language_tag(given: str) -> str | None:
    """``given`` as a BCP 47 tag in its usual case (fr, zh-Hant-TW, pt-BR; "_" read as "-"), or None when it is not one."""
    m = _TAG.match(str(given).strip().replace("_", "-").lower())
    if not m:
        return None
    parts = [m["lang"]]
    if m["script"]:
        parts.append(m["script"].title())
    if m["region"]:
        parts.append(m["region"].upper())
    parts += [v for v in m["variants"].split("-") if v]
    return "-".join(parts)


def words_language(tag: str) -> str:
    """The bundled table a tag's words come from: its language's when bundled (ja-JP → ja), else English."""
    base = tag.split("-")[0]
    return base if base in LANGUAGES else FALLBACK_LANGUAGE


_PLURAL_ROWS: dict = {}


def _plural_rows() -> dict:
    """plural_rules.json's rows by tag (and its "cldr" under "")."""
    if not _PLURAL_ROWS:
        data = json.loads((resources.files("jui_cli.viz") / "plural_rules.json").read_text(encoding="utf-8"))
        for row in data["rows"]:
            for tag in row["languages"]:
                _PLURAL_ROWS[tag] = row
        _PLURAL_ROWS[""] = data["cldr"]
    return _PLURAL_ROWS


def _known_plural_tags():
    return _plural_rows().keys()


def _plural_cldr() -> str:
    return _plural_rows()[""]


def _plural_row(language: str) -> dict:
    """plural_rules.json's row for a tag: the tag itself (pt-PT), its language (pt), else English's."""
    rows = _plural_rows()
    return rows.get(language) or rows.get(language.split("-")[0]) or rows["en"]


def plural_categories(language: str) -> list:
    """The plural categories a language uses (Intl.PluralRules' pluralCategories), e.g. fr: one, many, other."""
    return list(_plural_row(language)["categories"])


def bundled(language: str) -> dict:
    """web/i18n/<language>.json as shipped."""
    node = resources.files("jui_cli.viz") / "web" / "i18n" / f"{language}.json"
    return json.loads(node.read_text(encoding="utf-8"))


def slots(value) -> set:
    """The {name} slots a value uses (every form of a plural)."""
    texts = value.values() if isinstance(value, dict) else [value]
    return {m for text in texts if isinstance(text, str) for m in _SLOT.findall(text)}


def shape_problem(value, like, language: str = "") -> str | None:
    """Why ``value`` cannot stand for ``like`` (the bundled English words of the same key), or None. With ``language``,
    a plural form it does not use is one too."""
    if isinstance(like, dict):
        if not isinstance(value, dict) or not value or "other" not in value \
                or any(k not in PLURAL_FORMS or not isinstance(v, str) for k, v in value.items()):
            return 'needs {"one": ..., "other": ...} (a count changes these words)'
        if language:
            used = plural_categories(language)
            unused = [k for k in value if k not in used]
            if unused:
                return f"has plural form(s) {', '.join(unused)} that {language} does not use (it uses {', '.join(used)})"
    elif not isinstance(value, str):
        return "is not a string"
    if slots(value) != slots(like):
        want = ", ".join(sorted("{%s}" % s for s in slots(like))) or "none"
        return f"slots differ from the bundled words (they use {want})"
    return None


@dataclass
class Strings:
    language: str = FALLBACK_LANGUAGE
    table: dict = field(default_factory=dict)
    #: the bundled table the words come from (en, ja): the language's own, else English
    words: str = FALLBACK_LANGUAGE
    #: the person's file, when one is named (resolved), how many keys it holds and how many of them are used
    own_path: str = ""
    own_keys: int = 0
    own_used: int = 0
    problems: list = field(default_factory=list)

    @property
    def locale(self) -> str:
        """The page's Intl locale: the language code itself (en and ja as they always were: en-US, ja-JP)."""
        return {"en": "en-US", "ja": "ja-JP"}.get(self.language, self.language)


def _own_path(given: str) -> Path:
    path = Path(given).expanduser()
    return path if path.is_absolute() else paths.viz_home() / path


def load(language: str = "", own: str = "", use_env: bool = True) -> Strings:
    """English, overlaid with ``language``'s words, overlaid with the person's file ``own``. JUI_VIZ_LANGUAGE comes
    before ``language`` unless ``use_env`` is false (export-demo's --lang is said on the command line)."""
    out = Strings()
    english = bundled(FALLBACK_LANGUAGE)
    out.table = dict(english)
    chosen = (os.environ.get(LANGUAGE_ENV, "") if use_env else "") or language or DEFAULT_LANGUAGE
    tag = language_tag(chosen)
    if tag is None:
        out.problems.append(f'language "{chosen}" is not a language code (BCP 47: fr, de, zh-TW, pt-BR …); '
                            f'using {DEFAULT_LANGUAGE}')
        tag = DEFAULT_LANGUAGE
    out.language = tag
    out.words = words_language(tag)
    if tag not in _known_plural_tags() and tag.split("-")[0] not in _known_plural_tags():
        out.problems.append(f'language "{tag}" has no plural rule in CLDR {_plural_cldr()}; counts read as English\'s '
                            f'(one, other)')
    if out.words != FALLBACK_LANGUAGE:
        out.table.update({k: v for k, v in bundled(out.words).items() if k in english})
    if own:
        path = _own_path(own)
        out.own_path = str(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
        except (OSError, ValueError) as exc:
            out.problems.append(f"strings file {path} is not used ({exc})")
            return out
        out.own_keys = len(data)
        for key, value in data.items():
            if key not in english:
                out.problems.append(f'strings file: unknown key "{key}" left out')
                continue
            why = shape_problem(value, english[key], tag)
            if why:
                out.problems.append(f'strings file: "{key}" {why}; left out')
                continue
            out.table[key] = value
            out.own_used += 1
    return out


def from_config(config) -> Strings:
    return load(getattr(config, "language", ""), getattr(config, "strings", ""))


def plural_form(n, language: str) -> str:
    """Intl.PluralRules' category of a whole count in a language (plural_rules.json; a count that is not a whole
    number, or a language CLDR has no rule for, as English: one for 1)."""
    row = _plural_row(language)
    try:
        count = abs(int(n))
        if count != n:
            raise ValueError
    except (TypeError, ValueError):
        return "other"
    if count >= 200:
        if count % 1_000_000 == 0:
            return _LETTER_FORM[row["million"]]
        count = 100 + count % 100
    return _LETTER_FORM[row["counts"][count]]


def template(language: str) -> dict:
    """The person's file to start from: every key with its English words, a plural key with ``language``'s categories
    (one from English's one, the others from its other)."""
    english = bundled(FALLBACK_LANGUAGE)
    used = plural_categories(language)
    return {key: ({form: value.get(form, value["other"]) if form == "one" else value["other"] for form in used}
                  if isinstance(value, dict) else value) for key, value in english.items()}


def lookup(strings: Strings, key: str, params: dict | None = None) -> str:
    """The words of ``key`` with its slots filled. An unknown key is given back as itself (the gate keeps them out)."""
    value = strings.table.get(key, key)
    params = params or {}
    if isinstance(value, dict):
        value = value.get(plural_form(params.get("n"), strings.language)) or value.get("other", key)
    return _SLOT.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), value)


_ACTIVE = Strings()


def activate(strings: Strings) -> None:
    """The server's words from now on (serve calls this once, after reading config.json)."""
    global _ACTIVE
    _ACTIVE = strings


def active() -> Strings:
    """The server's words: the default language's until serve activates the configured ones (a test's server, an import)."""
    if not _ACTIVE.table:
        activate(load())
    return _ACTIVE


def tl(key: str, **params) -> str:
    """The words of ``key`` in the server's language."""
    return lookup(active(), key, params)


#: index.html's words: {{tl:key}}the words as written{{/tl}}, in text or in an attribute's value. The server puts the
#: table's words there, HTML-escaped; {{tlhtml:key}}…{{/tl}} also draws `…` as <code>…</code>. A key the table does not
#: have keeps the words as written. The gate holds the words as written to the Japanese table, letter for letter.
WORDS_MARK = re.compile(r"\{\{(tl|tlhtml):([\w.\-]+)\}\}(.*?)\{\{/tl\}\}", re.S)


def fill_words(html: str, strings: Strings) -> str:
    def one(m):
        kind, key, written = m.groups()
        if key not in strings.table:
            return written
        words = html_mod.escape(lookup(strings, key), quote=True)
        return re.sub(r"`([^`]*)`", r"<code>\1</code>", words) if kind == "tlhtml" else words
    return WORDS_MARK.sub(one, html)


def page_html(html: str, strings: Strings) -> str:
    """index.html with its language and its words: <html lang>, the {{tl:…}} marks, and the JSON the page's tl()
    reads. ``</`` is written ``<\\/`` so no word can end the script element."""
    blob = json.dumps({"language": strings.language, "words": strings.words, "locale": strings.locale,
                       "strings": strings.table},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return fill_words(html, strings).replace(LANG_SLOT, strings.language).replace(STRINGS_SLOT, blob)
