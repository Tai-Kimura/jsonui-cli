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
)
from ..core.schema_ir import (
    EnumDef,
    FieldDef,
    FieldType,
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
        for imp in self._dto_imports():
            lines.append(imp)
        if self._dto_imports():
            lines.append("")
        if schema.description:
            lines.extend(_kdoc_lines(schema.description))
        if schema.deprecated:
            lines.append('@Deprecated("schema marked deprecated")')
        if schema.is_strict:
            lines.append("// additionalProperties: false (strict — extra fields are dropped on decode)")

        # Annotation line(s) at class scope (Moshi / kotlinx only).
        for ann in self._dto_class_annotations():
            lines.append(ann)
        lines.append(f"data class {schema.name}Dto(")
        last = len(schema.fields) - 1
        for i, f in enumerate(schema.fields):
            for ln in self._dto_field_lines(
                f, enum_names, enums_by_name, trailing_comma=(i < last) or True
            ):
                lines.append(ln)
        # Trailing comma after the last field is valid Kotlin and matches Moshi codegen output.
        lines.append(")")
        body = "\n".join(lines)
        return f"{header}\n\n{body}\n\n{footer}\n"

    def _dto_imports(self) -> list[str]:
        if self._config.serializer == "moshi":
            return [
                "import com.squareup.moshi.Json",
                "import com.squareup.moshi.JsonClass",
            ]
        if self._config.serializer == "kotlinx":
            return [
                "import kotlinx.serialization.SerialName",
                "import kotlinx.serialization.Serializable",
            ]
        return []

    def _dto_class_annotations(self) -> list[str]:
        if self._config.serializer == "moshi":
            return ["@JsonClass(generateAdapter = true)"]
        if self._config.serializer == "kotlinx":
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

        if enum.kind == PrimitiveKind.STRING:
            lines.append(f"enum class {enum.name}(val wire: String) {{")
            cases = list(zip(enum.case_names, enum.string_values))
            for i, (case_name, raw) in enumerate(cases):
                ident = escape_keyword(_kotlin_enum_case(case_name), language="kotlin")
                suffix = "," if i < len(cases) - 1 else ";"
                lines.append(f'    {ident}("{raw}"){suffix}')
            lines.append("}")
        else:
            lines.append(f"enum class {enum.name}(val wire: Int) {{")
            cases_int = list(zip(enum.case_names, enum.integer_values))
            for i, (case_name, raw_int) in enumerate(cases_int):
                ident = escape_keyword(_kotlin_enum_case(case_name), language="kotlin")
                suffix = "," if i < len(cases_int) - 1 else ";"
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
