"""Tests for mock body drift detection and --update-default.

Regression: test-mock-generate-check-misses-stale-response-bodies.

`--check` compared only `source.method` / `source.path`, so a mock whose
response body encoded a contract the server no longer had reported "No drift".
Silent *and* reassuring: UI tests stayed green against a fiction. In the
reporting project 26 of 151 mocks were stale and the check named none of them.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import (
    empty_array_prefixes,
    generate,
    key_paths,
    update_default,
)


SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/bars/{bar_uuid}/follow": {
            "post": {
                "operationId": "followBar",
                "tags": ["Bars"],
                "responses": {
                    "200": {"content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/FollowStatus"}}}},
                    "404": {"content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/Detail"}}}},
                },
            }
        },
        "/api/bottles": {
            "get": {
                "operationId": "listBottles",
                "tags": ["Bottles"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/BottleList"}}}}},
            }
        },
    },
    "components": {"schemas": {
        "FollowStatus": {"type": "object", "properties": {
            "status": {"type": "string"},
            "bar_id": {"type": "string", "format": "uuid"},
            "new_arrival_notification": {"type": "boolean"},
        }},
        "Detail": {"type": "object", "properties": {"detail": {"type": "string"}}},
        "BottleList": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/Bottle"}},
        }},
        "Bottle": {"type": "object", "properties": {
            "id": {"type": "string"}, "series": {"type": "string"},
        }},
    }},
}


def _setup(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / "mocks"
    generate([str(spec)], out)
    return str(spec), out


def _write(path, scenarios, source=None):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scenarios"] = scenarios
    if source:
        data["source"].update(source)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestKeyPaths:
    def test_descends_objects_and_arrays(self):
        assert key_paths({"a": {"b": 1}}) == {".a", ".a.b"}
        assert key_paths({"items": [{"id": 1}]}) == {".items", ".items[].id"}

    def test_empty_array_prefixes_finds_the_emptied_field(self):
        assert empty_array_prefixes({"items": []}) == {".items[]"}
        assert empty_array_prefixes({"items": [{"id": 1}]}) == set()


class TestBodyDrift:
    def test_a_freshly_generated_tree_has_no_drift(self, tmp_path):
        spec, out = _setup(tmp_path)
        assert not generate([spec], out, check=True).has_drift

    def test_a_stale_body_is_reported_with_both_directions(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"message": "string"}}})

        report = generate([spec], out, check=True)
        assert report.has_drift
        assert len(report.bodies) == 1
        drift = report.bodies[0]
        assert drift.scenario == "default"
        assert drift.missing == [".bar_id", ".new_arrival_notification", ".status"]
        assert drift.extra == [".message"]
        assert "swagger has, mock lacks" in str(drift)

    def test_scenarios_are_matched_by_status_not_by_name(self, tmp_path):
        # The trap the report called out: a name-based rule mangles a
        # legitimately error-shaped scenario called `not_found`.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {
            "default": {"status": 200, "body": {
                "status": "followed", "bar_id": "x", "new_arrival_notification": True}},
            "not_found": {"status": 404, "body": {"detail": "no such bar"}},
        })
        assert not generate([spec], out, check=True).has_drift

    def test_a_scenario_with_the_wrong_error_shape_is_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {
            "default": {"status": 200, "body": {
                "status": "followed", "bar_id": "x", "new_arrival_notification": True}},
            "not_found": {"status": 404, "body": {"message": "no such bar"}},
        })
        report = generate([spec], out, check=True)
        assert [d.scenario for d in report.bodies] == ["not_found"]

    def test_drift_inside_array_items_is_found(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bottles" / "listBottles.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "items": [{"id": "1", "brand": "x"}]}}})
        report = generate([spec], out, check=True)
        drift = report.bodies[0]
        assert drift.missing == [".items[].series"]
        assert drift.extra == [".items[].brand"]

    def test_an_empty_array_is_a_valid_instance_not_drift(self, tmp_path):
        # The generator emits exactly this for its own `empty` scenario.
        spec, out = _setup(tmp_path)
        mock = out / "bottles" / "listBottles.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"items": []}}})
        assert not generate([spec], out, check=True).has_drift

    def test_a_missing_body_is_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200}})
        assert generate([spec], out, check=True).bodies[0].missing == ["<body>"]

    def test_an_undeclared_status_is_noted_but_not_drift(self, tmp_path):
        # A deliberate edge case the spec does not describe — there is
        # nothing to compare it to, so it is surfaced rather than failed.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {
            "default": {"status": 200, "body": {
                "status": "followed", "bar_id": "x", "new_arrival_notification": True}},
            "teapot": {"status": 418, "body": {"anything": True}},
        })
        report = generate([spec], out, check=True)
        assert not report.has_drift
        assert any("418 not declared" in n for n in report.unmatched)

    def test_source_drift_is_still_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        data = json.loads(mock.read_text(encoding="utf-8"))
        data["source"]["path"] = "/api/old/follow"
        mock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        assert any("/api/old/follow" in d for d in generate([spec], out, check=True).drifted)


class TestUpdateDefault:
    def test_refreshes_the_default_body_and_clears_the_check(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"message": "string"}}})

        report = update_default([spec], out)
        assert report.updated == ["bars/followBar.mock.json"]
        body = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert set(body) == {"status", "bar_id", "new_arrival_notification"}
        assert not generate([spec], out, check=True).has_drift

    def test_leaves_hand_grown_scenarios_untouched(self, tmp_path):
        # 50 of 151 mocks in the reporting project carry scenarios the tests
        # drive; regenerating them would replace fixtures with placeholders.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        driven = {"status": 200, "body": {"status": "followed", "bar_id": "real-id",
                                          "new_arrival_notification": False}}
        _write(mock, {
            "default": {"status": 200, "body": {"message": "string"}},
            "real_id": dict(driven),
            "not_found": {"status": 404, "body": {"detail": "no such bar"}},
        })
        update_default([spec], out)
        scenarios = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]
        assert scenarios["real_id"] == driven
        assert scenarios["not_found"] == {"status": 404, "body": {"detail": "no such bar"}}

    def test_repairs_a_drifted_source_path(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        data = json.loads(mock.read_text(encoding="utf-8"))
        data["source"]["path"] = "/api/old/follow"
        mock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        update_default([spec], out)
        assert json.loads(mock.read_text(encoding="utf-8"))["source"]["path"] \
            == "/api/bars/{bar_uuid}/follow"

    def test_keeps_the_recorded_swagger_path(self, tmp_path):
        # Otherwise every mock churns the moment someone runs this from a
        # different directory.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        data = json.loads(mock.read_text(encoding="utf-8"))
        data["source"]["swagger"] = "../docs/api/swagger.json"
        mock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        update_default([spec], out)
        assert json.loads(mock.read_text(encoding="utf-8"))["source"]["swagger"] \
            == "../docs/api/swagger.json"

    def test_a_current_tree_is_left_alone(self, tmp_path):
        spec, out = _setup(tmp_path)
        report = update_default([spec], out)
        assert report.updated == []
        assert len(report.unchanged) == 2
