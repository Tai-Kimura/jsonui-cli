"""`jui build` decides web's include id prefix and hands rjui the answer (U8).

rjui reads no version literal: INCLUDE_ID_PREFIX_GATE_FROM is read once, by
`layout_facts.include_id_prefix_state` through shared/core/gate_versions, and
`_run_tool` puts the answer in JSONUI_INCLUDE_ID_PREFIX for the rjui process —
`announce:<release>` below the release, `on` from it, `off` when withdrawn.
Here a stand-in `rjui` on PATH records what it was handed; the other tools are
handed nothing.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from jui_cli.commands import build_cmd
from jui_cli.core import layout_facts


def _stand_in(tmp_path: Path, name: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    record = tmp_path / f"{name}.env"
    tool.write_text(f'#!/bin/sh\nprintf "%s" "${{JSONUI_INCLUDE_ID_PREFIX-unset}}" > "{record}"\n')
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return record


@pytest.fixture
def on_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("JSONUI_INCLUDE_ID_PREFIX", raising=False)
    return tmp_path


@pytest.mark.parametrize("version, literal, handed", [
    ("1.8.119", "1.8.120", "announce:1.8.120"),
    ("1.8.120", "1.8.120", "on"),                 # the equal point
    ("1.8.121", "1.8.120", "on"),
    ("9.9.9", "withdrawn", "off"),
])
def test_rjui_is_handed_the_answer(on_path, monkeypatch, version, literal, handed):
    monkeypatch.setattr(layout_facts, "INCLUDE_ID_PREFIX_GATE_FROM", literal)
    monkeypatch.setattr("jui_cli.version.toolchain_version", lambda root=None: version)
    record = _stand_in(on_path, "rjui")
    assert build_cmd._run_tool(["rjui", "build"], on_path) is True
    assert record.read_text() == handed


def test_the_other_tools_are_handed_nothing(on_path):
    record = _stand_in(on_path, "sjui")
    assert build_cmd._run_tool(["sjui", "build"], on_path) is True
    assert record.read_text() == "unset"


def test_the_shipped_literal_is_one_line_the_tag_gate_reads():
    # 1e's tag gate reads a module-level, column-0 literal in a tracked .py.
    src = Path(layout_facts.__file__).read_text(encoding="utf-8")
    lines = [l for l in src.splitlines() if l.startswith("INCLUDE_ID_PREFIX_GATE_FROM")]
    assert lines == ['INCLUDE_ID_PREFIX_GATE_FROM: str | None = "1.8.121"']
