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
