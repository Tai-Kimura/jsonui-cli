"""The view's words in one language (ticket 2026-10-21-jui-viz-language-switch-ja-en).

The requester's ruling (10-21): "言語の切り替えは設定ファイル読み込みでデフォルトは英語で自分で同じキーに文言当てて
好きに設定できるようにしたい". So:

- ``language`` in config.json picks the words: "en" or "ja", bundled as web/i18n/<language>.json; DEFAULT_LANGUAGE
  when it says none.
  ``JUI_VIZ_LANGUAGE`` in the environment comes first (the browser tests pin "ja" with it: their checks wait on the
  Japanese words).
- ``strings`` in config.json names a file of the person's own words: the same flat ``{key: words}``, any part of it.
  A path that is not absolute is taken from the viz folder (paths.viz_home()).
- A key is looked up in the person's file, then the language, then English.
- Read once, when the server starts (config.json is read the same way). A mistake never stops the server: what cannot
  be used is left out, and ``problems`` says why (serve's log, ``jui viz doctor``).

A value is a string with ``{name}`` slots, or — for words that change with a count — ``{"one": …, "other": …}``
(Intl.PluralRules' categories; Japanese has "other" only). The page gets the merged table in index.html
(``page_html``) and reads it with ``tl()`` (web/js/05-i18n.js); Python reads it with ``tl()`` here.

The person's file is checked against the English table, which holds every key: a key it does not know, a value of the
wrong shape, or slots that differ from the bundled words are each left out with a problem.
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

LANGUAGES = ("en", "ja")
#: The words when config.json names no language. Japanese until the page's words are all in the table (2.3.12: a page
#: in English with Japanese left in it is not shipped); English from then on, as the requester ruled.
DEFAULT_LANGUAGE = "ja"
#: The table that holds every key: what a key missing from the others falls back to.
FALLBACK_LANGUAGE = "en"
LANGUAGE_ENV = "JUI_VIZ_LANGUAGE"
#: index.html's slots, filled by page_html
LANG_SLOT = "__JUI_VIZ_LANG__"
STRINGS_SLOT = "__JUI_VIZ_STRINGS__"
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
_SLOT = re.compile(r"\{(\w+)\}")


def bundled(language: str) -> dict:
    """web/i18n/<language>.json as shipped."""
    node = resources.files("jui_cli.viz") / "web" / "i18n" / f"{language}.json"
    return json.loads(node.read_text(encoding="utf-8"))


def slots(value) -> set:
    """The {name} slots a value uses (every form of a plural)."""
    texts = value.values() if isinstance(value, dict) else [value]
    return {m for text in texts if isinstance(text, str) for m in _SLOT.findall(text)}


def shape_problem(value, like) -> str | None:
    """Why ``value`` cannot stand for ``like`` (the bundled English words of the same key), or None."""
    if isinstance(like, dict):
        if not isinstance(value, dict) or not value or "other" not in value \
                or any(k not in PLURAL_FORMS or not isinstance(v, str) for k, v in value.items()):
            return 'needs {"one": ..., "other": ...} (a count changes these words)'
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
    #: the person's file, when one is named (resolved), and how many of its keys are used
    own_path: str = ""
    own_used: int = 0
    problems: list = field(default_factory=list)

    @property
    def locale(self) -> str:
        return "ja-JP" if self.language == "ja" else "en-US"


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
    if chosen not in LANGUAGES:
        out.problems.append(f'language "{chosen}" is not one of {", ".join(LANGUAGES)}; using {DEFAULT_LANGUAGE}')
        chosen = DEFAULT_LANGUAGE
    out.language = chosen
    if chosen != FALLBACK_LANGUAGE:
        out.table.update({k: v for k, v in bundled(chosen).items() if k in english})
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
        for key, value in data.items():
            if key not in english:
                out.problems.append(f'strings file: unknown key "{key}" left out')
                continue
            why = shape_problem(value, english[key])
            if why:
                out.problems.append(f'strings file: "{key}" {why}; left out')
                continue
            out.table[key] = value
            out.own_used += 1
    return out


def from_config(config) -> Strings:
    return load(getattr(config, "language", ""), getattr(config, "strings", ""))


def plural_form(n, language: str) -> str:
    """Intl.PluralRules' category for a whole count, for the bundled languages (Japanese: other only)."""
    return "one" if language == "en" and n == 1 else "other"


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
    blob = json.dumps({"language": strings.language, "locale": strings.locale, "strings": strings.table},
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return fill_words(html, strings).replace(LANG_SLOT, strings.language).replace(STRINGS_SLOT, blob)
