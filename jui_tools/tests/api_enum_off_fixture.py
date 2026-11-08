"""The swagger and the faces the api.enum_unknown_case-off arm writes (tests/test_api_model_enum_unknown_case.py), and
how its golden was made: by the 2.5.14 generators (v2.5.14 164a47f9), each face's files written here. Run as
``python tests/api_enum_off_fixture.py <jui_tools of that version> <out>`` to write them again."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

_REF = {"$ref": "#/components/schemas/DeviceKind"}
SPEC = {"openapi": "3.0.3", "info": {"title": "T", "version": "1.0.0"}, "components": {"schemas": {
    "DeviceKind": {"type": "string", "enum": ["phone", "tablet", "desktop"], "description": "What the session runs on."},
    "LoginMethod": {"type": "string", "enum": ["email_link", "apple-id", "Google"]},
    "Level": {"type": "integer", "enum": [-1, 0, 2]},
    "Severity": {"type": "integer", "enum": [1, 5], "x-enum-varnames": ["low", "high"]},
    "Legacy": {"type": "string", "enum": ["old", "older"], "deprecated": True},
    "Inner": {"type": "object", "required": ["kind"], "properties": {"kind": _REF}},
    "Item": {"type": "object", "required": ["id", "kind", "inline", "level", "kinds"], "properties": {
        "id": {"type": "string"},
        "kind": _REF,
        "optKind": _REF,
        "nullKind": {"allOf": [_REF], "nullable": True},
        "defaulted": {"$ref": "#/components/schemas/LoginMethod", "default": "apple-id"},
        "inline": {"type": "string", "enum": ["email", "apple", "google"]},
        "level": {"$ref": "#/components/schemas/Level"},
        "severity": {"$ref": "#/components/schemas/Severity"},
        "kinds": {"type": "array", "items": _REF},
        "byName": {"type": "object", "additionalProperties": _REF},
        "inner": {"$ref": "#/components/schemas/Inner"},
    }},
}}}

FACES = ("ios", "android-kotlinx", "android-moshi", "android-none", "web")


def sources(face: str, off: bool = True) -> dict[str, str]:
    """{file name: source} of every enum and DTO the face writes for SPEC (off: api.enum_unknown_case false, when the
    generator knows the flag)."""
    from jui_cli.core.openapi_loader import parse_swagger
    from jui_cli.generators.android_api_model_generator import AndroidApiModelGenerator, AndroidApiPlatformConfig
    from jui_cli.generators.ios_api_model_generator import IosApiModelGenerator, IosApiPlatformConfig
    from jui_cli.generators.web_api_model_generator import WebApiModelGenerator, WebApiPlatformConfig

    def knows(cls) -> dict:
        return {"enum_unknown_case": not off} if "enum_unknown_case" in inspect.signature(cls).parameters else {}

    doc = parse_swagger(SPEC, "spec.json")
    root = Path("/generated")
    if face == "ios":
        gen, ext = IosApiModelGenerator(IosApiPlatformConfig(sources_root=root, **knows(IosApiPlatformConfig))), "swift"
    elif face.startswith("android-"):
        gen, ext = AndroidApiModelGenerator(AndroidApiPlatformConfig(
            sources_root=root, domain_package="com.example.model", dto_package="com.example.model.generated",
            serializer=face.split("-", 1)[1], **knows(AndroidApiPlatformConfig))), "kt"
    else:
        gen, ext = WebApiModelGenerator(WebApiPlatformConfig(sources_root=root, model_dir="models", dto_subdir="generated")), "ts"
    out = {f"{e.name}.{ext}": gen.generate_enum_source(e, doc) for e in doc.enums}
    out |= {f"{s.name}Dto.{ext}": gen.generate_dto_source(s, doc) for s in doc.schemas}
    return out


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    dest = Path(sys.argv[2])
    for face in FACES:
        for name, src in sources(face).items():
            (dest / face).mkdir(parents=True, exist_ok=True)
            (dest / face / name).write_text(src, encoding="utf-8")
    print(sum(1 for _ in dest.rglob("*.*")), "files")
