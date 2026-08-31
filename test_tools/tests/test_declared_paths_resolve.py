"""A declaration that names a file is resolved, not just typed.

Reported with a control arm, which is what makes it a finding rather than a
preference: rewriting one `source.layout` to a path that does not exist and
re-running produced the same `PASSED / Errors: 0, Warnings: 0` as before. The
green meant "the paths are right" and "nothing looked at the paths" equally
well, and only the broken arm tells them apart.

It hid the way its siblings did this week. `relatedFiles[].type` is checked
against an allow-list and errors on a bad value, so `relatedFiles` reads as a
validated declaration and `path` — beside something guarded — is not
suspected. Same shape as `additionalProperties: false` being enforced while
the schema's `required` was not.

Warning, not error, and the tests say why in both directions: one repository
already carries 11 of these and nobody has measured the others, so an error
would redden gates in places that cannot act that day. The message states
that it becomes an error, because "temporarily a warning" and "a warning
forever" look identical to a reader and only the second gets ignored.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation import declared_paths
from jsonui_test_cli.validation.validator import TestValidator

SCREEN = {
    "type": "screen",
    "source": {"layout": "home.json"},
    "metadata": {"name": "home", "description": "d"},
    "cases": [{"name": "c", "description": "d",
               "steps": [{"action": "wait", "ms": 10}]}],
}

FLOW = {
    "type": "flow",
    "metadata": {"name": "f", "description": "d"},
    "sources": [{"layout": "home.json", "alias": "home"}],
    "steps": [{"action": "wait", "ms": 10, "screen": "home"}],
}


@pytest.fixture
def project(tmp_path):
    """A project whose layouts directory exists and holds one layout."""
    (tmp_path / "jui.config.json").write_text("{}", encoding="utf-8")
    layouts = tmp_path / "docs" / "screens" / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "home.json").write_text("{}", encoding="utf-8")
    (tmp_path / "docs" / "screens" / "json").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    declared_paths.set_path_roots(tmp_path)
    yield tmp_path
    declared_paths.set_path_roots(None)


def _validate(project, doc, name="probe.test.json"):
    path = project / "tests" / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return TestValidator().validate_file(path)


def _path_warnings(result):
    return [m for m in result.warnings if "does not exist" in m.message]


class TestScreenSource:
    def test_a_layout_that_exists_says_nothing(self, project):
        """The control. Without it, "the broken arm warns" is the same
        observation as "everything warns"."""
        assert _path_warnings(_validate(project, SCREEN)) == []

    def test_a_layout_that_does_not_exist_warns(self, project):
        doc = dict(SCREEN, source={"layout": "gone.json"})

        result = _validate(project, doc)

        [warning] = _path_warnings(result)
        assert "gone.json" in warning.message
        # A warning, not an error: the run still passes, and the number to
        # walk to zero is visible.
        assert result.is_valid

    def test_the_message_says_the_weight_will_change(self, project):
        """A warning that never becomes anything is one people learn to
        scroll past — the failure mode this check would otherwise join."""
        [warning] = _path_warnings(
            _validate(project, dict(SCREEN, source={"layout": "gone.json"})))
        assert "becomes an error" in warning.message

    def test_a_document_resolves_under_the_spec_directory(self, project):
        (project / "docs" / "screens" / "json" / "home.json").write_text(
            "{}", encoding="utf-8")
        doc = dict(SCREEN,
                   source={"layout": "home.json", "document": "home.json"})

        assert _path_warnings(_validate(project, doc)) == []

    def test_a_repository_relative_spelling_also_resolves(self, project):
        """Both spellings are in use and this check does not choose between
        them: a false positive costs more than a miss, because one visibly
        wrong finding is what stops people acting on the rest."""
        doc = dict(SCREEN,
                   source={"layout": "docs/screens/layouts/home.json"})

        assert _path_warnings(_validate(project, doc)) == []


class TestFlowSources:
    def test_a_layout_that_exists_says_nothing(self, project):
        assert _path_warnings(_validate(project, FLOW)) == []

    def test_a_layout_that_does_not_exist_warns(self, project):
        doc = dict(FLOW, sources=[{"layout": "gone.json", "alias": "home"}])

        [warning] = _path_warnings(_validate(project, doc))

        assert "gone.json" in warning.message

    def test_each_entry_is_resolved(self, project):
        doc = dict(FLOW, sources=[
            {"layout": "home.json", "alias": "a"},
            {"layout": "gone.json", "alias": "b"},
            {"layout": "also-gone.json", "alias": "c"},
        ])

        assert len(_path_warnings(_validate(project, doc))) == 2


class TestTheCheckDeclinesLoudly:
    """A project this run cannot resolve against gets silence, and the run
    says the check did not happen.

    Reporting every reference as missing on a project that keeps its layouts
    somewhere else would be hundreds of unactionable findings on the first
    run after an upgrade. But declining SILENTLY is the defect this whole
    file is about: "no dangling paths" and "nothing was resolved" would
    print identically.
    """

    def test_no_layouts_directory_means_no_findings(self, tmp_path):
        (tmp_path / "tests").mkdir()
        declared_paths.set_path_roots(tmp_path)
        try:
            result = _validate(tmp_path, dict(SCREEN,
                                              source={"layout": "gone.json"}))
            assert _path_warnings(result) == []
            assert declared_paths.skipped_kinds() == ["layout"]
        finally:
            declared_paths.set_path_roots(None)

    def test_no_project_root_means_no_findings_and_nothing_to_report(
            self, tmp_path):
        """Validating a file with no project around it — the check has no
        question to answer, so it does not invent one."""
        (tmp_path / "tests").mkdir()
        declared_paths.set_path_roots(None)

        result = _validate(tmp_path, dict(SCREEN,
                                          source={"layout": "gone.json"}))

        assert _path_warnings(result) == []
        assert declared_paths.skipped_kinds() == []

    def test_the_skip_record_is_cleared_between_runs(self, tmp_path):
        """It is process-global state, and a stale entry would make the next
        run report a check it did perform as skipped."""
        declared_paths.set_path_roots(tmp_path)
        declared_paths.resolves("gone.json", "layout")
        assert declared_paths.skipped_kinds() == ["layout"]

        declared_paths.set_path_roots(None)

        assert declared_paths.skipped_kinds() == []
