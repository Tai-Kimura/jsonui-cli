"""`jui generate` validates specs with the validator beside it.

The launcher puts only jui_tools on sys.path, and generate imported
`document_tools.jsonui_doc_cli…` — resolvable only where jui.config.json set
`document_tools_path`, which no face did. Every face printed "WARNING:
document_tools not available, skipping validation" and generated from specs
nobody validated. `load_spec_validator` finds it beside the running
jui_tools (the distribution's own document_tools), or by its pip name.

The arms run in fresh interpreters with the launcher's sys.path (`-I`: no
PYTHONPATH, no user site), since the defect is a property of that path and
not of this test process.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VALIDATOR_FILE = REPO / "document_tools/jsonui_doc_cli/spec_doc/validator.py"


def _python(paths: list[Path], code: str) -> subprocess.CompletedProcess:
    prelude = f"import sys; sys.path[:0] = {[str(p) for p in paths]!r}\n"
    return subprocess.run([sys.executable, "-I", "-c", prelude + code],
                          capture_output=True, text=True, timeout=120)


_LOAD = """
import inspect, jui_cli
from jui_cli.core.document_tools_import import load_spec_validator
cls, where = load_spec_validator()
print("JUI", jui_cli.__file__)
print("FILE", inspect.getfile(cls) if cls else None)
print("WHERE", where)
"""


def _fields(out: str) -> dict:
    return dict(line.split(" ", 1) for line in out.strip().splitlines() if " " in line)


def test_control_the_launchers_path_cannot_import_the_old_name():
    run = _python([REPO / "jui_tools"],
                  "from document_tools.jsonui_doc_cli.spec_doc.validator import SpecValidator")
    assert run.returncode != 0 and "No module named 'document_tools'" in run.stderr, run.stderr


def test_the_launchers_path_reaches_the_validator_beside_jui_tools():
    run = _python([REPO / "jui_tools"], _LOAD)
    assert run.returncode == 0, run.stderr
    got = _fields(run.stdout)
    assert Path(got["FILE"]) == VALIDATOR_FILE, got
    assert "beside jui_tools" in got["WHERE"], got


def test_the_pip_name_reaches_the_same_validator(tmp_path):
    """A jui_tools with no document_tools beside it (installed apart), and
    document_tools importable by its pip name: the same file is reached."""
    shutil.copytree(REPO / "jui_tools" / "jui_cli", tmp_path / "jui_tools" / "jui_cli")
    run = _python([tmp_path / "jui_tools", REPO / "document_tools", REPO / "test_tools"], _LOAD)
    assert run.returncode == 0, run.stderr
    got = _fields(run.stdout)
    assert got["JUI"].startswith(str(tmp_path)), got          # the copy ran, not the checkout
    assert Path(got["FILE"]) == VALIDATOR_FILE and got["WHERE"] == "jsonui_doc_cli (pip)", got


def _project(root: Path) -> Path:
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps({
        "project_name": "mini", "spec_directory": "docs/screens/json",
        "layouts_directory": "docs/screens/layouts", "platforms": {"web": {"root": "web"}}}),
        encoding="utf-8")
    (root / "docs/screens/json/home.spec.json").write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "Home", "description": "d"},
        "structure": {"components": [], "layout": {}}}), encoding="utf-8")
    return root


def _generate(launcher: Path, cwd: Path) -> subprocess.CompletedProcess:
    """The launcher as a face runs it, with no site-packages (`-I -S`): what
    this interpreter happens to have installed (CI installs document_tools
    editable, by its pip name) cannot answer for the route under test."""
    return subprocess.run([sys.executable, "-I", "-S", str(launcher), "g", "project", "--dry-run"],
                          cwd=cwd, capture_output=True, text=True, timeout=300)


def test_generate_through_the_launcher_stops_on_an_invalid_spec(tmp_path):
    run = _generate(REPO / "jui_tools/bin/jui", _project(tmp_path / "p"))
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert "ERROR: Validation failed for home.spec.json" in out, out
    assert "document_tools not available" not in out, out


def test_control_a_jui_without_the_validator_says_what_it_tried(tmp_path):
    """jui_tools alone (no document_tools beside it, none installed by name):
    the old WARNING, now naming every route it tried."""
    shutil.copytree(REPO / "jui_tools" / "jui_cli", tmp_path / "jui_tools" / "jui_cli")
    shutil.copytree(REPO / "jui_tools" / "bin", tmp_path / "jui_tools" / "bin")
    run = _generate(tmp_path / "jui_tools/bin/jui", _project(tmp_path / "p"))
    out = run.stdout + run.stderr
    assert run.returncode == 0 and "WARNING: document_tools not available" in out, out
    # All three routes, each with why it did not answer.
    assert "No module named 'document_tools'" in out, out
    assert "no document_tools/ beside jui_tools" in out, out
    assert "No module named 'jsonui_doc_cli'" in out, out
