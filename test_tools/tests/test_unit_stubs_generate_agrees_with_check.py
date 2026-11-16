"""`generate unit-stubs` ends the way `--check` judges the same tree.

A name several targets declare, whose tests sit in no target's class,
describe or file, can be MISSING for `--check` ("at least N" — fewer tests
than targets) while `generate` has no target to write the stub for. It then
printed "no stubs to write — every declared case has an implementation" and
exited 0, right under the MISSING line. Now it names what it cannot write and
exits 1, as `--check` does; a tree whose tests merely cannot be placed
(`--check` passes) exits 0 without claiming every case is implemented.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from jsonui_test_cli import cli

SHARED = "teardown_cancelsPendingWork"
TARGETS = ("AlphaViewModel", "BetaViewModel", "GammaViewModel")
CLAIM = "every declared case has an implementation"


def _project(root: Path) -> Path:
    specs = root / "docs" / "screens"
    specs.mkdir(parents=True)
    for target in TARGETS:
        (specs / f"{target.lower()}.spec.json").write_text(json.dumps({
            "type": "screen",
            "unitContracts": {"target": target, "cases": [{"name": SHARED}, {"name": _own(target)}]},
        }), encoding="utf-8")
    (root / "ios" / "tests").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens",
        "platforms": {"ios": {"root": "ios", "unitTestsDir": "tests", "testModule": "App"}},
    }), encoding="utf-8")
    return root


def _own(target: str) -> str:
    return f"{target[:-len('ViewModel')].lower()}_loadsItsFirstPage"


def _swift(root: Path, filename: str, *classes) -> None:
    text = "import XCTest\n" + "".join(
        f"final class {name}: XCTestCase {{\n"
        + "".join(f"    func test_{c}() throws {{ }}\n" for c in cases) + "}\n"
        for name, cases in classes)
    (root / "ios" / "tests" / filename).write_text(text, encoding="utf-8")


def _each_target(root: Path, cases_of) -> None:
    for target in TARGETS:
        _swift(root, f"{target}ContractTests.swift",
               (f"{target}ContractTests", cases_of.get(target, (SHARED, _own(target)))))


def _run(root: Path, monkeypatch, capsys, check: bool):
    monkeypatch.chdir(root)
    rc = cli.cmd_generate_unit_stubs(argparse.Namespace(check=check, dry_run=False, spec_dir=None))
    return rc, capsys.readouterr().out


def test_a_shortfall_no_target_can_be_named_for_exits_1_as_check_does(tmp_path, monkeypatch,
                                                                      capsys):
    root = _project(tmp_path)
    _each_target(root, {t: (_own(t),) for t in TARGETS})
    _swift(root, "LifecycleTests.swift", ("LifecycleTests", (SHARED,)))
    check_rc, _ = _run(root, monkeypatch, capsys, check=True)
    rc, out = _run(root, monkeypatch, capsys, check=False)
    assert (check_rc, rc) == (1, 1), out
    assert CLAIM not in out
    assert "no stub can be written for 2 missing case(s)" in out
    assert f"ios: {SHARED}  (at least 2)" in out


def test_stubs_it_can_write_are_written_and_the_rest_still_exits_1(tmp_path, monkeypatch,
                                                                   capsys):
    # Beta's own case is missing where a stub can go; SHARED is short.
    root = _project(tmp_path)
    _each_target(root, {t: (_own(t),) for t in TARGETS if t != "BetaViewModel"}
                 | {"BetaViewModel": ()})
    _swift(root, "LifecycleTests.swift", ("LifecycleTests", (SHARED,)))
    beta = root / "ios" / "tests" / "BetaViewModelContractTests.swift"
    beta.unlink()
    rc, out = _run(root, monkeypatch, capsys, check=False)
    assert rc == 1, out
    assert "created" in out and "BetaViewModelContractTests.swift" in out
    assert f"test_{_own('BetaViewModel')}" in beta.read_text(encoding="utf-8")
    assert "no stub can be written for 2 missing case(s)" in out


def test_tests_that_cannot_be_placed_exit_0_without_the_claim(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _each_target(root, {t: (_own(t),) for t in TARGETS})
    _swift(root, "LifecycleTests.swift", *[(f"Lifecycle{i}Tests", (SHARED,)) for i in range(3)])
    check_rc, _ = _run(root, monkeypatch, capsys, check=True)
    rc, out = _run(root, monkeypatch, capsys, check=False)
    assert (check_rc, rc) == (0, 0), out
    assert "every declared case has an implementation or a test no target's name places " \
           "(1 UNATTRIBUTED line(s) above: not checked)" in out


def test_control_every_pair_implemented_keeps_the_claim(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _each_target(root, {})
    check_rc, _ = _run(root, monkeypatch, capsys, check=True)
    rc, out = _run(root, monkeypatch, capsys, check=False)
    assert (check_rc, rc) == (0, 0), out
    assert f"  no stubs to write — {CLAIM}\n" in out
