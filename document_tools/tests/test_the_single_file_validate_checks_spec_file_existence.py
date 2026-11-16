"""`validate spec <file>` checks that a declared `specFile` exists, like the walk.

Reported 2026-09-11 from a downstream admin face with a synthetic control:
`customComponents[0].specFile` pointed at a file that does not exist, and

    validate spec docs/screens/json                   rc 1, 2 errors
    validate spec docs/screens/json/<screen>.spec.json  rc 0, 0 errors
    MCP doc_validate_spec (single file)                PASSED

The define agent declares "done" with the third form. The existence check
lived only in the directory walk (`_component_declaration_gaps`); the
single-file path called the validator alone. Now the same function serves
all three mouths, with the second direction (on disk, declared by nobody)
dropped for a single file, which has no standing to say it.

🔻 THE SHAPE IS THE TICKET'S: the component spec sits BESIDE the screen
specs under `<face>/screens/json`, which is how that face keeps them — not
under `components/json`, the layout this tool writes by default.

⚠️ The MCP mouth reads only the exit code (`is_valid: exitCode === 0`), so
the arm for it runs the real entrypoint as a subprocess and reads rc.
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

SCREEN = {
    "type": "screen_spec",
    "version": "1.0",
    "metadata": {"name": "AdminDashboard", "displayName": "Dashboard",
                 "description": "d", "layoutFile": "admin_dashboard"},
    "structure": {
        "components": [{"type": "Label", "id": "title", "description": "d"}],
        "layout": {"root": "View", "children": [{"id": "title"}]},
        "customComponents": [
            {"name": "ChartBars", "specFile": "chart_bars.component.json",
             "description": "bars"},
        ],
    },
}


def _face(root: Path, spec_file: str = "chart_bars.component.json",
          component_on_disk: bool = True, flat: bool = False) -> Path:
    """The ticket's layout: screen spec and component spec side by side."""
    d = root if flat else root / "docs" / "screens" / "json"
    d.mkdir(parents=True, exist_ok=True)
    data = json.loads(json.dumps(SCREEN))
    data["structure"]["customComponents"][0]["specFile"] = spec_file
    spec = d / "admin_dashboard.spec.json"
    spec.write_text(json.dumps(data), encoding="utf-8")
    if component_on_disk:
        (d / "chart_bars.component.json").write_text(json.dumps({
            "componentId": "chart_bars", "name": "ChartBars", "description": "x"}),
            encoding="utf-8")
    return spec


def _single(spec: Path) -> tuple[int, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_validate_spec(Namespace(file=str(spec)))
    return rc, buf.getvalue()


def _directory(d: Path) -> tuple[int, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_validate_spec(Namespace(file=str(d)))
    return rc, buf.getvalue()


MISSING = "customComponents declares 'chart_bars_MISSING.component.json'"


class TestTheSingleFileFormSeesWhatTheWalkSees:
    def test_control_a_declared_file_that_exists_is_silent(self, tmp_path):
        spec = _face(tmp_path)
        rc, out = _single(spec)
        assert rc == 0, out
        assert "customComponents declares" not in out
        assert "not checked" not in out

    def test_a_dangling_spec_file_fails_the_single_file_form(self, tmp_path):
        spec = _face(tmp_path, spec_file="chart_bars_MISSING.component.json")
        rc, out = _single(spec)
        assert rc == 1, out
        assert MISSING in out, out
        assert "Result: FAILED" in out
        # The totals line the reader (and any grep) counts it in.
        assert "Errors: 1," in out, out

    def test_the_walk_and_the_single_file_form_agree_on_the_same_tree(self, tmp_path):
        spec = _face(tmp_path, spec_file="chart_bars_MISSING.component.json")
        rc_dir, out_dir = _directory(spec.parent)
        rc_one, out_one = _single(spec)
        assert (rc_dir, rc_one) == (1, 1)
        assert MISSING in out_dir and MISSING in out_one
        # The walk ALSO reports the on-disk file nobody declares; one file
        # has no standing for that direction and must not claim it.
        assert "declared by no screen spec" in out_dir
        assert "declared by no screen spec" not in out_one

    def test_outside_a_face_the_check_says_it_did_not_run(self, tmp_path):
        """Not `<face>/screens/json`: the face cannot be derived, so say so."""
        spec = _face(tmp_path, spec_file="chart_bars_MISSING.component.json", flat=True)
        rc, out = _single(spec)
        assert "component declarations were not checked" in out, out
        assert MISSING not in out


class TestBoundaries:
    def test_a_same_named_file_in_another_face_does_not_count(self, tmp_path):
        spec = _face(tmp_path / "admin", component_on_disk=False)
        _face(tmp_path / "other")  # the file exists — under a different face
        rc, out = _single(spec)
        assert rc == 1 and "customComponents declares 'chart_bars.component.json'" in out, out

    def test_an_existing_but_empty_file_is_not_an_existence_error(self, tmp_path):
        """Existence is this check's whole claim; the file's content is the
        component validator's, and this arm names that limit."""
        spec = _face(tmp_path, component_on_disk=False)
        (spec.parent / "chart_bars.component.json").write_text("", encoding="utf-8")
        rc, out = _single(spec)
        assert "customComponents declares" not in out, out


class TestTheMouthTheMCPUses:
    def test_the_real_entrypoint_exits_1_on_a_dangling_spec_file(self, tmp_path):
        spec = _face(tmp_path, spec_file="chart_bars_MISSING.component.json")
        env = dict(os.environ, PYTHONPATH=str(REPO / "document_tools"))
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "spec", str(spec)],
            capture_output=True, text=True, env=env, timeout=120)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert MISSING in proc.stdout

    def test_the_real_entrypoint_exits_0_on_the_control(self, tmp_path):
        spec = _face(tmp_path)
        env = dict(os.environ, PYTHONPATH=str(REPO / "document_tools"))
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_doc_cli.cli", "validate", "spec", str(spec)],
            capture_output=True, text=True, env=env, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
