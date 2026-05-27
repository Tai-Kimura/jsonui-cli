"""Load OpenAPI / Swagger 2.0 JSON files and extract :class:`SchemaIR`.

Entry point: :func:`load_swagger`. Reads ``*.json`` files from a directory,
filters to OpenAPI / Swagger artifacts via :func:`is_swagger_file`, parses
each into a :class:`SwaggerDocument`.

§3.3 ERROR halt rules enforced here (raise :class:`OpenAPILoadError`):

- ``oneOf`` / ``anyOf`` / discriminator → halt (Q11)
- multi-file ``$ref`` (``./other.yaml#/Foo``) → halt (Q12)
- direct self-reference without collection indirection → halt (Q13)
- inline object name collision with top-level schema → halt (Q4 / B2)
- ``type: object`` with no ``$ref`` / ``properties`` / ``additionalProperties``
  → halt (§3.3)
- YAML files → halt (Q8: JSON only in v1)

Soft cases (warning only, NOT halt):

- ``additionalProperties: true`` / omitted → silently drop extra fields,
  DTO declares only enumerated properties (§3.3, §4)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema_filter import SchemaFilterConfig, apply_filter
from .schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    OneOfRef,
    OneOfVariant,
    PrimitiveKind,
    SchemaDef,
    SwaggerDocument,
)


class OpenAPILoadError(Exception):
    """Raised when a swagger document violates §3.3 v1 constraints.

    Carries the source file + JSON pointer so the caller can show the user
    where the offending construct lives. ``code`` is a short tag used by
    ``_sync_api_models`` to surface a meaningful CLI error.
    """

    def __init__(self, code: str, message: str, *, source: str = "", pointer: str = ""):
        self.code = code
        self.source = source
        self.pointer = pointer
        suffix = []
        if source:
            suffix.append(source)
        if pointer:
            suffix.append(pointer)
        location = f" ({' '.join(suffix)})" if suffix else ""
        super().__init__(f"[{code}] {message}{location}")


def is_swagger_file(path: Path) -> bool:
    """Return True if *path* looks like an OpenAPI 3.x or Swagger 2.0 doc.

    Reads only the top-level keys via ``json.load`` — cheap enough to call
    on every ``*.json`` in ``api_directory`` during discovery.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return "openapi" in data or "swagger" in data


def load_swagger(
    api_directory: Path,
    *,
    schema_filter: SchemaFilterConfig | None = None,
) -> list[SwaggerDocument]:
    """Discover and parse every swagger doc under *api_directory*.

    YAML files trigger an :class:`OpenAPILoadError` (Q8 — v1 is JSON only).
    Non-swagger ``*.json`` files are silently skipped.

    *schema_filter* is the optional v2 path/schema filter. When omitted
    or :meth:`SchemaFilterConfig.is_active` returns False, every
    ``components.schemas.*`` entry is processed (v3 Phase 1 behavior).

    Returns a list of :class:`SwaggerDocument`, one per source file, in
    sorted-path order. Generators iterate this list.
    """
    if not api_directory.exists():
        return []

    for yml in sorted(api_directory.rglob("*.yaml")) + sorted(api_directory.rglob("*.yml")):
        raise OpenAPILoadError(
            "yaml-not-supported",
            "YAML swagger files are not supported in v1 (Q8). Convert to JSON.",
            source=str(yml),
        )

    docs: list[SwaggerDocument] = []
    for json_path in sorted(api_directory.rglob("*.json")):
        if not is_swagger_file(json_path):
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        docs.append(parse_swagger(raw, str(json_path), schema_filter=schema_filter))
    return docs


def parse_swagger(
    raw: dict[str, Any],
    source_path: str,
    *,
    schema_filter: SchemaFilterConfig | None = None,
) -> SwaggerDocument:
    """Parse one swagger dict into a :class:`SwaggerDocument`.

    Splits ``components.schemas`` into ``EnumDef`` (standalone enums) and
    ``SchemaDef`` (object schemas). Inline object schemas are extracted as
    derived ``SchemaDef`` with a synthesized name.

    When *schema_filter* is active, the kept schema set is computed
    **before** parsing — schemas outside the kept set are skipped entirely
    (their content never reaches the per-schema parser, so their
    polymorphic / shapeless / cyclic constructs do not trigger halts).
    This matches the v2 plan §2.2 "filter is lenient, parser is strict"
    contract.
    """
    # Resolve the kept set up front. When no filter is supplied or it's
    # inactive, the resulting set covers every schema name so the loop
    # below is a no-op filter.
    if schema_filter is not None and schema_filter.is_active():
        filter_result = apply_filter(raw, schema_filter)
        kept_schema_names: set[str] | None = set(filter_result.kept)
        filtered_out = filter_result.excluded
        skip_domain_overrides = filter_result.skip_domain_matches
    else:
        kept_schema_names = None  # sentinel: "keep everything"
        filtered_out = frozenset()
        # skip_domain may still be active in isolation — apply it against
        # all schema names so the generator can honor per-app overrides
        # without filtering anything else.
        if schema_filter is not None and schema_filter.skip_domain:
            filter_result = apply_filter(raw, schema_filter)
            skip_domain_overrides = filter_result.skip_domain_matches
        else:
            skip_domain_overrides = frozenset()
    info = raw.get("info", {}) if isinstance(raw, dict) else {}
    title = info.get("title", "") if isinstance(info, dict) else ""
    version = info.get("version", "") if isinstance(info, dict) else ""

    components = raw.get("components", {}) if "openapi" in raw else {}
    if "swagger" in raw and "definitions" in raw:
        # Swagger 2.0: definitions live at top level instead of components.schemas
        schemas_root = raw.get("definitions", {})
    else:
        schemas_root = (components or {}).get("schemas", {})

    if not isinstance(schemas_root, dict):
        return SwaggerDocument(source_path=source_path, title=title, version=version,
                               schemas=[], enums=[])

    schema_names = set(schemas_root.keys())
    enums: list[EnumDef] = []
    schemas: list[SchemaDef] = []
    # Inline object schemas extracted on the fly — appended to `schemas`
    # after the main loop so post-processing (cycle / collision) sees them.
    inline_schemas: list[SchemaDef] = []
    inline_names: set[str] = set()

    for name, body in schemas_root.items():
        if not isinstance(body, dict):
            continue
        # Skip filtered-out schemas before any parse work (lenient filter).
        if kept_schema_names is not None and name not in kept_schema_names:
            continue
        pointer = f"#/components/schemas/{name}"
        if _is_enum_only(body):
            enums.append(_parse_enum(name, body, source_path=source_path, pointer=pointer))
            continue

        merged = _resolve_all_of(body, schemas_root, source_path=source_path, pointer=pointer)
        _check_polymorphic(merged, source_path=source_path, pointer=pointer)

        # Wrapper path: top-level non-object schemas (``type: string`` /
        # ``type: array`` / etc.) are emitted as single-field wrapper DTOs
        # with custom single-value (en|de)coders. Detected before
        # ``_check_object_typed`` because that helper only fires on
        # ``type: object`` and would silently allow ``type: string`` to
        # fall through into ``_extract_fields`` which returns empty fields.
        if _is_wrapper_schema(merged):
            wrapper_schema, wrapper_extras, wrapper_enums = _parse_wrapper_schema(
                name,
                merged,
                schema_names,
                inline_names,
                source_path=source_path,
                pointer=pointer,
            )
            for derived in wrapper_extras:
                inline_schemas.append(derived)
                inline_names.add(derived.name)
            for enum_def in wrapper_enums:
                if enum_def.name not in {e.name for e in enums}:
                    enums.append(enum_def)
            schemas.append(wrapper_schema)
            continue

        _check_object_typed(merged, source_path=source_path, pointer=pointer)

        fields, extra_inline, extra_enums = _extract_fields(
            merged,
            parent_name=name,
            top_level_names=schema_names,
            inline_names=inline_names,
            source_path=source_path,
            parent_pointer=pointer,
        )
        for derived in extra_inline:
            inline_schemas.append(derived)
            inline_names.add(derived.name)
        for enum_def in extra_enums:
            if enum_def.name in {e.name for e in enums}:
                # Same derived name re-derived from another field — both
                # cases produce identical enum cases by construction, so
                # silently dedupe.
                continue
            enums.append(enum_def)

        schemas.append(
            SchemaDef(
                name=name,
                fields=fields,
                description=_str_or_none(merged.get("description")),
                deprecated=bool(merged.get("deprecated", False)),
                skip_domain=bool(merged.get("x-jui-skip-domain", False)),
                source_pointer=f"{source_path}{pointer}",
                is_strict=merged.get("additionalProperties") is False,
                # Conformance flags computed after we know all field types.
                is_equatable=_all_equatable(fields),
                is_hashable=_all_hashable(fields),
                is_sendable=_all_sendable(fields),
            )
        )

    schemas.extend(inline_schemas)

    # oneOf discriminator: validate that each parent carrying a one_of
    # field actually declares a sibling property matching
    # ``discriminator.propertyName``. Catches typos in swagger early.
    for schema in schemas:
        for f in schema.fields:
            if f.type.is_one_of_ref and f.type.one_of is not None:
                disc_prop = f.type.one_of.discriminator_property
                if not any(g.wire_name == disc_prop for g in schema.fields):
                    raise OpenAPILoadError(
                        "oneof-discriminator-sibling-missing",
                        f"Schema {schema.name!r} field {f.wire_name!r} uses "
                        f"discriminator.propertyName={disc_prop!r} but no "
                        f"sibling property with that name exists in the "
                        f"parent schema. Add the property or fix the "
                        f"discriminator name.",
                        source=source_path,
                        pointer=schema.source_pointer,
                    )

    # Cycle detection — only direct self-reference without collection
    # indirection. Collection-mediated cycles are explicitly allowed (§3.3 / Q13).
    for schema in schemas:
        if schema.has_direct_self_reference():
            raise OpenAPILoadError(
                "direct-self-reference",
                f"Schema '{schema.name}' has a direct self-reference field "
                f"(no collection indirection). Wrap the field in an array "
                f"or map, or split into a non-recursive shape. "
                f"v1 halts on all 3 platforms for cross-platform parity.",
                source=source_path,
                pointer=schema.source_pointer,
            )

    return SwaggerDocument(
        source_path=source_path,
        title=title,
        version=version,
        schemas=schemas,
        enums=enums,
        filtered_out=filtered_out,
        skip_domain_overrides=skip_domain_overrides,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _str_or_none(v: Any) -> str | None:
    if isinstance(v, str) and v.strip():
        return v
    return None


def _is_wrapper_schema(body: dict[str, Any]) -> bool:
    """True when a top-level schema body is a non-object primitive/array.

    These wire as bare values (``"hello"``, ``[1, 2, 3]``) — not JSON
    objects — so codegen has to emit a single-field wrapper with a
    custom single-value (en|de)coder rather than the normal object DTO.

    ``type: string|integer`` + ``enum`` is excluded because the
    enum-only branch handles it earlier in :func:`parse_swagger`. Bodies
    that have ``properties`` are excluded too (an object that happens
    to declare a ``type:`` is just a normal object).
    """
    t = body.get("type")
    if t not in ("string", "integer", "number", "boolean", "array"):
        return False
    if body.get("properties"):
        return False
    if t in ("string", "integer") and "enum" in body:
        return False
    return True


def _parse_wrapper_schema(
    name: str,
    body: dict[str, Any],
    top_level_names: set[str],
    inline_names: set[str],
    *,
    source_path: str,
    pointer: str,
) -> tuple[SchemaDef, list[SchemaDef], list[EnumDef]]:
    """Build a single-field wrapper :class:`SchemaDef` for a non-object schema.

    Reuses :func:`_field_type` to resolve primitives / arrays / inline
    derived schemas — anything the regular object path can emit. The
    synthesized field is named ``"items"`` for arrays and ``"value"`` for
    everything else; this is the property consumer code will see on the
    generated DTO (``dto.value`` / ``dto.items``).
    """
    wrapped_type, extra_inline, extra_enums = _field_type(
        body,
        parent_name=name,
        field_name="value",
        top_level_names=top_level_names,
        inline_names=inline_names,
        source_path=source_path,
        pointer=pointer,
    )
    field_name = "items" if wrapped_type.is_array else "value"
    field = FieldDef(
        wire_name=field_name,
        type=wrapped_type,
        required=True,
        description=None,
        deprecated=False,
        default=None,
        has_default=False,
    )
    fields = [field]
    schema = SchemaDef(
        name=name,
        fields=fields,
        description=_str_or_none(body.get("description")),
        deprecated=bool(body.get("deprecated", False)),
        skip_domain=bool(body.get("x-jui-skip-domain", False)),
        source_pointer=f"{source_path}{pointer}",
        is_strict=False,
        is_equatable=_all_equatable(fields),
        is_hashable=_all_hashable(fields),
        is_sendable=_all_sendable(fields),
        is_wrapper=True,
        wrapped_type=wrapped_type,
        wrapper_field_name=field_name,
    )
    return schema, list(extra_inline), list(extra_enums)


def _is_enum_only(body: dict[str, Any]) -> bool:
    """True if *body* is a standalone enum (no nested properties).

    Heuristic: has ``enum`` AND has a primitive ``type`` (``string`` /
    ``integer``) AND has no ``properties``. Schemas like
    ``{"type": "string", "enum": [...]}`` qualify.
    """
    if "enum" not in body:
        return False
    if body.get("type") not in ("string", "integer"):
        return False
    if "properties" in body:
        return False
    return True


def _parse_enum(
    name: str,
    body: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> EnumDef:
    """Parse a standalone enum schema into :class:`EnumDef`.

    Honors ``x-enum-varnames`` (a non-standard but widely used extension)
    for case name overrides. Falls back to raw values (strings) or
    ``value_<N>`` for integers.
    """
    raw_values = body.get("enum", []) or []
    if not isinstance(raw_values, list):
        raise OpenAPILoadError(
            "invalid-enum",
            f"Enum '{name}' must be a list",
            source=source_path,
            pointer=pointer,
        )
    type_str = body.get("type")
    if type_str == "string":
        kind = PrimitiveKind.STRING
        string_values = [str(v) for v in raw_values]
        integer_values: list[int] = []
        default_case_names = string_values
    elif type_str == "integer":
        kind = PrimitiveKind.INTEGER
        try:
            integer_values = [int(v) for v in raw_values]
        except (TypeError, ValueError) as e:
            raise OpenAPILoadError(
                "invalid-enum",
                f"Integer enum '{name}' contains non-integer value: {e}",
                source=source_path,
                pointer=pointer,
            ) from e
        string_values = []
        default_case_names = [f"value_{v}" for v in integer_values]
    else:
        raise OpenAPILoadError(
            "invalid-enum",
            f"Enum '{name}' must declare type: string or type: integer "
            f"(got: {type_str})",
            source=source_path,
            pointer=pointer,
        )

    varnames = body.get("x-enum-varnames")
    if isinstance(varnames, list) and len(varnames) == len(raw_values):
        case_names = [str(v) for v in varnames]
    else:
        case_names = list(default_case_names)

    return EnumDef(
        name=name,
        kind=kind,
        case_names=case_names,
        string_values=string_values,
        integer_values=integer_values,
        description=_str_or_none(body.get("description")),
        deprecated=bool(body.get("deprecated", False)),
    )


def _resolve_all_of(
    body: dict[str, Any],
    schemas_root: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> dict[str, Any]:
    """Flatten ``allOf`` into a merged single-schema dict.

    Later items override earlier ones for ``properties`` (right-bias matches
    common OpenAPI tool behavior). ``required`` lists are unioned.
    """
    if "allOf" not in body:
        return body
    parts = body.get("allOf")
    if not isinstance(parts, list):
        return body

    merged: dict[str, Any] = {k: v for k, v in body.items() if k != "allOf"}
    merged_props: dict[str, Any] = dict(merged.get("properties") or {})
    merged_required: list[str] = list(merged.get("required") or [])

    for i, part in enumerate(parts):
        if isinstance(part, dict) and "$ref" in part:
            ref = part["$ref"]
            resolved = _resolve_ref_inline(
                ref, schemas_root,
                source_path=source_path,
                pointer=f"{pointer}/allOf/{i}",
            )
        else:
            resolved = part if isinstance(part, dict) else {}
        if not isinstance(resolved, dict):
            continue
        for k, v in (resolved.get("properties") or {}).items():
            merged_props[k] = v
        for r in (resolved.get("required") or []):
            if r not in merged_required:
                merged_required.append(r)

    merged["properties"] = merged_props
    merged["required"] = merged_required
    return merged


def _resolve_ref_inline(
    ref: str,
    schemas_root: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
) -> dict[str, Any]:
    """Resolve a same-file ``$ref`` to its target dict.

    Multi-file refs (``./other.yaml#/Foo``) and URL refs halt — silent
    partial codegen is worse than explicit fail (§9.3, Q12).
    """
    _check_ref_local(ref, source_path=source_path, pointer=pointer)
    # Strip the leading "#/components/schemas/" (OpenAPI 3) or
    # "#/definitions/" (Swagger 2.0) prefix to get the bare name.
    if ref.startswith("#/components/schemas/"):
        name = ref[len("#/components/schemas/"):]
    elif ref.startswith("#/definitions/"):
        name = ref[len("#/definitions/"):]
    else:
        raise OpenAPILoadError(
            "unsupported-ref",
            f"Unsupported $ref shape: {ref!r}",
            source=source_path,
            pointer=pointer,
        )
    target = schemas_root.get(name)
    if not isinstance(target, dict):
        raise OpenAPILoadError(
            "ref-not-found",
            f"$ref target '{name}' not found in components.schemas",
            source=source_path,
            pointer=pointer,
        )
    return target


def _check_ref_local(ref: str, *, source_path: str, pointer: str) -> None:
    """Halt on multi-file / URL refs. Used by every ref resolution path."""
    if not isinstance(ref, str):
        raise OpenAPILoadError(
            "invalid-ref",
            "$ref must be a string",
            source=source_path,
            pointer=pointer,
        )
    if ref.startswith("#"):
        return
    # Anything with a file path component or scheme is multi-file/URL.
    if ref.startswith(("http://", "https://", "./", "../", "/")) or ".yaml" in ref or ".yml" in ref or ".json" in ref:
        raise OpenAPILoadError(
            "multi-file-ref",
            f"Multi-file / URL $ref not supported in v1: {ref!r}. "
            f"Inline the referenced schema or wait for v2 multi-file support.",
            source=source_path,
            pointer=pointer,
        )
    raise OpenAPILoadError(
        "unsupported-ref",
        f"Unrecognized $ref shape: {ref!r}",
        source=source_path,
        pointer=pointer,
    )


def _parse_one_of_discriminator(
    body: dict[str, Any],
    *,
    top_level_names: set[str],
    source_path: str,
    pointer: str,
) -> OneOfRef:
    """Parse ``{ oneOf: [...], discriminator: { propertyName, mapping } }``.

    Validates everything the v1 contract requires:

    - ``discriminator`` is a dict with non-empty ``propertyName`` (string)
    - ``mapping`` is a non-empty dict (explicit mapping required in v1)
    - every mapping value is a same-file ``$ref`` to a top-level schema
    - every ``oneOf`` entry is itself a ``$ref`` (inline variants not
      supported)
    - the set of variants in ``oneOf`` matches the set of mapped refs

    Returns an :class:`OneOfRef` with variants in **mapping order** so
    generators emit deterministic ``case`` / ``when`` branches.
    """
    disc = body.get("discriminator")
    if not isinstance(disc, dict):
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator' must be a dict with 'propertyName' and 'mapping'",
            source=source_path,
            pointer=pointer,
        )
    prop_name = disc.get("propertyName")
    if not isinstance(prop_name, str) or not prop_name.strip():
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.propertyName' must be a non-empty string",
            source=source_path,
            pointer=pointer,
        )
    mapping = disc.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise OpenAPILoadError(
            "invalid-discriminator",
            "'discriminator.mapping' is required (explicit map of "
            "discriminator value → variant $ref). Default-from-schema-name "
            "is deferred to v2.",
            source=source_path,
            pointer=pointer,
        )

    one_of = body.get("oneOf")
    if not isinstance(one_of, list) or not one_of:
        raise OpenAPILoadError(
            "invalid-oneof",
            "'oneOf' must be a non-empty list of $ref objects",
            source=source_path,
            pointer=pointer,
        )

    # Collect variant ref names from oneOf (inline variants not supported).
    one_of_refs: set[str] = set()
    for i, entry in enumerate(one_of):
        if not isinstance(entry, dict) or "$ref" not in entry or len(entry) != 1:
            raise OpenAPILoadError(
                "invalid-oneof",
                "Each oneOf entry must be a `$ref` object — inline variants "
                "are not supported in v1.",
                source=source_path,
                pointer=f"{pointer}/oneOf/{i}",
            )
        ref = entry["$ref"]
        _check_ref_local(ref, source_path=source_path, pointer=f"{pointer}/oneOf/{i}")
        ref_name = ref.rsplit("/", 1)[-1]
        if ref_name not in top_level_names:
            raise OpenAPILoadError(
                "oneof-variant-not-found",
                f"oneOf variant {ref_name!r} is not a top-level schema. "
                f"Inline / nested variants are not supported in v1.",
                source=source_path,
                pointer=f"{pointer}/oneOf/{i}",
            )
        one_of_refs.add(ref_name)

    # Parse mapping in declared order; validate each ref + cross-check.
    variants: list[OneOfVariant] = []
    mapped_refs: set[str] = set()
    for disc_value, ref in mapping.items():
        if not isinstance(disc_value, str) or not disc_value.strip():
            raise OpenAPILoadError(
                "invalid-discriminator",
                "discriminator.mapping keys must be non-empty strings",
                source=source_path,
                pointer=pointer,
            )
        if not isinstance(ref, str):
            raise OpenAPILoadError(
                "invalid-discriminator",
                f"discriminator.mapping[{disc_value!r}] must be a $ref string",
                source=source_path,
                pointer=pointer,
            )
        _check_ref_local(ref, source_path=source_path, pointer=pointer)
        ref_name = ref.rsplit("/", 1)[-1]
        if ref_name not in top_level_names:
            raise OpenAPILoadError(
                "oneof-variant-not-found",
                f"discriminator.mapping[{disc_value!r}] → {ref_name!r} is "
                f"not a top-level schema",
                source=source_path,
                pointer=pointer,
            )
        if ref_name not in one_of_refs:
            raise OpenAPILoadError(
                "discriminator-mapping-mismatch",
                f"discriminator.mapping[{disc_value!r}] points to {ref_name!r} "
                f"but this schema is not listed in the oneOf array. Add it "
                f"to oneOf or remove the mapping entry.",
                source=source_path,
                pointer=pointer,
            )
        variants.append(OneOfVariant(disc_value, ref_name))
        mapped_refs.add(ref_name)

    # Every oneOf entry must have a mapping (otherwise it's unreachable).
    unmapped = one_of_refs - mapped_refs
    if unmapped:
        raise OpenAPILoadError(
            "discriminator-mapping-mismatch",
            "oneOf variants are missing from discriminator.mapping: "
            + ", ".join(sorted(unmapped))
            + ". Add explicit mapping entries for each variant.",
            source=source_path,
            pointer=pointer,
        )

    return OneOfRef(
        discriminator_property=prop_name,
        variants=tuple(variants),
    )


def _check_polymorphic(
    body: dict[str, Any],
    *,
    source_path: str,
    pointer: str,
    at_field_level: bool = False,
) -> None:
    """Halt on unsupported polymorphism.

    Allowed in v1:
    - ``oneOf`` **with** ``discriminator`` and explicit ``mapping``, **only
      at field level** (parsed in :func:`_field_type`)

    Halted:
    - Schema-level ``oneOf`` even with discriminator — top-level
      discriminated unions are a v2 follow-up
    - Field-level ``oneOf`` alone (no discriminator) — no way to dispatch
    - ``anyOf`` — untagged union, codegen pattern unclear, deferred to v2
    - ``discriminator`` without ``oneOf`` — meaningless alone
    """
    if "anyOf" in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'anyOf' polymorphism is not supported. "
            "Wait for v2 untagged-union codegen.",
            source=source_path,
            pointer=pointer,
        )
    if "oneOf" in body and "discriminator" not in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'oneOf' without 'discriminator' is not supported. "
            "Add a discriminator block with an explicit mapping so codegen "
            "knows which sibling field tags the union and which value selects "
            "which variant.",
            source=source_path,
            pointer=pointer,
        )
    if "discriminator" in body and "oneOf" not in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "'discriminator' without 'oneOf' is meaningless. "
            "Either remove the discriminator or add a oneOf list of variants.",
            source=source_path,
            pointer=pointer,
        )
    # Schema-level oneOf even with discriminator is deferred to v2 —
    # discriminated envelopes (the OpenAPI-standard pattern) need different
    # codegen than field-level oneOf and aren't yet implemented.
    if not at_field_level and "oneOf" in body and "discriminator" in body:
        raise OpenAPILoadError(
            "polymorphic-not-supported",
            "Schema-level 'oneOf' + 'discriminator' (top-level discriminated "
            "envelope) is not supported in v1. v1 supports oneOf + discriminator "
            "only when used inside a property (field-level union with a sibling "
            "tag field). Wait for v2 envelope codegen.",
            source=source_path,
            pointer=pointer,
        )


def _check_object_typed(body: dict[str, Any], *, source_path: str, pointer: str) -> None:
    """Halt on ``type: object`` schemas with no type information (§3.3).

    Only fires at the top-level schema body. Inline objects are checked
    individually when their parent field is parsed.
    """
    if body.get("type") != "object":
        return
    has_props = isinstance(body.get("properties"), dict) and body["properties"]
    has_typed_addl = isinstance(body.get("additionalProperties"), dict)
    addl_value = body.get("additionalProperties")
    has_strict_or_open = isinstance(addl_value, bool) or addl_value is None
    if has_props or has_typed_addl or "allOf" in body or "$ref" in body:
        return
    # additionalProperties: true / false / omitted with NO properties → schema
    # is shapeless; we'd emit an empty struct with no fields. Halt instead so
    # the user fixes the schema.
    if has_strict_or_open and not has_props:
        raise OpenAPILoadError(
            "object-without-type",
            "Schema declares 'type: object' but has no $ref / properties / "
            "typed additionalProperties. Add explicit field declarations or "
            "wait for v2 (which may treat this as `Map<String, Any>`).",
            source=source_path,
            pointer=pointer,
        )


def _extract_fields(
    body: dict[str, Any],
    *,
    parent_name: str,
    top_level_names: set[str],
    inline_names: set[str],
    source_path: str,
    parent_pointer: str,
) -> tuple[list[FieldDef], list[SchemaDef], list[EnumDef]]:
    """Extract :class:`FieldDef` list + inline-derived schemas + inline enums.

    Walks ``properties`` in declaration order. For each property:

    - ``$ref`` → object/enum reference (resolution decided at IR consumption
      time since we don't yet know if the target is enum or object)
    - field-level ``allOf: [{$ref}]`` (common nullable/default-wrapping
      idiom in OpenAPI 3) → unwrapped to the ref'd type
    - inline ``type: object`` with ``properties`` → derive a child schema
      named ``{ParentName}{FieldPascal}``, halt on collision with top-level
    - inline ``type: string | integer`` + ``enum`` → derive a top-level
      enum named the same way, append to ``extra_enums``
    - ``array`` / typed-map / primitives → straightforward
    """
    properties = body.get("properties") or {}
    required_set = set(body.get("required") or [])
    fields: list[FieldDef] = []
    extra_inline: list[SchemaDef] = []
    extra_enums: list[EnumDef] = []

    if not isinstance(properties, dict):
        return fields, extra_inline, extra_enums

    for prop_name, prop_body in properties.items():
        if not isinstance(prop_body, dict):
            continue
        prop_pointer = f"{parent_pointer}/properties/{prop_name}"
        ftype, derived, enums = _field_type(
            prop_body,
            parent_name=parent_name,
            field_name=prop_name,
            top_level_names=top_level_names,
            inline_names=inline_names,
            source_path=source_path,
            pointer=prop_pointer,
        )
        extra_inline.extend(derived)
        extra_enums.extend(enums)
        is_required = prop_name in required_set
        ftype_with_null = FieldType(
            **{**ftype.__dict__, "nullable": (not is_required) or bool(prop_body.get("nullable"))}
        )
        fields.append(
            FieldDef(
                wire_name=prop_name,
                type=ftype_with_null,
                required=is_required,
                description=_str_or_none(prop_body.get("description")),
                deprecated=bool(prop_body.get("deprecated", False)),
                default=prop_body.get("default") if "default" in prop_body else None,
                has_default="default" in prop_body,
            )
        )
    return fields, extra_inline, extra_enums


def _field_type(
    body: dict[str, Any],
    *,
    parent_name: str,
    field_name: str,
    top_level_names: set[str],
    inline_names: set[str],
    source_path: str,
    pointer: str,
) -> tuple[FieldType, list[SchemaDef], list[EnumDef]]:
    """Resolve a single property's type to :class:`FieldType`.

    Returns the type + any inline-derived schemas + any inline-derived enums
    (transitively, since nested inline objects can themselves contain inline
    objects/enums).
    """
    _check_polymorphic(body, source_path=source_path, pointer=pointer, at_field_level=True)

    # 1pre. ``oneOf`` + ``discriminator`` with explicit ``mapping`` →
    # discriminated union. The parent schema's field becomes a tagged enum;
    # generators emit a custom Codable / KSerializer / discriminated union
    # type and dispatch on the sibling property named in ``discriminator``.
    if "oneOf" in body and "discriminator" in body:
        one_of = _parse_one_of_discriminator(
            body,
            top_level_names=top_level_names,
            source_path=source_path,
            pointer=pointer,
        )
        return (
            FieldType(is_one_of_ref=True, one_of=one_of),
            [],
            [],
        )

    # 1a. Field-level ``allOf: [{$ref: X}]`` is the OpenAPI 3 idiom for adding
    # nullable / default / description to a $ref'd type. Unwrap it to the
    # underlying ref so the field is just a reference.
    if isinstance(body.get("allOf"), list) and len(body["allOf"]) == 1:
        only = body["allOf"][0]
        if isinstance(only, dict) and "$ref" in only and len(only) == 1:
            ref = only["$ref"]
            _check_ref_local(ref, source_path=source_path, pointer=pointer)
            ref_name = ref.rsplit("/", 1)[-1]
            return (
                FieldType(is_object_ref=True, ref_name=ref_name),
                [],
                [],
            )

    # 1. $ref → another schema
    if "$ref" in body:
        ref = body["$ref"]
        _check_ref_local(ref, source_path=source_path, pointer=pointer)
        ref_name = ref.rsplit("/", 1)[-1]
        return (
            FieldType(is_object_ref=True, ref_name=ref_name),
            [],
            [],
        )

    type_str = body.get("type")

    # 2. array<T>
    if type_str == "array":
        items = body.get("items")
        if not isinstance(items, dict):
            raise OpenAPILoadError(
                "invalid-array",
                f"'array' field '{field_name}' is missing 'items'",
                source=source_path,
                pointer=pointer,
            )
        element_type, derived, derived_enums = _field_type(
            items,
            parent_name=parent_name,
            field_name=field_name + "_item",
            top_level_names=top_level_names,
            inline_names=inline_names,
            source_path=source_path,
            pointer=f"{pointer}/items",
        )
        return (
            FieldType(is_array=True, element=element_type),
            derived,
            derived_enums,
        )

    # 3. object
    if type_str == "object" or "properties" in body or "additionalProperties" in body:
        # 3a. typed additionalProperties → map
        addl = body.get("additionalProperties")
        if isinstance(addl, dict):
            value_type, derived, derived_enums = _field_type(
                addl,
                parent_name=parent_name,
                field_name=field_name + "_value",
                top_level_names=top_level_names,
                inline_names=inline_names,
                source_path=source_path,
                pointer=f"{pointer}/additionalProperties",
            )
            return (
                FieldType(is_map=True, element=value_type),
                derived,
                derived_enums,
            )

        # 3b. inline object with properties → derive a child schema
        if isinstance(body.get("properties"), dict) and body["properties"]:
            derived_name = body.get("x-jui-name") or f"{parent_name}{_pascal(field_name)}"
            if derived_name in top_level_names:
                raise OpenAPILoadError(
                    "inline-name-collision",
                    f"Inline object at {pointer} would be named '{derived_name}' "
                    f"but a top-level schema with that name already exists. "
                    f"Set 'x-jui-name' on the inline schema or extract it to "
                    f"components.schemas.",
                    source=source_path,
                    pointer=pointer,
                )
            if derived_name in inline_names:
                raise OpenAPILoadError(
                    "inline-name-collision",
                    f"Inline object at {pointer} resolves to '{derived_name}' "
                    f"but the same name was already derived elsewhere. "
                    f"Set 'x-jui-name' to disambiguate.",
                    source=source_path,
                    pointer=pointer,
                )
            inline_fields, transitive, transitive_enums = _extract_fields(
                body,
                parent_name=derived_name,
                top_level_names=top_level_names,
                inline_names=inline_names | {derived_name},
                source_path=source_path,
                parent_pointer=pointer,
            )
            derived_schema = SchemaDef(
                name=derived_name,
                fields=inline_fields,
                description=_str_or_none(body.get("description")),
                deprecated=bool(body.get("deprecated", False)),
                skip_domain=bool(body.get("x-jui-skip-domain", False)),
                source_pointer=f"{source_path}{pointer}",
                is_strict=body.get("additionalProperties") is False,
                is_equatable=_all_equatable(inline_fields),
                is_hashable=_all_hashable(inline_fields),
                is_sendable=_all_sendable(inline_fields),
            )
            return (
                FieldType(is_object_ref=True, ref_name=derived_name),
                [derived_schema] + transitive,
                transitive_enums,
            )

        # 3c. additionalProperties: true / false / omitted on an inline object
        # → silently drop extras, but field has no shape → halt
        if not body.get("properties"):
            raise OpenAPILoadError(
                "object-without-type",
                f"Inline object at {pointer} has no 'properties' and no "
                f"typed 'additionalProperties'. Add field declarations or "
                f"use $ref.",
                source=source_path,
                pointer=pointer,
            )

    # 4. inline enum (string or integer) — derive a top-level enum named
    # ``{ParentName}{FieldPascal}`` (or ``x-jui-name`` override). Matches the
    # inline-object treatment.
    if type_str in ("string", "integer") and "enum" in body:
        derived_name = body.get("x-jui-name") or f"{parent_name}{_pascal(field_name)}"
        if derived_name in top_level_names:
            raise OpenAPILoadError(
                "inline-name-collision",
                f"Inline enum at {pointer} would be named '{derived_name}' "
                f"but a top-level schema with that name already exists. "
                f"Set 'x-jui-name' on the inline enum or extract it to "
                f"components.schemas.",
                source=source_path,
                pointer=pointer,
            )
        enum_def = _parse_enum(derived_name, body, source_path=source_path, pointer=pointer)
        return (
            FieldType(is_enum_ref=True, ref_name=derived_name),
            [],
            [enum_def],
        )

    # 5. primitives
    if type_str == "string":
        return (
            FieldType(is_primitive=True, primitive=PrimitiveKind.STRING),
            [],
            [],
        )
    if type_str == "boolean":
        return (
            FieldType(is_primitive=True, primitive=PrimitiveKind.BOOLEAN),
            [],
            [],
        )
    if type_str == "integer":
        fmt = body.get("format")
        if fmt == "int32":
            kind = PrimitiveKind.INTEGER_32
        elif fmt == "int64":
            kind = PrimitiveKind.INTEGER_64
        else:
            kind = PrimitiveKind.INTEGER
        return FieldType(is_primitive=True, primitive=kind), [], []
    if type_str == "number":
        fmt = body.get("format")
        if fmt == "float":
            return FieldType(is_primitive=True, primitive=PrimitiveKind.FLOAT), [], []
        return FieldType(is_primitive=True, primitive=PrimitiveKind.DOUBLE), [], []

    raise OpenAPILoadError(
        "unknown-type",
        f"Field at {pointer} has unrecognized type {type_str!r}",
        source=source_path,
        pointer=pointer,
    )


_PASCAL_RE = re.compile(r"(?:^|[_\s-])([a-z0-9])")
_TRAILING_CASE_RE = re.compile(r"[^A-Za-z0-9]+")


def _pascal(s: str) -> str:
    """Convert wire name (snake_case / kebab-case / camelCase) to PascalCase.

    Examples:
        ``display_name`` → ``DisplayName``
        ``user-id`` → ``UserId``
        ``displayName`` → ``DisplayName``
    """
    if not s:
        return s
    cleaned = _TRAILING_CASE_RE.sub("_", s)
    parts = [p for p in cleaned.split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _all_equatable(fields: list[FieldDef]) -> bool:
    """All field types support equality (no ``Any`` leakage).

    In v1 we halt on oneOf/anyOf, so ``Any`` shouldn't actually appear.
    Kept as a flag for future-proofing when v2 adds polymorphic types.
    """
    return True


def _all_hashable(fields: list[FieldDef]) -> bool:
    """All field types are hashable.

    Typed maps break Hashable on Swift (``[String: T]`` is Hashable only
    when ``T: Hashable`` — usually true for primitive values, but we
    conservatively drop Hashable when any field is a map to avoid an
    obscure compile error in consumer code).
    """
    for f in fields:
        if f.type.is_map:
            return False
        if f.type.is_array and f.type.element and f.type.element.is_map:
            return False
    return True


def _all_sendable(fields: list[FieldDef]) -> bool:
    """All field types are Sendable.

    In v1, every emitted type is a value type or a primitive, so this is
    trivially True. The flag exists so a future v2 introducing class-typed
    DTOs can downgrade conformance per schema.
    """
    return True
