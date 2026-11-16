"""Escaping for externally-authored text that generators put in comments.

A comment delimiter inside a swagger `description` is the same class of
hazard as a quote inside a string literal: the text ends the construct
that was supposed to contain it, and everything after it is read as code.
Escaping is the generator's responsibility, not the author's — a schema
description is prose, and a path glob like `/api/x/*` is a legitimate
thing to write in it.

Kotlin makes it worst: block comments NEST, so a `/*` inside a KDoc opens
an inner comment and the closing `*/` only closes that one, leaving the
KDoc unterminated and the file uncompilable (measured: a shared swagger's
`error_code` description broke two Android projects' builds). TypeScript
and Java do not nest, but a `*/` in the text still ends the comment early
there, so both delimiters are handled for every block-comment target.
Line comments (`///`, `//`) are unaffected as long as the emitter splits
on newlines, which the iOS generator does.
"""
from __future__ import annotations

__all__ = ["sanitize_block_comment"]


def sanitize_block_comment(text: str) -> str:
    """Make *text* safe to place inside a `/* ... */` comment.

    Both delimiters are broken with a space rather than dropped or
    entity-encoded: the reader still sees the path or glob that was
    written, which is the point of the description.
    """
    return text.replace("/*", "/ *").replace("*/", "* /")
