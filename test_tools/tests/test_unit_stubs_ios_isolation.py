"""The iOS unit stub is declared as branch-tests declares its tests.

`generate unit-stubs` wrote `final class <T>ContractTests: XCTestCase`; under
`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` that is three errors, and a
consumer fixed the line by hand in every new file (30 of 30). branch-tests
already wrote `nonisolated` and `@MainActor` per method — a second
implementation that had moved on. Both now take the declaration from
`swift_isolation`. The compiler arms are in test_unit_stubs_ios_typecheck.py
(they need swiftc 6.2 for `-default-isolation`); these read the text.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from jsonui_test_cli import unit_contracts as uc
from jsonui_test_cli.swift_isolation import TEST_METHOD_ISOLATION, xctest_class_header

PKG = Path(uc.__file__).resolve().parent
CASES = [uc.UnitCase(screen="splash", target="SplashUseCase", name="startsTheSession",
                     platforms=("ios",), intent="starts the session"),
         uc.UnitCase(screen="splash", target="SplashUseCase", name="failsOffline",
                     platforms=("ios",), intent="fails offline")]


def _stub(cases=CASES) -> str:
    return uc.stub_text("ios", "SplashUseCase", cases, module="App")


def test_a_new_file_opens_with_the_shared_declaration():
    lines = _stub().splitlines()
    assert [l for l in lines if "XCTestCase" in l] == [xctest_class_header("SplashUseCaseContractTests")]
    assert xctest_class_header("X") == "nonisolated final class X: XCTestCase {"


def _string_literals(path: Path) -> list[str]:
    """Every str constant in the module, f-string pieces included — what it
    can emit, and not what its comments say."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


#: A piece of a declaration: an f-string splits `class {n}Tests: XCTestCase {`
#: into `class ` and `Tests: XCTestCase {`, so the predicate is one that a
#: single piece satisfies — the control below is how that was found.
_DECLARES = re.compile(r":\s*XCTestCase\b")


def test_neither_generator_spells_the_declaration_itself():
    """One place writes `…: XCTestCase {` — so the next measurement moves
    both generators, not one."""
    for name in ("unit_contracts.py", "branch_tests.py"):
        spelled = [s for s in _string_literals(PKG / name) if _DECLARES.search(s)]
        assert spelled == [], (name, spelled)
        assert "xctest_class_header(" in (PKG / name).read_text(encoding="utf-8"), name


def test_control_the_scan_sees_both_old_spellings():
    """The two generators' spellings before swift_isolation — a plain str
    (unit-stubs) and an f-string (branch-tests) — are both found."""
    for source in ('T = "final class {target}ContractTests: XCTestCase {{\\n"',
                   'x = f"nonisolated final class {pascal}BranchesTest: XCTestCase {{"'):
        tree = ast.parse(source)
        pieces = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert any(_DECLARES.search(p) for p in pieces), (source, pieces)


def test_every_new_stub_method_is_main_actor():
    funcs = [l.strip() for l in _stub().splitlines() if " func " in f" {l.strip()}"]
    assert len(funcs) == len(CASES), funcs
    assert all(f.startswith(f"{TEST_METHOD_ISOLATION} func {uc.IOS_TEST_PREFIX}") for f in funcs), funcs


def test_the_scanner_reads_the_annotated_methods_back():
    """If `--check` could not see an `@MainActor func`, every stub would be
    missing again on the next run and appended a second time."""
    found = uc._swift_test_methods(_stub())
    assert sorted(found) == sorted(uc.IOS_TEST_PREFIX + c.name for c in CASES), found


def _old_file(head: str) -> str:
    return (f"import XCTest\n@testable import App\n\n{head}\n{uc.STUB_BEGIN}\n"
            f"    func {uc.IOS_TEST_PREFIX}startsTheSession() throws {{\n"
            f"        XCTAssertTrue(true)\n    }}\n{uc.STUB_END}\n}}\n")


def test_an_existing_file_keeps_its_class_line_and_its_methods():
    """The declaration is outside the markers: written when the file is
    created, never again. A file from before — the old line, or the line a
    consumer fixed by hand — keeps it; a new case is appended, annotated."""
    for head in ("final class SplashUseCaseContractTests: XCTestCase {",
                 "nonisolated final class SplashUseCaseContractTests: XCTestCase {"):
        existing = _old_file(head)
        merged = uc.merge_stubs(existing, _stub(CASES[1:]))
        assert merged.split(uc.STUB_BEGIN)[0] == existing.split(uc.STUB_BEGIN)[0], head
        assert f"    func {uc.IOS_TEST_PREFIX}startsTheSession() throws {{\n        XCTAssertTrue(true)" in merged
        assert f"    {TEST_METHOD_ISOLATION} func {uc.IOS_TEST_PREFIX}failsOffline() throws" in merged
        assert merged.endswith(f"{uc.STUB_END}\n}}\n")
