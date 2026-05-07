"""Spec validation helpers.

Validates ScreenSpec after extraction. Raises SpecValidationError on hard
errors; returns a list of warnings for soft issues so callers can decide
how to surface them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .spec_extractor import ScreenSpec


VALID_PLATFORMS = ("ios", "android", "web")

# Catches `"Bool (computed)"` / `"String (localized)"` — free-form human
# annotations smuggled into the type field. Lowercase-only inside so it
# doesn't flag generics like `Map(String, String)`.
_ANNOTATION_SUFFIX_RE = re.compile(r"\s*\([a-z][a-z_\-\s]*\)\s*\??\s*$")


class SpecValidationError(Exception):
    """Raised when a spec violates a required invariant."""


@dataclass
class SpecWarning:
    spec_name: str
    message: str


def validate_screen_spec(spec: ScreenSpec) -> list[SpecWarning]:
    """Validate a ScreenSpec. Returns warnings; raises on ERRORs.

    Checks:
    - viewModel.methods[].platforms — invalid values → ERROR, `[]` → WARNING
    - viewModel.vars[].platforms    — invalid values → ERROR, `[]` → WARNING
    - vars[].name uniqueness within the viewModel
    - methods[].name uniqueness within the viewModel
    """
    warnings: list[SpecWarning] = []
    errors: list[str] = []

    # --- UI Variables — annotation-suffix check ---
    for v in spec.ui_variables:
        if _ANNOTATION_SUFFIX_RE.search(v.type or ""):
            errors.append(
                f"uiVariables['{v.name}'].type = {v.type!r} — trailing "
                "annotation like '(computed)' / '(localized)' is not a real "
                "type. Use description/notes for human metadata; for computed "
                "properties declare on the ViewModel Impl as a `var` getter."
            )

    vm = spec.view_model

    method_names: set[str] = set()
    for m in vm.methods:
        if m.name in method_names:
            errors.append(f"viewModel.methods has duplicate name '{m.name}'")
        method_names.add(m.name)
        for err in _platform_errors(f"viewModel.methods['{m.name}']", m.platforms):
            errors.append(err)
        for err in _annotation_suffix_errors(
            f"viewModel.methods['{m.name}']", m
        ):
            errors.append(err)
        # MethodDef convention: empty list == "all platforms" (preserved from
        # Repository/UseCase use). Don't warn on [] here.

    var_names: set[str] = set()
    for v in vm.vars:
        if v.name in var_names:
            errors.append(f"viewModel.vars has duplicate name '{v.name}'")
        var_names.add(v.name)
        for err in _platform_errors(f"viewModel.vars['{v.name}']", v.platforms):
            errors.append(err)
        for warn in _platform_warnings(spec.name, f"viewModel.vars['{v.name}']", v.platforms):
            warnings.append(warn)
        if _ANNOTATION_SUFFIX_RE.search(v.type or ""):
            errors.append(
                f"viewModel.vars['{v.name}'].type = {v.type!r} — trailing "
                "annotation like '(computed)' is not a real type. Remove the "
                "annotation; for computed state declare a Swift/Kotlin "
                "computed property on the ViewModel Impl instead."
            )
        if v.read_only and v.observable is False and not v.type:
            errors.append(
                f"viewModel.vars['{v.name}'] must declare a 'type' "
                "(readOnly + non-observable still needs the protocol type)"
            )

    if errors:
        joined = "\n  - ".join(errors)
        raise SpecValidationError(
            f"Spec '{spec.name}' failed validation:\n  - {joined}"
        )

    return warnings


def _annotation_suffix_errors(path: str, method) -> Iterable[str]:
    """Flag ``(lowercase)`` suffix annotations on method params / returnType."""
    errs = []
    for p in getattr(method, "params", []) or []:
        if _ANNOTATION_SUFFIX_RE.search(p.type or ""):
            errs.append(
                f"{path}.params['{p.name}'].type = {p.type!r} — trailing "
                "annotation like '(computed)' is not a real type; drop it."
            )
    ret = getattr(method, "return_type", "") or ""
    if _ANNOTATION_SUFFIX_RE.search(ret):
        errs.append(
            f"{path}.returnType = {ret!r} — trailing annotation like "
            "'(computed)' is not a real type; drop it."
        )
    return errs


def _platform_errors(path: str, platforms: list[str] | None) -> Iterable[str]:
    if platforms is None:
        return []
    if not isinstance(platforms, list):
        return [f"{path}.platforms must be an array"]
    invalid = [p for p in platforms if p not in VALID_PLATFORMS]
    if invalid:
        return [
            f"{path}.platforms contains invalid values {invalid!r}; "
            f"allowed: {list(VALID_PLATFORMS)}"
        ]
    return []


def _platform_warnings(
    spec_name: str, path: str, platforms: list[str] | None
) -> Iterable[SpecWarning]:
    if isinstance(platforms, list) and not platforms:
        return [SpecWarning(
            spec_name=spec_name,
            message=(
                f"{path}.platforms is [] — member will not be auto-imported "
                "into any ViewModel Protocol."
            ),
        )]
    return []


def resolve_platforms(platforms: list[str] | None) -> tuple[str, ...]:
    """Normalize a member's ``platforms`` field into the effective target set.

    ``None`` → all platforms. Explicit list → verbatim (already validated).
    """
    if platforms is None:
        return VALID_PLATFORMS
    return tuple(platforms)


def emit_warnings(warnings: Iterable[SpecWarning], *, prefix: str = "WARNING") -> None:
    """Print warnings to stderr in a uniform format."""
    import sys
    for w in warnings:
        print(f"{prefix} [spec:{w.spec_name}] {w.message}", file=sys.stderr)
