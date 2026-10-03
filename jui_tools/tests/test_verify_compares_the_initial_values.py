"""`jui verify` compares the initial values a spec declares with its layout's.

A uiVariable's `default` / `defaultValue` (default wins) against the data
entry of the same name in the layout verify resolves for the spec — wherever
the layout declares `data`, as the platform tools read it — and a Collection
entry's uiVariables against the layout its section names. One line per value
the layout does not carry: the variable, both values, both files. Reported,
not counted by --fail-on-diff. Externally authored layouts are compared too:
their data section is still the spec's to declare.

Until jsonui-cli 1.9.0 nothing compared them — the data check read entry names, in one
direction, from the root `data` only, so on a layout keeping its data in a
child (the hand-written form) it read nothing at all. Measured 2026-09-26 on
three faces: 37 values not carried, 8 of them given another value.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path

import pytest

from jui_cli.commands.verify_cmd import cmd_verify


@pytest.fixture(autouse=True)
def _runs_as_the_release_before_the_gate(monkeypatch):
    """Every arm here runs as jsonui-cli 1.9.0, the release before
    INITIAL_VALUE_GATE_FROM: an arm about the announced line reads the
    toolchain's version against the gate, so a tree stamped with the gate's
    release (run-suites' next-stamp leg, 1.9.1) turned two of them red. The
    arm about the switch moves the gate, not the version."""
    monkeypatch.setattr("jui_cli.version.toolchain_version", lambda root=None: "1.9.0")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    _write(tmp_path / "jui.config.json", {
        "spec_directory": "specs", "layouts_directory": "layouts", "platforms": {"ios": {"root": "ios"}}})
    (tmp_path / "layouts").mkdir()
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(cwd)


def _verify(fail_on_diff=False) -> tuple[int, str]:
    out = io.StringIO()
    args = argparse.Namespace(file=None, detail=False, fail_on_diff=fail_on_diff, platform=None, json_out=None)
    with contextlib.redirect_stdout(out):
        rc = cmd_verify(args)
    return rc, out.getvalue()


def _external(project: Path, variables: list[dict], data_node: dict, collection: dict | None = None,
              data_in_child: bool = True) -> None:
    """A spec whose layout is authored elsewhere (layoutFile, no components)."""
    structure = {"components": [], "layout": {}}
    if collection:
        structure["collection"] = collection
    _write(project / "specs/home.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d", "layoutFile": "home"},
        "structure": structure, "stateManagement": {"uiVariables": variables}})
    layout = ({"type": "View", "child": [data_node, {"type": "Label", "id": "title"}]} if data_in_child
              else {"type": "View", **data_node, "child": [{"type": "Label", "id": "title"}]})
    _write(project / "layouts/home.json", layout)


def _var(name, type_, **given):
    return {"name": name, "type": type_, "description": "d", **given}


def test_a_value_the_layout_gives_differently_is_named_with_both_values_and_both_files(project):
    _external(project, [_var("releaseIndex", "Int", defaultValue=0)],
              {"data": [{"name": "releaseIndex", "class": "Int", "defaultValue": "-1"}]})
    rc, said = _verify()
    assert "**WARNING: 1 initial value(s) a spec declares that its layout does not carry**" in said, said
    assert ("- specs/home.spec.json: stateManagement.uiVariables 'releaseIndex' is 0 — layouts/home.json "
            "has \"-1\"") in said, said
    assert rc == 0


@pytest.mark.parametrize("type_,spec_value,layout_value", [
    ("Int", "0", 0), ("Int", 0, "0"), ("Bool", "false", False), ("Bool", True, "true"),
    ("String", "", "''"), ("Array", [], "[]"), ("Double", 1, 1.0), ("String", "gone", "gone"),
], ids=["int string", "int", "bool string", "bool", "empty string shorthand", "array literal",
        "double", "same"])
def test_two_spellings_of_one_value_agree(project, type_, spec_value, layout_value):
    _external(project, [_var("v", type_, defaultValue=spec_value)],
              {"data": [{"name": "v", "class": type_, "defaultValue": layout_value}]})
    assert "initial value(s)" not in _verify()[1]


@pytest.mark.parametrize("type_,spec_value,layout_value", [
    ("String", "0", 0), ("String", "register", "screen_register"), ("Int", 0, 1),
], ids=["a String is not the number", "another string", "another number"])
def test_two_values_do_not_agree(project, type_, spec_value, layout_value):
    _external(project, [_var("v", type_, defaultValue=spec_value)],
              {"data": [{"name": "v", "class": type_, "defaultValue": layout_value}]})
    assert "1 initial value(s)" in _verify()[1]


def test_an_entry_without_a_default_value_and_a_missing_entry_are_named(project):
    _external(project, [_var("a", "String", defaultValue="x"), _var("b", "String", default="y")],
              {"data": [{"name": "a", "class": "String"}]})
    said = _verify()[1]
    assert "'a' is \"x\" — layouts/home.json gives it no defaultValue" in said, said
    assert "'b' is \"y\" — layouts/home.json declares no data entry 'b'" in said, said


def test_a_null_or_absent_value_declares_nothing(project):
    _external(project, [_var("a", "String", defaultValue=None), _var("b", "String")], {"data": []})
    assert "initial value(s)" not in _verify()[1]


def test_root_data_is_read_too(project):
    _external(project, [_var("v", "Int", defaultValue=3)],
              {"data": [{"name": "v", "class": "Int", "defaultValue": 4}]}, data_in_child=False)
    assert "'v' is 3 — layouts/home.json has 4" in _verify()[1]


def test_a_cells_values_are_compared_with_its_layout(project):
    _external(project, [], {"data": []}, collection={"id": "items", "cell": {
        "root": "cell_root", "layoutFile": "home/cell",
        "uiVariables": [_var("title", "String", defaultValue="t")]}})
    _write(project / "layouts/home/cell.json",
           {"type": "View", "id": "cell_root", "child": [{"data": [{"name": "title", "class": "String",
                                                                     "defaultValue": "u"}]}]})
    assert ("structure.collection.cell.uiVariables 'title' is \"t\" — layouts/home/cell.json has \"u\""
            in _verify()[1])


def test_fail_on_diff_does_not_count_them(project):
    _external(project, [_var("v", "Int", defaultValue=0)], {"data": [{"name": "v", "class": "Int",
                                                                      "defaultValue": 1}]})
    rc, said = _verify(fail_on_diff=True)
    assert "1 initial value(s)" in said and rc == 0


def test_a_data_orphan_in_a_child_data_section_is_reported(project):
    """The existing orphan check on a spec-generated layout — its entries read
    wherever the layout declares them."""
    _write(project / "specs/home.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d"},
        "structure": {"components": [{"id": "title", "type": "Label", "description": "t"}],
                      "layout": {"root": "root", "children": ["title"]}},
        "stateManagement": {"uiVariables": []}})
    _write(project / "layouts/home.json", {"type": "View", "child": [
        {"data": [{"name": "handWritten", "class": "String"}]}, {"type": "Label", "id": "title"}]})
    said = _verify()[1]
    assert "data.handWritten (String)" in said, said


# ---- a strings key stands for its text --------------------------------------

def _strings(project: Path, table: dict) -> None:
    _write(project / "layouts/Resources/strings.json", table)


@pytest.mark.parametrize("table,spec_value,layout_value", [
    ({"home": {"title": "Hello"}}, "Hello", "home_title"),
    ({"home": {"title": "Hello"}}, "title", "home_title"),
    ({"home": {"title": {"en": "Hello", "ja": "こんにちは"}}}, "こんにちは", "home_title"),
    ({"home": {"title": "Hello"}}, "home_title", "Hello"),
], ids=["a full key and its text", "the bare key and the full key of one entry", "a language's text",
        "the spec holds the key"])
def test_a_strings_key_and_its_text_agree(project, table, spec_value, layout_value):
    _strings(project, table)
    _external(project, [_var("v", "String", defaultValue=spec_value)],
              {"data": [{"name": "v", "class": "String", "defaultValue": layout_value}]})
    assert "initial value(s)" not in _verify()[1]


def test_a_key_that_stands_for_another_text_is_named_with_it(project):
    _strings(project, {"home": {"title": "Hello"}})
    _external(project, [_var("v", "String", defaultValue="Bye")],
              {"data": [{"name": "v", "class": "String", "defaultValue": "home_title"}]})
    assert "'v' is \"Bye\" — layouts/home.json has \"home_title\" (strings: \"Hello\")" in _verify()[1]


def test_a_bare_key_of_a_section_the_layout_does_not_own_is_not_a_key(project):
    _strings(project, {"other": {"title": "Hello"}})
    _external(project, [_var("v", "String", defaultValue="Hello")],
              {"data": [{"name": "v", "class": "String", "defaultValue": "title"}]})
    assert "has \"title\"" in _verify()[1]


# ---- the release --fail-on-diff counts them from ----------------------------

def test_the_count_starts_in_a_named_release():
    from jui_cli.commands import verify_cmd
    assert verify_cmd.INITIAL_VALUE_GATE_FROM == "1.9.1"
    assert verify_cmd.initial_value_gate_state(version="1.9.0") == "announce"
    assert verify_cmd.initial_value_gate_state(version="1.9.1") == "on"
    assert verify_cmd.initial_value_gate_state(version="1.9.0", literal="withdrawn") == "off"


def test_the_line_names_the_release_and_the_gate_counts_from_it(project, monkeypatch):
    from jui_cli.commands import verify_cmd
    _external(project, [_var("v", "Int", defaultValue=0)],
              {"data": [{"name": "v", "class": "Int", "defaultValue": 1}]})
    rc, said = _verify(fail_on_diff=True)
    assert rc == 0 and "from jsonui-cli 1.9.1 `--fail-on-diff` counts these" in said, said
    monkeypatch.setattr(verify_cmd, "INITIAL_VALUE_GATE_FROM", "0.0.1")
    rc, said = _verify(fail_on_diff=True)
    assert rc == 1 and "(counted by `--fail-on-diff`)" in said, said
    monkeypatch.setattr(verify_cmd, "INITIAL_VALUE_GATE_FROM", "withdrawn")
    rc, said = _verify(fail_on_diff=True)
    assert rc == 0 and "`--fail-on-diff` does not count these" in said, said



# ---- an include's entries, under the include id's prefix ---------------------
#
# sjui / kjui expand an include into the screen before they read its data
# (data_model_updater_core.rb `expand_includes`): the included layout's entries
# are the screen's Data properties, named with the include id as a camelCase
# prefix. Until jsonui-cli 1.9.1 this check did not open an include, and a spec
# declaring the prefixed name was told the layout declares no such entry.

def _screen_with(project: Path, variables: list[dict], child: list) -> None:
    """An externally authored screen whose layout is *child* (plus a label)."""
    _write(project / "specs/home.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d", "layoutFile": "home"},
        "structure": {"components": [], "layout": {}}, "stateManagement": {"uiVariables": variables}})
    _write(project / "layouts/home.json",
           {"type": "View", "child": [*child, {"type": "Label", "id": "title_label"}]})


def _part(project: Path, name: str, tree: dict) -> None:
    _write(project / f"layouts/{name}.json", tree)


def _card(project: Path) -> None:
    _part(project, "parts/card", {"type": "View", "child": [
        {"data": [{"name": "title", "class": "String", "defaultValue": ""},
                  {"name": "item_count", "class": "Int", "defaultValue": 0}]},
        {"type": "Label", "id": "card_label", "text": "@{title}"}]})


def test_an_includes_entry_is_read_under_the_include_ids_prefix(project):
    _card(project)
    _screen_with(project, [_var("cardTitle", "String", defaultValue=""),
                           _var("cardItemCount", "Int", defaultValue=0)],
                 [{"include": "parts/card", "id": "card"}])
    said = _verify()[1]
    assert "initial value(s)" not in said, said


def test_an_includes_entry_with_another_value_is_still_named(project):
    _card(project)
    _screen_with(project, [_var("cardTitle", "String", defaultValue="x")],
                 [{"include": "parts/card", "id": "card"}])
    said = _verify()[1]
    assert ("- specs/home.spec.json: stateManagement.uiVariables 'cardTitle' is \"x\" — "
            "layouts/home.json has \"\" (in include 'parts/card')") in said, said


def test_the_raw_name_inside_an_include_with_an_id_is_not_a_screen_entry(project):
    """`title` is `cardTitle` in the screen's Data type — the unprefixed name
    is not there on iOS or Android."""
    _card(project)
    _screen_with(project, [_var("title", "String", defaultValue="")],
                 [{"include": "parts/card", "id": "card"}])
    assert "'title' is \"\" — layouts/home.json declares no data entry 'title'" in _verify()[1]


def test_an_include_without_an_id_adds_no_prefix(project):
    """No prefix, and so no camelCase either: `item_count` stays as written."""
    _card(project)
    _screen_with(project, [_var("title", "String", defaultValue=""),
                           _var("item_count", "Int", defaultValue=3)],
                 [{"include": "parts/card"}])
    said = _verify()[1]
    assert "'title'" not in said, said
    assert "'item_count' is 3 — layouts/home.json has 0 (in include 'parts/card')" in said, said


def test_a_nested_include_takes_both_prefixes(project):
    """`header` inside `card`: the inner entry is `cardHeaderCaption`; an
    include without an id inside it passes `card` on."""
    _part(project, "parts/header", {"type": "View", "data": [
        {"name": "caption", "class": "String", "defaultValue": "c"}]})
    _part(project, "parts/card", {"type": "View", "child": [
        {"include": "parts/header", "id": "header"}, {"include": "parts/header"}]})
    _screen_with(project, [_var("cardHeaderCaption", "String", defaultValue="c"),
                           _var("cardCaption", "String", defaultValue="other")],
                 [{"include": "parts/card", "id": "card"}])
    said = _verify()[1]
    assert "'cardHeaderCaption'" not in said, said
    assert ("'cardCaption' is \"other\" — layouts/home.json has \"c\" (in include "
            "'parts/header')") in said, said


def test_an_include_nodes_own_data_takes_its_prefix(project):
    _card(project)
    _screen_with(project, [_var("cardNote", "String", defaultValue="n")],
                 [{"include": "parts/card", "id": "card",
                   "data": [{"name": "note", "class": "String", "defaultValue": "n"}]}])
    assert "initial value(s)" not in _verify()[1]


def test_a_missing_include_does_not_stop_the_check_and_is_named(project):
    """The tools stop the build ("Include file not found"). verify compares
    what it can read, and a variable it did not find names the include it
    could not read — counted, not excused: the value is not shown carried."""
    _screen_with(project, [_var("goneTitle", "String", defaultValue=""),
                           _var("own", "Int", defaultValue=1)],
                 [{"data": [{"name": "own", "class": "Int", "defaultValue": 2}]},
                  {"include": "parts/gone", "id": "gone"}])
    rc, said = _verify()
    assert "'own' is 1 — layouts/home.json has 2" in said, said
    assert ("'goneTitle' is \"\" — layouts/home.json declares no data entry 'goneTitle' — "
            "include(s) not read: 'parts/gone' (not found)") in said, said
    assert "2 initial value(s)" in said and rc == 0, said


def test_an_include_cycle_does_not_stop_the_check_and_is_named(project):
    _part(project, "parts/loop_a", {"type": "View", "child": [
        {"data": [{"name": "title", "class": "String", "defaultValue": "a"}]},
        {"include": "parts/loop_b", "id": "next"}]})
    _part(project, "parts/loop_b", {"type": "View", "child": [
        {"include": "parts/loop_a", "id": "back"}]})
    _screen_with(project, [_var("loopTitle", "String", defaultValue="a"),
                           _var("loopNextBackTitle", "String", defaultValue="a")],
                 [{"include": "parts/loop_a", "id": "loop"}])
    said = _verify()[1]
    assert "'loopTitle'" not in said, said
    assert ("'loopNextBackTitle' is \"a\" — layouts/home.json declares no data entry "
            "'loopNextBackTitle' — include(s) not read: 'parts/loop_a' (cycle)") in said, said


def test_a_layout_including_itself_is_a_cycle_at_the_first_step(project):
    """The file verify read is one the include is inside: it is not expanded
    once more first, so its own entry is not also there as `selfOwn`."""
    _screen_with(project, [_var("selfOwn", "Int", defaultValue=1)],
                 [{"data": [{"name": "own", "class": "Int", "defaultValue": 1}]},
                  {"include": "home", "id": "self"}])
    said = _verify()[1]
    assert ("'selfOwn' is 1 — layouts/home.json declares no data entry 'selfOwn' — "
            "include(s) not read: 'home' (cycle)") in said, said


def test_a_value_nothing_carries_is_still_named_beside_includes(project):
    """Control: following includes adds the entries they carry and nothing
    else — a name no file declares is reported as before, with no note."""
    _card(project)
    _screen_with(project, [_var("cardSubtitle", "String", defaultValue="")],
                 [{"include": "parts/card", "id": "card"}])
    said = _verify()[1]
    assert ("'cardSubtitle' is \"\" — layouts/home.json declares no data entry 'cardSubtitle'\n"
            in said), said


def test_the_data_orphan_check_does_not_open_an_include(project):
    """The orphan check reads the file regeneration writes: an entry an
    included layout declares is not that file's to drop (layout_data)."""
    _card(project)
    _write(project / "specs/home.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d"},
        "structure": {"components": [{"id": "title_label", "type": "Label", "description": "t"}],
                      "layout": {"root": "root", "children": ["title_label"]}},
        "stateManagement": {"uiVariables": []}})
    _write(project / "layouts/home.json", {"type": "View", "child": [
        {"include": "parts/card", "id": "card"}, {"type": "Label", "id": "title_label"}]})
    said = _verify()[1]
    assert "data-section entries not declared" not in said, said


# ---- two spellings the platform tools do NOT emit as one value ----------------
#
# Measured on jsonui-cli 1.9.0 (53ddb54d) by generating each tool's Data model
# from one layout (sjui / kjui / rjui data model updaters, Ruby 3.3.1):
#
#   class CollectionDataSource   sjui                        kjui                      rjui
#   "CollectionDataSource()"     = CollectionDataSource()    = CollectionDataSource()  new CollectionDataSource()
#   "[]"                         = []                        = CollectionDataSource()  []
#   (no defaultValue)            ? = nil                     ? = null                  undefined
#   class [OptionRow], none      ? = nil                     ? = null                  undefined
#
# sjui's `= []` is not a CollectionDataSource (SwiftJsonUI declares no array
# literal for it) and rjui's `[]` is a plain array, so the two spellings are
# one value on one platform of three; and an entry with no defaultValue starts
# as nil / null / undefined on all three, not as an empty list. Both stay
# reported until the tools agree.

def test_an_empty_data_source_and_an_empty_list_are_not_one_value(project):
    _external(project, [_var("options", "Array(OptionRow)", defaultValue="[]")],
              {"data": [{"name": "options", "class": "CollectionDataSource",
                         "defaultValue": "CollectionDataSource()"}]})
    assert "'options' is \"[]\" — layouts/home.json has \"CollectionDataSource()\"" in _verify()[1]


@pytest.mark.parametrize("klass", ["[OptionRow]", "CollectionDataSource"])
def test_an_entry_without_a_default_value_does_not_carry_an_empty_list(project, klass):
    _external(project, [_var("options", "Array(OptionRow)", defaultValue=[])],
              {"data": [{"name": "options", "class": klass}]})
    assert "'options' is [] — layouts/home.json gives it no defaultValue" in _verify()[1]


def _without_gate_versions(monkeypatch):
    from jui_cli.core import shared_core
    load = shared_core.load
    monkeypatch.setattr(shared_core, "load", lambda name: None if name == "gate_versions" else load(name))


def test_without_gate_versions_fail_on_diff_fails_on_them_and_says_why(project, monkeypatch):
    # A tree without shared/core/gate_versions.py cannot say whether
    # --fail-on-diff counts them. Until jsonui-cli 1.9.8 the state was "off"
    # and they were "reported only" — the gate silently off (ticket
    # gate-readers-without-shared-core-fall-silent-five-more).
    from jui_cli.commands.verify_cmd import INITIAL_VALUE_GATE_UNREADABLE
    _without_gate_versions(monkeypatch)
    _external(project, [_var("v", "Int", defaultValue=0)], {"data": [{"name": "v", "class": "Int",
                                                                      "defaultValue": 1}]})
    rc, said = _verify(fail_on_diff=True)
    assert rc == 1, said
    assert INITIAL_VALUE_GATE_UNREADABLE in said
    assert _verify(fail_on_diff=False)[0] == 0          # without the flag verify never fails


def test_without_gate_versions_agreeing_values_still_pass(project, monkeypatch):
    # The control: nothing differs, so the gate decides nothing.
    _without_gate_versions(monkeypatch)
    _external(project, [_var("v", "Int", defaultValue=1)], {"data": [{"name": "v", "class": "Int",
                                                                      "defaultValue": 1}]})
    rc, said = _verify(fail_on_diff=True)
    assert rc == 0, said
