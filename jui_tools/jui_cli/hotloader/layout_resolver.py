"""Read a layout JSON from disk and produce a flat, platform-ready dict.

Pipeline:
    raw layout JSON
      → StyleMerger.resolve         (resolve "style" references)
      → IncludeExpander.expand      (inline-expand "include" + id prefix)
      → filter_for_platform         (merge "platform" overrides, drop mismatched)
      → flat JSON ready for the runtime renderer
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .include_expander import IncludeExpander
from .platform_filter import filter_for_platform
from .style_merger import StyleMerger


class LayoutResolver:
    def __init__(self, layouts_dir: Path, styles_dir: Path):
        self._layouts_dir = layouts_dir
        self._style_merger = StyleMerger(styles_dir)
        self._include_expander = IncludeExpander(layouts_dir, self._style_merger)

    @property
    def layouts_dir(self) -> Path:
        return self._layouts_dir

    def resolve(self, layout_name: str, platform: str) -> dict[str, Any] | None:
        """Resolve ``<layouts_dir>/<layout_name>.json`` for *platform*.

        ``layout_name`` may contain forward slashes for subdirectories
        (``"home/home_header"`` → ``<layouts_dir>/home/home_header.json``).
        Returns ``None`` when the file is missing.
        """
        path = self._path_for(layout_name)
        if path is None or not path.exists():
            return None
        raw = self._read_json(path)
        if raw is None:
            return None
        merged = self._style_merger.resolve(copy.deepcopy(raw))
        expanded = self._include_expander.expand(merged)
        filtered = filter_for_platform(expanded, platform)
        return filtered

    def invalidate_styles(self, style_name: str | None = None) -> None:
        self._style_merger.invalidate(style_name)

    def layout_name_for_path(self, file_path: Path) -> str | None:
        """Convert an absolute path inside ``layouts_dir`` back to a layout name."""
        try:
            rel = file_path.resolve().relative_to(self._layouts_dir)
        except ValueError:
            return None
        if rel.suffix != ".json":
            return None
        return str(rel.with_suffix("")).replace("\\", "/")

    def style_name_for_path(self, file_path: Path, styles_dir: Path) -> str | None:
        try:
            rel = file_path.resolve().relative_to(styles_dir)
        except ValueError:
            return None
        if rel.suffix != ".json":
            return None
        return str(rel.with_suffix("")).replace("\\", "/")

    def _path_for(self, layout_name: str) -> Path | None:
        safe = layout_name.lstrip("/").replace("..", "")
        return self._layouts_dir / f"{safe}.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
