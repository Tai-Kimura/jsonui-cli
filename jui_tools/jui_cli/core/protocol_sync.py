"""Merge spec.view_model (methods + vars) and Impl ``@jui:protocol`` markers
into an ordered list of Protocol members.

Used by the iOS / Android / Web generators and by
``build_cmd._sync_viewmodel_protocols``.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from .method_extractor import MarkerBlock, extract_marker_blocks
from .spec_extractor import MethodDef, ScreenSpec, VarDef
from .spec_validator import resolve_platforms


MethodSignatureBuilder = Callable[[MethodDef], str]
VarSignatureBuilder = Callable[[VarDef], str]


@dataclass
class SyncedMember:
    """One entry that should appear in the Protocol body."""

    name: str
    signature: str
    kind: str   # "method" | "var"
    source: str  # "spec" | "marker"


@dataclass
class SyncResult:
    methods: list[SyncedMember]
    vars: list[SyncedMember]
    missing_methods_in_impl: list[str]  # spec-declared methods with no Impl decl
    missing_vars_in_impl: list[str]     # spec-declared vars with no Impl decl
    method_override_conflicts: list[str]
    var_override_conflicts: list[str]


def default_method_signature(method: MethodDef, *, platform: str) -> str:
    """Platform-default signature for a ``view_model.methods`` entry."""
    params_str = ", ".join(f"{p.name}: {p.type}" for p in method.params)
    if platform == "ios":
        sig = f"func {method.name}({params_str})"
        if method.is_async:
            sig += " async throws"
        if method.return_type:
            sig += f" -> {method.return_type}"
        return sig
    if platform == "android":
        prefix = "suspend " if method.is_async else ""
        sig = f"{prefix}fun {method.name}({params_str})"
        if method.return_type:
            sig += f": {method.return_type}"
        return sig
    if platform == "web":
        ret = method.return_type or "void"
        if method.is_async:
            ret = f"Promise<{method.return_type or 'void'}>"
        return f"{method.name}({params_str}): {ret}"
    raise ValueError(f"unknown platform {platform!r}")


def default_var_signature(var: VarDef, *, platform: str) -> str:
    """Platform-default signature for a ``view_model.vars`` entry (Protocol side)."""
    if platform == "ios":
        type_str = _swift_optional(var.type, var.optional)
        accessors = "{ get }" if var.read_only else "{ get set }"
        return f"var {var.name}: {type_str} {accessors}"
    if platform == "android":
        type_str = _kotlin_optional(var.type, var.optional)
        keyword = "val" if var.read_only else "var"
        return f"{keyword} {var.name}: {type_str}"
    if platform == "web":
        readonly = "readonly " if var.read_only else ""
        opt = "?" if var.optional else ""
        return f"{readonly}{var.name}{opt}: {var.type}"
    raise ValueError(f"unknown platform {platform!r}")


def _swift_optional(type_str: str, optional: bool) -> str:
    """Append Swift ``?`` to *type_str*, wrapping closure types in parens."""
    if not optional:
        return type_str
    # Already optional-suffixed (spec authored with `String?`): don't double up.
    if type_str.endswith("?"):
        return type_str
    # Closure types need parens: `() -> Void` → `(() -> Void)?`
    if "->" in type_str and not (type_str.startswith("(") and type_str.endswith(")")):
        return f"({type_str})?"
    return f"{type_str}?"


def _kotlin_optional(type_str: str, optional: bool) -> str:
    """Append Kotlin ``?`` to *type_str*, wrapping lambdas in parens."""
    if not optional:
        return type_str
    if type_str.endswith("?"):
        return type_str
    # Lambda types need parens: `() -> Unit` → `(() -> Unit)?`
    if "->" in type_str and not (type_str.startswith("(") and type_str.endswith(")")):
        return f"({type_str})?"
    return f"{type_str}?"


def collect_protocol_members(
    spec: ScreenSpec,
    *,
    platform: str,
    impl_source: str | None,
    impl_method_names: set[str] | None = None,
    impl_var_names: set[str] | None = None,
    method_signature_builder: MethodSignatureBuilder | None = None,
    var_signature_builder: VarSignatureBuilder | None = None,
) -> SyncResult:
    """Build ordered method/var lists for the Protocol/Base body.

    Order:
    1. spec entries in spec order (filtered by ``platforms``)
    2. Marker-only entries in Impl order (not in spec)

    Duplicates (spec + marker with same name) → marker wins, spec entry is
    dropped with an info log.

    Consistency:
    - spec-declared methods/vars whose name is missing from
      ``impl_method_names`` / ``impl_var_names`` are reported for the caller
      to surface as ERRORs.
    """
    vm = spec.view_model

    # ---- methods ----
    spec_methods: list[SyncedMember] = []
    missing_methods: list[str] = []
    for m in vm.methods:
        target = _resolve_method_platforms(m.platforms)
        if platform not in target:
            continue
        sig = method_signature_builder(m) if method_signature_builder else \
            default_method_signature(m, platform=platform)
        spec_methods.append(SyncedMember(
            name=m.name, signature=sig, kind="method", source="spec",
        ))
        if impl_method_names is not None and m.name not in impl_method_names:
            missing_methods.append(m.name)

    # ---- vars ----
    spec_vars: list[SyncedMember] = []
    missing_vars: list[str] = []
    for v in vm.vars:
        target = resolve_platforms(v.platforms)
        if platform not in target:
            continue
        sig = var_signature_builder(v) if var_signature_builder else \
            default_var_signature(v, platform=platform)
        spec_vars.append(SyncedMember(
            name=v.name, signature=sig, kind="var", source="spec",
        ))
        if impl_var_names is not None and v.name not in impl_var_names:
            missing_vars.append(v.name)

    # ---- markers ----
    marker_methods: list[SyncedMember] = []
    marker_vars: list[SyncedMember] = []
    if impl_source:
        for blk in extract_marker_blocks(impl_source):
            name = _marker_member_name(blk)
            if name is None:
                continue
            entry = SyncedMember(
                name=name, signature=blk.signature,
                kind=blk.kind, source="marker",
            )
            if blk.kind == "var":
                marker_vars.append(entry)
            else:
                marker_methods.append(entry)

    methods = _merge_members(spec.name, spec_methods, marker_methods, "method")
    vars_ = _merge_members(spec.name, spec_vars, marker_vars, "var")

    return SyncResult(
        methods=methods[0],
        vars=vars_[0],
        missing_methods_in_impl=missing_methods,
        missing_vars_in_impl=missing_vars,
        method_override_conflicts=methods[1],
        var_override_conflicts=vars_[1],
    )


def _resolve_method_platforms(platforms: list[str]) -> tuple[str, ...]:
    """``MethodDef.platforms`` convention: empty list means all platforms
    (kept from existing Repository/UseCase behaviour)."""
    if not platforms:
        return ("ios", "android", "web")
    return tuple(platforms)


def _merge_members(
    spec_name: str,
    spec_entries: list[SyncedMember],
    marker_entries: list[SyncedMember],
    label: str,
) -> tuple[list[SyncedMember], list[str]]:
    marker_name_set = {e.name for e in marker_entries}
    override_conflicts: list[str] = []
    merged: list[SyncedMember] = []
    for entry in spec_entries:
        if entry.name in marker_name_set:
            override_conflicts.append(entry.name)
            print(
                f"INFO [protocol-sync] {spec_name}: {label} '{entry.name}' from "
                "spec overridden by marker (using marker signature)",
                file=sys.stderr,
            )
            continue
        merged.append(entry)
    merged.extend(marker_entries)
    return merged, override_conflicts


def _marker_member_name(blk: MarkerBlock) -> str | None:
    """Extract the identifier from a marker's raw signature."""
    import re
    flat = " ".join(line.strip() for line in blk.signature.splitlines() if line.strip())
    # Swallow leading attributes.
    while flat.startswith("@"):
        m = re.match(r"@\w+(?:\([^)]*\))?\s*", flat)
        if not m:
            break
        flat = flat[m.end():]
    # Strip leading modifiers.
    flat = re.sub(
        r"^(?:(?:public|internal|private|protected|fileprivate|open|abstract|"
        r"override|suspend|inline|operator|infix|tailrec|static|class|final|"
        r"lateinit)\s+)+",
        "",
        flat,
    )
    if blk.kind == "var":
        m = re.match(r"(?:var|val|let)\s+(\w+)", flat)
    else:
        m = re.match(r"(?:func|fun)\s+(?:<[^>]+>\s+)?(\w+)", flat)
    return m.group(1) if m else None


def list_impl_method_names(impl_source: str) -> set[str]:
    """Names of every top-level ``func``/``fun`` in *impl_source*."""
    import re
    pattern = re.compile(
        r"^[ \t]*"
        r"(?:(?:public|internal|private|protected|fileprivate|open)\s+)?"
        r"(?:override\s+)?"
        r"(?:(?:suspend|static|class|final|inline|operator|infix|tailrec)\s+)*"
        r"(?:override\s+)?"
        r"(?:(?:suspend|static|class|final)\s+)*"
        r"(?:func|fun)\s+(?:<[^>]+>\s+)?(\w+)",
        re.MULTILINE,
    )
    return {m.group(1) for m in pattern.finditer(impl_source)}


def list_impl_var_names(impl_source: str) -> set[str]:
    """Names of every top-level ``var``/``val``/``let`` in *impl_source*.

    Swallows property wrappers (``@Published var x``) and access modifiers.
    """
    import re
    pattern = re.compile(
        r"^[ \t]*"
        r"(?:@\w+(?:\([^)]*\))?\s+)*"
        r"(?:(?:public|internal|private|protected|fileprivate|open)\s+)?"
        r"(?:override\s+)?"
        r"(?:(?:lateinit|abstract|open|final|static|class)\s+)*"
        r"(?:override\s+)?"
        r"(?:var|val|let)\s+(\w+)",
        re.MULTILINE,
    )
    return {m.group(1) for m in pattern.finditer(impl_source)}
