"""The diagram's ONE source: ``<screen spec>.transitions[].destination``.

Ruled 2026-09-10: the flow diagram is drawn from the SPECS only. Flow tests
are checked AGAINST it — a transition a flow test performs that no spec
declares is an ERROR — and a destination the classifier cannot resolve is
treated as ABSENT (not drawn, not an error by itself; it is counted and
listed so the spec author can see what did not resolve).

🚨 WHY THIS FILE EXISTS. Until v1.8.66 ``generator.py`` read only flow tests
and answered "No flow tests found" on a face with 48 specs, while the canon
(``shared/core/screen_identity.json`` → ``diagram.nodeSource``) declared two
sources. Measured 2026-09-10: readers of ``specTransitions`` in
document_tools — 0. A declaration with no reader is a sentence, not a rule.

Every rule here is jui_cli's: the id space comes from ``build_screen_index``
and the destination vocabulary from ``classify_destination``. This module
only walks the spec directory and shapes the result for the diagram; a
second classifier would be a second canon.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .flow_graph import EDGE_BACK, EDGE_FORWARD, import_jui_cli_module, normalize_screen_ref

SPEC_SUFFIX = ".spec.json"


@dataclass(frozen=True)
class SpecTransition:
    """One classified ``transitions[].destination`` of one spec."""

    #: Canonical id of the screen whose spec (or app-owned declaration) carries it.
    source: str
    raw: str
    #: One of jui_cli's closed ``DESTINATION_KINDS``.
    kind: str
    #: Resolved screen id when ``kind == "screen"``.
    target: str | None
    why: str
    #: The spec file, or None for an app-owned declaration (jui.config.json).
    spec_file: Path | None


@dataclass
class SpecGraph:
    """Everything one walk of the spec directory tells the diagram."""

    #: screen id -> label from the spec's metadata ("" when it has none)
    nodes: dict[str, str] = field(default_factory=dict)
    #: (from, to, kind) — forward edges from ``screen`` destinations, plus a
    #: derived return edge for each ``back`` declaration (see below)
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    #: (from, raw) — ``external`` destinations, drawn as terminal nodes
    externals: list[tuple[str, str]] = field(default_factory=list)
    #: ``unknown`` and unmapped ``route`` destinations: treated as ABSENT
    unresolved: list[SpecTransition] = field(default_factory=list)
    #: ``none`` destinations. Today every one of them is INFERRED from the
    #: wording ("画面内", "SPA"...) — no spec declares the kind explicitly —
    #: so an author who wrote a screen name that happens to contain such a
    #: word lands here silently. Listed (not warned) so the two can be told
    #: apart by a reader; a consumer lane asked for exactly this 2026-09-10.
    nones: list[SpecTransition] = field(default_factory=list)
    transitions: list[SpecTransition] = field(default_factory=list)
    #: screen ids that HAVE a spec file or an app-owned declaration — the
    #: error message for a flow transition needs to say which of "no spec"
    #: and "spec declares no such transition" it is
    sources_with_spec: set[str] = field(default_factory=set)
    id_space: set[str] = field(default_factory=set)
    specs_scanned: int = 0

    def forward_pairs(self) -> set[tuple[str, str]]:
        return {(f, t) for f, t, k in self.edges if k == EDGE_FORWARD}

    def declared_pairs(self) -> set[tuple[str, str]]:
        """Every (from, to) the specs declare, forward or derived return."""
        return {(f, t) for f, t, _k in self.edges}


def spec_screen_id(spec_file: Path) -> str:
    """The screen id a spec file describes: its stem, variant-normalized.

    Canon ``diagram.specTransitions.measured.idSpace``: "the spec stems". A
    ``Path.stem`` keeps ``.spec`` (``settings.spec``), which resolves to
    nothing — that exact slip made a first measurement report 100% of flow
    transitions absent. Strip the whole suffix.
    """
    name = spec_file.name
    if name.endswith(SPEC_SUFFIX):
        name = name[: -len(SPEC_SUFFIX)]
    return normalize_screen_ref(name)


def iter_spec_files(spec_dir: Path | str | None) -> list[Path]:
    if not spec_dir:
        return []
    path = Path(spec_dir)
    if not path.is_dir():
        return []
    return sorted(p for p in path.glob(f"*{SPEC_SUFFIX}") if p.is_file())


def _screen_ids_from_layouts(layouts_dir: Path | str | None) -> set[str]:
    if not layouts_dir or not Path(layouts_dir).is_dir():
        return set()
    module = import_jui_cli_module("jui_cli.core.screen_identity")
    if module is None:
        return set()
    try:
        index = module.build_screen_index(layouts_dir)
    except OSError:
        return set()
    return set(index.screen_ids)


def _spec_label(data: dict) -> str:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    for key in ("displayName", "name"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _sub_spec_transitions(spec_file: Path, data: dict) -> list[tuple[dict, Path]]:
    """``transitions`` of a ``screen_parent_spec``'s ``subSpecs[]`` files.

    A parent spec (``chat.spec.json``, type ``screen_parent_spec``) carries
    no transitions of its own; they live in its sub specs
    (``chat/chat-core.spec.json``, type ``screen_sub_spec``). Reading only the
    parent reported "chat's spec declares no transition to mypage" for a
    transition declared 15 lines into the sub spec — 42 flow tests' worth of
    false errors on one face (reported by that face 2026-09-10). The screen
    id stays the parent's stem; the sub file is kept for the message.
    """
    if data.get("type") != "screen_parent_spec":
        return []
    out: list[tuple[dict, Path]] = []
    for entry in data.get("subSpecs") or []:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("file")
        if not isinstance(rel, str) or not rel:
            continue
        path = spec_file.parent / rel
        sub = _load_spec(path)
        if sub is None:
            continue
        transitions = sub.get("transitions")
        if isinstance(transitions, list):
            out.extend((t, path) for t in transitions if isinstance(t, dict))
    return out


def _load_spec(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_spec_graph(
    spec_dir: Path | str | None,
    *,
    layouts_dir: Path | str | None = None,
    aliases: Iterable[tuple[str, str]] = (),
    app_owned: Iterable[str] = (),
    app_owned_transitions: dict[str, list[str]] | None = None,
) -> SpecGraph:
    """Walk ``spec_dir`` once and classify every destination.

    ``aliases`` are the face's ``spec.transitionAliases`` as ``(position,
    affix)`` pairs; ``app_owned`` the ids of its ``test.appOwnedScreens`` and
    ``app_owned_transitions`` their declared destinations. All three come from
    the face's jui.config.json — nothing here is a default, because an alias
    that helps one face silently rewrites another's ids (canon
    ``aliases.scopingIsARiskChoiceNotAMeasuredOne``).

    The id space is the union the canon names: layout-derived screen ids,
    spec stems, app-owned ids. Cells are NOT in it — a destination naming a
    cell is not a screen transition and must not resolve to one.

    Raises ``RuntimeError`` when jui_cli is not importable: the classifier
    IS the rule, and drawing without it would be a second implementation.
    """
    screen_identity = import_jui_cli_module("jui_cli.core.screen_identity")
    if screen_identity is None:
        raise RuntimeError(
            "jui_cli is not importable — the destination classifier lives there "
            "(jui_cli.core.screen_identity.classify_destination) and the diagram "
            "does not carry a second one")
    classify = screen_identity.classify_destination
    destination_parts = getattr(screen_identity, "destination_parts", None)

    graph = SpecGraph()
    spec_files = iter_spec_files(spec_dir)
    graph.specs_scanned = len(spec_files)
    owned = [normalize_screen_ref(s) for s in app_owned]
    owned_transitions = {
        normalize_screen_ref(k): list(v) for k, v in (app_owned_transitions or {}).items()
    }

    # (screen id, spec file or None, spec data or None, [(transition, origin file)])
    loaded: list[tuple[str, Path | None, dict | None, list[tuple[Any, Path | None]]]] = []
    for path in spec_files:
        data = _load_spec(path)
        if data is None:
            continue
        own = data.get("transitions")
        entries: list[tuple[Any, Path | None]] = [
            (t, path) for t in (own if isinstance(own, list) else [])]
        entries.extend(_sub_spec_transitions(path, data))
        loaded.append((spec_screen_id(path), path, data, entries))
    for screen_id, raws in owned_transitions.items():
        loaded.append((screen_id, None, None, [({"destination": r}, None) for r in raws]))

    graph.id_space = (
        _screen_ids_from_layouts(layouts_dir)
        | {screen_id for screen_id, _p, _d, _t in loaded if _p is not None}
        | set(owned)
    )
    aliases = list(aliases)

    backs: set[str] = set()
    for screen_id, path, data, transitions in loaded:
        graph.sources_with_spec.add(screen_id)
        if path is not None:
            graph.nodes.setdefault(screen_id, _spec_label(data or {}))
        else:
            graph.nodes.setdefault(screen_id, "")
        for entry, origin in transitions:
            if not isinstance(entry, dict):
                continue
            raw = entry.get("destination")
            raw_text = raw.strip() if isinstance(raw, str) else ""
            target = classify(raw_text, graph.id_space, aliases=aliases)
            # "Chat or Mypage（…）" names two screens: a transition to each.
            # The classifier returns the first match; ask for the parts and
            # classify each, and only when MORE than one resolves take them
            # all (one match is what the classifier already found).
            targets = [target]
            parts = destination_parts(raw_text) if destination_parts else []
            if parts:
                resolved = [t for t in (classify(p, graph.id_space, aliases=aliases) for p in parts)
                            if t.kind == "screen" and t.screen_id]
                if len(resolved) > 1:
                    targets = resolved
            for target in targets:
                transition = SpecTransition(
                    screen_id, raw_text, target.kind, target.screen_id, target.why, origin)
                graph.transitions.append(transition)
                if target.kind != "screen":
                    break
                graph.nodes.setdefault(target.screen_id, "")
                graph.edges.append((screen_id, target.screen_id, EDGE_FORWARD))
            if target.kind == "screen":
                continue
            if target.kind == "back":
                backs.add(screen_id)
            elif target.kind == "external":
                graph.externals.append((screen_id, raw_text))
            elif target.kind == "none":
                graph.nones.append(transition)
            elif target.kind in ("unknown", "route"):
                # `route` is "an edge once the route is mapped to a screen;
                # until then, reported" — no mapping exists yet, so it is
                # reported here with the unknowns and treated as absent.
                graph.unresolved.append(transition)
            # `none` draws nothing and is a positive declaration, not a gap.

    # A `back` declaration has no target of its own: it returns to whoever
    # pushed the screen. That is derivable from the spec — every P with a
    # forward edge P → X — so it is drawn as a dotted return edge per P.
    forward = graph.forward_pairs()
    for screen_id in sorted(backs):
        for from_id, to_id in sorted(forward):
            if to_id == screen_id and from_id != screen_id:
                graph.edges.append((screen_id, from_id, EDGE_BACK))

    # Self-loops are discarded (canon diagram.rules), duplicates collapsed.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[tuple[str, str, str]] = []
    for edge in graph.edges:
        if edge[0] == edge[1] or edge in seen:
            continue
        seen.add(edge)
        deduped.append(edge)
    graph.edges = deduped
    return graph
