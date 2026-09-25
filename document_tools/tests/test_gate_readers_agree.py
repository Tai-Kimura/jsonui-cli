"""Every reader of a `*_GATE_FROM` literal gives the same answer (design v4.20).

The comparison lives in ONE module, shared/core/gate_versions.py. It had been
written in three places, and "withdrawn" broke in two of them in two
different shapes (the gate always on; generation stopping). Here one table
goes through every reader this tree has, and they must agree:

  gate_versions   the module itself
  coverage        validate's contracts coverage gate (test_tools)
  layout ids      the spec validator: an id not in the layout is a WARNING
                  when the gate is on, else INFO — plus the notice (document_tools)
  unmatched       P2e's generator: whether an unmatched request fails the
                  generated test, and the gate it hands the runtime to print
                  (test_tools branch_tests)
  tag gate        dev-guide/release/validate_gate_version.py: its verdict on
                  the literal kept from the previous tag at the table's version
  include ids     jui's decision for web's include ids, handed to rjui as
                  JSONUI_INCLUDE_ID_PREFIX (jui_tools; U8)

The three `shared_core` loaders that find the module must stay one loader
in three copies: a copy that diverged would be a second way to find it.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import importlib.util

from jsonui_doc_cli import shared_core as doc_shared_core
from jsonui_doc_cli.spec_doc import validator as validator_mod
from jsonui_test_cli import branch_tests as bt
from jsonui_test_cli import contracts_coverage as cc

REPO = Path(__file__).resolve().parents[2]
GATES = doc_shared_core.load("gate_versions")


def _load_tag_gate():
    path = REPO / "dev-guide/release/validate_gate_version.py"
    spec = importlib.util.spec_from_file_location("_tag_gate_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TAG_GATE = _load_tag_gate()

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


def _reader_unmatched(literal, version, monkeypatch):
    """What the four renderers are handed: red, and the gate string the
    runtime prints (a release announces it; "withdrawn" says so; None says no
    release) — plus the line `generate branch-tests` prints for unreadable."""
    monkeypatch.setattr(bt, "UNMATCHED_GATE_FROM", literal)
    monkeypatch.setattr(bt, "_running_version", lambda: version)
    red, gate = bt.unmatched_gate()
    state = ("withdrawn" if gate == GATES.GATE_WITHDRAWN else "release" if gate
             else "unreadable" if bt.unmatched_gate_note() else "undeclared")
    return state, red, state == "release" and not red


#: The tag gate's verdict on (L -> L) at the table's version, by what it says.
_TAG_VERDICTS = [
    (True, "gates since", ("release", True, False)),
    (True, "announces", ("release", False, True)),
    (True, "withdrawn", ("withdrawn", False, False)),
    (True, "unset", ("undeclared", False, False)),
    (False, "version unreadable", ("unreadable", False, False)),
]


def _reader_tag_gate(literal, version):
    ok, why = TAG_GATE.judge("X_GATE_FROM", version, literal, literal)
    for want_ok, start, answer in _TAG_VERDICTS:
        if ok == want_ok and (why.startswith(start) if ok else start in why):
            return answer
    return ("no verdict the table knows", ok, why)


def _reader_include_prefix(literal, version, monkeypatch):
    """jui's decision for web's include ids (design U8) — what it hands rjui."""
    from jui_cli.core import layout_facts
    monkeypatch.setattr(layout_facts, "INCLUDE_ID_PREFIX_GATE_FROM", literal)
    state = layout_facts.include_id_prefix_state(version)
    return state == "on", state == "announce"


@pytest.mark.parametrize("literal, version, state, gates, announces", TABLE)
def test_every_reader_gives_the_tables_answer(literal, version, state, gates, announces,
                                             monkeypatch, tmp_path):
    # The layout-id reader prints no state; it is held to the two answers it acts on.
    answers = {
        "gate_versions": _reader_module(literal, version),
        "coverage": _reader_coverage(literal, version, monkeypatch),
        "layout ids": (state, *_reader_layout_ids(literal, version, monkeypatch, tmp_path)),
        "unmatched": _reader_unmatched(literal, version, monkeypatch),
        "tag gate": _reader_tag_gate(literal, version),
        "include ids (jui -> rjui)": (state, *_reader_include_prefix(literal, version,
                                                                     monkeypatch)),
    }
    assert answers == {name: (state, gates, announces) for name in answers}, answers


def test_the_readers_load_the_same_file():
    from jsonui_test_cli import shared_core as test_shared_core
    here = GATES.__file__
    assert test_shared_core.load("gate_versions").__file__ == here
    assert bt._gates().__file__ == here
    assert Path(TAG_GATE.gates.__file__) == Path(here) == REPO / "shared/core/gate_versions.py"


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
