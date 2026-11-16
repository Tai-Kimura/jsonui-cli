"""A sub-spec's component declarations are checked where the rules put it.

The rules put a split screen's sub-specs in `<face>/screens/json/<screen>/`.
`validate spec` on one of them derived the face from the spec's OWN
directory, tested only that directory for `screens/json`, and so found no
face for any sub-spec. Reported 2026-09-25 from a consumer's admin face, 4 of
4 sub-specs:

- every one warned "component declarations were not checked" — three of
  them declared no component at all, so the warning was about nothing and
  the author had no way to clear it;
- the one that declared a component was never checked: a `specFile` naming
  nothing passed.

Now the face is found by walking up to the nearest `screens/json`, and a
single spec that declares nothing gets no warning — there is nothing to
check. A walk rooted below `screens/json` reads part of the face, so it keeps
only the direction one file keeps (declared, file missing): a component
declared outside the walk is not "declared by no screen spec".

🔻 The positive control is the dangling declaration: a sub-spec naming a
component file that does not exist must turn the run red. Before the fix it
passed with rc 0 and one warning.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli import cli  # noqa: E402

NOT_CHECKED = "component declarations were not checked"
COMPONENT = "date_picker.component.json"


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _face(root: Path, *, declares: str | None, component_on_disk: bool = True,
          layout_uses_component: bool = False) -> Path:
    """A face with a parent spec and one sub-spec in `screens/json/settings/`.

    Returns the sub-spec. The parent owns the layout, as a split screen's
    does; the sub-spec declares *declares* (or nothing).
    """
    specs = root / "docs" / "screens" / "json"
    _write(specs / "settings.spec.json", {
        "type": "screen_parent_spec", "version": "1.0",
        "metadata": {"name": "Settings", "displayName": "Settings",
                     "description": "d", "layoutFile": "settings"},
        "subSpecs": [{"file": "settings/settings-plans.spec.json", "name": "Plans"}],
    })
    sub = {
        "type": "screen_sub_spec", "version": "1.0",
        "metadata": {"name": "SettingsPlans", "parentSpec": "settings.spec.json",
                     "displayName": "Plans", "description": "d"},
        "structure": {},
    }
    if declares:
        sub["structure"]["customComponents"] = [
            {"name": "DatePicker", "specFile": declares, "description": "d"}]
    spec = _write(specs / "settings" / "settings-plans.spec.json", sub)
    if component_on_disk:
        _write(root / "docs" / "components" / "json" / COMPONENT,
               {"type": "component_spec", "version": "1.0",
                "metadata": {"name": "DatePicker", "displayName": "DatePicker",
                             "description": "x"}})
    layouts = root / "docs" / "screens" / "layouts"
    layouts.mkdir(parents=True, exist_ok=True)
    if layout_uses_component:
        _write(layouts / "settings.json",
               {"type": "View", "child": [{"type": "DatePicker"}]})
    return spec


def _validate(target: Path) -> tuple[int, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_validate_spec(Namespace(file=str(target)))
    return rc, buf.getvalue()


class TestASubSpecHasAFace:
    def test_control_a_declared_component_that_exists_passes_quietly(self, tmp_path):
        spec = _face(tmp_path, declares=COMPONENT)
        rc, out = _validate(spec)
        assert rc == 0, out
        assert NOT_CHECKED not in out, out
        assert "customComponents declares" not in out, out

    def test_positive_control_a_dangling_declaration_turns_it_red(self, tmp_path):
        # Before the fix: rc 0, and the not-checked warning in place of this.
        spec = _face(tmp_path, declares="date_picker_MISSING.component.json")
        rc, out = _validate(spec)
        assert rc == 1, out
        assert "customComponents declares 'date_picker_MISSING.component.json'" in out, out
        assert NOT_CHECKED not in out, out

    def test_two_levels_down_is_the_same_face(self, tmp_path):
        spec = _face(tmp_path, declares="date_picker_MISSING.component.json")
        deeper = _write(spec.parent / "more" / spec.name, json.loads(spec.read_text()))
        spec.unlink()
        rc, out = _validate(deeper)
        assert rc == 1 and "date_picker_MISSING" in out, out

    def test_the_real_entrypoint_the_mcp_runs_exits_1(self, tmp_path):
        # MCP `doc_validate_spec` reads only the exit code.
        spec = _face(tmp_path, declares="date_picker_MISSING.component.json")
        env = dict(os.environ, PYTHONPATH=str(REPO / "document_tools"))
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "spec", str(spec)],
            capture_output=True, text=True, env=env, timeout=120)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "date_picker_MISSING" in proc.stdout


class TestNothingDeclaredNothingToReport:
    def test_a_sub_spec_that_declares_nothing_gets_no_warning(self, tmp_path):
        spec = _face(tmp_path, declares=None)
        rc, out = _validate(spec)
        assert rc == 0, out
        assert NOT_CHECKED not in out, out

    def test_outside_any_face_a_spec_that_declares_nothing_gets_no_warning(self, tmp_path):
        spec = _write(tmp_path / "loose" / "x.spec.json", {"structure": {}})
        errors, warnings = cli._component_declaration_gaps([spec], spec.parent,
                                                           this_spec_only=True)
        assert (errors, warnings) == ([], [])

    def test_outside_any_face_a_declaration_still_says_it_was_not_checked(self, tmp_path):
        # The boundary: the same loose spec, now with something to check.
        spec = _write(tmp_path / "loose" / "x.spec.json", {"structure": {
            "customComponents": [{"name": "DatePicker", "specFile": COMPONENT}]}})
        errors, warnings = cli._component_declaration_gaps([spec], spec.parent,
                                                           this_spec_only=True)
        assert errors == [] and len(warnings) == 1 and NOT_CHECKED in warnings[0], warnings


class TestAWalkBelowScreensJsonReadsPartOfTheFace:
    def _face_with_a_top_level_declarer(self, root: Path) -> Path:
        # The component is declared by a TOP-LEVEL spec and used by a layout;
        # the walk below starts in the sub-spec directory and never reads it.
        spec = _face(root, declares=None, layout_uses_component=True)
        _write(spec.parent.parent / "home.spec.json", {
            "type": "screen_spec", "version": "1.0",
            "metadata": {"name": "Home", "displayName": "Home", "description": "d",
                         "layoutFile": "home"},
            "structure": {"components": [{"type": "View", "id": "root", "description": "d"}],
                          "layout": {"root": "root", "children": []},
                          "customComponents": [{"name": "DatePicker", "specFile": COMPONENT,
                                                "description": "d"}]}})
        return spec

    def test_a_component_declared_outside_the_walk_is_not_undeclared(self, tmp_path):
        spec = self._face_with_a_top_level_declarer(tmp_path)
        rc, out = _validate(spec.parent)
        assert "declared by no screen spec" not in out, out
        assert NOT_CHECKED not in out, out

    def test_control_the_whole_face_walk_still_runs_the_second_direction(self, tmp_path):
        # Same tree minus the top-level declaration: from screens/json the
        # walk has the whole face, and the component IS declared by nobody.
        spec = _face(tmp_path, declares=None, layout_uses_component=True)
        rc, out = _validate(spec.parent.parent)
        assert rc == 1, out
        assert "declared by no screen spec" in out, out

    def test_the_subdirectory_walk_still_checks_what_it_read(self, tmp_path):
        spec = self._face_with_a_top_level_declarer(tmp_path)
        data = json.loads(spec.read_text())
        data["structure"]["customComponents"] = [
            {"name": "X", "specFile": "x_MISSING.component.json", "description": "d"}]
        spec.write_text(json.dumps(data), encoding="utf-8")
        rc, out = _validate(spec.parent)
        assert rc == 1 and "x_MISSING.component.json" in out, out


class TestTheWalkUp:
    def test_nearest_screens_json_wins(self, tmp_path):
        outer = tmp_path / "a" / "screens" / "json"
        inner = outer / "x" / "screens" / "json" / "sub"
        inner.mkdir(parents=True)
        assert cli._face_spec_dir(inner) == (outer / "x" / "screens" / "json").resolve()
        assert cli._face_spec_dir(outer / "x") == outer.resolve()

    def test_a_json_dir_not_under_screens_is_not_a_face(self, tmp_path):
        d = tmp_path / "docs" / "requirements" / "json"
        d.mkdir(parents=True)
        assert cli._face_spec_dir(d) is None
