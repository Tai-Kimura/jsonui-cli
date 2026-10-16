"""`initialState`: what a test file asks to be put into a screen's Data.

Contract: jsonui-test-runner spec §10 (specs/2026-07-08-advanced-test-features.md)
and its vectors — initial-state-payload.json (which files are errors and
warnings, by code) and initial-state-coercion.json (which values a Data class
accepts), both vendored into shared/core/.
"""

from __future__ import annotations


def is_empty(value) -> bool:
    """An initialState that delivers nothing: `{}`, `{"viewModel": {}}`,
    `{"viewModels": {}}`. Spec §10.2: the same as none — no payload, no
    launch, nothing for a driver to read or to ignore.

    Anything else counts as written, a malformed value included: its shape
    is the shape check's finding, not a reason to treat it as absent.
    """
    return isinstance(value, dict) and all(v == {} for v in value.values())
