"""Screen identity resolution — the single implementation of the
``shared/core/screen_identity.json`` canon.

Everything that needs to answer "which layouts are screens?" or "what is
this screen's canonical id?" goes through here: the flow-diagram
generator, the test validator, code generation and the MCP snapshot. A
second implementation would be a second canon, so the rules live in one
place and callers consume :class:`ScreenIndex`.

Canonical rules implemented (see the JSON asset for the full text):

- id = layout basename without ``.json``, collected RECURSIVELY, unique
  project-wide, variants (``home@regular``) normalized to the base.
- classification = explicit ``role`` > referenced-as-cell/include >
  ``partial: true`` > screen. Derivation is deliberately imperfect and is
  reported so authors can correct outliers with an explicit role.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .layout_variant import split_variant

#: Keys through which a layout instantiates ANOTHER layout. A layout on the
#: receiving end of one of these is not a screen — it renders inside its
#: host, potentially once per data row.
NON_SCREEN_REFERENCE_KEYS: tuple[str, ...] = (
    "cell",
    "header",
    "footer",
    "include",
)

#: Same idea, but the value is a list of layout references.
NON_SCREEN_REFERENCE_LIST_KEYS: tuple[str, ...] = ("cellClasses",)

#: Roles a layout may declare explicitly on its root node.
VALID_ROLES: tuple[str, ...] = ("screen", "cell", "partial")

MARKER_PREFIX = "__screen_"


def marker_name(screen_id: str) -> str:
    """Runtime marker identifier for a screen id."""
    return f"{MARKER_PREFIX}{screen_id}"


def screen_id_for_path(path: Path | str) -> str:
    """Canonical screen id for a layout path (variant-normalized)."""
    stem = Path(path).name
    if stem.endswith(".json"):
        stem = stem[: -len(".json")]
    base, _cls = split_variant(stem)
    return base


@dataclass(frozen=True)
class ScreenEntry:
    """One layout, classified."""

    screen_id: str
    path: Path
    role: str  # 'screen' | 'cell' | 'partial'
    #: how the role was decided: 'explicit' | 'referenced' | 'partial-flag' | 'default'
    reason: str

    @property
    def is_screen(self) -> bool:
        return self.role == "screen"

    @property
    def marker(self) -> str:
        return marker_name(self.screen_id)


@dataclass
class ScreenIndex:
    """Classified view of a project's layout tree."""

    entries: dict[str, ScreenEntry] = field(default_factory=dict)
    #: basename -> paths, for ids that resolve to more than one file
    collisions: dict[str, list[Path]] = field(default_factory=dict)

    # --- lookups ---------------------------------------------------------

    def get(self, screen_id: str) -> ScreenEntry | None:
        return self.entries.get(screen_id)

    def is_known(self, screen_id: str) -> bool:
        return screen_id in self.entries

    def is_screen(self, screen_id: str) -> bool:
        entry = self.entries.get(screen_id)
        return bool(entry and entry.is_screen)

    @property
    def screen_ids(self) -> list[str]:
        return sorted(k for k, v in self.entries.items() if v.is_screen)

    @property
    def non_screen_ids(self) -> list[str]:
        return sorted(k for k, v in self.entries.items() if not v.is_screen)

    def classification_report(self) -> list[dict[str, str]]:
        """Derived classification, for tools to surface so authors can
        correct outliers with an explicit ``role``."""
        return [
            {
                "screen": entry.screen_id,
                "role": entry.role,
                "reason": entry.reason,
                "path": str(entry.path),
            }
            for entry in sorted(self.entries.values(), key=lambda e: e.screen_id)
        ]


def _iter_layout_files(layouts_dir: Path) -> Iterable[Path]:
    yield from sorted(layouts_dir.rglob("*.json"))


def _load(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _collect_non_screen_references(node: Any, out: set[str]) -> None:
    """Collect basenames referenced as cell/header/footer/include/cellClasses."""
    if isinstance(node, dict):
        for key in NON_SCREEN_REFERENCE_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value:
                out.add(screen_id_for_path(value))
        for key in NON_SCREEN_REFERENCE_LIST_KEYS:
            value = node.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item:
                        out.add(screen_id_for_path(item))
        for value in node.values():
            _collect_non_screen_references(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_non_screen_references(item, out)


def _explicit_role(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    role = data.get("role")
    if isinstance(role, str) and role in VALID_ROLES:
        return role
    return None


def build_screen_index(layouts_dir: Path | str) -> ScreenIndex:
    """Classify every layout under ``layouts_dir`` (recursive)."""
    layouts_path = Path(layouts_dir)
    index = ScreenIndex()
    if not layouts_path.is_dir():
        return index

    documents: dict[str, tuple[Path, Any]] = {}
    seen_paths: dict[str, list[Path]] = {}
    referenced: set[str] = set()

    for path in _iter_layout_files(layouts_path):
        screen_id = screen_id_for_path(path)
        data = _load(path)
        _collect_non_screen_references(data, referenced)

        # Variants collapse onto their base; the base file owns the entry.
        stem = path.name[: -len(".json")]
        _base, variant_class = split_variant(stem)
        if variant_class:
            continue

        seen_paths.setdefault(screen_id, []).append(path)
        documents.setdefault(screen_id, (path, data))

    for screen_id, paths in seen_paths.items():
        if len(paths) > 1:
            index.collisions[screen_id] = paths

    for screen_id, (path, data) in documents.items():
        explicit = _explicit_role(data)
        if explicit:
            index.entries[screen_id] = ScreenEntry(screen_id, path, explicit, "explicit")
            continue
        if screen_id in referenced:
            index.entries[screen_id] = ScreenEntry(screen_id, path, "cell", "referenced")
            continue
        if isinstance(data, dict) and data.get("partial") is True:
            index.entries[screen_id] = ScreenEntry(screen_id, path, "partial", "partial-flag")
            continue
        index.entries[screen_id] = ScreenEntry(screen_id, path, "screen", "default")

    return index


def load_canon(shared_core_dir: Path | str | None = None) -> dict:
    """Load the canonical asset (for tools that surface its rules)."""
    if shared_core_dir is None:
        shared_core_dir = Path(__file__).resolve().parents[3] / "shared" / "core"
    with open(Path(shared_core_dir) / "screen_identity.json", "r", encoding="utf-8") as f:
        return json.load(f)
