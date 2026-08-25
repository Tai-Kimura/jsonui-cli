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
    GENERATED_DIR,
    compare_to_schema,
    generate,
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
        "/api/items": {
            "get": {
                "operationId": "listItems",
                "tags": ["Items"],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/ItemList"}}}}},
            }
        },
    },
    "components": {"schemas": {
        "FollowStatus": {
            "type": "object",
            "required": ["status", "new_arrival_notification"],
            "properties": {
                "status": {"type": "string", "enum": ["followed", "unfollowed"]},
                "bar_id": {"type": "string", "format": "uuid", "nullable": True},
                "new_arrival_notification": {"type": "boolean"},
            },
        },
        "Detail": {"type": "object", "properties": {"detail": {"type": "string"}}},
        "ItemList": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"$ref": "#/components/schemas/Item"}},
        }},
        "Item": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}, "series": {"type": "string"},
        }},
    }},
}


def _setup(tmp_path):
    """Generate, then adopt both mocks as hand-written.

    Most of these tests are about drift a person has to fix, which lives
    outside `generated/` — that tree is a pure function of the swagger and
    its findings are warnings. `TestGeneratedTree` covers the split itself.
    """
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    out = tmp_path / "mocks"
    generate([str(spec)], out)
    for src in sorted((out / GENERATED_DIR).rglob("*.mock.json")):
        dst = out / src.relative_to(out / GENERATED_DIR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    return str(spec), out


def _write(path, scenarios, source=None):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["scenarios"] = scenarios
    if source:
        data["source"].update(source)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
        # `bar_id` is optional in the contract, so it is a note, not drift.
        assert drift.missing == [".new_arrival_notification", ".status"]
        assert drift.optional == [".bar_id"]
        assert drift.extra == [".message"]
        assert "missing (required)" in str(drift)
        assert "missing (optional)" in str(drift)

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
        mock = out / "items" / "listItems.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "items": [{"id": "1", "brand": "x"}]}}})
        report = generate([spec], out, check=True)
        drift = report.bodies[0]
        # `series` is optional; the undeclared `brand` is the real problem.
        # Paths are indexed, so a bad element is identified, not just its array.
        assert drift.optional == [".items[0].series"]
        assert drift.extra == [".items[0].brand"]

    def test_an_empty_array_is_a_valid_instance_not_drift(self, tmp_path):
        # The generator emits exactly this for its own `empty` scenario.
        spec, out = _setup(tmp_path)
        mock = out / "items" / "listItems.mock.json"
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
        # Under route identity this is one deleted route plus one new one;
        # pairing by operationId keeps the actionable message.
        report = generate([spec], out, check=True)
        assert any("/api/old/follow" in d for d in report.drifted)
        assert report.missing == []
        assert report.orphaned == []


class TestMockIdentity:
    """Regression: mock-contract-validation-does-not-run.

    `mock serve` routes on source.method + source.path; the checker matched
    on filename. A project naming its mocks after the path had all 166
    reported as ORPHAN, all 188 operations as MISSING, and the body
    comparison — which only runs on matched files — never executed once.
    """

    def _renamed(self, tmp_path):
        spec, out = _setup(tmp_path)
        src = out / "bars" / "followBar.mock.json"
        dst = out / "bars" / "post_api-bars-by-uuid-follow.mock.json"
        src.rename(dst)
        return spec, out, dst

    def test_a_mock_named_anything_is_matched_by_its_route(self, tmp_path):
        spec, out, _ = self._renamed(tmp_path)
        report = generate([spec], out, check=True)
        assert report.missing == []
        assert report.orphaned == []

    def test_a_renamed_mock_is_still_body_checked(self, tmp_path):
        # The whole point: the body comparison must actually run.
        spec, out, dst = self._renamed(tmp_path)
        _write(dst, {"default": {"status": 200, "body": {"message": "string"}}})
        report = generate([spec], out, check=True)
        assert [d.scenario for d in report.bodies] == ["default"]

    def test_the_naming_difference_is_reported_but_is_not_drift(self, tmp_path):
        spec, out, _ = self._renamed(tmp_path)
        report = generate([spec], out, check=True)
        assert any("post_api-bars-by-uuid-follow" in m for m in report.misnamed)
        assert not report.has_drift

    def test_scaffolding_does_not_duplicate_a_renamed_mock(self, tmp_path):
        spec, out, _ = self._renamed(tmp_path)
        report = generate([spec], out)
        assert "bars/post_api-bars-by-uuid-follow.mock.json" in report.skipped
        assert not any("followBar" in c for c in report.created)

    def test_update_default_finds_a_renamed_mock(self, tmp_path):
        spec, out, dst = self._renamed(tmp_path)
        _write(dst, {"default": {"status": 200, "body": {"status": "followed"}}})
        report = update_default([spec], out)
        assert report.updated == ["bars/post_api-bars-by-uuid-follow.mock.json"]
        body = json.loads(dst.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert "new_arrival_notification" in body


class TestSchemaConformance:
    """Right keys is not the same as valid values."""

    def test_a_wrong_type_is_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "items" / "listItems.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "items": [{"id": "1", "series": 42}]}}})
        report = generate([spec], out, check=True)
        assert report.has_drift
        assert any("series" in v and "contract says string" in v
                   for v in report.bodies[0].violations)

    def test_a_missing_required_field_is_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "bar_id": "x"}}})
        report = generate([spec], out, check=True)
        assert report.bodies[0].missing == [".new_arrival_notification"]

    def test_a_value_outside_an_enum_is_reported(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "sideways", "bar_id": "x", "new_arrival_notification": True}}})
        report = generate([spec], out, check=True)
        assert any("sideways" in v for v in report.bodies[0].violations)

    def test_a_nullable_field_accepts_null(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "bar_id": None, "new_arrival_notification": True}}})
        assert not generate([spec], out, check=True).has_drift

    def test_a_valid_body_passes(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "items" / "listItems.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "items": [{"id": "1", "series": "Yamazaki"}]}}})
        assert not generate([spec], out, check=True).has_drift


class TestUpdateDefault:
    def test_adds_the_missing_required_fields(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"status": "followed"}}})

        report = update_default([spec], out)
        assert report.updated == ["bars/followBar.mock.json"]
        assert report.added["bars/followBar.mock.json"] == [".new_arrival_notification"]
        body = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert body["new_arrival_notification"] is not None
        assert not generate([spec], out, check=True).has_drift

    def test_never_overwrites_data_the_tests_read(self, tmp_path):
        # The `default` scenario is where a project grows its fixtures —
        # `mock generate` only ever scaffolds `default`, so there is nowhere
        # else for them to live. Replacing it reds out every assertion.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "bar_id": "R-2026-04871"}}})

        update_default([spec], out)
        body = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert body["bar_id"] == "R-2026-04871"
        assert body["status"] == "followed"

    def test_removes_nothing(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "new_arrival_notification": True,
            "receipt_available": True}}})
        update_default([spec], out)
        body = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert body["receipt_available"] is True

    def test_a_violation_a_merge_cannot_decide_is_reported_not_guessed(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": 42, "new_arrival_notification": True}}})
        report = update_default([spec], out)
        assert report.needs_review
        rel, problems = report.needs_review[0]
        assert any("contract says string" in p for p in problems)
        body = json.loads(mock.read_text(encoding="utf-8"))["scenarios"]["default"]["body"]
        assert body["status"] == 42  # left for a person

    def test_dry_run_writes_nothing(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"status": "followed"}}})
        before = mock.read_bytes()
        report = update_default([spec], out, dry_run=True)
        assert report.updated == ["bars/followBar.mock.json"]
        assert mock.read_bytes() == before

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


class TestGeneratedTree:
    """`generated/` is the tool's; everything else belongs to the project."""

    def _fresh(self, tmp_path):
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps(SPEC), encoding="utf-8")
        out = tmp_path / "mocks"
        generate([str(spec)], out)
        return str(spec), out

    def test_generation_writes_only_under_generated(self, tmp_path):
        _spec, out = self._fresh(tmp_path)
        written = sorted(p.relative_to(out) for p in out.rglob("*.mock.json"))
        assert written and all(p.parts[0] == GENERATED_DIR for p in written)

    def test_regeneration_drops_a_mock_whose_operation_is_gone(self, tmp_path):
        # Wipe-and-rewrite is what makes a contract change show up as a
        # regeneration instead of a hand-merge.
        spec, out = self._fresh(tmp_path)
        stale = out / GENERATED_DIR / "bars" / "goneAway.mock.json"
        stale.write_text(json.dumps({
            "source": {"operationId": "goneAway", "method": "GET", "path": "/api/gone"},
            "scenarios": {"default": {"status": 200, "body": {}}},
        }), encoding="utf-8")
        generate([spec], out)
        assert not stale.exists()

    def test_a_stale_generated_mock_is_a_warning_not_a_failure(self, tmp_path):
        spec, out = self._fresh(tmp_path)
        (out / GENERATED_DIR / "bars" / "extra.mock.json").write_text(json.dumps({
            "source": {"operationId": "extra", "method": "GET", "path": "/api/extra"},
            "scenarios": {"default": {"status": 200, "body": {}}},
        }), encoding="utf-8")
        report = generate([spec], out, check=True)
        assert not report.has_drift
        assert any("regenerate" in w for w in report.warnings)

    def test_a_stale_hand_written_mock_is_a_failure(self, tmp_path):
        spec, out = self._fresh(tmp_path)
        (out / "bars").mkdir(parents=True, exist_ok=True)
        (out / "bars" / "extra.mock.json").write_text(json.dumps({
            "source": {"operationId": "extra", "method": "GET", "path": "/api/extra"},
            "scenarios": {"default": {"status": 200, "body": {}}},
        }), encoding="utf-8")
        report = generate([spec], out, check=True)
        assert report.has_drift
        assert any("extra" in o for o in report.orphaned)

    def test_body_drift_inside_generated_does_not_fail_the_check(self, tmp_path):
        spec, out = self._fresh(tmp_path)
        mock = out / GENERATED_DIR / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"message": "x"}}})
        report = generate([spec], out, check=True)
        assert report.bodies and report.bodies[0].generated
        assert report.errors == []
        assert not report.has_drift


class TestOptionalFields:
    """Regression: mock-check-treats-optional-fields-as-drift.

    Omitting an optional field is a valid instance of the schema. Failing on
    it made the gate unusable — one project measured 53 scenarios of purely
    optional omissions against 0 real violations, another 13 against 0 — so
    consumers switched the check off and lost the real signal with it. Worse,
    filling them in mechanically puts null into non-nullable slots and
    manufactures violations that were not there.
    """

    def test_a_missing_optional_field_is_a_note_not_drift(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "new_arrival_notification": True}}})
        report = generate([spec], out, check=True)
        assert report.bodies[0].optional == [".bar_id"]
        assert report.bodies[0].is_note_only
        assert not report.has_drift

    def test_a_missing_required_field_still_fails(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"status": "followed"}}})
        report = generate([spec], out, check=True)
        assert report.bodies[0].missing == [".new_arrival_notification"]
        assert report.has_drift

    def test_a_field_the_contract_does_not_have_still_fails(self, tmp_path):
        # The front end reading a value the server never sends is exactly
        # what the previous report was about.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "new_arrival_notification": True, "extra": 1}}})
        report = generate([spec], out, check=True)
        assert report.bodies[0].extra == [".extra"]
        assert report.has_drift

    def test_a_required_field_under_an_omitted_optional_parent_is_optional(self, tmp_path):
        # Leaving out an optional object legitimately leaves out its required
        # children; reporting those as violations would be wrong.
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps({
            "openapi": "3.0.0",
            "paths": {"/api/x": {"get": {
                "tags": ["X"], "operationId": "getX",
                "responses": {"200": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["id"], "properties": {
                        "id": {"type": "string"},
                        "tier": {"type": "object", "required": ["tier_id"],
                                     "properties": {"tier_id": {"type": "string"}}},
                    }}}}}},
            }}},
        }), encoding="utf-8")
        out = tmp_path / "mocks"
        generate([str(spec)], out)
        mock = out / GENERATED_DIR / "x" / "getX.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"id": "1"}}})
        report = generate([str(spec)], out, check=True)
        drift = report.bodies[0]
        # The walk stops at the absent optional parent — reporting its
        # required children would be reporting an omission that is not one.
        assert drift.missing == []
        assert drift.optional == [".tier"]

    def test_notes_and_violations_are_labelled_separately(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {"status": "followed"}}})
        rendered = str(generate([spec], out, check=True).bodies[0])
        assert "missing (required): .new_arrival_notification" in rendered
        assert "missing (optional): .bar_id" in rendered

    def test_strict_promotes_optional_omissions_without_relabelling_them(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        _write(mock, {"default": {"status": 200, "body": {
            "status": "followed", "new_arrival_notification": True}}})
        report = generate([spec], out, check=True, strict=True)
        assert report.has_drift
        # Still reported as optional — strict changes the weight, not the fact.
        assert report.bodies[0].optional == [".bar_id"]
        assert report.errors == report.bodies


class TestArrayElementShape:
    """Regression: mock-check-array-element-shape-false-positives.

    The comparison flattened both sides into key sets, which forces one
    representative shape per array. Two false positives fell out of that: a
    `nullable` array holding `null` was asked for its element shape, and one
    empty element made the OTHER elements' fields read as undeclared.
    """

    ARRAYS = {
        "openapi": "3.0.0",
        "paths": {"/api/plan": {"get": {
            "tags": ["Plan"], "operationId": "getPlan",
            "responses": {"200": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Plan"}}}}},
        }}},
        "components": {"schemas": {
            "Plan": {"type": "object", "properties": {
                "unit_rates": {"type": "array", "nullable": True,
                                "items": {"$ref": "#/components/schemas/Rate"}},
                "shelves": {"type": "array", "items": {"$ref": "#/components/schemas/Shelf"}},
            }},
            "Rate": {"type": "object", "required": ["apply_on_peak", "unit_price"],
                     "properties": {"apply_on_peak": {"type": "boolean"},
                                    "unit_price": {"type": "integer"}}},
            "Shelf": {"type": "object", "required": ["name"], "properties": {
                "name": {"type": "string"},
                "assignments": {"type": "array",
                                "items": {"$ref": "#/components/schemas/Assignment"}}}},
            "Assignment": {"type": "object", "required": ["variant_id"], "properties": {
                "variant_id": {"type": "string"},
                "tier_name": {"type": "string", "nullable": True}}},
        }},
    }

    def _project(self, tmp_path, body):
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps(self.ARRAYS), encoding="utf-8")
        out = tmp_path / "mocks"
        generate([str(spec)], out)
        mock = out / GENERATED_DIR / "plan" / "getPlan.mock.json"
        _write(mock, {"default": {"status": 200, "body": body}})
        return generate([str(spec)], out, check=True)

    def test_a_nullable_array_holding_null_is_not_asked_for_element_shape(self, tmp_path):
        # null is a valid value and there are no elements — an absent array is
        # not an array of absent elements.
        report = self._project(tmp_path, {"unit_rates": None, "shelves": []})
        assert report.bodies == [] or report.bodies[0].missing == []

    def test_an_empty_element_does_not_invalidate_its_siblings(self, tmp_path):
        report = self._project(tmp_path, {"unit_rates": None, "shelves": [
            {"name": "A-01", "assignments": [
                {"variant_id": "u1", "tier_name": "標準A"}]},
            {"name": "A-03", "assignments": []},
        ]})
        drift = report.bodies[0] if report.bodies else None
        assert drift is None or drift.extra == []
        assert drift is None or drift.missing == []

    def test_a_bad_element_is_identified_by_its_index(self, tmp_path):
        report = self._project(tmp_path, {"unit_rates": None, "shelves": [
            {"name": "A-01"},
            {"name": 42},
        ]})
        violations = report.bodies[0].violations
        assert any(".shelves[1].name" in v for v in violations)
        assert not any(".shelves[0].name" in v for v in violations)


class TestSourceIdentityIsPreserved:
    """Regression: mock-update-default-renames-source-operationid-…

    `operationId` is the key test files select a scenario with
    (`mocks: { "<operationId>": ... }`). The server routes by method+path and
    only *reports* a naming difference, so rewriting the id detaches every
    reference to it — and `scenario-set` answered 200 for the now-unknown
    key, so a caller checking `res.ok()` ran on `default` and went green.
    """

    def _renamed_id(self, tmp_path):
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        data = json.loads(mock.read_text(encoding="utf-8"))
        data["source"]["operationId"] = "post_api-bars-by-uuid-follow"
        data["scenarios"] = {"default": {"status": 200, "body": {"status": "followed"}}}
        mock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return spec, out, mock

    def test_update_default_keeps_the_projects_operation_id(self, tmp_path):
        spec, out, mock = self._renamed_id(tmp_path)
        update_default([spec], out)
        source = json.loads(mock.read_text(encoding="utf-8"))["source"]
        assert source["operationId"] == "post_api-bars-by-uuid-follow"

    def test_update_default_still_repairs_a_drifted_route(self, tmp_path):
        spec, out, mock = self._renamed_id(tmp_path)
        data = json.loads(mock.read_text(encoding="utf-8"))
        data["source"]["path"] = "/api/old/follow"
        mock.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        update_default([spec], out)
        source = json.loads(mock.read_text(encoding="utf-8"))["source"]
        assert source["path"] == "/api/bars/{bar_uuid}/follow"
        assert source["operationId"] == "post_api-bars-by-uuid-follow"

    def test_a_file_needing_no_repair_is_not_rewritten(self, tmp_path):
        # Rewriting re-serialises the whole file; doing it for nothing buries
        # the one repaired field in a reformatting diff.
        spec, out = _setup(tmp_path)
        mock = out / "bars" / "followBar.mock.json"
        mock.write_text(mock.read_text(encoding="utf-8").replace("\n  ", "\n\t"),
                        encoding="utf-8")
        before = mock.read_bytes()
        update_default([spec], out)
        assert mock.read_bytes() == before
