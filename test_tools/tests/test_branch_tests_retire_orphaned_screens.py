"""A screen that leaves the scan has its generated test taken away.

Removing a screen's spec (or its branchContracts) took it out of the
whole-project scan, so no run reached the test it had generated: the file
stayed, still importing the removed ViewModel and harness, and `--check`
passed because it counts only the screens it scans. Measured on two consumer
copies (one iOS + Android screen, one web screen) and then on every
platform x {spec removed, contracts removed} x {whole project, one other
screen named, the removed screen named, check}: the test stayed in all 24
cells and the check exited 0.

The family, after the fix:

- whole project: the test is retired (banner checked), the harness is named
  and kept; `--check` reports it as retired and fails;
- one other screen named: nothing is deleted (the run was asked about one
  screen), the leftover is named in a note;
- the removed screen named: its own test is retired and the run still fails
  (nothing was generated for the name it was given).

Ownership is the banner's, as for the per-screen retire: the harness, the
shared runtime and a hand-written file under a generated test's name are
never touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli.branch_tests import _banner_screen
from jsonui_test_cli.cli import main

from test_branch_tests_generator import BASIC, _project, _write

PLATFORM = {
    "web": dict(argv=[], dead="tests/unit/generated/cart.branches.test.ts",
                harness="tests/unit/branch-harness/cart.ts",
                live="tests/unit/generated/checkout.branches.test.ts",
                runtime="tests/unit/generated/jsonui-branch-runtime.ts"),
    "android": dict(argv=["--platform", "android", "--package", "com.acme.app"],
                    dead="app/src/test/java/com/acme/app/CartBranchesTest.kt",
                    harness="app/src/test/java/com/acme/app/CartBranchHarness.kt",
                    live="app/src/test/java/com/acme/app/CheckoutBranchesTest.kt",
                    runtime="app/src/test/java/com/acme/app/JsonuiBranchRuntime.kt"),
    "ios": dict(argv=["--platform", "ios", "--module", "Acme"],
                dead="Tests/Generated/CartBranchesTest.swift",
                harness="Tests/Generated/CartBranchHarness.swift",
                live="Tests/Generated/CheckoutBranchesTest.swift",
                runtime="Tests/Generated/JsonuiBranchRuntime.swift"),
}


def _cli(root: Path, *argv, monkeypatch) -> int:
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["jsonui-test", "generate",
                                      "branch-tests", *argv])
    return main()


@pytest.fixture(params=sorted(PLATFORM))
def platform(request):
    return request.param


@pytest.fixture(params=["spec_removed", "contracts_removed"])
def change(request):
    return request.param


@pytest.fixture
def project(tmp_path, platform, monkeypatch):
    root = _project(tmp_path, BASIC)
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())
    spec["metadata"]["name"] = "Cart"
    _write(root / "docs/specs/cart.spec.json", spec)
    assert _cli(root, *PLATFORM[platform]["argv"], monkeypatch=monkeypatch) == 0
    p = PLATFORM[platform]
    for rel in (p["dead"], p["harness"], p["live"], p["runtime"]):
        assert (root / rel).exists(), rel
    return root


def _remove_cart(root: Path, change: str) -> None:
    spec_file = root / "docs/specs/cart.spec.json"
    if change == "spec_removed":
        spec_file.unlink()
    else:
        spec = json.loads(spec_file.read_text())
        spec.pop("branchContracts")
        _write(spec_file, spec)


def _harness_bytes(root, platform):
    return (root / PLATFORM[platform]["harness"]).read_bytes()


class TestWholeProject:
    def test_the_dead_screens_test_is_retired_and_its_harness_named(
            self, project, platform, change, monkeypatch, capsys):
        p = PLATFORM[platform]
        harness_before = _harness_bytes(project, platform)
        _remove_cart(project, change)
        capsys.readouterr()

        assert _cli(project, *p["argv"], monkeypatch=monkeypatch) == 0

        out = capsys.readouterr().out
        assert not (project / p["dead"]).exists()
        assert f"removed {project.resolve() / p['dead']}" in out \
            or f"removed {project / p['dead']}" in out
        # The consumer's file: kept byte for byte, and named.
        assert _harness_bytes(project, platform) == harness_before
        assert "[WARN]" in out and Path(p["harness"]).name in out
        # The live screen and the shared runtime are untouched.
        assert (project / p["live"]).exists()
        assert (project / p["runtime"]).exists()

    def test_the_check_fails_on_it_and_deletes_nothing(
            self, project, platform, change, monkeypatch, capsys):
        p = PLATFORM[platform]
        _remove_cart(project, change)
        capsys.readouterr()

        assert _cli(project, *p["argv"], "--check", monkeypatch=monkeypatch) == 1

        out = capsys.readouterr().out
        assert "[RETIRED]" in out and Path(p["dead"]).name in out
        assert "1 retired" in out
        assert (project / p["dead"]).exists()

    def test_the_check_is_green_again_after_the_retire(
            self, project, platform, change, monkeypatch):
        p = PLATFORM[platform]
        _remove_cart(project, change)
        assert _cli(project, *p["argv"], monkeypatch=monkeypatch) == 0

        assert _cli(project, *p["argv"], "--check", monkeypatch=monkeypatch) == 0

    def test_control_a_healthy_project_retires_nothing(
            self, project, platform, monkeypatch, capsys):
        """The retire must find the dead screen, not every screen."""
        p = PLATFORM[platform]
        capsys.readouterr()

        assert _cli(project, *p["argv"], monkeypatch=monkeypatch) == 0
        assert _cli(project, *p["argv"], "--check", monkeypatch=monkeypatch) == 0

        out = capsys.readouterr().out
        assert "removed" not in out and "[RETIRED]" not in out
        assert (project / p["dead"]).exists()


class TestOneScreenNamed:
    def test_another_screen_named_deletes_nothing_and_says_so(
            self, project, platform, change, monkeypatch, capsys):
        p = PLATFORM[platform]
        _remove_cart(project, change)
        capsys.readouterr()

        assert _cli(project, "checkout", *p["argv"], monkeypatch=monkeypatch) == 0

        out = capsys.readouterr().out
        assert (project / p["dead"]).exists()
        assert "without a screen name to remove it" in out
        assert Path(p["dead"]).name in out

    def test_the_removed_screen_named_retires_its_own_test(
            self, project, platform, change, monkeypatch, capsys):
        p = PLATFORM[platform]
        harness_before = _harness_bytes(project, platform)
        _remove_cart(project, change)
        capsys.readouterr()

        # Still a failure: nothing was generated for the name given.
        assert _cli(project, "cart", *p["argv"], monkeypatch=monkeypatch) == 1

        err = capsys.readouterr().err
        assert not (project / p["dead"]).exists()
        assert "removed" in err
        assert _harness_bytes(project, platform) == harness_before
        assert (project / p["live"]).exists()

    def test_the_removed_screen_named_in_a_check_deletes_nothing(
            self, project, platform, change, monkeypatch, capsys):
        p = PLATFORM[platform]
        _remove_cart(project, change)

        assert _cli(project, "cart", *p["argv"], "--check",
                    monkeypatch=monkeypatch) == 1
        assert (project / p["dead"]).exists()


class TestOwnership:
    def test_a_file_without_the_banner_is_never_deleted(
            self, project, platform, monkeypatch):
        """A hand-written file under a generated test's name is not ours."""
        p = PLATFORM[platform]
        dead = project / p["dead"]
        dead.write_text("// hand-written\n", encoding="utf-8")
        _remove_cart(project, "spec_removed")

        assert _cli(project, *p["argv"], monkeypatch=monkeypatch) == 0
        assert dead.read_text(encoding="utf-8") == "// hand-written\n"

    def test_a_shared_file_banner_names_no_screen(self, project, platform):
        """The runtime's banner is followed by a flag or the closing quote;
        reading a screen out of it would make the runtime an orphan."""
        p = PLATFORM[platform]
        assert _banner_screen(project / p["runtime"]) is None
        assert _banner_screen(project / p["live"]) == "checkout"
        assert _banner_screen(project / p["dead"]) == "cart"

    def test_a_screen_named_with_spec_outside_spec_directory_is_not_called_a_leftover(
            self, project, platform, monkeypatch, capsys):
        """`--spec` may point outside spec_directory, so the scan does not see
        the screen; the run that just generated it must not call it an orphan."""
        p = PLATFORM[platform]
        moved = project / "elsewhere/cart.spec.json"
        moved.parent.mkdir()
        (project / "docs/specs/cart.spec.json").rename(moved)
        capsys.readouterr()

        assert _cli(project, "cart", "--spec", "elsewhere/cart.spec.json",
                    *p["argv"], monkeypatch=monkeypatch) == 0

        out = capsys.readouterr().out
        assert "no longer declares branchContracts" not in out
        assert (project / p["dead"]).exists()
