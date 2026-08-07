"""Intermediate model for the typed attribute code generator.

Loads ``shared/core/attribute_definitions.json`` (the attribute SSoT) and
classifies every attribute into a language-neutral shape that the Swift /
Kotlin / Ruby emitters consume.

Classification rules (derived from the real shapes in the definitions file):

- ``type`` is either a string (``"string"``) or a list
  (``["string", "binding"]``). List elements are strings except the inline
  keyword-enum dict used by ``width`` / ``height``:
  ``["number", {"enum": ["matchParent", "wrapContent"]}, "binding"]``.
- ``"binding"`` in the type list marks the attribute *binding-capable*: the
  author may write either a static value or a ``@{expr}`` binding. This is
  represented in generated code as ``AttrValue<T>`` (value | binding).
- ``type == "binding"`` (binding **only**) attributes hold a binding
  expression string (event handlers like ``onClick``).
- ``enum`` + single ``string`` type → language enum (unknown value → nil/null
  plus a warning-hook call, never a crash).
- ``callback``-typed attributes are function-valued and cannot be extracted
  from JSON → skipped (listed in the emitted skip list with a reason).
- Metadata attributes (``generatedBy``) are not rendered → skipped.
- Multi-type unions that have no dedicated representation (for example
  ``["string", "object"]``) fall back to a RAW (untyped) property; the
  accepted kinds are recorded for doc comments.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AttrKind(str, Enum):
    """Language-neutral value kind of an attribute."""

    STRING = "string"
    COLOR = "color"          # color string (hex or named color) — string-typed
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    ANY = "any"              # declared `any` in the definitions
    RAW = "raw"              # multi-type union without a dedicated repr
    ENUM = "enum"            # string + enum values → language enum
    DIMENSION = "dimension"  # number | keyword enum (width / height)
    BINDING = "binding"      # binding-only (event handlers) → expression str


#: Attributes that are pure metadata (never rendered) — skipped from codegen.
#: `platform` is a build directive consumed (and removed) at distribution
#: time by PlatformResolver, so no runtime extraction code should exist.
METADATA_ATTRS = frozenset({"generatedBy", "platform", "role"})


@dataclass(frozen=True)
class Attribute:
    """One extractable attribute (canonical name + typing info)."""

    name: str
    component: str
    kind: AttrKind
    bindable: bool = False
    enum_values: tuple[str, ...] = ()
    #: ``((alias value, canonical value), …)`` from the definition's
    #: ``valueAliases`` object — the enum keeps ACCEPTING the alias
    #: spellings, but emitters fold them into the canonical case so every
    #: runtime routes them through the canonical code path (e.g.
    #: Collection.layout ``LeftAligned`` → ``flow``).
    value_aliases: tuple[tuple[str, str], ...] = ()
    dimension_keywords: tuple[str, ...] = ()
    raw_kinds: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    required: bool = False
    default: Any = None
    deprecated: bool = False
    deprecation_note: str = ""
    binding_direction: str = ""
    description: str = ""

    @property
    def context(self) -> str:
        """`component.attr` string used in generated warning messages."""
        return f"{self.component}.{self.name}"

    @property
    def value_alias_map(self) -> dict[str, str]:
        """``{alias value: canonical value}`` (see ``value_aliases``)."""
        return dict(self.value_aliases)


@dataclass(frozen=True)
class SkippedAttr:
    """An attribute excluded from codegen, with the reason."""

    component: str
    name: str
    reason: str
    type_repr: str


@dataclass
class Component:
    """A component section (or ``common``) with its extractable attrs."""

    name: str
    attrs: list[Attribute] = field(default_factory=list)
    #: attr names that shadow a same-named `common` attribute
    common_overrides: tuple[str, ...] = ()
    #: canonical component when this section is an `_alias_of` pointer
    #: (EditText -> TextField, ...). The emitted table is a full clone of
    #: the canonical one: the dynamic runtimes select tables by the raw
    #: spelling, so an alias table must parse the complete canonical
    #: surface.
    alias_of: str | None = None


@dataclass
class AttrModel:
    """The whole definitions file, classified and sorted (deterministic)."""

    common: Component
    components: list[Component]
    skipped: list[SkippedAttr]
    #: distinct keyword sets used by DIMENSION attrs (sorted tuples)
    dimension_keyword_sets: list[tuple[str, ...]]
    source: str = "shared/core/attribute_definitions.json"

    def all_components(self) -> list[Component]:
        """``common`` first, then components alphabetically."""
        return [self.common, *self.components]


def default_definitions_path() -> Path:
    """The bundled SSoT definitions file (repo layout and installed layout
    both keep ``shared/`` next to ``jui_tools/``)."""
    return (
        Path(__file__).resolve().parents[4]
        / "shared" / "core" / "attribute_definitions.json"
    )


def load_model(path: Path | None = None) -> AttrModel:
    """Load + classify the definitions file into an :class:`AttrModel`."""
    definitions_path = path or default_definitions_path()
    with open(definitions_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return build_model(data)


def build_model(data: dict[str, Any]) -> AttrModel:
    """Classify an already-parsed definitions dict (used by tests)."""
    common_attrs: list[Attribute] = []
    components: list[Component] = []
    skipped: list[SkippedAttr] = []

    common_section = data.get("common") or {}
    common_names = {
        k for k, v in common_section.items()
        if not k.startswith("_") and isinstance(v, dict)
    }

    for section_name in sorted(k for k in data if k != "_comment"):
        section = data[section_name]
        if not isinstance(section, dict):
            continue
        # Component alias (`_alias_of` pointer section, B1 shape): emit a
        # full clone of the canonical section under the alias name. One
        # hop only; a pointer to a missing or alias-shaped target falls
        # back to the section's own (empty) body.
        alias_of: str | None = None
        target_name = section.get("_alias_of")
        if isinstance(target_name, str):
            target = data.get(target_name)
            if isinstance(target, dict) and not isinstance(
                target.get("_alias_of"), str
            ):
                alias_of = target_name
                section = target
        attrs: list[Attribute] = []
        overrides: list[str] = []
        # `_`-prefixed keys are section DIRECTIVES (`_alias_of`, `_alias`, and
        # the prose `_comment`) — 15 of the 16 in the SSoT, all strings, and
        # the `isinstance(entry, dict)` guard below drops every one of them.
        # The sixteenth is `View._comment`, a real declared attribute carrying
        # a type and a description. Filtering the prefix here excluded it
        # BEFORE `classify_attr`, i.e. before the only place that records why
        # an attribute was excluded, so it was the one spelling dropped
        # without a line in skipped_attributes.json. Excluding it is right;
        # doing so silently is the part that was not (plan 49 lane C).
        for attr_name in sorted(section):
            entry = section[attr_name]
            if not isinstance(entry, dict):
                continue
            result = classify_attr(section_name, attr_name, entry)
            if isinstance(result, SkippedAttr):
                skipped.append(result)
                continue
            attrs.append(result)
            if section_name != "common" and attr_name in common_names:
                overrides.append(attr_name)
        component = Component(
            name=section_name,
            attrs=attrs,
            common_overrides=tuple(sorted(overrides)),
            alias_of=alias_of,
        )
        if section_name == "common":
            common = component
            common_attrs = attrs
        else:
            components.append(component)

    if not common_attrs:
        common = Component(name="common", attrs=[])

    keyword_sets = sorted({
        a.dimension_keywords
        for comp in [common, *components]
        for a in comp.attrs
        if a.kind is AttrKind.DIMENSION
    })

    return AttrModel(
        common=common,
        components=components,
        skipped=sorted(skipped, key=lambda s: (s.component, s.name)),
        dimension_keyword_sets=keyword_sets,
    )


def classify_attr(
    component: str, name: str, entry: dict[str, Any]
) -> Attribute | SkippedAttr:
    """Classify one raw attribute entry."""
    raw_type = entry.get("type")
    types: list[Any] = raw_type if isinstance(raw_type, list) else [raw_type]
    type_repr = json.dumps(raw_type, ensure_ascii=False)

    str_types = [t for t in types if isinstance(t, str)]
    if "callback" in str_types:
        return SkippedAttr(
            component=component,
            name=name,
            reason="callback type — function-valued, not extractable from JSON",
            type_repr=type_repr,
        )
    if name.startswith("_"):
        # A declared attribute whose name reads as a section directive — the
        # SSoT has exactly one (`View._comment`). Never emitted, and now said
        # so out loud rather than filtered upstream of this function.
        return SkippedAttr(
            component=component,
            name=name,
            reason="developer metadata — leading underscore, never rendered",
            type_repr=type_repr,
        )
    if name in METADATA_ATTRS or name.startswith("$"):
        # ``$``-prefixed names are harness/normalizer markers (e.g. ``$jui``)
        # and are invalid identifiers in Swift/Kotlin — never emit them.
        return SkippedAttr(
            component=component,
            name=name,
            reason="metadata — not rendered by any platform",
            type_repr=type_repr,
        )

    bindable = "binding" in str_types
    others = [t for t in types if t != "binding"]

    kind, enum_values, dim_keywords, raw_kinds = _resolve_kind(entry, others)
    if kind is AttrKind.BINDING:
        bindable = False  # binding-only is its own kind, not AttrValue-wrapped

    value_aliases = _resolve_value_aliases(entry, enum_values, f"{component}.{name}")

    return Attribute(
        name=name,
        component=component,
        kind=kind,
        bindable=bindable,
        enum_values=enum_values,
        value_aliases=value_aliases,
        dimension_keywords=dim_keywords,
        raw_kinds=raw_kinds,
        aliases=tuple(entry.get("aliases") or ()),
        required=bool(entry.get("required", False)),
        default=entry.get("default"),
        deprecated=bool(entry.get("deprecated", False)),
        deprecation_note=str(entry.get("deprecation_note") or ""),
        binding_direction=str(entry.get("binding_direction") or ""),
        description=_clean_text(entry.get("description")),
    )


def _resolve_value_aliases(
    entry: dict, enum_values: tuple[str, ...], context: str
) -> tuple[tuple[str, str], ...]:
    """Validated ``valueAliases`` pairs for one attribute definition.

    Authoring errors fail loudly: an alias or target outside the declared
    enum values means the SSoT contradicts itself, and silently dropping
    the mapping would leave each runtime free to disagree about it.
    """
    raw = entry.get("valueAliases")
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ValueError(f"{context}: valueAliases must be an object")
    if not enum_values:
        raise ValueError(
            f"{context}: valueAliases declared but the attribute has no enum values"
        )
    declared = set(enum_values)
    pairs: list[tuple[str, str]] = []
    for alias, canonical in raw.items():
        if not isinstance(alias, str) or not isinstance(canonical, str):
            raise ValueError(f"{context}: valueAliases entries must map string to string")
        if alias == canonical:
            raise ValueError(f"{context}: valueAliases maps '{alias}' to itself")
        if alias not in declared or canonical not in declared:
            raise ValueError(
                f"{context}: valueAliases '{alias}' -> '{canonical}' must both "
                "appear in the declared enum values"
            )
        if canonical in raw:
            raise ValueError(
                f"{context}: valueAliases target '{canonical}' is itself an alias"
            )
        pairs.append((alias, canonical))
    return tuple(pairs)


def _resolve_kind(
    entry: dict[str, Any], others: list[Any]
) -> tuple[AttrKind, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return ``(kind, enum_values, dimension_keywords, raw_kinds)``."""
    if not others:
        # type == "binding" (binding only)
        return AttrKind.BINDING, (), (), ()

    keyword_dicts = [
        t for t in others if isinstance(t, dict) and isinstance(t.get("enum"), list)
    ]
    str_others = [t for t in others if isinstance(t, str)]

    if len(others) == 1 and not keyword_dicts:
        single = str_others[0]
        if single == "string":
            enum_values = entry.get("enum")
            if enum_values and all(isinstance(v, str) for v in enum_values):
                return AttrKind.ENUM, tuple(enum_values), (), ()
            return AttrKind.STRING, (), (), ()
        simple = {
            "color": AttrKind.COLOR,
            "number": AttrKind.NUMBER,
            "boolean": AttrKind.BOOLEAN,
            "object": AttrKind.OBJECT,
            "array": AttrKind.ARRAY,
            "any": AttrKind.ANY,
        }.get(single)
        if simple is not None:
            return simple, (), (), ()
        # Unknown single kind — never crash, fall back to RAW.
        return AttrKind.RAW, (), (), (single,)

    # number + inline keyword enum (width / height dimension union)
    if (
        len(keyword_dicts) == 1
        and set(str_others) == {"number"}
        and all(isinstance(v, str) for v in keyword_dicts[0]["enum"])
    ):
        keywords = tuple(keyword_dicts[0]["enum"])
        return AttrKind.DIMENSION, (), keywords, ()

    # Any other union → RAW, but record accepted kinds for doc comments.
    raw_kinds: list[str] = []
    for t in others:
        if isinstance(t, str):
            raw_kinds.append(t)
        elif isinstance(t, dict) and isinstance(t.get("enum"), list):
            raw_kinds.append("enum(" + "|".join(map(str, t["enum"])) + ")")
        else:
            raw_kinds.append("unknown")
    return AttrKind.RAW, (), (), tuple(raw_kinds)


def merged_alias_map(
    comp: Component, common: Component | None = None
) -> dict[str, str]:
    """Public metadata contract: alias spelling → canonical name (sorted).

    Rows are merged common-first (component rows override on name
    collision — same precedence as the generated extract/parse methods).
    Alias spellings that are ALSO declared canonical names (e.g. ``alpha``
    next to ``opacity``) keep their own row and are not redirected.
    """
    rows: dict[str, Attribute] = {}
    sources = [common, comp] if common is not None and comp is not common else [comp]
    for source in sources:
        for attr in source.attrs:
            rows[attr.name] = attr
    out: dict[str, str] = {}
    for attr in rows.values():
        for alias in attr.aliases:
            if alias not in rows:
                out[alias] = attr.name
    return dict(sorted(out.items()))


def skipped_payload(model: AttrModel) -> dict[str, Any]:
    """JSON payload of the skip list, emitted into every language dir."""
    return {
        "_comment": (
            "@generated by `jui generate attr-bindings` — attributes "
            "excluded from typed extraction, with reasons. DO NOT EDIT."
        ),
        "source": model.source,
        "skipped": [
            {
                "component": s.component,
                "attribute": s.name,
                "type": s.type_repr,
                "reason": s.reason,
            }
            for s in model.skipped
        ],
    }


def _clean_text(value: Any) -> str:
    """Single-line, comment-safe text for doc comments."""
    if not value:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    # Defensive: never let a description terminate a block comment.
    text = text.replace("*/", "* /")
    return " ".join(text.split())


def format_default(value: Any) -> str:
    """A declared default rendered as the JSON it was actually written in.

    `f"{value}"` renders Python's spelling, so a boolean default reached the
    generated Ruby, Kotlin AND Swift doc comments as `True` — a word none of
    those three languages spells that way. The declaration lives in JSON and
    the comment documents the declaration, so JSON's spelling is the one that
    is correct in every emitter rather than accidentally correct in none.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)
