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

from jsonui_test_cli.mock.generate import generate
from jsonui_test_cli.validation.mock import set_mock_source
from jsonui_test_cli.validation.validator import TestValidator

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/items": {"get": {
            "operationId": "listItems",
            "responses": {"200": {"content": {"application/json": {
                "schema": {"type": "object",
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


def _overlay(mocks: Path, body: dict) -> Path:
    # The directory name is load-bearing: the shadowing this file guards
    # against was LAST-WINS collapse over `sorted(rglob(...))`, so it only
    # fired when the hand-written directory sorted BEFORE `generated/`
    # (the reporting consumer's tag dirs did; an `items/` fixture sorts
    # after and hides the defect by accident).
    path = mocks / "custom" / "listItems.mock.json"
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
