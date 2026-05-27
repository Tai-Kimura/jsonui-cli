"""Android API model emitter — Kotlin DTO (`@generated`) + Domain scaffold.

Mirrors :mod:`ios_api_model_generator` for the Android platform with the
key v3 plan §3.2 addition: a configurable ``serializer`` choice between:

- ``"moshi"`` (default) — emits ``@JsonClass(generateAdapter = true)`` +
  ``@Json(name = "...")``; requires ksp/kapt + Moshi codegen dependency
- ``"kotlinx"`` — emits ``@Serializable`` + ``@SerialName("...")`` from
  ``kotlinx.serialization``; compiler plugin handles adapter generation
- ``"none"`` — emits a bare ``data class`` with no annotations; consumer is
  expected to configure their JSON parser (e.g. global ``ObjectMapper``
  snake_case strategy) to bridge wire ↔ field naming

Layout under ``<android_root>/<source_main>/<package_path>/``:

::

    model/
      generated/
        UserDto.kt          (DTO, @generated)
        AuthProvider.kt     (enum, @generated)
      User.kt               (Domain scaffold, user-owned after first emit)

See plan §2.2 Android section + §3.2 for the full contract.
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


SERIALIZER_CHOICES = ("moshi", "kotlinx", "none")


@dataclass(frozen=True)
class AndroidApiPlatformConfig:
    """Resolved ``api.platforms.android`` config (with defaults applied).

    The caller (typically ``api_model_sync.plan_android``) computes the
    **fully-qualified** package strings from the consumer's
    ``kjui.config.json#package_name`` + ``api.platforms.android.model_package``
    + ``dto_subpackage``. The generator stores them verbatim and just
    splits them on ``.`` when computing file paths under
    ``sources_root``.

    This shape replaces the v3 Phase 2 initial design which kept a
    separate ``package`` (base FQN) + ``model_subpackage`` and tried to
    join them inside the generator — that left no escape hatch for
    consumers who wanted ``model_package`` to be a full FQN (see bug
    ``jui-android-api-model-generator-wrong-source-dir-and-base-package``).
    """

    sources_root: Path           # absolute, e.g. <project>/<android.root>/<source_directory>/kotlin
    domain_package: str = "com.example.app.model"           # FQN for Domain wrapper files
    dto_package: str = "com.example.app.model.generated"    # FQN for DTO files (under domain_package)
    serializer: str = "moshi"


class AndroidApiModelGenerator:
    """Render Kotlin DTO + Domain scaffold files for a swagger document.

    Constructor validates the ``serializer`` choice against
    :data:`SERIALIZER_CHOICES` so a typo in ``jui.config.json`` surfaces
    immediately rather than at file write time.
    """

    GENERATOR_NAME = "jui build (api model)"

    def __init__(self, config: AndroidApiPlatformConfig):
        if config.serializer not in SERIALIZER_CHOICES:
            raise ValueError(
                f"Unknown Android serializer {config.serializer!r}; "
                f"expected one of {SERIALIZER_CHOICES}"
            )
        self._config = config

    # ----------------------------- paths ----------------------------- #

    def _package_to_path(self, full_package: str) -> Path:
        return self._config.sources_root / Path(*full_package.split("."))

    def _dto_package(self) -> str:
        return self._config.dto_package

    def _domain_package(self) -> str:
        return self._config.domain_package

    def dto_path(self, schema_name: str) -> Path:
        return self._package_to_path(self._dto_package()) / f"{schema_name}Dto.kt"

    def enum_path(self, enum_name: str) -> Path:
        return self._package_to_path(self._dto_package()) / f"{enum_name}.kt"

    def domain_path(self, schema_name: str) -> Path:
        return self._package_to_path(self._domain_package()) / f"{schema_name}.kt"

    # ---------------------------- emit DTO --------------------------- #

    def generate_dto_source(self, schema: SchemaDef, doc: SwaggerDocument) -> str:
        """Return the Kotlin source for the DTO file (with @generated banner)."""
        has_oneof = any(f.type.is_one_of_ref for f in schema.fields)
        if has_oneof and self._config.serializer != "kotlinx":
            raise ValueError(
                f"Schema {schema.name!r} uses oneOf + discriminator, which "
                f"requires the kotlinx serializer (current={self._config.serializer!r}). "
                f"Switch api.platforms.android.serializer to 'kotlinx' or wait "
                f"for v2 Moshi sealed-class codegen."
            )

        header = comment_header(
            source=_relative_source(doc.source_path) + f"#{schema.source_pointer.rsplit('#', 1)[-1]}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        enums_by_name = {e.name: e for e in doc.enums}
        enum_names = set(enums_by_name)

        lines: list[str] = []
        lines.append(f"package {self._dto_package()}")
        lines.append("")
        for imp in self._dto_imports(has_oneof=has_oneof):
            lines.append(imp)
        if self._dto_imports(has_oneof=has_oneof):
            lines.append("")
        if schema.description:
            lines.extend(_kdoc_lines(schema.description))
        if schema.deprecated:
            lines.append('@Deprecated("schema marked deprecated")')
        if schema.is_strict:
            lines.append("// additionalProperties: false (strict — extra fields are dropped on decode)")

        # Annotation line(s) at class scope (Moshi / kotlinx only).
        for ann in self._dto_class_annotations(schema=schema, has_oneof=has_oneof):
            lines.append(ann)
        lines.append(f"data class {schema.name}Dto(")
        last = len(schema.fields) - 1
        for i, f in enumerate(schema.fields):
            for ln in self._dto_field_lines(
                f, enum_names, enums_by_name, trailing_comma=(i < last) or True
            ):
                lines.append(ln)
        # Trailing comma after the last field is valid Kotlin and matches Moshi codegen output.
        if has_oneof:
            # Nested sealed class declarations + closing of the data class.
            lines.append(") {")
            for f in schema.fields:
                if f.type.is_one_of_ref and f.type.one_of is not None:
                    lines.extend(_emit_kotlin_oneof_sealed_class(f, f.type.one_of))
            lines.append("}")
            # Custom KSerializer object for the parent DTO (placed at file
            # scope, alongside the data class).
            lines.append("")
            lines.extend(
                _emit_kotlin_oneof_serializer(
                    schema, self._dto_package(), enum_names
                )
            )
        else:
            lines.append(")")
        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    def _dto_imports(self, *, has_oneof: bool = False) -> list[str]:
        if self._config.serializer == "moshi":
            return [
                "import com.squareup.moshi.Json",
                "import com.squareup.moshi.JsonClass",
            ]
        if self._config.serializer == "kotlinx":
            base = [
                "import kotlinx.serialization.SerialName",
                "import kotlinx.serialization.Serializable",
            ]
            if has_oneof:
                # oneOf parents drive a custom KSerializer that hand-rolls
                # the JSON parse/emit, so we pull in the Json* helpers and
                # the descriptor builders here.
                base.extend([
                    "import kotlinx.serialization.KSerializer",
                    "import kotlinx.serialization.descriptors.SerialDescriptor",
                    "import kotlinx.serialization.descriptors.buildClassSerialDescriptor",
                    "import kotlinx.serialization.descriptors.element",
                    "import kotlinx.serialization.encoding.Decoder",
                    "import kotlinx.serialization.encoding.Encoder",
                    "import kotlinx.serialization.json.JsonDecoder",
                    "import kotlinx.serialization.json.JsonEncoder",
                    "import kotlinx.serialization.json.JsonNull",
                    "import kotlinx.serialization.json.buildJsonObject",
                    "import kotlinx.serialization.json.decodeFromJsonElement",
                    "import kotlinx.serialization.json.encodeToJsonElement",
                    "import kotlinx.serialization.json.jsonObject",
                    "import kotlinx.serialization.json.put",
                ])
            return base
        return []

    def _dto_class_annotations(
        self,
        *,
        schema: SchemaDef | None = None,
        has_oneof: bool = False,
    ) -> list[str]:
        if self._config.serializer == "moshi":
            return ["@JsonClass(generateAdapter = true)"]
        if self._config.serializer == "kotlinx":
            if has_oneof and schema is not None:
                return [f"@Serializable(with = {schema.name}DtoSerializer::class)"]
            return ["@Serializable"]
        return []

    def _dto_field_lines(
        self,
        field: FieldDef,
        enum_names: set[str],
        enums_by_name: dict[str, EnumDef],
        *,
        trailing_comma: bool,
    ) -> list[str]:
        out: list[str] = []
        if field.description:
            out.extend(f"    {ln}" for ln in _kdoc_lines(field.description))
        if field.deprecated:
            out.append('    @Deprecated("field marked deprecated")')
        if field.type.is_one_of_ref:
            type_str = _kotlin_oneof_field_type(field)
        else:
            type_str = _kotlin_type_with_enums(field.type, enum_names)
        name = _kotlin_property_name(field)
        default = _kotlin_default_literal(field, enums_by_name)
        rename_annot = self._field_rename_annotation(field, name)
        prefix = f"    {rename_annot}val " if rename_annot else "    val "
        decl = f"{prefix}{name}: {type_str}"
        if default is not None:
            decl += f" = {default}"
        decl += "," if trailing_comma else ""
        out.append(decl)
        return out

    def _field_rename_annotation(self, field: FieldDef, kotlin_name: str) -> str:
        """Return the per-field rename annotation, if any.

        - Moshi: always emit ``@Json(name = "wire")`` to keep the JSON
          shape stable even when wire name equals kotlin name (defensive
          against future renames).
        - kotlinx: emit ``@SerialName("wire")`` only when names differ.
        - none: never emit.
        """
        if self._config.serializer == "moshi":
            return f'@Json(name = "{field.wire_name}") '
        if self._config.serializer == "kotlinx":
            if kotlin_name != field.wire_name:
                return f'@SerialName("{field.wire_name}") '
            return ""
        return ""

    # ---------------------------- emit enum -------------------------- #

    def generate_enum_source(self, enum: EnumDef, doc: SwaggerDocument) -> str:
        header = comment_header(
            source=_relative_source(doc.source_path) + f"#/components/schemas/{enum.name}",
            generator=self.GENERATOR_NAME,
        )
        footer = comment_footer()
        lines: list[str] = []
        lines.append(f"package {self._dto_package()}")
        lines.append("")
        for imp in self._dto_imports():
            lines.append(imp)
        if self._dto_imports():
            lines.append("")
        if enum.description:
            lines.extend(_kdoc_lines(enum.description))
        if enum.deprecated:
            lines.append('@Deprecated("enum marked deprecated")')
        for ann in self._dto_class_annotations():
            lines.append(ann)

        # kotlinx.serialization default-serializes enum cases by their
        # Kotlin name (e.g. ``CONVERSATION_ID``), but swaggers expect the
        # raw wire value (``conversation_id``). Without ``@SerialName`` per
        # case, the wire ↔ case mapping breaks at runtime even though the
        # constructor-stored ``wire`` property is correct. Emit the
        # rename annotation whenever the case identifier diverges from the
        # raw value.
        use_serial_name = self._config.serializer == "kotlinx"
        if enum.kind == PrimitiveKind.STRING:
            lines.append(f"enum class {enum.name}(val wire: String) {{")
            cases = list(zip(enum.case_names, enum.string_values))
            for i, (case_name, raw) in enumerate(cases):
                ident = escape_keyword(_kotlin_enum_case(case_name), language="kotlin")
                suffix = "," if i < len(cases) - 1 else ";"
                ident_bare = ident.strip("`")
                if use_serial_name and ident_bare != raw:
                    lines.append(f'    @SerialName("{raw}") {ident}("{raw}"){suffix}')
                else:
                    lines.append(f'    {ident}("{raw}"){suffix}')
            lines.append("}")
        else:
            lines.append(f"enum class {enum.name}(val wire: Int) {{")
            cases_int = list(zip(enum.case_names, enum.integer_values))
            for i, (case_name, raw_int) in enumerate(cases_int):
                ident = escape_keyword(_kotlin_enum_case(case_name), language="kotlin")
                suffix = "," if i < len(cases_int) - 1 else ";"
                if use_serial_name:
                    lines.append(f'    @SerialName("{raw_int}") {ident}({raw_int}){suffix}')
                else:
                    lines.append(f"    {ident}({raw_int}){suffix}")
            lines.append("}")

        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    # --------------------------- emit Domain ------------------------- #

    def generate_domain_source(self, schema: SchemaDef) -> str:
        """Plain ``class`` (not ``data class``) so users can freely add
        ``var`` stored properties / equality / methods. Mirrors the v3
        plan §2.2 Android section.

        For ``serializer == "kotlinx"`` the scaffold also carries the
        ``@Serializable(with = {Name}Serializer::class)`` annotation and a
        delegating ``KSerializer`` object below the user customization
        zone, marked with AUTO-GENERATED markers so subsequent builds can
        regenerate just the serializer block without touching user edits.
        Required because Retrofit + kotlinx.serialization converter and
        ``@Serializable`` composites refuse non-``@Serializable`` types
        for request / response / nested field positions — see bug
        ``kjui-wrapper-class-not-serializable-blocks-retrofit-and-composites``.
        """
        if self._config.serializer == "kotlinx":
            return self._generate_kotlinx_domain_source(schema)

        return (
            f"package {self._domain_package()}\n"
            "\n"
            f"import {self._dto_package()}.{schema.name}Dto\n"
            "\n"
            f"class {schema.name}(val dto: {schema.name}Dto) {{\n"
            "    // User customization zone — add proxies, computed properties,\n"
            "    // stored properties, methods, and conversions here.\n"
            "}\n"
        )

    def _generate_kotlinx_domain_source(self, schema: SchemaDef) -> str:
        name = schema.name
        imports = "\n".join(
            [f"import {self._dto_package()}.{name}Dto"]
            + list(_KOTLINX_DOMAIN_IMPORTS)
        )
        return (
            f"package {self._domain_package()}\n"
            "\n"
            f"{imports}\n"
            "\n"
            f"@Serializable(with = {name}Serializer::class)\n"
            f"class {name}(val dto: {name}Dto) {{\n"
            "    // User customization zone — add proxies, computed properties,\n"
            "    // stored properties, methods, and conversions here.\n"
            "}\n"
            "\n"
            f"{_generate_kotlinx_serializer_block(name)}"
        )

    # ----------------------------- writes ---------------------------- #

    @dataclass(frozen=True)
    class WriteResult:
        path: Path
        wrote: bool
        skipped_existing: bool = False

    def write_dto(self, schema: SchemaDef, doc: SwaggerDocument) -> "AndroidApiModelGenerator.WriteResult":
        path = self.dto_path(schema.name)
        wrote = atomic_write_text(path, self.generate_dto_source(schema, doc))
        return self.WriteResult(path=path, wrote=wrote)

    def write_enum(self, enum: EnumDef, doc: SwaggerDocument) -> "AndroidApiModelGenerator.WriteResult":
        path = self.enum_path(enum.name)
        wrote = atomic_write_text(path, self.generate_enum_source(enum, doc))
        return self.WriteResult(path=path, wrote=wrote)

    def write_domain(self, schema: SchemaDef) -> "AndroidApiModelGenerator.WriteResult":
        path = self.domain_path(schema.name)
        if path.exists():
            if self._config.serializer == "kotlinx":
                wrote = _patch_kotlinx_domain(path, schema.name)
                return self.WriteResult(
                    path=path,
                    wrote=wrote,
                    skipped_existing=not wrote,
                )
            return self.WriteResult(path=path, wrote=False, skipped_existing=True)
        wrote = atomic_write_text(path, self.generate_domain_source(schema))
        return self.WriteResult(path=path, wrote=wrote)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


# kotlinx mode Domain wrapper — AUTO-GENERATED block markers. Codegen owns
# the lines between BEGIN and END (inclusive); the rest of the file is user-
# owned and never touched once the scaffold has been written once.
_KOTLINX_SERIALIZER_BEGIN = (
    "// ╔═══ AUTO-GENERATED Serializer — do not edit, will be overwritten on next build ═══"
)
_KOTLINX_SERIALIZER_END = "// ╚═══ END AUTO-GENERATED Serializer ═══"

_KOTLINX_DOMAIN_IMPORTS: tuple[str, ...] = (
    "import kotlinx.serialization.KSerializer",
    "import kotlinx.serialization.Serializable",
    "import kotlinx.serialization.descriptors.SerialDescriptor",
    "import kotlinx.serialization.encoding.Decoder",
    "import kotlinx.serialization.encoding.Encoder",
)


def _generate_kotlinx_serializer_block(name: str) -> str:
    """Render the delegating ``KSerializer`` object for a Domain wrapper.

    Descriptor is forwarded from ``{name}Dto.serializer()`` so the wire
    format is exactly the DTO's — the wrapper is invisible on the wire.
    """
    return (
        f"{_KOTLINX_SERIALIZER_BEGIN}\n"
        f"object {name}Serializer : KSerializer<{name}> {{\n"
        f"    private val dtoSerializer = {name}Dto.serializer()\n"
        f"    override val descriptor: SerialDescriptor = dtoSerializer.descriptor\n"
        f"    override fun serialize(encoder: Encoder, value: {name}) =\n"
        f"        dtoSerializer.serialize(encoder, value.dto)\n"
        f"    override fun deserialize(decoder: Decoder): {name} =\n"
        f"        {name}(dtoSerializer.deserialize(decoder))\n"
        f"}}\n"
        f"{_KOTLINX_SERIALIZER_END}\n"
    )


def _patch_kotlinx_domain(path: Path, schema_name: str) -> bool:
    """Update an existing kotlinx Domain wrapper to carry the serializer.

    Three idempotent transformations:

    1. Insert ``import kotlinx.serialization.*`` lines that are missing
       from the import block (after the package line).
    2. If ``@Serializable(with = {Name}Serializer::class)`` does not
       already appear in the file, inject it on the line immediately
       above the ``class {Name}(`` declaration.
    3. Replace or append the AUTO-GENERATED serializer block. When the
       markers already exist, the block between them is rewritten;
       otherwise the block is appended at end-of-file.

    Returns True when any of the three steps actually changed the file
    contents — used by ``write_domain`` to report ``wrote`` accurately.
    Atomic write (single file replace) so a crash mid-patch never leaves
    a half-edited Kotlin source.

    User customization zone (the class body) is never read or modified.
    """
    import re

    original = path.read_text(encoding="utf-8")
    text = original

    annotation = f"@Serializable(with = {schema_name}Serializer::class)"
    class_decl_re = re.compile(rf"^class {re.escape(schema_name)}\b", re.MULTILINE)

    # Step 1: ensure required imports are present. Insert after the last
    # existing import line, or directly after the package line when the
    # file has no imports yet.
    lines = text.splitlines()
    package_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("package ")),
        None,
    )
    if package_idx is not None:
        existing_imports = {
            ln.strip() for ln in lines if ln.strip().startswith("import ")
        }
        missing = [imp for imp in _KOTLINX_DOMAIN_IMPORTS if imp not in existing_imports]
        if missing:
            # Find the last consecutive import line after the package decl.
            last_import_idx = package_idx
            for i in range(package_idx + 1, len(lines)):
                if lines[i].strip().startswith("import "):
                    last_import_idx = i
                elif lines[i].strip() == "":
                    continue
                else:
                    break
            insert_at = last_import_idx + 1
            for imp in reversed(missing):
                lines.insert(insert_at, imp)
        text = "\n".join(lines)
        if not text.endswith("\n"):
            text += "\n"

    # Step 2: inject @Serializable annotation above the class declaration
    # when the file doesn't already carry an annotation that targets the
    # codegen serializer. Detect both with `in` (avoids re-injection on
    # second build) and by string presence (avoids stomping a user's
    # manual customization that already specifies a different serializer).
    if annotation not in text:
        match = class_decl_re.search(text)
        if match:
            insert_pos = match.start()
            # Only inject when the line above does not already carry an
            # `@Serializable(with = ` annotation — user may have written
            # their own variant; we leave that alone.
            prior_newline = text.rfind("\n", 0, insert_pos)
            prior_line_start = text.rfind("\n", 0, prior_newline) + 1 if prior_newline >= 0 else 0
            prior_line = text[prior_line_start:prior_newline]
            if "@Serializable(with = " not in prior_line:
                text = text[:insert_pos] + f"{annotation}\n" + text[insert_pos:]

    # Step 3: replace or append the serializer block.
    serializer_block = _generate_kotlinx_serializer_block(schema_name)
    if _KOTLINX_SERIALIZER_BEGIN in text and _KOTLINX_SERIALIZER_END in text:
        begin = text.index(_KOTLINX_SERIALIZER_BEGIN)
        end = text.index(_KOTLINX_SERIALIZER_END) + len(_KOTLINX_SERIALIZER_END)
        # Trim trailing newline from the source block once so the splice
        # doesn't double-up blank lines after replacement.
        replacement = serializer_block.rstrip("\n")
        text = text[:begin] + replacement + text[end:]
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + serializer_block

    if text == original:
        return False
    return atomic_write_text(path, text)


def _relative_source(absolute_path: str) -> str:
    return Path(absolute_path).name


def _kdoc_lines(text: str) -> list[str]:
    """Render *text* as a Kotlin ``/** ... */`` doc comment block."""
    raw_lines = text.splitlines() or [text]
    if len(raw_lines) == 1:
        return [f"/** {raw_lines[0]} */"]
    out = ["/**"]
    for ln in raw_lines:
        out.append(f" * {ln}")
    out.append(" */")
    return out


def _kotlin_property_name(field: FieldDef) -> str:
    return escape_keyword(snake_to_camel(field.wire_name), language="kotlin")


def _kotlin_enum_case(case_name: str) -> str:
    """Enum case identifier — Kotlin convention is SCREAMING_SNAKE_CASE.

    Convert snake_case → UPPER_SNAKE, camelCase → UPPER_SNAKE, etc.
    """
    # Insert underscore between camelCase boundaries first, then upper.
    import re
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", case_name)
    s = s.replace("-", "_").replace(" ", "_")
    return s.upper()


_PRIMITIVE_TO_KOTLIN: dict[PrimitiveKind, str] = {
    PrimitiveKind.STRING: "String",
    PrimitiveKind.INTEGER_32: "Int",
    PrimitiveKind.INTEGER_64: "Long",
    PrimitiveKind.INTEGER: "Int",
    PrimitiveKind.FLOAT: "Float",
    PrimitiveKind.DOUBLE: "Double",
    PrimitiveKind.BOOLEAN: "Boolean",
}


def _kotlin_type_with_enums(ftype: FieldType, enum_names: set[str]) -> str:
    """Render a :class:`FieldType` as a Kotlin type expression.

    Object refs become ``<Name>Dto``; enum refs become just ``<Name>``.
    Nullable adds the ``?`` suffix.
    """
    if ftype.is_primitive:
        base = _PRIMITIVE_TO_KOTLIN[ftype.primitive]
    elif (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enum_names:
        base = ftype.ref_name
    elif ftype.is_object_ref or ftype.is_enum_ref:
        base = f"{ftype.ref_name}Dto"
    elif ftype.is_array:
        inner = _kotlin_type_with_enums(ftype.element, enum_names) if ftype.element else "String"
        base = f"List<{inner}>"
    elif ftype.is_map:
        inner = _kotlin_type_with_enums(ftype.element, enum_names) if ftype.element else "String"
        base = f"Map<String, {inner}>"
    else:
        base = "String"
    return f"{base}?" if ftype.nullable else base


def _kotlin_default_literal(
    field: FieldDef,
    enums_by_name: dict[str, EnumDef],
) -> str | None:
    """Render OpenAPI ``default`` as a Kotlin literal, or None if absent.

    Enum-typed fields (``field.type.is_object_ref`` / ``is_enum_ref`` resolving
    to an enum schema) emit ``EnumName.CASE_NAME`` instead of a raw string /
    integer literal — required so ``allOf: [$ref: <enum>] + default: <value>``
    compiles. When the swagger ``default`` does not match any enum case, the
    default is skipped entirely (decoder fills the field at runtime).

    Conservatively skips complex defaults — the JSON parser will fill them.
    """
    if not field.has_default:
        # Nullable fields without an explicit default get `= null` for
        # ergonomic call sites. Required fields are positional.
        if field.type.nullable and not field.required:
            return "null"
        return None
    value = field.default
    if value is None:
        return "null"

    # Enum-typed field → resolve to EnumName.CASE_NAME.
    ftype = field.type
    if (ftype.is_object_ref or ftype.is_enum_ref) and ftype.ref_name in enums_by_name:
        enum = enums_by_name[ftype.ref_name]
        case_name = resolve_enum_case_for_default(enum, value)
        if case_name is None:
            return None
        ident = escape_keyword(_kotlin_enum_case(case_name), language="kotlin")
        return f"{enum.name}.{ident}"

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list) and not value:
        return "emptyList()"
    if isinstance(value, dict) and not value:
        return "emptyMap()"
    return None


# --------------------------------------------------------------------------- #
# oneOf / discriminator helpers (kotlinx only)
# --------------------------------------------------------------------------- #


def _kotlin_oneof_nested_type_name(field: FieldDef) -> str:
    """Nested sealed class name — e.g. ``content`` → ``Content``."""
    return snake_to_pascal(field.wire_name)


def _kotlin_oneof_field_type(field: FieldDef) -> str:
    """Type expression for a oneOf field — references the nested sealed class."""
    base = _kotlin_oneof_nested_type_name(field)
    return f"{base}?" if field.type.nullable else base


def _kotlin_oneof_variant_class_name(discriminator_value: str) -> str:
    """``conversation_id`` → ``ConversationId`` for the data-class variant."""
    return snake_to_pascal(discriminator_value)


def _emit_kotlin_oneof_sealed_class(field: FieldDef, one_of: OneOfRef) -> list[str]:
    """Emit a nested ``sealed class Content`` with one ``data class`` per variant.

    Each variant wraps the corresponding DTO under ``val data: XDto``.
    ``data object Unknown`` provides forward-compat for unrecognized
    discriminator values from the server.
    """
    type_name = _kotlin_oneof_nested_type_name(field)
    lines: list[str] = []
    lines.append(f"    sealed class {type_name} {{")
    for variant in one_of.variants:
        cls = _kotlin_oneof_variant_class_name(variant.discriminator_value)
        lines.append("        @Serializable")
        lines.append(
            f"        data class {cls}(val data: {variant.ref_name}Dto) : {type_name}()"
        )
    lines.append("        @Serializable")
    lines.append(f"        data object Unknown : {type_name}()")
    lines.append("    }")
    return lines


def _emit_kotlin_oneof_serializer(
    schema: SchemaDef,
    dto_package: str,
    enum_names: set[str],
) -> list[str]:
    """Emit ``object {Name}DtoSerializer : KSerializer<{Name}Dto>``.

    Parses the JSON object once, reads each discriminator field, then
    dispatches into the matching variant's DTO decoder using the
    surrounding ``Json`` instance via ``decodeFromJsonElement``. The
    serialize path mirrors this by encoding each non-oneOf field straight
    into the resulting ``JsonObject`` and folding each oneOf variant's
    underlying DTO back into the named slot.
    """
    name = schema.name
    lines: list[str] = []
    lines.append(f"object {name}DtoSerializer : KSerializer<{name}Dto> {{")
    lines.append(
        f'    override val descriptor: SerialDescriptor = '
        f'buildClassSerialDescriptor("{name}Dto") {{'
    )
    for f in schema.fields:
        prop = _kotlin_property_name(f)
        if f.type.is_one_of_ref and f.type.one_of is not None:
            nested = _kotlin_oneof_nested_type_name(f)
            lines.append(
                f'        element("{f.wire_name}", '
                f'buildClassSerialDescriptor("{nested}") {{}})'
            )
        else:
            kt_type = _kotlin_type_with_enums(f.type, enum_names)
            base = kt_type.rstrip("?")
            lines.append(f'        element<{base}>("{f.wire_name}")')
    lines.append("    }")

    # ---------- serialize ----------
    lines.append("")
    lines.append(f"    override fun serialize(encoder: Encoder, value: {name}Dto) {{")
    lines.append(
        '        val jsonEncoder = encoder as? JsonEncoder '
        f'?: error("{name}DtoSerializer requires Json format")'
    )
    lines.append("        val json = jsonEncoder.json")
    lines.append("        val obj = buildJsonObject {")
    for f in schema.fields:
        prop = _kotlin_property_name(f)
        if f.type.is_one_of_ref and f.type.one_of is not None:
            nested = _kotlin_oneof_nested_type_name(f)
            lines.append(f"            val {prop}Json = when (val c = value.{prop}) {{")
            for variant in f.type.one_of.variants:
                cls = _kotlin_oneof_variant_class_name(variant.discriminator_value)
                lines.append(
                    f"                is {name}Dto.{nested}.{cls} -> json.encodeToJsonElement(c.data)"
                )
            lines.append(f"                {name}Dto.{nested}.Unknown -> JsonNull")
            lines.append("            }")
            lines.append(f'            put("{f.wire_name}", {prop}Json)')
        else:
            lines.append(f'            put("{f.wire_name}", json.encodeToJsonElement(value.{prop}))')
    lines.append("        }")
    lines.append("        jsonEncoder.encodeJsonElement(obj)")
    lines.append("    }")

    # ---------- deserialize ----------
    lines.append("")
    lines.append(f"    override fun deserialize(decoder: Decoder): {name}Dto {{")
    lines.append(
        '        val jsonDecoder = decoder as? JsonDecoder '
        f'?: error("{name}DtoSerializer requires Json format")'
    )
    lines.append("        val json = jsonDecoder.json")
    lines.append("        val obj = jsonDecoder.decodeJsonElement().jsonObject")

    # Decode each non-oneOf field; for oneOf fields, dispatch on its
    # discriminator sibling.
    for f in schema.fields:
        prop = _kotlin_property_name(f)
        if f.type.is_one_of_ref:
            continue
        kt_type = _kotlin_type_with_enums(f.type, enum_names)
        base = kt_type.rstrip("?")
        if f.type.nullable:
            lines.append(
                f'        val {prop}: {kt_type} = obj["{f.wire_name}"]?.let '
                f'{{ json.decodeFromJsonElement<{base}>(it) }}'
            )
        else:
            lines.append(
                f'        val {prop}: {kt_type} = json.decodeFromJsonElement('
                f'obj["{f.wire_name}"] ?: error("missing {f.wire_name}"))'
            )

    for f in schema.fields:
        if not f.type.is_one_of_ref or f.type.one_of is None:
            continue
        prop = _kotlin_property_name(f)
        nested = _kotlin_oneof_nested_type_name(f)
        disc_field = next(
            (g for g in schema.fields if g.wire_name == f.type.one_of.discriminator_property),
            None,
        )
        disc_prop = _kotlin_property_name(disc_field) if disc_field else f.type.one_of.discriminator_property
        # When the discriminator field is an inline-derived enum the Kotlin
        # type is the enum (``StreamEventType``) — compare against its
        # ``.wire`` raw-string property so the literal cases below still
        # type-check. ``.wire`` is unconditionally emitted by the enum
        # codegen so this is always safe when ``is_enum_ref`` is true.
        disc_is_enum = (
            disc_field is not None
            and disc_field.type.is_enum_ref
            and disc_field.type.ref_name in enum_names
        )
        when_arg = f"{disc_prop}.wire" if disc_is_enum else disc_prop
        lines.append(
            f'        val {prop}Elem = obj["{f.wire_name}"] ?: JsonNull'
        )
        lines.append(f'        val {prop}: {name}Dto.{nested} = when ({when_arg}) {{')
        for variant in f.type.one_of.variants:
            cls = _kotlin_oneof_variant_class_name(variant.discriminator_value)
            lines.append(
                f'            "{variant.discriminator_value}" -> {name}Dto.{nested}.{cls}('
                f'json.decodeFromJsonElement<{variant.ref_name}Dto>({prop}Elem))'
            )
        lines.append(f"            else -> {name}Dto.{nested}.Unknown")
        lines.append("        }")

    # Construct the data class — fields in declaration order.
    init_args = ", ".join(
        f"{_kotlin_property_name(f)} = {_kotlin_property_name(f)}"
        for f in schema.fields
    )
    lines.append(f"        return {name}Dto({init_args})")
    lines.append("    }")
    lines.append("}")
    return lines
