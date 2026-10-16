"""The web API model's `| null` is handed to a compiler (ticket
jui-web-api-model-types-nullable-fields-as-optional-only).

The generator's own arms compare strings (jui_tools). Here the DTO files are
type-checked with a consumer's code beside them, under `--strict`: a field
the server sends as `null` must be assignable `null`, a required one must not
be omittable, and the parse / serialize helpers must type-check with the
null-preserving guards. Lives in test_tools because CI installs the compiler
(`npm ci --prefix rjui_tools/spec/support`) after the jui_tools step.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.test_emitted_typescript_compiles import _TSC_ARGS, _tsc

from jui_cli.core.openapi_loader import parse_swagger
from jui_cli.generators.web_api_model_generator import (
    WebApiModelGenerator,
    WebApiPlatformConfig,
)

SCHEMAS = {
    "Place": {
        "type": "object",
        "required": ["name", "lat", "seen_at"],
        "properties": {
            "name": {"type": "string"},
            "lat": {"type": "number", "nullable": True},
            "note": {"type": "string"},
            "lng": {"type": "number", "nullable": True},
            "seen_at": {"type": "string", "format": "date-time", "nullable": True},
            "due_at": {"type": "string", "format": "date-time"},
            "left_at": {"type": "string", "format": "date-time", "nullable": True},
        },
    },
}

CONSUMER = """
import { PlaceDto, parsePlaceDto, serializePlaceDto } from "./PlaceDto";

// null is a value the type admits where the server may send it
const fromServer: PlaceDto = { name: "a", lat: null, seenAt: null, lng: null, leftAt: null };
const lat: number | null = fromServer.lat;
const seen: Date | null = parsePlaceDto(serializePlaceDto(fromServer)).seenAt;

// @ts-expect-error — `lat` may be null, but it is required: it cannot be omitted
const omitted: PlaceDto = { name: "a", seenAt: null };

// @ts-expect-error — `note` may be omitted, but it is not nullable
const nullNote: PlaceDto = { name: "a", lat: 1, seenAt: null, note: null };

export { lat, seen, omitted, nullNote };
"""


def _emit(into: Path, case: str, formats: bool) -> None:
    doc = parse_swagger({"openapi": "3.0.3", "info": {"title": "T", "version": "1"},
                         "components": {"schemas": SCHEMAS}}, "test.json")
    gen = WebApiModelGenerator(WebApiPlatformConfig(
        sources_root=into, model_dir="models", dto_subdir="generated",
        case_convention=case, format_mapping=formats))
    (into / "PlaceDto.ts").write_text(gen.generate_dto_source(doc.schemas[0], doc),
                                      encoding="utf-8")


def _check(into: Path, consumer: str) -> subprocess.CompletedProcess:
    (into / "consumer.ts").write_text(consumer, encoding="utf-8")
    return subprocess.run([str(_tsc()), *_TSC_ARGS, "PlaceDto.ts", "consumer.ts"],
                          cwd=into, capture_output=True, text=True)


@pytest.mark.parametrize("case, formats", [("camelCase", True), ("camelCase", False)])
def test_null_and_omitted_are_two_things_to_the_compiler(tmp_path, case, formats):
    _emit(tmp_path, case, formats)
    consumer = CONSUMER
    if not formats:     # dates stay strings without format mapping
        consumer = consumer.replace("const seen: Date | null", "const seen: string | null")
    if not formats:     # no parse / serialize helpers without a skew to bridge
        consumer = re.sub(r"parsePlaceDto\(serializePlaceDto\(fromServer\)\)", "fromServer",
                          consumer).replace(", parsePlaceDto, serializePlaceDto", "")
    done = _check(tmp_path, consumer)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_check_can_fail(tmp_path):
    """The control: a consumer line the types reject makes tsc exit non-zero."""
    _emit(tmp_path, "camelCase", True)
    done = _check(tmp_path, CONSUMER + "\nconst wrong: number = ({} as PlaceDto).lat;\n")
    assert done.returncode != 0 and "TS2322" in done.stdout + done.stderr


#: ticket jui-web-api-model-nullable-array-items-dropped: `nullable: true` on
#: `items` / `additionalProperties` — the element has no field of its own.
ELEMENT_SCHEMAS = {
    "Pet": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string"},
        "born_at": {"type": "string", "format": "date-time"}}},
    "Grid": {"type": "object", "required": ["cells", "scores", "when", "pets"], "properties": {
        "cells": {"type": "array", "items": {"type": "array", "items": {
            "type": "integer", "format": "int64", "nullable": True}}},
        "scores": {"type": "object", "additionalProperties": {"type": "number", "nullable": True}},
        "when": {"type": "array", "items": {"type": "string", "format": "date-time",
                                            "nullable": True}},
        "pets": {"type": "array", "items": {
            "allOf": [{"$ref": "#/components/schemas/Pet"}], "nullable": True}},
        "plain": {"type": "array", "items": {"type": "integer"}},
    }},
}

ELEMENT_CONSUMER = """
import { GridDto, parseGridDto, serializeGridDto } from "./GridDto";

// a null element is a value the type admits
const fromServer: GridDto = { cells: [[1, null], [null]], scores: { x: 1, y: null },
  when: [new Date(0), null], pets: [{ name: "p" }, null] };
const cell: number | null = fromServer.cells[0][1];
const score: number | null = fromServer.scores.y;
const at: Date | null = parseGridDto(serializeGridDto(fromServer)).when[1];

// @ts-expect-error — a null element is not a number: it has to be narrowed first
const unchecked: number = fromServer.cells[0][0];

// @ts-expect-error — `plain` declares no null element (the control)
const plain: GridDto = { ...fromServer, plain: [1, null] };

export { cell, score, at, unchecked, plain };
"""


def test_a_null_element_is_typed_null(tmp_path):
    doc = parse_swagger({"openapi": "3.0.3", "info": {"title": "T", "version": "1"},
                         "components": {"schemas": ELEMENT_SCHEMAS}}, "test.json")
    gen = WebApiModelGenerator(WebApiPlatformConfig(
        sources_root=tmp_path, model_dir="models", dto_subdir="generated",
        case_convention="camelCase", format_mapping=True))
    for schema in doc.schemas:
        (tmp_path / f"{schema.name}Dto.ts").write_text(gen.generate_dto_source(schema, doc),
                                                       encoding="utf-8")
    (tmp_path / "consumer.ts").write_text(ELEMENT_CONSUMER, encoding="utf-8")
    done = subprocess.run([str(_tsc()), *_TSC_ARGS, "PetDto.ts", "GridDto.ts", "consumer.ts"],
                          cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
