"""The `required` half of the canonical schemas.

Each test schema declares two things about a document's shape:
`additionalProperties: false` and `required`. Only the first was
implemented as an error — missing keys came out as warnings, and a flow
test's `metadata` produced nothing at all — so a file holding nothing but
`{"type": "screen"}` validated clean. That file names no screen and
asserts nothing.

The half that worked is what made this hard to see. A reader who watches
unknown keys get rejected has no reason to suspect that missing ones are
not: **one declaration being enforced looks like evidence that its
neighbour is.**

The list itself lives in `schema.py` beside the other vocabulary
constants, and `test_required_fields_are_enforced` walks it against the
vendored schemas in both directions — so a key added to a schema's
`required` cannot reach a release either unchecked or undeclared.
"""
from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import REQUIRED_TOP_LEVEL_KEYS


#: Keys whose absence changes how the RUNNER behaves, not only what the
#: document records. Filling one in is not metadata housekeeping, and an
#: error that reads like housekeeping gets acted on as if it were — the
#: consumer would find out at the next run, from a timeout that names the
#: screen rather than the edit.
#:
#: Only `source` is in here, and the control test says so: a sentence
#: appended to every message is a sentence nobody reads.
_RUNTIME_CONSEQUENCE = {
    ("screen", "source"): (
        " — note that `source.layout` is also the readiness input: under the "
        "default `screenReady: auto` the runner derives the screen id from "
        "it, and a test with no `source` falls back to the `networkidle` "
        "gate. Adding it switches that file to waiting for a screen marker, "
        "which a production build does not emit. A suite running against a "
        "production build needs `screenReady: 'networkidle'` (or `'none'`) "
        "on those files — driver 1.8.4 and later."
    ),
}


def check_required_top_level(
    data: dict, test_type: str, path: str, result: ValidationResult,
) -> None:
    """Report every `required` top-level key this document does not have."""
    for key in REQUIRED_TOP_LEVEL_KEYS.get(test_type, []):
        if key not in data:
            result.errors.append(ValidationMessage(
                path=path,
                message=(f"Missing required top-level key '{key}'"
                         + _RUNTIME_CONSEQUENCE.get((test_type, key), "")),
            ))
