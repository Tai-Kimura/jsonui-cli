"""Validator for JsonUI test files.

This module re-exports from the validation package for backwards compatibility.
"""

from .validation import (
    ValidationMessage,
    ValidationResult,
    TestValidator,
)

__all__ = [
    "ValidationMessage",
    "ValidationResult",
    "TestValidator",
]
