"""``jui screens`` — which layouts are screens, and what are their ids.

Exposes the ONE Python implementation of the screen-identity canon
(``shared/core/screen_identity.json``) so callers do not grow their own.
The MCP server in particular consumes ``--json`` here rather than
reimplementing classification in TypeScript, which would be a third
reader of the same canon.

Reports, per layout: the canonical screen id, its role
(``screen`` / ``cell`` / ``partial``), and HOW the role was decided —
``explicit`` when the layout declares ``"role"``, otherwise the
derivation step that fired. Derivation is deliberately imperfect, so the
reason is what lets an author see they need an explicit ``role``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.config_manager import ConfigManager
from ..core.screen_identity import build_screen_index, marker_name


def register_screens_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "screens",
        help="List layouts classified as screens / cells / partials",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON (used by MCP wrappers)",
    )
    parser.add_argument(
        "--layouts-dir",
        help="Layout directory to classify (default: the project's shared layouts)",
    )


def _layouts_dir(args: argparse.Namespace) -> Path | None:
    if getattr(args, "layouts_dir", None):
        return Path(args.layouts_dir)
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        return None
    config = config_mgr.load()
    layouts = config.get("layouts_directory") or "Layouts"
    return config_mgr.project_root / layouts


def _app_owned(args: argparse.Namespace) -> list[str]:
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        return []
    config = config_mgr.load()
    test_config = config.get("test")
    if not isinstance(test_config, dict):
        return []
    declared = test_config.get("appOwnedScreens")
    return [s for s in declared if isinstance(s, str)] if isinstance(declared, list) else []


def cmd_screens(args: argparse.Namespace) -> int:
    layouts_dir = _layouts_dir(args)
    if layouts_dir is None:
        print("ERROR: jui.config.json not found. Run 'jui init' first, or pass --layouts-dir.")
        return 1

    index = build_screen_index(layouts_dir, app_owned_screens=_app_owned(args))

    if getattr(args, "as_json", False):
        payload = {
            "layoutsDir": str(layouts_dir),
            "screens": index.screen_ids,
            "nonScreens": index.non_screen_ids,
            "entries": [
                {**row, "marker": marker_name(row["screen"]) if row["role"] == "screen" else None}
                for row in index.classification_report()
            ],
            "collisions": {k: [str(p) for p in v] for k, v in index.collisions.items()},
            # The complete set whose role was derived rather than declared —
            # what an audit has to walk. needsReview is only the name-based
            # hint inside it and must not be read as a complete list.
            "derivedScreens": index.derived_screen_ids(),
            "needsReview": index.screens_needing_review(),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if index.collisions else 0

    for line in index.report_lines():
        print(line)
    for row in index.classification_report():
        print(f"  {row['role']:<8} {row['screen']:<32} ({row['reason']})")
    for screen_id, paths in sorted(index.collisions.items()):
        print(f"ERROR: screen id '{screen_id}' is ambiguous — {len(paths)} layouts share the basename:")
        for path in paths:
            print(f"    {path}")
    return 1 if index.collisions else 0
