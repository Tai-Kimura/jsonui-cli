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
from ..core.openapi_naming import (
    escape_keyword,
    resolve_enum_case_for_default,
    snake_to_camel,
    snake_to_pascal,
)
from ..core.schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
    OneOfRef,
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

        enums_by_name = {e.name: e for e in doc.enums}
        enum_names = set(enums_by_name)

        # Hashable is always declared so consumers can put DTOs in `Set` /
        # `Dictionary` keys without having to write extensions. When the
        # schema has a field Swift can't auto-synthesize on (map, array of
        # map, etc.) we emit an explicit ``hash(into:)`` body that hashes
        # the synthesis-safe subset — see ``_emit_hash_body`` below.
        # Equatable / Sendable still respect their own flags; only
        # Hashable is forced on.
        conformances = ["Codable"]
        if schema.is_sendable:
            conformances.append("Sendable")
        if schema.is_equatable:
            conformances.append("Equatable")
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

        has_oneof = any(f.type.is_one_of_ref for f in schema.fields)

        # Stored properties (one per field).
        for f in schema.fields:
            body_lines.extend(_dto_field_lines(f, enum_names, enums_by_name))

        # Nested ``enum {Field}: Codable`` declarations — one per oneOf field.
        # Variants live alongside the parent type so consumers refer to them as
        # ``StreamEventDto.Content.conversationId(...)``.
        for f in schema.fields:
            if f.type.is_one_of_ref and f.type.one_of is not None:
                body_lines.extend(_emit_swift_oneof_nested_enum(f, f.type.one_of))

        # Memberwise initializer — Swift suppresses the auto-synthesized one
        # once we write a custom ``init(from decoder:)`` below, so explicitly
        # restore it for consumers who construct DTOs at call sites.
        if has_oneof:
            body_lines.extend(_emit_swift_memberwise_init(schema, enum_names))

        # Custom CodingKeys when at least one field is renamed, OR always when
        # the schema has a oneOf field (the custom ``init(from:)`` needs the
        # keys to dispatch).
        if has_oneof or any(_swift_property_name(f) != f.wire_name for f in schema.fields):
            body_lines.append("")
            body_lines.append("    enum CodingKeys: String, CodingKey {")
            for f in schema.fields:
                prop = _swift_property_name(f)
                if prop == f.wire_name:
                    body_lines.append(f"        case {prop}")
                else:
                    body_lines.append(f'        case {prop} = "{f.wire_name}"')
            body_lines.append("    }")

        # Custom ``init(from:)`` + ``encode(to:)`` for oneOf-bearing schemas:
        # decoder reads the sibling discriminator first, then dispatches into
        # the matching variant decode; encoder is symmetric.
        if has_oneof:
            body_lines.extend(_emit_swift_oneof_init_from_decoder(schema, enum_names))
            body_lines.extend(_emit_swift_oneof_encode_to_encoder(schema, enum_names))

        # Explicit ``hash(into:)`` when Swift auto-synthesis would fail —
        # currently triggered by any map / array-of-map / nested-map field.
        if _schema_needs_explicit_hash(schema):
            body_lines.extend(_emit_hash_body_lines(schema))

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


def _dto_field_lines(
    field: FieldDef,
    enum_names: set[str],
    enums_by_name: dict[str, EnumDef],
) -> list[str]:
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
    if field.type.is_one_of_ref:
        type_str = _swift_oneof_field_type(field)
    else:
        type_str = _swift_type_with_enums(field.type, enum_names)
    name = _swift_property_name(field)
    default = _swift_default_literal(field, type_str, enums_by_name)
    line = f"    let {name}: {type_str}"
    if default is not None:
        line += f" = {default}"
    out.append(line)
    return out


def _swift_property_name(field: FieldDef) -> str:
    """Wire ``snake_case`` → Swift ``camelCase`` + reserved-word escape."""
    return escape_keyword(snake_to_camel(field.wire_name), language="swift")


def _hash_safe(ftype: FieldType) -> bool:
    """True when Swift can hash a field of this type without help.

    Primitives, enums, object refs and oneOf union refs are safe — object
    refs because every DTO now declares ``Hashable`` unconditionally (see
    plan ``2026-05-27-ios-dto-hashable-explicit-body.md``), oneOf because
    the nested enum we emit conforms to Hashable through its associated
    DTO values. Arrays inherit safety from their element type. Maps
    short-circuit to False — the auto-synthesis path bails on ``[K: V]``
    even when both K and V are Hashable in many real-world Swift compiler
    versions, so we keep the rule conservative.
    """
    if ftype.is_primitive:
        return True
    if ftype.is_enum_ref:
        return True
    if ftype.is_object_ref:
        return True
    if ftype.is_one_of_ref:
        return True
    if ftype.is_map:
        return False
    if ftype.is_array and ftype.element is not None:
        return _hash_safe(ftype.element)
    return False


def _schema_needs_explicit_hash(schema: SchemaDef) -> bool:
    """True iff at least one field requires us to hand-write ``hash(into:)``."""
    return any(not _hash_safe(f.type) for f in schema.fields)


def _emit_hash_body_lines(schema: SchemaDef) -> list[str]:
    """Emit the explicit ``hash(into:)`` body for *schema*.

    Hash-safe fields are ``hasher.combine``'d in declaration order. Unsafe
    fields are listed in a trailing comment so a reader can tell at a
    glance which fields were dropped from the hash and why. The Equatable
    auto-synthesis still considers every field, so ``a == b ⟹ hash(a) ==
    hash(b)`` holds (if all fields equal, the safe subset is also equal,
    so hashes match). The reverse — ``hash(a) == hash(b) ⟹ a == b`` — is
    never required by the Hashable contract.
    """
    safe: list[str] = []
    omitted: list[str] = []
    for f in schema.fields:
        name = _swift_property_name(f)
        if _hash_safe(f.type):
            safe.append(name)
        else:
            omitted.append(name)

    lines: list[str] = ["", "    func hash(into hasher: inout Hasher) {"]
    for name in safe:
        lines.append(f"        hasher.combine({name})")
    if omitted:
        lines.append(
            "        // Omitted from hash (synthesis-incompatible types): "
            + ", ".join(omitted)
        )
    lines.append("    }")
    return lines


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


def _swift_default_literal(
    field: FieldDef,
    type_str: str,
    enums_by_name: dict[str, EnumDef],
) -> str | None:
    """Render OpenAPI ``default`` to a Swift literal, or None if absent.

    Enum-typed fields emit ``EnumName.caseName`` (or the keyword-escaped
    form) instead of a raw string / integer literal. Required to compile
    when a swagger schema uses ``allOf: [$ref: <enum>] + default: <value>``
    on a Swift enum without ``ExpressibleByStringLiteral``.

    Conservative: only emit literals for scalar defaults whose JSON shape
    maps cleanly to Swift. Complex defaults (objects / arrays of objects)
    are skipped — the decoder will fill them.
    """
    if not field.has_default:
        return None
    value = field.default
    if value is None:
        return "nil"

    # Enum-typed field → EnumName.caseName.
    ftype = field.type
    if (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enums_by_name:
        enum = enums_by_name[ftype.ref_name]
        case_name = resolve_enum_case_for_default(enum, value)
        if case_name is None:
            return None
        ident = escape_keyword(_swift_case_name(case_name), language="swift")
        return f"{enum.name}.{ident}"

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


# --------------------------------------------------------------------------- #
# oneOf / discriminator helpers
# --------------------------------------------------------------------------- #


def _swift_oneof_nested_type_name(field: FieldDef) -> str:
    """Nested enum name for a oneOf field — e.g. ``content`` → ``Content``."""
    return snake_to_pascal(field.wire_name)


def _swift_oneof_field_type(field: FieldDef) -> str:
    """Render a oneOf field's type as a reference to the nested enum."""
    base = _swift_oneof_nested_type_name(field)
    return f"{base}?" if field.type.nullable else base


def _swift_oneof_case_ident(discriminator_value: str) -> str:
    """``conversation_id`` → ``conversationId`` (snake → camel + escape)."""
    return escape_keyword(snake_to_camel(discriminator_value), language="swift")


def _emit_swift_oneof_nested_enum(field: FieldDef, one_of: OneOfRef) -> list[str]:
    """Emit ``enum Content: Codable, Sendable, Equatable, Hashable { ... }``.

    Each variant carries the corresponding DTO type as associated value;
    an ``unknown`` case provides forward-compatibility when the server
    introduces a new discriminator value before the client is rebuilt.
    """
    type_name = _swift_oneof_nested_type_name(field)
    lines: list[str] = [
        "",
        f"    enum {type_name}: Codable, Sendable, Equatable, Hashable {{",
    ]
    for variant in one_of.variants:
        case = _swift_oneof_case_ident(variant.discriminator_value)
        lines.append(f"        case {case}({variant.ref_name}Dto)")
    lines.append("        case unknown")
    lines.append("    }")
    return lines


def _emit_swift_memberwise_init(
    schema: SchemaDef,
    enum_names: set[str],
) -> list[str]:
    """Emit a memberwise ``init`` so consumers can build oneOf-bearing DTOs.

    Swift suppresses the auto-synthesized memberwise initializer once a
    custom ``init(from decoder:)`` is declared in the same type, so we
    have to re-emit it manually.
    """
    params: list[str] = []
    for f in schema.fields:
        name = _swift_property_name(f)
        if f.type.is_one_of_ref:
            type_str = _swift_oneof_field_type(f)
        else:
            type_str = _swift_type_with_enums(f.type, enum_names)
        params.append(f"{name}: {type_str}")
    lines: list[str] = ["", f"    init({', '.join(params)}) {{"]
    for f in schema.fields:
        name = _swift_property_name(f)
        lines.append(f"        self.{name} = {name}")
    lines.append("    }")
    return lines


def _emit_swift_oneof_init_from_decoder(
    schema: SchemaDef,
    enum_names: set[str],
) -> list[str]:
    """Emit ``init(from decoder:)`` that dispatches each oneOf field on its
    discriminator sibling's wire value."""
    lines: list[str] = ["", "    init(from decoder: Decoder) throws {"]
    lines.append("        let container = try decoder.container(keyedBy: CodingKeys.self)")

    # Decode non-oneOf fields first — they're plain Codable.
    for f in schema.fields:
        if f.type.is_one_of_ref:
            continue
        name = _swift_property_name(f)
        if f.type.is_one_of_ref:
            continue
        type_str = _swift_type_with_enums(f.type, enum_names)
        bare = type_str.rstrip("?")
        if f.type.nullable:
            lines.append(
                f"        self.{name} = try container.decodeIfPresent({bare}.self, forKey: .{name})"
            )
        else:
            lines.append(
                f"        self.{name} = try container.decode({bare}.self, forKey: .{name})"
            )

    # Dispatch each oneOf field.
    for f in schema.fields:
        if not f.type.is_one_of_ref or f.type.one_of is None:
            continue
        prop = _swift_property_name(f)
        type_name = _swift_oneof_nested_type_name(f)
        disc_field = _find_field_by_wire_name(schema, f.type.one_of.discriminator_property)
        disc_prop = _swift_property_name(disc_field) if disc_field else f.type.one_of.discriminator_property
        lines.append(f"        switch self.{disc_prop} {{")
        for variant in f.type.one_of.variants:
            case = _swift_oneof_case_ident(variant.discriminator_value)
            decode_call = (
                f"try container.decode({variant.ref_name}Dto.self, forKey: .{prop})"
                if not f.type.nullable
                else f"try container.decodeIfPresent({variant.ref_name}Dto.self, forKey: .{prop}) ?? "
                     f"{variant.ref_name}Dto()"
            )
            lines.append(f'        case "{variant.discriminator_value}":')
            lines.append(f"            self.{prop} = .{case}({decode_call})")
        lines.append("        default:")
        lines.append(f"            self.{prop} = .unknown")
        lines.append("        }")
    lines.append("    }")
    return lines


def _emit_swift_oneof_encode_to_encoder(
    schema: SchemaDef,
    enum_names: set[str],
) -> list[str]:
    """Emit the symmetric ``encode(to:)`` for oneOf-bearing schemas."""
    lines: list[str] = ["", "    func encode(to encoder: Encoder) throws {"]
    lines.append("        var container = encoder.container(keyedBy: CodingKeys.self)")

    for f in schema.fields:
        name = _swift_property_name(f)
        if f.type.is_one_of_ref and f.type.one_of is not None:
            lines.append(f"        switch self.{name} {{")
            for variant in f.type.one_of.variants:
                case = _swift_oneof_case_ident(variant.discriminator_value)
                lines.append(
                    f"        case .{case}(let value): "
                    f"try container.encode(value, forKey: .{name})"
                )
            lines.append(f"        case .unknown: try container.encodeNil(forKey: .{name})")
            lines.append("        }")
            continue
        if f.type.nullable:
            lines.append(
                f"        try container.encodeIfPresent(self.{name}, forKey: .{name})"
            )
        else:
            lines.append(
                f"        try container.encode(self.{name}, forKey: .{name})"
            )
    lines.append("    }")
    return lines


def _find_field_by_wire_name(schema: SchemaDef, wire_name: str) -> FieldDef | None:
    for f in schema.fields:
        if f.wire_name == wire_name:
            return f
    return None
