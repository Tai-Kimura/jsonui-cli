"""A new screen's ViewModel / UseCase / Repository scaffolds compile as `jui g
project` and one `jui build` leave them: iOS (swiftc, iOS Simulator SDK, Swift
5 and Swift 6) and Android (kotlinc). Ticket
jui-g-project-new-screen-stubs-do-not-compile: in the reporting consumer three new screens were
rc=65 on xcodebuild and 394 errors on compileDevDebugKotlin.

Compiled to an object, not -typecheck: "return from initializer without
initializing all stored properties" is definite initialisation, which
-typecheck never runs. Swift 6 with `-default-isolation MainActor` (the consumer's
setting) is test_new_screen_stubs_compile_mainactor.py: CI's compiler job's
swiftc predates the flag. The project is the shape _new_screen_stubs.py
writes; what it stands in for, and why, is said there.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import _new_screen_stubs as ns
from tests import _toolchain as tc


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    return ns.write_project(tmp_path_factory.mktemp("stubs") / "app")


def _xcrun(*args: str) -> str:
    return subprocess.run(["xcrun", *args], capture_output=True, text=True, timeout=120).stdout.strip()


def swift_errors(project: Path, tmp: Path, *flags: str) -> list[str]:
    """The distinct errors swiftc reports for the scaffolds (and the exit code, asserted against them)."""
    tc.tool("xcrun")
    sdk = _xcrun("--sdk", "iphonesimulator", "--show-sdk-path")
    assert sdk, "no iOS Simulator SDK: the scaffolds import UIKit"
    target = ["-sdk", sdk, "-target", "arm64-apple-ios17.0-simulator"]
    scratch = tmp / "swift-tmp"
    scratch.mkdir(exist_ok=True)
    env = {**os.environ, "TMPDIR": f"{scratch}/"}
    shim = tmp / "SwiftJsonUI.swift"
    shim.write_text(ns.SWIFTJSONUI_SHIM, encoding="utf-8")
    module = subprocess.run(["xcrun", "swiftc", "-emit-module", "-parse-as-library", "-module-name", "SwiftJsonUI",
                             *target, "-emit-module-path", str(tmp / "SwiftJsonUI.swiftmodule"), str(shim)],
                            capture_output=True, text=True, timeout=600, env=env)
    assert module.returncode == 0, module.stderr[-2000:]
    run = subprocess.run(["xcrun", "swiftc", "-c", "-wmo", "-parse-as-library", "-module-name", "StubFix", *target,
                          "-I", str(tmp), *flags, "-o", str(tmp / "out.o"), *map(str, ns.swift_sources(project))],
                         capture_output=True, text=True, timeout=900, env=env)
    errors = sorted({line.split(str(project) + "/", 1)[-1] for line in (run.stdout + run.stderr).splitlines()
                     if ": error:" in line})
    assert (run.returncode == 0) == (not errors), f"rc={run.returncode} {errors}\n{run.stderr[-2000:]}"
    return errors


def kotlin_errors(project: Path, tmp: Path) -> list[str]:
    kotlinc = tc.tool("kotlinc")
    shims = tmp / "kshims"
    shims.mkdir(exist_ok=True)
    for name, text in ns.KOTLIN_SHIMS.items():
        (shims / name).write_text(text, encoding="utf-8")
    run = subprocess.run([kotlinc, *map(str, ns.kotlin_sources(project)), *map(str, sorted(shims.glob("*.kt"))),
                          "-d", str(tmp / "kout")], capture_output=True, text=True, timeout=900)
    out = run.stdout + run.stderr
    errors = sorted({line.split(str(project) + "/", 1)[-1] for line in out.splitlines() if "error:" in line})
    assert (run.returncode == 0) == (not errors), f"rc={run.returncode} {errors}\n{out[-2000:]}"   # the exit code, not a word
    return errors


@pytest.mark.parametrize("version", ["5", "6"])
def test_the_ios_scaffolds_compile(project, tmp_path, version):
    assert swift_errors(project, tmp_path, "-swift-version", version) == []


def test_the_android_scaffolds_compile(project, tmp_path):
    assert kotlin_errors(project, tmp_path) == []


def test_the_project_has_every_shape_bar_had(project):
    """The arm reaches what it claims: each shape that did not compile for the consumer is in the scaffolds it compiles."""
    vm = (project / ns.SWIFT / "ViewModel/StubIntroViewModel.swift").read_text(encoding="utf-8")
    assert "let isRetry: Bool = false" in vm and "let termsURL: URL = " in vm       # readOnly, with and without a default
    assert "var item: StubItem = " in vm and "var lastSeen: Date = " in vm         # an app type, not observable
    assert "private let useCase = StubIntroUseCase()" in vm                          # a UseCase made in a default value
    kt = (project / ns.KOTLIN / "viewmodels/StubIntroViewModel.kt").read_text(encoding="utf-8")
    assert "MutableStateFlow<StubIntroData>" in kt and "MutableStateFlow<StubItem>" in kt
    assert "override val termsURL" not in kt   # iOS-only in the spec
    uc = (project / ns.KOTLIN / "usecase/StubIntroUseCase.kt").read_text(encoding="utf-8")
    assert "suspend fun start(version: Int): StubStartResult" in uc
    for name in ns.SCREENS:   # kjui writes updateData (and its `update` import) only between the pair
        text = (project / ns.KOTLIN / f"viewmodels/{name}ViewModel.kt").read_text(encoding="utf-8")
        assert text.count("    // >>> GENERATED_CODE_START\n    // >>> GENERATED_CODE_END\n") == 1, name
