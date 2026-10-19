"""The talk view's WebSocket contract: talk_contract.json (the source of truth; TALK_CONTRACT.md explains it).

``validate(frame)`` checks one frame (server -> page, ``talk.list`` / ``talk.messages`` / ``talk.update`` /
``talk.badges``) or one
request (page -> server, ``talk.open`` / ``talk.close`` / ``talk.get`` / ``talk.seen``) against it and returns every
problem, one line each (empty: it conforms). Only the part of JSON Schema the contract uses is understood: type,
enum, const, required, properties, additionalProperties (false or a schema), propertyNames, maxProperties,
min/maxLength, minimum/maximum, pattern, items, min/maxItems, a local $ref, anyOf, oneOf. The server's own frames are checked with it in tests; the page's side
can be checked the same way from a test that feeds a sample through it.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads((resources.files("jui_cli.viz") / "talk_contract.json").read_text(encoding="utf-8"))


def limits() -> dict:
    return dict(load()["limits"])


def _is(value: Any, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[kind])


def _check(value: Any, schema: dict, where: str, root: dict) -> list[str]:
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return _check(value, node, where, root)
    out: list[str] = []
    if "anyOf" in schema:
        if all(_check(value, s, where, root) for s in schema["anyOf"]):
            out.append(f"{where}: matches none of anyOf")
        return out
    if "oneOf" in schema:
        good = [s for s in schema["oneOf"] if not _check(value, s, where, root)]
        if len(good) != 1:
            why = "; ".join(p for s in schema["oneOf"] for p in _check(value, s, where, root)[:2])
            out.append(f"{where}: matches {len(good)} of oneOf ({why})")
        return out
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_is(value, k) for k in kinds):
            return [f"{where}: {type(value).__name__} is not {'/'.join(kinds)}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{where}: {value!r} is not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            out.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{where}: longer than {schema['maxLength']} ({len(value)})")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{where}: {value[:60]!r} does not match {schema['pattern']}")
    if _is(value, "number"):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{where}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{where}: {value} > {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{where}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{where}: more than {schema['maxItems']} items ({len(value)})")
        if "items" in schema:
            for i, item in enumerate(value):
                out += _check(item, schema["items"], f"{where}[{i}]", root)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{where}: missing {key!r}")
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            out.append(f"{where}: more than {schema['maxProperties']} keys ({len(value)})")
        for key, item in value.items():
            if "propertyNames" in schema:
                out += [f"{p} (a key)" for p in _check(key, schema["propertyNames"], f"{where}[{key!r}]", root)]
            if key in props:
                out += _check(item, props[key], f"{where}.{key}", root)
            elif extra is False:
                out.append(f"{where}: unexpected key {key!r}")
            elif isinstance(extra, dict):
                out += _check(item, extra, f"{where}[{key!r}]", root)
    return out


def validate(frame: Any) -> list[str]:
    """Every way ``frame`` (a server frame or a page request, by its ``type``) breaks the contract."""
    root = load()
    kind = frame.get("type") if isinstance(frame, dict) else None
    schema = root["frames"].get(kind) or root["requests"].get(kind)
    if schema is None:
        return [f"type {kind!r} is not a talk frame or request"]
    return _check(frame, schema, kind, root)


def validate_def(value: Any, name: str) -> list[str]:
    """Check one value against a named definition (``conversation``, ``message``, ``op``, …)."""
    root = load()
    return _check(value, root["$defs"][name], name, root)
