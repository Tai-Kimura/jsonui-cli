"""Platform-independent intermediate representation for OpenAPI schemas.

Produced by :mod:`openapi_loader` and consumed by per-platform generators
(``ios_api_model_generator``, ``android_api_model_generator``,
``web_api_model_generator``). Carries enough information for each generator
to emit a DTO + Domain scaffold without re-parsing the swagger.

All names are stored in their **wire form** (``snake_case`` as written in the
swagger). Each generator decides how to convert to its native casing.

See :doc:`docs/plans/2026-05-27-swagger-data-model-generation.md` §2 / §4 for
the design rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PrimitiveKind(str, Enum):
    """Atomic OpenAPI types resolved to a normalized enum.

    Reflects the §4 mapping table. String-typed schemas always resolve to
    ``STRING`` here; the recognized string ``format`` hints
    (``date-time`` / ``uuid`` / ``binary``) are retained as a side channel
    on :attr:`FieldType.format` (plan ``2026-07-24-v1-unsupported/03``).
    Whether a generator maps them to native types is decided per doc by
    the opt-in ``api.format_mapping`` config — the IR carries the hint
    unconditionally so the loader stays orthogonal to the flag.
    """

    STRING = "string"
    INTEGER_32 = "int32"
    INTEGER_64 = "int64"
    INTEGER = "integer"
    FLOAT = "float"
    DOUBLE = "double"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class OneOfVariant:
    """One arm of a discriminated ``oneOf`` union.

    Attributes:
        discriminator_value: the raw string value (matched against the
            sibling discriminator field's wire value).
        ref_name: the variant schema name (must resolve to a top-level
            entry in ``components.schemas``).
    """

    discriminator_value: str
    ref_name: str


@dataclass(frozen=True)
class UnionDef:
    """A top-level (schema-level) discriminated ``oneOf`` union.

    Unlike :class:`OneOfRef` (field-level union, tag lives in the parent
    schema's sibling property), a ``UnionDef`` is a standalone top-level
    type whose wire form is the **variant payload itself** with the
    discriminator tag *inside* the payload. Generators emit a
    self-decoding union type (Swift enum + custom Codable / Kotlin sealed
    class + custom KSerializer / TS payload union + match helper) named
    ``{name}Dto``.

    ``variants`` preserves mapping (or inference) order so generated
    case / branch order is deterministic. ``mapping_inferred`` is True
    when ``discriminator.mapping`` was absent and the mapping was
    inferred from each variant's internal tag property (``const`` string
    or single-value string enum) — the loader logs the inferred mapping
    as a WARNING so it is visible outside the swagger diff.
    """

    name: str
    discriminator_property: str
    variants: tuple["OneOfVariant", ...]
    mapping_inferred: bool = False
    description: str | None = None
    deprecated: bool = False
    skip_domain: bool = False
    source_pointer: str = ""

    def referenced_schemas(self) -> set[str]:
        return {v.ref_name for v in self.variants}


@dataclass(frozen=True)
class OneOfRef:
    """A field whose value is one of several variant DTOs, tagged by a
    sibling property in the parent schema.

    ``discriminator_property`` is the **wire name** of the sibling that
    carries the discriminator value (as ``String`` on the wire). v1
    enforces that the sibling exists in the same parent schema; nested /
    self-discriminator variants are deferred to v2.

    ``variants`` preserves the swagger ``discriminator.mapping`` order so
    generators emit cases / branches deterministically.
    """

    discriminator_property: str
    variants: tuple[OneOfVariant, ...]


@dataclass(frozen=True)
class FieldType:
    """The type of a single DTO field.

    Exactly one of the discriminator booleans is True. Generators inspect
    these to emit ``String`` / ``List<Foo>`` / ``Map<String, Foo>`` etc.

    Attributes:
        is_primitive: ``primitive`` carries the resolved :class:`PrimitiveKind`.
        is_enum_ref: ``ref_name`` carries the enum schema name.
        is_object_ref: ``ref_name`` carries another schema's name (DTO type).
        is_array: ``element`` carries the element type recursively.
        is_map: ``element`` carries the value type
            (``additionalProperties: <typed>``).
        is_one_of_ref: ``one_of`` carries the discriminated union spec.
        nullable: True if the field is optional or ``nullable: true``.
        format: retained OpenAPI string ``format`` hint — one of
            ``"date-time"`` / ``"uuid"`` / ``"binary"`` when the swagger
            declared it on a ``type: string`` schema, else ``None``.
            Only meaningful when ``primitive is PrimitiveKind.STRING``;
            generators consult it only when ``api.format_mapping`` is
            enabled for the doc (integer/number widths use dedicated
            :class:`PrimitiveKind` members instead).
    """

    is_primitive: bool = False
    is_enum_ref: bool = False
    is_object_ref: bool = False
    is_array: bool = False
    is_map: bool = False
    is_one_of_ref: bool = False
    primitive: PrimitiveKind | None = None
    ref_name: str | None = None
    element: "FieldType | None" = None
    one_of: OneOfRef | None = None
    nullable: bool = False
    format: str | None = None

    def referenced_schemas(self) -> set[str]:
        """Names of schemas this type depends on (transitively).

        Used by the cycle detector to walk the dependency graph and by the
        generator's import resolver.
        """
        names: set[str] = set()
        if self.is_object_ref and self.ref_name:
            names.add(self.ref_name)
        if self.is_enum_ref and self.ref_name:
            names.add(self.ref_name)
        if self.element is not None:
            names |= self.element.referenced_schemas()
        if self.one_of is not None:
            for v in self.one_of.variants:
                names.add(v.ref_name)
        return names

    def is_collection(self) -> bool:
        """True if this field provides heap indirection (array or map).

        A direct self-reference through an array/map is safe in Swift
        struct / Kotlin data class — only ``is_object_ref`` without a
        wrapping collection forces infinite size.
        """
        return self.is_array or self.is_map


@dataclass(frozen=True)
class FieldDef:
    """One field on a DTO.

    Attributes:
        wire_name: Field name exactly as written in swagger.
        type: :class:`FieldType` describing the value shape.
        required: True if listed in the schema's ``required`` array.
        nullable: True if ``nullable: true`` is set.
        description: OpenAPI ``description`` text, emitted as doc comment.
        deprecated: True if ``deprecated: true``.
        default: Default value literal as written in swagger
            (``None`` if not provided). Generators serialize per platform.
    """

    wire_name: str
    type: FieldType
    required: bool = False
    description: str | None = None
    deprecated: bool = False
    default: Any = None  # `None` means "not set"; null default is sentinel-encoded
    has_default: bool = False


@dataclass(frozen=True)
class EnumDef:
    """A standalone enum schema.

    ``integer_values`` is populated only when ``kind == INTEGER`` — Swift
    raw value ``= N`` / Kotlin ``constructor(val wire: Int)`` need the
    numeric value alongside the case name.

    ``case_names`` is the user-facing name for each value; defaults to a
    derived form (raw value for string enums, ``value_N`` for ints) when
    ``x-enum-varnames`` is not present.
    """

    name: str
    kind: PrimitiveKind  # STRING or INTEGER
    case_names: list[str]
    string_values: list[str] = field(default_factory=list)
    integer_values: list[int] = field(default_factory=list)
    description: str | None = None
    deprecated: bool = False


@dataclass(frozen=True)
class SchemaDef:
    """One top-level (or inline-derived) object schema.

    Attributes:
        name: PascalCase schema name (key under ``components.schemas`` or
            the derived ``ParentField`` for inline objects).
        fields: Ordered list of :class:`FieldDef` (preserve swagger order).
        description: OpenAPI ``description`` for the whole schema.
        deprecated: True if ``deprecated: true`` on the schema.
        skip_domain: True if ``x-jui-skip-domain: true`` is set — codegen
            emits only the DTO, no Domain scaffold.
        source_pointer: JSON pointer in the source swagger (for diagnostics).
        is_strict: True if ``additionalProperties: false`` — emit as a
            doc comment annotation.
        is_equatable: True if all fields' types support equality without
            ``Any`` leakage.
        is_hashable: True if all fields' types are hashable
            (typed maps break Hashable on Swift).
        is_sendable: True if all fields' types are Sendable conformant.
        is_wrapper: True when the swagger schema is a non-object top-level
            type (``type: string`` / ``type: integer`` / ``type: array``
            etc.). The wire format is the bare wrapped value (no JSON
            object envelope), so codegen emits a single-field wrapper type
            with a custom single-value (en|de)coder.
        wrapped_type: For wrapper schemas, the :class:`FieldType` of the
            sole synthesized field. ``None`` for regular object schemas.
        wrapper_field_name: Synthesized field name on the wrapper — by
            convention ``"items"`` for ``type: array``, ``"value"`` for
            primitives. Used by every platform generator so consumer code
            accesses ``dto.value`` or ``dto.items``.
    """

    name: str
    fields: list[FieldDef]
    description: str | None = None
    deprecated: bool = False
    skip_domain: bool = False
    source_pointer: str = ""
    is_strict: bool = False
    is_equatable: bool = True
    is_hashable: bool = True
    is_sendable: bool = True
    is_wrapper: bool = False
    wrapped_type: "FieldType | None" = None
    wrapper_field_name: str = "value"

    def referenced_schemas(self) -> set[str]:
        names: set[str] = set()
        for f in self.fields:
            names |= f.type.referenced_schemas()
        return names

    def has_direct_self_reference(self) -> bool:
        """True if any field references this schema *without* collection indirection.

        ``next: $ref(Self)`` → True (struct can't hold itself by value)
        ``children: [$ref(Self)]`` → False (Array provides heap indirection)
        """
        for f in self.fields:
            t = f.type
            if t.is_object_ref and t.ref_name == self.name:
                return True
        return False


@dataclass(frozen=True)
class SwaggerDocument:
    """Top-level parsed swagger artifact.

    Holds the schemas + enums extracted from a single ``*.json`` file
    under ``api_directory``. Generators iterate over ``schemas`` and
    ``enums`` to emit DTOs.

    ``filtered_out`` carries names dropped by ``schema_filter`` so the
    build command can report them to the user (v2 plan §2.5). Empty
    set when no filter was applied.

    ``skip_domain_overrides`` is the per-app overlay from
    ``api.schemas.skip_domain`` — generators must OR-evaluate this with
    each schema's own ``skip_domain`` attribute (which mirrors
    ``x-jui-skip-domain``) to decide if the Domain scaffold should be
    skipped (v2 plan §2.6).
    """

    source_path: str  # absolute path of the swagger json
    title: str
    version: str
    schemas: list[SchemaDef]
    enums: list[EnumDef]
    filtered_out: frozenset[str] = field(default_factory=frozenset)
    skip_domain_overrides: frozenset[str] = field(default_factory=frozenset)
    unions: list[UnionDef] = field(default_factory=list)

    def should_skip_domain(self, schema: "SchemaDef | UnionDef") -> bool:
        """OR-evaluate per-app skip + per-schema skip (v2 plan §2.6).

        Accepts :class:`UnionDef` too — both carry ``skip_domain`` +
        ``name`` and the override set is keyed by schema name either way.
        """
        return schema.skip_domain or schema.name in self.skip_domain_overrides


def collect_string_formats(ftype: FieldType) -> set[str]:
    """Retained string formats reachable through array / map nesting.

    Refs are not followed — the referenced schema reports its own formats.
    Used by generators / sync planners to decide which format support
    artifacts (typealias / serializer files, halts) a schema or doc needs.
    """
    found: set[str] = set()
    if ftype.is_primitive and ftype.format is not None:
        found.add(ftype.format)
    if ftype.element is not None:
        found |= collect_string_formats(ftype.element)
    return found


def schema_string_formats(schema: SchemaDef) -> set[str]:
    """Union of :func:`collect_string_formats` over a schema's fields."""
    found: set[str] = set()
    for f in schema.fields:
        found |= collect_string_formats(f.type)
    return found


def doc_string_formats(doc: SwaggerDocument) -> set[str]:
    """Union of :func:`schema_string_formats` over every schema in *doc*.

    Wrapper schemas are covered through their synthesized field; unions
    carry no fields of their own (variants are refs), so they contribute
    nothing here.
    """
    found: set[str] = set()
    for schema in doc.schemas:
        found |= schema_string_formats(schema)
    return found
