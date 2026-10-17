"""Builds /app.js: the page's sources under web/js/ joined in a fixed order.

Placeholder until the page lands (P3): no sources yet, so ``build`` raises
``LookupError`` and the server answers /app.js with 404.
"""
from __future__ import annotations


def build(mode: str) -> str:
    raise LookupError("the viz page has no scripts yet")
