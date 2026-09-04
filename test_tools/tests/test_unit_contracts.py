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


def _swift(tmp_path, *names, discoverable=True):
    # XCTest runs only `test`-prefixed methods, so that is what an
    # implementation looks like. `discoverable=False` writes the bare name,
    # which compiles, reads as present, and never runs.
    prefix = "test_" if discoverable else ""
    body = "\n".join(f"    func {prefix}{n}() throws {{ }}" for n in names)
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
        assert "1 case(s) declared across 1 spec file(s) scanned" in lines
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
        assert "0 case(s) declared across 1 spec file(s) scanned" in lines


class TestStubGeneration:
    def test_a_stub_fails_rather_than_passes(self, tmp_path):
        # A stub that passes is a case reporting success without a body,
        # which is worse than a missing one because it is counted.
        case = uc.UnitCase("chat", "ChatViewModel", "a_case", ("ios",), "keeps the draft")
        assert "XCTFail" in uc.stub_text("ios", "ChatViewModel", [case], module="App")
        assert "fail(" in uc.stub_text("android", "ChatViewModel", [case], package="com.x")

    def test_regeneration_keeps_the_body_outside_the_markers(self, tmp_path):
        case = uc.UnitCase("chat", "ChatViewModel", "b_case", ("ios",), "")
        existing = (
            "import XCTest\nfinal class T: XCTestCase {\n"
            + uc.STUB_BEGIN + "\n    func test_a_case() throws { }\n" + uc.STUB_END
            + "\n    func hand_written() throws { XCTAssertTrue(true) }\n}\n"
        )
        merged = uc.merge_stubs(existing, uc.stub_text("ios", "ChatViewModel", [case], module="App"))
        assert "hand_written" in merged
        assert "b_case" in merged
        assert "test_a_case() throws { }" not in merged

    def test_a_file_without_markers_is_left_alone(self, tmp_path):
        # The author removed them; overwriting on that basis deletes work.
        existing = "final class T: XCTestCase {\n    func mine() throws { }\n}\n"
        case = uc.UnitCase("chat", "ChatViewModel", "x", ("ios",), "")
        assert uc.merge_stubs(existing, uc.stub_text("ios", "T", [case], module="App")) == existing


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
        assert "0 spec file(s) carrying a unitContracts block" in "\n".join(uc.format_report(report))


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


class TestAStubMustActuallyRun:
    """The mechanism must not manufacture the failure it prevents.

    Reported as a blocker against 1.8.25: generated ios stubs were named
    exactly as declared, so XCTest — which discovers only `test`-prefixed
    methods — never ran them, while `--check` counted the names as
    implemented and went green. Three declared cases, three "implementations",
    zero executions.

    Third instance of the same family: `implemented` had two states, really
    present and present-but-never-run.
    """

    def test_a_bare_swift_name_is_not_counted_as_implemented(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}], android=False)
        _swift(root, "a_case", discoverable=False)
        report = uc.check_unit_contracts(root)
        assert not report.ok
        assert report.missing("ios") == ["a_case"]
        assert report.undiscoverable.get("ios") == ["a_case"]

    def test_the_prefixed_form_is_counted(self, tmp_path):
        # Positive control for the arm above: the discoverable spelling must
        # still satisfy the declaration, or the guard would just break it.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}], android=False)
        _swift(root, "a_case")
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)

    def test_generated_ios_stubs_carry_the_prefix(self, tmp_path):
        case = uc.UnitCase("chat", "VM", "a_case", ("ios",), "")
        text = uc.stub_text("ios", "VM", [case], module="App")
        assert "func test_a_case()" in text

    def test_ios_stubs_refuse_to_emit_without_a_module(self, tmp_path):
        # `@testable import <class name>` does not compile. Refusing beats
        # emitting a file that cannot build.
        case = uc.UnitCase("chat", "VM", "a_case", ("ios",), "")
        with pytest.raises(uc.UnitContractError) as e:
            uc.stub_text("ios", "VM", [case])
        assert "testModule" in str(e.value)

    def test_android_stubs_refuse_to_emit_without_a_package(self, tmp_path):
        # Compiles either way, but a default-package class drops out of
        # package-scoped test filters — present and not run, again.
        case = uc.UnitCase("chat", "VM", "a_case", ("android",), "")
        with pytest.raises(uc.UnitContractError) as e:
            uc.stub_text("android", "VM", [case])
        assert "testPackage" in str(e.value)

    def test_android_stubs_declare_their_package(self, tmp_path):
        case = uc.UnitCase("chat", "VM", "a_case", ("android",), "")
        text = uc.stub_text("android", "VM", [case], package="com.example.unittests")
        assert text.startswith("package com.example.unittests")


class TestOnlyTestMethodsAreScanned:
    """A file-scope helper is not a mis-named test method.

    Reported against 1.8.26: `--check` flagged a consumer's
    `func settle()` — a free function in their own support file — as NEVER
    RUNS, so the gate was red with nothing wrong. Their point is the reason
    this is not cosmetic: a finding that is always wrong for a legitimate
    shape is worse than no finding, because it teaches the reader to skip
    that line and the next real one goes with it.

    The old scan also looked arity-dependent, which was a second bug wearing
    the first one's clothes: its argument pattern stopped at the first `)`,
    so any helper with a closure parameter escaped by accident.
    """

    def _ios_project(self, tmp_path, support: str, tests: str):
        (tmp_path / "docs" / "screens").mkdir(parents=True)
        (tmp_path / "docs" / "screens" / "s.spec.json").write_text(
            json.dumps({"type": "screen", "unitContracts": {
                "target": "VM", "cases": [{"name": "a_case", "platforms": ["ios"]}]}}),
            encoding="utf-8")
        (tmp_path / "ios" / "Tests").mkdir(parents=True)
        (tmp_path / "ios" / "Tests" / "Support.swift").write_text(support, encoding="utf-8")
        (tmp_path / "ios" / "Tests" / "VMTests.swift").write_text(tests, encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens", "platforms": {
                "ios": {"root": "ios", "unitTestsDir": "Tests", "testModule": "App"}}}),
            encoding="utf-8")
        return tmp_path

    _SUPPORT = (
        "import XCTest\n"
        "func settle() { }\n"                                  # no args — the reported one
        "func servingRoutes(_ r: [Int], _ body: () -> Void) { }\n"   # closure arg
        "func usageRoute(tier: String) -> Int { 0 }\n"
    )
    _TESTS = ("import XCTest\nfinal class VMTests: XCTestCase {\n"
              "    func test_a_case() throws { }\n}\n")

    def test_a_file_scope_helper_is_not_flagged(self, tmp_path):
        root = self._ios_project(tmp_path, self._SUPPORT, self._TESTS)
        report = uc.check_unit_contracts(root)
        assert report.undiscoverable == {}, uc.format_report(report)
        assert report.ok, uc.format_report(report)

    def test_a_bare_method_inside_the_test_class_is_still_flagged(self, tmp_path):
        # Positive control: the guard must keep firing where it was right.
        tests = ("import XCTest\nfinal class VMTests: XCTestCase {\n"
                 "    func a_case() throws { }\n}\n")
        root = self._ios_project(tmp_path, self._SUPPORT, tests)
        report = uc.check_unit_contracts(root)
        assert report.undiscoverable.get("ios") == ["a_case"]

    def test_an_in_class_helper_that_could_never_be_a_test_is_not_flagged(self, tmp_path):
        """Third false positive from this warning, reported by a consumer.

        The rule used to be "scope, not arity" — anything in the class body,
        whatever its signature. That over-fires: XCTest enumerates NO-ARGUMENT,
        NON-PRIVATE INSTANCE methods, so a helper taking a parameter or marked
        `private` cannot be a mis-named test. Its NAME is not what stops it,
        and renaming would not silence the warning — only make the source
        worse to suit the tool.

        The reporter declined to rename round it and said so, which is what
        made the predicate rather than the source the thing to fix. A warning
        the reader can do nothing about is the defect closed in 1.8.27, in a
        new place: the only way to keep using the gate is to stop reading its
        exit code, and then the gate is gone.
        """
        tests = ("import XCTest\nfinal class VMTests: XCTestCase {\n"
                 "    func test_a_case() throws { }\n"
                 "    func withRoutes(_ body: () -> Void) { }\n"          # parameter
                 "    private func loadedViewModel() { }\n"               # private
                 "    static func makeSubject() { }\n}\n")                # not an instance
        root = self._ios_project(tmp_path, self._SUPPORT, tests)
        report = uc.check_unit_contracts(root)
        assert report.undiscoverable == {}, uc.format_report(report)

    def test_xctest_lifecycle_overrides_are_not_flagged(self, tmp_path):
        """`setUp` has no arguments, is not private, and carries no prefix.

        So the reachability rule above admits it — and XCTest calls it on
        every case. Flagging it would report "never runs" about the one method
        that runs most. Found by reading the new predicate rather than from a
        report, which is the whole reason to write the predicate down.
        """
        tests = ("import XCTest\nfinal class VMTests: XCTestCase {\n"
                 "    override func setUp() { }\n"
                 "    override func tearDownWithError() throws { }\n"
                 "    func test_a_case() throws { }\n}\n")
        root = self._ios_project(tmp_path, self._SUPPORT, tests)
        report = uc.check_unit_contracts(root)
        assert report.undiscoverable == {}, uc.format_report(report)

    def test_a_reachable_bare_method_is_still_flagged(self, tmp_path):
        """Positive control for both arms above.

        Without it, "nothing is flagged" would be satisfied by a predicate
        that flags nothing at all — which is how a gate dies quietly rather
        than loudly.
        """
        tests = ("import XCTest\nfinal class VMTests: XCTestCase {\n"
                 "    func test_a_case() throws { }\n"
                 "    func meant_to_be_a_test() throws { }\n}\n")
        root = self._ios_project(tmp_path, self._SUPPORT, tests)
        report = uc.check_unit_contracts(root)
        assert report.undiscoverable.get("ios") == ["meant_to_be_a_test"]


def _split_project(tmp_path, *, sub_blocks, second_sub=False):
    """A parent spec plus sub-specs — the shape a large screen is authored in.

    The parent may not declare `unitContracts` (the merger refuses it), so
    the sub-specs are the only legal home and this is the only fixture that
    exercises the path a split screen actually takes.
    """
    specs = tmp_path / "docs" / "screens"
    (specs / "chat").mkdir(parents=True)
    subs = [{"file": "chat/reco.spec.json"}]
    if second_sub:
        subs.append({"file": "chat/subs.spec.json"})
    (specs / "chat.spec.json").write_text(json.dumps({
        "type": "screen_parent_spec", "version": "1.0",
        "metadata": {"name": "Chat", "displayName": "Chat",
                     "description": "d", "layoutFile": "chat"},
        "subSpecs": subs,
    }), encoding="utf-8")

    def sub(name, block):
        spec = {
            "type": "screen_spec", "version": "1.0",
            "metadata": {"name": name, "displayName": name,
                         "description": "d", "layoutFile": name},
            "structure": {"components": [], "layout": {}},
            "dataFlow": {"viewModel": {"description": "V", "methods": [], "vars": []}},
            "stateManagement": {"uiVariables": [], "eventHandlers": []},
        }
        if block is not None:
            spec["unitContracts"] = block
        return spec

    (specs / "chat" / "reco.spec.json").write_text(
        json.dumps(sub("Reco", sub_blocks[0])), encoding="utf-8")
    if second_sub:
        (specs / "chat" / "subs.spec.json").write_text(
            json.dumps(sub("Subs", sub_blocks[1])), encoding="utf-8")
    (tmp_path / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens"}), encoding="utf-8")
    return tmp_path


class TestSplitScreens:
    """Reported 2026-09-04: a sub-spec's block was read by nobody.

    The consumer's A/B was decisive — the same block, the same command, only
    the file it sits in changes:

        in a sub-spec:  3 case(s) declared across 55 spec(s) (1 carrying)
        in the parent:  6 case(s) declared across 55 spec(s) (2 carrying)

    and the `3 / 1` was a DIFFERENT screen's block. What makes it worse than
    a missing feature is that the output is shaped exactly like the correct
    answer for someone who declared nothing: `--check` then reported
    `missing 0` and exited 0, so the gate agreed the declaration was
    satisfied while never having read it.
    """

    def test_a_sub_spec_block_is_read(self, tmp_path):
        root = _split_project(tmp_path, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}, {"name": "b"}]}])
        cases, scanned, declaring, problems, _files, _unread = uc.discover_unit_contracts(root)
        assert sorted(c.name for c in cases) == ["a", "b"]
        assert problems == []

    def test_the_carrying_count_names_the_screen_that_carries(self, tmp_path):
        """The numerator and the denominator have to agree.

        `declaring` used to be read off the raw file. A parent is forbidden
        from declaring the block, so a split screen reported "0 carrying"
        beside a non-zero case count — a summary line contradicting itself,
        and the line the consumer read to conclude the block was ignored.
        """
        root = _split_project(tmp_path, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}]}])
        cases, scanned, declaring, problems, _files, _unread = uc.discover_unit_contracts(root)
        assert declaring == ["chat"]
        assert len(cases) == 1

    def test_two_sub_specs_contributing_to_one_target_both_land(self, tmp_path):
        root = _split_project(tmp_path, second_sub=True, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}]},
            {"target": "H", "cases": [{"name": "b"}]}])
        cases, _, declaring, problems, _files, _unread = uc.discover_unit_contracts(root)
        assert sorted(c.name for c in cases) == ["a", "b"]
        assert declaring == ["chat"]
        assert problems == []

    def test_a_sub_spec_declaration_that_never_lands_is_named(self, tmp_path,
                                                              monkeypatch):
        """The safety net, for the day the merge stops carrying it.

        `_load_spec` falls back to the unmerged parent whenever jui_cli is
        not importable in the synced tree, and that fallback is silent. The
        whole complaint was that silence here is indistinguishable from
        success, so the sweep now compares what the sub-specs declared
        against what the parent came back with and says so.

        Asserted on the MESSAGE, not just on a non-empty list: a problem line
        that named the wrong file would satisfy `problems != []`.
        """
        root = _split_project(tmp_path, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}]}])

        real = uc._load_spec

        def stripped(path):
            spec = dict(real(path))
            spec.pop("unitContracts", None)
            return spec

        monkeypatch.setattr(uc, "_load_spec", stripped)
        cases, _, declaring, problems, _files, _unread = uc.discover_unit_contracts(root)
        assert cases == []
        assert declaring == []
        assert len(problems) == 1
        assert "chat" in problems[0] and "reco" in problems[0]
        assert "NOT being checked" in problems[0]

    def test_a_split_screen_with_no_block_says_nothing(self, tmp_path):
        """Control for the arm above.

        Without it, the safety net could fire on every split screen and the
        message would be noise rather than a finding — and a warning that is
        always wrong is the defect fixed in 1.8.27, not a fix.
        """
        root = _split_project(tmp_path, sub_blocks=[None])
        cases, _, declaring, problems, _files, _unread = uc.discover_unit_contracts(root)
        assert (cases, declaring, problems) == ([], [], [])


class TestDeclaringDenominatorIsCountedInFiles:
    """`D` counts spec FILES, not screens — so a reader can check it.

    The two units differ by exactly the folding rule: a parent and its
    sub-specs are one screen but several files. Reported in a single line
    beside a file-counted `K`, the screen-counted `D` made `U - D` look like
    a missing declaration, and the mismatch was read as a defect twice (once
    in each direction) before anyone noticed the units were different.

    A file count is reproducible from outside the tool — `grep -l
    unitContracts` over the spec tree returns exactly these files. A screen
    count is not: reproducing it means knowing that a parent absorbs its
    subs, which is precisely the knowledge a reader checking the number does
    not have.
    """

    def _tree(self, tmp_path):
        # Parent + 2 declaring subs (= 1 screen, 2 files), plus 3 standalone
        # declaring specs (= 3 screens, 3 files). Files 5, screens 4.
        root = _split_project(tmp_path, second_sub=True, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}]},
            {"target": "H", "cases": [{"name": "b"}]}])
        for i, name in enumerate(("one", "two", "three")):
            (tmp_path / "docs" / "screens" / f"{name}.spec.json").write_text(
                json.dumps({"type": "screen", "unitContracts": {
                    "target": f"T{i}", "cases": [{"name": f"case_{i}"}]}}),
                encoding="utf-8")
        return root

    def test_the_denominator_counts_files_not_screens(self, tmp_path):
        report = uc.check_unit_contracts(self._tree(tmp_path))
        assert len(report.declaring_files) == 5
        assert len(report.declaring_specs) == 4, "screens still fold; only the report unit changed"
        assert "5 spec file(s) carrying a unitContracts block" in uc.summary_line(report)

    def test_the_file_count_is_what_grep_would_find(self, tmp_path):
        # The property that makes the number checkable from outside.
        root = self._tree(tmp_path)
        specs = root / "docs" / "screens"
        grep = sorted(
            f.relative_to(specs).as_posix()
            for f in specs.rglob("*.spec.json")
            if "unitContracts" in f.read_text(encoding="utf-8")
        )
        report = uc.check_unit_contracts(root)
        assert sorted(report.declaring_files) == grep

    def test_an_unreadable_spec_is_scanned_but_not_counted_as_declaring(self, tmp_path):
        root = self._tree(tmp_path)
        (root / "docs" / "screens" / "broken.spec.json").write_text(
            "{ not json", encoding="utf-8")
        report = uc.check_unit_contracts(root)
        assert len(report.declaring_files) == 5
        assert "broken" in report.scanned_specs, "unreadable is not 'declares nothing'"
        assert any("could not be read" in p for p in report.problems)

    def test_pages_report_the_file_count(self, tmp_path):
        pages = uc.unit_contract_pages(self._tree(tmp_path))
        assert pages["totals"]["specs_declaring"] == 5


class TestUnreadableSpecsAreNamed:
    """A spec that could not be parsed stays in the denominator and is named.

    Keeping it in `scanned` is deliberate — dropping it would make "could not
    be read" indistinguishable from "declares nothing", which is the failure
    this mechanism exists to prevent. But `declaring` counts only files that
    parsed, so an unreadable spec silently widens `scanned - declaring`, and
    the closing line of a generated site would look entirely normal.
    """

    def _tree(self, tmp_path, *, extra_problem=False):
        specs = tmp_path / "docs" / "screens"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / "ok.spec.json").write_text(json.dumps({
            "type": "screen",
            "unitContracts": {"target": "T", "cases": [{"name": "a_case"}]},
        }), encoding="utf-8")
        (specs / "broken.spec.json").write_text("{ not json", encoding="utf-8")
        if extra_problem:
            # A DIFFERENT kind of problem: parses fine, declares badly.
            (specs / "typo.spec.json").write_text(json.dumps({
                "type": "screen",
                "unitContracts": {"target": "U", "cases": [{"name": "b"}],
                                  "caes": "misspelled"},
            }), encoding="utf-8")
        (tmp_path / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens", "platforms": {}}),
            encoding="utf-8")
        return tmp_path

    def test_an_unreadable_spec_is_counted_and_named(self, tmp_path):
        pages = uc.unit_contract_pages(self._tree(tmp_path))
        assert pages["totals"]["specs_scanned"] == 2
        assert pages["totals"]["specs_declaring"] == 1
        assert pages["totals"]["specs_unreadable"] == 1
        assert pages["totals"]["unreadable_files"] == ["broken.spec.json"]

    def test_the_count_is_not_the_number_of_problems(self, tmp_path):
        """The shortcut this exists to forbid.

        `len(problems)` is the tempting stand-in and it is a different
        question: `problems` also carries malformed-block lines. With one
        unreadable file and one badly-declared file it reads 2 where the
        answer is 1, and it would drift again on any new problem kind.
        """
        root = self._tree(tmp_path, extra_problem=True)
        pages = uc.unit_contract_pages(root)
        report = uc.check_unit_contracts(root)
        assert pages["totals"]["specs_unreadable"] == 1
        assert len(report.problems) > 1, "fixture must mix problem kinds or this asserts nothing"
        assert pages["totals"]["specs_unreadable"] != len(report.problems)

    def test_a_clean_tree_reports_none(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}])
        _swift(root, "a_case")
        pages = uc.unit_contract_pages(root)
        assert pages["totals"]["specs_unreadable"] == 0
        assert pages["totals"]["unreadable_files"] == []


class TestUnitContractPages:
    """The grouped-by-target view `document_tools` generates pages from.

    The judgment is not reimplemented there, so these tests are about the
    REGROUPING: that a target owns the right cases, that a face's state is
    per-case and not per-target, and that the two states which look alike
    from a distance stay apart.
    """

    def test_groups_cases_under_their_target_with_per_face_status(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root, "a_case")
        pages = uc.unit_contract_pages(root)
        assert [t["target"] for t in pages["targets"]] == ["ChatViewModel"]
        target = pages["targets"][0]
        assert target["screens"] == ["chat"]
        assert target["cases"][0]["status"] == {"ios": "implemented", "android": "implemented"}
        assert pages["ok"] is True

    def test_a_case_missing_on_one_face_only_is_missing_on_that_face_alone(self, tmp_path):
        # The state the docs ticket exists to make visible: "declared, but
        # implemented on only one side" must be readable off the page.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root)  # android has the file, not the case
        pages = uc.unit_contract_pages(root)
        target = pages["targets"][0]
        assert target["cases"][0]["status"] == {"ios": "implemented", "android": "missing"}
        assert target["faces"]["android"]["missing"] == ["a_case"]
        assert target["faces"]["ios"]["missing"] == []
        assert pages["ok"] is False

    def test_declared_for_one_face_is_not_missing_on_the_other(self, tmp_path):
        # `missing` and `not_declared_for_face` are different facts. Collapsing
        # them would paint an ios-only case red on the android column of a
        # project that is entirely correct.
        root = _project(tmp_path, [{"name": "ios_only", "platforms": ["ios"]}])
        _swift(root, "ios_only")
        _kotlin(root)
        pages = uc.unit_contract_pages(root)
        target = pages["targets"][0]
        assert target["cases"][0]["status"] == {
            "ios": "implemented",
            "android": "not_declared_for_face",
        }
        assert target["faces"]["android"]["declared"] == []
        assert target["faces"]["android"]["missing"] == []
        assert pages["ok"] is True

    def test_undeclared_is_top_level_because_it_belongs_to_no_target(self, tmp_path):
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case", "a_stray")
        _kotlin(root, "a_case")
        pages = uc.unit_contract_pages(root)
        assert pages["undeclared"] == {"ios": ["a_stray"]}
        for target in pages["targets"]:
            for face in target["faces"].values():
                assert "a_stray" not in face["declared"]
                assert "a_stray" not in face["implemented"]

    def test_the_file_reference_comes_from_content_not_from_the_filename(self, tmp_path):
        # The fixture's file is `ChatTests.swift` while the target is
        # `ChatViewModel`, so the naming convention would predict
        # `ChatViewModelContractTests.swift`. Guessing from the name would
        # link to a file that does not exist.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root, "a_case")
        pages = uc.unit_contract_pages(root)
        faces = pages["targets"][0]["faces"]
        assert [Path(p).name for p in faces["ios"]["files"]] == ["ChatTests.swift"]
        assert [Path(p).name for p in faces["android"]["files"]] == ["ChatTest.kt"]

    def test_the_denominator_line_is_the_one_check_prints(self, tmp_path):
        # Requirement 3 of the docs ticket: the index shows the same numbers
        # as `--check`. One call site is the only way that cannot drift.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root, "a_case")
        report = uc.check_unit_contracts(root)
        assert pages_line(root) == uc.format_report(report)[0]

    def test_the_result_is_json_safe(self, tmp_path):
        # document_tools serialises this straight into a template; a set()
        # anywhere raises only at render time, in the caller's repo.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}])
        _swift(root, "a_case")
        pages = uc.unit_contract_pages(root)
        json.dumps(pages)

    def test_a_method_that_never_runs_is_not_reported_as_missing(self, tmp_path):
        # An XCTest method without the `test` prefix exists, compiles, and
        # executes zero times. Calling that `missing` sends the reader to
        # write a test that is already there — and it still will not run.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios"]}])
        _swift(root, "a_case", discoverable=False)
        pages = uc.unit_contract_pages(root)
        target = pages["targets"][0]
        assert target["cases"][0]["status"]["ios"] == "never_runs"
        assert target["faces"]["ios"]["never_runs"] == ["a_case"]
        assert target["faces"]["ios"]["missing"] == []
        assert pages["undiscoverable"]["ios"] == ["a_case"]
        assert pages["ok"] is False

    def test_implementation_files_are_project_relative_never_absolute(self, tmp_path):
        # These paths go into a generated site that consumers commit. An
        # absolute path bakes the developer's home directory — username and
        # all — into it. `_test_roots` resolves its roots, so absolute is what
        # arrives here unless this layer relativises it.
        root = _project(tmp_path, [{"name": "a_case", "platforms": ["ios", "android"]}])
        _swift(root, "a_case")
        _kotlin(root, "a_case")
        pages = uc.unit_contract_pages(root)
        files = [f for t in pages["targets"] for face in t["faces"].values()
                 for f in face["files"]]
        assert files, "fixture produced no file references, so this asserts nothing"
        for path in files:
            assert not Path(path).is_absolute(), path
            assert str(tmp_path) not in path, path
            assert "\\" not in path, path
        assert sorted(files) == ["android/test/ChatTest.kt", "ios/Tests/ChatTests.swift"]

    def test_spec_file_is_relative_to_the_spec_root_and_keeps_nesting(self, tmp_path):
        # The docs site builds a spec page URL from the spec's PATH, so a
        # nested spec cannot be reached from the screen id alone.
        (tmp_path / "docs" / "screens" / "settings").mkdir(parents=True)
        (tmp_path / "docs" / "screens" / "settings" / "profile.spec.json").write_text(
            json.dumps({
                "type": "screen",
                "unitContracts": {"target": "ProfileViewModel",
                                  "cases": [{"name": "a_case", "platforms": ["ios"]}]},
            }),
            encoding="utf-8",
        )
        (tmp_path / "ios" / "Tests").mkdir(parents=True)
        (tmp_path / "jui.config.json").write_text(
            json.dumps({"spec_directory": "docs/screens",
                        "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests"}}}),
            encoding="utf-8",
        )
        pages = uc.unit_contract_pages(tmp_path)
        target = pages["targets"][0]
        assert target["spec_files"] == ["settings/profile.spec.json"]


def pages_line(root):
    return uc.unit_contract_pages(root)["totals"]["summary_line"]
