"""Build ``{alias -> canonical}`` attribute tables from attribute_definitions.json.

The SSoT for attribute names is ``shared/core/attribute_definitions.json``.
An attribute definition may carry an ``aliases`` array — the key that
*declares* the ``aliases`` field is the canonical spelling, and every name
in the array is an alternate spelling that the L1 canonicalizer rewrites
to it (e.g. ``opacity`` declares ``"aliases": ["alpha"]`` so ``alpha`` →
``opacity``).

Resolution order is component-specific definitions first, then ``common``
(component-specific entries win when the same alias name appears in both).

Definitions may also carry ``deprecated`` (``true`` or a platform/mode
scope string such as ``"swiftui"`` / ``"kotlin"``, or an array of scopes)
plus an optional ``deprecation_note``; the table exposes these so the
canonicalizer can emit warnings without rewriting (there is no rewrite
target for deprecated attributes).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Cross-platform type-spelling synonyms, applied AFTER the exact-match
# check in definition_key_for. This table is one of four implementations
# of the same mapping — see {s,k,r}jui_tools/lib/core/attribute_validator.rb
# (map_type_to_definition) — and jui_tools/tests/
# test_type_synonyms_cross_language.py holds the agreed canon and fails CI
# on any divergence: change all four together, never one alone.
# Deliberately absent: EditText / Input / Check / Toggle. Those spellings
# are real sections in attribute_definitions.json shaped as `_alias_of`
# pointers (B1); the exact-match check resolves them first and the
# component-alias hop in definition_key_for follows the pointer to the
# canonical section, so an entry here would be dead code.
_TYPE_SYNONYMS = {
    "Text": "Label",
    "MultiLineEditText": "TextView",
    "Textarea": "TextView",
    "ImageView": "Image",
    "Img": "Image",
    "NetworkImageView": "NetworkImage",
    "CircleImage": "NetworkImage",
    "CircleImageView": "NetworkImage",
    "AsyncImage": "NetworkImage",
    "Spinner": "SelectBox",
    "DatePicker": "SelectBox",
    "Select": "SelectBox",
    "Picker": "SelectBox",
    "Checkbox": "CheckBox",
    "RadioButton": "Radio",
    "RadioGroup": "Radio",
    "SegmentedControl": "Segment",
    "TabLayout": "Segment",
    "TabGroup": "Segment",
    "SeekBar": "Slider",
    "Range": "Slider",
    "ProgressBar": "Progress",
    "ActivityIndicator": "Indicator",
    "Loading": "Indicator",
    "LinearLayout": "View",
    "RelativeLayout": "View",
    "FrameLayout": "View",
    "HStack": "View",
    "VStack": "View",
    "ZStack": "View",
    "Div": "View",
    "Box": "View",
    "Container": "View",
    "Column": "View",
    "Row": "View",
    "ConstraintLayout": "View",
    "Scroll": "ScrollView",
    "CollectionView": "Collection",
    "RecyclerView": "Collection",
    "Table": "Collection",
    "TableView": "Collection",
    "List": "Collection",
    "Grid": "Collection",
    "LazyGrid": "Collection",
    "ListView": "Collection",
    "LazyColumn": "Collection",
    "Gradient": "GradientView",
    "BlurView": "Blur",
    "WebView": "Web",
    "Iframe": "Web",
}

# The SSoT definitions file, in preference order: the shared/ tree of a
# full jsonui-cli checkout, then the per-platform tool copies (project-local
# installs sync {k,s,r}jui_tools/ next to jui_tools/ WITHOUT shared/ — the
# tool copies dereference the same shared/core file at sync time).
_DEFINITIONS_RELPATHS = (
    Path("shared") / "core" / "attribute_definitions.json",
    Path("kjui_tools") / "lib" / "core" / "attribute_definitions.json",
    Path("sjui_tools") / "lib" / "core" / "attribute_definitions.json",
    Path("rjui_tools") / "lib" / "core" / "attribute_definitions.json",
)


@dataclass(frozen=True)
class DeprecationInfo:
    """Deprecation metadata for one attribute."""

    scope: Any  # True, or str / list[str] platform/mode scope(s)
    note: str = ""

    def scope_label(self) -> str:
        if self.scope is True:
            return "all platforms"
        if isinstance(self.scope, (list, tuple)):
            return "/".join(str(s) for s in self.scope)
        return str(self.scope)


def default_definitions_path() -> Path | None:
    """Locate ``attribute_definitions.json`` relative to the installed
    tool tree: ``shared/core/`` in a full jsonui-cli checkout, or a
    per-platform tool copy (``{k,s,r}jui_tools/lib/core/``) in a
    project-local install where only the tool directories are synced."""
    for parent in Path(__file__).resolve().parents:
        for relpath in _DEFINITIONS_RELPATHS:
            candidate = parent / relpath
            if candidate.exists():
                return candidate
    return None


class AliasTable:
    """Per-component alias → canonical maps plus deprecation metadata."""

    def __init__(self, definitions: dict[str, Any]):
        self._definitions = definitions or {}
        self._common_aliases = self._alias_map_for_section("common")
        self._common_deprecated = self._deprecated_map_for_section("common")
        self._common_value_aliases = self._value_alias_map_for_section("common")
        # component key -> cached maps
        self._alias_cache: dict[str | None, dict[str, str]] = {}
        self._deprecated_cache: dict[str | None, dict[str, DeprecationInfo]] = {}
        self._value_alias_cache: dict[str | None, dict[str, dict[str, str]]] = {}

    # ------------------------------------------------------------------
    # Construction

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> "AliasTable":
        """Load from *path*, defaulting to the bundled SSoT definitions.

        Missing / unreadable file degrades to an empty table (normalizer
        becomes a marker-only pass) rather than failing the build.
        Callers that stamp the L1 marker should check :meth:`is_empty`
        and warn — consumers on the canonical-only path assume aliases
        were actually rewritten.
        """
        resolved = Path(path) if path else default_definitions_path()
        if resolved is None or not resolved.exists():
            return cls({})
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                return cls(json.load(f))
        except (OSError, json.JSONDecodeError):
            return cls({})

    def is_empty(self) -> bool:
        """True when no definitions were loaded (marker-only pass)."""
        return not self._definitions

    # ------------------------------------------------------------------
    # Lookup

    def definition_key_for(self, component_type: str | None) -> str | None:
        """Map a node ``type`` value to its definition key (exact match
        first, then cross-platform type synonyms), following a component
        alias (`_alias_of`) to the canonical section."""
        if not component_type:
            return None
        if component_type in self._definitions:
            key: str | None = component_type
        else:
            key = _TYPE_SYNONYMS.get(component_type)
        target = self.component_alias_target(key)
        return target if target is not None else key

    def component_alias_target(self, component_type: str | None) -> str | None:
        """Canonical section name when *component_type* is a component
        alias — a real section whose body is an ``_alias_of`` pointer
        (EditText/Input -> TextField, Check -> CheckBox, Toggle ->
        Switch). None for canonical sections, synonyms and unknowns.

        One hop only: a canonical section must not itself declare
        ``_alias_of`` (the collapse that introduced this shape keeps
        alias sections attribute-free, so a chain cannot mean anything).
        A pointer to a nonexistent section is ignored rather than
        followed — the alias then degrades to its own (empty) section,
        which the schema guard suite reports loudly."""
        if not component_type:
            return None
        section = self._definitions.get(component_type)
        if not isinstance(section, dict):
            return None
        target = section.get("_alias_of")
        if isinstance(target, str) and target in self._definitions:
            target_section = self._definitions.get(target)
            if isinstance(target_section, dict) and not isinstance(
                target_section.get("_alias_of"), str
            ):
                return target
        return None

    def aliases_for(self, component_type: str | None) -> dict[str, str]:
        """``{alias: canonical}`` effective for *component_type* —
        ``common`` aliases overlaid with component-specific ones."""
        key = self.definition_key_for(component_type)
        if key in self._alias_cache:
            return self._alias_cache[key]
        merged = dict(self._common_aliases)
        if key and key != "common":
            merged.update(self._alias_map_for_section(key))
        self._alias_cache[key] = merged
        return merged

    def value_aliases_for(self, component_type: str | None) -> dict[str, dict[str, str]]:
        """``{attribute: {alias value: canonical value}}`` for *component_type*.

        Declared via a ``valueAliases`` object on the attribute definition —
        the enum keeps accepting the alias spellings, the canonicalizer
        rewrites them, and attr-codegen folds them into the canonical enum
        case (e.g. Collection.layout ``LeftAligned``/``leftAligned``/``Flow``
        → ``flow``). Same overlay rule as :meth:`aliases_for`.
        """
        key = self.definition_key_for(component_type)
        if key in self._value_alias_cache:
            return self._value_alias_cache[key]
        merged = {attr: dict(m) for attr, m in self._common_value_aliases.items()}
        if key and key != "common":
            for attr, m in self._value_alias_map_for_section(key).items():
                merged.setdefault(attr, {}).update(m)
        self._value_alias_cache[key] = merged
        return merged

    def deprecated_for(self, component_type: str | None) -> dict[str, DeprecationInfo]:
        """``{attribute: DeprecationInfo}`` effective for *component_type*."""
        key = self.definition_key_for(component_type)
        if key in self._deprecated_cache:
            return self._deprecated_cache[key]
        merged = dict(self._common_deprecated)
        if key and key != "common":
            merged.update(self._deprecated_map_for_section(key))
        self._deprecated_cache[key] = merged
        return merged

    # ------------------------------------------------------------------
    # Internals

    def _section(self, key: str) -> dict[str, Any]:
        section = self._definitions.get(key)
        return section if isinstance(section, dict) else {}

    def _alias_map_for_section(self, key: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for canonical, spec in self._section(key).items():
            if not isinstance(spec, dict):
                continue
            aliases = spec.get("aliases")
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                if isinstance(alias, str) and alias and alias != canonical:
                    out[alias] = canonical
        return out

    def _value_alias_map_for_section(self, key: str) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for attr, spec in self._section(key).items():
            if not isinstance(spec, dict):
                continue
            value_aliases = spec.get("valueAliases")
            if not isinstance(value_aliases, dict):
                continue
            table = {
                alias: canonical
                for alias, canonical in value_aliases.items()
                if isinstance(alias, str)
                and isinstance(canonical, str)
                and alias
                and alias != canonical
            }
            if table:
                out[attr] = table
        return out

    def _deprecated_map_for_section(self, key: str) -> dict[str, DeprecationInfo]:
        out: dict[str, DeprecationInfo] = {}
        for attr, spec in self._section(key).items():
            if not isinstance(spec, dict):
                continue
            deprecated = spec.get("deprecated")
            if not deprecated:
                continue
            out[attr] = DeprecationInfo(
                scope=deprecated,
                note=str(spec.get("deprecation_note") or ""),
            )
        return out
