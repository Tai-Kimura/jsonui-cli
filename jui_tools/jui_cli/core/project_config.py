"""Locating the ``jui.config.json`` that owns a file.

Every tool that reads project settings from somewhere other than the cwd
(the test validator walks up from a test file, the doc generator from a
test tree) needs the same answer to "which config governs this path?".
:class:`~jui_cli.core.config_manager.ConfigManager` answers it for the cwd;
this module answers it for an arbitrary starting directory, including the
multi-app layout where the config is a SIBLING of the tests rather than an
ancestor.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Config file names that may carry project settings, in priority order.
CONFIG_CANDIDATES: tuple[str, ...] = ("jui.config.json", "jsonui-test.config.json")


def read_config(path: Path) -> dict | None:
    """Parse a config file, or None when it is missing/unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def find_project_config(start: Path | str) -> tuple[dict, Path] | tuple[None, None]:
    """Locate the project config that owns ``start``.

    Single-app projects keep the config above their tests, so walking up
    finds it. Multi-app projects put each app beside a shared test tree
    (``tests/<app>/...`` next to ``<app>/jui.config.json``); there the
    config is a SIBLING, never an ancestor, so try the app directory too.
    """
    start = Path(start)
    for directory in [start, *start.parents]:
        for name in CONFIG_CANDIDATES:
            candidate = directory / name
            if not candidate.is_file():
                continue
            config = read_config(candidate)
            if config is not None:
                return config, candidate

    parts = start.parts
    for index in range(len(parts) - 1, 0, -1):
        if parts[index - 1] != "tests":
            continue
        app_root = Path(*parts[: index - 1]) / parts[index]
        for name in CONFIG_CANDIDATES:
            candidate = app_root / name
            if not candidate.is_file():
                continue
            config = read_config(candidate)
            if config is not None:
                return config, candidate

    return None, None


def declared_app_owned_screens(config: dict | None) -> list:
    """The raw ``test.appOwnedScreens`` list, or ``[]``.

    Returned unparsed — entries may be a bare id or an object, and
    ``jui_cli.core.screen_identity.parse_app_owned_screens`` is the one
    place that knows both shapes.
    """
    if not isinstance(config, dict):
        return []
    test_config = config.get("test")
    if not isinstance(test_config, dict):
        return []
    declared = test_config.get("appOwnedScreens")
    return declared if isinstance(declared, list) else []
