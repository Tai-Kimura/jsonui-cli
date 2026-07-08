"""Validation result models."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ValidationMessage:
    """Represents a validation error or warning."""
    path: str
    message: str
    level: str = "error"  # "error" or "warning"

    def __str__(self):
        prefix = "ERROR" if self.level == "error" else "WARN"
        return f"  [{prefix}] {self.path}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validating a test file."""
    file_path: Path
    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)
    test_data: dict | None = None

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)
