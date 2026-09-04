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
        cases, scanned, declaring, problems = uc.discover_unit_contracts(root)
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
        cases, scanned, declaring, problems = uc.discover_unit_contracts(root)
        assert declaring == ["chat"]
        assert len(cases) == 1

    def test_two_sub_specs_contributing_to_one_target_both_land(self, tmp_path):
        root = _split_project(tmp_path, second_sub=True, sub_blocks=[
            {"target": "H", "cases": [{"name": "a"}]},
            {"target": "H", "cases": [{"name": "b"}]}])
        cases, _, declaring, problems = uc.discover_unit_contracts(root)
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
        cases, _, declaring, problems = uc.discover_unit_contracts(root)
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
        cases, _, declaring, problems = uc.discover_unit_contracts(root)
        assert (cases, declaring, problems) == ([], [], [])
