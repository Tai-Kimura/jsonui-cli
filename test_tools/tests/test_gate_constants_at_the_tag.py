"""Red-check xxxi generalized: every `*_GATE_FROM` literal, judged at the tag.

`dev-guide/release/validate_gate_version.py` used to read VALIDATE_GATE_FROM
alone. P2e(a) adds UNMATCHED_GATE_FROM, shipped unset on purpose in N, and a
second literal the tag gate does not read could be set at or below the tag by
mistake and switch a gate on with no release announcing it. Design v4.18
(§6.1 P3a-1) judges every such constant on the pair (the previous tag's
value, this tree's value), and the constants are collected from the tree, not
named in the check.

The arms: one per row of the table and per pair it leaves open; the tree form
on real git repositories (N's shape, one of two constants in violation, a
withdrawal); the collector's controls (a computed value, an indented
assignment, a double assignment, a module that names VALIDATE_GATE_FROM
without the collector finding it, the same name in two files); this very
tree; and two mutations of the check that must flip a verdict.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "dev-guide/release/validate_gate_version.py"


def _load(source: str | None = None):
    spec = importlib.util.spec_from_file_location("validate_gate_version_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(SCRIPT), "exec"), module.__dict__)
    return module


vgv = _load()
A = vgv.ABSENT
W = vgv.WITHDRAWN


# ------------------------------------------------------------ the table ---

@pytest.mark.parametrize("row, previous, current, ok, word", [
    ("unset -> unset", None, None, True, "nothing announced"),
    ("unset -> next patch", None, "1.8.120", True, "announces 1.8.120"),
    ("unset -> next minor", None, "1.9.0", True, "announces 1.9.0"),
    ("unset -> next major", None, "2.0.0", True, "announces 2.0.0"),
    ("L -> L at or below the tag", "1.8.119", "1.8.119", True, "gates since"),
    ("L -> the next release, later (postponed)", "1.8.119", "1.8.120", True, "postpones"),
    ("anything -> withdrawn", "1.8.120", W, True, "withdrawn (was '1.8.120')"),
    ("unset -> at the tag", None, "1.8.119", False, "had it unset"),
    ("unset -> below the tag", None, "1.8.100", False, "had it unset"),
    ("L -> unset", "1.8.120", None, False, "withdraw it with"),
    ("L -> earlier than L", "1.9.0", "1.8.120", False, "brought forward"),
    ("not a next release", None, "1.8.121", False, "cannot be the next release"),
    ("postponed too far", "1.8.119", "1.8.125", False, "cannot be the next release"),
])
def test_the_transition_table(row, previous, current, ok, word):
    got, why = vgv.judge("UNMATCHED_GATE_FROM", "1.8.119", current, previous)
    assert (got, word in why) == (ok, True), (row, why)


@pytest.mark.parametrize("pair, previous, current, ok, word", [
    # The pairs the table leaves open, read by its intent.
    ("withdrawn -> announced again", W, "1.8.120", True, "announces 1.8.120"),
    ("withdrawn -> at the tag", W, "1.8.119", False, "had it withdrawn"),
    ("withdrawn -> unset", W, None, True, "nothing announced"),
    ("L -> L while still the next release", "1.8.120", "1.8.120", True, "announces 1.8.120 again"),
    ("L -> gone from the tree", "1.8.120", A, False, "gone from this tree"),
    ("unset -> gone", None, A, True, "n/a"),
    ("new in this tree, announcing", A, "1.8.120", True, "announces"),
    ("new in this tree, at the tag", A, "1.8.119", False, "had no section"),
])
def test_the_pairs_the_table_leaves_open(pair, previous, current, ok, word):
    got, why = vgv.judge("UNMATCHED_GATE_FROM", "1.8.119", current, previous)
    assert (got, word in why) == (ok, True), (pair, why)


def test_only_validate_fails_when_unset():
    assert vgv.judge("VALIDATE_GATE_FROM", "1.8.119", None, None)[0] is False
    assert vgv.judge("UNMATCHED_GATE_FROM", "1.8.119", None, None)[0] is True


# ------------------------------------------------------------ tree form ---

_VALIDATE_PATH = "test_tools/jsonui_test_cli/contracts_coverage.py"
_UNMATCHED_PATH = "test_tools/jsonui_test_cli/branch_tests.py"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


def _commit(root: Path, files: dict, tag: str) -> None:
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if text is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
         "--allow-empty", "-m", tag)
    _git(root, "tag", tag)


def _repo(tmp_path: Path, previous: dict, current: dict) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _commit(root, {"README.md": "r\n", **previous}, "prev")
    _commit(root, current, "cur")
    return root


def _module(name: str, value) -> str:
    rendered = "None" if value is None else f'"{value}"'
    return f'"""m"""\nfrom __future__ import annotations\n\n{name}: str | None = {rendered}\n'


def _run(root: Path, tag="1.8.119") -> tuple[int, list[str]]:
    run = subprocess.run(["python3", str(SCRIPT), tag, "--repo", str(root), "cur", "prev"],
                         capture_output=True, text=True)
    return run.returncode, run.stdout.splitlines()


def test_n_ships_unmatched_unset_and_the_tag_gate_is_green(tmp_path):
    """N (1.8.119): the previous tag has neither constant; VALIDATE announces
    the next patch, UNMATCHED is left unset on purpose (the table's first row)."""
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
        _UNMATCHED_PATH: _module("UNMATCHED_GATE_FROM", None)})
    rc, lines = _run(root)
    assert rc == 0, lines
    assert lines[0].startswith("ok 2 gate constant(s) in cur: UNMATCHED_GATE_FROM, VALIDATE_GATE_FROM")
    assert any(l.startswith("  ok UNMATCHED_GATE_FROM") and "nothing announced" in l for l in lines)
    assert any(l.startswith("  ok VALIDATE_GATE_FROM") and "announces 1.8.120" in l for l in lines)


def test_one_of_two_in_violation_is_named(tmp_path):
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
        _UNMATCHED_PATH: _module("UNMATCHED_GATE_FROM", "1.8.119")})
    rc, lines = _run(root)
    assert rc == 1 and lines[0].startswith("FAIL"), lines
    fails = [l for l in lines[1:] if l.startswith("  FAIL")]
    assert len(fails) == 1 and "UNMATCHED_GATE_FROM" in fails[0], lines
    assert any(l.startswith("  ok VALIDATE_GATE_FROM") for l in lines), lines


def test_a_withdrawal_is_printed_and_green(tmp_path):
    root = _repo(tmp_path,
                 {_VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
                  _UNMATCHED_PATH: _module("UNMATCHED_GATE_FROM", "1.8.120")},
                 {_UNMATCHED_PATH: _module("UNMATCHED_GATE_FROM", W)})
    rc, lines = _run(root, tag="1.8.120")
    assert rc == 0, lines
    assert any("UNMATCHED_GATE_FROM" in l and "withdrawn (was '1.8.120')" in l for l in lines), lines


def test_a_constant_that_vanished_is_red(tmp_path):
    root = _repo(tmp_path,
                 {_VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
                  _UNMATCHED_PATH: _module("UNMATCHED_GATE_FROM", "1.8.121")},
                 {_UNMATCHED_PATH: '"""m"""\n'})
    rc, lines = _run(root, tag="1.8.120")
    assert rc == 1 and any("gone from this tree" in l for l in lines), lines


# ------------------------------------------------------- the collector ---

@pytest.mark.parametrize("case, text, word", [
    ("computed", 'X_GATE_FROM = "1." + "9.0"\n', "not a literal"),
    ("indented", 'import os\nif os:\n    X_GATE_FROM = "1.9.0"\n', "below module level"),
    ("double assignment", 'ALIAS = X_GATE_FROM = None\n', "line scan reads"),
    ("not a version", 'X_GATE_FROM = 190\n', "neither a version string nor None"),
])
def test_a_constant_the_readers_cannot_agree_on_is_red(tmp_path, case, text, word):
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
        "jui_tools/jui_cli/gate.py": text})
    rc, lines = _run(root)
    assert rc == 1 and any(word in l for l in lines), (case, lines)


def test_control_a_module_that_names_validate_must_yield_it(tmp_path):
    """The collector being blind must not read as the tree being empty."""
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: '"""m"""\n# VALIDATE_GATE_FROM is set when the release is cut\n'})
    rc, lines = _run(root)
    assert rc == 1 and any("collector is blind" in l for l in lines), lines


def test_the_same_name_in_two_files_is_red(tmp_path):
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
        "a/one.py": _module("X_GATE_FROM", None), "b/two.py": _module("X_GATE_FROM", None)})
    rc, lines = _run(root)
    assert rc == 1 and any("which one gates is ambiguous" in l for l in lines), lines


def test_quoted_assignments_in_tests_are_not_constants(tmp_path):
    root = _repo(tmp_path, {}, {
        _VALIDATE_PATH: _module("VALIDATE_GATE_FROM", "1.8.120"),
        "test_tools/tests/test_x.py": 'def f():\n    return f"X_GATE_FROM: str = {1}"\n'})
    rc, lines = _run(root)
    assert rc == 0 and lines[0].startswith("ok 1 gate constant(s)"), lines


def test_this_tree_yields_the_constants_it_ships():
    found, problems = vgv.collect(str(REPO), "HEAD")
    assert problems == [], problems
    assert {"VALIDATE_GATE_FROM", "UNMATCHED_GATE_FROM"} <= set(found), found
    assert found["UNMATCHED_GATE_FROM"][0] == _UNMATCHED_PATH


def test_check_tag_runs_the_tree_form():
    text = (REPO / "dev-guide/release/check-tag.sh").read_text(encoding="utf-8")
    assert 'validate_gate_version.py" "$VER"' in text
    assert '--repo "$R" "$BRANCH" "$PREV"' in text
    assert 'ck "validate gate version (xxxi)"' in text


# ------------------------------------------------------------ mutations ---

def _mutant(old: str, new: str):
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count(old) == 1, old
    return _load(source.replace(old, new))


def test_mutation_accepting_any_gate_at_the_tag_flips_the_unannounced_row():
    mutant = _mutant("        if before == current:\n            return True, f\"gates since",
                     "        if True:\n            return True, f\"gates since")
    assert vgv.judge("UNMATCHED_GATE_FROM", "1.8.119", "1.8.119", None)[0] is False
    assert mutant.judge("UNMATCHED_GATE_FROM", "1.8.119", "1.8.119", None)[0] is True


def test_mutation_dropping_the_line_scan_lets_a_double_assignment_through():
    text = 'ALIAS = X_GATE_FROM = None\n'
    mutant = _mutant("    if scanned != set(found) and not problems:",
                     "    if False:")
    assert vgv.collect_source("m.py", text)[1] != []
    assert mutant.collect_source("m.py", text)[1] == []
