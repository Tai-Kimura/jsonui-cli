"""A unit case is declared for a target, and implemented only by a test of
that target.

`--check` compared the set of case NAMES declared for a platform with the set
implemented on it. A name several targets declare is one name there, so one
test anywhere answered for all of them: with the case declared for three
view models, deleting it from one view model's tests still read `missing 0`
and exited 0. A rule that asks every screen for the same case produces
exactly that shape, so the more such a rule was applied, the less the gate
checked it.

A test's target is read from the names `generate` gives a target's stubs —
its class (ios, android) or outermost describe (web), else its file. A test
no such name places still belongs to the only target declaring its case
name; for a name several targets declare it could be any of theirs, and is
reported as such instead of counting as an implementation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jsonui_test_cli import unit_contracts as uc

SHARED = "teardown_cancelsPendingWork"
TARGETS = ("AlphaViewModel", "BetaViewModel", "GammaViewModel")
PLATFORMS = ("ios", "android", "web")


def _own(target: str) -> str:
    return f"{target[:-len('ViewModel')].lower()}_loadsItsFirstPage"


def _project(root: Path, platform: str, declared=None) -> Path:
    """Three screens, one target each; every target declares SHARED and a case
    of its own, and the project builds *platform*. *declared* overrides a
    target's names."""
    specs = root / "docs" / "screens"
    specs.mkdir(parents=True)
    for target in TARGETS:
        names = (declared or {}).get(target, (SHARED, _own(target)))
        (specs / f"{target.lower()}.spec.json").write_text(json.dumps({
            "type": "screen",
            "unitContracts": {"target": target, "cases": [{"name": n} for n in names]},
        }), encoding="utf-8")
    platforms = {platform: {"root": platform, "unitTestsDir": "tests",
                            "testModule": "App", "testPackage": "app"}}
    (root / platform / "tests").mkdir(parents=True)
    (root / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens", "platforms": platforms}), encoding="utf-8")
    return root


def _container(platform: str, name: str, cases) -> str:
    """One class (ios, android) or top-level describe (web) holding *cases*."""
    if platform == "ios":
        body = "\n".join(f"    func test_{c}() throws {{ }}" for c in cases)
        return f"final class {name}: XCTestCase {{\n{body}\n}}\n"
    if platform == "android":
        body = "\n".join(f"    @Test\n    fun `{c}`() {{ }}" for c in cases)
        return f"class {name} {{\n{body}\n}}\n"
    body = "\n".join(f"  it('{c}', () => {{}});" for c in cases)
    return f"describe('{name}', () => {{\n{body}\n}});\n"


HEAD = {"ios": "import XCTest\n", "android": "import org.junit.Test\n", "web": ""}


def _file(root: Path, platform: str, filename: str, *containers) -> None:
    text = HEAD[platform] + "".join(_container(platform, n, cs) for n, cs in containers)
    (root / platform / "tests" / filename).write_text(text, encoding="utf-8")


def _stub_file(platform: str, target: str) -> str:
    return uc._STUB_FILENAME[platform].format(target=target)


def _stub_class(platform: str, target: str) -> str:
    return uc._STUB_CONTAINER[platform].format(target=target)


def _each_target(root: Path, platform: str, cases_of=None) -> None:
    """Every target's cases in the class and file generate would give it."""
    for target in TARGETS:
        cases = (cases_of or {}).get(target, (SHARED, _own(target)))
        _file(root, platform, _stub_file(platform, target), (_stub_class(platform, target), cases))


def _check(root: Path, platform: str):
    report = uc.check_unit_contracts(root)
    # Every declared pair is exactly one of implemented, missing, unattributed.
    declared = len(report.declared_pairs[platform])
    assert declared == (report.implemented_count(platform) + report.missing_count(platform)
                        + report.unattributed_count(platform)), uc.format_report(report)
    return report


def _lines(report, platform: str) -> list[str]:
    out, inside = [], False
    for line in uc.format_report(report):
        if line.startswith(f"  {platform}:"):
            inside = True
        elif line.startswith("  ") and not line.startswith("    "):
            inside = False
        if inside:
            out.append(line.strip())
    return out


# --------------------------------------------------------------- the defect


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_pair_implemented_is_clean(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform)
    report = _check(root, platform)
    assert report.missing(platform) == [] and report.ok, uc.format_report(report)
    assert report.implemented_count(platform) == 6


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_shared_case_one_target_lost_is_missing_for_that_target(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform, {"BetaViewModel": (_own("BetaViewModel"),)})
    report = _check(root, platform)
    assert report.missing_pairs(platform) == [("BetaViewModel", SHARED)]
    assert report.missing(platform) == [SHARED]
    assert not report.ok
    assert f"MISSING     {SHARED}  (declared for BetaViewModel, no test of BetaViewModel " \
           f"implements it)" in _lines(report, platform)
    assert _lines(report, platform)[0].startswith(
        f"{platform}: declared 6, implemented 5, missing 1, undeclared 0")


@pytest.mark.parametrize("platform", PLATFORMS)
def test_control_a_case_only_one_target_declares_is_missing_when_lost(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform, {"BetaViewModel": (SHARED,)})
    report = _check(root, platform)
    assert report.missing_pairs(platform) == [("BetaViewModel", _own("BetaViewModel"))]
    assert not report.ok


# ------------------------------------------ what places a test in a target


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_class_or_describe_places_a_test_whatever_its_file(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform)
    (root / platform / "tests" / _stub_file(platform, "BetaViewModel")).unlink()
    _file(root, platform, "renamed" + uc.PLATFORM_TEST_SUFFIX[platform],
          (_stub_class(platform, "BetaViewModel"), (SHARED, _own("BetaViewModel"))))
    report = _check(root, platform)
    assert report.ok, uc.format_report(report)
    assert report.implemented_count(platform) == 6


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_file_places_a_test_whose_class_names_no_target(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform)
    _file(root, platform, _stub_file(platform, "BetaViewModel"),
          ("SomethingElse", (SHARED, _own("BetaViewModel"))))
    report = _check(root, platform)
    assert report.ok, uc.format_report(report)
    # `ok` alone does not tell: a test no name places is not a failure.
    assert (report.implemented_count(platform), report.unattributed_count(platform)) == (6, 0)


def test_the_outermost_describe_places_a_web_test(tmp_path):
    root = _project(tmp_path, "web")
    _each_target(root, "web", {"BetaViewModel": (_own("BetaViewModel"),)})
    (root / "web" / "tests" / "beta_offline.test.ts").write_text(
        "describe('BetaViewModel', () => {\n"
        "  describe('while offline', () => {\n"
        f"    it('{SHARED}', () => {{}});\n"
        "  });\n});\n", encoding="utf-8")
    report = _check(root, "web")
    assert (report.implemented_count("web"), report.unattributed_count("web")) == (6, 0), \
        uc.format_report(report)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_generated_stub_is_placed_in_its_target(tmp_path, platform):
    # What `generate` writes is what `--check` reads a target from: stubs for
    # a project with no tests at all make every pair implemented.
    root = _project(tmp_path, platform)
    written = uc.write_stubs(root, uc.check_unit_contracts(root))
    assert sum(n for _path, _action, n in written) == 6
    report = _check(root, platform)
    assert report.implemented_count(platform) == 6


#: A stub as `stub_text` writes it, one case: from its signature line up to
#: the blank line or the marker that follows it.
STUB_OF = {
    "ios": r"    @MainActor func test_{name}\(\) throws \{{\n.*?\n    \}}\n\n?",
    "android": r"    @Test\n    fun `{name}`\(\) \{{\n.*?\n    \}}\n\n?",
    "web": r"  it\('{name}', .*?\n  \}}\);\n\n?",
}


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_stub_is_written_for_the_target_that_lost_a_shared_case(tmp_path, platform):
    import re
    root = _project(tmp_path, platform)
    uc.write_stubs(root, uc.check_unit_contracts(root))
    beta = root / platform / "tests" / _stub_file(platform, "BetaViewModel")
    text = beta.read_text(encoding="utf-8")
    pattern = STUB_OF[platform].format(name=SHARED)
    assert len(re.findall(pattern, text, flags=re.S)) == 1, text
    beta.write_text(re.sub(pattern, "", text, flags=re.S), encoding="utf-8")
    assert _check(root, platform).missing_pairs(platform) == [("BetaViewModel", SHARED)]
    written = uc.write_stubs(root, uc.check_unit_contracts(root))
    assert [(Path(p).name, a, n) for p, a, n in written if n] == [
        (_stub_file(platform, "BetaViewModel"), "updated", 1)]
    assert _check(root, platform).implemented_count(platform) == 6


# ------------------------------------- tests no target's name places


@pytest.mark.parametrize("platform", PLATFORMS)
def test_as_many_unplaced_tests_as_targets_are_named_not_counted(tmp_path, platform):
    # Each target's own case where generate would put it; SHARED in three
    # containers whose names are no target's.
    root = _project(tmp_path, platform)
    _each_target(root, platform, {t: (_own(t),) for t in TARGETS})
    _file(root, platform, "lifecycle" + uc.PLATFORM_TEST_SUFFIX[platform],
          *[(f"Lifecycle{i}", (SHARED,)) for i in range(3)])
    report = _check(root, platform)
    assert report.ok, uc.format_report(report)
    assert report.unattributed(platform) == [SHARED]
    assert report.unattributed_count(platform) == 3
    assert report.implemented_count(platform) == 3
    lines = _lines(report, platform)
    assert lines[0].startswith(f"{platform}: declared 6, implemented 3, missing 0, "
                               "undeclared 0, unattributed 3")
    [line] = [l for l in lines if l.startswith("UNATTRIBUTED")]
    assert "AlphaViewModel, BetaViewModel, GammaViewModel" in line
    pages = uc.unit_contract_pages(root)
    [beta] = [t for t in pages["targets"] if t["target"] == "BetaViewModel"]
    [case] = [c for c in beta["cases"] if c["name"] == SHARED]
    assert case["status"][platform] == uc.CASE_UNATTRIBUTED


@pytest.mark.parametrize("platform", PLATFORMS)
def test_fewer_unplaced_tests_than_targets_is_missing_the_difference(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform, {t: (_own(t),) for t in TARGETS})
    _file(root, platform, "lifecycle" + uc.PLATFORM_TEST_SUFFIX[platform],
          ("Lifecycle", (SHARED,)))
    report = _check(root, platform)
    assert not report.ok
    assert report.missing(platform) == [SHARED]
    assert report.missing_count(platform) == 2 and report.unattributed_count(platform) == 1
    assert any("at least 2 of them have none" in l for l in _lines(report, platform))


@pytest.mark.parametrize("platform", PLATFORMS)
def test_control_an_unplaced_test_of_a_case_one_target_declares_is_its(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform, {t: (SHARED,) for t in TARGETS})
    _file(root, platform, "misc" + uc.PLATFORM_TEST_SUFFIX[platform],
          ("Misc", tuple(_own(t) for t in TARGETS)))
    report = _check(root, platform)
    assert report.ok, uc.format_report(report)
    assert report.implemented_count(platform) == 6


# ------------------------------------ a test in a target that does not declare it


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_test_in_a_target_that_does_not_declare_its_case_fails_alone(tmp_path, platform):
    # Every declared pair implemented; Gamma, which does not declare SHARED,
    # also has a test of it.
    root = _project(tmp_path, platform, {"GammaViewModel": (_own("GammaViewModel"),)})
    _each_target(root, platform)
    report = _check(root, platform)
    assert report.missing(platform) == [] and report.undeclared(platform) == []
    assert report.misplaced[platform] == [("GammaViewModel", SHARED)]
    assert not report.ok


@pytest.mark.parametrize("platform", PLATFORMS)
def test_a_case_implemented_in_a_target_that_does_not_declare_it_is_undeclared_there(
        tmp_path, platform):
    # Gamma does not declare SHARED; its tests implement it. Alpha's own case
    # is implemented only in Beta's tests.
    root = _project(tmp_path, platform, {"GammaViewModel": (_own("GammaViewModel"),)})
    _each_target(root, platform, {
        "AlphaViewModel": (SHARED,),
        "BetaViewModel": (SHARED, _own("BetaViewModel"), _own("AlphaViewModel")),
    })
    report = _check(root, platform)
    assert report.misplaced[platform] == [("BetaViewModel", _own("AlphaViewModel")),
                                          ("GammaViewModel", SHARED)]
    assert report.missing_pairs(platform) == [("AlphaViewModel", _own("AlphaViewModel"))]
    assert not report.ok
    assert f"UNDECLARED  {SHARED}  (implemented in GammaViewModel's tests, which does not " \
           f"declare it — another target does)" in _lines(report, platform)


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_page_of_the_target_that_lost_the_case_says_missing(tmp_path, platform):
    root = _project(tmp_path, platform)
    _each_target(root, platform, {"BetaViewModel": (_own("BetaViewModel"),)})
    pages = {t["target"]: t for t in uc.unit_contract_pages(root)["targets"]}
    status = {name: {c["name"]: c["status"][platform] for c in pages[name]["cases"]}
              for name in TARGETS}
    assert status["BetaViewModel"][SHARED] == uc.CASE_MISSING
    assert status["AlphaViewModel"][SHARED] == uc.CASE_IMPLEMENTED
    assert pages["BetaViewModel"]["faces"][platform]["missing"] == [SHARED]
    assert pages["AlphaViewModel"]["faces"][platform]["files"] == [
        f"{platform}/tests/{_stub_file(platform, 'AlphaViewModel')}"]
