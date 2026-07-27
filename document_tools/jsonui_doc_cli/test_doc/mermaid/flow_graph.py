"""Flow test → screen-transition graph.

The ONE extraction used by every diagram builder. Both the combined and
the grouped diagram used to carry their own copy of the fold, so a change
to the returned shape broke one of them silently.

Canonical rules (``shared/core/screen_identity.json`` → ``diagram``):

    resolve → canonicalize → collapse consecutive duplicates → build edges

* Nodes come from a flow's inline ``screen`` values AND from ``file:``
  references — both normalized into the SAME id space, so a mixed flow
  cannot produce two nodes for one screen. A ``file:`` reference resolves
  through the referenced test's own ``source.layout``, because a test file
  name is not a screen id (one screen has many test files).
* Values that resolve to a non-screen layout (a Collection cell, a
  partial) are dropped rather than drawn: they are sub-areas of the
  screen the step already runs on, and drawing them both invents edges
  (``chat → message_cell``) and hides real ones (``chat → item_detail``).
* Self-loops are discarded.
* An edge whose causing step was a ``back`` action is a return edge and is
  reported as such so the renderer can distinguish it.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

#: Actions that move BACKWARDS through the navigation stack.
BACK_ACTIONS = frozenset({"back"})

EDGE_FORWARD = "forward"
EDGE_BACK = "back"


def file_ref_stem(ref: str) -> str:
    """Basename of a ``file:`` reference, without the test suffix.

    ``../screens/booking_complete--bank_pending.test.json`` →
    ``booking_complete--bank_pending``. This is a FILE name, not a screen
    id — see :meth:`ScreenResolver.canonical_file_ref`.
    """
    name = str(ref).split("/")[-1]
    if name.endswith(".test.json"):
        name = name[: -len(".test.json")]
    elif name.endswith(".json"):
        name = name[: -len(".json")]
    return name


def normalize_screen_ref(ref: str) -> str:
    """Canonical screen id for a raw test value or file reference.

    ``../screens/home/home.test.json`` → ``home``; ``home@regular`` →
    ``home``; ``mypage`` → ``mypage``.
    """
    name = file_ref_stem(ref)
    # Variant files are alternate renderings of one screen, never a screen
    # of their own (screen_identity.json → screenId.variantNormalization).
    if "@" in name:
        name = name.rpartition("@")[0] or name
    return name


class ScreenResolver:
    """Resolves raw test values to canonical screen ids and tells screens
    apart from cells/partials.

    Classification needs the project's layout tree. When it is not
    available the resolver stays permissive (every value is a screen) so
    the diagram degrades to "draws what the tests say" instead of failing.

    ``file_ref_screen_ids`` maps a screen test's FILE name to the screen it
    covers, which is what lets a ``file:`` step land in the same id space
    as an inline ``screen`` value.
    """

    def __init__(
        self,
        layouts_dir: Path | str | None = None,
        file_ref_screen_ids: dict[str, str] | None = None,
    ):
        self._index = None
        if layouts_dir:
            self._index = _load_screen_index(layouts_dir)
        self._file_ref_screen_ids = dict(file_ref_screen_ids or {})

    def canonical(self, ref: str) -> str:
        return normalize_screen_ref(ref)

    def canonical_file_ref(self, ref: str) -> str:
        """Screen id a ``file:`` step runs on.

        A test file's NAME is not a screen id. One screen routinely has
        several test files — ``login_smoke``, ``booking_complete--
        bank_pending`` — so naming the node after the file splits one
        screen into several, and the split node loses the group its test
        declared. The referenced test already says which screen it covers
        (``source.layout``), so resolve through that.

        Falls back to the basename when the reference resolves to nothing
        we indexed: a broken reference, or a test with no ``source.layout``.
        That is the old behaviour, kept so an unresolvable reference still
        draws something rather than dropping an edge silently.
        """
        resolved = self._file_ref_screen_ids.get(file_ref_stem(ref))
        return resolved or normalize_screen_ref(ref)

    def is_screen(self, screen_id: str) -> bool:
        if self._index is None:
            return True
        # Unknown ids are kept: the diagram is not the place to enforce the
        # screen-unknown rule (that is the validator's job), and dropping
        # them would silently break the graph.
        if not self._index.is_known(screen_id):
            return True
        return self._index.is_screen(screen_id)


def import_jui_cli_module(name: str):
    """Import a ``jui_cli`` module, or None when jui is not installed.

    The rules the diagram obeys — screen classification, where a project's
    config lives — live in jui_cli, the single implementation of the canon,
    deliberately not duplicated here. jsonui-doc is packaged separately
    from jui but always ships beside it (``<root>/document_tools`` and
    ``<root>/jui_tools``), so fall back to the sibling path before giving
    up.
    """
    sibling = Path(__file__).resolve().parents[4] / "jui_tools"
    if (sibling / "jui_cli" / "core" / "screen_identity.py").is_file():
        # Prefer the copy from THIS tree over a separately installed jui: a
        # doc tool classifying screens by different rules than the build
        # tool would be a second canon.
        if str(sibling) not in sys.path:
            sys.path.insert(0, str(sibling))
        cached = sys.modules.get("jui_cli")
        cached_file = str(getattr(cached, "__file__", "") or "")
        if cached is not None and not cached_file.startswith(str(sibling)):
            for cached_name in [
                n for n in sys.modules if n == "jui_cli" or n.startswith("jui_cli.")
            ]:
                del sys.modules[cached_name]

    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _import_build_screen_index():
    """The shared screen classifier, or None when jui is not installed."""
    module = import_jui_cli_module("jui_cli.core.screen_identity")
    return getattr(module, "build_screen_index", None)


def _load_screen_index(layouts_dir: Path | str):
    """Build the shared ScreenIndex, or ``None`` when jui_cli is absent."""
    build_screen_index = _import_build_screen_index()
    if build_screen_index is None:
        return None
    try:
        return build_screen_index(layouts_dir)
    except OSError:
        return None


def _step_screen(step: dict, resolver: ScreenResolver) -> str | None:
    """Canonical screen id a step runs on, or None when it carries none."""
    if "file" in step and isinstance(step["file"], str):
        return resolver.canonical_file_ref(step["file"])
    screen = step.get("screen")
    if isinstance(screen, str) and screen:
        return resolver.canonical(screen)
    return None


def _is_back_step(step: dict) -> bool:
    return step.get("action") in BACK_ACTIONS


def flow_screen_sequence(
    steps: Iterable[dict], resolver: ScreenResolver
) -> list[tuple[str, bool]]:
    """Collapse a flow's steps into ``[(screen_id, arrived_via_back)]``.

    ``arrived_via_back`` describes the transition INTO that screen: it is
    true when the last step executed on the previous screen was a ``back``
    action. The first entry is always ``False``.
    """
    sequence: list[tuple[str, bool]] = []
    current: str | None = None
    last_step: dict | None = None

    for step in steps:
        if not isinstance(step, dict):
            continue
        screen = _step_screen(step, resolver)
        if screen is None:
            # Block steps and other screen-less shapes continue the
            # enclosing screen; they can still cause a transition, so they
            # stay eligible as the "causing step".
            last_step = step
            continue
        if not resolver.is_screen(screen):
            # Sub-area of the current screen (cell / partial): the step
            # runs on the screen we are already on.
            last_step = step
            continue
        if screen != current:
            via_back = bool(last_step is not None and _is_back_step(last_step))
            sequence.append((screen, via_back and current is not None))
            current = screen
        last_step = step

    return sequence


def flow_edges(
    steps: Iterable[dict], resolver: ScreenResolver
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Return ``(ordered_nodes, edges)`` for one flow.

    ``edges`` are ``(from_id, to_id, kind)`` with kind ``forward``/``back``.
    Self-loops cannot occur (consecutive duplicates are collapsed first)
    but are filtered defensively.
    """
    sequence = flow_screen_sequence(steps, resolver)
    nodes = [screen for screen, _ in sequence]
    edges: list[tuple[str, str, str]] = []
    for index in range(len(sequence) - 1):
        from_id = sequence[index][0]
        to_id, via_back = sequence[index + 1]
        if from_id == to_id:
            continue
        edges.append((from_id, to_id, EDGE_BACK if via_back else EDGE_FORWARD))
    return nodes, edges


def load_flow(path: Path) -> dict[str, Any] | None:
    """Load a flow test file, returning None for anything that is not one."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("type") != "flow":
        return None
    return data
