"""`generate branch-tests` FAILS when this tool tree cannot read its unmatched-request gate.

A tree without shared/core/gate_versions.py (the test_tools subtree alone — a
pip copy from `git+…#subdirectory=test_tools`) announces no release, so it
cannot say whether the generated tests should fail on unmatched requests, and
writes them as if they should not. Until jsonui-cli 1.9.8 the run printed that
as a note and exited 0 (ticket
jui-test-branch-tests-unmatched-gate-unreadable-is-a-note-not-a-failure) — the
shape 1.9.7 made a failure on validate's coverage gate.

The control on each arm: the same project with the gate readable exits 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli.cli import cmd_generate_branch_tests

from test_branch_tests_names_its_toolchain import _Args, project  # noqa: F401  (fixture)


def _run(root, capsys, **kw):
    rc = cmd_generate_branch_tests(_Args(root, **kw))
    return rc, capsys.readouterr()


def test_generate_fails_and_says_how_to_fix(project, capsys, monkeypatch):
    rc, _ = _run(project, capsys)
    assert rc == 0                                              # control: readable
    monkeypatch.setattr(bt, "_gates", lambda: None)
    rc, out = _run(project, capsys)
    assert rc == 1, out.out + out.err
    assert bt.UNMATCHED_GATE_UNAVAILABLE in out.out
    assert "~/.jsonui-cli/test_tools/jsonui-test" in bt.UNMATCHED_GATE_UNAVAILABLE
    assert "FAILS" in bt.UNMATCHED_GATE_UNAVAILABLE


def test_check_fails_too(project, capsys, monkeypatch):
    rc, _ = _run(project, capsys)                               # write the files
    assert rc == 0
    rc, out = _run(project, capsys, check=True)
    assert rc == 0, out.out + out.err                           # control: readable, fresh
    monkeypatch.setattr(bt, "_gates", lambda: None)
    rc, out = _run(project, capsys, check=True)
    assert rc == 1, out.out + out.err
    assert bt.UNMATCHED_GATE_UNAVAILABLE in out.err


def test_the_note_is_the_failure_line_when_unavailable(monkeypatch):
    monkeypatch.setattr(bt, "_gates", lambda: None)
    assert bt.unmatched_gate_unavailable()
    assert bt.unmatched_gate_note() == bt.UNMATCHED_GATE_UNAVAILABLE
