"""Helpers that produce the "DO NOT EDIT" header/footer for auto-generated files.

Every file written by jui/sjui/kjui/rjui that is expected to be overwritten on
the next build MUST surround its content with these markers so that:

1. Human contributors are warned before editing.
2. LLM/Agent tools (Claude Code etc.) detect the tag and refuse to modify the
   file.
3. CI (``jui lint-generated``) can sanity-check that every file in a generated
   output directory still carries the tag.

Keep the constants in sync with the Ruby counterparts in
``sjui_tools/lib/core/generated_marker.rb`` etc.
"""
from __future__ import annotations

from typing import Any


SENTINEL = "@generated"
AGENT_WARNING = "LLM/Agent: you MUST NOT modify this file."
HUMAN_WARNING = "Any manual edits will be OVERWRITTEN on next generation."
END_LINE = "END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE"


def comment_header(
    *,
    source: str,
    generator: str,
    prefix: str = "//",
) -> str:
    """Return a multi-line comment banner for Swift/Kotlin/TS/JS files.

    Example output (with prefix="//")::

        // ╔══════════════════════════════════════════════════════════════╗
        // ║  @generated AUTO-GENERATED FILE — DO NOT EDIT                ║
        // ║  Source:    docs/screens/json/login.spec.json                ║
        // ║  Generator: jui g project                                    ║
        // ║  Any manual edits will be OVERWRITTEN on next generation.    ║
        // ║  LLM/Agent: you MUST NOT modify this file.                   ║
        // ╚══════════════════════════════════════════════════════════════╝

    The banner is intentionally wide enough that grep ``@generated`` finds a
    unique line per file.
    """
    lines = [
        "╔══════════════════════════════════════════════════════════════════╗",
        f"║  {SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT",
        f"║  Source:    {source}",
        f"║  Generator: {generator}",
        f"║  {HUMAN_WARNING}",
        f"║  {AGENT_WARNING}",
        "╚══════════════════════════════════════════════════════════════════╝",
    ]
    return "\n".join(f"{prefix} {line}" for line in lines)


def comment_footer(*, prefix: str = "//") -> str:
    """Return the one-line closing marker for Swift/Kotlin/TS/JS files."""
    return f"{prefix} ══ {END_LINE} ══"


def xml_header(*, source: str, generator: str) -> str:
    """Return an XML-comment banner for Android resource files."""
    return "\n".join(
        [
            "<!--",
            f"  {SENTINEL} AUTO-GENERATED FILE — DO NOT EDIT",
            f"  Source:    {source}",
            f"  Generator: {generator}",
            f"  {HUMAN_WARNING}",
            f"  {AGENT_WARNING}",
            "-->",
        ]
    )


def xml_footer() -> str:
    return f"<!-- ══ {END_LINE} ══ -->"


def json_marker(*, source: str, generator: str) -> dict[str, Any]:
    """Return the dict literal to embed as the top-level ``_generated`` key.

    Top-level unknown keys are silently ignored by every JSON-driven parser
    used by SwiftJsonUI/KotlinJsonUI/ReactJsonUI (they access specific keys by
    name), so this is safe to prepend to any Layout JSON dict.
    """
    return {
        "sentinel": SENTINEL,
        "source": source,
        "generator": generator,
        "doNotEdit": True,
        "humanWarning": HUMAN_WARNING,
        "agentWarning": AGENT_WARNING,
    }


def wrap_source_with_comment(
    *,
    body: str,
    source: str,
    generator: str,
    prefix: str = "//",
) -> str:
    """Convenience wrapper: header + blank line + body + blank line + footer."""
    header = comment_header(source=source, generator=generator, prefix=prefix)
    footer = comment_footer(prefix=prefix)
    if not body.endswith("\n"):
        body = body + "\n"
    return f"{header}\n\n{body}\n{footer}\n"
