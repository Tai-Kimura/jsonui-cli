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

