"""iOS API model emitter — Swift DTO (`@generated`) + Domain scaffold.

Consumes :class:`SchemaIR` from :mod:`openapi_loader` and emits per-schema
output. The DTO file is always rewritten on every build; the Domain
scaffold is written only when it does not already exist.

Layout under ``<ios_root>/<sources>/<model_dir>/``:

::

    Model/
      Generated/
        UserDto.swift       (DTO, @generated)
        AuthProvider.swift  (enum, @generated)
      User.swift            (Domain scaffold, user-owned after first emit)

See plan §2.2, §3.2, §4 for the full contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.generated_marker import comment_footer, comment_header
from ..core.impl_updater import atomic_write_text
from ..core.openapi_naming import escape_keyword, snake_to_camel
from ..core.schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    PrimitiveKind,
    SchemaDef,
    SwaggerDocument,
)


@dataclass(frozen=True)
class IosApiPlatformConfig:
    """Resolved ``api.platforms.ios`` config (with defaults applied).

    Carried through the generator so callers don't have to pass paths
    around piecewise.
    """

    sources_root: Path  # absolute, e.g. <project>/<ios.root>/<sources>
    model_dir: str = "Model"          # relative to sources_root
    dto_subdir: str = "Generated"     # relative to model_dir


class IosApiModelGenerator:
    """Render Swift DTO + Domain scaffold files for a swagger document.

    The generator is **pure**: :meth:`generate_dto_source` /
    :meth:`generate_domain_source` / :meth:`generate_enum_source` return
    strings. :meth:`write` does disk I/O and is the only side-effecting
    method.

    Caller responsibilities:

    - Loop over each :class:`SwaggerDocument` and feed every schema/enum
      to ``generate_*``
    - Decide whether the Domain scaffold file already exists (the
      generator does NOT touch existing scaffolds)
    """

    GENERATOR_NAME = "jui build (api model)"

    def __init__(self, config: IosApiPlatformConfig):
        self._config = config

    # ----------------------------- paths ----------------------------- #

    def dto_path(self, schema_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / self._config.dto_subdir
            / f"{schema_name}Dto.swift"
        )

    def enum_path(self, enum_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / self._config.dto_subdir
            / f"{enum_name}.swift"
        )

    def domain_path(self, schema_name: str) -> Path:
        return (
            self._config.sources_root
            / self._config.model_dir
            / f"{schema_name}.swift"
        )

    # ---------------------------- emit DTO --------------------------- #

    def generate_dto_source(
        self,
        schema: SchemaDef,
        doc: SwaggerDocument,
    ) -> str:
        """Return the Swift source for the DTO file (with @generated banner)."""
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#{schema.source_pointer.rsplit('#', 1)[-1]}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()

        enum_names = {e.name for e in doc.enums}

        conformances = ["Codable"]
        if schema.is_sendable:
            conformances.append("Sendable")
        if schema.is_equatable:
            conformances.append("Equatable")
        if schema.is_hashable:
            conformances.append("Hashable")

        body_lines: list[str] = []
        if schema.description:
            for ln in _doc_comment_lines(schema.description):
                body_lines.append(ln)
        if schema.deprecated:
            body_lines.append("@available(*, deprecated)")
        if schema.is_strict:
            body_lines.append("// additionalProperties: false (strict — extra fields are dropped on decode)")

        body_lines.append(
            f"struct {schema.name}Dto: {', '.join(conformances)} {{"
        )

        # Stored properties (one per field).
        for f in schema.fields:
            body_lines.extend(_dto_field_lines(f, enum_names))

        # Custom CodingKeys when at least one field is renamed.
        if any(_swift_property_name(f) != f.wire_name for f in schema.fields):
            body_lines.append("")
            body_lines.append("    enum CodingKeys: String, CodingKey {")
            for f in schema.fields:
                prop = _swift_property_name(f)
                if prop == f.wire_name:
                    body_lines.append(f"        case {prop}")
                else:
                    body_lines.append(f'        case {prop} = "{f.wire_name}"')
            body_lines.append("    }")

        body_lines.append("}")

        body = "\n".join(body_lines)
        return f"{header}\nimport Foundation\n\n{body}\n\n{footer}\n"

    # ---------------------------- emit enum -------------------------- #

    def generate_enum_source(self, enum: EnumDef, doc: SwaggerDocument) -> str:
        """Return the Swift source for a standalone enum schema."""
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#/components/schemas/{enum.name}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()

        if enum.kind == PrimitiveKind.STRING:
            raw_type = "String"
            value_pairs = list(zip(enum.case_names, enum.string_values))
            lines = [f"enum {enum.name}: {raw_type}, Codable, CaseIterable, Sendable {{"]
            for case_name, raw_value in value_pairs:
                escaped = escape_keyword(_swift_case_name(case_name), language="swift")
                if escaped == raw_value or escaped.strip("`") == raw_value:
                    lines.append(f"    case {escaped}")
                else:
                    lines.append(f'    case {escaped} = "{raw_value}"')
            lines.append("}")
        else:  # INTEGER
            raw_type = "Int"
            value_pairs_int = list(zip(enum.case_names, enum.integer_values))
            lines = [f"enum {enum.name}: {raw_type}, Codable, CaseIterable, Sendable {{"]
            for case_name, raw_int in value_pairs_int:
                escaped = escape_keyword(_swift_case_name(case_name), language="swift")
                lines.append(f"    case {escaped} = {raw_int}")
            lines.append("}")

        preamble: list[str] = []
        if enum.description:
            preamble.extend(_doc_comment_lines(enum.description))
        if enum.deprecated:
            preamble.append("@available(*, deprecated)")

        body = "\n".join(preamble + lines)
        return f"{header}\nimport Foundation\n\n{body}\n\n{footer}\n"

    # --------------------------- emit Domain ------------------------- #

    def generate_domain_source(self, schema: SchemaDef) -> str:
        """Return the Swift source for the initial Domain scaffold.

        This is the *first-time* output. Subsequent builds skip writing
        when the file already exists — user edits are preserved.
        """
        return (
            "import Foundation\n"
            "\n"
            f"struct {schema.name} {{\n"
            f"    let dto: {schema.name}Dto\n"
            "\n"
            f"    init(dto: {schema.name}Dto) {{\n"
            "        self.dto = dto\n"
            "    }\n"
            "\n"
            "    // User customization zone — add proxies, computed properties,\n"
            "    // stored properties, methods, and conversions here.\n"
            "}\n"
        )

    # ----------------------------- writes ---------------------------- #

    @dataclass(frozen=True)
    class WriteResult:
        """Summary of what changed on disk during a single ``write_*`` call."""

        path: Path
        wrote: bool
        skipped_existing: bool = False

    def write_dto(self, schema: SchemaDef, doc: SwaggerDocument) -> "IosApiModelGenerator.WriteResult":
        path = self.dto_path(schema.name)
        source = self.generate_dto_source(schema, doc)
        wrote = atomic_write_text(path, source)
        return self.WriteResult(path=path, wrote=wrote)

    def write_enum(self, enum: EnumDef, doc: SwaggerDocument) -> "IosApiModelGenerator.WriteResult":
        path = self.enum_path(enum.name)
        source = self.generate_enum_source(enum, doc)
        wrote = atomic_write_text(path, source)
        return self.WriteResult(path=path, wrote=wrote)

    def write_domain(self, schema: SchemaDef) -> "IosApiModelGenerator.WriteResult":
        path = self.domain_path(schema.name)
        if path.exists():
            return self.WriteResult(path=path, wrote=False, skipped_existing=True)
        source = self.generate_domain_source(schema)
        wrote = atomic_write_text(path, source)
        return self.WriteResult(path=path, wrote=wrote)

    # ---------------------------- discovery -------------------------- #

    def expected_dto_paths(self, doc: SwaggerDocument) -> set[Path]:
        """All DTO + enum paths that should exist for *doc*.

        Used by the orphan-prune step in ``build_cmd`` to remove DTOs
        whose source schema disappeared from the swagger.
        """
        paths = {self.dto_path(s.name) for s in doc.schemas}
        paths |= {self.enum_path(e.name) for e in doc.enums}
        return paths


# --------------------------------------------------------------------------- #
# Internals (module-level so they can be unit-tested without instantiating
# the generator class).
# --------------------------------------------------------------------------- #


def _relative_source(absolute_path: str) -> str:
    """Best-effort relative path for the comment-header ``Source:`` line.

    We don't have the project root in scope here; the build pipeline will
    fix this up when wiring the generator. For now return the basename so
    that snapshot tests don't depend on absolute paths.
    """
    return Path(absolute_path).name


def _doc_comment_lines(text: str) -> list[str]:
    """Convert *text* to Swift triple-slash doc comment lines."""
    out: list[str] = []
    for raw in text.splitlines() or [text]:
        out.append(f"/// {raw}")
    return out


def _dto_field_lines(field: FieldDef, enum_names: set[str]) -> list[str]:
    """Lines emitted for one DTO stored property.

    Includes:

    - leading blank line for readability when annotations are present
    - doc comment (if ``description`` set)
    - ``@available(*, deprecated)`` annotation if marked
    - ``let <name>: <Type>`` declaration with default literal when applicable
    """
    out: list[str] = []
    if field.description or field.deprecated:
        out.append("")  # blank line separator before annotated fields
    if field.description:
        for ln in _doc_comment_lines(field.description):
            out.append(f"    {ln}")
    if field.deprecated:
        out.append("    @available(*, deprecated)")
    type_str = _swift_type_with_enums(field.type, enum_names)
    name = _swift_property_name(field)
    default = _swift_default_literal(field, type_str)
    line = f"    let {name}: {type_str}"
    if default is not None:
        line += f" = {default}"
    out.append(line)
    return out


def _swift_property_name(field: FieldDef) -> str:
    """Wire ``snake_case`` → Swift ``camelCase`` + reserved-word escape."""
    return escape_keyword(snake_to_camel(field.wire_name), language="swift")


def _swift_case_name(case_name: str) -> str:
    """Enum case identifier; snake/kebab → camelCase + escape."""
    return snake_to_camel(case_name)


def _swift_type(ftype: FieldType) -> str:
    """Render a :class:`FieldType` as a Swift type expression."""
    if ftype.is_primitive:
        base = _PRIMITIVE_TO_SWIFT[ftype.primitive]
    elif ftype.is_object_ref or ftype.is_enum_ref:
        # Object refs become ``<Name>Dto``; enum refs become just ``<Name>``.
        # We don't have the enum/object disambiguation here without a doc-
        # wide lookup, so we default to the DTO suffix and let the call
        # site override when we know it's an enum. (Implemented below via
        # _swift_type_with_enums.)
        base = f"{ftype.ref_name}Dto"
    elif ftype.is_array:
        inner = _swift_type(ftype.element) if ftype.element else "String"
        base = f"[{inner}]"
    elif ftype.is_map:
        inner = _swift_type(ftype.element) if ftype.element else "String"
        base = f"[String: {inner}]"
    else:
        base = "String"
    return f"{base}?" if ftype.nullable else base


def _swift_type_with_enums(ftype: FieldType, enum_names: set[str]) -> str:
    """Like :func:`_swift_type` but treats enum refs without the ``Dto`` suffix.

    Used when the generator has access to the doc-level enum name set
    (most production callsites do).
    """
    if (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enum_names:
        base = ftype.ref_name
        return f"{base}?" if ftype.nullable else base
    if ftype.is_array and ftype.element:
        inner = _swift_type_with_enums(ftype.element, enum_names)
        rendered = f"[{inner}]"
        return f"{rendered}?" if ftype.nullable else rendered
    if ftype.is_map and ftype.element:
        inner = _swift_type_with_enums(ftype.element, enum_names)
        rendered = f"[String: {inner}]"
        return f"{rendered}?" if ftype.nullable else rendered
    return _swift_type(ftype)


def _swift_default_literal(field: FieldDef, type_str: str) -> str | None:
    """Render OpenAPI ``default`` to a Swift literal, or None if absent.

    Conservative: only emit literals for scalar defaults whose JSON shape
    maps cleanly to Swift. Complex defaults (objects / arrays of objects)
    are skipped — the decoder will fill them.
    """
    if not field.has_default:
        return None
    value = field.default
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Treat as string default — strip nothing, just quote.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list) and not value:
        return "[]"
    if isinstance(value, dict) and not value:
        return "[:]"
    return None


_PRIMITIVE_TO_SWIFT: dict[PrimitiveKind, str] = {
    PrimitiveKind.STRING: "String",
    PrimitiveKind.INTEGER_32: "Int32",
    PrimitiveKind.INTEGER_64: "Int64",
    PrimitiveKind.INTEGER: "Int",
    PrimitiveKind.FLOAT: "Float",
    PrimitiveKind.DOUBLE: "Double",
    PrimitiveKind.BOOLEAN: "Bool",
}
