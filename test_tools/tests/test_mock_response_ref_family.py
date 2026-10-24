"""A response written as a `$ref` reaches the mock (ticket 2026-10-24-jui-mock-generate-ignores-response-ref).

OpenAPI 3 shares a response through `#/components/responses/*`, and the operation's entry is then only the `$ref`.
Read raw it had no `content`: the error scenario was `{"detail": "HTTP 429"}` beside an example that said otherwise,
the success body `{}`, `--check` filed the status as declaring no body (so a hand-written error body was never
compared), and `mock update` added nothing. The family, in JSON and in YAML OpenAPI alike: a response `$ref` (to a
schema, to a media `example`, to `examples` with a value or a `$ref` into components/examples, through a second
`$ref`) is read by generate's default / empty / error scenarios, by `--check` on a declared status and on one that
falls to `default`, and by `mock update`; an example entry's `$ref` chain is followed whole; a loop stops as no body;
a request body's `$ref` is checked by serve.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock import contract
from jsonui_test_cli.mock.generate import build_mock_definition, generate, update_default
from jsonui_test_cli.mock.openapi import OpenApiDoc

ERR = {"type": "object", "required": ["error_code"], "properties": {"error_code": {"type": "string"}}}
LIST = {"type": "object", "required": ["items", "total"],
        "properties": {"items": {"type": "array", "items": {"type": "integer"}}, "total": {"type": "integer"}}}
EX = {"error_code": "rate_limited"}


def _resp(media: dict) -> dict:
    return {"description": "x", "content": {"application/json": media}}


SCHEMA = {"$ref": "#/components/schemas/Err"}
# name -> (components/responses beside List, the error body generate must write)
MATERIALS = {
    "schema only": ({"Err": _resp({"schema": SCHEMA})}, {"error_code": "string"}),
    "media example": ({"Err": _resp({"schema": SCHEMA, "example": EX})}, EX),
    "media examples value": ({"Err": _resp({"schema": SCHEMA, "examples": {"a": {"value": EX}}})}, EX),
    "media examples -> components/examples":
        ({"Err": _resp({"schema": SCHEMA, "examples": {"a": {"$ref": "#/components/examples/E"}}})}, EX),
    "media examples -> $ref -> $ref":
        ({"Err": _resp({"schema": SCHEMA, "examples": {"a": {"$ref": "#/components/examples/E0"}}})}, EX),
    "$ref -> $ref": ({"Err": {"$ref": "#/components/responses/Err2"}, "Err2": _resp({"schema": SCHEMA, "example": EX})}, EX),
}


def _write(tmp_path: Path, fmt: str, responses: dict, request_body=None) -> Path:
    op = {"operationId": "getX", "responses": {"200": {"$ref": "#/components/responses/List"},
                                               "429": {"$ref": "#/components/responses/Err"},
                                               "default": {"$ref": "#/components/responses/Err"}}}
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"},
            "components": {"schemas": {"Err": ERR, "List": LIST},
                           "examples": {"E": {"value": EX}, "E0": {"$ref": "#/components/examples/E"}},
                           "requestBodies": {"B": {"required": True, "content": {"application/json": {"schema": ERR}}}},
                           "responses": {"List": _resp({"schema": {"$ref": "#/components/schemas/List"}}), **responses}},
            "paths": {"/x": {"get": op}}}
    if request_body is not None:
        spec["paths"]["/x"] = {"post": {**op, "requestBody": request_body}}
    path = tmp_path / f"api.{fmt}"
    path.write_text(json.dumps(spec) if fmt == "json" else yaml.safe_dump(spec), encoding="utf-8")
    return path


def _hand_written(mock_dir: Path) -> None:
    path = mock_dir / "x" / "getX.mock.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "source": {"method": "GET", "path": "/x", "operationId": "getX"}, "activeScenario": "default",
        "scenarios": {"default": {"status": 200, "body": {"items": []}},
                      "e429": {"status": 429, "body": {"error_code": 5}},
                      "e503": {"status": 503, "body": {"error_code": 5}}}}))


@pytest.mark.parametrize("fmt", ["json", "yaml"])
@pytest.mark.parametrize("material", list(MATERIALS))
def test_generate_reads_a_response_ref(tmp_path, fmt, material):
    responses, error_body = MATERIALS[material]
    doc = OpenApiDoc.load(_write(tmp_path, fmt, responses))
    (op,) = doc.operations()
    scenarios = build_mock_definition(doc, op)["scenarios"]
    assert scenarios["default"]["body"] == {"items": [0], "total": 0}
    assert scenarios["empty"]["body"] == {"items": [], "total": 0}
    assert scenarios["error_429"] == {"status": 429, "body": error_body}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
@pytest.mark.parametrize("material", list(MATERIALS))
def test_check_and_update_read_a_response_ref(tmp_path, fmt, material):
    swagger = str(_write(tmp_path, fmt, MATERIALS[material][0]))
    mock_dir = tmp_path / "mocks"
    generate([swagger], mock_dir)
    _hand_written(mock_dir)
    report = generate([swagger], mock_dir, check=True)
    hand = [b for b in report.bodies if b.rel == "x/getX.mock.json"]
    # 429 is declared, 503 falls to `default`: both bodies are compared to the referenced schema and named.
    assert sorted(b.scenario for b in hand) == ["default", "e429", "e503"]
    assert [b.missing for b in hand if b.scenario == "default"] == [[".total"]]
    assert all(b.violations for b in hand if b.scenario != "default")
    assert not [n for n in report.no_schema if "getX" in n]
    assert update_default([swagger], mock_dir, dry_run=True).added == {"x/getX.mock.json": [".total"]}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_a_looping_response_ref_is_no_body(tmp_path, fmt):
    loop = {"Err": {"$ref": "#/components/responses/Err2"}, "Err2": {"$ref": "#/components/responses/Err"}}
    doc = OpenApiDoc.load(_write(tmp_path, fmt, loop))
    (op,) = doc.operations()
    assert build_mock_definition(doc, op)["scenarios"]["error_429"]["body"] == {"detail": "HTTP 429"}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_serve_checks_a_request_body_ref(tmp_path, fmt):
    doc = OpenApiDoc.load(_write(tmp_path, fmt, MATERIALS["schema only"][0],
                                 request_body={"$ref": "#/components/requestBodies/B"}))
    (op,) = doc.operations()
    assert contract._check_body(doc, op, {"error_code": 5}) == ["body.error_code: int, contract says string"]
    assert contract._check_body(doc, op, None) == ["body: required by the contract, missing"]
