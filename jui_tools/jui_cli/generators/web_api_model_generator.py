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

from dataclasses import dataclass
from pathlib import Path

from ..core.generated_marker import comment_footer, comment_header
from ..core.impl_updater import atomic_write_text
from ..core.openapi_naming import factory_name, snake_to_camel
from ..core.schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    PrimitiveKind,
    SchemaDef,
    SwaggerDocument,
)


CASE_CONVENTIONS = ("snake_case", "camelCase")


@dataclass(frozen=True)
class WebApiPlatformConfig:
    """Resolved ``api.platforms.web`` config (with defaults applied)."""

    sources_root: Path           # absolute, e.g. <project>/<web.root>/src
    model_dir: str = "models"    # relative to sources_root
    dto_subdir: str = "generated"
    case_convention: str = "snake_case"


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

    # ---------------------------- emit DTO --------------------------- #

    def generate_dto_source(self, schema: SchemaDef, doc: SwaggerDocument) -> str:
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#{schema.source_pointer.rsplit('#', 1)[-1]}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        enum_names = {e.name for e in doc.enums}

        lines: list[str] = []
        # Import enum / nested DTO refs that appear in this schema.
        for imp in self._collect_imports(schema, enum_names, doc):
            lines.append(imp)
        if lines:
            lines.append("")
        if schema.description:
            lines.extend(_jsdoc_lines(schema.description))
        if schema.deprecated:
            lines.append("/** @deprecated */")
        if schema.is_strict:
            lines.append("// additionalProperties: false (strict — extra fields are dropped on decode)")
        lines.append(f"export interface {schema.name}Dto {{")
        for f in schema.fields:
            lines.extend(self._dto_field_lines(f, enum_names))
        lines.append("}")

        # camelCase mode also needs parse/serialize helpers since the wire
        # format is snake_case.
        if self._config.case_convention == "camelCase" and self._has_wire_camel_skew(schema):
            lines.extend(self._parse_serialize_helpers(schema, enum_names))

        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    def _collect_imports(
        self,
        schema: SchemaDef,
        enum_names: set[str],
        doc: SwaggerDocument,
    ) -> list[str]:
        """Return ``import`` lines for every other DTO/enum this schema references."""
        refs = schema.referenced_schemas() - {schema.name}
        if not refs:
            return []
        lines: list[str] = []
        for name in sorted(refs):
            if name in enum_names:
                lines.append(f'import type {{ {name} }} from "./{name}";')
            else:
                lines.append(f'import type {{ {name}Dto }} from "./{name}Dto";')
        return lines

    def _dto_field_lines(self, field: FieldDef, enum_names: set[str]) -> list[str]:
        out: list[str] = []
        if field.description:
            out.extend(f"  {ln}" for ln in _jsdoc_lines(field.description))
        if field.deprecated:
            out.append("  /** @deprecated */")
        type_str = _ts_type_with_enums(field.type, enum_names)
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
        date parsing (those are user responsibility per the v3 plan
        "filter native conversion through Domain proxies" principle).
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


def _ts_type_with_enums(ftype: FieldType, enum_names: set[str]) -> str:
    """Render a :class:`FieldType` as a TypeScript type expression.

    Optional/nullable is signaled by the parent (``?:`` in field
    declaration) — this function only returns the bare type.
    """
    if ftype.is_primitive:
        return _PRIMITIVE_TO_TS[ftype.primitive]
    if (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enum_names:
        return ftype.ref_name
    if ftype.is_object_ref or ftype.is_enum_ref:
        return f"{ftype.ref_name}Dto"
    if ftype.is_array:
        inner = _ts_type_with_enums(ftype.element, enum_names) if ftype.element else "string"
        return f"{inner}[]"
    if ftype.is_map:
        inner = _ts_type_with_enums(ftype.element, enum_names) if ftype.element else "string"
        return f"Record<string, {inner}>"
    return "string"
