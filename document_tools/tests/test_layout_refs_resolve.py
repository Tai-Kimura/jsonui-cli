"""`metadata.layoutFile` and `cellClasses[]` name layouts that have to exist.

Both were read for their CONTENTS with nothing asking whether the file was
there. `cellClasses` was checked for shape only — a non-empty array — so a
name resolving to nothing counted as a satisfied declaration.

The reporter counted their whole population before reporting: 18 `layoutFile`
and 12 `cellClasses` references, all 30 resolving, 0 wrong. The report is
that the check is absent, not that the data is broken — and they fired a
control arm to earn it, mutating `layoutFile` at the same time, because
"`cellClasses` alone produced no reaction" is equally predicted by "there is
no check" and by "the probe missed".

They also named the trap in their own survey: defining "looks like a path"
by file extension dropped both of these fields, since both name a layout
WITHOUT the `.json` suffix. Half the population vanished from the
denominator. The suffix is added here rather than demanded from the author,
for the same reason.

The bases are the three-step rule, with the kind's declared directory first:
`layouts_directory` for these, which `relatedFiles[].path` skips because a
layout, a view model and a model all share that key and it has no kind.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.spec_doc.validator import SpecValidator


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"layouts_directory": "docs/screens/layouts"}), encoding="utf-8")
    layouts = tmp_path / "docs" / "screens" / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "admin_master.json").write_text("{}", encoding="utf-8")
    (layouts / "admin_master").mkdir()
    (layouts / "admin_master" / "row_cell.json").write_text(
        "{}", encoding="utf-8")
    (tmp_path / "docs" / "screens" / "json").mkdir(parents=True)
    return tmp_path


def _spec(*, layout_file="admin_master", cell_classes=None):
    doc = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"name": "AdminMaster", "displayName": "Admin",
                     "description": "d", "layoutFile": layout_file},
        "structure": {"components": []},
    }
    if cell_classes is not None:
        doc["structure"]["collection"] = {"id": "list",
                                          "cellClasses": cell_classes}
    return doc


def _validate(project, doc):
    path = project / "docs" / "screens" / "json" / "admin_master.spec.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return SpecValidator().validate_file(str(path))


def _layout_warnings(result):
    return [m for m in result.warnings if "does not exist" in m.message]


class TestTheControl:
    def test_a_document_naming_real_layouts_is_clean(self, project):
        """The control, and it has to be clean for the RIGHT reason: an
        invalid document stops the validator before either check runs, and
        every "no warnings" assertion below would then hold for that."""
        result = _validate(project, _spec(
            cell_classes=["admin_master/row_cell"]))

        assert result.errors == [], [m.message for m in result.errors]
        assert result.warnings == []


class TestLayoutFile:
    def test_a_name_that_resolves_to_nothing_is_reported(self, project):
        result = _validate(project, _spec(layout_file="no_such_probe"))

        [warning] = _layout_warnings(result)
        assert "no_such_probe" in warning.message
        assert "metadata.layoutFile" in warning.path

    def test_the_suffix_is_supplied_not_demanded(self, project):
        """Every reference in the reporting corpus omits `.json`. Requiring
        it would report all 30 of them."""
        assert _layout_warnings(_validate(project, _spec())) == []

    def test_writing_the_suffix_is_also_accepted(self, project):
        """Both spellings appear in the wild and neither is wrong here."""
        assert _layout_warnings(
            _validate(project, _spec(layout_file="admin_master.json"))) == []

    def test_it_stays_a_warning(self, project):
        """Same weight as its sibling check, and for the same reason: no
        project has measured its count, and a gate that reddens where it
        cannot be cleared that day is one people learn to skip."""
        result = _validate(project, _spec(layout_file="no_such_probe"))

        assert result.is_valid
        assert "becomes an error" in _layout_warnings(result)[0].message


class TestCellClasses:
    def test_an_entry_that_resolves_to_nothing_is_reported(self, project):
        result = _validate(project, _spec(
            cell_classes=["admin_master/no_such_cell_probe"]))

        [warning] = _layout_warnings(result)
        assert "no_such_cell_probe" in warning.message

    def test_every_entry_is_checked_not_just_the_first(self, project):
        """The shape check asked only that the array was non-empty, so one
        good entry made the rest unexamined."""
        result = _validate(project, _spec(cell_classes=[
            "admin_master/row_cell",
            "admin_master/gone_one",
            "admin_master/gone_two",
        ]))

        assert len(_layout_warnings(result)) == 2

    def test_the_index_is_named(self, project):
        result = _validate(project, _spec(cell_classes=[
            "admin_master/row_cell", "admin_master/gone"]))

        assert _layout_warnings(result)[0].path.endswith("cellClasses[1]")

    def test_the_shape_check_still_holds(self, project):
        """Resolution is added beside the shape rule, not in place of it."""
        doc = _spec()
        doc["structure"]["collection"] = {"id": "list", "cellClasses": []}

        result = _validate(project, doc)

        assert any("at least one of" in m.message for m in result.errors)


class TestTheBases:
    def test_the_declared_layouts_directory_is_tried_first(self, project):
        """The kind-specific step. `relatedFiles[].path` does not get one,
        because that key carries layouts, view models and models alike."""
        validator = SpecValidator()
        validator._spec_file_path = (
            project / "docs" / "screens" / "json" / "x.spec.json").resolve()

        with_kind = validator._declared_path_roots("layout")
        without = validator._declared_path_roots()

        assert with_kind[0] == project / "docs" / "screens" / "layouts"
        assert with_kind[1:] == without

    def test_a_layout_beside_the_spec_resolves(self, project):
        """Step 2, unchanged from the sibling check."""
        beside = project / "docs" / "screens" / "json" / "local.json"
        beside.write_text("{}", encoding="utf-8")

        assert _layout_warnings(_validate(project, _spec(
            layout_file="local"))) == []

    def test_the_ascent_still_stops_at_the_project(self, project):
        """Step 3 keeps its ceiling: a name that resolves only outside the
        repository must not answer, or the check goes machine-dependent —
        green at a desk, warning in CI."""
        outside = project.parent / "stray_layout.json"
        outside.write_text("{}", encoding="utf-8")
        try:
            result = _validate(project, _spec(layout_file="stray_layout"))
            assert len(_layout_warnings(result)) == 1
        finally:
            outside.unlink()
