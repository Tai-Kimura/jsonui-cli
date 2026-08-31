"""An `[ABSENT]` parent, beside files named after its sub-specs, is explained.

A parent spec and its `subSpecs` are ONE screen and generate one set of
files under the parent's name. A project upgrading across that change still
has a file per sub-spec on disk and none for the parent, so `--check`
reports the parent absent and says nothing about the leftovers — which are
now orphans nothing regenerates.

Measured cost, from the consumer who hit it: they started from an unrelated
import error and took several steps to reach the model change. The check had
the information and printed the file name only. The refusal message on the
generate path is exact ("is a sub-spec of X, not a screen of its own"), but
`--check` never reaches it — nobody asked for the sub-spec by name.

The note appears only when BOTH halves are present. An absent file on its
own has several explanations, and picking one for the reader is how an
explanation turns into noise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.branch_tests import (
    orphaned_sub_spec_artefacts, sub_spec_screen_names,
)
from jsonui_test_cli.cli import _branch_check_summary


def _spec(name, **extra):
    doc = {"metadata": {"name": name, "description": "d"}}
    doc.update(extra)
    return doc


@pytest.fixture
def project(tmp_path):
    (tmp_path / "jui.config.json").write_text(json.dumps(
        {"spec_directory": "docs/screens/json"}), encoding="utf-8")
    specs = tmp_path / "docs" / "screens" / "json"
    specs.mkdir(parents=True)
    (specs / "checkout.spec.json").write_text(json.dumps(_spec(
        "checkout",
        type="screen_parent_spec",
        subSpecs=[{"file": "checkout_form.spec.json"},
                  {"file": "checkout_review.spec.json"}],
    )), encoding="utf-8")
    for part in ("checkout_form", "checkout_review"):
        (specs / f"{part}.spec.json").write_text(
            json.dumps(_spec(part)), encoding="utf-8")
    (specs / "home.spec.json").write_text(
        json.dumps(_spec("home")), encoding="utf-8")
    return tmp_path


class TestFindingTheLeftovers:
    def test_sub_specs_are_named_and_the_parent_is_not(self, project):
        assert sub_spec_screen_names(project) == [
            "checkout_form", "checkout_review"]

    def test_a_standalone_screen_is_not_a_sub_spec(self, project):
        """The control: a spec that is nobody's part must not be swept up,
        or the note would name files that are perfectly current."""
        assert "home" not in sub_spec_screen_names(project)

    def test_generated_files_named_after_a_sub_spec_are_found(self, project):
        out = project / "tests" / "unit" / "generated"
        out.mkdir(parents=True)
        for name in ("checkout_form", "checkout_review", "home"):
            (out / f"{name}.branches.test.ts").write_text("", encoding="utf-8")

        orphans = orphaned_sub_spec_artefacts(
            project, "tests/unit/generated", "web")

        assert [p.name for p in orphans] == [
            "checkout_form.branches.test.ts",
            "checkout_review.branches.test.ts"]

    def test_an_output_directory_that_does_not_exist_finds_nothing(self, project):
        assert orphaned_sub_spec_artefacts(project, "nope", "web") == []

    def test_a_platform_with_other_filenames_is_matched_on_its_own(self, project):
        out = project / "app" / "src" / "test"
        out.mkdir(parents=True)
        (out / "checkout_formBranchTest.kt").write_text("", encoding="utf-8")
        (out / "checkout_form.branches.test.ts").write_text("", encoding="utf-8")

        android = orphaned_sub_spec_artefacts(project, "app/src/test", "android")

        assert [p.name for p in android] == ["checkout_formBranchTest.kt"]


class _Report:
    """The shape `_branch_check_summary` reads."""

    def __init__(self, screen, absent=(), drifted=(), matched=()):
        self.screen = screen
        self.absent = list(absent)
        self.drifted = list(drifted)
        self.matched = list(matched)
        self.platform_applicable = True
        self.harness_absent = False
        self.harness_file = None


class TestTheNote:
    def test_it_names_the_model_the_orphans_and_the_migration(self, capsys):
        orphans = [Path("tests/unit/generated/checkout_form.branches.test.ts")]
        reports = [_Report("checkout",
                           absent=[Path("tests/unit/generated/"
                                        "checkout.branches.test.ts")])]

        rc = _branch_check_summary(reports, scanned=4, orphans=orphans)
        out = capsys.readouterr().out

        assert rc == 1
        assert "ONE screen" in out                       # the model
        assert "checkout_form.branches.test.ts" in out   # which files
        assert "delete" in out                           # what to do
        assert "Mocks first" in out                      # the ordering

    def test_an_absent_file_with_no_orphans_is_not_explained(self, capsys):
        """A screen that has simply never been generated. Guessing that the
        reader has just upgraded would put a migration note in front of
        somebody who has not migrated anything."""
        reports = [_Report("home", absent=[Path("home.branches.test.ts")])]

        _branch_check_summary(reports, scanned=4, orphans=[])
        out = capsys.readouterr().out

        assert "[ABSENT]" in out
        assert "ONE screen" not in out

    def test_orphans_with_nothing_absent_are_not_explained(self, capsys):
        """Leftovers beside a parent that IS generated are the state after a
        successful migration minus the delete — real, but not this note's
        story, and not a failure."""
        reports = [_Report("checkout",
                           matched=[Path("checkout.branches.test.ts")])]

        rc = _branch_check_summary(
            reports, scanned=4,
            orphans=[Path("checkout_form.branches.test.ts")])
        out = capsys.readouterr().out

        assert rc == 0
        assert "ONE screen" not in out

    def test_the_summary_still_reports_what_it_always_did(self, capsys):
        reports = [_Report("checkout",
                           absent=[Path("checkout.branches.test.ts")])]

        _branch_check_summary(reports, scanned=4, orphans=[])
        out = capsys.readouterr().out

        assert "1 screen(s) declaring branchContracts of 4 spec(s) scanned" in out
        assert "Regenerate with the same command without --check." in out
