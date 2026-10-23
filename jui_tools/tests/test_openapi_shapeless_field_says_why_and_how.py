"""A field whose shape is not declared is refused, and the refusal says why and how to write it (2.3.22; ticket
2026-10-23-jui-openapi-free-form-json-field, withdrawn as a feature with the requester and liquor-order: an API returns
a typed shape, not free-form JSON).

Until 2.3.21 object-without-type promised "wait for v2 (which may treat this as `Map<String, Any>`)" and unknown-type
said only "unrecognized type None". Now both say, on one line in English then Japanese, that such a field cannot be
read and written safely on every platform, and how to declare it instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jui_cli.core import openapi_loader as L
from jui_cli.core.openapi_loader import OpenAPILoadError, load_swagger

SHAPES = {   # name -> (the schemas, the code)
    "a top-level object with no fields": ({"Free": {"type": "object"}}, "object-without-type"),
    "an inline additionalProperties: true": ({"Item": {"type": "object", "properties": {
        "detail": {"type": "object", "additionalProperties": True, "nullable": True}}}}, "object-without-type"),
    "an additionalProperties: {}": ({"Item": {"type": "object", "properties": {
        "detail": {"type": "object", "additionalProperties": {}, "nullable": True}}}}, "unknown-type"),
    "a field with no type": ({"Item": {"type": "object", "properties": {"detail": {"nullable": True}}}}, "unknown-type"),
}


@pytest.mark.parametrize("name", list(SHAPES))
def test_the_refusal_says_why_and_how_in_english_and_japanese(tmp_path, name):
    schemas, code = SHAPES[name]
    (tmp_path / "api.json").write_text(json.dumps({"openapi": "3.0.3", "info": {"title": "T", "version": "1"}, "paths": {},
                                                   "components": {"schemas": schemas}}), encoding="utf-8")
    with pytest.raises(OpenAPILoadError) as got:
        load_swagger(tmp_path)
    line = str(got.value)
    assert got.value.code == code, line
    assert "\n" not in line, "one line"
    for part in (L.SHAPELESS_WHY_EN, L.SHAPELESS_HOW_EN, L.SHAPELESS_WHY_JA, L.SHAPELESS_HOW_JA):
        assert part in line, (part, line)
    assert line.index(L.SHAPELESS_WHY_EN) < line.index(" / ") < line.index(L.SHAPELESS_WHY_JA), "English, then Japanese"
    assert "{key, value}" in line and "oneOf" in line and "key・value" in line
    assert "v2" not in line and "Map<String, Any>" not in line, line


def test_an_unknown_type_word_is_still_named_and_said_in_both(tmp_path):
    """A type the loader does not know (a word, not a missing one) keeps naming it, in both languages."""
    (tmp_path / "api.json").write_text(json.dumps({"openapi": "3.0.3", "info": {"title": "T", "version": "1"}, "paths": {},
                                                   "components": {"schemas": {"Item": {"type": "object", "properties": {
                                                       "f": {"type": "file"}}}}}}), encoding="utf-8")
    with pytest.raises(OpenAPILoadError) as got:
        load_swagger(tmp_path)
    line = str(got.value)
    assert got.value.code == "unknown-type" and "unrecognized type 'file'" in line and "の型 'file' は読めない" in line, line
