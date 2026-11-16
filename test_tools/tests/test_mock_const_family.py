"""A field's declared value reaches the mock (ticket 2026-10-24-jsonui-test-mock-generate-ignores-const).

`mock generate` wrote `"kind": "string"` for `{"type": "string", "const": "item"}`: the generator read no `const`,
and `--check` compared none, so the iOS DTO (a one-case enum) could not decode the generated default. The family,
in JSON and in YAML OpenAPI alike: a `const` (with an example, a default, `nullable` or a 3.1 type list beside it, a
boolean and an integer one, inside oneOf / anyOf / allOf, through a `$ref`) is the value of the generated body, of
the empty result and of a self-referring stop; a one-value enum is its value; a default or an example is a value the
schema takes. `--check` names a value that is not the `const`, and takes a value one oneOf / anyOf branch takes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import GENERATED_DIR, compare_to_schema, generate
from jsonui_test_cli.mock.openapi import OpenApiDoc, _stop_value

# name -> (schema, the value it must be, or None when any value the schema takes will do; a value --check must name)
CASES = {
    "const": ({"type": "string", "const": "item"}, "item", "string"),
    "const 3.1 type list": ({"type": ["string", "null"], "const": "item"}, "item", "string"),
    "const nullable": ({"type": "string", "nullable": True, "const": "item"}, "item", "string"),
    "const beside an example": ({"type": "string", "const": "item", "example": "bundle"}, "item", "bundle"),
    "const beside a default": ({"type": "string", "const": "item", "default": "bundle"}, "item", "bundle"),
    "const boolean": ({"type": "boolean", "const": False}, False, True),
    "const integer": ({"type": "integer", "const": 3}, 3, 0),
    "one-value enum": ({"type": "string", "enum": ["item"]}, "item", "string"),
    "default": ({"type": "string", "default": "bundle"}, None, None),
    "example": ({"type": "string", "example": "bundle"}, None, None),
    "oneOf const": ({"oneOf": [{"type": "string", "const": "a"}, {"type": "string", "const": "b"}]}, "a", "string"),
    "anyOf const or null": ({"anyOf": [{"type": "string", "const": "a"}, {"type": "null"}]}, "a", "string"),
    "allOf const": ({"allOf": [{"type": "string"}, {"const": "item"}]}, "item", "string"),
    "const through a $ref": ({"$ref": "#/components/schemas/Kind"}, "item", "string"),
    "an example beside a $ref to a const": ({"$ref": "#/components/schemas/Kind", "example": "bundle"}, "item", "bundle"),
}


def _doc(tmp_path: Path, fmt: str) -> OpenApiDoc:
    spec = {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {},
            "components": {"schemas": {"Kind": {"type": "string", "const": "item"},
                                       **{f"C{i}": {"type": "object", "properties": {"v": s}}
                                          for i, (s, _, _) in enumerate(CASES.values())}}}}
    path = tmp_path / f"api.{fmt}"
    path.write_text(json.dumps(spec) if fmt == "json" else yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return OpenApiDoc.load(path)


def _prop(doc: OpenApiDoc, name: str):
    return doc.spec["components"]["schemas"][f"C{list(CASES).index(name)}"]["properties"]["v"]


def _exactly(got, want) -> bool:
    return got == want and type(got) is type(want)


@pytest.mark.parametrize("fmt", ["json", "yaml"])
@pytest.mark.parametrize("name", list(CASES))
def test_the_generated_values_are_the_declared_ones(tmp_path, fmt, name):
    doc = _doc(tmp_path, fmt)
    prop = _prop(doc, name)
    want = CASES[name][1]
    got = {"sample": doc.sample_for_schema(prop), "empty": doc.empty_for_schema(prop),
           "stop": _stop_value(doc.resolve_schema(prop))}
    for where, value in got.items():
        if want is None:   # no declared value: any value the schema takes
            assert compare_to_schema(doc, prop, value).violations == [], (where, value)
        else:
            assert _exactly(value, want), (where, value)
            assert compare_to_schema(doc, prop, value).violations == [], (where, value)


@pytest.mark.parametrize("fmt", ["json", "yaml"])
@pytest.mark.parametrize("name", [n for n, (_, _, wrong) in CASES.items() if wrong is not None])
def test_check_names_a_value_that_is_not_the_declared_one(tmp_path, fmt, name):
    doc = _doc(tmp_path, fmt)
    assert compare_to_schema(doc, _prop(doc, name), CASES[name][2]).violations


def test_a_value_any_union_branch_takes_is_the_contract_s():
    doc = OpenApiDoc({"openapi": "3.0.3", "paths": {}})
    consts = {"oneOf": [{"type": "string", "const": "a"}, {"type": "string", "const": "b"}]}
    types = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
    assert compare_to_schema(doc, consts, "b").violations == []
    assert compare_to_schema(doc, consts, "c").violations
    assert compare_to_schema(doc, types, 3).violations == []
    assert compare_to_schema(doc, types, True).violations   # a boolean is neither
    assert compare_to_schema(doc, {"const": 1}, True).violations      # true is not 1 (no type to stop it first)
    assert compare_to_schema(doc, {"const": False}, 0).violations     # nor 0 false
    assert compare_to_schema(doc, {"const": 1}, 1).violations == []


SPEC = {
    "openapi": "3.0.3",
    "paths": {"/api/imports/withdrawn": {"post": {
        "operationId": "registerImportWithdrawn", "tags": ["Imports"],
        "responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Registered"}}}}}}}},
    "components": {"schemas": {"Registered": {
        "type": "object", "required": ["kind", "item_id"],
        "properties": {"kind": {"type": "string", "const": "item"}, "item_id": {"type": "integer"}}}}},
}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_generate_writes_the_const_and_check_names_a_mock_that_is_not_it(tmp_path, fmt):
    spec = tmp_path / f"spec.{fmt}"
    spec.write_text(json.dumps(SPEC) if fmt == "json" else yaml.safe_dump(SPEC), encoding="utf-8")
    out = tmp_path / "mocks"
    generate([str(spec)], out)
    made = next((out / GENERATED_DIR).rglob("registerImportWithdrawn.mock.json"))
    data = json.loads(made.read_text(encoding="utf-8"))
    assert data["scenarios"]["default"]["body"]["kind"] == "item"
    assert not generate([str(spec)], out, check=True).has_drift
    # the shape the ticket found, adopted as a hand-written mock: --check names it
    hand = out / made.relative_to(out / GENERATED_DIR)
    hand.parent.mkdir(parents=True, exist_ok=True)
    data["scenarios"]["default"]["body"]["kind"] = "string"
    hand.write_text(json.dumps(data), encoding="utf-8")
    made.unlink()
    report = generate([str(spec)], out, check=True)
    assert report.has_drift
    assert any("'string' is not the contract's const 'item'" in v for b in report.bodies for v in b.violations), report.bodies


# The keys beside an allOf (ticket's family, the integrator's mutants): `{"allOf": [{"$ref": E}], "nullable": true}`
# is E's value in a body and null in an empty result; a key beside the allOf beats the same key in a branch.
NEIGHBOURS = {
    "openapi": "3.0.3", "paths": {},
    "components": {"schemas": {
        "Status": {"type": "string", "enum": ["charged", "skipped"], "default": "charged"},
        "Pick": {"oneOf": [{"type": "string", "const": "a"}, {"type": "string", "const": "b"}]},
        "Row": {"type": "object", "properties": {
            "status": {"allOf": [{"$ref": "#/components/schemas/Status"}], "nullable": True},
            "chosen": {"allOf": [{"$ref": "#/components/schemas/Status"}], "default": "skipped"},
            "pick": {"$ref": "#/components/schemas/Pick"}}}}},
}


def test_a_nullable_beside_an_allof_is_read_with_it():
    doc = OpenApiDoc(NEIGHBOURS)
    row = {"$ref": "#/components/schemas/Row"}
    assert doc.sample_for_schema(row)["status"] == "charged"   # a body: the enum's value
    assert doc.empty_for_schema(row)["status"] is None          # an empty result: null, as nullable says


def test_a_key_beside_an_allof_beats_the_branch_s():
    doc = OpenApiDoc(NEIGHBOURS)
    assert doc.sample_for_schema({"$ref": "#/components/schemas/Row"})["chosen"] == "skipped"


@pytest.mark.parametrize("types", [["string", "null"], ["null", "string"]])
def test_a_stop_skips_null_in_a_type_list_in_either_order(types):
    assert _stop_value({"type": types}) == "string"


def test_a_second_branch_of_a_union_behind_a_ref_is_the_contract_s():
    doc = OpenApiDoc(NEIGHBOURS)
    pick = {"$ref": "#/components/schemas/Pick"}
    assert compare_to_schema(doc, pick, "b").violations == []
    assert compare_to_schema(doc, pick, "c").violations
