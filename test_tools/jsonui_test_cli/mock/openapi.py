"""Dependency-free OpenAPI parsing for mock generation.

Two jobs:
  1. Enumerate operations (method + path + operationId + tag + responses).
  2. Synthesize a JSON sample body from a response schema, resolving $ref
     (including deep JSON Pointers) and merging allOf, with a depth cap to
     survive recursive schemas.

Semantics deliberately mirror document_tools' resolver (local $ref only, allOf
merge, oneOf/anyOf tolerated by taking the first branch). Unlike jui_tools'
strict loader this does NOT halt on oneOf/anyOf/YAML — mock generation is
best-effort scaffolding, not a contract gate. That behavior difference is
intentional (see plan §14.2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Guard against unbounded recursion through self-referential schemas.
_MAX_DEPTH = 8

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")


@dataclass
class Operation:
    method: str            # upper-case: GET, POST, ...
    path: str              # e.g. /v1/stocks/{id}
    operation_id: str      # from spec, or synthesized fallback
    tag: str               # first tag, or "default"
    id_was_synthesized: bool = False
    responses: dict = field(default_factory=dict)  # raw responses object


class OpenApiDoc:
    """Loaded OpenAPI document with $ref resolution and sample synthesis."""

    def __init__(self, spec: dict, source_path: str = ""):
        self.spec = spec
        self.source_path = source_path
        self._schemas = spec.get("components", {}).get("schemas", {}) or {}

    # ---- loading -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "OpenApiDoc":
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            spec = json.load(f)
        return cls(spec, source_path=str(p))

    def is_api_spec(self) -> bool:
        """True if this doc declares paths (an API spec, not a DB-model-only spec)."""
        return bool(self.spec.get("paths"))

    # ---- operation enumeration ----------------------------------------

    def operations(self) -> list[Operation]:
        ops: list[Operation] = []
        for path, item in (self.spec.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                    continue
                tags = op.get("tags") or []
                tag = tags[0] if tags else "default"
                op_id = op.get("operationId")
                synthesized = False
                if not op_id:
                    op_id = _fallback_operation_id(method, path)
                    synthesized = True
                ops.append(Operation(
                    method=method.upper(),
                    path=path,
                    operation_id=op_id,
                    tag=tag,
                    id_was_synthesized=synthesized,
                    responses=op.get("responses") or {},
                ))
        return ops

    # ---- $ref resolution ----------------------------------------------

    def _resolve_ref(self, ref: str):
        """Resolve a local JSON Pointer ref like '#/components/schemas/Foo'."""
        if not ref.startswith("#/"):
            # External / cross-file refs are out of scope for mock scaffolding.
            return {}
        node = self.spec
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and token in node:
                node = node[token]
            else:
                return {}
        return node

    def resolve_schema(self, schema, _depth: int = 0):
        """Return a schema with top-level $ref/allOf resolved (shallow, one hop of merge)."""
        if not isinstance(schema, dict) or _depth > _MAX_DEPTH:
            return schema if isinstance(schema, dict) else {}
        if "$ref" in schema:
            return self.resolve_schema(self._resolve_ref(schema["$ref"]), _depth + 1)
        if "allOf" in schema:
            merged: dict = {"type": "object", "properties": {}, "required": []}
            for sub in schema["allOf"]:
                rs = self.resolve_schema(sub, _depth + 1)
                if rs.get("type") == "object" or "properties" in rs:
                    merged["properties"].update(rs.get("properties", {}))
                    merged["required"].extend(rs.get("required", []))
                else:
                    # non-object branch (rare) — fall back to it
                    return rs
            # carry sibling keywords (e.g. example) alongside allOf
            for k, v in schema.items():
                if k != "allOf":
                    merged[k] = v
            return merged
        if "oneOf" in schema or "anyOf" in schema:
            branches = schema.get("oneOf") or schema.get("anyOf")
            if branches:
                return self.resolve_schema(branches[0], _depth + 1)
        return schema

    # ---- sample synthesis ---------------------------------------------

    def sample_for_schema(self, schema, _depth: int = 0):
        """Synthesize a representative JSON value for a (possibly $ref) schema."""
        if _depth > _MAX_DEPTH:
            return None
        schema = self.resolve_schema(schema, _depth)
        if not isinstance(schema, dict):
            return None

        # Prefer explicit examples when present.
        if "example" in schema:
            return schema["example"]
        if "examples" in schema and isinstance(schema["examples"], list) and schema["examples"]:
            return schema["examples"][0]
        if "default" in schema:
            return schema["default"]
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]

        stype = schema.get("type")
        if stype is None and "properties" in schema:
            stype = "object"

        if stype == "object" or "properties" in schema:
            out = {}
            for name, prop in (schema.get("properties") or {}).items():
                out[name] = self.sample_for_schema(prop, _depth + 1)
            return out
        if stype == "array":
            item = self.sample_for_schema(schema.get("items", {}), _depth + 1)
            return [item] if item is not None else []
        return _primitive_sample(schema, stype)

    def success_schema(self, op: Operation):
        """Pick the 2xx JSON response schema for an operation, if any.

        Returns (schema_or_None, content_type). content_type is None when the
        response has no body; non-JSON when the success response is e.g. a PDF.
        """
        for code in sorted(op.responses.keys()):
            if code.startswith("2") or code == "default":
                resp = op.responses[code] or {}
                content = resp.get("content") or {}
                if not content:
                    return None, None
                if "application/json" in content:
                    return content["application/json"].get("schema"), "application/json"
                # first non-JSON content type (PDF/CSV/ZIP/...)
                ctype = next(iter(content.keys()))
                return content[ctype].get("schema"), ctype
        return None, None

    def error_codes(self, op: Operation) -> list[str]:
        """Declared 4xx/5xx status codes for this operation."""
        return sorted(c for c in op.responses if c[:1] in ("4", "5") and c.isdigit())


def _primitive_sample(schema: dict, stype):
    fmt = schema.get("format")
    if stype == "string":
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt == "email":
            return "user@example.com"
        if fmt in ("uri", "url"):
            return "https://example.com"
        return "string"
    if stype == "integer":
        return 0
    if stype == "number":
        return 0
    if stype == "boolean":
        return True
    if stype == "null":
        return None
    return None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Filesystem-safe slug: lower-case, non-alnum runs -> single hyphen."""
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "default"


def _fallback_operation_id(method: str, path: str) -> str:
    """Synthesize an operationId for specs that omit it: <method>_<path slug>."""
    parts = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            parts.append("by-" + seg[1:-1])
        elif seg:
            parts.append(seg)
    return method.lower() + "_" + slugify("-".join(parts))
