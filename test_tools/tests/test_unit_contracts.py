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


class TestATypoCannotDeleteTheDeclaration:
    """A mechanism that exists to stop drift must not be removable by one
    misspelled key.

    Measured on the shipped 1.8.24: `"caes"` for `"cases"` made the block
    vanish, `--check` printed "0 case(s) declared" and exited 0, and
    `validate spec` printed 0 errors. Neither output was false — the block
    really did declare nothing readable — which is exactly why it was
    dangerous. Found by a face before it had written a single declaration.
    """

    def _spec(self, tmp_path, block):
        (tmp_path / "docs" / "screens").mkdir(parents=True)
        (tmp_path / "docs" / "screens" / "chat.spec.json").write_text(
            json.dumps({"type": "screen", "unitContracts": block}), encoding="utf-8"
        )
        (tmp_path / "ios" / "Tests").mkdir(parents=True)
        (tmp_path / "jui.config.json").write_text(
            json.dumps({
                "spec_directory": "docs/screens",
                "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests"}},
            }),
            encoding="utf-8",
        )
        return tmp_path

    def test_a_misspelled_cases_key_is_named_not_ignored(self, tmp_path):
        root = self._spec(tmp_path, {"target": "VM", "caes": [{"name": "x"}]})
        report = uc.check_unit_contracts(root)
        assert not report.ok
        joined = "\n".join(uc.format_report(report))
        assert "unknown key 'caes'" in joined
        assert "drops the declaration" in joined

    def test_a_block_that_reads_as_empty_is_called_out(self, tmp_path):
        # The aggregate guard: even if the specific typo were not enumerable,
        # "specs carry the key and zero cases came out" is itself the signal.
        root = self._spec(tmp_path, {"target": "VM", "cases": []})
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert "no case could be read" in "\n".join(uc.format_report(report))

    def test_a_misspelled_case_key_is_named(self, tmp_path):
        root = self._spec(tmp_path, {"target": "VM", "cases": [{"nmae": "x"}]})
        report = uc.check_unit_contracts(root)
        assert not report.ok
        joined = "\n".join(uc.format_report(report))
        assert "unknown key 'nmae'" in joined
        assert "'name' is missing" in joined

    def test_wrong_types_are_named_rather_than_skipped(self, tmp_path):
        root = self._spec(tmp_path, {"target": "VM", "cases": "not-an-array"})
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert "'cases' must be an array" in "\n".join(uc.format_report(report))

    def test_a_missing_target_is_named(self, tmp_path):
        root = self._spec(tmp_path, {"cases": [{"name": "x", "platforms": ["ios"]}]})
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert "'target' is missing" in "\n".join(uc.format_report(report))

    def test_a_project_that_declares_nothing_at_all_is_still_clean(self, tmp_path):
        # Positive control. The guard fires on "carries the key but reads as
        # empty", NOT on "has no unitContracts anywhere" — otherwise every
        # project without the feature would fail.
        (tmp_path / "docs" / "screens").mkdir(parents=True)
        (tmp_path / "docs" / "screens" / "chat.spec.json").write_text(
            json.dumps({"type": "screen"}), encoding="utf-8"
        )
        (tmp_path / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens", "platforms": {}}), encoding="utf-8"
        )
        report = uc.check_unit_contracts(tmp_path)
        assert report.ok, uc.format_report(report)
        assert "0 carrying a unitContracts block" in "\n".join(uc.format_report(report))


class TestZeroWithTwoMeanings:
    """`missing == 0` is two opposite facts: everything is implemented, or
    nothing was compared.

    Reported against 1.8.24: with the test directory absent, `--check` said
    NOT CHECKED and failed while `--dry-run` said "every declared case has an
    implementation" and exited 0, about the same tree with zero
    implementations. `--dry-run` is the first command anyone runs, so a
    mistyped unitTestsDir read as "done".
    """

    def _declared_but_no_dir(self, tmp_path):
        (tmp_path / "docs" / "screens").mkdir(parents=True)
        (tmp_path / "docs" / "screens" / "a.spec.json").write_text(
            json.dumps({"type": "screen", "unitContracts": {
                "target": "VM", "cases": [{"name": "a_case", "platforms": ["android"]}]}}),
            encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens", "platforms": {
                "android": {"root": "android", "unitTestsDir": "does/not/exist"}}}),
            encoding="utf-8")
        return tmp_path

    def test_an_absent_directory_is_not_checked_not_complete(self, tmp_path):
        report = uc.check_unit_contracts(self._declared_but_no_dir(tmp_path))
        assert not report.ok
        assert "android" in report.unscannable

    def test_write_stubs_produces_nothing_for_a_platform_it_cannot_scan(self, tmp_path):
        # The mechanism behind the wrong claim: no work is produced, which
        # the caller then has to be careful not to read as "no work needed".
        report = uc.check_unit_contracts(self._declared_but_no_dir(tmp_path))
        assert uc.write_stubs(tmp_path, report, dry_run=True) == []

    def test_the_absent_directory_message_names_both_causes(self, tmp_path):
        # git does not track empty directories, so a fresh clone of a project
        # that has declared but not yet generated looks identical to a typo.
        report = uc.check_unit_contracts(self._declared_but_no_dir(tmp_path))
        text = "\n".join(uc.format_report(report))
        assert "before its first stub is generated" in text
        assert "suspecting the path" in text
