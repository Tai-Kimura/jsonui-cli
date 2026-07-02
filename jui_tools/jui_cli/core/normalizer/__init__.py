"""Layout JSON normalizer — build-time SSoT for alias / style / include /
platform semantics (renderer SSoT plan, phase 05).

Normalization levels (shared terminology from the master plan):

- **L0 (raw)**: the layout exactly as authored. Never rewritten on disk.
- **L1 (canonical)**: alias → canonical attribute rewrite + deprecation
  warnings + ``$jui`` marker. ``style`` / ``include`` / ``platform`` are
  NOT resolved (codegen needs the include structure).
- **L2 (resolved)**: L1 + style merge + include expansion + platform
  filter. Matches what the hotloader serves at runtime.

Public API::

    from jui_cli.core.normalizer import normalize

    result = normalize(tree, "L1")                       # canonical
    result = normalize(tree, "L2", platform="ios",
                       styles_dir=..., layouts_dir=...)  # resolved
    result.tree      # normalized layout dict
    result.warnings  # list[str] (alias conflicts, deprecations)

The transform is idempotent: ``normalize(normalize(x)) == normalize(x)``.
This feature is **experimental** and opt-in via ``jui.config.json``:
``"build": {"normalizeLayouts": true}``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .alias_table import AliasTable, default_definitions_path
from .canonicalizer import MARKER_KEY, SCHEMA_VERSION, Canonicalizer, apply_marker
from .include_expander import IncludeExpander
from .platform_filter import filter_for_platform
from .style_merger import StyleMerger

__all__ = [
    "AliasTable",
    "Canonicalizer",
    "IncludeExpander",
    "MARKER_KEY",
    "NormalizeResult",
    "SCHEMA_VERSION",
    "StyleMerger",
    "apply_marker",
    "default_definitions_path",
    "filter_for_platform",
    "normalize",
]

LEVELS = ("L1", "L2")


@dataclass
class NormalizeResult:
    tree: Any
    level: str
    warnings: list[str] = field(default_factory=list)


def normalize(
    tree: Any,
    level: str = "L1",
    *,
    platform: str | None = None,
    styles_dir: Path | None = None,
    layouts_dir: Path | None = None,
    alias_table: AliasTable | None = None,
    source: str = "",
) -> NormalizeResult:
    """Normalize a layout *tree* to *level*. The input is never mutated.

    - ``L1``: alias canonicalization only (platform ignored).
    - ``L2``: requires *styles_dir* and *layouts_dir*; applies style merge
      and include expansion, then the platform filter when *platform* is
      given. The style/include/platform behavior is identical to the
      hotloader's :class:`~jui_cli.hotloader.layout_resolver.LayoutResolver`.
    """
    if level not in LEVELS:
        raise ValueError(f"Unknown normalization level {level!r}. Valid: {LEVELS}")
    if not isinstance(tree, dict):
        return NormalizeResult(tree=tree, level=level)

    canonicalizer = Canonicalizer(alias_table)

    if level == "L1":
        result, warnings = canonicalizer.canonicalize(tree, source=source)
        return NormalizeResult(tree=result, level="L1", warnings=warnings)

    # --- L2 ---
    if styles_dir is None or layouts_dir is None:
        raise ValueError("L2 normalization requires styles_dir and layouts_dir")

    working, warnings = canonicalizer.canonicalize(
        tree, source=source, add_marker=False
    )
    style_merger = StyleMerger(Path(styles_dir))
    include_expander = IncludeExpander(Path(layouts_dir), style_merger)
    working = style_merger.resolve(copy.deepcopy(working))
    working = include_expander.expand(working)
    if platform:
        working = filter_for_platform(working, platform)
    # Styles / includes may themselves use alias spellings — run a second
    # canonical pass on the fully resolved tree (idempotent; new warnings
    # only for attributes introduced by the resolution steps).
    working, resolve_warnings = canonicalizer.canonicalize(
        working, source=source, add_marker=False
    )
    for w in resolve_warnings:
        if w not in warnings:
            warnings.append(w)

    working = apply_marker(working, level="L2", platform=platform)
    return NormalizeResult(tree=working, level="L2", warnings=warnings)
