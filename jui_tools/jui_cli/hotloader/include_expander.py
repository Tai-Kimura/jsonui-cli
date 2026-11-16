"""Thin re-export — implementation moved to ``jui_cli.core.normalizer``.

The include-expansion logic was promoted from the hotloader to the
shared build-time normalizer (renderer SSoT plan, phase 05). Import from
``jui_cli.core.normalizer.include_expander`` in new code; this module
only keeps the historical import path working.
"""
from __future__ import annotations

from ..core.normalizer.include_expander import (
    BINDING_RE,
    IncludeExpander,
    _apply_id_prefix,
    _combine_with_prefix,
    _derive_prefix,
    _to_camel_case,
)

__all__ = [
    "BINDING_RE",
    "IncludeExpander",
    "_apply_id_prefix",
    "_combine_with_prefix",
    "_derive_prefix",
    "_to_camel_case",
]
