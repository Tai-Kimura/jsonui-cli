"""The `empty` scenario is an empty result, drawn from the schema, never the example with its array emptied.

Since 2.3.20 the `default` body is the example the OpenAPI document wrote, and `empty` was that body with its first
top-level array emptied: the counts, totals and flags beside it stayed the example's (`results: []` beside
`revoked: 1`), and a body whose example array was already empty came out as the default itself
(ticket 2026-10-23-jui-test-mock-empty-scenario-keeps-counts-from-example).

The rule:
- an `empty` is drawn when the body is an array, or an object with an array among its own properties; a response
  with no array, or arrays only deeper, has none;
- its body comes from the schema: every array [], every number 0 (its minimum when that is above 0), every boolean
  false, a nullable field null, an enum its first value, a string its type's sample; objects followed the same way;
- with no schema, an example that is an array gives [], anything else no `empty`.

The shapes are the reporting consumer's admin responses, cut down (its swagger read, not copied).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import build_mock_definition, compare_to_schema, generate
from jsonui_test_cli.mock.openapi import OpenApiDoc

RESULT = {"type": "object", "properties": {"bar_uuid": {"type": "string", "format": "uuid"}, "result": {"type": "string", "enum": ["revoked", "failed"]},
                                           "error": {"type": "string", "nullable": True}}}
SCHEMAS = {
    # array + counts: the bulk revoke
    "RevokeAll": {"type": "object", "required": ["results", "revoked", "failed", "already_revoked"], "properties": {
        "results": {"type": "array", "items": {"$ref": "#/components/schemas/Result"}},
        "revoked": {"type": "integer"}, "failed": {"type": "integer"}, "already_revoked": {"type": "integer"}}},
    "Result": RESULT,
    # array + a flag + a nested object: the deletion watch
    "Watch": {"type": "object", "properties": {
        "latest_run": {"type": "object", "properties": {"id": {"type": "integer"}, "started_at": {"type": "string", "format": "date-time"},
                                                        "remaining_file_count": {"type": "integer"}, "error": {"type": "string", "nullable": True}}},
        "poller_stale": {"type": "boolean"}, "db_undeleted_count": {"type": "integer"},
        "warnings": {"type": "array", "items": {"type": "string", "enum": ["unmapped_buckets", "poller_stale"]}}}},
    # counts, nullable fields, a flag and an array of runs: one batch
    "Batch": {"type": "object", "properties": {
        "batch_id": {"type": "string"}, "status": {"type": "string", "enum": ["ready", "running", "closed"]}, "received_count": {"type": "integer"}, "cost_micro_yen": {"type": "integer", "nullable": True},
        "closed_at": {"type": ["string", "null"], "format": "date-time"}, "cost_finalized": {"type": "boolean"},
        "job_runs": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}}}}}},
    # a page: the limit has a floor
    "Page": {"type": "object", "properties": {
        "batches": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}}}},
        "total": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1}, "offset": {"type": "integer", "minimum": 0},
        "ratio": {"type": "number", "exclusiveMinimum": 0.5}}},
    # arrays only deeper: one audited item
    "Item": {"type": "object", "properties": {"item": {"type": "object", "properties": {
        "id": {"type": "integer"}, "candidates": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}}}}}}}},
    # no array: the settings
    "Settings": {"type": "object", "properties": {"import_enabled": {"type": "boolean"}, "threshold": {"type": "number", "minimum": 0.9}}},
}
EXAMPLES = {
    "RevokeAll": {"results": [{"bar_uuid": "5b0c7a2e-3f41-4a8e-9d6b-2c1e8f7a9b10", "result": "revoked", "error": None}], "revoked": 1, "failed": 0, "already_revoked": 0},
    "Watch": {"latest_run": {"id": 9021, "started_at": "2026-10-22T12:15:00+09:00", "remaining_file_count": 0, "error": None},
              "poller_stale": False, "db_undeleted_count": 0, "warnings": []},
    "Batch": {"batch_id": "b-1", "status": "closed", "received_count": 120, "cost_micro_yen": 1500, "closed_at": None, "cost_finalized": True, "job_runs": []},
    "Page": {"batches": [{"id": 7}], "total": 1, "limit": 50, "offset": 0, "ratio": 0.9},
    "Item": {"item": {"id": 3, "candidates": [{"id": 1}]}},
    "Settings": {"import_enabled": True, "threshold": 0.95},
}


def _doc(name, media=None):
    media = media if media is not None else {"schema": {"$ref": f"#/components/schemas/{name}"}, "example": EXAMPLES[name]}
    return OpenApiDoc({"openapi": "3.0.3", "components": {"schemas": SCHEMAS}, "paths": {
        f"/x/{name.lower()}": {"get": {"operationId": f"get{name}", "responses": {"200": {"content": {"application/json": media}}}}}}})


def _scenarios(doc):
    (op,) = doc.operations()
    return build_mock_definition(doc, op)["scenarios"]


def _empty(name):
    return _scenarios(_doc(name)).get("empty", {}).get("body", "<none>")


class TestAnArrayAndItsCounts:
    def test_the_counts_go_to_zero_with_the_array(self):
        assert _empty("RevokeAll") == {"results": [], "revoked": 0, "failed": 0, "already_revoked": 0}

    def test_the_default_keeps_the_example(self):
        assert _scenarios(_doc("RevokeAll"))["default"]["body"] == EXAMPLES["RevokeAll"]


class TestAnArrayAFlagAndAnObject:
    def test_nothing_is_there_and_it_says_so(self):
        assert _empty("Watch") == {"latest_run": {"id": 0, "started_at": "2024-01-01T00:00:00Z", "remaining_file_count": 0, "error": None},
                                   "poller_stale": False, "db_undeleted_count": 0, "warnings": []}

    def test_it_is_not_the_default_whose_array_was_empty_already(self):
        sc = _scenarios(_doc("Watch"))
        assert sc["empty"]["body"] != sc["default"]["body"]


class TestNullableAFlagAndAnArray:
    def test_nullable_fields_null_a_flag_false_both_spellings(self):
        assert _empty("Batch") == {"batch_id": "string", "status": "ready", "received_count": 0, "cost_micro_yen": None, "closed_at": None,
                                   "cost_finalized": False, "job_runs": []}


class TestAFloorOnANumber:
    def test_a_minimum_above_zero_is_kept_and_an_exclusive_one_is_passed(self):
        body = _empty("Page")
        assert body["batches"] == [] and body["total"] == 0 and body["limit"] == 1 and body["offset"] == 0
        assert body["ratio"] > 0.5


class TestTheTwoSpellings:
    """OpenAPI 3.0 and 3.1 write an exclusive bound and a nullable body each its own way; both are read."""

    def test_an_exclusive_minimum_the_3_0_way(self):
        doc = OpenApiDoc({})
        assert doc.empty_for_schema({"type": "integer", "minimum": 0, "exclusiveMinimum": True}) == 1
        assert doc.empty_for_schema({"type": "integer", "minimum": 3, "exclusiveMinimum": True}) == 4

    def test_an_exclusive_minimum_the_3_1_way(self):
        assert OpenApiDoc({}).empty_for_schema({"type": "integer", "exclusiveMinimum": 0}) == 1

    def test_a_nullable_array_body_the_3_1_way_has_an_empty_and_it_is_an_empty_array(self):
        doc = _doc("X", {"schema": {"type": ["array", "null"], "items": {"$ref": "#/components/schemas/Result"}}, "example": [RESULT]})
        assert _scenarios(doc)["empty"]["body"] == []

    def test_a_nullable_array_body_the_3_0_way_too(self):
        doc = _doc("X", {"schema": {"type": "array", "nullable": True, "items": {"$ref": "#/components/schemas/Result"}}, "example": [RESULT]})
        assert _scenarios(doc)["empty"]["body"] == []

    def test_a_nullable_array_field_is_an_empty_array(self):
        doc = OpenApiDoc({})
        body = doc.empty_for_schema({"type": "object", "properties": {"rows": {"type": ["array", "null"], "items": {"type": "integer"}}, "n": {"type": "integer"}}})
        assert body == {"rows": [], "n": 0}


class TestNoEmptyWhereThereIsNoArrayOnTop:
    def test_arrays_only_deeper(self):
        assert "empty" not in _scenarios(_doc("Item"))

    def test_no_array(self):
        assert "empty" not in _scenarios(_doc("Settings"))


class TestNoSchema:
    def test_an_example_that_is_an_array(self):
        assert _scenarios(_doc("X", {"example": [{"id": 1}]}))["empty"]["body"] == []

    def test_an_example_that_is_an_object(self):
        assert "empty" not in _scenarios(_doc("X", {"example": {"results": [], "revoked": 1}}))

    def test_a_body_that_is_an_array_by_its_schema(self):
        doc = _doc("X", {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/Result"}}, "example": [RESULT]})
        assert _scenarios(doc)["empty"]["body"] == []


class TestTheEmptyBodyKeepsTheContract:
    def test_every_shape_passes_the_check_the_generator_runs(self):
        for name in ("RevokeAll", "Watch", "Batch", "Page"):
            doc = _doc(name)
            body = _empty(name)
            found = compare_to_schema(doc, {"$ref": f"#/components/schemas/{name}"}, body)
            assert found.violations == [] and found.missing == [], (name, found)

    def test_the_check_finds_no_drift_in_what_it_generated(self, tmp_path):
        spec = {"openapi": "3.0.3", "components": {"schemas": SCHEMAS}, "paths": {
            f"/x/{n.lower()}": {"get": {"operationId": f"get{n}", "responses": {"200": {"content": {"application/json": {
                "schema": {"$ref": f"#/components/schemas/{n}"}, "example": EXAMPLES[n]}}}}}} for n in EXAMPLES}}
        swagger = tmp_path / "swagger.json"
        swagger.write_text(json.dumps(spec), encoding="utf-8")
        generate([str(swagger)], tmp_path / "mocks")
        report = generate([str(swagger)], tmp_path / "mocks", check=True)
        assert not report.has_drift, report.drift_summary
        assert [d for d in report.bodies if d.scenario == "empty"] == []
