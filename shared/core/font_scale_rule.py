"""The font scaling rule's Python reference (ticket sjui-label-font-size-ignores-dynamic-type, ruling 2026-11-13).

shared/core/font_scale_vectors.json is the contract each face's runtime reads for `fontScaling` / `maxFontScale`:
SwiftJsonUI, KotlinJsonUI and rjui size a component's text by it. This module is the same rule written once in Python,
pinned against the vectors by jui_tools/tests/test_font_scale_vectors.py, so a vector that contradicts its own rule
text is caught where it is written. No face imports it.

The ruling: every text follows the OS / browser text size unless it (or the app default) says `fontScaling: false`;
`maxFontScale` caps the drawn size at fontSize x maxFontScale. `scale` below is what the system would multiply this
size by: on Android 14+ that factor is non-linear (it depends on the size), so a face passes the factor its own
conversion gives for this size; iOS and the web pass one factor for every size.
"""
from __future__ import annotations

from collections.abc import Mapping


def follows(declared: bool | None, app_default: bool = True) -> bool:
    """Whether the component's text follows the text size: its own declaration, else the app default."""
    return app_default if declared is None else bool(declared)


def drawn(size: float, scale: float, declared: bool | None = None, max_scale: float | None = None,
          app_default: bool = True) -> float:
    """The size the text is drawn at: *size* when it does not follow; size x scale, capped at size x max_scale."""
    if not follows(declared, app_default):
        return size
    factor = scale if max_scale is None else min(scale, max_scale)
    return size * factor


def ios_cap_step(max_scale: float | None, ratios: Mapping[str, float]) -> str:
    """iOS: the Dynamic Type step a cap rounds down to -- the largest step whose ratio is at most *max_scale*.

    *ratios* is each step's .body ratio on the running OS (UIFontMetrics), in order from the standard size up. No cap:
    the largest step. A cap below every step above the standard one: the standard step.
    """
    steps = list(ratios)
    if max_scale is None:
        return steps[-1]
    fitting = [s for s in steps if ratios[s] <= max_scale + 1e-9]
    return fitting[-1] if fitting else steps[0]
