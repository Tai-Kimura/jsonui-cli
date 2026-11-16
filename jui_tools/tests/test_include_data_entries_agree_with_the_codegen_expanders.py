"""The data entries `jui verify` reads through an include are the ones sjui /
kjui put in the screen's Data type.

sjui and kjui build a screen's Data type from its layout with every include
expanded inline (data_model_updater_core.rb `expand_includes` ->
IncludeExpander.process_includes), each included entry named with the include
id as a camelCase prefix. `layout_data.data_entries_with_includes` reads a
layout through the normalizer's IncludeExpander, the Python port. One corpus
goes through all three and the ordered name lists must be equal — machine
against machine, not a transcription of the Ruby rule. Needs `ruby` (every CI
image carries it); without it the arm skips and says so.

The expander's own arms: an include it cannot expand is reported when the
caller asks, and a cycle is never cut silently.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from jui_cli.core.layout_data import data_entries_with_includes
from jui_cli.core.normalizer.include_expander import IncludeCycleError, IncludeExpander
from jui_cli.core.normalizer.style_merger import StyleMerger

REPO = Path(__file__).resolve().parents[2]
EXPANDERS = {
    "sjui": ("sjui_tools/lib", "swiftui/include_expander", "SjuiTools::SwiftUI::IncludeExpander"),
    "kjui": ("kjui_tools/lib", "compose/include_expander", "KjuiTools::Compose::IncludeExpander"),
    # rjui builds a screen's Data type from the include-expanded tree too,
    # from jsonui-cli 1.9.6 (ticket rjui-include-does-not-read-the-screens-data).
    "rjui": ("rjui_tools/lib", "react/include_expander", "RjuiTools::React::IncludeExpander"),
}

#: One screen and its partials: an include with an `_` id and a data list of
#: its own; one with no id; a nested include with an id (its own data list
#: too) beside one without; an id with a capital; an upper-case segment in an
#: entry name; `children` in place of `child`; a partial in a subdirectory.
CORPUS = {
    "screen": {"type": "View", "child": [
        {"data": [{"name": "own", "class": "String", "defaultValue": "o"}]},
        {"include": "parts/card", "id": "card_row",
         "data": [{"name": "extra_note", "class": "String", "defaultValue": "e"}]},
        {"include": "parts/plain"},
        {"include": "parts/outer", "id": "outer"},
        {"include": "parts/card", "id": "Side"},
    ]},
    "parts/card": {"type": "View", "child": [{"data": [
        {"name": "title_text", "class": "String", "defaultValue": "t"},
        {"name": "infoURL", "class": "String"}, {"name": "info_URL", "class": "String"}]}]},
    "parts/plain": {"type": "View", "data": [{"name": "plain_value", "class": "Int", "defaultValue": 1}]},
    "parts/outer": {"type": "View", "children": [
        {"data": [{"name": "head", "class": "String"}]},
        {"include": "parts/inner", "id": "inner", "data": [{"name": "note", "class": "String"}]},
        {"include": "parts/inner"}]},
    "parts/inner": {"type": "View", "child": [{"data": [{"name": "deep", "class": "String"}]}]},
}

RUBY = """
require 'json'
require '%(lib)s'
root = ARGV[0]
expanded = %(mod)s.process_includes(JSON.parse(File.read(File.join(root, 'screen.json'))), root, nil, root)
# data_model_updater_core.rb extract_data_properties' walk: `data` at any
# level, down `child` (process_includes has renamed `children`).
def names(node, out)
  return out unless node.is_a?(Hash)
  Array(node['data']).each { |d| out << d['name'] if d.is_a?(Hash) && d['name'] }
  child = node['child']
  (child.is_a?(Array) ? child : [child].compact).each { |c| names(c, out) }
  out
end
puts JSON.generate(names(expanded, []))
"""


def _write(root: Path, corpus: dict) -> None:
    for name, tree in corpus.items():
        path = root / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tree), encoding="utf-8")


def _python_names(root: Path) -> list:
    entries, unresolved = data_entries_with_includes(
        json.loads((root / "screen.json").read_text(encoding="utf-8")),
        layouts_root=root, styles_root=root / "styles", source=root / "screen.json")
    assert unresolved == []
    return [entry["name"] for entry, _ in entries]


def _ruby_names(tool: str, root: Path) -> list:
    lib, required, mod = EXPANDERS[tool]
    out = subprocess.run(["ruby", "-I", str(REPO / lib), "-e", RUBY % {"lib": required, "mod": mod},
                          str(root)], capture_output=True, text=True, check=True,
                         env={"LC_ALL": "en_US.UTF-8", "PATH": os.environ.get("PATH", "")})
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("ruby") is None, reason="ruby not installed — the codegen "
                    "expanders cannot be run here; the agreement is UNMEASURED")
@pytest.mark.parametrize("tool", sorted(EXPANDERS))
def test_the_entries_are_the_ones_codegen_expands(tmp_path, tool):
    _write(tmp_path, CORPUS)
    assert _python_names(tmp_path) == _ruby_names(tool, tmp_path)


def test_the_answers_are_the_codegen_spelling(tmp_path):
    """What the arm above agrees ON, so a change to both sides at once shows."""
    _write(tmp_path, CORPUS)
    assert _python_names(tmp_path) == [
        "own", "cardRowExtraNote", "cardRowTitleText", "cardRowInfoURL", "cardRowInfoUrl",
        "plain_value", "outerHead", "outerInnerOuterNote", "outerInnerDeep", "outerDeep",
        "SideTitleText", "SideInfoURL", "SideInfoUrl"]


def test_each_entry_names_the_include_that_declares_it(tmp_path):
    _write(tmp_path, CORPUS)
    entries, _ = data_entries_with_includes(
        json.loads((tmp_path / "screen.json").read_text(encoding="utf-8")),
        layouts_root=tmp_path, styles_root=tmp_path / "styles")
    by_name = {entry["name"]: declared_in for entry, declared_in in entries}
    # The include node's own list is declared where the node is written.
    assert by_name["own"] is None and by_name["cardRowExtraNote"] is None
    assert by_name["cardRowTitleText"] == "parts/card"
    assert by_name["outerInnerOuterNote"] == "parts/outer"
    assert by_name["outerInnerDeep"] == "parts/inner"
    assert all("$jui.declaredIn" not in entry for entry, _ in entries)


# ---- what the expander cannot expand ------------------------------------------

def _expander(root: Path) -> IncludeExpander:
    return IncludeExpander(root, StyleMerger(root / "styles"))


def test_a_cycle_raises_naming_the_chain_unless_the_caller_collects_it(tmp_path):
    _write(tmp_path, {"a": {"type": "View", "child": [{"include": "b", "id": "x"}]},
                      "b": {"type": "View", "child": [{"include": "a", "id": "y"}]}})
    tree = {"type": "View", "child": [{"include": "a"}]}
    with pytest.raises(IncludeCycleError) as raised:
        _expander(tmp_path).expand(json.loads(json.dumps(tree)))
    assert str(raised.value) == "include cycle: a -> b -> a"
    unresolved: list = []
    _expander(tmp_path).expand(json.loads(json.dumps(tree)), unresolved=unresolved)
    assert unresolved == [("a", "cycle")]


def test_one_partial_side_by_side_is_not_a_cycle(tmp_path):
    """A cycle is an include of a file the node is INSIDE, not one seen
    before: the same partial twice in one screen is expanded twice."""
    _write(tmp_path, {"p": {"type": "View", "data": [{"name": "v", "class": "Int", "defaultValue": 1}]}})
    unresolved: list = []
    entries, unresolved = data_entries_with_includes(
        {"type": "View", "child": [{"include": "p", "id": "one"}, {"include": "p", "id": "two"}]},
        layouts_root=tmp_path, styles_root=tmp_path / "styles")
    assert [e["name"] for e, _ in entries] == ["oneV", "twoV"] and unresolved == []


def test_a_missing_or_unreadable_include_is_reported_and_left_out(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "listed.json").write_text("[]", encoding="utf-8")
    entries, unresolved = data_entries_with_includes(
        {"type": "View", "child": [
            {"data": [{"name": "kept", "class": "Int", "defaultValue": 0}]},
            {"include": "absent", "id": "a"}, {"include": "broken"}, {"include": "listed"}]},
        layouts_root=tmp_path, styles_root=tmp_path / "styles")
    assert [e["name"] for e, _ in entries] == ["kept"]
    assert unresolved == [("absent", "not found"), ("broken", "unreadable"), ("listed", "unreadable")]
