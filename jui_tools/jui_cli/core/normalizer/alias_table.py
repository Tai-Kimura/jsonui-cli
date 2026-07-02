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


# Node ``type`` spellings that map onto a different top-level definition
# key. Mirrors the union of the ``map_type_to_definition`` tables in
# {s,k,r}jui_tools/lib/core/attribute_validator.rb, minus spellings that
# already exist as top-level keys in attribute_definitions.json (exact
# key match always wins).
_TYPE_SYNONYMS = {
    "Text": "Label",
    "MultiLineEditText": "TextView",
    "ImageView": "Image",
    "NetworkImageView": "NetworkImage",
    "CircleImage": "NetworkImage",
    "CircleImageView": "NetworkImage",
    "Spinner": "SelectBox",
    "DatePicker": "SelectBox",
    "SegmentedControl": "Segment",
    "SeekBar": "Slider",
    "ProgressBar": "Progress",
    "LinearLayout": "View",
    "RelativeLayout": "View",
    "FrameLayout": "View",
    "HStack": "View",
    "VStack": "View",
    "ZStack": "View",
    "Scroll": "ScrollView",
    "CollectionView": "Collection",
    "RecyclerView": "Collection",
    "Table": "Collection",
    "TableView": "Collection",
    "RadioButton": "Radio",
    "ActivityIndicator": "Indicator",
    "BlurView": "Blur",
    "WebView": "Web",
}

_DEFINITIONS_RELPATH = Path("shared") / "core" / "attribute_definitions.json"


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
    """Locate ``shared/core/attribute_definitions.json`` relative to the
    installed tool tree (jui_tools/ and shared/ are siblings)."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _DEFINITIONS_RELPATH
        if candidate.exists():
            return candidate
    return None


class AliasTable:
    """Per-component alias → canonical maps plus deprecation metadata."""

    def __init__(self, definitions: dict[str, Any]):
        self._definitions = definitions or {}
        self._common_aliases = self._alias_map_for_section("common")
        self._common_deprecated = self._deprecated_map_for_section("common")
        # component key -> cached maps
        self._alias_cache: dict[str | None, dict[str, str]] = {}
        self._deprecated_cache: dict[str | None, dict[str, DeprecationInfo]] = {}

    # ------------------------------------------------------------------
    # Construction

    @classmethod
    def from_file(cls, path: Path | str | None = None) -> "AliasTable":
        """Load from *path*, defaulting to the bundled SSoT definitions.

        Missing / unreadable file degrades to an empty table (normalizer
        becomes a marker-only pass) rather than failing the build.
        """
        resolved = Path(path) if path else default_definitions_path()
        if resolved is None or not resolved.exists():
            return cls({})
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                return cls(json.load(f))
        except (OSError, json.JSONDecodeError):
            return cls({})

    # ------------------------------------------------------------------
    # Lookup

    def definition_key_for(self, component_type: str | None) -> str | None:
        """Map a node ``type`` value to its definition key (exact match
        first, then cross-platform type synonyms)."""
        if not component_type:
            return None
        if component_type in self._definitions:
            return component_type
        return _TYPE_SYNONYMS.get(component_type)

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
