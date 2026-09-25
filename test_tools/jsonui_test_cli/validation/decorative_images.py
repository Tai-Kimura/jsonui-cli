"""`notVisible` on a decorative image cannot fail on iOS — named as an INFO.

An image with no alt that operates nothing is decorative
(shared/core/image_accessibility.py): iOS hides it from VoiceOver
(`.accessibilityHidden(true)`), and the iOS driver's notVisible is
`!(exists && isHittable)` — an element hidden from VoiceOver still exists
but is never hittable, so it reads as not visible while it is on screen.
Measured on an iOS 18 simulator (SwiftJsonUI ConformanceHost,
-decorativeImageProbe): the same element satisfies both `visible` and
`notVisible`. Android (By.res) and web (data-testid) are unaffected.

Judged on the screen the step runs on: a screen test's `source.layout`, a
flow step's `screen` (the steps a repeat or retry runs take their step's),
looked up by screen id — the layout's basename, as the screen check looks it
up — and resolved for iOS with its includes expanded by the same
`layout_facts` the element-id check resolves every layout with, together
with the cell layouts it names. The layout named is that one. It was keyed
by id across the whole project, so the layout named was the first by name
of those that had a decorative image with the id, and an id that had an alt
or a tap on the test's own screen was named all the same.

Not judged, so nothing is said:
- an id the screen does not carry: a screen test moves on to other screens
  and nothing records which one a step is on;
- the steps of a flow's block: the drivers run them without a screen;
- a step iOS never runs: the config the run read builds no iOS app (one that
  declares no platforms is taken to build it, as the platform warnings take
  it), or the test's `platform`, the case's, or a `when.platform` on the
  step or on a step around it leaves iOS out (`install._platform_matches`,
  the rule the drivers' bundles are shaped by).

An INFO, not a warning: it never changes `Warnings:` or the exit.
"""

from __future__ import annotations

from collections import Counter

from ..install import _platform_matches
from .element_ids import CONDITION_KEYS, run_project
from .models import ValidationMessage, ValidationResult
from .step import _reaches, project_platforms

#: (layouts dir, screen id) -> {image id: (role, layout file)}.
_SCREENS: dict = {}
#: layouts dir -> the screen index.
_INDEX: dict = {}


def _rule():
    from .screen_ids import _prefer_sibling_jui_cli
    _prefer_sibling_jui_cli()
    try:
        from jui_cli.core import shared_core
    except ImportError:
        return None
    return shared_core.load("image_accessibility")


def _screen_layout(project, screen_id: str):
    """The layout of *screen_id* relative to the layouts dir, without
    `.json`; None when no single layout has that id."""
    key = str(project.layouts_dir)
    if key not in _INDEX:
        from jui_cli.core.screen_identity import build_screen_index
        _INDEX[key] = build_screen_index(project.layouts_dir)
    index = _INDEX[key]
    entry = index.get(screen_id)
    if entry is None or screen_id in index.collisions:
        return None
    return str(entry.path.relative_to(project.layouts_dir).with_suffix(""))


def screen_images(project, screen_id: str) -> dict:
    """{image id: (role, layout file)} on screen *screen_id* as iOS draws it:
    its layout and the cell layouts it names, each with its includes
    expanded. An id also carried by a node that is not an image, or by
    images of different roles, is left out."""
    key = (str(project.layouts_dir), screen_id)
    if key in _SCREENS:
        return _SCREENS[key]
    found: dict = {}
    rule = _rule()
    name = _screen_layout(project, screen_id) if rule is not None else None
    if name is not None:
        from jui_cli.core.layout_facts import layout_facts
        roles: dict = {}
        where: dict = {}
        carriers: Counter = Counter()
        seen: set = set()
        queue = [name]
        while queue:
            layout = queue.pop(0)
            if layout in seen:
                continue
            seen.add(layout)
            facts = layout_facts({"metadata": {"layoutFile": layout}}, "ios",
                                 layouts_dir=project.layouts_dir,
                                 styles_dir=project.styles_dir)
            if facts.tree is None:
                continue
            carriers.update(facts.id_counts)
            for node, role in rule.roles(facts.tree):
                ident = node.get("id")
                if isinstance(ident, str) and ident:
                    roles.setdefault(ident, []).append(role)
                    where.setdefault(ident, f"{layout}.json")
            queue += sorted(facts.cell_layouts)
        found = {ident: (held[0], where[ident]) for ident, held in roles.items()
                 if len(set(held)) == 1 and len(held) == carriers[ident]}
    _SCREENS[key] = found
    return found


def _off_ios(step: dict) -> bool:
    return not _reaches(step, "ios")


def _not_visible_ids(step, path: str, screen, out: list, flow: bool = False) -> None:
    """(path, id, screen) of every notVisible *step* names that iOS can run."""
    if not isinstance(step, dict) or _off_ios(step) or "file" in step:
        return
    if flow:
        # A flow's inline step names the screen it runs on; a block does not.
        named = step.get("screen")
        screen = named.strip() if isinstance(named, str) and named.strip() else None
    if step.get("assert") == "notVisible" and isinstance(step.get("id"), str):
        out.append((path, step["id"], screen))
    for key in CONDITION_KEYS:
        condition = step.get(key)
        if isinstance(condition, dict) and isinstance(condition.get("notVisible"), str):
            out.append((f"{path}.{key}", condition["notVisible"], screen))
    for i, inner in enumerate(step.get("steps") or []):
        _not_visible_ids(inner, f"{path}.steps[{i}]", screen, out)


def check_decorative_not_visible(data: dict, path: str, result: ValidationResult) -> None:
    platforms = project_platforms()
    if platforms is not None and "ios" not in platforms:
        return
    if not _platform_matches(data.get("platform"), "ios"):
        return
    project, _why = run_project()
    if project is None:
        return
    from jui_cli.core.screen_identity import screen_id_for_path

    flow = data.get("type") == "flow"
    screen = None
    source = data.get("source")
    if not flow and isinstance(source, dict) and isinstance(source.get("layout"), str) \
            and source["layout"].strip():
        screen = screen_id_for_path(source["layout"].strip())
    named: list = []
    for section in ("setup", "steps", "cases", "teardown"):
        for i, item in enumerate(data.get(section) or []):
            if section != "cases":
                _not_visible_ids(item, f"{path}.{section}[{i}]", screen, named, flow)
            elif isinstance(item, dict) and _platform_matches(item.get("platform"), "ios"):
                for j, step in enumerate(item.get("steps") or []):
                    _not_visible_ids(step, f"{path}.cases[{i}].steps[{j}]", screen, named)
    for where, ident, on in named:
        if on is None:
            continue
        role, layout = screen_images(project, on).get(ident, (None, None))
        if role != "decorative":
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
    _SCREENS.clear()
    _INDEX.clear()
