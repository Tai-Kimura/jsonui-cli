"""The page's tl() says, once, on the console, a key the table lacks, a plural form it lacks, and a slot a call leaves
unfilled (ticket 2026-10-21-viz-english-screen-checks): each would read on the page as the key or as {name},
silently. The browser tests fail on any console warning (tools/viz_e2e/run.py check_watch), so every suite catches
one in Japanese and in English. A page without the server's table (debug.html) says nothing.

05-i18n.js's own functions, cut out and run in node with a stand-in table and console.
"""
from __future__ import annotations

from tests.test_viz_hist_card_off import _cut, _node

SAID = "const said = []; const console = { warn: (m) => said.push(m) };"
TABLE = ("const I18N = { served: true, strings: { 'a.hi': 'Hi {name}', 'a.n': { one: '{n} robot', other: '{n} robots' },"
         " 'a.few': { few: '{n}' }, 'a.code': 'Run `{cmd}`' } }; const PLURAL = new Intl.PluralRules('en-US');")
TL_ESC = "const TL_ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;', '\\x60': '&#96;' };"


def _parts(table: str = TABLE) -> list[str]:
    return [SAID, table, _cut("05-i18n.js", "TL_SAID"), *(_cut("05-i18n.js", f) for f in ("tlSay", "tlWords", "tlSlot", "tl")),
            TL_ESC, _cut("05-i18n.js", "TL_CODE"), _cut("05-i18n.js", "tlEsc"), _cut("05-i18n.js", "tlHTML")]


def test_words_found_and_filled_say_nothing():
    got = _node(_parts(), "[tl('a.hi', {name: 'Ann'}), tl('a.n', {n: 1}), tl('a.n', {n: 3}), tlHTML('a.code', {cmd: 'x'}), said]")
    assert got == ["Hi Ann", "1 robot", "3 robots", "Run <code>x</code>", []]


def test_a_key_the_table_lacks_is_itself_on_the_page_and_said_once():
    got = _node(_parts(), "[tl('panel.nope'), tl('panel.nope'), tlHTML('panel.nope'), said]")
    assert got == ["panel.nope", "panel.nope", "panel.nope", ["[viz i18n] no words for the key: panel.nope"]]


def test_a_slot_left_unfilled_is_said_with_its_key():
    got = _node(_parts(), "[tl('a.hi'), tlHTML('a.code', {}), said]")
    assert got == ["Hi {name}", "Run <code>{cmd}</code>",
                   ["[viz i18n] slot {name} not filled: a.hi", "[viz i18n] slot {cmd} not filled: a.code"]]


def test_a_plural_form_the_table_lacks_is_said():
    got = _node(_parts(), "[tl('a.few', {n: 2}), said]")
    assert got == ["a.few", ["[viz i18n] no plural form for the key: a.few"]]


def test_without_the_servers_table_nothing_is_said():
    table = TABLE.replace("served: true, ", "")
    assert _node(_parts(table), "[tl('panel.nope'), tl('a.hi'), said]") == ["panel.nope", "Hi {name}", []]
