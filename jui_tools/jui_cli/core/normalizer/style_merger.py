"""Resolve ``style`` references on layout nodes.

A node may declare ``"style": "foo"`` which refers to a JSON file at
``<styles_dir>/foo.json``. The style file's fields form the base, and
the node's own fields override. This mirrors
``sjui_tools/lib/swiftui/style_loader.rb`` — deep merge with arrays
replaced (not concatenated), ``type`` from the style skipped when the
node already specifies its own.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


#: The sentence every path says for a ``style`` named inside a responsive
#: override (the shared validator, SwiftJsonUI Dynamic's ResponsiveResolver).
STYLE_IN_RESPONSIVE_OVERRIDE = (
    "'style' inside a responsive override is not applied — put the attributes in the override"
)


class StyleMerger:
    """Resolves ``style`` references recursively across a layout tree.

    Not inside a ``responsive`` override: an override's attributes are its
    own, and no path applies a style named there (4f's ruling on
    control-onclick-is-called-differently-on-every-path's style family,
    1.9.0 — sjui / kjui codegen, rjui and both Dynamic runtimes do not). It
    is dropped from the override and named once in :attr:`warnings`. This
    merger applied it, so the hotloader drew what no build draws.
    """

    def __init__(self, styles_dir: Path):
        self._styles_dir = styles_dir
        self._cache: dict[str, dict[str, Any] | None] = {}
        self.warnings: list[str] = []

    def resolve(self, component: Any) -> Any:
        if not isinstance(component, dict):
            return component

        # Style merge at this node
        if "style" in component:
            style_name = component["style"]
            style_data = self._load_style(style_name)
            component_without_style = {k: v for k, v in component.items() if k != "style"}
            if style_data is not None:
                base = dict(style_data)
                if "type" in component_without_style and "type" in base:
                    base.pop("type", None)
                component = _deep_merge(base, component_without_style)
            else:
                component = component_without_style

        # Recurse into children under "child" or "children"
        for child_key in ("child", "children"):
            if child_key in component:
                value = component[child_key]
                if isinstance(value, list):
                    component[child_key] = [self.resolve(c) for c in value]
                else:
                    component[child_key] = self.resolve(value)

        # Also recurse into any dict/list attribute values so nested style
        # references (e.g. inside `data` arrays) are resolved.
        for key, value in list(component.items()):
            if key in ("child", "children"):
                continue
            if key == "responsive" and isinstance(value, dict):
                component[key] = self._without_override_styles(value)
                continue
            if isinstance(value, dict):
                component[key] = self.resolve(value)
            elif isinstance(value, list):
                component[key] = [
                    self.resolve(v) if isinstance(v, dict) else v for v in value
                ]

        return component

    def _without_override_styles(self, responsive: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for size_class, override in responsive.items():
            if isinstance(override, dict) and "style" in override:
                override = {k: v for k, v in override.items() if k != "style"}
                if STYLE_IN_RESPONSIVE_OVERRIDE not in self.warnings:
                    self.warnings.append(STYLE_IN_RESPONSIVE_OVERRIDE)
            out[size_class] = self.resolve(override) if isinstance(override, dict) else override
        return out

    def _load_style(self, style_name: str) -> dict[str, Any] | None:
        if style_name in self._cache:
            return self._cache[style_name]
        path = self._styles_dir / f"{style_name}.json"
        if not path.exists():
            self._cache[style_name] = None
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._cache[style_name] = None
            return None
        self._cache[style_name] = data
        return data

    def invalidate(self, style_name: str | None = None) -> None:
        if style_name is None:
            self._cache.clear()
        else:
            self._cache.pop(style_name, None)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
