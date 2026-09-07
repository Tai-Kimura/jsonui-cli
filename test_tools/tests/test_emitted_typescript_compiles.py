"""The emitted TypeScript is handed to a compiler, not just to `assert in`.

Every other check on this generator's TS output compares strings. A string
assert cannot tell a well-formed reference from a dangling one, and this
project has shipped exactly that: four defects in one release lived on paths
whose only gate was text. The Swift side measured the same boundary from the
other direction — `swiftc -parse` accepted a property nothing declares
calling a method that exists nowhere, and only `-typecheck` rejected it.

So the runtime and the harness skeleton are type-checked as a pair, which is
how a consumer receives them: the skeleton imports from the runtime, and a
member added to one and not the other is exactly the defect this file was
added alongside.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import branch_tests as bt

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TSC = _REPO_ROOT / "rjui_tools/spec/support/node_modules/.bin/tsc"

#: Matches the rjui suite's invocation surface. `--strict` is the point: the
#: emitted code is handed to consumers whose own tsconfig is usually strict,
#: and a check run loose would pass code their build rejects.
_TSC_ARGS = ["--noEmit", "--strict", "--target", "ES2022", "--module",
             "ESNext", "--moduleResolution", "bundler", "--lib", "ES2022,DOM"]


def _tsc() -> Path:
    """The pinned compiler, or a decision about its absence.

    In CI this FAILS. A gate that skips gates nothing, and the skip would be
    invisible in a green summary — the failure mode the rjui step's comment
    already names, one suite over.

    Locally it skips, through `pytest.skip` so it lands in the skipped count
    rather than passing silently. That distinction is not theoretical here:
    an rspec `skip` raised bare counts as PASSED, and this project has had a
    gate that reported success while never executing.
    """
    if _TSC.is_file():
        return _TSC
    if os.environ.get("CI"):
        pytest.fail(
            "tsc is not installed and this is CI. The emitted TypeScript "
            "would go unchecked: run `npm ci --prefix rjui_tools/spec/support`"
        )
    pytest.skip("tsc not installed — `npm ci --prefix rjui_tools/spec/support`")


def _emit(into: Path, *, runtime: str | None = None,
          skeleton: str | None = None) -> None:
    (into / "jsonui-branch-runtime.ts").write_text(
        runtime if runtime is not None else bt.RUNTIME_TS, encoding="utf-8")
    (into / "some_screen.ts").write_text(
        skeleton if skeleton is not None else bt.HARNESS_SKELETON % {
            "screen": "some_screen", "screen_const": "SOME_SCREEN"},
        encoding="utf-8")


def _type_check(into: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(_tsc()), *_TSC_ARGS, "jsonui-branch-runtime.ts", "some_screen.ts"],
        cwd=into, capture_output=True, text=True,
    )


class TestTheEmittedPairTypeChecks:
    def test_the_runtime_and_the_skeleton_compile_together(self, tmp_path):
        _emit(tmp_path)
        done = _type_check(tmp_path)
        assert done.returncode == 0, done.stdout + done.stderr

    def test_the_check_can_fail(self, tmp_path):
        """The control this check needs for itself.

        Without it, "tsc exited 0" and "tsc never looked at these files" are
        the same observation — a wrong path, an empty file list or a silently
        ignored argument all produce the clean exit above.
        """
        _emit(tmp_path, runtime=bt.RUNTIME_TS +
              '\nconst bad: number = invokeFromStore({}, "x");\n')
        done = _type_check(tmp_path)
        assert done.returncode != 0
        assert "TS2322" in done.stdout + done.stderr

    def test_it_catches_what_a_string_assert_cannot(self, tmp_path):
        """The reason this file exists rather than another `assert in`.

        The skeleton here declares `invoke` exactly as the real one does, and
        calls it with an argument list the interface does not accept. Every
        text assertion in the suite passes on this file: the member is
        present, spelled correctly, in the right block. Only a type-checker
        knows the call is wrong.
        """
        broken = bt.HARNESS_SKELETON % {"screen": "some_screen",
                                        "screen_const": "SOME_SCREEN"}
        broken += (
            "\nexport function press(h: BranchHarness): void {\n"
            "  h.invoke(42);\n"
            "}\n"
        )
        # What a string-only gate would see, on the file that does not compile:
        assert "invoke(" in broken
        assert "invoke(name: string, ...args: unknown[]): unknown;" in broken

        _emit(tmp_path, skeleton=broken)
        done = _type_check(tmp_path)
        assert done.returncode != 0
        assert "TS2345" in done.stdout + done.stderr, done.stdout


class TestTheCompilerIsReallyReached:
    def test_the_pinned_compiler_is_the_one_that_runs(self):
        """Named from `rjui_tools/spec/support`, not from PATH.

        A tsc picked up from PATH is whatever the machine has, so the check
        would mean something different on every machine and something else
        again in CI. It lives under spec/, which `jui sync_tool` deletes, so
        pinning it cannot reach a consumer's tree.
        """
        _tsc()  # skips or fails before asserting anything about the path
        assert _TSC.parts[-4:] == ("support", "node_modules", ".bin", "tsc")
        assert shutil.which("tsc") is None or _TSC.is_file()
