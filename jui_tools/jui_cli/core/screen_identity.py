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
class AppOwnedScreen:
    """One normalized ``test.appOwnedScreens`` declaration.

    An app-owned screen has no layout, so it also has no test file — which
    is where every other screen declares its diagram group. The declaration
    is therefore the only place such a screen can carry one, and the entry
    accepts an object form to hold it. Canon: ``appOwnedScreens.declaration``.
    """

    screen_id: str
    #: Diagram groups, from the object form's ``group``. Empty for a bare id.
    groups: tuple[str, ...] = ()


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

    def derived_screen_ids(self) -> list[str]:
        """Screens whose role was DERIVED, not declared.

        This is the COMPLETE set of classifications the derivation could
        have got wrong. ``screens_needing_review`` is only a name-based
        hint inside it, so anything that reports "what needs checking"
        has to start here — a hint presented as a complete list is what
        lets a wrongly-derived screen keep its marker unnoticed.
        """
        return sorted(
            entry.screen_id
            for entry in self.entries.values()
            if entry.is_screen and entry.reason == "default"
        )

    def screens_needing_review(self) -> list[str]:
        """The subset of derived screens that are NAMED like a fragment.

        A hint, never a complete list: it only catches ``_cell`` / ``_row``
        style names. A cell instantiated from host-language code
        (CellBuilder, a ViewModel assembling cellClasses) is referenced by
        no layout JSON and is usually not named like one either, so it
        defaults to ``screen`` and this misses it. Measured on a real
        project: 7 flagged here, 8 more wrongly derived screens not
        flagged. Callers must present it as a hint and surface
        :meth:`derived_screen_ids` as the set that actually needs review.
        """
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
        derived = self.derived_screen_ids()
        if derived:
            lines.append(
                f"  {len(derived)} of {len(self.screen_ids)} screen(s) DERIVED, not declared. "
                "Derivation cannot see cells built from host code; declare "
                '"role": "cell" on any that are not screens '
                "('jui screens --json' lists them under derivedScreens)."
            )
        for screen_id in self.screens_needing_review():
            lines.append(
                f"  hint: '{screen_id}' is treated as a SCREEN (nothing references it as a "
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


def _as_groups(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    if isinstance(value, list):
        return tuple(v for v in value if isinstance(v, str) and v)
    return ()


def parse_app_owned_screens(declared: Iterable[Any] | None) -> list[AppOwnedScreen]:
    """Normalize a ``test.appOwnedScreens`` list.

    Accepts both declaration forms — a bare id, or ``{"id": ..., "group":
    ...}`` — because the group is diagram metadata that only some
    declarations need. Entries that carry no usable id are skipped rather
    than raised on: the list is hand-written config, and one malformed
    entry must not take down a build.
    """
    parsed: list[AppOwnedScreen] = []
    for raw in declared or ():
        if isinstance(raw, str):
            screen_id, groups = raw, ()
        elif isinstance(raw, dict):
            screen_id = raw.get("id")
            groups = _as_groups(raw.get("group"))
        else:
            continue
        if not isinstance(screen_id, str) or not screen_id:
            continue
        parsed.append(AppOwnedScreen(screen_id_for_path(screen_id), groups))
    return parsed


def app_owned_groups(declared: Iterable[Any] | None) -> dict[str, list[str]]:
    """``{screen_id: [group, ...]}`` for declarations that name a group."""
    return {
        entry.screen_id: list(entry.groups)
        for entry in parse_app_owned_screens(declared)
        if entry.groups
    }


def build_screen_index(
    layouts_dir: Path | str,
    app_owned_screens: Iterable[Any] | None = None,
) -> ScreenIndex:
    """Classify every layout under ``layouts_dir`` (recursive).

    ``app_owned_screens`` are ids the app implements without a JsonUI
    layout (a hand-written page). They are real navigation destinations, so
    they enter the index as screens — otherwise a legitimate test value
    would be rejected as unknown. Entries may be a bare id or the object
    form (see :func:`parse_app_owned_screens`); classification uses only
    the id.
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


def _app_owned_entries(declared: Iterable[Any] | None) -> dict[str, ScreenEntry]:
    return {
        entry.screen_id: ScreenEntry(entry.screen_id, Path(), "screen", "app-owned")
        for entry in parse_app_owned_screens(declared)
    }


def load_canon(shared_core_dir: Path | str | None = None) -> dict:
    """Load the canonical asset (for tools that surface its rules)."""
    if shared_core_dir is None:
        shared_core_dir = Path(__file__).resolve().parents[3] / "shared" / "core"
    with open(Path(shared_core_dir) / "screen_identity.json", "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Spec transitions — canon: diagram.specTransitions
#
# A spec's ``transitions[].destination`` is FREE PROSE. The validator requires
# only that the key is present, so nothing has ever constrained its shape, and
# one column carries at least six kinds of value.
#
# 🚫 THIS LIVES HERE, NOT IN THE DIAGRAM GENERATOR. Three places resolve screen
# ids today — this module, ``document_tools/.../mermaid/flow_graph.py`` (which
# reimplements the rules rather than importing them), and an inline expression
# in ``jui_cli/commands/verify_cmd.py``. A rule added at one of them is absent
# from the other two, and the absence is silent.
# ─────────────────────────────────────────────────────────────────────────────

# ⚠️ WHAT THE ARMS DO NOT COVER, said here because the test file is not where
# someone editing this code will look. The canon entry for this vocabulary is
# pinned STRUCTURALLY (field names, pipeline length, the kind list) and that is
# all a machine can do. Its PROSE is unpinned: a mutation prefixing the
# nodeSource sentence with "flow test only." left the whole suite green, and
# neither a substring check nor a structural one catches that. A sentence in
# the canon can contradict the code and ship.
#
# ⚠️ AND THE VOCABULARY DOES NOT REACH EVERY FACE EQUALLY. Measured 2026-09-09
# over four faces of one project, unknown went 8→0, 26→16 and 93→41 — and
# 42→42 on the fourth, where not one destination was recovered. That is why
# `summarize_destinations` refuses to print only a total: "169→99" reads like
# progress everywhere, and one of the four faces got nothing.

#: Affix positions the alias mechanism can express. Canon:
#: diagram.specTransitions.normalization.aliases.positions.
#:
#: 🚫 THIS IS "THE TWO POSITIONS SEEN SO FAR", NOT "ALL OF THEM". Infix and
#: partial matches are not covered. The distinction is not pedantry: a
#: generalization that names what it covers makes the third example a
#: COUNTEREXAMPLE that asks for a redesign, and one that says "all" makes the
#: same example an EXCEPTION to be pushed in sideways, leaving the mechanism
#: bent.
ALIAS_POSITIONS: tuple[str, ...] = ("prefix", "suffix")

#: Closed vocabulary. Canon: diagram.specTransitions.kinds.
DESTINATION_KINDS: tuple[str, ...] = (
    "screen", "route", "external", "none", "back", "unknown",
)

_PAREN = re.compile(r"[（(][^）)]*[）)]")
_SPLIT = re.compile(r"\s+or\s+|/|、|,")
_ROUTE = re.compile(r"\A/[A-Za-z0-9\-_/\[\]:.]*\Z")
_EXTERNAL = re.compile(
    r"https?://|tel:|mailto:|外部ブラウザ|外部アプリ|ブラウザ[でを]|App ?Store|"
    r"Google Maps|Apple Maps|メーラー|Phone app"
)
_NONE = re.compile(r"同画面|画面内|遷移なし|遷移しない|タブ切替|そのまま|留まる")
#: Anchored at the start ON PURPOSE — see `classify_destination`. The spelling
#: list is the part that rots: `前画面` was here and `前の画面` was not, and 7
#: destinations that plainly say "go back" were filed as `unknown` because of
#: the の. A marker set is a claim about how people write, and it is only ever
#: as good as the corpus it was read off.
_BACK = re.compile(r"\A(?:previous screen|back|dismiss|pop|前の画面|前画面|戻る)",
                   re.IGNORECASE)


@dataclass(frozen=True)
class TransitionTarget:
    """One classified ``transitions[].destination``.

    ``why`` is carried even when the kind is obvious, because the unresolved
    report has to say what it tried — a bare "unknown" tells a spec author
    nothing about which of the six kinds they were close to.
    """

    kind: str
    screen_id: str | None
    raw: str
    why: str


def _norm_id(value: str) -> str:
    return re.sub(r"[\s_\-]", "", value).lower()


def _candidates(raw: str) -> list[str]:
    """The raw value first, then its de-parenthesized parts.

    Order matters: the whole string is tried before it is cut up, so a screen
    literally named ``a/b`` is not split into two misses.
    """
    out = [raw]
    cleaned = _PAREN.sub("", raw).strip()
    if cleaned and cleaned != raw:
        out.append(cleaned)
    out.extend(p.strip() for p in _SPLIT.split(cleaned) if p.strip())
    return out


def classify_destination(
    raw: str,
    known_ids: Iterable[str],
    *,
    aliases: Iterable[tuple[str, str]] = (),
) -> TransitionTarget:
    """Classify one destination. Canon: diagram.specTransitions.

    ⚠️ SCREEN RESOLUTION IS TRIED BEFORE THE PROSE MARKERS. A real transition
    explains itself in a parenthetical, and the explanation is written in the
    words the other kinds are detected by:

        "Chat or Mypage（source依存。onDismissコールバックで遷移元に戻る）"

    TWO different mechanisms keep that a ``screen``, and they cover different
    markers — a mutation that reorders the blocks only proves one of them:

        _BACK is anchored at the start of the string (``\\A``), so 戻る
        inside a parenthetical never
        matches it. This case survives marker-first ordering. Measured: a
        mutation moving the markers above the id loop left the whole suite
        green, and the arm named "the order is load-bearing" was the thing
        that was wrong, not the code.

        _NONE and _EXTERNAL are NOT anchored — they match anywhere. For those
        the ORDER is the only protection: a screen destination whose
        parenthetical mentions 画面内 or a URL would be filed as ``none`` or
        ``external`` if the markers ran first.

    The corpus has 0 such values today (measured 2026-09-09 across 4 faces,
    271 destinations), so the arm for it is PLANTED and says so. An unexercised
    hazard is still a hazard; it just cannot be found by sampling.

    ``aliases`` is per-face, defaults to EMPTY, and each entry is
    ``(position, affix)`` with position drawn from :data:`ALIAS_POSITIONS`.
    Two shapes have been measured, and they sit at DIFFERENT ends:

        prefix ``Web``   resolves 50 of one face's 93 destinations
        suffix ``画面``   resolves 10 of another face's 69

    🚫 THE SCOPING IS A RISK CHOICE AND NOT A MEASURED ONE, and saying so is
    the point. Measured 2026-09-09, applying either affix to ALL FOUR faces
    unconditionally changes not one count: the other faces' zeros come from
    having no id that matches after the strip, not from the declaration
    withholding itself. So the corpus cannot tell a per-face declaration from
    a global rule.

    What CAN be measured is how close the global rule is to going wrong:

        ids starting with ``Web``   `web_view`, in two of the four faces
        strip it and you get        ``view``, which is no face's id — today

    The distance is ONE id. A face that adds ``view`` turns the global rule
    into a silent misresolution that ends up drawn in a diagram. That is why
    the declaration is per-face; it is not because the numbers said so.
    """
    text = (raw or "").strip()
    known = {_norm_id(k): k for k in known_ids}

    if not text or text in {"-", "—", "N/A"}:
        return TransitionTarget("unknown", None, raw, "no destination declared")

    # Structural, and checked first: a leading "/" is a router path, and the
    # splitter below would otherwise tear "/admin/login" into two words.
    if _ROUTE.match(text):
        return TransitionTarget("route", None, raw, "a router path")

    for candidate in _candidates(text):
        hit = known.get(_norm_id(candidate))
        if hit:
            return TransitionTarget("screen", hit, raw, f"matched `{candidate}`")

    for position, affix in aliases:
        if position not in ALIAS_POSITIONS:
            raise ValueError(
                f"alias position {position!r} is not one of {ALIAS_POSITIONS}; "
                f"the set is closed, and an unknown position that silently did "
                f"nothing would look exactly like a face that declared nothing")
        for candidate in _candidates(text):
            if position == "prefix":
                if not candidate.startswith(affix):
                    continue
                stripped = candidate[len(affix):]
            else:
                if not candidate.endswith(affix):
                    continue
                stripped = candidate[: -len(affix)]
            hit = known.get(_norm_id(stripped)) if stripped else None
            if hit:
                return TransitionTarget(
                    "screen", hit, raw,
                    f"matched `{stripped}` after the declared "
                    f"{position} `{affix}`")

    if _EXTERNAL.search(text):
        return TransitionTarget("external", None, raw, "leaves the app")
    if _NONE.search(text):
        return TransitionTarget("none", None, raw, "declares no screen change")
    if _BACK.search(text):
        return TransitionTarget("back", None, raw, "returns through the stack")
    return TransitionTarget("unknown", None, raw, "matched no id and no kind")


def summarize_destinations(per_face: dict[str, list[TransitionTarget]]) -> list[str]:
    """Report lines for classified destinations. Canon: unresolvedReporting.

    🔻 PER FACE, NEVER ONLY A TOTAL, and always beside the scanned count.
    Measured unresolved rates were 28% / 61% / 50% / 100%; summed, the face
    that resolves nothing vanishes into the average. And a face at 100% looks
    the same whether the instrument found nothing or never reached it — which
    is why the scanned total sits on the same line as the zero.
    """
    lines: list[str] = []
    totals: dict[str, int] = {k: 0 for k in DESTINATION_KINDS}
    for face in sorted(per_face):
        targets = per_face[face]
        counts = {k: 0 for k in DESTINATION_KINDS}
        for t in targets:
            counts[t.kind] = counts.get(t.kind, 0) + 1
            totals[t.kind] = totals.get(t.kind, 0) + 1
        body = "  ".join(f"{k}={counts[k]}" for k in DESTINATION_KINDS)
        lines.append(f"  {face}: scanned {len(targets)}  {body}")
        for t in targets:
            if t.kind == "unknown":
                lines.append(f"      unknown: {t.raw[:78]}   ({t.why})")
    scanned = sum(len(v) for v in per_face.values())
    body = "  ".join(f"{k}={totals[k]}" for k in DESTINATION_KINDS)
    lines.append(f"  ALL {len(per_face)} face(s): scanned {scanned}  {body}")
    if not per_face:
        lines.append("  no face was scanned — this is not `0 unresolved`")
    return lines
