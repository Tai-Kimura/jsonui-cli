"""Spec-declared hand-written unit cases: the sets must match across faces.

The spec does not generate the body — that was measured and does not reach
the target. It carries the SET, so two faces implementing one screen cannot
quietly diverge: a case renamed on one side and not the other is invisible
until someone reads both trees.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc


def _project(tmp_path, cases, *, ios=True, android=True, unit_dirs=True):
    (tmp_path / "docs" / "screens").mkdir(parents=True)
    spec = {
        "type": "screen",
        "unitContracts": {"target": "ChatViewModel", "cases": cases},
    }
    (tmp_path / "docs" / "screens" / "chat.spec.json").write_text(
        json.dumps(spec), encoding="utf-8"
    )
    platforms = {}
    if ios:
        platforms["ios"] = {"root": "ios"}
        if unit_dirs:
            platforms["ios"]["unitTestsDir"] = "Tests"
        (tmp_path / "ios" / "Tests").mkdir(parents=True)
    if android:
        platforms["android"] = {"root": "android"}
        if unit_dirs:
            platforms["android"]["unitTestsDir"] = "test"
        (tmp_path / "android" / "test").mkdir(parents=True)
    (tmp_path / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens", "platforms": platforms}),
        encoding="utf-8",
    )
    return tmp_path


def _swift(tmp_path, *names):
    body = "\n".join(f"    func {n}() throws {{ }}" for n in names)
    (tmp_path / "ios" / "Tests" / "ChatTests.swift").write_text(
        f"import XCTest\nfinal class ChatTests: XCTestCase {{\n{body}\n}}\n", encoding="utf-8"
    )


def _kotlin(tmp_path, *names):
    body = "\n".join(f"    @Test\n    fun `{n}`() {{ }}" for n in names)
    (tmp_path / "android" / "test" / "ChatTest.kt").write_text(
        f"import org.junit.Test\nclass ChatTest {{\n{body}\n}}\n", encoding="utf-8"
    )


class TestDriftDetection:
    def test_matching_sets_are_clean(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root, "a_case")
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)

    def test_declared_but_not_implemented_is_drift(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root)  # android never wrote it
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert report.missing("android") == ["a_case"]
        assert report.missing("ios") == []

    def test_implemented_but_not_declared_is_drift(self, tmp_path):
        # The direction that matters most: a case added on one face only.
        # Nothing else in the project compares the two trees.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case", "someone_added_this_on_ios_only")
        _kotlin(root, "a_case")
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert report.undeclared("ios") == ["someone_added_this_on_ios_only"]
        assert report.undeclared("android") == []

    def test_declared_for_both_present_on_one(self, tmp_path):
        root = _project(tmp_path, [{"name": "shared", "platforms": ["ios", "android"]}])
        _swift(root, "shared")
        _kotlin(root)
        report = uc.check_unit_contracts(root)
        assert report.missing("android") == ["shared"]

    def test_a_case_naming_one_platform_is_not_demanded_of_the_other(self, tmp_path):
        # `platforms` is a shaping vocabulary, not a default-to-all.
        root = _project(tmp_path, [{"name": "ios_only", "platforms": ["ios"]}])
        _swift(root, "ios_only")
        _kotlin(root)
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)


class TestDenominator:
    def test_a_clean_report_still_names_what_it_read(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}])
        _swift(root, "a_case")
        lines = "\n".join(uc.format_report(uc.check_unit_contracts(root)))
        assert "1 case(s) declared across 1 spec(s) scanned" in lines
        assert "file(s) read" in lines

    def test_an_undeclared_test_root_is_not_checked_rather_than_clean(self, tmp_path):
        # The failure this guards: scanning a directory that does not exist
        # finds nothing, which reads as "every declared case is missing" —
        # or worse, as "nothing drifted" if the declaration is also empty.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}], unit_dirs=False)
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert "ios" in report.unscannable
        assert "NOT CHECKED" in "\n".join(uc.format_report(report))

    def test_no_declarations_at_all_says_so(self, tmp_path):
        root = _project(tmp_path, [])
        report = uc.check_unit_contracts(root)
        lines = "\n".join(uc.format_report(report))
        assert "0 case(s) declared across 1 spec(s) scanned" in lines


class TestStubGeneration:
    def test_a_stub_fails_rather_than_passes(self, tmp_path):
        # A stub that passes is a case reporting success without a body,
        # which is worse than a missing one because it is counted.
        case = uc.UnitCase("chat", "ChatViewModel", "a_case", ("ios",), "keeps the draft")
        assert "XCTFail" in uc.stub_text("ios", "ChatViewModel", [case])
        assert "fail(" in uc.stub_text("android", "ChatViewModel", [case])

    def test_regeneration_keeps_the_body_outside_the_markers(self, tmp_path):
        case = uc.UnitCase("chat", "ChatViewModel", "b_case", ("ios",), "")
        existing = (
            "import XCTest\nfinal class T: XCTestCase {\n"
            + uc.STUB_BEGIN + "\n    func a_case() throws { }\n" + uc.STUB_END
            + "\n    func hand_written() throws { XCTAssertTrue(true) }\n}\n"
        )
        merged = uc.merge_stubs(existing, uc.stub_text("ios", "ChatViewModel", [case]))
        assert "hand_written" in merged
        assert "b_case" in merged
        assert "a_case() throws { }" not in merged

    def test_a_file_without_markers_is_left_alone(self, tmp_path):
        # The author removed them; overwriting on that basis deletes work.
        existing = "final class T: XCTestCase {\n    func mine() throws { }\n}\n"
        case = uc.UnitCase("chat", "ChatViewModel", "x", ("ios",), "")
        assert uc.merge_stubs(existing, uc.stub_text("ios", "T", [case])) == existing


class TestExtraction:
    def test_kotlin_names_come_from_annotated_functions_only(self, tmp_path):
        # A helper `fun` is not a case; counting it would report drift that
        # is not there.
        root = _project(tmp_path, [{"name": "real", "platforms": ["android"]}], ios=False)
        (root / "android" / "test" / "T.kt").write_text(
            "import org.junit.Test\nclass T {\n"
            "    private fun helper() { }\n"
            "    @Test\n    fun `real`() { }\n}\n",
            encoding="utf-8",
        )
        report = uc.check_unit_contracts(root)
        assert report.implemented["android"] == {"real"}
        assert report.ok, uc.format_report(report)
