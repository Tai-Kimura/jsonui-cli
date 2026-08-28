"""Loader for Python modules under `shared/core/`.

Bootstrap only — it holds no logic of its own, because logic here would be the
second copy this exists to prevent. `jsonui-doc` and `jui build` read the same
spec fields, so anything that interprets those fields lives in `shared/core/`
and is loaded from both.

Located by walking up from this file, the same way `attribute_definitions.json`
is found: `shared/core/` sits at the root of a full checkout and at the root of
an installed tool tree, and this file is at a known depth under neither — so
the walk is the portable answer rather than a path guess.

Loaded by file path rather than by putting the directory on `sys.path`. The
bridge has a known failure mode (see `project_config`, which avoids it by
importing nothing), and a module this small does not need to import anything
of its own.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CACHE: dict = {}


def shared_core_dir() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "shared" / "core"
        if candidate.is_dir():
            return candidate
    return None


def load(module_name: str):
    """Import `shared/core/<module_name>.py`, or None when it is not there.

    None rather than raising: a tool tree synced without `shared/` still runs
    every check that does not need it, and the caller says what it is skipping.
    """
    if module_name in _CACHE:
        return _CACHE[module_name]
    core = shared_core_dir()
    path = core / f"{module_name}.py" if core else None
    if path is None or not path.is_file():
        _CACHE[module_name] = None
        return None
    qualified = f"_jsonui_shared_core_{module_name}"
    existing = sys.modules.get(qualified)
    if existing is not None:
        _CACHE[module_name] = existing
        return existing
    spec = importlib.util.spec_from_file_location(qualified, path)
    if spec is None or spec.loader is None:
        _CACHE[module_name] = None
        return None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass` resolves a class's own module
    # out of `sys.modules`, so a module that is only a local variable while it
    # runs cannot define one.
    sys.modules[qualified] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[qualified]
        raise
    _CACHE[module_name] = module
    return module


def openapi_canonical():
    return load("openapi_canonical")
