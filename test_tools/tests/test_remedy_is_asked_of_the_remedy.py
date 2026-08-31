"""A printed remedy has to actually change something, and out-of-scope files
are not this command's to change.

Two findings from one consumer run, on the same pair of commands.

**The remedy.** `--check` printed "Refresh the generated bodies with
`jsonui-test mock generate --update-default`" for every body finding. That
merge only touches the `default` scenario and never overwrites a value, so
on a stale `error_422` — the reported case — and on a `default` holding a
value of the wrong type, running it repairs nothing and the same check comes
back identical. Measured: "Repaired the default scenario of 0 mock file(s)",
target unchanged, exit 1 again.

Picking the remedy by scenario NAME does not close this: the wrong-type case
is called `default` and is still unfixable. What decides is whether the
merge would change that body, which only the merge knows — so it is asked,
in dry-run, rather than re-derived from the kind of drift. A second
implementation of "what a merge can decide" diverges the day the merge's
policy changes, silently, in the direction of printing advice that does
nothing.

**The scope.** `update_default` read the project's declared API paths in one
branch — whether an absent file counts as a gap — and wrote to every file it
found. In one run, `--check` called `legacy/legacyPing.mock.json` "outside
this project's API paths, safe to delete" and `--update-default` then edited
that file and nothing else, reporting "Repaired the default scenario of 1
mock file(s)" with exit 0 while the file that made the check red went
untouched.

The predicate below matters more than the fix. The consumer who hit this in
production hit the variant where **what was written was a correct update**,
and closed it as their own procedural mistake without ever asking why an
out-of-scope file had been written at all — which is what has kept the bug
alive. The live example of this bug lives on the path where the content is
right, so a test that checks the content is wrong walks straight past it.
These tests assert the file is not written *even though the write would be
correct*.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import generate, update_default
from jsonui_test_cli.mock.scope import PathScope


def _op(operation_id, statuses=(200,)):
    responses = {}
    for status in statuses:
        responses[str(status)] = {"content": {"application/json": {"schema": {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "string"},
                           "name": {"type": "string"}},
        }}}}
    return {"operationId": operation_id, "responses": responses}


SPEC = {"openapi": "3.0.3", "paths": {
    "/api/shop/items": {"post": _op("createItem", (200, 404))},
    "/api/legacy/ping": {"get": _op("legacyPing")},
}}

#: The reported shape: a shared swagger, one realm excluded.
SCOPE = PathScope(exclude=("/api/legacy/*",))


@pytest.fixture
def swagger(tmp_path):
    path = tmp_path / "api.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return str(path)


def _write(mock_dir, rel, method, path, operation_id, scenarios):
    target = mock_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": {"method": method, "path": path,
                   "operationId": operation_id},
        "scenarios": scenarios,
    }, indent=2), encoding="utf-8")
    return target


class TestOutOfScopeFilesAreNotWritten:
    def _legacy(self, mock_dir):
        """A mock for an excluded route, missing a required field — so the
        merge has something correct to write. That is the point."""
        return _write(mock_dir, "legacy/legacyPing.mock.json",
                      "GET", "/api/legacy/ping", "legacyPing",
                      {"default": {"status": 200, "body": {"name": "x"}}})

    def test_the_file_is_not_written_even_though_the_write_would_be_correct(
            self, swagger, tmp_path):
        """The whole finding. `.id` really is required and really is absent,
        so every check of WHAT was written passes — which is exactly how the
        one person who hit this explained it away."""
        mock_dir = tmp_path / "mocks"
        legacy = self._legacy(mock_dir)
        before = legacy.read_text(encoding="utf-8")

        update_default([swagger], mock_dir, scope=SCOPE)

        assert legacy.read_text(encoding="utf-8") == before

    def test_without_the_scope_the_same_write_happens(self, swagger, tmp_path):
        """The control: the merge does have something to do here, so the
        assertion above is about the scope and not about an inert file."""
        mock_dir = tmp_path / "mocks"
        legacy = self._legacy(mock_dir)
        before = legacy.read_text(encoding="utf-8")

        update_default([swagger], mock_dir)

        assert legacy.read_text(encoding="utf-8") != before
        assert json.loads(legacy.read_text(encoding="utf-8"))[
            "scenarios"]["default"]["body"]["id"] is not None

    def test_it_is_not_reported_as_repaired_either(self, swagger, tmp_path):
        """`Repaired the default scenario of 1 mock file(s)` counted it."""
        mock_dir = tmp_path / "mocks"
        self._legacy(mock_dir)

        upd = update_default([swagger], mock_dir, scope=SCOPE)

        assert upd.updated == []
        assert upd.repaired == {}

    def test_the_two_commands_agree_about_which_files_are_the_projects(
            self, swagger, tmp_path):
        """One check called it safe to delete while its sibling command
        maintained it. Whichever is right, a reader cannot be handed both."""
        mock_dir = tmp_path / "mocks"
        self._legacy(mock_dir)

        report = generate([swagger], mock_dir, check=True, scope=SCOPE)
        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        excluded = {line.split()[0] for line in report.out_of_scope}
        assert excluded == {"legacy/legacyPing.mock.json"}
        assert excluded.isdisjoint(upd.updated)

    def test_an_in_scope_file_is_still_repaired(self, swagger, tmp_path):
        """The other control. A guard at the top of the loop is one `continue`
        away from excluding everything."""
        mock_dir = tmp_path / "mocks"
        shop = _write(mock_dir, "shop/createItem.mock.json",
                      "POST", "/api/shop/items", "createItem",
                      {"default": {"status": 200, "body": {"name": "x"}}})

        upd = update_default([swagger], mock_dir, scope=SCOPE)

        assert upd.updated == ["shop/createItem.mock.json"]
        assert json.loads(shop.read_text(encoding="utf-8"))[
            "scenarios"]["default"]["body"]["id"]


class TestTheRemedyIsAskedOfTheRemedy:
    """`repaired` answers "would running this close that finding?"."""

    def test_a_wrong_type_in_default_is_not_offered_the_merge(
            self, swagger, tmp_path):
        """The case that separates the two candidate designs. The scenario
        is NAMED `default`, so routing by name prints the merge remedy — and
        the merge cannot touch it, because it never overwrites a value."""
        mock_dir = tmp_path / "mocks"
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"id": 1, "name": "x"}}})

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.repaired == {}
        assert [rel for rel, _ in upd.needs_review] == [
            "shop/createItem.mock.json"]

    def test_a_missing_required_field_in_default_is(self, swagger, tmp_path):
        """The control arm. Without it, "nothing is ever merge-fixable"
        passes every assertion above."""
        mock_dir = tmp_path / "mocks"
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"name": "x"}}})

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.repaired == {"shop/createItem.mock.json": ["default"]}
        assert upd.needs_review == []

    def test_a_non_default_scenario_is_never_offered_the_merge(
            self, swagger, tmp_path):
        """The reported case: a stale `error_422`. `--update-default` does
        not touch scenarios other than `default` at all."""
        mock_dir = tmp_path / "mocks"
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"id": "1", "name": "x"}},
                "not_found": {"status": 404, "body": {"id": "1"}}})

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.repaired == {}

    def test_a_source_only_refresh_does_not_claim_to_repair_a_body(
            self, swagger, tmp_path):
        """`updated` holds these — it is the union of both kinds of change —
        which is why the remedy reads `repaired` instead. Routing by
        `updated` would print the merge remedy for a body the merge left
        exactly as it found it."""
        mock_dir = tmp_path / "mocks"
        # The body satisfies the contract; only `source` is short of what a
        # fresh scaffold records (no `swagger` provenance), which is the
        # half of the file this command also refreshes.
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"id": "1", "name": "x"}}})

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.updated == ["shop/createItem.mock.json"]
        assert upd.repaired == {}

    def test_a_default_the_merge_only_half_fixes_still_needs_a_person(
            self, swagger, tmp_path):
        """Both halves of the answer come from the merge: it would change
        this body, AND it would leave a violation behind. Reading only the
        first would promise a fix that arrives half-done."""
        mock_dir = tmp_path / "mocks"
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"name": 7}}})

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.repaired == {"shop/createItem.mock.json": ["default"]}
        assert [rel for rel, _ in upd.needs_review] == [
            "shop/createItem.mock.json"]

    def test_the_printed_advice_follows_the_answer(self, swagger, tmp_path,
                                                   capsys):
        """What the reader actually gets. One file, two findings: the
        `default` the merge would fill in, and the `not_found` it cannot
        touch. Before, both got the same sentence."""
        from jsonui_test_cli.cli import _print_body_drift_remedy

        mock_dir = tmp_path / "mocks"
        _write(mock_dir, "shop/createItem.mock.json",
               "POST", "/api/shop/items", "createItem",
               {"default": {"status": 200, "body": {"id": "1"}},
                "not_found": {"status": 404, "body": {"id": 7, "name": "x"}}})
        report = generate([swagger], mock_dir, check=True, scope=SCOPE)
        assert len(report.errors) == 2

        _print_body_drift_remedy(report, [swagger], mock_dir, SCOPE)
        out = capsys.readouterr().out

        offered, by_hand = out.split("cannot decide")
        assert "--update-default" in offered
        assert "default" in offered and "not_found" not in offered
        assert "not_found" in by_hand

    def test_dry_run_writes_nothing(self, swagger, tmp_path):
        """The check calls this on every red run. If it wrote, the gate
        would be repairing the thing it is measuring."""
        mock_dir = tmp_path / "mocks"
        target = _write(mock_dir, "shop/createItem.mock.json",
                        "POST", "/api/shop/items", "createItem",
                        {"default": {"status": 200, "body": {"name": "x"}}})
        before = target.read_text(encoding="utf-8")

        upd = update_default([swagger], mock_dir, dry_run=True, scope=SCOPE)

        assert upd.repaired  # it did decide the body would change
        assert target.read_text(encoding="utf-8") == before
