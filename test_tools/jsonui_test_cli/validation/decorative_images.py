"""`notVisible` on a decorative image cannot fail on iOS — named as an INFO.

An image with no alt that operates nothing is decorative
(shared/core/image_accessibility.py): iOS hides it from VoiceOver
(`.accessibilityHidden(true)`), and the iOS driver's notVisible is
`!(exists && isHittable)` — an element hidden from VoiceOver still exists
but is never hittable, so it reads as not visible while it is on screen.
Measured on an iOS 18 simulator (SwiftJsonUI ConformanceHost,
-decorativeImageProbe): the same element satisfies both `visible` and
`notVisible`. Android (By.res) and web (data-testid) are unaffected.

An INFO, not a warning: it never changes `Warnings:` or the exit.
"""

from __future__ import annotations

import json
from pathlib import Path

from .element_ids import CONDITION_KEYS, run_project
from .models import ValidationMessage, ValidationResult

_ROLES: dict = {}


def _rule():
    from .screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core import shared_core
    except ImportError:
        return None
    return shared_core.load("image_accessibility")


def decorative_images(layouts_dir: Path) -> dict:
    """{image id: layout path} for every decorative image of the project's
    layouts (read as written — an include not expanded here hides nothing:
    the images inside it are judged in their own file)."""
    key = str(layouts_dir)
    if key in _ROLES:
        return _ROLES[key]
    rule = _rule()
    found: dict = {}
    if rule is not None:
        for path in sorted(layouts_dir.rglob("*.json")):
            try:
                tree = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for node, role in rule.roles(tree):
                ident = node.get("id")
                if role == "decorative" and isinstance(ident, str) and ident:
                    found.setdefault(ident, str(path.relative_to(layouts_dir)))
    _ROLES[key] = found
    return found


def _not_visible_ids(step, path: str, out: list) -> None:
    if not isinstance(step, dict):
        return
    if step.get("assert") == "notVisible" and isinstance(step.get("id"), str):
        out.append((path, step["id"]))
    for key in CONDITION_KEYS:
        condition = step.get(key)
        if isinstance(condition, dict) and isinstance(condition.get("notVisible"), str):
            out.append((f"{path}.{key}", condition["notVisible"]))
    for i, inner in enumerate(step.get("steps") or []):
        _not_visible_ids(inner, f"{path}.steps[{i}]", out)


def check_decorative_not_visible(data: dict, path: str, result: ValidationResult) -> None:
    project, _why = run_project()
    if project is None:
        return
    decorative = decorative_images(project.layouts_dir)
    if not decorative:
        return
    named: list = []
    for section in ("setup", "steps", "cases", "teardown"):
        for i, item in enumerate(data.get(section) or []):
            if section != "cases":
                _not_visible_ids(item, f"{path}.{section}[{i}]", named)
            elif isinstance(item, dict):
                for j, step in enumerate(item.get("steps") or []):
                    _not_visible_ids(step, f"{path}.cases[{i}].steps[{j}]", named)
    for where, ident in named:
        layout = decorative.get(ident)
        if layout is None:
            continue
        result.infos.append(ValidationMessage(
            path=where,
            level="info",
            kind="decorative-not-visible",
            message=(
                f"notVisible on '{ident}' cannot fail on iOS: it is a decorative image in "
                f"{layout} (no alt, operates nothing), iOS hides it from VoiceOver, and the "
                "iOS driver reads an element hidden from VoiceOver as not visible even while "
                "it is on screen. Assert on the id of the view around it, or give the image "
                "an alt."
            ),
        ))


def clear_cache() -> None:
    _ROLES.clear()
