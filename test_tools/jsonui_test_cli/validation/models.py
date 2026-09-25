"""Validation result models."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ValidationMessage:
    """Represents a validation error or warning."""
    path: str
    message: str
    level: str = "error"  # "error", "warning" or "info" (printed, never counted)
    #: Optional machine-readable tag, for callers that must act on a class of
    #: message rather than display it. Set on the platform-constraint warnings
    #: so the CLI can say "a project-level declaration would have silenced
    #: these" without matching on wording — the message text is for humans and
    #: is expected to change.
    kind: str = ""

    def __str__(self):
        prefix = {"error": "ERROR", "info": "INFO"}.get(self.level, "WARN")
        return f"  [{prefix}] {self.path}: {self.message}"


@dataclass
class ValidationResult:
    """Result of validating a test file."""
    file_path: Path
    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)
    #: Reported and not counted: they never change `Warnings:` or the exit.
    infos: list[ValidationMessage] = field(default_factory=list)
    test_data: dict | None = None
    #: The element ids the steps name, by what the layout says of them
    #: (`validation.element_ids`): named = on_layout + missing + cannot_check
    #: + not_checked.
    element_ids: Counter = field(default_factory=Counter)
    #: Why none of this file's element ids could be checked ("" when they were).
    element_ids_unchecked_why: str = ""

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)
