"""The overlay model is one model, not a serve-side behaviour.

`mock serve` documents the thin-overlay contract: generated/ supplies the
routine scenarios, a hand-written file carries only what its tests drive,
and an omitted `activeScenario` inherits the generated side's. generate and
validate did not know the model:

- generate's hand-written detection was shadowed by the previous run's
  generated tree (`index_existing` collapses per route LAST-WINS and
  `generated/` sorts after most tag directories), so it read 0 hand-written
  mocks on every run but the first. The branch it fed SUPPRESSED the
  route's generated file — the opposite of the overlay model — and the two
  defects cancelled into the documented behaviour. Fixing either alone
  would have broken it: detection without the branch fix activates the
  suppression everywhere.
- validate judged each mock file alone, so the exact shape the serve
  docstring recommends (thin overlay, omitted activeScenario) failed the
  gate with "activeScenario 'default' is not among scenarios".
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.branch_tests import find_mock, index_mock_files
from jsonui_test_cli.mock.generate import _check, generate, update_default
from jsonui_test_cli.mock.server import MockStore
from jsonui_test_cli.validation.mock import find_mock_index, set_mock_source
from jsonui_test_cli.validation.validator import TestValidator

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/items": {"get": {
            "operationId": "listItems",
            "responses": {"200": {"content": {"application/json": {
                "schema": {"type": "object", "required": ["id"],
                           "properties": {"id": {"type": "string"}}}}}}},
        }},
    },
}


@pytest.fixture
def project(tmp_path):
    (tmp_path / "swagger.json").write_text(json.dumps(SPEC), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    generate([str(tmp_path / "swagger.json")], mocks)
    set_mock_source(directory=mocks, boundary=tmp_path)
    yield tmp_path, mocks
    set_mock_source()


def _overlay(mocks: Path, body: dict, dirname: str = "custom") -> Path:
    # The directory name is load-bearing: each collapse defect only fires
    # for one sort order relative to `generated/`. "custom" sorts BEFORE it
    # (the generate-detection shadow, the reporting consumer's tag dirs);
    # pass a name sorting AFTER it ("z-custom") for the defects where the
    # HAND-WRITTEN file winning the collapse is the harmful direction
    # (update_default scaffolding a default into a thin overlay). A fixture
    # on the wrong side of the order hides its defect by accident.
    path = mocks / dirname / "listItems.mock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


THIN = {
    "source": {"operationId": "listItems", "method": "GET",
               "path": "/api/items"},
    "scenarios": {"paging": {"status": 200, "body": {"id": "1"}},
                  "paging_page2": {"status": 200, "body": {"id": "2"}}},
}


class TestGenerateSeesTheOverlay:
    def test_detection_survives_the_generated_tree(self, project):
        # The reported steady state: generated/ from the previous run AND a
        # hand-written mock for the same route. Detection collapsed to 0
        # here — the generated entry shadowed the hand-written one out of
        # the last-wins index.
        root, mocks = project
        rel = str(_overlay(mocks, THIN).relative_to(mocks))
        report = generate([str(root / "swagger.json")], mocks)
        assert report.overlaid == [rel]

    def test_the_overlaid_route_is_still_generated(self, project):
        # The other half of the cancelling pair: an overlay must not
        # suppress its generated counterpart — that file is where the
        # routine scenarios the thin overlay omits come from.
        root, mocks = project
        _overlay(mocks, THIN)
        generate([str(root / "swagger.json")], mocks)
        assert (mocks / "generated" / "default" / "listItems.mock.json").exists()


class TestValidateSeesTheOverlay:
    def _validate(self, path: Path):
        return TestValidator().validate_file(path)

    def test_a_thin_overlay_with_omitted_active_scenario_passes(self, project):
        # The reported false positive: the exact shape the serve docstring
        # recommends failed the gate. An omitted activeScenario inherits
        # the generated side's, so there is nothing to check per-file.
        _root, mocks = project
        result = self._validate(_overlay(mocks, THIN))
        assert [e.message for e in result.errors] == []

    def test_an_explicit_active_may_name_a_generated_scenario(self, project):
        # "Run this route on the generated variant" is a legitimate
        # overlay: the scenario lives on the generated side, the choice on
        # the hand-written side. Membership is judged against the union
        # serve builds, not the file alone.
        _root, mocks = project
        body = dict(THIN, activeScenario="default")
        result = self._validate(_overlay(mocks, body))
        assert [e.message for e in result.errors] == []

    def test_an_active_scenario_found_nowhere_is_still_an_error(self, project):
        _root, mocks = project
        body = dict(THIN, activeScenario="no_such")
        result = self._validate(_overlay(mocks, body))
        assert len(result.errors) == 1
        assert "no_such" in result.errors[0].message
        # The union view must be readable from the message: both sets named.
        assert "paging" in result.errors[0].message
        assert "overlays" in result.errors[0].message

    def test_a_mock_with_no_counterpart_is_judged_alone(self, project):
        # The protection the widening must not remove: a fully hand-written
        # route (nothing generated to inherit from) with no 'default' and
        # no activeScenario serves nothing predictable — still an error.
        _root, mocks = project
        body = dict(THIN)
        body["source"] = {"operationId": "other", "method": "GET",
                         "path": "/api/other"}
        result = self._validate(_overlay(mocks, body))
        assert len(result.errors) == 1
        assert "'default' is not among" in result.errors[0].message

    def test_the_counterpart_is_found_in_the_files_own_tree(self, project):
        """Anchoring, not discovery. When the run's declared mockDir does
        not contain the file being validated — a monorepo sub-project
        validated while an ancestor config answers — asking the declared
        directory about this file found nothing and judged the thin
        overlay alone, resurrecting the very error 1.7.22 removed. The
        file's own tree still has the sibling generated/."""
        _root, mocks = project
        overlay = _overlay(mocks, THIN)
        elsewhere = mocks.parent.parent / "other-project" / "mocks"
        elsewhere.mkdir(parents=True)
        set_mock_source(directory=elsewhere, boundary=elsewhere.parent)
        result = self._validate(overlay)
        assert [e.message for e in result.errors] == []

    def test_a_file_with_no_generated_sibling_is_still_judged_alone(
            self, project):
        """The protection the anchoring must not dissolve: no counterpart
        anywhere above the file means it IS the whole route."""
        _root, mocks = project
        lonely = mocks.parent.parent / "loose" / "listItems.mock.json"
        lonely.parent.mkdir(parents=True)
        lonely.write_text(json.dumps(THIN), encoding="utf-8")
        set_mock_source(directory=None, boundary=lonely.parent)
        result = self._validate(lonely)
        assert len(result.errors) == 1
        assert "'default' is not among" in result.errors[0].message

    def test_a_generated_file_is_judged_alone_too(self, project):
        _root, mocks = project
        gen = mocks / "generated" / "default" / "listItems.mock.json"
        data = json.loads(gen.read_text(encoding="utf-8"))
        data["activeScenario"] = "gone"
        gen.write_text(json.dumps(data), encoding="utf-8")
        result = self._validate(gen)
        assert any("gone" in e.message for e in result.errors)


class TestEveryIndexSeesTheUnion:
    """The overlay model guarantees every hand-written route a generated
    counterpart, so every index that collapses a route to ONE file picks
    its winner by directory sort order. That shape shipped four separate
    shadowing defects (generate detection, then — after v1.7.22 made the
    counterpart universal — the scenario-reference index, with the branch
    test lookup and the update-default target as the same class); the
    reference-index one reached a consumer as 24 errors whose `available:`
    sets all came from the generated side.
    """

    def test_the_reference_index_unions_both_files(self, project):
        # The reported regression: a test referencing a hand-written,
        # test-driven scenario must stay valid with the counterpart
        # present — and the generated side's scenarios stay valid too.
        # Asserting BOTH directions makes the red-check deterministic:
        # a one-file collapse loses one side whichever file wins.
        _root, mocks = project
        _overlay(mocks, THIN)
        index = find_mock_index(mocks / "custom" / "listItems.mock.json")
        assert index["listItems"] >= {"paging", "paging_page2", "default"}

    def test_branch_tests_read_the_merged_route(self, project):
        _root, mocks = project
        _overlay(mocks, dict(THIN, activeScenario="paging"))
        merged = index_mock_files(mocks)
        assert len(merged) == 1
        m = find_mock(merged, "GET", "/api/items")
        assert set(m.scenarios) >= {"paging", "paging_page2", "default"}
        # the hand-written explicit active wins, mirroring serve
        assert m.active_scenario == "paging"

    def test_update_default_repairs_the_generated_side_of_a_thin_overlay(
            self, project):
        # A thin overlay deliberately has no `default`; scaffolding one
        # into it would fork the very body the layout keeps unforked. The
        # served default comes from the generated side, so that is the
        # repair target — and the hand-written file's bytes stay untouched.
        root, mocks = project
        hand = _overlay(mocks, THIN, dirname="z-custom")
        before = hand.read_bytes()
        report = update_default([str(root / "swagger.json")], mocks)
        assert hand.read_bytes() == before
        assert all("z-custom/" not in rel for rel in report.updated)

    def test_update_default_repairs_a_hand_written_default_that_serves(
            self, project):
        # The other direction: a full hand-written mock DOES override the
        # generated default at serve time, so the repair belongs to it.
        root, mocks = project
        body = dict(THIN)
        body["scenarios"] = dict(THIN["scenarios"],
                                 default={"status": 200, "body": {}})
        hand = _overlay(mocks, body, dirname="z-custom")
        update_default([str(root / "swagger.json")], mocks)
        repaired = json.loads(hand.read_text(encoding="utf-8"))
        assert "id" in repaired["scenarios"]["default"]["body"]


def _wrong_type_default(scenarios: dict | None = None) -> dict:
    """A `default` whose `id` is an integer where the contract says string."""
    return dict(THIN, scenarios=dict(
        scenarios if scenarios is not None else THIN["scenarios"],
        default={"status": 200, "body": {"id": 1}}))


class TestTheCheckIndexSeesTheUnion:
    """`--check` compared the derived file and skipped the served one.

    Fifth member of the same family, and the one that matters most: serve
    resolves a request from the merged view, where a hand-written scenario
    overwrites the generated one of the same name — so the hand-written body
    is what a test receives. `_check`'s index collapsed the route last-wins
    over sorted paths, and `generated/` sorts after most tag directories, so
    the body that ships was never compared to the contract while the run
    printed "mocks are in sync with swagger".

    On the reporting project all ten hand-written mocks had a counterpart:
    0 of 10 files and 0 of 48 scenarios reached the comparison.
    """

    def _run(self, root, mocks):
        return _check([str(root / "swagger.json")], mocks)

    # Each collapse defect fires on one side of the sort order only. A
    # fixture on the wrong side passes without the fix, so both are asserted.
    @pytest.mark.parametrize("dirname", ["custom", "z-custom"])
    def test_a_hand_written_body_that_serves_is_compared(self, project, dirname):
        root, mocks = project
        rel = str(_overlay(mocks, _wrong_type_default(), dirname=dirname)
                  .relative_to(mocks))
        report = self._run(root, mocks)
        assert [d.rel for d in report.errors] == [rel]
        # It has to gate, not merely print: the reporting project read the
        # exit code and the closing line, both of which said clean.
        assert report.has_drift

    @pytest.mark.parametrize("dirname", ["custom", "z-custom"])
    def test_the_generated_counterpart_is_compared_too(self, project, dirname):
        # Not "whichever file wins" in the other direction — both. The
        # generated side keeps its own weight: reported, never gating.
        root, mocks = project
        _overlay(mocks, THIN, dirname=dirname)
        gen = mocks / "generated" / "default" / "listItems.mock.json"
        data = json.loads(gen.read_text(encoding="utf-8"))
        data["scenarios"]["default"]["body"] = {"id": 1}
        gen.write_text(json.dumps(data), encoding="utf-8")
        report = self._run(root, mocks)
        assert [d.rel for d in report.stale_generated] == [
            str(gen.relative_to(mocks))]
        assert report.errors == []
        assert not report.has_drift

    def test_a_matching_overlay_pair_reports_nothing(self, project):
        # The control. Widening the compared set is only useful if the
        # bodies that were never compared pass when they are correct — 10
        # files and 48 scenarios entered the comparison on the reporting
        # project's corpus and produced 0 findings.
        root, mocks = project
        _overlay(mocks, dict(THIN, scenarios=dict(
            THIN["scenarios"], default={"status": 200, "body": {"id": "1"}})))
        report = self._run(root, mocks)
        assert report.bodies == []
        assert not report.has_drift

    def test_a_retired_route_names_both_of_its_files(self, project):
        # The index change reaches the route-existence findings as well: a
        # route deleted upstream leaves two files behind, and they need
        # opposite advice — regenerate the derived one, decide about the
        # hand-written one. Naming one of them hid the other.
        root, mocks = project
        rel = str(_overlay(mocks, THIN).relative_to(mocks))
        (root / "swagger.json").write_text(
            json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
        report = self._run(root, mocks)
        assert [o.split(" ")[0] for o in report.orphaned] == [rel]
        assert [w.split(" ")[0] for w in report.warnings] == [
            "generated/default/listItems.mock.json"]


class TestTheGateClosesInBothSortOrders:
    """Findings and exit code are separate claims, and the gap was the defect.

    With the same files, the same swagger and the same command, renaming the
    tag directory from one that sorts after `generated/` to one that sorts
    before it turned a violating hand-written `default` from `[BODY]` +
    exit 1 into "No drift: mocks are in sync with swagger." + exit 0. So a
    green `--check` before this fix meant only that the directory name
    happened to be favourable.

    Run through the CLI rather than `_check`: the exit code is the part a CI
    job reads, and it is one `has_drift` and two printers away from the
    report object the other tests assert on.
    """

    def _project(self, tmp_path, dirname: str, hand_body, gen_body=None):
        (tmp_path / "swagger.json").write_text(json.dumps(SPEC),
                                               encoding="utf-8")
        mocks = tmp_path / "tests" / "mocks"
        generate([str(tmp_path / "swagger.json")], mocks)
        if gen_body is not None:
            gen = mocks / "generated" / "default" / "listItems.mock.json"
            data = json.loads(gen.read_text(encoding="utf-8"))
            data["scenarios"]["default"]["body"] = gen_body
            gen.write_text(json.dumps(data), encoding="utf-8")
        _overlay(mocks, dict(THIN, scenarios=dict(
            THIN["scenarios"], default={"status": 200, "body": hand_body})),
            dirname=dirname)
        (tmp_path / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": ["swagger.json"], "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "jsonui_test_cli.cli", "mock", "generate",
             "--check"],
            cwd=tmp_path, capture_output=True, text=True,
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                 "PATH": "/usr/bin:/bin"})
        return proc.returncode, proc.stdout + proc.stderr

    # "custom" sorts before `generated/`, "z-custom" after. The defect only
    # ever fired on one side, so one fixture is a coin toss.
    @pytest.mark.parametrize("dirname", ["custom", "z-custom"])
    def test_a_violating_hand_written_default_closes_the_gate(
            self, tmp_path, dirname):
        rc, out = self._project(tmp_path, dirname, {"wrong": "key"})
        assert rc == 1, out
        assert "[BODY]" in out
        assert "No drift" not in out

    @pytest.mark.parametrize("dirname", ["custom", "z-custom"])
    def test_a_violating_generated_default_does_not(self, tmp_path, dirname):
        # The other half of the ruling: the derived side is reported and
        # never gates, because regenerating fixes it. Widening what gets
        # compared must not quietly widen what fails.
        rc, out = self._project(tmp_path, dirname, {"id": "1"},
                                gen_body={"wrong": "key"})
        assert rc == 0, out
        assert "[WARN]" in out
        assert "stale" in out

    @pytest.mark.parametrize("dirname", ["custom", "z-custom"])
    def test_both_sides_drifting_produce_two_findings(self, tmp_path, dirname):
        """One arm per side, however many, cannot tell "both are checked"
        from "one is checked and each arm happened to hit the one".

        Breaking both at once separates them: an index that still resolves
        the route to a single file reports exactly one finding whichever
        file it picked. Two findings, with the weights split by file — the
        hand-written one gating, the derived one not — is the claim.
        """
        rc, out = self._project(tmp_path, dirname, {"wrong": "key"},
                                gen_body={"also_wrong": "key"})
        assert rc == 1, out
        assert out.count("[BODY]") == 1, out
        assert out.count("[WARN]") == 1, out


class TestServeAndCheckAgreeOnRouteIdentity:
    """A path variable's name is not part of the URL it matches.

    The checker has matched mocks to operations on the normalized route
    since a swagger rename detached every hand-written mock on it. `serve`
    kept grouping on the raw spelling, so the two disagreed about which
    files are one route — and disagreeing indexes is what produced this
    whole family. Here the disagreement is not a silent gap in a report but
    a mock that never answers: both files registered as endpoints with
    identical regexes, and the generated one, registered first, won.
    """

    def _store(self, tmp_path, hand_path: str) -> MockStore:
        gen = tmp_path / "generated" / "default" / "getItem.mock.json"
        gen.parent.mkdir(parents=True)
        gen.write_text(json.dumps({
            "source": {"operationId": "getItem", "method": "GET",
                       "path": "/api/items/{item_id}"},
            "scenarios": {"default": {"status": 200, "body": {"id": "gen"}}},
        }), encoding="utf-8")
        hand = tmp_path / "custom" / "getItem.mock.json"
        hand.parent.mkdir(parents=True)
        hand.write_text(json.dumps({
            "source": {"operationId": "getItem", "method": "GET",
                       "path": hand_path},
            "scenarios": {"default": {"status": 200, "body": {"id": "hand"}}},
        }), encoding="utf-8")
        return MockStore.load(tmp_path)

    def test_a_differently_spelled_variable_still_overlays(self, tmp_path):
        store = self._store(tmp_path, "/api/items/{id}")
        assert len(store.endpoints) == 1
        assert store.endpoints[0].scenarios["default"]["body"] == {"id": "hand"}
        assert store.overrides == ["custom/getItem.mock.json"]

    def test_the_same_spelling_is_unaffected(self, tmp_path):
        # The behaviour that already worked, pinned: normalizing must widen
        # what counts as one route, never change what a matched route serves.
        store = self._store(tmp_path, "/api/items/{item_id}")
        assert len(store.endpoints) == 1
        assert store.endpoints[0].scenarios["default"]["body"] == {"id": "hand"}

    def test_a_genuinely_different_route_stays_separate(self, tmp_path):
        store = self._store(tmp_path, "/api/items/{id}/history")
        assert len(store.endpoints) == 2
        assert store.overrides == []
