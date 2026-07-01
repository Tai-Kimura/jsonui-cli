"""Thin re-export — implementation moved to ``jui_cli.core.normalizer``.

The platform-filter wrapper was promoted from the hotloader to the
shared build-time normalizer (renderer SSoT plan, phase 05). Import from
``jui_cli.core.normalizer.platform_filter`` in new code; this module
only keeps the historical import path working.
"""
from __future__ import annotations

from ..core.normalizer.platform_filter import VALID_PLATFORMS, filter_for_platform

__all__ = ["VALID_PLATFORMS", "filter_for_platform"]
