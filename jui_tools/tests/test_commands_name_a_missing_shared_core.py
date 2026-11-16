"""A jui tree without shared/core says so and exits 1 — verify, g project, build.

Every spec's type comes from shared/core/spec_types.py. Without it each
command skipped every spec as a type it did not know: `jui verify` printed
"no screens found — nothing to verify" plus an ERROR list of layouts "with no
spec" and exited 0, `jui g project` said each spec's type was "neither a
screen nor a known non-screen type" and exited 0 having generated nothing,
and `jui build` stopped on an AttributeError from generation_manifest
(measured 2026-09-26 on a jui_tools copied without its sibling shared/).

The arms run the launcher in fresh interpreters (`-I -S`), from copies of
jui_tools with and without shared/ beside it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _tree(root: Path, with_shared: bool) -> Path:
    shutil.copytree(REPO / "jui_tools" / "jui_cli", root / "jui_tools" / "jui_cli")
    shutil.copytree(REPO / "jui_tools" / "bin", root / "jui_tools" / "bin")
    if with_shared:
        shutil.copytree(REPO / "shared", root / "shared")
    return root / "jui_tools" / "bin" / "jui"


def _project(root: Path) -> Path:
    (root / "specs").mkdir(parents=True)
    (root / "layouts").mkdir()
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "specs", "layouts_directory": "layouts", "platforms": {"web": {"root": "web"}}}))
    (root / "specs/home.spec.json").write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "Home", "displayName": "H", "description": "d"},
        "structure": {"components": [{"id": "title", "type": "Label", "description": "t"}],
                      "layout": {"root": "root", "children": ["title"]}}}))
    (root / "layouts/home.json").write_text(json.dumps({"type": "View", "child": [{"type": "Label",
                                                                                   "id": "title"}]}))
    return root


def _run(launcher: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-S", str(launcher), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("command", [["verify"], ["g", "project", "--dry-run"], ["build"]],
                         ids=["verify", "g project", "build"])
def test_without_shared_core_the_command_names_it_and_exits_1(tmp_path, command):
    run = _run(_tree(tmp_path / "t", with_shared=False), _project(tmp_path / "p"), *command)
    out = run.stdout + run.stderr
    assert run.returncode == 1, out
    assert (f"ERROR: `jui {' '.join(command[:2]) if command[0] == 'g' else command[0]}` cannot read specs: "
            "shared/core/spec_types.py is not in this tool tree") in out, out
    assert "Traceback" not in out and "neither a screen" not in out and "no screens found" not in out, out


def test_control_with_shared_core_verify_verifies(tmp_path):
    run = _run(_tree(tmp_path / "t", with_shared=True), _project(tmp_path / "p"), "verify")
    out = run.stdout + run.stderr
    assert run.returncode == 0 and "**verified 1 of 1 screen(s)**" in out, out
    assert "cannot read specs" not in out, out
