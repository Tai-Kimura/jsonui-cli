"""`visibleElements` and `displayLogic` element ids are checked against the LAYOUT.

Ticket doc-validate-spec-checks-visibleelements-against-nothing-when-layoutfile-is-set
(ee, 2026-09-25): `_validate_cross_references` returned at once for a spec with a
`layoutFile` — 86 of 93 specs with contracts across five faces — so an id the
layout does not have (a typo, a removed element) was never reported. Now the ids
come from `jui_cli.core.layout_facts` (includes expanded with their prefixes,
every platform), the reader the coverage data axis uses too; a sub-spec uses
its parent's layout. A WARNING, as the components-list check has always been.
When the layout cannot be read through (an include that does not resolve), it
says the ids were not checked.
"""
from __future__ import annotations

import json
from pathlib import Path

import re
import sys

import pytest

from jsonui_doc_cli.spec_doc import validator as validator_mod
from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _face(root: Path, *, visible, effect="summary", layout_extra=()):
    _write(root / "jui.config.json", {"spec_directory": "docs/screens/json",
                                      "layouts_directory": "docs/screens/layouts"})
    _write(root / "docs/screens/layouts/detail.json", {"type": "View", "id": "root", "child": [
        {"type": "Label", "id": "summary"}, {"include": "panel", "id": "side"},
        *layout_extra]})
    _write(root / "docs/screens/layouts/panel.json",
           {"type": "View", "id": "box", "child": [{"type": "Label", "id": "hint"}]})
    return _write(root / "docs/screens/json/detail.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Detail", "displayName": "Detail", "description": "d",
                     "layoutFile": "detail"},
        "stateManagement": {
            "states": [{"name": "mode", "values": [
                {"value": "view", "description": "d", "visibleElements": visible}]}],
            "displayLogic": [{"condition": "c", "effects": [{"element": effect, "state": "hidden"}]}]},
    })


def _messages(spec: Path):
    """(level, path, message) of every stateManagement message, in order."""
    result = SpecValidator().validate_file(spec)
    return [(m.level, m.path, m.message) for m in result.errors + result.warnings + result.infos
            if m.path.startswith("stateManagement")]


def _element_warnings(spec: Path):
    return [(p, m) for level, p, m in _messages(spec) if level == "warning"]


@pytest.fixture
def at(monkeypatch):
    """Run the validator as jsonui-cli *version*, the layout-id gate at *gate*."""
    def go(version, gate="1.8.120"):
        monkeypatch.setattr(validator_mod, "_running_version", lambda: version)
        monkeypatch.setattr(validator_mod, "LAYOUT_ID_GATE_FROM", gate)
    return go


NOTICE = "from jsonui-cli 1.8.120, spec element ids not in the layout become WARNING"
MISSING = ("Element 'sumary' not found in the layout detail.json (includes expanded, every "
           "platform)")


def test_ids_the_layout_has_including_prefixed_include_ids_pass(tmp_path, at):
    at("1.8.121")
    spec = _face(tmp_path, visible=["summary", "sideBox", "sideHint"])
    assert _messages(spec) == []


@pytest.mark.parametrize("version, level, announced", [
    ("1.8.119", "info", True),       # N: reported and announced, not a warning
    ("1.8.120", "warning", False),   # the release it names — the equal point
    ("1.8.121", "warning", False),
])
def test_an_id_the_layout_lacks_is_info_then_a_warning_from_the_release(
        tmp_path, at, version, level, announced):
    at(version)
    spec = _face(tmp_path, visible=["summary", "sumary"], effect="gone_element")
    messages = _messages(spec)
    assert (level, "stateManagement.states[0].values[0].visibleElements", MISSING) in messages
    assert any(lv == level and "gone_element" in m and "displayLogic[0].effects[0].element" in p
               for lv, p, m in messages), messages
    assert (("info", "stateManagement", NOTICE) in messages) is announced
    assert sum(1 for lv, *_ in messages if lv == "warning") == (0 if announced else 2)


@pytest.mark.parametrize("gate", ["withdrawn", "1.8", "next"])
def test_withdrawn_or_unreadable_never_warns_and_announces_nothing(tmp_path, at, gate):
    at("9.9.9", gate=gate)
    spec = _face(tmp_path, visible=["summary", "sumary"])
    messages = _messages(spec)
    assert ("info", "stateManagement.states[0].values[0].visibleElements", MISSING) in messages
    assert not any(lv == "warning" for lv, *_ in messages)
    assert not any("become WARNING" in m for *_, m in messages)


@pytest.mark.parametrize("spelling", ["hint", "side_hint"])
def test_an_include_ids_other_spellings_cannot_be_checked(tmp_path, at, spelling):
    # `hint` inside the include `side` is `sideHint` on native (what the
    # resolved layout holds), `side_hint` on UIKit, `hint` on web (it does not
    # flatten includes). Against one resolution only the first can be told
    # right; the others are CANNOT CHECK, not missing (ee, design v4.20).
    at("1.8.119")                      # below INCLUDE_ID_PREFIX_GATE_FROM
    spec = _face(tmp_path, visible=["summary", spelling])
    assert _messages(spec) == [(
        "info", "stateManagement",
        f"cannot check: 1 element id(s) inside includes of detail.json ({spelling}) — an "
        "include's ids are spelled differently per platform (web keeps the included "
        "layout's id; native prefixes it with the include's)")]


@pytest.mark.parametrize("version", ["1.8.120", "1.8.121"])     # 1.8.120: the equal point
@pytest.mark.parametrize("spelling", ["hint", "side_hint"])
def test_from_the_include_gate_an_include_ids_spelling_is_checked_exactly(tmp_path, at,
                                                                         version, spelling):
    # From INCLUDE_ID_PREFIX_GATE_FROM web spells it as native does (U8): the
    # web and UIKit spellings are mismatches, and the candidates name native's.
    at(version)
    spec = _face(tmp_path, visible=["summary", spelling])
    assert _element_warnings(spec) == [(
        "stateManagement.states[0].values[0].visibleElements",
        f"Element '{spelling}' not found in the layout detail.json (includes expanded, every "
        "platform); the layout has 'sideHint' — the runtime id is the layout's spelling")]


def test_a_withdrawn_include_gate_never_checks_them_exactly(tmp_path, at, monkeypatch):
    from jui_cli.core import layout_facts
    at("9.9.9")
    monkeypatch.setattr(layout_facts, "INCLUDE_ID_PREFIX_GATE_FROM", "withdrawn")
    spec = _face(tmp_path, visible=["summary", "hint"])
    assert [lv for lv, *_ in _messages(spec)] == ["info"]


def test_an_unresolved_include_says_it_cannot_check(tmp_path, at):
    at("1.8.121")
    spec = _face(tmp_path, visible=["anything"],
                 layout_extra=({"include": "does_not_exist", "id": "x"},))
    assert _messages(spec) == [(
        "info", "stateManagement",
        "cannot check: element ids against detail.json — an include does not resolve "
        "(does_not_exist), so its ids are unknown")]


def test_a_sub_spec_is_checked_against_its_parents_layout(tmp_path, at):
    at("1.8.121")
    _face(tmp_path, visible=["summary"])
    parent = tmp_path / "docs/screens/json/detail.spec.json"
    data = json.loads(parent.read_text())
    data["type"] = "screen_parent_spec"
    parent.write_text(json.dumps(data), encoding="utf-8")
    sub = _write(tmp_path / "docs/screens/json/detail/detail-part.spec.json", {
        "type": "screen_sub_spec", "version": "1.0",
        "metadata": {"name": "DetailPart", "displayName": "Part", "description": "d",
                     "parentSpec": "detail.spec.json"},
        "stateManagement": {"states": [{"name": "m", "values": [
            {"value": "v", "description": "d", "visibleElements": ["summary", "not_there"]}]}]},
    })
    warnings = _element_warnings(sub)
    assert [m for _, m in warnings] == [
        "Element 'not_there' not found in the layout detail.json (includes expanded, every platform)"]


def test_control_a_spec_without_a_layout_still_checks_its_components(tmp_path, at):
    at("1.8.119")      # the layout gate does not reach the components list
    spec = _write(tmp_path / "s.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "S", "displayName": "S", "description": "d"},
        "structure": {"components": [{"type": "View", "id": "root", "description": "d"}],
                      "layout": {"root": "root", "children": []}},
        "stateManagement": {"states": [{"name": "m", "values": [
            {"value": "v", "description": "d", "visibleElements": ["root", "missing"]}]}]},
    })
    assert [m for _, m in _element_warnings(spec)] == ["Element 'missing' not found in components list"]


def test_without_gate_versions_the_ids_are_still_checked_all_info(tmp_path, at, monkeypatch):
    # A tool tree without shared/core/gate_versions.py: nothing may become a
    # WARNING that was never announced (U5), and it says why — as INFO.
    at("1.8.121")
    load = validator_mod.shared_core.load
    monkeypatch.setattr(validator_mod.shared_core, "load",
                        lambda name: None if name == "gate_versions" else load(name))
    spec = _face(tmp_path, visible=["summary", "sumary"])
    messages = _messages(spec)
    assert ("info", "stateManagement.states[0].values[0].visibleElements", MISSING) in messages
    assert not any(lv == "warning" for lv, *_ in messages), messages
    assert ("info", "stateManagement",
            "the level of 1 element id(s) not in detail.json cannot be decided — "
            "shared/core/gate_versions.py is not in this tool tree; they are listed as "
            "INFO") in messages


class TestEveryPlatform:
    """"every platform" is the union of each platform's resolution: an id only
    a platform override gives a node was reported missing (the unfiltered
    tree never merges an override)."""

    OVERRIDE = {"type": "Label", "id": "base", "platform": {"ios": {"id": "iosOnly"}}}

    def test_an_id_only_an_override_gives_is_on_the_layout(self, tmp_path, at):
        at("1.8.121")
        spec = _face(tmp_path, visible=["summary", "iosOnly", "base"], layout_extra=(self.OVERRIDE,))
        assert _messages(spec) == []

    def test_boundary_an_id_in_neither_is_missing(self, tmp_path, at):
        at("1.8.121")
        spec = _face(tmp_path, visible=["androidOnly"], layout_extra=(self.OVERRIDE,))
        assert _element_warnings(spec) == [(
            "stateManagement.states[0].values[0].visibleElements",
            "Element 'androidOnly' not found in the layout detail.json (includes expanded, "
            "every platform)")]


class TestWhatIsNotAMissingId:
    CELL = {"type": "Collection", "id": "rows", "cellClasses": ["detail/row_cell"]}
    SECTION_CELL = {"type": "Collection", "id": "rows", "sections": [{"cell": "detail/row_cell"}]}

    @pytest.mark.parametrize("version, holder", [
        ("1.8.119", "cellClasses"), ("1.8.120", "cellClasses"), ("1.8.121", "cellClasses"),
        ("1.8.121", "sections")])
    def test_ids_inside_a_cell_are_one_info_count_in_every_version(self, tmp_path, at, version,
                                                                   holder):
        at(version)
        _write(tmp_path / "docs/screens/layouts/detail/row_cell.json",
               {"type": "View", "id": "cellRoot", "child": [{"type": "Label", "id": "cellTitle"}]})
        spec = _face(tmp_path, visible=["summary", "cellTitle", "cellRoot"],
                     effect="cellTitle",
                     layout_extra=(self.CELL if holder == "cellClasses" else self.SECTION_CELL,))
        assert _messages(spec) == [(
            "info", "stateManagement",
            "cannot check: 3 element id(s) inside cells of detail.json (cellRoot, cellTitle) — "
            "ids in cell layouts are not checked")]



class TestCandidates:
    """A spelling that matches only when folded is NOT a match (ee, design
    v4.20): the runtime id is the layout's spelling, on every platform and in
    every driver. The mismatch names what a person may have meant."""

    EXTRA = ({"type": "Toggle", "id": "sampleToggle"},
             {"type": "View", "id": "samplePanelView"},
             {"type": "View", "id": "samplePanelWrapper"},
             {"type": "View", "id": "side_sample_row"})

    @pytest.mark.parametrize("element, candidates", [
        ("sample_toggle", "'sampleToggle'"),                 # the same name, folded
        ("sample_panel", "'samplePanelView'"),           # its type after it
        ("sample_row", "'side_sample_row'"),   # after an include prefix
    ])
    @pytest.mark.parametrize("version, level", [("1.8.119", "info"), ("1.8.121", "warning")])
    def test_a_mismatch_names_its_candidates_at_the_missing_level(self, tmp_path, at, element,
                                                                 candidates, version, level):
        at(version)
        spec = _face(tmp_path, visible=["summary"], effect=element, layout_extra=self.EXTRA)
        assert (level, "stateManagement.displayLogic[0].effects[0].element",
                f"Element '{element}' not found in the layout detail.json (includes expanded, "
                f"every platform); the layout has {candidates} — the runtime id is the "
                "layout's spelling") in _messages(spec)

    def test_boundary_a_remainder_that_is_not_the_nodes_type_is_no_candidate(self, tmp_path, at):
        # `samplePanelWrapper` is a View: "wrapper" is not its type.
        at("1.8.121")
        spec = _face(tmp_path, visible=["summary"], effect="sample_panel",
                     layout_extra=(self.EXTRA[2],))
        assert _element_warnings(spec) == [(
            "stateManagement.displayLogic[0].effects[0].element",
            "Element 'sample_panel' not found in the layout detail.json (includes expanded, "
            "every platform)")]


def test_the_coverage_data_axis_gives_the_same_answer(tmp_path, at):
    """Both readers classify through `layout_facts.classify_element`: the
    validator's messages and the data axis's detail name the same ids with
    the same kinds and candidates."""
    at("1.8.121")
    from jsonui_test_cli import contracts_data_axis
    from jui_cli.core.layout_facts import cell_ids_for, layout_facts
    extra = ({"type": "Toggle", "id": "sampleToggle"},
             {"type": "Collection", "id": "rows", "cellClasses": ["detail/row_cell"]})
    _write(tmp_path / "docs/screens/layouts/detail/row_cell.json",
           {"type": "View", "id": "cellTitle"})
    spec = _face(tmp_path, visible=["summary", "sample_toggle", "cellTitle", "nowhere"],
                 layout_extra=extra)
    layouts = tmp_path / "docs/screens/layouts"
    data = json.loads(spec.read_text())
    facts = layout_facts(data, "ios", layouts_dir=layouts, styles_dir=layouts)
    axis = contracts_data_axis.screen_data(
        data, facts, [], cell_ids=cell_ids_for(facts, "ios", layouts_dir=layouts,
                                               styles_dir=layouts))
    by_axis = {o["id"]: (o["kind"], o["candidates"]) for o in axis.visible_ids_detail}
    assert by_axis == {"sample_toggle": ("missing", ["sampleToggle"]), "cellTitle": ("in_cell", []),
                       "nowhere": ("missing", [])}
    messages = [m for *_, m in _messages(spec)]
    assert any("'sample_toggle' not found" in m and "has 'sampleToggle'" in m for m in messages)
    assert any("'nowhere' not found" in m and "the layout has" not in m for m in messages)
    assert any(m.startswith("cannot check: 1 element id(s) inside cells") and "cellTitle" in m
               for m in messages)


class TestThePrintedReport:
    def test_info_is_printed_apart_and_not_counted(self, tmp_path, at, capsys):
        at("1.8.119")
        spec = _face(tmp_path, visible=["summary", "sumary"])
        data = json.loads(spec.read_text())      # a spec valid but for the id
        data["structure"] = {"components": [{"type": "View", "id": "root", "description": "d"}],
                             "layout": {"root": "root", "children": []}}
        spec.write_text(json.dumps(data), encoding="utf-8")
        from jsonui_doc_cli.cli import main
        import sys as _sys
        argv = _sys.argv
        try:
            _sys.argv = ["jsonui-doc", "validate", "spec", str(spec)]
            rc = main()
        finally:
            _sys.argv = argv
        out = capsys.readouterr().out
        assert rc == 0 and "Result: PASSED" in out
        assert "Errors: 0, Warnings: 0" in out and "Info: 2" in out
        assert f"  [INFO] stateManagement: {NOTICE}" in out
        # The agents' rulebook counts warnings with this expression (invariants.md);
        # an INFO line — even the one saying "become WARNING" — must not match it.
        rule = re.compile(r"warning \[|warning:|\[warn|⚠", re.I)
        assert [line for line in out.splitlines() if rule.search(line)] == []

    def test_the_batch_run_prints_and_totals_them(self, tmp_path, at, capsys):
        at("1.8.119")
        spec = _face(tmp_path, visible=["summary", "sumary"])
        from jsonui_doc_cli.cli import main
        argv = sys.argv
        try:
            sys.argv = ["jsonui-doc", "validate", "spec", str(spec.parent)]
            main()
        finally:
            sys.argv = argv
        out = capsys.readouterr().out
        assert f"  [INFO] stateManagement.states[0].values[0].visibleElements: {MISSING}" in out
        assert f"  [INFO] stateManagement: {NOTICE}" in out
        assert "Info: 2 (reported, not counted)" in out
        assert "Warnings: 0" in out
