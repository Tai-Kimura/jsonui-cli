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


def _element_warnings(spec: Path):
    result = SpecValidator().validate_file(spec)
    return [(w.path, w.message) for w in result.warnings
            if w.path.startswith("stateManagement")]


def test_ids_the_layout_has_including_prefixed_include_ids_pass(tmp_path):
    spec = _face(tmp_path, visible=["summary", "sideBox", "sideHint"])
    assert _element_warnings(spec) == []


def test_an_id_the_layout_lacks_is_named(tmp_path):
    spec = _face(tmp_path, visible=["summary", "sumary"], effect="gone_element")
    warnings = _element_warnings(spec)
    assert ("stateManagement.states[0].values[0].visibleElements",
            "Element 'sumary' not found in the layout detail.json (includes expanded, every "
            "platform)") in warnings
    assert any("gone_element" in m and "displayLogic[0].effects[0].element" in p
               for p, m in warnings), warnings


def test_the_unprefixed_include_id_is_not_the_layouts(tmp_path):
    # The include's own id `hint` becomes `sideHint` in the screen: the same
    # prefixing the runtime and the normalizer apply.
    spec = _face(tmp_path, visible=["hint"])
    assert any("'hint' not found in the layout" in m for _, m in _element_warnings(spec))


def test_an_unresolved_include_says_it_did_not_check(tmp_path):
    spec = _face(tmp_path, visible=["anything"],
                 layout_extra=({"include": "does_not_exist", "id": "x"},))
    warnings = _element_warnings(spec)
    assert len(warnings) == 1 and "were not checked against detail.json" in warnings[0][1]
    assert "does_not_exist" in warnings[0][1]


def test_a_sub_spec_is_checked_against_its_parents_layout(tmp_path):
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


def test_control_a_spec_without_a_layout_still_checks_its_components(tmp_path):
    spec = _write(tmp_path / "s.spec.json", {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "S", "displayName": "S", "description": "d"},
        "structure": {"components": [{"type": "View", "id": "root", "description": "d"}],
                      "layout": {"root": "root", "children": []}},
        "stateManagement": {"states": [{"name": "m", "values": [
            {"value": "v", "description": "d", "visibleElements": ["root", "missing"]}]}]},
    })
    assert [m for _, m in _element_warnings(spec)] == ["Element 'missing' not found in components list"]
