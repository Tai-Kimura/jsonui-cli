"""Every reader of a `*_GATE_FROM` literal gives the same answer (design v4.20).

The comparison lives in ONE module, shared/core/gate_versions.py. It had been
written in three places, and "withdrawn" broke in two of them in two
different shapes (the gate always on; generation stopping). Here one table
goes through every reader this tree has, and they must agree:

  gate_versions   the module itself
  coverage        validate's contracts coverage gate (test_tools)
  layout ids      the spec validator: an id not in the layout is a WARNING
                  when the gate is on, else INFO — plus the notice (document_tools)

P2e's generator and the tag gate (dev-guide/release/validate_gate_version.py)
read the same module once 1e moves them onto it; add them to READERS then.

The three `shared_core` loaders that find the module must stay one loader
in three copies: a copy that diverged would be a second way to find it.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from jsonui_doc_cli import shared_core as doc_shared_core
from jsonui_doc_cli.spec_doc import validator as validator_mod
from jsonui_test_cli import contracts_coverage as cc

REPO = Path(__file__).resolve().parents[2]
GATES = doc_shared_core.load("gate_versions")

#: (literal, running version) -> state, gates?, announces?
TABLE = [
    (None, "1.8.119", "undeclared", False, False),
    ("", "1.8.119", "undeclared", False, False),
    ("1.8.120", "1.8.119", "release", False, True),     # announced: the next release
    ("1.8.120", "1.8.120", "release", True, False),     # the equal point
    ("1.8.120", "1.8.121", "release", True, False),
    ("1.8.119", "1.8.119", "release", True, False),     # the same literal, at or below the tag
    ("1.8.100", "1.8.99", "release", False, True),      # numeric, not string order
    ("withdrawn", "9.9.9", "withdrawn", False, False),
    ("1.8", "1.8.119", "unreadable", False, False),     # a prefix of every version
    ("1.8.l20", "1.8.119", "unreadable", False, False),
    ("v1.8.120", "9.9.9", "unreadable", False, False),
    ("1.8.120rc1", "9.9.9", "unreadable", False, False),
]


def _reader_module(literal, version):
    return (GATES.gate_state(literal), GATES.gate_is_on(version, literal),
            GATES.gate_state(literal) == "release" and not GATES.gate_is_on(version, literal))


def _reader_coverage(literal, version, monkeypatch):
    monkeypatch.setattr(cc, "VALIDATE_GATE_FROM", literal)
    return (cc.gate_state(), cc.gate_is_on(version),
            cc._gate_line(version).startswith("from jsonui-cli "))


def _reader_layout_ids(literal, version, monkeypatch, tmp_path):
    monkeypatch.setattr(validator_mod, "_running_version", lambda: version)
    monkeypatch.setattr(validator_mod, "LAYOUT_ID_GATE_FROM", literal)
    root = tmp_path / "face"
    (root / "docs/screens/layouts").mkdir(parents=True)
    (root / "docs/screens/json").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json", "layouts_directory": "docs/screens/layouts"}))
    (root / "docs/screens/layouts/s.json").write_text(json.dumps({"type": "View", "id": "root"}))
    spec = root / "docs/screens/json/s.spec.json"
    spec.write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": "S", "displayName": "S", "description": "d", "layoutFile": "s"},
        "stateManagement": {"states": [{"name": "m", "values": [
            {"value": "v", "description": "d", "visibleElements": ["nowhere"]}]}]}}))
    result = validator_mod.SpecValidator().validate_file(spec)
    warned = any("'nowhere'" in m.message for m in result.warnings)
    announced = any(m.message.startswith("from jsonui-cli ") for m in result.infos)
    return warned, announced


@pytest.mark.parametrize("literal, version, state, gates, announces", TABLE)
def test_every_reader_gives_the_tables_answer(literal, version, state, gates, announces,
                                             monkeypatch, tmp_path):
    # The layout-id reader prints no state; it is held to the two answers it acts on.
    answers = {
        "gate_versions": _reader_module(literal, version),
        "coverage": _reader_coverage(literal, version, monkeypatch),
        "layout ids": (state, *_reader_layout_ids(literal, version, monkeypatch, tmp_path)),
    }
    assert answers == {name: (state, gates, announces) for name in answers}, answers


def test_the_readers_load_the_same_file():
    from jsonui_test_cli import shared_core as test_shared_core
    here = GATES.__file__
    assert test_shared_core.load("gate_versions").__file__ == here
    assert Path(here) == REPO / "shared/core/gate_versions.py"


def _loader_functions(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: ast.dump(n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in ("shared_core_dir", "load")}


def test_the_three_loaders_are_one_loader():
    copies = {rel: _loader_functions(REPO / rel) for rel in (
        "jui_tools/jui_cli/core/shared_core.py",
        "document_tools/jsonui_doc_cli/shared_core.py",
        "test_tools/jsonui_test_cli/shared_core.py")}
    first = next(iter(copies.values()))
    assert set(first) == {"shared_core_dir", "load"}
    assert all(c == first for c in copies.values()), list(copies)
