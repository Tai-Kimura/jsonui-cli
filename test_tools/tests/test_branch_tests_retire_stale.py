"""A screen that stops producing a test here has its old one taken away.

The generator only ever wrote. When a screen's branches move to another
platform it reports `Skipped 'X'` and leaves the file it wrote last time on
disk, still running the old contract — and no gate says so, because
`--check` does not count a screen that is not applicable to this platform.

Reported after a consumer hit the loud direction: the leftover kept FAILING,
so the skip read as "my `platforms` declaration is not working" and they
went looking for a misspelling. The quiet direction is worse — a leftover
that still passes reads as "this screen has branch tests for this platform",
about a screen that has none.

It needs a state TRANSITION to reproduce, which is why a healthy project
never shows it: a screen that was never applicable has nothing left behind.
Measured on one Android target: 8 applicable screens, 10 not, and exactly 8
files on disk.

Ownership is read from the file, not from its path. The `@generated` banner
decides; the hand-written harness sits in the same tree under the same
naming convention, and "we built the name correctly" is not something a
delete should rest on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli.branch_tests import GENERATED_MARKER, generate_branch_tests

from test_branch_tests_generator import _contract, _project, _write

PLATFORM = {
    "web": dict(kwargs={}, name="checkout.branches.test.ts",
                harness="checkout.ts"),
    "android": dict(kwargs={"platform": "android", "package": "com.acme.app"},
                    name="CheckoutBranchesTest.kt",
                    harness="CheckoutBranchHarness.kt"),
    "ios": dict(kwargs={"platform": "ios", "module": "Acme"},
                name="CheckoutBranchesTest.swift",
                harness="CheckoutBranchHarness.swift"),
}


def _branches(platforms=None):
    branch = {"when": {"api.createOrder": "conflict"},
              "then": {"data.screenState": "order_error"}}
    if platforms is not None:
        branch["platforms"] = platforms
    return _contract([branch])


def _respec(root: Path, platforms):
    spec = json.loads((root / "docs/specs/checkout.spec.json").read_text())
    spec["branchContracts"] = _branches(platforms)
    _write(root / "docs/specs/checkout.spec.json", spec)


def _artefact(root: Path, platform: str) -> Path:
    [found] = [p for p in root.rglob(PLATFORM[platform]["name"])]
    return found


@pytest.fixture(params=sorted(PLATFORM))
def platform(request):
    return request.param


@pytest.fixture
def project(tmp_path):
    return _project(tmp_path, _branches())


def _run(root, platform, **extra):
    return generate_branch_tests("checkout", project_root=root,
                                 **PLATFORM[platform]["kwargs"], **extra)


class TestTheTransition:
    def test_the_leftover_is_removed_when_the_screen_stops_applying(
            self, project, platform):
        """The reported sequence, on every platform the generator emits for."""
        _run(project, platform)
        artefact = _artefact(project, platform)
        assert artefact.exists()

        _respec(project, ["nowhere"])
        report = _run(project, platform)

        assert not report.platform_applicable
        assert report.stale == [artefact]
        assert not artefact.exists()

    def test_a_screen_that_never_applied_leaves_nothing_to_report(
            self, project, platform):
        """The control, and the reason a healthy project never sees this:
        with no transition there is nothing on disk to retire, so "the
        leftover was removed" and "there was no leftover" have to be
        distinguishable."""
        _respec(project, ["nowhere"])

        report = _run(project, platform)

        assert not report.platform_applicable
        assert report.stale == []

    def test_the_screen_still_generates_where_it_does_apply(
            self, project, platform):
        """The other control. A retire that ran unconditionally would pass
        the first test and delete every generated file in the project."""
        _run(project, platform)

        report = _run(project, platform)

        assert report.platform_applicable
        assert report.stale == []
        assert _artefact(project, platform).exists()


class TestOwnership:
    def test_the_hand_written_harness_is_never_touched(self, project,
                                                       platform):
        """It sits in the same tree under the same naming convention, and it
        is the consumer's file. The retire is aimed at one path, so this is
        a guard on the aim rather than on the marker check."""
        _run(project, platform)
        [harness] = list(project.rglob(PLATFORM[platform]["harness"]))
        before = harness.read_text(encoding="utf-8")

        _respec(project, ["nowhere"])
        _run(project, platform)

        assert harness.exists()
        assert harness.read_text(encoding="utf-8") == before

    def test_a_file_without_the_banner_is_reported_not_deleted(self, project,
                                                              platform):
        """Ownership is read from the file. If the name were built wrongly —
        or a project keeps a hand-written test under the generated name —
        deleting on the strength of the path would destroy work."""
        _run(project, platform)
        artefact = _artefact(project, platform)
        artefact.write_text("// mine, no banner\n", encoding="utf-8")

        _respec(project, ["nowhere"])
        report = _run(project, platform)

        assert artefact.exists()
        assert artefact.read_text(encoding="utf-8") == "// mine, no banner\n"
        assert report.stale == []
        assert report.unowned == [artefact]

    def test_the_banner_the_check_looks_for_is_the_one_that_is_written(
            self, project, platform):
        """Both halves of the ownership claim in one place. A generator that
        changed its banner would leave every retire silently declining, and
        the tests above would still pass — they only assert the file it
        wrote is removed, which a marker that matches nothing would not do…
        except that they use the same writer. So the marker is checked
        against the emitted bytes directly."""
        _run(project, platform)

        head = _artefact(project, platform).read_text(encoding="utf-8")[:400]

        assert GENERATED_MARKER in head


class TestCheckMode:
    def test_check_reports_the_leftover(self, project, platform):
        """It was reported by neither command: the run that skips knew, and
        `--check` filters out screens that are not applicable — which is the
        very filter that hides this."""
        _run(project, platform)
        artefact = _artefact(project, platform)
        _respec(project, ["nowhere"])

        report = _run(project, platform, check=True)

        assert report.stale == [artefact]

    def test_check_does_not_delete_it(self, project, platform):
        """Same rule as `mkdir`: a check that changes the tree it audits
        agrees with itself on the second run."""
        _run(project, platform)
        artefact = _artefact(project, platform)
        _respec(project, ["nowhere"])

        _run(project, platform, check=True)

        assert artefact.exists()

    def test_the_gate_fails_and_the_summary_counts_it(self, project, capsys):
        """End to end, because the finding has to survive the summary: a
        gate that fails on a category the summary does not count is the
        defect this repository fixed in the mock checker the same week."""
        from jsonui_test_cli.cli import _branch_check_summary

        _run(project, "web")
        _respec(project, ["nowhere"])
        report = _run(project, "web", check=True)

        rc = _branch_check_summary([report], scanned=1)
        out = capsys.readouterr().out

        assert rc == 1
        assert "[STALE]" in out
        assert "1 stale" in out
