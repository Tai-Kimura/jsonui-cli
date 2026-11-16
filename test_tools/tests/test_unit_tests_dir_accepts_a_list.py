"""`unitTestsDir` names one directory or several.

A face that keeps hand-written tests in more than one place could not say so:
the key took a single directory, so the choice was to point at one and lose
the rest, or to point at a parent and pull in the GENERATED stubs — which then
count as implementations of the cases they were generated from, and the check
compares a tree against itself.

A list rather than an exclusion pattern: excluding has to guess what to skip,
and the project already knows what it keeps where. Ruled that way by the user.

Three properties are load-bearing and each has an arm:

  every listed directory is scanned          (not just the first)
  a single STRING behaves exactly as before  (six faces ship that spelling)
  a listed directory that does not exist makes the platform UNSCANNABLE

The third is the one worth arguing about. Scanning the directories that exist
and skipping the missing one would raise the count — the surviving directories
still contribute — so a typo would read as "more implementations found", which
is indistinguishable from working. The existing rule for a single missing
directory is already "unscannable, not complete"; a list keeps it.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc


def _swift_test(target: str, *case_names: str) -> str:
    body = "\n".join(f"    func test_{n}() throws {{}}" for n in case_names)
    return (f"import XCTest\n@testable import App\n"
            f"final class {target}ContractTests: XCTestCase {{\n{body}\n}}\n")


def _project(tmp_path, unit_dir, *, cases=("alpha", "beta"), dirs=("hand",)):
    """A project declaring `cases`, with `dirs` created under ios/."""
    (tmp_path / "docs" / "screens").mkdir(parents=True)
    (tmp_path / "docs" / "screens" / "chat.spec.json").write_text(json.dumps({
        "type": "screen",
        "unitContracts": {
            "target": "ChatViewModel",
            "cases": [{"name": c, "platforms": ["ios"]} for c in cases],
        },
    }), encoding="utf-8")
    for d in dirs:
        (tmp_path / "ios" / d).mkdir(parents=True, exist_ok=True)
    (tmp_path / "jui.config.json").write_text(json.dumps({
        "spec_directory": "docs/screens",
        "platforms": {"ios": {"root": "ios", "unitTestsDir": unit_dir,
                              "testModule": "App"}},
    }), encoding="utf-8")
    return tmp_path


def test_both_declared_directories_are_scanned(tmp_path):
    root = _project(tmp_path, ["hand", "contracts"], dirs=("hand", "contracts"))
    (root / "ios" / "hand" / "AContractTests.swift").write_text(
        _swift_test("Chat", "alpha"), encoding="utf-8")
    (root / "ios" / "contracts" / "BContractTests.swift").write_text(
        _swift_test("Chat", "beta"), encoding="utf-8")

    report = uc.check_unit_contracts(root)
    assert report.unscannable == {}, report.unscannable
    # The union, not whichever directory sorted first.
    assert report.implemented["ios"] == {"alpha", "beta"}
    assert len(report.scanned_files["ios"]) == 2


def test_a_case_in_an_undeclared_directory_is_not_found(tmp_path):
    """The widening must not become "scan everything under root"."""
    root = _project(tmp_path, ["hand"], dirs=("hand", "elsewhere"))
    (root / "ios" / "hand" / "AContractTests.swift").write_text(
        _swift_test("Chat", "alpha"), encoding="utf-8")
    (root / "ios" / "elsewhere" / "BContractTests.swift").write_text(
        _swift_test("Chat", "beta"), encoding="utf-8")

    report = uc.check_unit_contracts(root)
    assert report.implemented["ios"] == {"alpha"}
    assert not report.ok  # beta is still missing, and says so


def test_a_single_string_behaves_exactly_as_before(tmp_path):
    """The population this change is not for: every shipping face."""
    root = _project(tmp_path, "hand", dirs=("hand",))
    (root / "ios" / "hand" / "AContractTests.swift").write_text(
        _swift_test("Chat", "alpha", "beta"), encoding="utf-8")

    report = uc.check_unit_contracts(root)
    assert report.unscannable == {}
    assert report.implemented["ios"] == {"alpha", "beta"}
    assert report.ok


def test_a_missing_entry_makes_the_platform_unscannable(tmp_path):
    """The dangerous shape: the surviving directory would still find cases,
    so the count goes UP and the typo reads as progress."""
    root = _project(tmp_path, ["hand", "typo_dir"], dirs=("hand",))
    (root / "ios" / "hand" / "AContractTests.swift").write_text(
        _swift_test("Chat", "alpha", "beta"), encoding="utf-8")

    report = uc.check_unit_contracts(root)
    assert "ios" in report.unscannable, (
        "a directory that does not exist was skipped in silence; the other "
        "directory's finds would then read as the whole answer")
    assert "typo_dir" in report.unscannable["ios"]
    assert not report.ok
    # And it must not ALSO claim the cases are implemented.
    assert not report.implemented.get("ios")


def test_the_message_names_which_entry_is_missing(tmp_path):
    root = _project(tmp_path, ["hand", "typo_dir", "other_typo"], dirs=("hand",))
    report = uc.check_unit_contracts(root)
    message = report.unscannable["ios"]
    assert "typo_dir" in message and "other_typo" in message, message
    assert "hand" not in message.replace("typo_dir", "").replace("other_typo", ""), (
        f"the directory that DOES exist is named as missing: {message}")


def test_an_empty_list_is_distinguishable_from_an_absent_key(tmp_path):
    root = _project(tmp_path, [], dirs=())
    report = uc.check_unit_contracts(root)
    assert "ios" in report.unscannable
    assert "empty list" in report.unscannable["ios"], report.unscannable["ios"]


def test_stubs_are_written_to_the_first_declared_directory(tmp_path):
    """Where new work lands must not move for a project that lists one."""
    root = _project(tmp_path, ["hand", "contracts"], dirs=("hand", "contracts"))
    report = uc.check_unit_contracts(root)
    uc.write_stubs(root, report)

    first = list((root / "ios" / "hand").glob("*.swift"))
    second = list((root / "ios" / "contracts").glob("*.swift"))
    assert first, "no stub was written to the first declared directory"
    assert not second, (
        f"a stub was also written to {second} — the same case would then "
        "exist twice and each copy would count as an implementation")


def test_totals_are_the_sum_over_the_declared_directories(tmp_path):
    """The control the reporting face asked for: two directories, and the
    denominator is their sum rather than either one alone."""
    root = _project(tmp_path, ["hand", "contracts"],
                    cases=("alpha", "beta", "gamma"),
                    dirs=("hand", "contracts"))
    (root / "ios" / "hand" / "AContractTests.swift").write_text(
        _swift_test("Chat", "alpha", "beta"), encoding="utf-8")
    (root / "ios" / "contracts" / "BContractTests.swift").write_text(
        _swift_test("Chat", "gamma"), encoding="utf-8")

    report = uc.check_unit_contracts(root)
    assert report.implemented["ios"] == {"alpha", "beta", "gamma"}
    assert len(report.scanned_files["ios"]) == 2
    assert report.ok
