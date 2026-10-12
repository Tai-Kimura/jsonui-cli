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
    - a method that collides with a var in the generated protocol
      (:func:`viewmodel_member_clashes`)
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

    errors.extend(viewmodel_member_clashes(vm.vars, vm.methods))

    if errors:
        joined = "\n  - ".join(errors)
        raise SpecValidationError(
            f"Spec '{spec.name}' failed validation:\n  - {joined}"
        )

    return warnings


def kotlin_accessor_names(var_name: str) -> tuple[str, str]:
    """(getter, setter) the JVM gets for a Kotlin property named *var_name*.

    A name that starts with ``is`` followed by anything but a lowercase
    letter keeps its name as the getter and drops the ``is`` for the setter
    (``isOpen`` → ``isOpen`` / ``setOpen``, ``is1`` → ``is1`` / ``set1``),
    whatever the type; every other name gets ``get`` / ``set`` plus the name
    with its first character upper-cased (``url`` → ``getUrl``, ``URL`` →
    ``getURL``, ``island`` → ``getIsland``). Measured with kotlinc 2.4.20
    (ticket jui-protocol-var-and-setter-method-clash-on-jvm).
    """
    if len(var_name) > 2 and var_name.startswith("is") and not var_name[2].islower():
        return var_name, "set" + var_name[2:]
    cap = var_name[:1].upper() + var_name[1:]
    return "get" + cap, "set" + cap


def viewmodel_member_clashes(vars_, methods) -> list[str]:
    """ERRORs for a viewModel method that the generated protocol cannot hold
    next to a var.

    - Android: a method named like a var's JVM getter with no parameters,
      or like its setter with one, is a "Platform declaration clash" in the
      Kotlin protocol. Only a plain ``var X: T`` (observable false, not
      readOnly) has a setter; ``val X: StateFlow<T>`` and ``val X: T`` have
      the getter only.
    - iOS: a method with the var's own name and no parameters is an
      "invalid redeclaration" in the Swift protocol.

    The rule compares names and parameter counts only, not types: a pair
    the compiler would accept because the types differ (``var count: Int``
    beside ``setCount(String)``) is refused too, so this never needs a
    second model of type erasure. An async method is ``suspend`` /
    ``async throws`` and collides with neither. Both members must reach the
    platform's protocol. The cases live in
    shared/core/viewmodel_member_clash_vectors.json, which the jsonui-doc
    validator answers as well.
    """
    from .protocol_sync import _resolve_method_platforms

    errors: list[str] = []
    for v in vars_:
        var_targets = resolve_platforms(v.platforms)
        getter, setter = kotlin_accessor_names(v.name)
        has_setter = not v.read_only and not v.observable
        for m in methods:
            if m.is_async:
                continue
            targets = set(var_targets) & set(_resolve_method_platforms(m.platforms))
            arity = len(m.params)
            if "android" in targets and (
                (m.name == getter and arity == 0)
                or (has_setter and m.name == setter and arity == 1)
            ):
                errors.append(
                    f"viewModel.methods['{m.name}'] has the JVM accessor name of "
                    f"viewModel.vars['{v.name}'] — on Android the property "
                    f"declares {m.name}() itself, so the generated Kotlin protocol "
                    "does not compile (Platform declaration clash). Rename the "
                    "method (or scope one of them with platforms)."
                )
            if "ios" in targets and m.name == v.name and arity == 0:
                errors.append(
                    f"viewModel.methods['{m.name}'] takes no arguments and has the "
                    f"name of viewModel.vars['{v.name}'] — the generated Swift "
                    f"protocol does not compile (invalid redeclaration of "
                    f"'{m.name}()'). Rename one of them (or scope one with "
                    "platforms)."
                )
    return errors


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
