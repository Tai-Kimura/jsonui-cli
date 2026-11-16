"""Do the calls a spec declares resolve to something a spec declares?

`dataFlow.useCases[].methods[].calls` names collaborators as
`Class.method`. Nothing checked they exist. The codegen does not read the
field, so `jui build` and `jui verify` stay green whatever it says — and
the HTML generator draws it as a reference, which makes an invented call
look authoritative on the published page.

One project declared `UserRepository.unregisterDeviceToken` for a call that
was never implemented. What makes this worth a gate rather than a note is
how it decays: a vocabulary rename (`device_token` → `installation_id`)
rewrites the phantom along with everything real, and a stale-looking name
becomes a current-looking one. Nobody suspects it again. The trigger is
ordinary, careful work.

CORPUS-WIDE BY CONSTRUCTION. A file-scoped version of this reports
`UserRepository.registerInstallationId` as unresolved when another spec
declares `UserRepository` — a real declaration called a phantom, which is
the worst possible output for a gate meant to find phantoms. A spec names
collaborators it does not itself declare, so the denominator is every spec
in the corpus. The scan therefore takes a root, never a file.

No language parsing: the judgment closes inside the specs. That keeps the
check honest about what it proves — a call resolving here means the SPEC
declares it, not that the implementation has it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .report import CheckReport, ResultItem


@dataclass
class Surface:
    """Every `Class.method` the corpus declares, and where each came from."""

    methods: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    #: spec files that contributed a declaration, for the report's inputs.
    sources: set[str] = field(default_factory=set)


def _iter_declared(doc: dict):
    """Yield (class_name, method_name) for repositories and use cases."""
    flow = doc.get("dataFlow")
    if not isinstance(flow, dict):
        return
    for key in ("repositories", "useCases"):
        entries = flow.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            yield name, None
            methods = entry.get("methods")
            if not isinstance(methods, list):
                continue
            for method in methods:
                if isinstance(method, dict) and isinstance(method.get("name"), str):
                    yield name, method["name"]


def _iter_calls(doc: dict):
    """Yield every `calls` entry, with the use case that declared it."""
    flow = doc.get("dataFlow")
    if not isinstance(flow, dict):
        return
    use_cases = flow.get("useCases")
    if not isinstance(use_cases, list):
        return
    for use_case in use_cases:
        if not isinstance(use_case, dict):
            continue
        owner = use_case.get("name") or "?"
        for method in use_case.get("methods") or []:
            if not isinstance(method, dict):
                continue
            for call in method.get("calls") or []:
                if isinstance(call, str) and call:
                    yield owner, method.get("name") or "?", call


def build_surface(spec_files, project_root: Path) -> Surface:
    """The resolution target set, gathered from the WHOLE corpus."""
    surface = Surface()
    for path in spec_files:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        contributed = False
        for class_name, method_name in _iter_declared(doc):
            surface.classes.add(class_name)
            contributed = True
            if method_name:
                surface.methods.add(f"{class_name}.{method_name}")
        if contributed:
            surface.sources.add(_rel(path, project_root))
    return surface


def _rel(path, project_root: Path) -> str:
    p = Path(path).resolve()
    root = Path(project_root).resolve()
    return str(p.relative_to(root)) if p.is_relative_to(root) else str(p)


def check_spec_calls(project_root: Path, spec_root: Path,
                     checker_name: str = "spec-calls") -> CheckReport:
    spec_files = sorted(Path(spec_root).rglob("*.spec.json"))
    surface = build_surface(spec_files, project_root)

    results: list[ResultItem] = []
    warnings: list[str] = []
    declared = 0

    for path in spec_files:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        for owner, method, call in _iter_calls(doc):
            declared += 1
            where = f"{_rel(path, project_root)}:{owner}.{method}"
            if call in surface.methods:
                results.append(ResultItem(
                    target=call, status="ok", confidence="proof",
                    message=f"declared by the corpus ({where})"))
                continue
            class_name = call.split(".", 1)[0]
            if class_name in surface.classes:
                detail = (f"'{class_name}' is declared but has no method "
                          f"'{call.split('.', 1)[-1]}'")
            else:
                detail = f"no spec declares '{class_name}'"
            results.append(ResultItem(
                target=call, status="missing_in_doc", confidence="proof",
                expected=f"a declaration of {call}", actual=detail,
                message=f"declared at {where}"))

    # An empty resolution surface cannot certify anything: with nothing to
    # resolve against, every call would report as missing and every corpus
    # with no calls would report as clean. Both are the same output as a
    # scan that found the wrong directory, so it is said out loud instead.
    if not spec_files:
        warnings.append(
            f"no spec files under {_rel(spec_root, project_root)} — nothing "
            "was scanned, which is NOT the same as nothing being wrong")
    elif not surface.methods:
        warnings.append(
            f"{len(spec_files)} spec file(s) scanned but none declares a "
            "repository or use-case method — there was nothing to resolve "
            "against, so a clean result here certifies nothing")

    return CheckReport(
        checker=checker_name,
        target_kind="custom",
        target_name="spec-declared calls",
        results=results,
        warnings=warnings,
        unit="call",
        declared=declared,
        # Every declared call is compared: resolution needs only the specs,
        # so there is no partial-coverage mode to hide behind.
        compared=declared,
        excluded=0,
        inputs={"spec_files": len(spec_files),
                "declaring_spec_files": len(surface.sources),
                "resolvable_methods": len(surface.methods)},
    )


def summary_line(report: CheckReport) -> str:
    """`95 of 95 declared call(s) resolve (420 spec file(s))`."""
    resolved = sum(1 for r in report.results if r.status == "ok")
    total = report.declared or 0
    files = report.inputs.get("spec_files", 0)
    line = (f"{resolved} of {total} declared call(s) resolve "
            f"({files} spec file(s) scanned)")
    if report.warnings:
        line += " — " + "; ".join(report.warnings)
    return line
