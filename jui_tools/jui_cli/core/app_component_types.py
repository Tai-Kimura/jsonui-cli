"""The component types a project registers as its own, per platform.

A project component (``jui g converter``) is drawn by its own converter
whatever its spelling: one named ``ProgressBar`` — a type synonym of
``Progress`` — or ``EditText`` — an alias section of ``TextField`` — is the
app's, and its attributes are its own definition's. The platform tools learn
the set from their registries and their validators from the extension
attribute definitions (``<tool>/lib/core/attribute_validator.rb``
``extension_definition_paths``, read from the platform root); `jui build`'s
layout normalizer is to leave such a node as written, so this reads the same
directories. Through 2.5.20 it read the node as the synonym's or the alias's
section: an extension ``SeekBar``'s ``minValue`` reached its converter as
``minimum``, an ``EditText`` as a ``TextField`` (ticket
jui-extension-component-named-as-type-synonym-validated-against-canonical).
"""
from __future__ import annotations

import json
from pathlib import Path

#: platform -> the extension attribute-definition directories its tool reads,
#: relative to the platform root (the tool's working directory in `jui build`).
#: jui_tools/tests/test_app_component_types.py pins these to the Ruby lists.
EXTENSION_DEFINITION_DIRS: dict[str, tuple[str, ...]] = {
    "ios": (
        "tools/sjui_tools/lib/swiftui/views/extensions/attribute_definitions",
        "sjui_tools/lib/swiftui/views/extensions/attribute_definitions",
        "tools/sjui_tools/lib/uikit/extensions/attribute_definitions",
        "sjui_tools/lib/uikit/extensions/attribute_definitions",
    ),
    "android": (
        "kjui_tools/lib/compose/components/extensions/attribute_definitions",
        "app/kjui_tools/lib/compose/components/extensions/attribute_definitions",
    ),
    "web": (
        "rjui_tools/lib/react/converters/extensions/attribute_definitions",
        "lib/react/converters/extensions/attribute_definitions",
        "rjui_tools/lib/react/components/extensions/attribute_definitions",
    ),
}


def app_component_types(platform: str, platform_root: Path | None) -> frozenset[str]:
    """The types *platform*'s extension definitions under *platform_root*
    declare (the keys of each ``*.json``). A file that does not parse is
    skipped, as the tool's validator skips it."""
    if platform_root is None:
        return frozenset()
    found: set[str] = set()
    for rel in EXTENSION_DEFINITION_DIRS.get(platform, ()):
        directory = Path(platform_root) / rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                found.update(k for k in data if isinstance(k, str))
    return frozenset(found)


def project_app_component_types(config_mgr) -> frozenset[str]:
    """Every platform's own types — for what reads the shared layouts once
    for all platforms (`jui verify`, `jui lint-strings`)."""
    found: set[str] = set()
    for platform in EXTENSION_DEFINITION_DIRS:
        try:
            root = getattr(config_mgr, f"{_ROOT_ATTR[platform]}")
        except Exception:  # an unreadable config: no platform roots to read
            root = None
        found |= app_component_types(platform, root)
    return frozenset(found)


_ROOT_ATTR = {"ios": "ios_root", "android": "android_root", "web": "web_root"}
