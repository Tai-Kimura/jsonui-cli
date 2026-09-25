"""The iOS unit stub, typechecked under both default isolations.

A consumer's test target builds with Swift 6 and
`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`, and every new contract-test file
`generate unit-stubs` wrote was three errors there until the class line was
fixed by hand. Here the generated file goes to swiftc in the configurations
that decide it — `-swift-version 6` with `-default-isolation MainActor` and
`nonisolated` — against the macOS SDK's XCTest, with a second file standing
for the app (its types take the same default, as an app built @MainActor
does). The `@testable import` of that app is the one line removed.

⚠️ `-default-isolation` is swiftc 6.2+. CI's compiler job runs 6.1.2
(measured 2026-09-24, run 36051178116), so ci.yml's python-suite ignores this
file and dev-guide/release/run-suites.sh's test_tools leg runs it with the
release machine's toolchain — the same owner as the executed branch runtime.
Without the flag it fails under CI or JSONUI_REQUIRE_DEFAULT_ISOLATION (which
run-suites.sh sets) and skips with the reason elsewhere.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import _toolchain as tc
from jsonui_test_cli import unit_contracts as uc
from jsonui_test_cli.swift_isolation import TEST_METHOD_ISOLATION, xctest_class_header

CASES = [uc.UnitCase(screen="splash", target="SplashUseCase", name="startsTheSession",
                     platforms=("ios",), intent="starts the session")]
APP = "final class SplashUseCase {\n    func run() -> Int { 1 }\n}\n"
#: The body a consumer writes in place of the stub's XCTFail: a call to the app.
FILLED = "XCTAssertEqual(SplashUseCase().run(), 1)"


def _xcrun(*args: str) -> str:
    return subprocess.run(["xcrun", *args], capture_output=True, text=True, timeout=120).stdout.strip()


def _require_default_isolation(tmp_path: Path) -> None:
    tc.tool("xcrun")
    probe = tmp_path / "probe.swift"
    probe.write_text("let x = 1\n", encoding="utf-8")
    run = subprocess.run(["xcrun", "swiftc", "-typecheck", "-default-isolation", "MainActor", str(probe)],
                         capture_output=True, text=True, timeout=300)
    if run.returncode == 0:
        return
    why = (f"swiftc has no -default-isolation (6.2+): {_xcrun('swiftc', '--version').splitlines()[0]}"
           f" — {run.stderr.strip()[:200]}")
    # run-suites.sh sets JSONUI_REQUIRE_DEFAULT_ISOLATION: the release gate
    # owns this arm, and a gate that skips it has no arm.
    if os.environ.get("CI") or os.environ.get("JSONUI_REQUIRE_DEFAULT_ISOLATION"):
        pytest.fail(why)
    pytest.skip(why)


def _stub() -> str:
    text = uc.stub_text("ios", "SplashUseCase", CASES, module="App")
    assert text.count("@testable import App\n") == 1
    return text.replace("@testable import App\n", "")


def _errors(tmp_path: Path, test_source: str, isolation: str) -> list[str]:
    """The distinct errors swiftc reports for the app + the test file."""
    _require_default_isolation(tmp_path)
    (tmp_path / "App.swift").write_text(APP, encoding="utf-8")
    test = tmp_path / "SplashUseCaseContractTests.swift"
    test.write_text(test_source, encoding="utf-8")
    platform = _xcrun("--sdk", "macosx", "--show-sdk-platform-path")
    run = subprocess.run(
        ["xcrun", "swiftc", "-typecheck", "-diagnostic-style", "llvm", "-swift-version", "6",
         "-default-isolation", isolation, "-sdk", _xcrun("--sdk", "macosx", "--show-sdk-path"),
         "-F", f"{platform}/Developer/Library/Frameworks", "-I", f"{platform}/Developer/usr/lib",
         str(tmp_path / "App.swift"), str(test)],
        capture_output=True, text=True, timeout=600)
    errors = sorted({line.split(": error: ", 1)[1] for line in run.stderr.splitlines() if ": error: " in line})
    assert (run.returncode == 0) == (errors == []), run.stderr[:2000]
    return errors


def _filled(source: str) -> str:
    assert source.count('XCTFail("not implemented: starts the session")') == 1
    return source.replace('XCTFail("not implemented: starts the session")', FILLED)


@pytest.mark.parametrize("isolation", ["MainActor", "nonisolated"])
def test_the_generated_stub_type_checks(tmp_path, isolation):
    assert _errors(tmp_path, _stub(), isolation) == []


@pytest.mark.parametrize("isolation", ["MainActor", "nonisolated"])
def test_a_stub_whose_body_calls_the_app_type_checks(tmp_path, isolation):
    assert _errors(tmp_path, _filled(_stub()), isolation) == []


def _before(source: str) -> str:
    """The template before swift_isolation: `final class`, plain `func`."""
    head = xctest_class_header("SplashUseCaseContractTests")
    assert source.count(head) == 1 and source.count(f"{TEST_METHOD_ISOLATION} func ") == 1
    return (source.replace(head, "final class SplashUseCaseContractTests: XCTestCase {")
                  .replace(f"{TEST_METHOD_ISOLATION} func ", "func "))


def test_control_the_old_template_is_the_three_errors_under_mainactor(tmp_path):
    errors = _errors(tmp_path, _before(_stub()), "MainActor")
    assert len(errors) == 3, errors
    assert all("has different actor isolation from nonisolated overridden declaration" in e
               for e in errors), errors
    assert _errors(tmp_path, _before(_stub()), "nonisolated") == []


def test_control_the_method_attribute_is_load_bearing(tmp_path):
    """`nonisolated` alone compiles the stub — and not the body that
    replaces it: the app is MainActor, the method then is not."""
    without = _filled(_stub()).replace(f"{TEST_METHOD_ISOLATION} func ", "func ")
    errors = _errors(tmp_path, without, "MainActor")
    assert len(errors) == 1 and "main actor-isolated" in errors[0], errors
