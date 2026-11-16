"""The default scenario serves the example the OpenAPI document wrote.

OpenAPI 3 puts a response's example in two places: on the schema, or on the
media type (`responses.<code>.content.<media>.example`, or the `examples`
map). Generation read only the schema's, so an operation whose example sat
on the media type got a body synthesised from the types — `0`, `"string"`,
`true`, the first enum value. Measured on a consumer's admin swagger: twelve
operations kept their example there, and a deletion watch whose example
says "nothing wrong" was mocked with `poller_stale: true`, a warning and an
error string, while a threshold with `minimum: 0.9` came out as `0`.

The order a body is taken from:

1. the media type's `example`
2. the first of the media type's `examples` that has a `value`
   (a `$ref` into `components/examples` is followed)
3. the schema's `example` (beside a `$ref` first, then the resolved schema),
   then the first of its `examples` list
4. synthesis from the types

Each place has an arm below, and each arm reads the generated scenario, the
value a test's `api.*: "default"` is served.
"""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import build_mock_definition, generate
from jsonui_test_cli.mock.openapi import OpenApiDoc

SCHEMA_EXAMPLE = {"id": 1, "state": "from-schema"}
MEDIA_EXAMPLE = {"id": 2, "state": "from-media"}
NAMED_FIRST = {"id": 3, "state": "first-named"}
NAMED_SECOND = {"id": 4, "state": "second-named"}

ITEM = {"type": "object", "required": ["id", "state"],
        "properties": {"id": {"type": "integer"},
                       "state": {"type": "string", "enum": ["synth", "other"]}}}


def _doc(media: dict, schemas: dict | None = None, extra: dict | None = None) -> OpenApiDoc:
    components = {"schemas": {"Item": ITEM, **(schemas or {})}, **(extra or {})}
    return OpenApiDoc({"openapi": "3.0.3", "components": components, "paths": {
        "/items/{id}": {"get": {"operationId": "getItem", "responses": {
            "200": {"content": {"application/json": media}},
            "404": {"content": {"application/json": {
                "schema": {"type": "object", "properties": {"detail": {"type": "string"}}},
                "example": {"detail": "no such item"}}}}}}}}})


def _scenarios(doc: OpenApiDoc) -> dict:
    (op,) = doc.operations()
    return build_mock_definition(doc, op)["scenarios"]


def _default(doc: OpenApiDoc):
    return _scenarios(doc)["default"]["body"]


REF = {"$ref": "#/components/schemas/Item"}


class TestEachPlaceIsRead:
    def test_the_media_types_example(self):
        assert _default(_doc({"schema": REF, "example": MEDIA_EXAMPLE})) == MEDIA_EXAMPLE

    def test_the_first_of_the_media_types_examples(self):
        doc = _doc({"schema": REF, "examples": {
            "ok": {"summary": "first", "value": NAMED_FIRST},
            "other": {"value": NAMED_SECOND}}})
        assert _default(doc) == NAMED_FIRST

    def test_an_examples_entry_that_points_into_components(self):
        doc = _doc({"schema": REF, "examples": {"ok": {"$ref": "#/components/examples/Ok"}}},
                   extra={"examples": {"Ok": {"value": NAMED_FIRST}}})
        assert _default(doc) == NAMED_FIRST

    def test_an_entry_with_only_an_external_value_is_passed_over(self):
        # Nothing is fetched: the next entry that carries a value is used.
        doc = _doc({"schema": REF, "examples": {
            "remote": {"externalValue": "https://example.invalid/item.json"},
            "local": {"value": NAMED_SECOND}}})
        assert _default(doc) == NAMED_SECOND

    def test_the_schemas_example(self):
        doc = _doc({"schema": REF}, schemas={"Item": {**ITEM, "example": SCHEMA_EXAMPLE}})
        assert _default(doc) == SCHEMA_EXAMPLE

    def test_the_schemas_examples_list(self):
        doc = _doc({"schema": REF}, schemas={"Item": {**ITEM, "examples": [SCHEMA_EXAMPLE]}})
        assert _default(doc) == SCHEMA_EXAMPLE

    def test_an_example_written_beside_a_ref(self):
        doc = _doc({"schema": {"$ref": "#/components/schemas/Item", "example": SCHEMA_EXAMPLE}})
        assert _default(doc) == SCHEMA_EXAMPLE

    def test_a_propertys_example(self):
        item = {**ITEM, "properties": {**ITEM["properties"], "id": {"type": "integer", "example": 77}}}
        assert _default(_doc({"schema": REF}, schemas={"Item": item}))["id"] == 77

    def test_a_media_example_with_no_schema(self):
        assert _default(_doc({"example": MEDIA_EXAMPLE})) == MEDIA_EXAMPLE

    def test_an_error_responses_media_example(self):
        scen = _scenarios(_doc({"schema": REF}))["error_404"]
        assert scen == {"status": 404, "body": {"detail": "no such item"}}

    def test_none_written_falls_back_to_the_types(self):
        assert _default(_doc({"schema": REF})) == {"id": 0, "state": "synth"}


class TestTheOrder:
    def test_media_example_before_media_examples(self):
        doc = _doc({"schema": REF, "example": MEDIA_EXAMPLE,
                    "examples": {"ok": {"value": NAMED_FIRST}}})
        assert _default(doc) == MEDIA_EXAMPLE

    def test_the_media_type_before_the_schema(self):
        doc = _doc({"schema": REF, "examples": {"ok": {"value": NAMED_FIRST}}},
                   schemas={"Item": {**ITEM, "example": SCHEMA_EXAMPLE}})
        assert _default(doc) == NAMED_FIRST

    def test_beside_the_ref_before_the_referenced_schema(self):
        doc = _doc({"schema": {"$ref": "#/components/schemas/Item", "example": MEDIA_EXAMPLE}},
                   schemas={"Item": {**ITEM, "example": SCHEMA_EXAMPLE}})
        assert _default(doc) == MEDIA_EXAMPLE


# The shape of the reporting consumer's deletion watch: the example on the
# media type says "nothing wrong", and every field synthesis picks from the
# types says the opposite (a stale poller, a warning, an error string).
WATCH_SPEC = {
    "openapi": "3.0.3",
    "paths": {"/api/admin/import/deletion-watch": {"get": {
        "operationId": "getDeletionWatch", "tags": ["admin"],
        "responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/DeletionWatch"},
            "example": {"latest_run": {"id": 9021, "started_at": "2026-10-20T03:00:00Z",
                                       "deleted_count": 2, "error": None},
                        "poller_stale": False, "db_undeleted_count": 0, "warnings": [],
                        "threshold": 0.95}}}}}}}},
    "components": {"schemas": {"DeletionWatch": {
        "type": "object",
        "required": ["latest_run", "poller_stale", "db_undeleted_count", "warnings", "threshold"],
        "properties": {
            "latest_run": {"type": "object", "properties": {
                "id": {"type": "integer"},
                "started_at": {"type": "string", "format": "date-time"},
                "deleted_count": {"type": "integer"},
                "error": {"type": "string", "nullable": True}}},
            "poller_stale": {"type": "boolean"},
            "db_undeleted_count": {"type": "integer"},
            "warnings": {"type": "array", "items": {"type": "string", "enum": ["unmapped_buckets", "slow_poller"]}},
            "threshold": {"type": "number", "minimum": 0.9, "maximum": 1}}}}},
}


class TestTheReportedShape:
    def _generate(self, tmp_path, spec=WATCH_SPEC):
        swagger = tmp_path / "swagger.json"
        swagger.write_text(json.dumps(spec), encoding="utf-8")
        mocks = tmp_path / "mocks"
        generate([str(swagger)], mocks)
        (path,) = (mocks / "generated").rglob("*.mock.json")
        return swagger, mocks, json.loads(path.read_text(encoding="utf-8"))

    def test_the_written_default_is_the_documents_example(self, tmp_path):
        _, _, data = self._generate(tmp_path)
        expected = WATCH_SPEC["paths"]["/api/admin/import/deletion-watch"]["get"][
            "responses"]["200"]["content"]["application/json"]["example"]
        assert data["scenarios"]["default"]["body"] == expected
        assert data["scenarios"]["default"]["body"]["threshold"] >= 0.9

    def test_the_check_finds_nothing_in_it(self, tmp_path):
        swagger, mocks, _ = self._generate(tmp_path)
        report = generate([str(swagger)], mocks, check=True)
        assert not report.has_drift, report.drift_summary
        assert report.bodies == []

    def test_the_checks_remedy_is_judged_against_the_same_order(self, tmp_path):
        # An example that breaks its own schema is the document's mistake:
        # the check reports it, and must not say that regenerating fixes it,
        # since regenerating writes the same example back. That judgement
        # rebuilds the scenario, so it has to rebuild it from the same place.
        spec = copy.deepcopy(WATCH_SPEC)
        spec["paths"]["/api/admin/import/deletion-watch"]["get"]["responses"]["200"][
            "content"]["application/json"]["example"]["threshold"] = "high"
        swagger, mocks, data = self._generate(tmp_path, spec)
        assert data["scenarios"]["default"]["body"]["threshold"] == "high"
        report = generate([str(swagger)], mocks, check=True)
        (drift,) = [d for d in report.bodies if d.scenario == "default"]
        assert drift.regenerating_helps is False
