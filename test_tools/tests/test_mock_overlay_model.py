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
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.branch_tests import find_mock, index_mock_files
from jsonui_test_cli.mock.generate import generate, update_default
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
