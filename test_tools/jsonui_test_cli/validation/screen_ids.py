"""Screen-id validation against the project's layout tree.

Enforces the canonical rules from ``shared/core/screen_identity.json``:

* ``screen-unknown`` (error) — the value is neither a layout nor a declared
  app-owned screen. Before this rule, a typo or a stale name simply ran the
  step against nothing and the diagram grew a ghost node.
* ``screen-not-a-screen`` (error) — the value resolves to a Collection cell
  or a partial. Cells are sub-areas of the screen the step already runs on.
* ``screen-id-collision`` (error) — two layouts share a basename, so the id
  is ambiguous.

Classification comes from ``jui_cli.core.screen_identity`` — the single
implementation of the canon. When the layout tree cannot be located the
whole check is SKIPPED rather than guessed: this validator also runs in
projects it knows nothing about (CI checkouts, doc-only trees), and a
false "unknown screen" error would block their install pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prefer_sibling_jui_cli() -> None:
    """Put the jui_cli from THIS tree ahead of any separately installed one.

    jsonui-test ships separately from jui but always sits beside it
    (``<root>/test_tools`` and ``<root>/jui_tools``). Preferring the sibling
    keeps the validator and the build tool on identical rules.
    """
    sibling = Path(__file__).resolve().parents[3] / "jui_tools"
    if not (sibling / "jui_cli" / "core" / "screen_identity.py").is_file():
        return
    if str(sibling) not in sys.path:
        sys.path.insert(0, str(sibling))
    cached = sys.modules.get("jui_cli")
    cached_file = str(getattr(cached, "__file__", "") or "")
    if cached is not None and not cached_file.startswith(str(sibling)):
        for name in [n for n in sys.modules if n == "jui_cli" or n.startswith("jui_cli.")]:
            del sys.modules[name]


def _import_build_screen_index():
    """Import the shared classifier, preferring this tree's copy."""
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core.screen_identity import build_screen_index

        return build_screen_index
    except ImportError:
        return None


def _find_project_config(start: Path) -> tuple[dict, Path] | tuple[None, None]:
    """Locate the project config that owns a test file.

    Delegates to ``jui_cli.core.project_config`` — the doc generator needs
    the same answer for its test tree, and two copies of the multi-app
    sibling probe would drift. When jui_cli cannot be imported the whole
    check is skipped anyway (the classifier is unavailable too), so
    returning "no config" here loses nothing.
    """
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core.project_config import find_project_config
    except ImportError:
        return None, None
    return find_project_config(start)


def _declared_app_owned(config: dict) -> list:
    """The raw ``test.appOwnedScreens`` list; ``build_screen_index`` parses it."""
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core.project_config import declared_app_owned_screens
    except ImportError:
        return []
    return declared_app_owned_screens(config)


def _layouts_dir_from_config(config: dict, config_path: Path) -> Path | None:
    """Resolve the layout tree from a project config.

    Multi-app projects declare their layouts per platform, so the first
    readable declaration wins; every app in one project shares the screen
    vocabulary anyway.
    """
    root = config_path.parent
    direct = config.get("layouts_directory")
    if isinstance(direct, str) and direct:
        path = root / direct
        if path.is_dir():
            return path

    platforms = config.get("platforms")
    if isinstance(platforms, dict):
        for platform in platforms.values():
            if not isinstance(platform, dict):
                continue
            for key in ("layouts_directory", "layouts"):
                value = platform.get(key)
                if isinstance(value, str) and value:
                    platform_root = platform.get("root")
                    base = root / platform_root if isinstance(platform_root, str) else root
                    path = base / value
                    if path.is_dir():
                        return path
    return None


class ScreenIdIndex:
    """Project screen vocabulary, or an inert index when it is unknown."""

    def __init__(self, index=None, collisions: dict | None = None):
        self._index = index
        self.collisions = collisions or {}

    @property
    def available(self) -> bool:
        return self._index is not None

    def is_known(self, screen_id: str) -> bool:
        return bool(self._index and self._index.is_known(screen_id))

    def is_screen(self, screen_id: str) -> bool:
        return bool(self._index and self._index.is_screen(screen_id))

    def role_of(self, screen_id: str) -> str | None:
        entry = self._index.get(screen_id) if self._index else None
        return entry.role if entry else None


_CACHE: dict[str, ScreenIdIndex] = {}


def load_screen_index(test_file_path: Path | None) -> ScreenIdIndex:
    """Build (and cache) the screen index for the project owning a test."""
    if test_file_path is None:
        return ScreenIdIndex()

    config, config_path = _find_project_config(Path(test_file_path).resolve().parent)
    if config is None:
        return ScreenIdIndex()

    cache_key = str(config_path)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    layouts_dir = _layouts_dir_from_config(config, config_path)
    app_owned = _declared_app_owned(config)
    build_screen_index = _import_build_screen_index()

    if layouts_dir is None or build_screen_index is None:
        result = ScreenIdIndex()
    else:
        index = build_screen_index(layouts_dir, app_owned)
        result = ScreenIdIndex(index, index.collisions)

    _CACHE[cache_key] = result
    return result


def clear_cache() -> None:
    """Drop the per-project cache (tests build throwaway projects)."""
    _CACHE.clear()


def check_screen_value(screen_id: str, index: ScreenIdIndex) -> str | None:
    """Return a rule violation message for a ``screen`` value, or None."""
    if not index.available or not screen_id:
        return None
    if not index.is_known(screen_id):
        return (
            f"Unknown screen '{screen_id}' (screen-unknown). Use a layout's basename, "
            "or declare an app-owned screen under test.appOwnedScreens in jui.config.json."
        )
    if not index.is_screen(screen_id):
        role = index.role_of(screen_id) or "non-screen"
        return (
            f"'{screen_id}' is a {role}, not a screen (screen-not-a-screen). "
            "Use the screen that hosts it — a cell or partial renders inside its host."
        )
    return None


def collision_messages(index: ScreenIdIndex) -> list[str]:
    """One message per ambiguous basename in the project."""
    messages = []
    for screen_id, paths in sorted(index.collisions.items()):
        joined = ", ".join(str(p) for p in paths)
        messages.append(
            f"Screen id '{screen_id}' is ambiguous — several layouts share the basename "
            f"(screen-id-collision): {joined}"
        )
    return messages
