"""Condition- and case-level `responsive` field validation.

The schema shape (actions.schema.json#/definitions/responsive, referenced by
the condition object and by screen-test case objects) is either a named
size-class bucket string — the render-side canonical vocabulary from
shared/core/responsive_resolver.rb (compact/medium/regular/landscape +
hyphenated combos) — or a constraint object (minWidth/maxWidth/minHeight/
maxHeight/orientation, keys ANDed, at least one key). Resolved at runtime by
each driver; the validator only guards the shape and rejects contradictions
(min > max), mirroring the guards `platform` already has.
"""

from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import (
    RESPONSIVE_BUCKETS,
    RESPONSIVE_CONSTRAINT_KEYS,
    RESPONSIVE_ORIENTATIONS,
)

# (min, max) width/height pairs that must not contradict each other
_MIN_MAX_PAIRS = [("minWidth", "maxWidth"), ("minHeight", "maxHeight")]


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_responsive_field(value, path: str, result: ValidationResult):
    """Validate a condition or case-level 'responsive' value."""
    if isinstance(value, str):
        if value not in RESPONSIVE_BUCKETS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Invalid responsive bucket: {value}. Must be one of: {RESPONSIVE_BUCKETS}"
            ))
    elif isinstance(value, dict):
        if len(value) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"'responsive' constraint object must have at least one key ({RESPONSIVE_CONSTRAINT_KEYS})"
            ))
            return

        for key in value.keys():
            if key not in RESPONSIVE_CONSTRAINT_KEYS:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Unknown responsive constraint key: {key}. Must be one of: {RESPONSIVE_CONSTRAINT_KEYS}"
                ))

        for key in ("minWidth", "maxWidth", "minHeight", "maxHeight"):
            if key in value and (not _is_number(value[key]) or value[key] < 0):
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Responsive '{key}' must be a number >= 0, got: {value[key]!r}"
                ))

        if "orientation" in value and value["orientation"] not in RESPONSIVE_ORIENTATIONS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Invalid responsive orientation: {value['orientation']!r}. "
                        f"Must be one of: {RESPONSIVE_ORIENTATIONS}"
            ))

        # Contradiction guard: min must not exceed max (same style as platform's guards)
        for min_key, max_key in _MIN_MAX_PAIRS:
            if min_key in value and max_key in value:
                low, high = value[min_key], value[max_key]
                if _is_number(low) and _is_number(high) and low > high:
                    result.errors.append(ValidationMessage(
                        path=path,
                        message=f"Responsive '{min_key}' ({low}) must not exceed '{max_key}' ({high})"
                    ))
    else:
        result.errors.append(ValidationMessage(
            path=path,
            message=f"'responsive' must be a bucket name string or constraint object, got: {type(value).__name__}"
        ))
