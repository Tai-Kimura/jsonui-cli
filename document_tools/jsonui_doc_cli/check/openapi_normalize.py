"""Normalization of OpenAPI documents into a comparable form.

Why this exists (review §3-1): the docs side is hand-written OpenAPI 3.0
(oneOf/anyOf banned by jui codegen), while implementation-side documents —
especially FastAPI + Pydantic v2 — are OpenAPI 3.1 full of:

- Optional fields as ``anyOf: [X, {"type": "null"}]``
- 3.1 type arrays ``type: ["string", "null"]``
- ``allOf: [{"$ref": ...}]`` wrappers (added around refs to carry defaults)
- ``Literal[X]`` fields as ``const: X`` (3.0 spells this ``enum: [X]``)
- auto-generated ``title`` on every schema
- auto-added 422 (HTTPValidationError) on every endpoint

Without folding those away, naive structural diff drowns in false
mismatches. Both sides are passed through the same normalizer so the
comparator only ever sees canonical shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Keys that never affect the wire contract.
_DROPPED_KEYS = {
    "title", "description", "examples", "example", "default",
    "deprecated", "externalDocs", "xml", "readOnly", "writeOnly",
    "summary", "operationId", "tags", "security", "servers",
}

# integer/number format widths are a type-family concern, not a contract
# difference (int32 vs int64 does not change the generated DTO type on any
# JsonUI platform). String formats (date-time, uuid, ...) DO matter.
_NUMERIC_TYPES = {"integer", "number"}

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

# Impl-side paths that are framework furniture, never part of the contract.
DEFAULT_IGNORE_PATHS = [
    "/docs", "/docs/*", "/redoc", "/openapi.json", "/openapi.yaml",
    "/health", "/healthz", "/favicon.ico",
]

# Response codes auto-added by frameworks (FastAPI: 422 HTTPValidationError).
DEFAULT_IGNORE_RESPONSE_CODES = {"422"}

# Pydantic v2 splits one model into `Name-Input` / `Name-Output` when its
# validation and serialization schemas differ, and then the base name does
# not exist at all. The docs side has one name for that class and no way to
# spell the split, so the difference is not something a rename can close.
# `-` cannot occur in a Python class name, which is what makes the suffix
# unambiguously the artifact rather than somebody's naming style.
_PYDANTIC_IO_SUFFIXES = ("-Input", "-Output")


def component_base_name(name: str) -> str:
    """The class name behind a components/schemas key."""
    for suffix in _PYDANTIC_IO_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


@dataclass
class NormOperation:
    """One path+method, normalized."""
    path: str                     # original path template (doc spelling)
    method: str                   # upper-case
    param_names: list[str]        # positional path-param names (for warnings)
    parameters: dict = field(default_factory=dict)   # (in,name) -> {required, schema}
    request_body: dict | None = None                 # {required, schema} | None
    responses: dict = field(default_factory=dict)    # code(str) -> schema|None
    # Which component name each side used AT each position, e.g.
    # {"requestBody body": "CreateUser", "→ 200 body[]": "UserOut"}.
    # $ref is inlined by normalization, so the name is captured on the way
    # through; a position where this side inlined the shape has no entry.
    ref_names: dict = field(default_factory=dict)    # location -> schema name


@dataclass
class NormSpec:
    operations: dict = field(default_factory=dict)   # (norm_path, method) -> NormOperation
    warnings: list = field(default_factory=list)


def normalize_path_key(path: str) -> str:
    """Positional path normalization: /users/{user_id} -> /users/{}
    and trailing-slash insensitivity."""
    out = []
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            out.append("{}")
        else:
            out.append(seg)
    norm = "/".join(out)
    if len(norm) > 1 and norm.endswith("/"):
        norm = norm[:-1]
    return norm


def path_param_names(path: str) -> list[str]:
    return [seg[1:-1] for seg in path.split("/")
            if seg.startswith("{") and seg.endswith("}")]


class _Resolver:
    """Local $ref resolver with cycle protection."""

    def __init__(self, doc: dict):
        self.doc = doc

    def lookup(self, ref: str) -> Any:
        if not ref.startswith("#/"):
            # Multi-file refs are banned on the docs side by jui; on the
            # impl side they shouldn't occur in a single exported document.
            raise KeyError(f"non-local $ref not supported: {ref}")
        node: Any = self.doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            node = node[part]
        return node


def _record_ref(names: dict | None, at: str | None, ref: str) -> None:
    """Note that this position carries a component name.

    Outermost wins: ``Foo = allOf[$ref Bar]`` names this position ``Foo``,
    and resolving through to ``Bar`` must not overwrite it. The same rule
    makes a multi-member ``allOf`` report its first named member rather than
    an arbitrary later one — under-reporting on an inherently unnameable
    composite, which is the safe direction for a warning whose whole purpose
    is that every line is actionable.
    """
    if names is None or at is None:
        return
    names.setdefault(at, ref.rsplit("/", 1)[-1])


def normalize_schema(schema: Any, resolver: _Resolver,
                     _seen: frozenset = frozenset(),
                     names: dict | None = None,
                     at: str | None = None) -> Any:
    """Recursively normalize one schema node. Returns a canonical dict
    (or a primitive for degenerate cases).

    With `names` and `at`, component names are collected by position as the
    refs are inlined (see NormOperation.ref_names). Positions are spelled the
    way `_schema_diffs` spells them, so a name and a structural difference at
    the same place carry the same location string.

    Two shapes deliberately record nothing: `additionalProperties` (no
    comparison descends there, so a name would be reported at a position
    nothing else can confirm) and multi-variant `anyOf`/`oneOf` (pairing
    branches across two documents by index is a guess).
    """
    if schema is None or schema is True:
        return {}
    if schema is False:
        return {"type": "never"}
    if not isinstance(schema, dict):
        return schema

    # $ref → inline (cycle-guarded)
    if "$ref" in schema:
        ref = schema["$ref"]
        _record_ref(names, at, ref)
        if ref in _seen:
            return {"$circular": ref.rsplit("/", 1)[-1]}
        try:
            target = resolver.lookup(ref)
        except KeyError:
            return {"$unresolved": ref}
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        base = normalize_schema(target, resolver, _seen | {ref}, names, at)
        if merged:
            extra = normalize_schema(merged, resolver, _seen | {ref}, names, at)
            if isinstance(base, dict) and isinstance(extra, dict):
                base = {**base, **extra}
        return base

    node = {k: v for k, v in schema.items()
            if k not in _DROPPED_KEYS and not k.startswith("x-")}
    nullable = bool(node.pop("nullable", False))

    # 3.1 type arrays: ["string", "null"] → string + nullable
    if isinstance(node.get("type"), list):
        types = [t for t in node["type"] if t != "null"]
        if len(types) < len(node["type"]):
            nullable = True
        node["type"] = types[0] if len(types) == 1 else types

    # anyOf/oneOf with a null branch → variant + nullable
    for comb in ("anyOf", "oneOf"):
        if comb in node and isinstance(node[comb], list):
            variants = [v for v in node[comb]
                        if not (isinstance(v, dict) and v.get("type") == "null")]
            if len(variants) < len(node[comb]):
                nullable = True
            if len(variants) == 1:
                inner = normalize_schema(variants[0], resolver, _seen, names, at)
                rest = {k: v for k, v in node.items() if k != comb}
                rest_norm = (normalize_schema(rest, resolver, _seen, names, at)
                             if rest else {})
                merged = {**inner, **rest_norm} if isinstance(inner, dict) else inner
                if nullable and isinstance(merged, dict):
                    merged["nullable"] = True
                return merged
            node[comb] = [normalize_schema(v, resolver, _seen) for v in variants]

    # allOf: single-wrapper collapse, else merge object members
    if "allOf" in node and isinstance(node["allOf"], list):
        parts = [normalize_schema(v, resolver, _seen, names, at)
                 for v in node["allOf"]]
        rest = {k: v for k, v in node.items() if k != "allOf"}
        merged: dict = {}
        mergeable = all(isinstance(p, dict) for p in parts)
        if mergeable:
            for p in parts:
                for k, v in p.items():
                    if k == "properties" and "properties" in merged:
                        merged["properties"] = {**merged["properties"], **v}
                    elif k == "required" and "required" in merged:
                        merged["required"] = sorted(set(merged["required"]) | set(v))
                    else:
                        merged[k] = v
            if rest:
                rest_norm = normalize_schema(rest, resolver, _seen, names, at)
                if isinstance(rest_norm, dict):
                    merged.update(rest_norm)
            node = merged
        else:
            node["allOf"] = parts

    # Recurse into structural members
    if isinstance(node.get("properties"), dict):
        node["properties"] = {
            name: normalize_schema(sub, resolver, _seen, names,
                                   f"{at}.{name}" if at is not None else None)
            for name, sub in sorted(node["properties"].items())
        }
    if "items" in node:
        node["items"] = normalize_schema(node["items"], resolver, _seen, names,
                                         f"{at}[]" if at is not None else None)
    if isinstance(node.get("additionalProperties"), dict):
        node["additionalProperties"] = normalize_schema(
            node["additionalProperties"], resolver, _seen)
    elif node.get("additionalProperties") is True:
        # absent and true mean the same thing in OpenAPI
        node.pop("additionalProperties")

    if isinstance(node.get("required"), list):
        req = sorted(set(node["required"]))
        if req:
            node["required"] = req
        else:
            node.pop("required")

    # 3.1 `const: X` is the single-value constraint 3.0 spells `enum: [X]`
    # (3.0 has no `const`, so a hand-written docs side can only use the enum
    # form). Fold it in before the enum rules below so null-folding and
    # sorting apply identically, and so the difference — when there is one —
    # surfaces under the closed comparison key `enum` rather than a key no
    # comparison ever reads. A node declaring both is the intersection;
    # const is the narrower constraint, so it wins.
    if "const" in node:
        node["enum"] = [node.pop("const")]

    # enum: drop null member (folded into nullable), sort for stable compare
    if isinstance(node.get("enum"), list):
        values = [v for v in node["enum"] if v is not None]
        if len(values) < len(node["enum"]):
            nullable = True
        node["enum"] = sorted(values, key=lambda v: (str(type(v)), str(v)))

    # numeric format widths are family-level noise
    if node.get("type") in _NUMERIC_TYPES:
        node.pop("format", None)

    if nullable:
        node["nullable"] = True
    return node


def _content_json_schema(container: dict, resolver: _Resolver,
                         names: dict | None = None,
                         at: str | None = None) -> Any | None:
    """Extract the application/json schema from a requestBody/response."""
    content = container.get("content")
    if not isinstance(content, dict):
        return None
    for ctype, media in content.items():
        if ctype.split(";")[0].strip() in ("application/json", "*/*"):
            return normalize_schema(media.get("schema"), resolver, frozenset(),
                                    names, at)
    return None


def normalize_spec(doc: dict, label: str) -> NormSpec:
    """Normalize a whole OpenAPI document into NormSpec."""
    resolver = _Resolver(doc)
    spec = NormSpec()
    paths = doc.get("paths", {})
    if not isinstance(paths, dict):
        return spec
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        if "$ref" in path_item:
            try:
                path_item = resolver.lookup(path_item["$ref"])
            except KeyError:
                spec.warnings.append(f"{label}: unresolved path $ref for {path}")
                continue
        shared_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            norm = NormOperation(
                path=path,
                method=method.upper(),
                param_names=path_param_names(path),
            )
            # parameters: path-level merged with operation-level
            for p in list(shared_params) + list(op.get("parameters", [])):
                if isinstance(p, dict) and "$ref" in p:
                    try:
                        p = resolver.lookup(p["$ref"])
                    except KeyError:
                        continue
                if not isinstance(p, dict):
                    continue
                key = (p.get("in", "query"), p.get("name", ""))
                norm.parameters[key] = {
                    "required": bool(p.get("required", False))
                    or p.get("in") == "path",
                    "schema": normalize_schema(
                        p.get("schema"), resolver, frozenset(), norm.ref_names,
                        f"param {key[0]}:{key[1]} schema"),
                }
            # requestBody
            body = op.get("requestBody")
            if isinstance(body, dict):
                if "$ref" in body:
                    try:
                        body = resolver.lookup(body["$ref"])
                    except KeyError:
                        body = None
                if isinstance(body, dict):
                    norm.request_body = {
                        "required": bool(body.get("required", False)),
                        "schema": _content_json_schema(
                            body, resolver, norm.ref_names, "requestBody body"),
                    }
            # responses
            for code, resp in (op.get("responses") or {}).items():
                if isinstance(resp, dict) and "$ref" in resp:
                    try:
                        resp = resolver.lookup(resp["$ref"])
                    except KeyError:
                        continue
                if not isinstance(resp, dict):
                    continue
                code_key = str(code)
                if code_key.lower() == "default":
                    spec.warnings.append(
                        f"{label}: 'default' response on {method.upper()} {path} "
                        "is not compared"
                    )
                    continue
                if code_key.upper().endswith("XX") and len(code_key) == 3:
                    spec.warnings.append(
                        f"{label}: wildcard response '{code_key}' on "
                        f"{method.upper()} {path} treated as {code_key[0]}00"
                    )
                    code_key = f"{code_key[0]}00"
                norm.responses[code_key] = _content_json_schema(
                    resp, resolver, norm.ref_names, f"→ {code_key} body")

            key = (normalize_path_key(path), norm.method)
            if key in spec.operations:
                spec.warnings.append(
                    f"{label}: duplicate operation {norm.method} {path} "
                    "(same normalized path)"
                )
            spec.operations[key] = norm
    return spec
