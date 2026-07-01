"""Thin re-export — implementation moved to ``jui_cli.core.normalizer``.

The style-merge logic was promoted from the hotloader to the shared
build-time normalizer (renderer SSoT plan, phase 05). Import from
``jui_cli.core.normalizer.style_merger`` in new code; this module only
keeps the historical import path working.
"""
from __future__ import annotations

from ..core.normalizer.style_merger import StyleMerger, _deep_merge

__all__ = ["StyleMerger", "_deep_merge"]
