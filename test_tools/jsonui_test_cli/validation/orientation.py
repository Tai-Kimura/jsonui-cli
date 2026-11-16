"""Top-level `orientation` field validation (screen tests and flow tests).

The value is checked here because a misspelling is otherwise invisible until
the run, and invisible in the direction that reads as success: an orientation
the driver does not recognise leaves the device in whatever orientation it was
already in, and every assertion in the file still passes — in the wrong
orientation. There is no timeout and no failing step to point at. The whole
reason this key exists is that "which orientation did this run verify?" was
not written down anywhere; a value nobody checks reintroduces exactly that.

Deliberately the same list as the `setOrientation` action and the responsive
constraint's `orientation` (`RESPONSIVE_ORIENTATIONS`): three sites naming
different value sets for one word would be the drift this repo's schema gate
exists to catch, one level below where that gate can see.
"""

from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import RESPONSIVE_ORIENTATIONS


def validate_orientation_field(value, path: str, result: ValidationResult):
    """Validate a test-level top-level 'orientation' value."""
    if not isinstance(value, str):
        result.errors.append(ValidationMessage(
            path=path,
            message=(
                f"'orientation' must be a string, got: {type(value).__name__} "
                f"(allowed: {', '.join(RESPONSIVE_ORIENTATIONS)})"
            )
        ))
        return
    if value not in RESPONSIVE_ORIENTATIONS:
        result.errors.append(ValidationMessage(
            path=path,
            message=(
                f"Unknown orientation: {value!r} (allowed: "
                f"{', '.join(RESPONSIVE_ORIENTATIONS)})"
            )
        ))
