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
#
# Depth alone was the guard, and depth is a proxy for "this schema refers to
# itself": it stops the infinite case, but it also stops finite ones. A
# consumer's swagger nested eight levels legitimately, and the synthesised
# body came back with `null` in a required, non-nullable integer — the
# generator writing a body that violates the contract it had just read, and
# then the check calling its own output stale with a remedy (regenerate)
# that could not change anything. Self-reference is now detected directly,
# by the `$ref`s on the current path, so a deep-but-finite schema is
# synthesised in full; the depth number stays only as a backstop against a
# pathological document, far above any hand-written nesting.
_MAX_DEPTH = 64

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "head", "options")


@dataclass
class Operation:
    method: str            # upper-case: GET, POST, ...
    path: str              # e.g. /v1/stocks/{id}
    operation_id: str      # from spec, or synthesized fallback
    tag: str               # first tag, or "default"
    id_was_synthesized: bool = False
    responses: dict = field(default_factory=dict)  # raw responses object
    # Request side, for `mock serve` contract checking. Path-level
    # parameters are merged in — OpenAPI lets them be declared once for
    # every method on a path, and a checker that only read the operation
    # level would miss the required ones.
    parameters: list = field(default_factory=list)
    request_body: dict = field(default_factory=dict)


class OpenApiLoadError(ValueError):
    """An OpenAPI document that could not be read: str() is one line naming the file and why."""


def read_document(path: Path) -> object:
    """One document's data, JSON or YAML, by the rule every tool shares (shared/core/openapi_file.py; ticket
    2026-10-23-jsonui-test-mock-generate-yaml-traceback: a YAML document ended `mock generate` in a JSONDecodeError
    traceback). A tree synced without shared/ reads JSON only and says so for anything else."""
    from .. import shared_core

    of = shared_core.load("openapi_file")
    if of is None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OpenApiLoadError(f"{path}: not readable as JSON (this install has no shared/core to read YAML): {exc}") from None
    try:
        return of.read(path)
    except of.OpenApiFileError as exc:
        raise OpenApiLoadError(str(exc)) from None


def api_documents(folder: Path) -> list[Path]:
    """The documents a folder holds: .json, .yaml and .yml (shared/core/openapi_file.py), .json only without it."""
    from .. import shared_core

    of = shared_core.load("openapi_file")
    return of.documents(folder) if of is not None else sorted(Path(folder).rglob("*.json"))


class OpenApiDoc:
    """Loaded OpenAPI document with $ref resolution and sample synthesis."""

    def __init__(self, spec: dict, source_path: str = ""):
        self.spec = spec
        self.source_path = source_path
        self._schemas = spec.get("components", {}).get("schemas", {}) or {}

    # ---- loading -------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "OpenApiDoc":
        """JSON or YAML (read_document); OpenApiLoadError with one line when it cannot be read."""
        p = Path(path)
        spec = read_document(p)
        if not isinstance(spec, dict):
            raise OpenApiLoadError(f"{p}: not an OpenAPI document (its top level is not a mapping)")
        return cls(spec, source_path=str(p))

    def is_api_spec(self) -> bool:
        """True if this doc declares paths (an API spec, not a DB-model-only spec)."""
        return bool(self.spec.get("paths"))

    # ---- operation enumeration ----------------------------------------

    def operations(self) -> list[Operation]:
        ops: list[Operation] = []
        for path, item in (self.spec.get("paths") or {}).items():
            # a path item may be a $ref (3.1 `components.pathItems`)
            item = self.resolve_object(item)
            if not item:
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
                # The path item's parameters, which every operation under it inherits, with the operation's: one of
                # the same `name` and `in` written on the operation takes the inherited one's place, as OpenAPI says
                # (shared/core/openapi_canonical.path_item_operations reads them the same way). Until jsonui-cli
                # 2.3.36 both lists end to end, a parameter written on both checked twice — the inherited
                # declaration too (ticket jui-openapi-canonical-ignores-path-item-parameters).
                merged: dict = {}
                for raw in list(item.get("parameters") or []) + list(op.get("parameters") or []):
                    p = self.resolve_object(raw)
                    if p.get("name"):
                        merged[(str(p.get("in") or "query"), p["name"])] = p
                parameters = list(merged.values())
                ops.append(Operation(
                    method=method.upper(),
                    path=path,
                    operation_id=op_id,
                    tag=tag,
                    id_was_synthesized=synthesized,
                    # Followed here, once, so every reader of a response or a request body sees its content:
                    # `#/components/responses/*` is how OpenAPI 3 shares an error response, and read raw it had
                    # no `content` — the error scenario became `{"detail": "HTTP 429"}`, `--check` filed the
                    # status as declaring no body, and serve checked no request body (ticket
                    # 2026-10-24-jui-mock-generate-ignores-response-ref).
                    responses={code: self.resolve_object(resp) for code, resp in (op.get("responses") or {}).items()},
                    parameters=parameters,
                    request_body=self.resolve_object(op.get("requestBody")),
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

    def resolve_object(self, obj):
        """A response, request body or example object with its `$ref` chain followed (`$ref` -> `$ref` -> object).

        `{}` for a chain that loops or points nowhere: no content, as a response that declares none."""
        seen: set = set()
        while isinstance(obj, dict) and isinstance(obj.get("$ref"), str):
            if obj["$ref"] in seen:
                return {}
            seen.add(obj["$ref"])
            obj = self._resolve_ref(obj["$ref"])
        return obj if isinstance(obj, dict) else {}

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
                    # Not an object: the branches are one value's constraints (`{"type": "string"}` beside
                    # `{"const": "item"}`), read together, not the first alone (ticket
                    # 2026-10-24-jsonui-test-mock-generate-ignores-const).
                    out: dict = {}
                    for branch in schema["allOf"]:
                        out.update(self.resolve_schema(branch, _depth + 1))
                    out.update({k: v for k, v in schema.items() if k != "allOf"})
                    return out
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

    def sample_for_schema(self, schema, _depth: int = 0, _seen: tuple = ()):
        """Synthesize a representative JSON value for a (possibly $ref) schema.

        `_seen` carries the `$ref` pointers already open on this path. A
        repeat means the schema refers to itself, which is the only case
        that cannot be synthesised in full — and there the value stops at
        the type's zero value, never at `null`: `null` in a required,
        non-nullable field makes the generated body violate the very
        contract it was built from, and `--check` then reports the
        generator's own output as drift.
        """
        ref = schema.get("$ref") if isinstance(schema, dict) else None
        if _depth > _MAX_DEPTH or (ref is not None and ref in _seen):
            return _stop_value(self.resolve_schema(schema, _depth))
        if ref is not None:
            # An example written beside the `$ref` is the one this use of the
            # shared schema was given (OpenAPI 3.1 allows it there); resolving
            # first would drop it for the referenced schema's own, or none.
            found, value = _schema_example(schema)
            if found and "const" not in self.resolve_schema(schema, _depth):
                return value
            _seen = _seen + (ref,)
        schema = self.resolve_schema(schema, _depth)
        if not isinstance(schema, dict):
            return None

        # A `const` is the only value the field may hold: before an example or a default that says otherwise.
        if "const" in schema:
            return schema["const"]
        # Prefer explicit examples when present.
        found, value = _schema_example(schema)
        if found:
            return value
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
                out[name] = self.sample_for_schema(prop, _depth + 1, _seen)
            return out
        if stype == "array":
            item = self.sample_for_schema(schema.get("items", {}), _depth + 1, _seen)
            return [item] if item is not None else []
        return _primitive_sample(schema, stype)

    def empty_for_schema(self, schema, _depth: int = 0, _seen: tuple = ()):
        """The body of an empty result for a schema: every array [], every number 0 (its minimum when that is above 0),
        every boolean false, a nullable field null (an array stays []), an enum its first value, a string its type's sample; objects
        followed the same way. No example is read: a body built from one keeps its counts, totals and flags beside the
        array emptied (`results: []` beside `revoked: 1`), and which number goes with which array cannot be told from
        the example (ticket 2026-10-23-jui-test-mock-empty-scenario-keeps-counts-from-example)."""
        ref = schema.get("$ref") if isinstance(schema, dict) else None
        if _depth > _MAX_DEPTH or (ref is not None and ref in _seen):
            return _stop_value(self.resolve_schema(schema, _depth))
        if ref is not None:
            _seen = _seen + (ref,)
        schema = self.resolve_schema(schema, _depth)
        if not isinstance(schema, dict):
            return None
        if "const" in schema:
            return schema["const"]   # a tag, not data: an empty result still carries it
        stype = schema.get("type")
        if stype == "array" or (isinstance(stype, list) and "array" in stype):
            return []   # an array is [], nullable or not: that is what an empty result of one is
        if isinstance(stype, list):   # OpenAPI 3.1: ["integer", "null"]
            if "null" in stype:
                return None
            stype = next((t for t in stype if t != "null"), None)
        if schema.get("nullable") is True:
            return None
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]
        if stype is None and "properties" in schema:
            stype = "object"
        if stype == "object" or "properties" in schema:
            return {name: self.empty_for_schema(prop, _depth + 1, _seen) for name, prop in (schema.get("properties") or {}).items()}
        if stype == "array":
            return []
        if stype in ("integer", "number"):
            low = schema.get("minimum")
            if isinstance(schema.get("exclusiveMinimum"), (int, float)) and not isinstance(schema.get("exclusiveMinimum"), bool):
                low = schema["exclusiveMinimum"] + (1 if stype == "integer" else 0.001)   # 3.1: the bound itself is out
            elif schema.get("exclusiveMinimum") is True and isinstance(low, (int, float)):
                low = low + (1 if stype == "integer" else 0.001)                          # 3.0: minimum is out
            return low if isinstance(low, (int, float)) and low > 0 else 0
        if stype == "boolean":
            return False
        return _primitive_sample(schema, stype)

    def has_top_level_array(self, schema) -> bool:
        """True when a body of this schema is an array, or an object with an array among its own properties: the
        responses an empty result is drawn for."""
        schema = self.resolve_schema(schema)
        if not isinstance(schema, dict):
            return False
        stype = schema.get("type")
        if stype == "array" or (isinstance(stype, list) and "array" in stype):
            return True
        return any(self._is_array(p) for p in (schema.get("properties") or {}).values())

    def _is_array(self, schema) -> bool:
        s = self.resolve_schema(schema)
        t = s.get("type") if isinstance(s, dict) else None
        return t == "array" or (isinstance(t, list) and "array" in t)

    def media_example(self, media) -> tuple[bool, object]:
        """`(found, value)` for the example a media type object carries.

        `example` first, then the first of `examples` that holds a `value`
        (a `$ref` chain into `components/examples` is followed; an entry with only
        an `externalValue` is skipped — nothing is fetched). This is where
        OpenAPI 3 puts a response's example as often as on the schema, and
        a body synthesised from the types instead reads `0`, `"string"` and
        the first enum value: below a declared `minimum`, and a "nothing
        wrong" response showing every warning flag set.
        """
        if not isinstance(media, dict):
            return False, None
        if "example" in media:
            return True, media["example"]
        examples = media.get("examples")
        if isinstance(examples, dict):
            for entry in examples.values():
                entry = self.resolve_object(entry)
                if "value" in entry:
                    return True, entry["value"]
        return False, None

    def response_headers(self, response) -> dict:
        """`{name: header object}` a response declares, each header's `$ref` chain followed (`components/headers`).
        `Content-Type` is left out: OpenAPI says a response's Content-Type header is ignored (the media type says it,
        and a scenario's `contentType` serves it)."""
        headers = (response or {}).get("headers") if isinstance(response, dict) else None
        if not isinstance(headers, dict):
            return {}
        return {name: self.resolve_object(h) for name, h in headers.items()
                if isinstance(name, str) and name.lower() != "content-type"}

    def header_value(self, header: dict, required: bool = False) -> tuple[bool, str]:
        """`(found, text)` for the value a scenario serves a declared header with: its `example` or first of
        `examples` (media_example's rule), else its schema's own value (`const`, an example, `default`, an enum's
        first). A required header with none of them gets one built from its schema, so a generated scenario carries
        every header the contract requires; an optional one with none is not written ("string" in a header is noise)."""
        found, value = self.media_example(header)
        if not found:
            schema = self.resolve_schema(header.get("schema") or {})
            if not (required or "const" in schema or _schema_example(schema)[0] or "default" in schema
                    or (isinstance(schema.get("enum"), list) and schema["enum"])):
                return False, ""
            value = self.sample_for_schema(header.get("schema") or {})
        if isinstance(value, bool):
            return True, "true" if value else "false"
        if isinstance(value, (dict, list)):
            return True, json.dumps(value, ensure_ascii=False)
        return True, "" if value is None else str(value)

    def body_for_media(self, media):
        """The body a scenario serves for one media type object: its own
        example (`media_example`), else one built from its schema."""
        found, value = self.media_example(media)
        if found:
            return value
        return self.sample_for_schema((media or {}).get("schema"))

    def success_media(self, op: Operation):
        """Pick the 2xx media type object for an operation, if any.

        Returns (media_or_None, content_type). content_type is None when the
        response has no body; non-JSON when the success response is e.g. a PDF.
        """
        for code in sorted(op.responses.keys()):
            if code.startswith("2") or code == "default":
                resp = op.responses[code] or {}
                content = resp.get("content") or {}
                if not content:
                    return None, None
                if "application/json" in content:
                    return content["application/json"] or {}, "application/json"
                # first non-JSON content type (PDF/CSV/ZIP/...)
                ctype = next(iter(content.keys()))
                return content[ctype] or {}, ctype
        return None, None

    def success_schema(self, op: Operation):
        """Pick the 2xx JSON response schema for an operation, if any.

        Returns (schema_or_None, content_type), as `success_media` does.
        """
        media, ctype = self.success_media(op)
        return (media.get("schema") if media is not None else None), ctype

    def error_codes(self, op: Operation) -> list[str]:
        """Declared 4xx/5xx status codes for this operation."""
        return sorted(c for c in op.responses if c[:1] in ("4", "5") and c.isdigit())


def _schema_example(schema) -> tuple[bool, object]:
    """`(found, value)` for a schema's own `example`, else the first of its
    `examples` list (JSON Schema's form, OpenAPI 3.1)."""
    if not isinstance(schema, dict):
        return False, None
    if "example" in schema:
        return True, schema["example"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return True, examples[0]
    return False, None


def _stop_value(schema):
    """The value to place where synthesis has to stop (self-reference).

    A zero value of the declared type, never `null`: the body is checked
    against the same schema it was built from, so a `null` in a required,
    non-nullable field turns the generator into the source of the drift it
    then reports. An object stops as `{}` — it may still be missing
    required properties, which the check names precisely, instead of
    "null, contract says integer" pointing at the tool.
    """
    if not isinstance(schema, dict):
        return None
    if "const" in schema:
        return schema["const"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]
    stype = schema.get("type")
    if isinstance(stype, list):   # OpenAPI 3.1: ["string", "null"]
        stype = next((t for t in stype if t != "null"), None)
    if stype is None and "properties" in schema:
        stype = "object"
    if stype == "object":
        return {}
    if stype == "array":
        return []
    return _primitive_sample(schema, stype)


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
