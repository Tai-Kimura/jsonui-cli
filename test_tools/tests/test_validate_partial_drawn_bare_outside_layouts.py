"""An id of a partial the layouts include only under an include id, named bare.

The layouts show the partial's ids only prefixed (`autofillSourceTabsTab1Button`),
so validate leaves its bare ids out of the union: that is web's old spelling of
an id inside an include. Code outside the layouts may draw the same partial
without an id prefix (a hand-written component rendering the generated
`TabStrip`), and there the bare id is the runtime one — 15 WARNINGs on one
project for tests that pass (ticket
jsonui-test-validate-unprefixed-ids-of-partial-included-with-id-elsewhere).

Validate cannot tell the two apart from the layouts, so: a test none of whose
layouts include the partial counts the bare id CANNOT CHECK, naming the
partial; a test whose layout includes it (at any depth, under an include id)
and a test that names no layout keep the WARNING. The count shows in the
summary's "cannot check".
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

import jsonui_test_cli
from jsonui_test_cli.validation import element_ids
from jsonui_test_cli.validation.screen_ids import _prefer_sibling_jui_cli
from jsonui_test_cli.validator import TestValidator as Validator

_prefer_sibling_jui_cli()
element_ids.layout_id_gate_from()
from jsonui_doc_cli.spec_doc import validator as spec_validator  # noqa: E402

TAB_STRIP = {"type": "View", "id": "tab_strip", "child": [
    {"type": "Button", "id": "tab_1_button"}, {"type": "View", "id": "tab_1_underline"}]}
WITH_ID = {"type": "View", "id": "panel_root", "child": [
    {"include": "common/tab_strip", "id": "autofill_source_tabs"}]}
# A screen that draws the strip from hand-written code: nothing in its layout.
FRAME = {"type": "View", "id": "frame_root", "child": [{"type": "Label", "id": "frame_title"}]}


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def gate(monkeypatch):
    from jui_cli.core import layout_facts
    monkeypatch.setattr(jsonui_test_cli, "__version__", "9.0.0")
    monkeypatch.setattr(spec_validator, "LAYOUT_ID_GATE_FROM", "1.8.120")
    monkeypatch.setattr(layout_facts, "INCLUDE_ID_PREFIX_GATE_FROM", "1.8.120")
    yield
    element_ids.set_run_project()


def _project(root: Path, layouts: dict) -> None:
    cfg = _write(root / "jui.config.json", {"layouts_directory": "docs/layouts"})
    _write(root / "docs/layouts/common/tab_strip.json", TAB_STRIP)
    for name, tree in layouts.items():
        _write(root / f"docs/layouts/{name}.json", tree)
    element_ids.set_run_project(json.loads(cfg.read_text()), cfg)


def _screen(root: Path, layout: str | None, ids) -> Path:
    steps = [{"action": "tap", "id": i} for i in ids]
    data = {"type": "screen", "metadata": {"name": "s"},
            "cases": [{"name": "c", "description": "d", "steps": steps}]}
    if layout is not None:
        # From the project root, as the reporting project writes it.
        data["source"] = {"layout": f"docs/layouts/{layout}.json"}
    return _write(root / "tests/s.test.json", data)


def _flow(root: Path, layouts, ids) -> Path:
    return _write(root / "tests/f.test.json", {
        "type": "flow", "metadata": {"name": "f"},
        # From the test file, as the conformance fixtures write it.
        "sources": [{"layout": f"../docs/layouts/{n}.json"} for n in layouts],
        "steps": [{"action": "tap", "id": i} for i in ids]})


def _run(path: Path):
    with contextlib.redirect_stdout(io.StringIO()):
        result = Validator().validate_file(path)
    missing = [m.message for m in result.warnings if " is on no layout" in m.message]
    cannot = [m.message for m in result.infos if m.message.startswith("cannot check:")]
    return result, missing, cannot


BARE = ["tab_strip", "tab_1_button", "tab_1_underline"]


def test_the_reported_shape_counts_the_bare_ids_cannot_check_naming_the_partial(tmp_path, gate):
    _project(tmp_path, {"common/panel": WITH_ID, "frame": FRAME})
    result, missing, cannot = _run(_screen(tmp_path, "frame", BARE))
    assert missing == []
    assert len(cannot) == 1 and "3 element id(s) (tab_1_button, tab_1_underline, tab_strip)" in cannot[0]
    assert "common/tab_strip" in cannot[0] and "without an id prefix" in cannot[0]
    # The summary's "cannot check" carries them: not silently zero.
    assert result.element_ids["cannot_check"] == 3 and result.element_ids["missing"] == 0


def test_a_test_whose_layout_includes_the_partial_under_an_id_keeps_the_warning(tmp_path, gate):
    # Web's old spelling of an id inside the include: what the gate is for.
    _project(tmp_path, {"panel": WITH_ID})
    result, missing, cannot = _run(_screen(tmp_path, "panel", ["tab_1_button"]))
    assert len(missing) == 1 and "autofillSourceTabsTab1Button" in missing[0]
    assert cannot == [] and result.element_ids["missing"] == 1


def test_a_layout_that_includes_it_deeper_under_an_id_keeps_the_warning(tmp_path, gate):
    # screen > outer (no id) > tab_strip (id), and screen > outer (id) > tab_strip (id).
    for outer_id in (None, "panel"):
        include = {"include": "common/outer", **({"id": outer_id} if outer_id else {})}
        _project(tmp_path, {
            "screen": {"type": "View", "id": "root", "child": [include]},
            "common/outer": {"type": "View", "id": "outer_box", "child": [
                {"include": "common/tab_strip", "id": "inner_tabs"}]},
            "frame": FRAME})
        _, missing, cannot = _run(_screen(tmp_path, "screen", ["tab_1_button"]))
        assert len(missing) == 1 and cannot == [], outer_id
        # The same id from a screen that does not include the strip.
        _, missing, cannot = _run(_screen(tmp_path, "frame", ["tab_1_button"]))
        assert missing == [] and len(cannot) == 1, outer_id
        element_ids.set_run_project()


def test_a_test_that_names_no_layout_keeps_the_warning(tmp_path, gate):
    _project(tmp_path, {"common/panel": WITH_ID, "frame": FRAME})
    _, missing, cannot = _run(_screen(tmp_path, None, ["tab_1_button"]))
    assert len(missing) == 1 and cannot == []


def test_a_flow_is_judged_by_every_layout_it_names(tmp_path, gate):
    _project(tmp_path, {"panel": WITH_ID, "frame": FRAME})
    _, missing, cannot = _run(_flow(tmp_path, ["frame"], ["tab_1_button"]))
    assert missing == [] and len(cannot) == 1
    _, missing, cannot = _run(_flow(tmp_path, ["frame", "panel"], ["tab_1_button"]))
    assert len(missing) == 1 and cannot == []


def test_an_id_on_no_layout_and_in_no_partial_still_warns(tmp_path, gate):
    # The control: only a partial's own ids are let through.
    _project(tmp_path, {"common/panel": WITH_ID, "frame": FRAME})
    _, missing, cannot = _run(_screen(tmp_path, "frame", ["tab_9_button"]))
    assert len(missing) == 1 and cannot == []


def test_a_partial_also_included_without_an_id_is_on_a_layout(tmp_path, gate):
    # Its bare ids are in the union already; nothing to say.
    _project(tmp_path, {"common/panel": WITH_ID, "frame": FRAME,
                        "list": {"type": "View", "id": "list_root", "child": [{"include": "common/tab_strip"}]}})
    result, missing, cannot = _run(_screen(tmp_path, "frame", ["tab_1_button"]))
    assert missing == [] and cannot == [] and result.element_ids["on_layout"] == 1
