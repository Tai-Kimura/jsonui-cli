"""Test- and case-level `platform` field validation.

The schema shape (screen-test.schema.json / flow-test.schema.json) is a scalar
`ios|android|web|all`, or an array whose items are `ios|android|web` — `all` is
not a legal array item. Deliberately NOT validated against SUPPORTED_PLATFORMS:
that list also contains `ios-swiftui` / `ios-uikit`, which the schema forbids
here, and reusing it would make the validator more permissive than the schema.
"""

from __future__ import annotations

from .models import ValidationMessage, ValidationResult
from ..schema import CONDITION_PLATFORMS, CONDITION_PLATFORM_ARRAY_ITEMS


def validate_platform_field(value, path: str, result: ValidationResult):
    """Validate a test-level or case-level 'platform' value."""
    if isinstance(value, str):
        if value not in CONDITION_PLATFORMS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Invalid platform: {value}. Must be one of: {CONDITION_PLATFORMS}"
            ))
    elif isinstance(value, list):
        if len(value) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message="'platform' array must not be empty"
            ))
        for item in value:
            if item not in CONDITION_PLATFORM_ARRAY_ITEMS:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Invalid platform: {item}. Must be one of: {CONDITION_PLATFORM_ARRAY_ITEMS}"
                ))
    else:
        result.errors.append(ValidationMessage(
            path=path,
            message=f"'platform' must be a string or array, got: {type(value).__name__}"
        ))
