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
import re
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

#: Directories under the layout root that hold resources rather than layouts.
#: Their contents are skipped entirely — a resource file is referenced by
#: nobody, so without this it would default to a screen and grow a marker.
#: Canon: screenId.nonLayoutSubtrees.
NON_LAYOUT_SUBTREES: frozenset[str] = frozenset({"Resources", "Styles"})

MARKER_PREFIX = "__screen_"

#: Name shapes that almost always mean "renders inside a host". Used ONLY to
#: flag a derived classification for human review — never to classify.
REVIEW_SUFFIXES = re.compile(r"_(cell|header|footer|row|item)\Z")


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

    def screens_needing_review(self) -> list[str]:
        """Screens the derivation is least sure about: nothing referenced
        them, so they defaulted to ``screen``, yet they are named like a
        fragment. This is the case the explicit ``role`` key exists for, and
        the canon requires tools to surface it rather than silently marking
        the wrong layouts."""
        return sorted(
            entry.screen_id
            for entry in self.entries.values()
            if entry.is_screen
            and entry.reason == "default"
            and REVIEW_SUFFIXES.search(entry.screen_id)
        )

    def report_lines(self) -> list[str]:
        """One-line summary plus any review hints, for a build to print."""
        lines = [
            f"Screen identity: {len(self.screen_ids)} screen(s), "
            f"{len(self.non_screen_ids)} non-screen(s)"
        ]
        for screen_id in self.screens_needing_review():
            lines.append(
                f"  '{screen_id}' is treated as a SCREEN (nothing references it as a "
                f'cell/include). If that is wrong, add "role": "cell" to its layout root.'
            )
        return lines

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
    for path in sorted(layouts_dir.rglob("*.json")):
        if NON_LAYOUT_SUBTREES.intersection(path.relative_to(layouts_dir).parts[:-1]):
            continue
        yield path


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


def build_screen_index(
    layouts_dir: Path | str,
    app_owned_screens: Iterable[str] | None = None,
) -> ScreenIndex:
    """Classify every layout under ``layouts_dir`` (recursive).

    ``app_owned_screens`` are ids the app implements without a JsonUI
    layout (a hand-written page). They are real navigation destinations, so
    they enter the index as screens — otherwise a legitimate test value
    would be rejected as unknown.
    """
    layouts_path = Path(layouts_dir)
    index = ScreenIndex()
    if not layouts_path.is_dir():
        index.entries.update(_app_owned_entries(app_owned_screens))
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

    for screen_id, entry in _app_owned_entries(app_owned_screens).items():
        # A declared id that also has a layout keeps its layout entry: the
        # declaration is for screens the app owns INSTEAD of a layout.
        index.entries.setdefault(screen_id, entry)

    return index


def _app_owned_entries(screen_ids: Iterable[str] | None) -> dict[str, ScreenEntry]:
    entries: dict[str, ScreenEntry] = {}
    for raw in screen_ids or ():
        if not isinstance(raw, str) or not raw:
            continue
        screen_id = screen_id_for_path(raw)
        entries[screen_id] = ScreenEntry(screen_id, Path(), "screen", "app-owned")
    return entries


def load_canon(shared_core_dir: Path | str | None = None) -> dict:
    """Load the canonical asset (for tools that surface its rules)."""
    if shared_core_dir is None:
        shared_core_dir = Path(__file__).resolve().parents[3] / "shared" / "core"
    with open(Path(shared_core_dir) / "screen_identity.json", "r", encoding="utf-8") as f:
        return json.load(f)
