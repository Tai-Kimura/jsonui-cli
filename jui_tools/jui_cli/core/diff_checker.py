"""Diff checker for declaration files."""
from __future__ import annotations

import re
from pathlib import Path


class DiffChecker:
    """Compares existing declaration files with newly generated content."""

    def check(self, existing_path: Path, new_content: str) -> str | None:
        """Compare existing file with new content.

        Returns a diff description string if different, None if identical.
        """
        if not existing_path.exists():
            return None

        existing_content = existing_path.read_text(encoding="utf-8")

        # Normalize whitespace for comparison
        existing_normalized = _normalize(existing_content)
        new_normalized = _normalize(new_content)

        if existing_normalized == new_normalized:
            return None

        # Extract method signatures and compare
        existing_methods = _extract_method_signatures(existing_content)
        new_methods = _extract_method_signatures(new_content)

        added = new_methods - existing_methods
        removed = existing_methods - new_methods

        lines = []
        for sig in sorted(added):
            lines.append(f"  + Added: {sig}")
        for sig in sorted(removed):
            lines.append(f"  - Removed: {sig}")

        if not lines:
            lines.append("  ~ Content changed (non-method differences)")

        return "\n".join(lines)


def _normalize(content: str) -> str:
    """Normalize content for comparison."""
    # Remove comments, blank lines, trailing whitespace
    lines = []
    for line in content.splitlines():
        stripped = line.rstrip()
        if stripped and not stripped.lstrip().startswith("//"):
            lines.append(stripped)
    return "\n".join(lines)


def _extract_method_signatures(content: str) -> set[str]:
    """Extract method/function signatures from Swift/Kotlin/TypeScript code."""
    signatures = set()

    # Swift: func methodName(params) async throws -> ReturnType
    for match in re.finditer(r"func\s+(\w+\([^)]*\)(?:\s*async)?(?:\s*throws)?(?:\s*->\s*\S+)?)", content):
        signatures.add(match.group(1).strip())

    # Kotlin: suspend fun methodName(params): ReturnType
    for match in re.finditer(r"(?:suspend\s+)?fun\s+(\w+\([^)]*\)(?:\s*:\s*\S+)?)", content):
        signatures.add(match.group(1).strip())

    # TypeScript: methodName(params): ReturnType
    for match in re.finditer(r"^\s+(\w+\([^)]*\)(?:\s*:\s*[^;{]+)?)", content, re.MULTILINE):
        sig = match.group(1).strip()
        if not sig.startswith(("if", "for", "while", "switch", "return", "class", "import")):
            signatures.add(sig)

    return signatures
