"""Web (TypeScript) API model emitter — DTO (`@generated`) + Domain scaffold.

Mirrors the iOS / Android generators with v3 plan §2.2 Web shape:

- DTO: ``export interface UserDto { ... }`` — wire-shape, regenerated every build
- Domain: ``export interface User { dto: UserDto }`` + ``export const userFromDto``
  factory function (camelCase + ``FromDto`` suffix per plan §2.2 naming rule)

Two ``case_convention`` modes (v3 plan §3.2):

- ``"snake_case"`` (default) — DTO field names match wire format exactly
  (``display_name``); no runtime conversion needed
- ``"camelCase"`` — DTO field names are camelCase (``displayName``);
  ``parse{Name}`` / ``serialize{Name}`` helpers emitted alongside to bridge
  wire ↔ domain naming
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.comment_safety import sanitize_block_comment
from ..core.generated_marker import comment_footer, comment_header
from ..core.impl_updater import atomic_write_text
from ..core.openapi_naming import factory_name, snake_to_camel, snake_to_pascal
from ..core.schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    OneOfRef,
    PrimitiveKind,
    SchemaDef,
    SwaggerDocument,
    UnionDef,
    collect_string_formats,
    schema_string_formats,
)


CASE_CONVENTIONS = ("snake_case", "camelCase")


@dataclass(frozen=True)
class WebApiPlatformConfig:
    """Resolved ``api.platforms.web`` config (with defaults applied).

    ``format_mapping`` mirrors the project-level ``api.format_mapping``
    opt-in (plan 03) with the per-doc opt-out in ``format_excluded_docs``
    (swagger file basenames). When on: ``date-time`` fields become ``Date``
    on the DTO with generated parse/serialize helpers doing the ISO 8601
    conversion (no ``JSON.parse`` passthrough for affected schemas);
    ``uuid`` / ``binary`` become documented string typealiases.
    """

    sources_root: Path           # absolute, e.g. <project>/<web.root>/src
    model_dir: str = "models"    # relative to sources_root
    dto_subdir: str = "generated"
    case_convention: str = "snake_case"
    format_mapping: bool = False
    format_excluded_docs: frozenset[str] = frozenset()


class WebApiModelGenerator:
    """Render TS DTO + Domain scaffold files for a swagger document."""

    GENERATOR_NAME = "jui build (api model)"

    def __init__(self, config: WebApiPlatformConfig):
        if config.case_convention not in CASE_CONVENTIONS:
            raise ValueError(
                f"Unknown Web case_convention {config.case_convention!r}; "
                f"expected one of {CASE_CONVENTIONS}"
            )
        self._config = config

    def _format_enabled(self, doc: SwaggerDocument) -> bool:
        """Per-doc format-aware mapping decision (opt-in + per-doc opt-out)."""
        if not self._config.format_mapping:
            return False
        return Path(doc.source_path).name not in self._config.format_excluded_docs

    # ----------------------------- paths ----------------------------- #

    def dto_path(self, schema_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / self._config.dto_subdir
            / f"{schema_name}Dto.ts"
        )

    def enum_path(self, enum_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / self._config.dto_subdir
            / f"{enum_name}.ts"
        )

    def domain_path(self, schema_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / f"{schema_name}.ts"
        )

    def support_path(self, basename: str) -> Path:
        """Path of a shared format support file (``Uuid.ts`` etc.)."""
        return (
            self._config.sources_root
            / self._config.model_dir
            / self._config.dto_subdir
            / basename
        )

    # ----------------------- format support files --------------------- #

    def generate_uuid_alias_source(self) -> str:
        """Shared ``Uuid.ts`` — a documented string typealias.

        Branded-type gymnastics are deliberately avoided; the alias exists
        for greppability and intent, not nominal safety.
        """
        header = comment_header(
            source="api.format_mapping (shared support)",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        body = (
            "/** OpenAPI `format: uuid` — kept as a string on the wire and in memory. */\n"
            "export type Uuid = string;"
        )
        return f"{header}\n\n{body}\n\n{footer}\n"

    def generate_base64_alias_source(self) -> str:
        """Shared ``Base64Data.ts`` — a documented string typealias."""
        header = comment_header(
            source="api.format_mapping (shared support)",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        body = (
            "/** OpenAPI `format: binary` — base64 string on the wire and in memory. */\n"
            "export type Base64Data = string;"
        )
        return f"{header}\n\n{body}\n\n{footer}\n"

    # ---------------------------- emit DTO --------------------------- #

    def generate_dto_source(self, schema: SchemaDef, doc: SwaggerDocument) -> str:
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#{schema.source_pointer.rsplit('#', 1)[-1]}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        enum_names = {e.name for e in doc.enums}

        fmt = self._format_enabled(doc)
        affected = web_affected_names(doc) if fmt else frozenset()
        is_affected = fmt and schema.name in affected

        # Wrapper path: ``type: string`` / ``type: array`` etc. become a
        # TypeScript type alias (``export type FooDto = string;``).
        # Structural typing makes this transparent at every call site —
        # the alias is interchangeable with the underlying primitive.
        if schema.is_wrapper:
            return _generate_web_wrapper_dto(
                schema,
                doc,
                header,
                footer,
                enum_names,
                format_native=fmt,
                affected=affected,
            )

        has_oneof = any(f.type.is_one_of_ref for f in schema.fields)

        lines: list[str] = []
        # Import enum / nested DTO refs that appear in this schema.
        for imp in self._collect_imports(
            schema, enum_names, doc, format_native=fmt, affected=affected
        ):
            lines.append(imp)
        if lines:
            lines.append("")

        # Emit a discriminated-union type per oneOf field, before the
        # interface so the interface can reference it.
        for f in schema.fields:
            if f.type.is_one_of_ref and f.type.one_of is not None:
                lines.extend(_emit_ts_oneof_union(schema, f, f.type.one_of))
                lines.append("")

        if schema.description:
            lines.extend(_jsdoc_lines(schema.description))
        if schema.deprecated:
            lines.append("/** @deprecated */")
        if schema.is_strict:
            lines.append("// additionalProperties: false (strict — extra fields are dropped on decode)")
        lines.append(f"export interface {schema.name}Dto {{")
        for f in schema.fields:
            lines.extend(
                self._dto_field_lines(f, enum_names, schema, format_native=fmt)
            )
        lines.append("}")

        if is_affected:
            # Format-aware helpers own the whole parse/serialize surface
            # for date-affected schemas (plan 03) — one emitter driven by
            # the reason set (Date conversion / camelCase skew / oneOf
            # dispatch) so the raw wire JSON never reaches the Date-typed
            # DTO without conversion.
            lines.extend(
                self._emit_ts_format_helpers(schema, enum_names, affected)
            )
        else:
            # camelCase mode also needs parse/serialize helpers since the
            # wire format is snake_case. Skip when the schema has oneOf —
            # the dedicated dispatch helpers (emitted below) own the
            # parse/serialize surface for that case.
            if (
                self._config.case_convention == "camelCase"
                and self._has_wire_camel_skew(schema)
                and not has_oneof
            ):
                lines.extend(self._parse_serialize_helpers(schema, enum_names))

            # oneOf-bearing schemas need dispatch helpers regardless of case
            # convention — caller passes raw JSON, helper wraps each variant
            # in the corresponding ``{ kind, data }`` shape.
            if has_oneof:
                lines.extend(_emit_ts_oneof_helpers(schema, enum_names, self._config.case_convention))

        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    def _collect_imports(
        self,
        schema: SchemaDef,
        enum_names: set[str],
        doc: SwaggerDocument,
        *,
        format_native: bool = False,
        affected: frozenset[str] | set[str] = frozenset(),
    ) -> list[str]:
        """Return ``import`` lines for every other DTO/enum this schema references."""
        refs = schema.referenced_schemas() - {schema.name}
        lines: list[str] = []
        for name in sorted(refs):
            if name in enum_names:
                lines.append(f'import type {{ {name} }} from "./{name}";')
            elif format_native and schema.name in affected and name in affected:
                # Affected refs are parsed/serialized by delegation — pull
                # in their helpers + wire type alongside the DTO type.
                lines.append(
                    f'import {{ parse{name}Dto, serialize{name}Dto }} from "./{name}Dto";'
                )
                lines.append(
                    f'import type {{ {name}Dto, {name}Wire }} from "./{name}Dto";'
                )
            else:
                lines.append(f'import type {{ {name}Dto }} from "./{name}Dto";')
        if format_native:
            used = schema_string_formats(schema)
            if "uuid" in used:
                lines.append('import type { Uuid } from "./Uuid";')
            if "binary" in used:
                lines.append('import type { Base64Data } from "./Base64Data";')
        return lines

    def _dto_field_lines(
        self,
        field: FieldDef,
        enum_names: set[str],
        schema: SchemaDef,
        *,
        format_native: bool = False,
    ) -> list[str]:
        out: list[str] = []
        if field.description:
            out.extend(f"  {ln}" for ln in _jsdoc_lines(field.description))
        if field.deprecated:
            out.append("  /** @deprecated */")
        if field.type.is_one_of_ref:
            type_str = _ts_oneof_union_name(schema, field)
        else:
            type_str = _ts_type_with_enums(
                field.type, enum_names, format_native=format_native
            )
        name = self._ts_property_name(field)
        # Optional fields use ``?:`` rather than ``| undefined`` for ergonomics.
        sep = "?:" if field.type.nullable else ":"
        out.append(f"  {name}{sep} {type_str};")
        return out

    def _ts_property_name(self, field: FieldDef) -> str:
        """In snake_case mode wire and TS names match (no transformation).

        In camelCase mode we lowercase-camel the wire name.
        """
        if self._config.case_convention == "camelCase":
            return snake_to_camel(field.wire_name)
        return field.wire_name

    def _has_wire_camel_skew(self, schema: SchemaDef) -> bool:
        """True if any field's wire name differs from its camelCase form."""
        for f in schema.fields:
            if snake_to_camel(f.wire_name) != f.wire_name:
                return True
        return False

    def _parse_serialize_helpers(
        self,
        schema: SchemaDef,
        enum_names: set[str],
    ) -> list[str]:
        """Emit ``parse{Name}`` / ``serialize{Name}`` for camelCase mode.

        These bridge the on-the-wire snake_case JSON to the domain-facing
        camelCase shape. Kept intentionally minimal — no enum coercion or
        date parsing. Historically dates were entirely a Domain-proxy
        responsibility (v3 plan "filter native conversion through Domain
        proxies"); since plan 03 that principle holds only while
        ``api.format_mapping`` is off — date-affected schemas take the
        format-aware helper path (:meth:`_emit_ts_format_helpers`) and
        never reach this emitter.
        """
        name = schema.name
        wire_iface = f"{name}Wire"
        out: list[str] = []
        out.append("")
        out.append(f"// Wire format (raw JSON shape) — used by parse{name} / serialize{name}.")
        out.append(f"export interface {wire_iface} {{")
        for f in schema.fields:
            type_str = _ts_type_with_enums(f.type, enum_names)
            sep = "?:" if f.type.nullable else ":"
            out.append(f"  {f.wire_name}{sep} {type_str};")
        out.append("}")
        out.append("")
        out.append(f"export const parse{name} = (wire: {wire_iface}): {name}Dto => ({{")
        for f in schema.fields:
            camel = snake_to_camel(f.wire_name)
            out.append(f"  {camel}: wire.{f.wire_name},")
        out.append("});")
        out.append("")
        out.append(f"export const serialize{name} = (model: {name}Dto): {wire_iface} => ({{")
        for f in schema.fields:
            camel = snake_to_camel(f.wire_name)
            out.append(f"  {f.wire_name}: model.{camel},")
        out.append("});")
        return out

    def _emit_ts_format_helpers(
        self,
        schema: SchemaDef,
        enum_names: set[str],
        affected: frozenset[str] | set[str],
    ) -> list[str]:
        """Unified wire ↔ DTO helpers for a date-affected schema (plan 03).

        One emitter driven by the reason set: ISO 8601 ⇄ ``Date``
        conversion, camelCase renames (when configured), and oneOf
        dispatch. Affected refs delegate to the referenced DTO's own
        ``parse{Ref}Dto`` / ``serialize{Ref}Dto`` so the conversion
        cascades without any ``JSON.parse``-passthrough gap.
        """
        name = schema.name
        camel_mode = self._config.case_convention == "camelCase"
        out: list[str] = []

        if "date-time" in schema_string_formats(schema):
            out.extend(_TS_PARSE_ISO_DATE_HELPER)

        out.append("")
        out.append(
            f"// Wire format (raw JSON shape) — used by parse{name}Dto / serialize{name}Dto."
        )
        out.append(f"export interface {name}Wire {{")
        for f in schema.fields:
            if f.type.is_one_of_ref:
                wire_type = "unknown"
            else:
                wire_type = _ts_wire_type(f.type, enum_names, affected)
            sep = "?:" if f.type.nullable else ":"
            out.append(f"  {_ts_obj_key(f.wire_name)}{sep} {wire_type};")
        out.append("}")

        # ---------- parse ----------
        out.append("")
        out.append(f"export const parse{name}Dto = (wire: {name}Wire): {name}Dto => {{")
        for f in schema.fields:
            if not (f.type.is_one_of_ref and f.type.one_of is not None):
                continue
            prop = self._ts_property_name(f)
            union_name = _ts_oneof_union_name(schema, f)
            disc_field = next(
                (g for g in schema.fields if g.wire_name == f.type.one_of.discriminator_property),
                None,
            )
            disc_wire = disc_field.wire_name if disc_field else f.type.one_of.discriminator_property
            out.append(f"  let {prop}: {union_name};")
            out.append(f"  switch (wire[{_ts_oneof_kind_literal(disc_wire)}]) {{")
            for variant in f.type.one_of.variants:
                kind = _ts_oneof_kind_literal(variant.discriminator_value)
                if variant.ref_name in affected:
                    data_expr = (
                        f"parse{variant.ref_name}Dto("
                        f"wire[{_ts_oneof_kind_literal(f.wire_name)}] as {variant.ref_name}Wire)"
                    )
                else:
                    data_expr = (
                        f"wire[{_ts_oneof_kind_literal(f.wire_name)}] as {variant.ref_name}Dto"
                    )
                out.append(f"    case {kind}:")
                out.append(f"      {prop} = {{ kind: {kind}, data: {data_expr} }};")
                out.append("      break;")
            out.append("    default:")
            out.append(f'      {prop} = {{ kind: "unknown" }};')
            out.append("  }")
        return_parts: list[str] = []
        for f in schema.fields:
            prop = self._ts_property_name(f)
            if f.type.is_one_of_ref:
                return_parts.append(f"{prop}: {prop}")
                continue
            src = f"wire.{f.wire_name}" if _ts_is_identifier(f.wire_name) else f"wire[{_ts_oneof_kind_literal(f.wire_name)}]"
            if _ts_needs_conversion(f.type, affected):
                converted = _ts_parse_expr(f.type, src, affected, depth=0)
                if f.type.nullable:
                    converted = f"{src} == null ? undefined : {converted}"
                return_parts.append(f"{prop}: {converted}")
            else:
                return_parts.append(f"{prop}: {src}")
        out.append("  return { " + ", ".join(return_parts) + " };")
        out.append("};")

        # ---------- serialize ----------
        out.append("")
        out.append(f"export const serialize{name}Dto = (model: {name}Dto): {name}Wire => {{")
        obj_parts: list[str] = []
        for f in schema.fields:
            prop = self._ts_property_name(f)
            key = _ts_obj_key(f.wire_name)
            if f.type.is_one_of_ref and f.type.one_of is not None:
                local = f"{prop}Value"
                out.append(f"  let {local}: unknown;")
                out.append(f"  switch (model.{prop}.kind) {{")
                for variant in f.type.one_of.variants:
                    kind = _ts_oneof_kind_literal(variant.discriminator_value)
                    if variant.ref_name in affected:
                        unwrap = f"serialize{variant.ref_name}Dto(model.{prop}.data)"
                    else:
                        unwrap = f"model.{prop}.data"
                    out.append(f"    case {kind}:")
                    out.append(f"      {local} = {unwrap};")
                    out.append("      break;")
                out.append('    case "unknown":')
                out.append(f"      {local} = null;")
                out.append("      break;")
                out.append("  }")
                obj_parts.append(f"{key}: {local}")
                continue
            src = f"model.{prop}"
            if _ts_needs_conversion(f.type, affected):
                converted = _ts_serialize_expr(f.type, src, affected, depth=0)
                if f.type.nullable:
                    converted = f"{src} == null ? undefined : {converted}"
                obj_parts.append(f"{key}: {converted}")
            else:
                obj_parts.append(f"{key}: {src}")
        out.append("  return { " + ", ".join(obj_parts) + " };")
        out.append("};")
        return out

    # ---------------------------- emit union ------------------------- #

    def generate_union_source(self, union: UnionDef, doc: SwaggerDocument) -> str:
        """TS source for a schema-level union.

        The DTO type is the plain payload union (``DogDto | CatDto``) —
        wire-faithful, so parents referencing it need no parse cascade.
        The ``{Name}DtoCase`` shape + ``match{Name}Dto`` helper mirror the
        field-level ``{ kind, data }`` convention including the
        forward-compat ``"unknown"`` arm; ``serialize{Name}Dto`` folds a
        case back to the wire payload, (re)writing the tag key so
        round-trips hold even when the variant schema does not declare
        the tag property.
        """
        header = comment_header(
            source=_relative_source(doc.source_path)
            + f"#{union.source_pointer.rsplit('#', 1)[-1]}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        name = union.name
        tag_key = _ts_oneof_kind_literal(union.discriminator_property)

        fmt = self._format_enabled(doc)
        affected = web_affected_names(doc) if fmt else frozenset()
        is_affected = fmt and name in affected

        lines: list[str] = []
        for ref in sorted({v.ref_name for v in union.variants}):
            if is_affected and ref in affected:
                lines.append(
                    f'import {{ parse{ref}Dto, serialize{ref}Dto }} from "./{ref}Dto";'
                )
                lines.append(
                    f'import type {{ {ref}Dto, {ref}Wire }} from "./{ref}Dto";'
                )
            else:
                lines.append(f'import type {{ {ref}Dto }} from "./{ref}Dto";')
        lines.append("")
        if union.description:
            lines.extend(_jsdoc_lines(union.description))
        if union.deprecated:
            lines.append("/** @deprecated */")
        payload_union = " | ".join(f"{v.ref_name}Dto" for v in union.variants)
        lines.append(f"export type {name}Dto = {payload_union};")
        lines.append("")
        lines.append(
            f"// Exhaustive-match shape for {name}Dto — mirrors the field-level"
        )
        lines.append(
            '// oneOf `{ kind, data }` convention, including the forward-compat'
        )
        lines.append('// "unknown" arm.')
        lines.append(f"export type {name}DtoCase =")
        for variant in union.variants:
            kind = _ts_oneof_kind_literal(variant.discriminator_value)
            lines.append(f"  | {{ kind: {kind}; data: {variant.ref_name}Dto }}")
        lines.append('  | { kind: "unknown" };')
        lines.append("")
        lines.append(
            f"export const match{name}Dto = (value: {name}Dto | unknown): {name}DtoCase => {{"
        )
        lines.append(
            f"  switch ((value as Record<string, unknown> | null)?.[{tag_key}]) {{"
        )
        for variant in union.variants:
            kind = _ts_oneof_kind_literal(variant.discriminator_value)
            lines.append(f"    case {kind}:")
            lines.append(
                f"      return {{ kind: {kind}, data: value as {variant.ref_name}Dto }};"
            )
        lines.append("    default:")
        lines.append('      return { kind: "unknown" };')
        lines.append("  }")
        lines.append("};")
        lines.append("")
        lines.append(
            f"export const serialize{name}Dto = (value: {name}DtoCase): unknown => {{"
        )
        lines.append("  switch (value.kind) {")
        for variant in union.variants:
            kind = _ts_oneof_kind_literal(variant.discriminator_value)
            lines.append(f"    case {kind}:")
            if is_affected and variant.ref_name in affected:
                lines.append(
                    f"      return {{ ...serialize{variant.ref_name}Dto(value.data), "
                    f"[{tag_key}]: {kind} }};"
                )
            else:
                lines.append(
                    f"      return {{ ...value.data, [{tag_key}]: {kind} }};"
                )
        lines.append('    case "unknown":')
        lines.append("      return {};")
        lines.append("  }")
        lines.append("};")

        if is_affected:
            wire_union = " | ".join(
                f"{v.ref_name}Wire" if v.ref_name in affected else f"{v.ref_name}Dto"
                for v in union.variants
            )
            lines.append("")
            lines.append(
                f"// Raw JSON shape of the union payload — parse{name}Dto converts"
            )
            lines.append("// date-affected variants into their Date-typed DTOs.")
            lines.append(f"export type {name}Wire = {wire_union};")
            lines.append("")
            lines.append(
                f"export const parse{name}Dto = (wire: {name}Wire | unknown): {name}Dto => {{"
            )
            lines.append(
                f"  switch ((wire as Record<string, unknown> | null)?.[{tag_key}]) {{"
            )
            for variant in union.variants:
                kind = _ts_oneof_kind_literal(variant.discriminator_value)
                lines.append(f"    case {kind}:")
                if variant.ref_name in affected:
                    lines.append(
                        f"      return parse{variant.ref_name}Dto(wire as {variant.ref_name}Wire);"
                    )
                else:
                    lines.append(f"      return wire as {variant.ref_name}Dto;")
            lines.append("    default:")
            lines.append(f"      return wire as {name}Dto;")
            lines.append("  }")
            lines.append("};")

        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    def generate_union_domain_source(self, union: UnionDef) -> str:
        """Domain scaffold for a union — thin wrapper, same shape as object
        schemas (see plan ``02a-union-emit-design.md``), plus a dispatch
        hint pointing at the match helper.
        """
        factory = factory_name(union.name)
        return (
            f'import type {{ {union.name}Dto }} from "./generated/{union.name}Dto";\n'
            "\n"
            f"export interface {union.name} {{\n"
            f"  dto: {union.name}Dto;\n"
            "  // User customization zone — add proxies, computed properties,\n"
            "  // stored properties, methods, and conversions here (or in a\n"
            f"  // separate utility module that consumes the {union.name} type).\n"
            f"  // Dispatch on the union with `match{union.name}Dto(dto)` from "
            f"./generated/{union.name}Dto.\n"
            "}\n"
            "\n"
            f"export const {factory} = (dto: {union.name}Dto): {union.name} => ({{ dto }});\n"
        )

    # ---------------------------- emit enum -------------------------- #

    def generate_enum_source(self, enum: EnumDef, doc: SwaggerDocument) -> str:
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#/components/schemas/{enum.name}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()

        if enum.kind == PrimitiveKind.STRING:
            values = " | ".join(f'"{v}"' for v in enum.string_values)
        else:
            values = " | ".join(str(v) for v in enum.integer_values)

        lines: list[str] = []
        if enum.description:
            lines.extend(_jsdoc_lines(enum.description))
        if enum.deprecated:
            lines.append("/** @deprecated */")
        lines.append(f"export type {enum.name} = {values};")

        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    # --------------------------- emit Domain ------------------------- #

    def generate_domain_source(self, schema: SchemaDef) -> str:
        """interface User + factory function ``userFromDto(dto)``.

        Per v3 plan §2.2 Web rationale: TS structural typing + zero-runtime
        interface is preferred over class. The factory keeps cross-platform
        consistency loose but documented in the plan.
        """
        factory = factory_name(schema.name)
        return (
            f'import type {{ {schema.name}Dto }} from "./generated/{schema.name}Dto";\n'
            "\n"
            f"export interface {schema.name} {{\n"
            f"  dto: {schema.name}Dto;\n"
            "  // User customization zone — add proxies, computed properties,\n"
            "  // stored properties, methods, and conversions here (or in a\n"
            "  // separate utility module that consumes the User type).\n"
            "}\n"
            "\n"
            f"export const {factory} = (dto: {schema.name}Dto): {schema.name} => ({{ dto }});\n"
        )

    # ----------------------------- writes ---------------------------- #

    @dataclass(frozen=True)
    class WriteResult:
        path: Path
        wrote: bool
        skipped_existing: bool = False

    def write_dto(self, schema: SchemaDef, doc: SwaggerDocument) -> "WebApiModelGenerator.WriteResult":
        path = self.dto_path(schema.name)
        wrote = atomic_write_text(path, self.generate_dto_source(schema, doc))
        return self.WriteResult(path=path, wrote=wrote)

    def write_enum(self, enum: EnumDef, doc: SwaggerDocument) -> "WebApiModelGenerator.WriteResult":
        path = self.enum_path(enum.name)
        wrote = atomic_write_text(path, self.generate_enum_source(enum, doc))
        return self.WriteResult(path=path, wrote=wrote)

    def write_domain(self, schema: SchemaDef) -> "WebApiModelGenerator.WriteResult":
        path = self.domain_path(schema.name)
        if path.exists():
            return self.WriteResult(path=path, wrote=False, skipped_existing=True)
        wrote = atomic_write_text(path, self.generate_domain_source(schema))
        return self.WriteResult(path=path, wrote=wrote)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _relative_source(absolute_path: str) -> str:
    return Path(absolute_path).name


def _jsdoc_lines(text: str) -> list[str]:
    """Render *text* as a `/** ... */` block.

    TS block comments do not nest, so `/*` is harmless here — but a `*/`
    in the text ends the comment early and spills prose into code, so the
    same sanitizer runs on this face too.
    """
    text = sanitize_block_comment(text)
    raw = text.splitlines() or [text]
    if len(raw) == 1:
        return [f"/** {raw[0]} */"]
    out = ["/**"]
    for ln in raw:
        out.append(f" * {ln}")
    out.append(" */")
    return out


_PRIMITIVE_TO_TS: dict[PrimitiveKind, str] = {
    PrimitiveKind.STRING: "string",
    PrimitiveKind.INTEGER_32: "number",
    PrimitiveKind.INTEGER_64: "number",
    PrimitiveKind.INTEGER: "number",
    PrimitiveKind.FLOAT: "number",
    PrimitiveKind.DOUBLE: "number",
    PrimitiveKind.BOOLEAN: "boolean",
}


# Native TS renderings for retained string formats (plan 03). ``uuid`` /
# ``binary`` are documented string typealiases (shared support files);
# only ``date-time`` changes the runtime representation.
_FORMAT_TO_TS: dict[str, str] = {
    "date-time": "Date",
    "uuid": "Uuid",
    "binary": "Base64Data",
}


def _ts_type_with_enums(
    ftype: FieldType,
    enum_names: set[str],
    *,
    format_native: bool = False,
) -> str:
    """Render a :class:`FieldType` as a TypeScript type expression.

    Optional/nullable is signaled by the parent (``?:`` in field
    declaration) — this function only returns the bare type.
    """
    if ftype.is_primitive:
        base = _PRIMITIVE_TO_TS[ftype.primitive]
        if format_native and ftype.format is not None:
            base = _FORMAT_TO_TS.get(ftype.format, base)
        return base
    if (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enum_names:
        return ftype.ref_name
    if ftype.is_object_ref or ftype.is_enum_ref:
        return f"{ftype.ref_name}Dto"
    if ftype.is_array:
        inner = (
            _ts_type_with_enums(ftype.element, enum_names, format_native=format_native)
            if ftype.element
            else "string"
        )
        return f"{inner}[]"
    if ftype.is_map:
        inner = (
            _ts_type_with_enums(ftype.element, enum_names, format_native=format_native)
            if ftype.element
            else "string"
        )
        return f"Record<string, {inner}>"
    return "string"


# --------------------------------------------------------------------------- #
# format-aware mapping helpers (plan 2026-07-24-v1-unsupported/03)
# --------------------------------------------------------------------------- #


_TS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _ts_is_identifier(name: str) -> bool:
    return bool(_TS_IDENTIFIER_RE.match(name))


def _ts_obj_key(wire_name: str) -> str:
    """Object-literal / interface key for a wire name (quoted when needed)."""
    if _ts_is_identifier(wire_name):
        return wire_name
    escaped = wire_name.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def web_affected_names(doc: SwaggerDocument) -> frozenset[str]:
    """Schemas / unions whose DTO runtime shape differs from the wire JSON.

    A schema is *affected* when it (transitively, through refs / arrays /
    maps / oneOf variants / union variants) contains a ``date-time``
    field — i.e. its parsed DTO holds ``Date`` objects somewhere, so raw
    ``JSON.parse`` output must not be cast to it. Enum refs never affect.
    """
    enum_names = {e.name for e in doc.enums}
    refs_by_name: dict[str, set[str]] = {}
    affected: set[str] = set()
    for schema in doc.schemas:
        if "date-time" in schema_string_formats(schema):
            affected.add(schema.name)
        refs_by_name[schema.name] = schema.referenced_schemas() - enum_names
    for union in doc.unions:
        refs_by_name[union.name] = union.referenced_schemas()
    changed = True
    while changed:
        changed = False
        for name, refs in refs_by_name.items():
            if name not in affected and refs & affected:
                affected.add(name)
                changed = True
    return frozenset(affected)


_TS_PARSE_ISO_DATE_HELPER: tuple[str, ...] = (
    "",
    "const parseIsoDate = (raw: string): Date => {",
    "  const parsed = new Date(raw);",
    "  if (Number.isNaN(parsed.getTime())) {",
    "    throw new Error(`Invalid ISO 8601 date-time: ${raw}`);",
    "  }",
    "  return parsed;",
    "};",
)


def _ts_needs_conversion(ftype: FieldType, affected: frozenset[str] | set[str]) -> bool:
    """True when wire value ≠ DTO value for this type (Date somewhere)."""
    if ftype.is_primitive:
        return ftype.format == "date-time"
    if ftype.is_object_ref:
        return ftype.ref_name in affected
    if ftype.element is not None:
        return _ts_needs_conversion(ftype.element, affected)
    return False


def _ts_wire_type(
    ftype: FieldType,
    enum_names: set[str],
    affected: frozenset[str] | set[str],
) -> str:
    """Raw JSON type expression: Dates stay strings, affected refs → Wire."""
    if ftype.is_object_ref and ftype.ref_name in affected:
        return f"{ftype.ref_name}Wire"
    if ftype.is_array:
        inner = (
            _ts_wire_type(ftype.element, enum_names, affected)
            if ftype.element
            else "string"
        )
        return f"{inner}[]"
    if ftype.is_map:
        inner = (
            _ts_wire_type(ftype.element, enum_names, affected)
            if ftype.element
            else "string"
        )
        return f"Record<string, {inner}>"
    # Primitives (incl. date-time → string) and unaffected refs match the
    # flag-off rendering exactly.
    return _ts_type_with_enums(ftype, enum_names)


def _ts_parse_expr(
    ftype: FieldType,
    src: str,
    affected: frozenset[str] | set[str],
    *,
    depth: int,
) -> str:
    """Wire → DTO conversion expression for a non-null value of *ftype*."""
    if ftype.is_primitive and ftype.format == "date-time":
        return f"parseIsoDate({src})"
    if ftype.is_object_ref and ftype.ref_name in affected:
        return f"parse{ftype.ref_name}Dto({src})"
    if ftype.is_array and ftype.element is not None:
        v = f"v{depth}"
        inner = _ts_parse_expr(ftype.element, v, affected, depth=depth + 1)
        return f"{src}.map(({v}) => {inner})"
    if ftype.is_map and ftype.element is not None:
        k, v = f"k{depth}", f"v{depth}"
        inner = _ts_parse_expr(ftype.element, v, affected, depth=depth + 1)
        return (
            f"Object.fromEntries(Object.entries({src}).map("
            f"([{k}, {v}]) => [{k}, {inner}]))"
        )
    return src


def _ts_serialize_expr(
    ftype: FieldType,
    src: str,
    affected: frozenset[str] | set[str],
    *,
    depth: int,
) -> str:
    """DTO → wire conversion expression for a non-null value of *ftype*."""
    if ftype.is_primitive and ftype.format == "date-time":
        return f"{src}.toISOString()"
    if ftype.is_object_ref and ftype.ref_name in affected:
        return f"serialize{ftype.ref_name}Dto({src})"
    if ftype.is_array and ftype.element is not None:
        v = f"v{depth}"
        inner = _ts_serialize_expr(ftype.element, v, affected, depth=depth + 1)
        return f"{src}.map(({v}) => {inner})"
    if ftype.is_map and ftype.element is not None:
        k, v = f"k{depth}", f"v{depth}"
        inner = _ts_serialize_expr(ftype.element, v, affected, depth=depth + 1)
        return (
            f"Object.fromEntries(Object.entries({src}).map("
            f"([{k}, {v}]) => [{k}, {inner}]))"
        )
    return src


# --------------------------------------------------------------------------- #
# Non-object wrapper helpers
# --------------------------------------------------------------------------- #


def _generate_web_wrapper_dto(
    schema: SchemaDef,
    doc: SwaggerDocument,
    header: str,
    footer: str,
    enum_names: set[str],
    *,
    format_native: bool = False,
    affected: frozenset[str] | set[str] = frozenset(),
) -> str:
    """Render a wrapper DTO as an ``export type`` alias.

    Structural typing in TypeScript makes the alias indistinguishable
    from the underlying primitive at every call site (so a ``ThinkingDto``
    in a discriminated union or repository return type just acts as a
    string at runtime). Date-affected wrappers additionally get a
    ``{Name}Wire`` alias + parse/serialize helpers (plan 03).
    """
    is_affected = format_native and schema.name in affected
    wrapped = schema.wrapped_type
    wrapped_type_str = (
        _ts_type_with_enums(wrapped, enum_names, format_native=format_native)
        if wrapped is not None
        else "unknown"
    )

    refs = schema.referenced_schemas()
    lines: list[str] = []
    for name in sorted(refs):
        if name in enum_names:
            lines.append(f'import type {{ {name} }} from "./{name}";')
        elif is_affected and name in affected:
            lines.append(
                f'import {{ parse{name}Dto, serialize{name}Dto }} from "./{name}Dto";'
            )
            lines.append(
                f'import type {{ {name}Dto, {name}Wire }} from "./{name}Dto";'
            )
        else:
            lines.append(f'import type {{ {name}Dto }} from "./{name}Dto";')
    if format_native and wrapped is not None:
        used = collect_string_formats(wrapped)
        if "uuid" in used:
            lines.append('import type { Uuid } from "./Uuid";')
        if "binary" in used:
            lines.append('import type { Base64Data } from "./Base64Data";')
    if lines:
        lines.append("")
    if schema.description:
        lines.extend(_jsdoc_lines(schema.description))
    if schema.deprecated:
        lines.append("/** @deprecated */")
    lines.append(f"export type {schema.name}Dto = {wrapped_type_str};")

    if is_affected and wrapped is not None:
        name = schema.name
        if "date-time" in collect_string_formats(wrapped):
            lines.extend(_TS_PARSE_ISO_DATE_HELPER)
        wire_type = _ts_wire_type(wrapped, enum_names, affected)
        lines.append("")
        lines.append(
            f"// Raw JSON shape — parse{name}Dto / serialize{name}Dto convert Date values."
        )
        lines.append(f"export type {name}Wire = {wire_type};")
        lines.append("")
        parse_expr = _ts_parse_expr(wrapped, "wire", affected, depth=0)
        lines.append(
            f"export const parse{name}Dto = (wire: {name}Wire): {name}Dto => {parse_expr};"
        )
        lines.append("")
        serialize_expr = _ts_serialize_expr(wrapped, "value", affected, depth=0)
        lines.append(
            f"export const serialize{name}Dto = (value: {name}Dto): {name}Wire => {serialize_expr};"
        )

    body = "\n".join(lines)
    return f"{header}\n\n{body}\n\n{footer}\n"


# --------------------------------------------------------------------------- #
# oneOf / discriminator helpers
# --------------------------------------------------------------------------- #


def _ts_oneof_union_name(schema: SchemaDef, field: FieldDef) -> str:
    """``StreamEvent`` + ``content`` → ``StreamEventContent``."""
    return f"{schema.name}{snake_to_pascal(field.wire_name)}"


def _ts_oneof_kind_literal(discriminator_value: str) -> str:
    """Discriminator value as a quoted TS string literal for the ``kind`` tag."""
    escaped = discriminator_value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _emit_ts_oneof_union(schema: SchemaDef, field: FieldDef, one_of: OneOfRef) -> list[str]:
    """Emit ``export type StreamEventContent = { kind: "..."; data: ... } | ...``."""
    name = _ts_oneof_union_name(schema, field)
    lines: list[str] = [f"export type {name} ="]
    for variant in one_of.variants:
        kind = _ts_oneof_kind_literal(variant.discriminator_value)
        lines.append(f"  | {{ kind: {kind}; data: {variant.ref_name}Dto }}")
    lines.append('  | { kind: "unknown" };')
    return lines


def _emit_ts_oneof_helpers(
    schema: SchemaDef,
    enum_names: set[str],
    case_convention: str,
) -> list[str]:
    """Emit ``parse{Name}Dto`` / ``serialize{Name}Dto`` discriminator dispatchers.

    Naming follows the existing wire-skew helper convention so consumers
    have a single entry point regardless of whether the helper exists
    because of casing or polymorphism.

    The helpers assume wire-format names (snake_case) on the input/output
    side. camelCase mode + oneOf is documented as a v2 follow-up — the
    plain dispatch is correct for snake_case wire; user can wrap if
    additional case conversion is required.
    """
    name = schema.name
    parse_fn = f"parse{name}Dto"
    ser_fn = f"serialize{name}Dto"

    # Build per-field handling. For non-oneOf fields we straight-pass the
    # value through (caller is responsible for any per-field shape
    # conversion). For oneOf fields we wrap in the discriminated union.
    disc_assignments_parse: list[str] = []
    disc_assignments_serialize: list[str] = []

    out: list[str] = ["", f"export const {parse_fn} = (wire: any): {name}Dto => {{"]
    # Build the object literal field by field.
    for f in schema.fields:
        wire_name = f.wire_name
        prop_name = wire_name  # case convention applied only to camel mode (skipped here)
        if f.type.is_one_of_ref and f.type.one_of is not None:
            union_name = _ts_oneof_union_name(schema, f)
            disc_field = next(
                (g for g in schema.fields if g.wire_name == f.type.one_of.discriminator_property),
                None,
            )
            disc_wire = disc_field.wire_name if disc_field else f.type.one_of.discriminator_property
            out.append(f"  let {prop_name}: {union_name};")
            out.append(f"  switch (wire[{_ts_oneof_kind_literal(disc_wire)}]) {{")
            for variant in f.type.one_of.variants:
                kind = _ts_oneof_kind_literal(variant.discriminator_value)
                out.append(f"    case {kind}:")
                out.append(
                    f"      {prop_name} = {{ kind: {kind}, "
                    f"data: wire[{_ts_oneof_kind_literal(wire_name)}] as {variant.ref_name}Dto }};"
                )
                out.append("      break;")
            out.append("    default:")
            out.append(f'      {prop_name} = {{ kind: "unknown" }};')
            out.append("  }")
    # Build the return object.
    return_parts: list[str] = []
    for f in schema.fields:
        wire_name = f.wire_name
        if f.type.is_one_of_ref:
            return_parts.append(f"{wire_name}: {wire_name}")
        else:
            return_parts.append(f"{wire_name}: wire[{_ts_oneof_kind_literal(wire_name)}]")
    out.append("  return { " + ", ".join(return_parts) + " };")
    out.append("};")

    # serialize: walk fields, unwrap oneOf variant back to raw data
    out.append("")
    out.append(f"export const {ser_fn} = (model: {name}Dto): any => {{")
    obj_parts: list[str] = []
    for f in schema.fields:
        wire_name = f.wire_name
        prop_name = wire_name
        if f.type.is_one_of_ref and f.type.one_of is not None:
            out.append(f"  let {prop_name}: unknown;")
            out.append(f"  switch (model.{wire_name}.kind) {{")
            for variant in f.type.one_of.variants:
                kind = _ts_oneof_kind_literal(variant.discriminator_value)
                out.append(f"    case {kind}:")
                out.append(f"      {prop_name} = model.{wire_name}.data;")
                out.append("      break;")
            out.append('    case "unknown":')
            out.append(f"      {prop_name} = null;")
            out.append("      break;")
            out.append("  }")
            obj_parts.append(f"[{_ts_oneof_kind_literal(wire_name)}]: {prop_name}")
        else:
            obj_parts.append(f"[{_ts_oneof_kind_literal(wire_name)}]: model.{wire_name}")
    out.append("  return { " + ", ".join(obj_parts) + " };")
    out.append("};")
    return out
