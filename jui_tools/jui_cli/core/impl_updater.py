"""In-place rewrites of ViewModel Impl source files.

Two responsibilities:

1. **Inheritance list completion** — ensure ``<Name>ViewModelProtocol`` is
   present in the class's inheritance list. Handles multi-line declarations,
   ``where`` clauses, Kotlin ``@Annotation constructor`` / primary
   constructor parentheses, Swift generic parameters.
2. **Override modifier injection (Kotlin only)** — any method paired with a
   ``@jui:protocol`` marker *or* auto-imported from ``spec.event_handlers``
   must carry ``override``. We don't touch Swift — protocol conformance in
   Swift doesn't require an override keyword.

All writes go through ``atomic_write_text``.

All operations are idempotent: a second run against the output of the first
yields a zero diff.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


# --------------------------------------------------------------------------- #
# Atomic write
# --------------------------------------------------------------------------- #

def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> bool:
    """Write *content* to *path* atomically via a tmp file + ``os.replace``.

    Returns True if content actually changed on disk, False otherwise (the
    caller can use this for log output). Skips the write entirely when the
    new content matches what's already there — preserving idempotency and
    avoiding needless filesystem churn.
    """
    if path.exists():
        try:
            existing = path.read_text(encoding=encoding)
        except OSError:
            existing = None
        if existing == content:
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding=encoding)
    os.replace(tmp_path, path)
    return True


# --------------------------------------------------------------------------- #
# Swift
# --------------------------------------------------------------------------- #

# Match `class <Name> [: <inheritance>] [where <clause>] {`
# - inheritance captures a comma list that can span lines
# - where clause optional, captured separately so we can keep its body intact
SWIFT_CLASS_HEADER_RE = re.compile(
    r"(?P<prefix>"
    r"(?:(?:^|\n)[ \t]*)"
    r"(?:(?:public|internal|private|fileprivate|open|final)\s+)*"
    r"class\s+(?P<name>\w+)(?:<[^>{]+>)?"
    r")"
    r"(?P<inherit>\s*:\s*[\s\S]+?)?"
    r"(?P<where>\s+where\s+[\s\S]+?)?"
    r"(?P<brace>\s*\{)",
    re.MULTILINE,
)


def ensure_swift_inheritance(
    source: str,
    class_name: str,
    protocol_name: str,
) -> str:
    """Add *protocol_name* to *class_name*'s inheritance list if missing.

    Preserves:
    - existing inheritance entries and their order
    - leading indentation of the inheritance continuation
    - ``where`` clauses (appended *after* the inheritance list)
    """
    matched = {"value": False}

    def _replace(m: re.Match[str]) -> str:
        if m.group("name") != class_name:
            return m.group(0)
        matched["value"] = True
        prefix = m.group("prefix")
        inherit = m.group("inherit") or ""
        where = m.group("where") or ""
        brace = m.group("brace")

        entries = _split_inheritance(inherit)
        if protocol_name in entries:
            return m.group(0)

        entries.append(protocol_name)
        new_inherit = ": " + ", ".join(entries)
        return f"{prefix} {new_inherit}{where}{brace}"

    new_source = SWIFT_CLASS_HEADER_RE.sub(_replace, source)
    if not matched["value"]:
        raise ValueError(
            f"Swift class '{class_name}' not found in source "
            "(tried multi-line class header with optional where clause)."
        )
    return new_source


def _split_inheritance(raw: str) -> list[str]:
    """Split an inheritance clause like ``: Foo, Bar,\n    Baz`` into
    ``["Foo", "Bar", "Baz"]``.

    Preserves comma-separated entries but drops whitespace + the leading ``:``.
    """
    if not raw:
        return []
    # Drop leading whitespace + ':'
    body = raw.lstrip()
    if body.startswith(":"):
        body = body[1:]
    return [e.strip() for e in body.split(",") if e.strip()]


# --------------------------------------------------------------------------- #
# Kotlin
# --------------------------------------------------------------------------- #

# Kotlin class header: class <Name>[<Generics>] [@Ann constructor] [(...)]
# [: Super(...) [, Iface...]] [where ...] {
KOTLIN_CLASS_HEADER_RE = re.compile(
    r"(?P<prefix>"
    r"(?:(?:^|\n)[ \t]*)"
    r"(?:(?:public|internal|private|protected|abstract|open|sealed|data|value|inner|final)\s+)*"
    r"class\s+(?P<name>\w+)(?:<[^>{]+>)?"
    r"(?:\s*@\w+(?:\([^)]*\))?\s+constructor)?"
    r"(?:\s*\((?:[^()]|\([^()]*\))*\))?"
    r")"
    r"(?P<inherit>\s*:\s*[\s\S]+?)?"
    r"(?P<where>\s+where\s+[\s\S]+?)?"
    r"(?P<brace>\s*\{)",
    re.MULTILINE,
)


def ensure_kotlin_inheritance(
    source: str,
    class_name: str,
    protocol_name: str,
) -> str:
    """Add *protocol_name* to *class_name*'s inheritance list if missing."""
    matched = {"value": False}

    def _replace(m: re.Match[str]) -> str:
        if m.group("name") != class_name:
            return m.group(0)
        matched["value"] = True
        prefix = m.group("prefix")
        inherit = m.group("inherit") or ""
        where = m.group("where") or ""
        brace = m.group("brace")

        entries = _split_kotlin_inheritance(inherit)
        # Compare against the plain identifier (strip ctor args / generics).
        simple_names = [_strip_kotlin_entry_suffix(e) for e in entries]
        if protocol_name in simple_names:
            return m.group(0)

        entries.append(protocol_name)
        new_inherit = " : " + ", ".join(entries)
        return f"{prefix}{new_inherit}{where}{brace}"

    new_source = KOTLIN_CLASS_HEADER_RE.sub(_replace, source)
    if not matched["value"]:
        raise ValueError(
            f"Kotlin class '{class_name}' not found in source."
        )
    return new_source


_KOTLIN_PACKAGE_RE = re.compile(r"^package[ \t]+(\S+)[ \t]*$", re.MULTILINE)
_KOTLIN_IMPORT_RE = re.compile(r"^import[ \t]+(\S+)[ \t]*$", re.MULTILINE)


def ensure_kotlin_import(source: str, fqn: str) -> str:
    """Insert ``import <fqn>`` into a Kotlin source file if missing.

    Placed after the last existing ``import`` line, or after the
    ``package`` declaration if no imports exist yet. Uses the same
    fully-qualified form that the existing imports use, so duplicate
    detection is exact-match only.
    """
    if not fqn:
        return source

    existing = {m.group(1) for m in _KOTLIN_IMPORT_RE.finditer(source)}
    if fqn in existing:
        return source

    new_line = f"import {fqn}"

    # Append after the last existing import (preserves grouping).
    last_import = None
    for m in _KOTLIN_IMPORT_RE.finditer(source):
        last_import = m
    if last_import is not None:
        insert_at = last_import.end()
        return f"{source[:insert_at]}\n{new_line}{source[insert_at:]}"

    # No imports yet — drop the line right after the package declaration.
    pkg = _KOTLIN_PACKAGE_RE.search(source)
    if pkg is not None:
        insert_at = pkg.end()
        return f"{source[:insert_at]}\n\n{new_line}{source[insert_at:]}"

    # No package either — prepend.
    return f"{new_line}\n{source}"


def _split_kotlin_inheritance(raw: str) -> list[str]:
    if not raw:
        return []
    body = raw.lstrip()
    if body.startswith(":"):
        body = body[1:]

    # Commas inside `Super(args)` must not split — walk the string tracking
    # paren depth.
    entries: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            entries.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        entries.append(tail)
    return [e for e in entries if e]


def _strip_kotlin_entry_suffix(entry: str) -> str:
    """``SuperClass(arg)`` → ``SuperClass``, ``Foo<T>`` → ``Foo``."""
    entry = entry.strip()
    # Strip trailing call args.
    paren = entry.find("(")
    if paren != -1:
        entry = entry[:paren]
    # Strip generic params.
    angle = entry.find("<")
    if angle != -1:
        entry = entry[:angle]
    return entry.strip()


# --------------------------------------------------------------------------- #
# Kotlin override injection
# --------------------------------------------------------------------------- #

# Match a Kotlin function declaration line, capturing the prefix (visibility +
# suspend/inline/operator/etc.) and confirming `fun` follows. We reconstruct
# the line with `override` injected just before `fun`.
KOTLIN_FUN_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<modifiers>(?:(?:public|internal|private|protected)\s+)?"
    r"(?:override\s+)?"
    r"(?:(?:suspend|inline|operator|infix|tailrec|abstract|open|final)\s+)*)"
    r"fun\s+(?P<rest>.+)$"
)


def extract_swift_method_labels(
    impl_source: str, method_name: str,
) -> list[tuple[str, str]] | None:
    """Return ``[(external_label, internal_name), ...]`` for *method_name*.

    Returns ``None`` if no matching ``func`` declaration is found. An entry's
    external label is:
    - the internal name itself when Impl writes ``name: Type`` (Swift default)
    - ``"_"`` when Impl writes ``_ name: Type`` (suppressed)
    - the leading identifier when Impl writes ``ext name: Type``
    """
    func_re = re.compile(
        r"func\s+(\w+)\s*(?:<[^>]+>)?\s*\((?P<params>[^)]*)\)",
    )
    for m in func_re.finditer(impl_source):
        if m.group(1) != method_name:
            continue
        return _parse_swift_param_labels(m.group("params"))
    return None


def _parse_swift_param_labels(params_str: str) -> list[tuple[str, str]]:
    """Split the param block and extract each (label, name) pair."""
    labels: list[tuple[str, str]] = []
    for part in _split_top_level_commas(params_str):
        stripped = part.strip()
        if not stripped:
            continue
        m = re.match(r"^\s*(?:(_|\w+)\s+)?(\w+)\s*:\s*", stripped)
        if not m:
            continue
        maybe_label = m.group(1)
        inner_name = m.group(2)
        if maybe_label is None:
            labels.append((inner_name, inner_name))
        elif maybe_label == "_":
            labels.append(("_", inner_name))
        else:
            labels.append((maybe_label, inner_name))
    return labels


def _split_top_level_commas(s: str) -> list[str]:
    """Split on commas that are not inside nested ``<>`` / ``()`` / ``[]``."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    openers = set("([{<")
    closers = set(")]}>")
    for ch in s:
        if ch in openers:
            depth += 1
            buf.append(ch)
        elif ch in closers:
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf)
    if tail.strip():
        parts.append(tail)
    return parts


def extract_expected_labels_from_swift_sig(
    signature: str,
) -> list[tuple[str, str]]:
    """Extract expected labels from a generated Swift Protocol signature
    like ``func foo(_ x: T, label y: U)`` → ``[("_", "x"), ("label", "y")]``.
    """
    m = re.search(r"\((?P<params>[^)]*)\)", signature)
    if not m:
        return []
    return _parse_swift_param_labels(m.group("params"))


def inject_kotlin_override(
    source: str,
    method_names: list[str],
) -> str:
    """Ensure every function declaration in *method_names* is prefixed with
    ``override``.

    Only the first ``fun <name>`` on its own line is considered per name; we
    avoid rewriting if ``override`` is already present.
    """
    if not method_names:
        return source

    name_set = set(method_names)
    lines = source.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        m = KOTLIN_FUN_LINE_RE.match(line.rstrip("\r\n"))
        if not m:
            continue
        rest = m.group("rest")
        # Extract the method name: `[<Generics>]? <name>(`
        nm = re.match(r"(?:<[^>]+>\s+)?(\w+)", rest)
        if not nm:
            continue
        method_name = nm.group(1)
        if method_name not in name_set:
            continue
        modifiers = m.group("modifiers")
        if "override" in modifiers.split():
            continue

        indent = m.group("indent")
        # Insert override just before fun, after existing modifiers.
        new_modifiers = modifiers + "override " if modifiers.strip() else "override "
        new_line_body = f"{indent}{new_modifiers}fun {rest}"
        # Preserve trailing newline.
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
        elif line.endswith("\n"):
            newline = "\n"
        lines[idx] = new_line_body + newline
    return "".join(lines)


# Match a Kotlin var/val declaration line. Property wrappers (@JvmField,
# @Volatile etc.) and modifiers are captured so we can reconstruct with
# ``override`` prefixed in the right position.
KOTLIN_VAR_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"(?P<annotations>(?:@\w+(?:\([^)]*\))?\s+)*)"
    r"(?P<modifiers>(?:(?:public|internal|private|protected)\s+)?"
    r"(?:override\s+)?"
    r"(?:(?:lateinit|abstract|open|final)\s+)*)"
    r"(?P<keyword>var|val)\s+(?P<rest>.+)$"
)


def inject_kotlin_var_override(
    source: str,
    var_names: list[str],
) -> str:
    """Ensure every ``var``/``val`` declaration in *var_names* is prefixed
    with ``override``.

    Same idempotency guarantee as ``inject_kotlin_override``.
    """
    if not var_names:
        return source

    name_set = set(var_names)
    lines = source.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        m = KOTLIN_VAR_LINE_RE.match(line.rstrip("\r\n"))
        if not m:
            continue
        rest = m.group("rest")
        nm = re.match(r"(\w+)", rest)
        if not nm:
            continue
        var_name = nm.group(1)
        if var_name not in name_set:
            continue
        modifiers = m.group("modifiers")
        if "override" in modifiers.split():
            continue

        indent = m.group("indent")
        annotations = m.group("annotations")
        keyword = m.group("keyword")
        new_modifiers = modifiers + "override " if modifiers.strip() else "override "
        new_line_body = f"{indent}{annotations}{new_modifiers}{keyword} {rest}"
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
        elif line.endswith("\n"):
            newline = "\n"
        lines[idx] = new_line_body + newline
    return "".join(lines)
