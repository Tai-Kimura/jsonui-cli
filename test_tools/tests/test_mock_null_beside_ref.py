"""A null where the schema as written admits one is not a body violation.

Regression: jui-test-mock-check-drops-nullable-beside-ref.

`{"$ref": X, "nullable": true}` (OpenAPI 3.0.3) was read as X — the keywords
beside the `$ref` went with the resolve — so a scenario carrying the null the
server really sends was a [BODY] violation and `jsonui-test validate` failed
the whole gate, while the API codegen of the same toolkit reads the property
as nullable. A `oneOf` / `anyOf` null branch passed only in first position.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import GENERATED_DIR, compare_to_schema, generate
from jsonui_test_cli.mock.openapi import OpenApiDoc

X_REF = {"$ref": "#/components/schemas/Analysis"}
ANALYSIS = {"type": "object", "properties": {"score": {"type": "integer"}}}


def _doc(prop: dict) -> tuple[OpenApiDoc, dict]:
    holder = {"type": "object", "required": ["analysis"], "properties": {"analysis": prop}}
    spec = {"openapi": "3.0.3", "paths": {},
            "components": {"schemas": {"Analysis": ANALYSIS, "Note": holder}}}
    return OpenApiDoc(spec), holder


ADMITS_NULL = {
    "3.0 $ref + nullable": {**X_REF, "nullable": True},
    "3.0 allOf[$ref] + nullable": {"allOf": [X_REF], "nullable": True},
    "3.1 type list": {"type": ["object", "null"], "properties": ANALYSIS["properties"]},
    "3.1 oneOf, null second": {"oneOf": [X_REF, {"type": "null"}]},
    "3.1 oneOf, null first": {"oneOf": [{"type": "null"}, X_REF]},
    "3.1 anyOf, null second": {"anyOf": [X_REF, {"type": "null"}]},
}

REJECTS_NULL = {
    "$ref alone": X_REF,
    "$ref + nullable false": {**X_REF, "nullable": False},
    "oneOf without a null branch": {"oneOf": [X_REF, {"type": "string"}]},
}


@pytest.mark.parametrize("name", sorted(ADMITS_NULL))
def test_a_null_the_schema_admits_is_not_a_violation(name):
    doc, holder = _doc(ADMITS_NULL[name])
    assert compare_to_schema(doc, holder, {"analysis": None}).violations == []


@pytest.mark.parametrize("name", sorted(REJECTS_NULL))
def test_a_null_the_schema_does_not_admit_is_still_a_violation(name):
    doc, holder = _doc(REJECTS_NULL[name])
    assert compare_to_schema(doc, holder, {"analysis": None}).violations == [
        ".analysis: null, contract says object"]


def test_a_value_beside_ref_nullable_is_still_compared_with_the_target():
    """Only null skips the comparison; an object is checked against X."""
    doc, holder = _doc({**X_REF, "nullable": True})
    assert compare_to_schema(doc, holder, {"analysis": {"score": "high"}}).violations == [
        ".analysis.score: str, contract says integer"]


@pytest.mark.parametrize("nullable, expected", [
    (True, []),
    # The control: without `nullable` the same null IS drift — so the empty
    # list above is the body compared and passed, not a body never compared.
    (None, [".analysis: null, contract says object"]),
])
def test_the_mock_check_over_the_reported_shape(tmp_path, nullable, expected):
    """End to end, the reported shape: `--check` over a scenario with the null."""
    analysis = {**X_REF, "nullable": True} if nullable else dict(X_REF)
    spec = {
        "openapi": "3.0.3",
        "paths": {"/api/notes/{id}": {"get": {
            "operationId": "getNote", "tags": ["Notes"],
            "responses": {"200": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Note"}}}}},
        }}},
        "components": {"schemas": {
            "Analysis": ANALYSIS,
            "Note": {"type": "object", "required": ["id"], "properties": {
                "id": {"type": "string"},
                "analysis": analysis,
            }},
        }},
    }
    spec_path = tmp_path / "api.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "mocks"
    generate([str(spec_path)], out)
    # Adopted as hand-written, as test_mock_body_drift's _setup does: drift
    # under generated/ is a warning, the hand-written tree is the gate.
    [generated] = sorted((out / GENERATED_DIR).rglob("*.mock.json"))
    mock = out / generated.relative_to(out / GENERATED_DIR)
    mock.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(generated.read_text(encoding="utf-8"))
    data["scenarios"] = {"locked": {"status": 200, "body": {"id": "n1", "analysis": None}}}
    mock.write_text(json.dumps(data), encoding="utf-8")
    report = generate([str(spec_path)], out, check=True)
    assert [v for b in report.bodies for v in b.violations] == expected
    assert report.has_drift == bool(expected)
