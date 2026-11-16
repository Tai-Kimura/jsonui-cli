"""A temporary conformance dir with ``shared/core`` beside it.

Gates asked for ``--cross-effect`` and every bake read ``shared/core`` beside
the conformance dir, and refuse when it is not there (conformance/shared_core).
A test that builds its own synthetic corpus gets the two files here: empty
definitions (no availability-gated attribute, so nothing is carved) and an
empty semantics contract, unless it passes its own.
"""
from __future__ import annotations

import json
from pathlib import Path


def conformance_with_shared_core(root, definitions=None, semantics=None) -> Path:
    """``<root>/conformance`` (created) with ``<root>/shared/core/*`` written if absent."""
    root = Path(root)
    core = root / "shared" / "core"
    core.mkdir(parents=True, exist_ok=True)
    # A test that already wrote its own (e.g. synthetic definitions) keeps them.
    for name, body in (
        ("attribute_definitions.json", definitions or {}),
        ("attribute_semantics.json", semantics or {"semantics": {}}),
    ):
        if not (core / name).exists():
            (core / name).write_text(json.dumps(body), encoding="utf-8")
    conf = root / "conformance"
    conf.mkdir(parents=True, exist_ok=True)
    return conf
