"""``jui conformance coverage`` — declared-but-unread attribute detection.

The conformance suite proves *stability*: every screenshot is compared against
that same platform's previous screenshot. It never compares platforms against
each other ("cross-platform pixel comparison is out of scope by design"), so a
fixture whose attribute is silently dropped renders a blank result, matches its
own blank baseline, and passes — which is exactly how ``Button.image`` and
``View.flexWrap`` stayed broken on some platforms while every gate was green.

This module closes that hole from the other side, statically:

    for every (component, attribute, platform)
        is the attribute declared for that platform?
        does that platform's converter source read it?

The gap between the two is the ledger, ``conformance/coverage.json``. It is a
ratchet, not a TODO list: every gap must be *recorded with a reason*, a new gap
fails CI, and closing a gap without deleting its entry fails CI too. That keeps
the accepted state explicit and reviewable instead of unknown.

Reading the source rather than the output is deliberate. Output-based detection
needs a rendered artifact per attribute per platform, which is the expensive
suite this check is meant to backstop.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import rules

#: Ledger schema version; bump when the entry shape changes.
SCHEMA_VERSION = 1

#: Canonical platform order, shared with the rest of the conformance tooling.
PLATFORMS = ("ios", "android", "web")

#: Converter source root per platform, relative to the repository root.
SOURCE_ROOTS = {
    "ios": "sjui_tools/lib",
    "android": "kjui_tools/lib",
    "web": "rjui_tools/lib",
}

#: definitions `platform` tag -> conformance platform.
PLATFORM_TAGS = {"swift": "ios", "kotlin": "android", "react": "web"}

#: definitions `mode` tag -> the platforms whose *Ruby converters* are expected
#: to read the attribute. A mode mapping to no platform scopes the attribute
#: out of this check entirely.
#:
#: `uikit` maps to nothing on purpose. UIKit applies attributes in the
#: SwiftJsonUI Swift runtime straight off the layout JSON (`SJUIButton` reads
#: `attr["image"]` itself); the Ruby side only generates binding glue. Those
#: 85 attributes are outside this repository, so a source scan here would
#: report every one of them as a gap. UIKit coverage is therefore a known
#: blind spot of this check, not a silently clean result.
#:
#: The blind spot is WIDER than the `uikit` tag, and that is the part which
#: misleads: an attribute with NO mode declared is still measured against the
#: Ruby codegen alone, so a feature the SwiftJsonUI UIKit runtime fully
#: implements reads here as an iOS gap. 32 recorded gaps are that shape
#: (28 in `SJUI*` / `SJUIViewCreator`, 4 in the KotlinJsonUI dynamic
#: components); each carries a ledger `note` naming the surface.
#:
#: Read a gap as "the codegen does not emit this", never as "the platform
#: cannot do this" — the two differ by a working reference implementation.
MODE_TAGS = {
    "uikit": set(),
    "swiftui": {"ios"},
    "compose": {"android"},
    "react": {"web"},
    "dynamic-only": set(),
}

#: Skip reasons from `rules` that mean "no converter is expected to read this".
#: Callback / binding-only / behavioral attributes stay in scope: a converter
#: very much does read `onClick` and `text`, they are just hard to *fixture*.
NON_RENDERER_REASONS = frozenset(
    {
        rules.REASON_DEFINITION_META,
        rules.REASON_METADATA,
        rules.REASON_STRUCTURAL,
        rules.REASON_CROSS_FILE,
    }
)

#: Why a gap is accepted. Recorded per entry so the ledger stays a decision
#: log rather than an undifferentiated pile.
REASONS = {
    # The attribute cannot mean anything on this platform. Prefer narrowing
    # `platform` / `mode` in attribute_definitions.json — then it is not a gap.
    "platform-na",
    # Should work here, nobody has built it. Real debt.
    "unimplemented",
    # The runtime / dynamic component applies it; the codegen has nothing to
    # emit (e.g. hot-reload-only behaviour).
    "runtime-only",
    # Read through a computed key, so the scanner cannot see it.
    "dynamic-key",
    # Kept for compatibility, intentionally not wired up.
    "legacy",
}

#: How a converter reads an attribute. Anything not matched here reads as a
#: gap — false gaps are recoverable (add a ledger entry), a missed gap is not.
#: The forms below were not guessed at: each one was found by grepping the
#: attributes a first pass reported as gaps and seeing them read anyway.
READ_PATTERNS = (
    # attributes['x'] / @component['x'] / json_data['x'] / child['x']
    re.compile(
        r"(?:attributes|@component|component|json_data|json|attrs|child)"
        r"\['([A-Za-z_$][A-Za-z0-9_]*)'\]"
    ),
    re.compile(r"\.dig\(\s*'([^']+)'"),
    re.compile(r"\.fetch\(\s*'([^']+)'"),
    re.compile(r"\.key\?\(\s*'([^']+)'"),
)

#: Helpers that resolve a canonical name plus any number of aliases in one
#: call. Capturing only the first two arguments missed every third alias —
#: `attr_with_alias('maximum', 'maximumValue', 'maxValue')` reads three.
ALIAS_HELPERS = re.compile(r"(?:attr_with_alias|attr_lookup)\(([^)]*)\)")
_QUOTED = re.compile(r"'([^']+)'")

#: `case key` / `case attribute_name` dispatch over attribute names is a read.
#: The subject matters: `case type.downcase` … `when 'alignment'` is a TYPE
#: name that happens to collide with an attribute, and counting it would
#: silently close a real gap.
ATTRIBUTE_CASE_SUBJECTS = frozenset({"key", "attribute_name"})
_CASE = re.compile(r"^(\s*)case\s+([A-Za-z_@][\w.\[\]'\"@]*)\s*$")
_WHEN = re.compile(r"^(\s*)when\s+(.+?)(?:\s+then\b.*)?$")


@dataclass(frozen=True)
class Gap:
    """One (component, attribute, platform) the platform never reads."""

    component: str
    attribute: str
    platform: str

    @property
    def key(self) -> str:
        return f"{self.component}.{self.attribute}"

    def __str__(self) -> str:
        return f"{self.key} [{self.platform}]"


@dataclass
class CoverageResult:
    checked: int = 0
    gaps: list = field(default_factory=list)
    #: gaps with no ledger entry — these fail the check
    unrecorded: list = field(default_factory=list)
    #: ledger entries whose attribute is now read, or no longer declared
    stale: list = field(default_factory=list)
    #: ledger entries grouped by reason, for the summary line
    by_reason: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.unrecorded and not self.stale


def coverage_path(conformance_dir) -> Path:
    return Path(conformance_dir) / "coverage.json"


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #


#: Key under which reads from non-component files (base converters, helpers,
#: modifier builders) are collected. Those files legitimately serve every
#: component, so their reads satisfy any (component, attribute) pair — the
#: same latitude `common.*` attributes get.
SHARED = "__shared__"

#: Converter/component file suffixes that name a component. Anything else
#: (helpers, base classes, builders) is SHARED.
_COMPONENT_FILE = re.compile(r"^(?P<stem>.+?)_(?:converter|component)\.rb$")

#: Per-platform converter files whose NAME lies about what they serve.
#: rjui's historical naming: ToggleConverter renders CheckBox/Check
#: (simple checkboxes) while SwitchConverter renders Switch/Toggle
#: (iOS-style switches) — the filename-derived owner would credit the
#: wrong components in both directions.
PLATFORM_FILE_COMPONENTS = {
    "web": {
        "toggle_converter.rb": ("CheckBox", "Check"),
        "switch_converter.rb": ("Switch", "Toggle"),
    },
}


def _component_index(definitions: dict) -> dict:
    """`normalized-name -> component` for every declared component.

    File stems are normalized the same way (lowercase, underscores stripped),
    which absorbs each tree's naming quirks: `text_field_converter.rb`,
    `textfield_converter.rb` and `textfield_component.rb` all resolve to
    `TextField`.
    """
    index = {}
    for component in definitions:
        if component.startswith("_") or component == "common":
            continue
        index[component.replace("_", "").lower()] = component
    return index


def components_for_file(path, component_index: dict, platform: str | None = None) -> tuple:
    """The component(s) a converter file belongs to, or (SHARED,).

    Unmatched files stay SHARED on purpose: SHARED satisfies every pair, so a
    mapping miss can only *hide* a gap (the pre-pair-scan behaviour for that
    file), never invent a false one. Per-platform overrides win over the
    filename for the files whose name lies (see PLATFORM_FILE_COMPONENTS).
    """
    name = Path(path).name
    override = PLATFORM_FILE_COMPONENTS.get(platform or "", {}).get(name)
    if override:
        return override
    match = _COMPONENT_FILE.match(name)
    if not match:
        return (SHARED,)
    stem = match.group("stem").replace("_", "").lower()
    return (component_index.get(stem, SHARED),)


def _reads_in_source(src: str) -> set:
    """Attribute names one Ruby source file reads."""
    keys: set = set()
    for pattern in READ_PATTERNS:
        for match in pattern.findall(src):
            if isinstance(match, tuple):
                keys.update(match)
            else:
                keys.add(match)
    for args in ALIAS_HELPERS.findall(src):
        keys.update(_QUOTED.findall(args))
    keys |= _attribute_case_reads(src)
    return keys


def scan_reads(source_root, definitions: dict | None = None, platform: str | None = None) -> dict:
    """Attribute reads under `source_root`, attributed per component.

    Returns `{component-or-SHARED: {attribute names}}`. A name read in
    `button_converter.rb` lands under `Button` and satisfies only Button's
    declarations; a name read in `base_view_converter.rb` (or any file that
    does not map to a declared component) lands under SHARED and satisfies
    every component. Without the attribution, a name read by ANY component's
    converter satisfied every component that declares it — Label.highlightColor
    reported implemented on web because button_converter.rb reads the name.
    """
    component_index = _component_index(definitions or {})
    reads: dict = {}
    root = Path(source_root)
    if not root.is_dir():
        return reads
    for path in sorted(root.rglob("*.rb")):
        src = path.read_text(encoding="utf-8", errors="replace")
        keys = _reads_in_source(src)
        if keys:
            for owner in components_for_file(path, component_index, platform):
                reads.setdefault(owner, set()).update(keys)
    return reads


def _attribute_case_reads(src: str) -> set:
    """Names dispatched on by a `case key` / `case attribute_name` block."""
    keys: set = set()
    subject_indent = None
    for line in src.splitlines():
        case_match = _CASE.match(line)
        if case_match:
            indent, subject = case_match.groups()
            subject_indent = len(indent) if subject in ATTRIBUTE_CASE_SUBJECTS else None
            continue
        if subject_indent is None:
            continue
        when_match = _WHEN.match(line)
        if when_match:
            indent, values = when_match.groups()
            if len(indent) >= subject_indent:
                keys.update(_QUOTED.findall(values))
            continue
        stripped = line.strip()
        if stripped == "end" and len(line) - len(line.lstrip()) <= subject_indent:
            subject_indent = None
    return keys


def applicable_platforms(defn: dict) -> tuple:
    """Platforms an attribute is declared for, honouring `platform` + `mode`."""
    scope: set | None = None

    raw = defn.get("platform")
    if raw is not None:
        tags = raw if isinstance(raw, list) else [raw]
        unknown = [t for t in tags if t not in PLATFORM_TAGS]
        if unknown:
            # Same guard as rules._platforms: a silently-dropped token shrinks
            # or (all-unknown -> None -> ALL) widens the declared surface with
            # no trace, corrupting this check's universe.
            raise ValueError(
                f"unknown platform token(s) {unknown!r} in attribute "
                f"definition (known: {sorted(PLATFORM_TAGS)})"
            )
        scope = {PLATFORM_TAGS[t] for t in tags}

    raw_mode = defn.get("mode")
    if raw_mode is not None:
        tags = raw_mode if isinstance(raw_mode, list) else [raw_mode]
        mode_scope: set = set()
        for tag in tags:
            mode_scope |= MODE_TAGS.get(tag, set(PLATFORMS))
        scope = mode_scope if scope is None else (scope & mode_scope)

    if scope is None:
        return PLATFORMS
    return tuple(p for p in PLATFORMS if p in scope)


def in_scope(component: str, attribute: str, defn) -> bool:
    """False for definition metadata and non-renderer attributes."""
    if not isinstance(defn, dict):
        return False
    if defn.get("deprecated"):
        return False
    reason = rules._untestable_reason(component, attribute, defn)
    return reason not in NON_RENDERER_REASONS


#: Components co-routed to another component's converter WITHOUT an
#: `_alias_of` declaration — dispatch facts, verified against the three
#: converter factories (sjui converter_factory.rb / kjui compose_builder.rb /
#: rjui base_converter.get_converter_class). SafeAreaView is a View with safe
#: area handling, rendered by the View converter on every platform.
ROUTED_WITH = {
    "SafeAreaView": "View",
}


def _routing_group(component: str, definitions: dict) -> set:
    """Every component whose converter file may legitimately read
    `component`'s attributes: the bidirectional closure of `_alias_of` plus
    ROUTED_WITH.

    `_alias_of` must close in BOTH directions because converter files are
    sometimes named after the alias: sjui routes `Switch, Toggle` to
    toggle_converter.rb, so the canonical Switch's reads live in the
    alias-named file.
    """
    group = {component}
    changed = True
    while changed:
        changed = False
        for name, attrs in definitions.items():
            if name.startswith("_") or not isinstance(attrs, dict):
                continue
            canonical = attrs.get("_alias_of")
            link = ROUTED_WITH.get(name)
            for a, b in ((name, canonical), (name, link)):
                if not b:
                    continue
                if (a in group) != (b in group):
                    group.update((a, b))
                    changed = True
    return group


def _readers_for(component: str, definitions: dict) -> tuple:
    """Read-sources allowed to satisfy `component`'s attributes.

    The component's routing group (own converter + aliases/co-routed, in
    either naming direction) plus SHARED. `common` is satisfied tree-wide:
    base converters and helpers legitimately implement common attributes for
    every component, and so, per the same logic, does any single converter.
    """
    if component == "common":
        return ("*",)
    return tuple(sorted(_routing_group(component, definitions))) + (SHARED,)


def _is_read(attribute: str, sources: tuple, reads: dict) -> bool:
    if sources == ("*",):
        return any(attribute in names for names in reads.values())
    return any(attribute in reads.get(source, ()) for source in sources)


def find_gaps(definitions: dict, reads: dict) -> list:
    """Every declared (component, attribute, platform) its component never reads."""
    gaps = []
    for component, attrs in sorted(definitions.items()):
        if component.startswith("_") or not isinstance(attrs, dict):
            continue
        sources = _readers_for(component, definitions)
        for attribute, defn in sorted(attrs.items()):
            if not in_scope(component, attribute, defn):
                continue
            for platform in applicable_platforms(defn):
                if not _is_read(attribute, sources, reads.get(platform, {})):
                    gaps.append(Gap(component, attribute, platform))
    return gaps


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def load_ledger(path) -> dict:
    """`{(component.attribute, platform): entry}` for a ledger file."""
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for entry in raw.get("entries", []):
        key = f"{entry['component']}.{entry['attribute']}"
        for platform in entry.get("platforms", []):
            out[(key, platform)] = entry
    return out


def alias_names(definitions: dict) -> dict:
    """`component -> {alias names}` declared on that component's attributes.

    An alias is rewritten to its canonical spelling by L1 normalization before
    a converter ever sees it, so no converter is expected to read one.
    """
    out: dict = {}
    for component, attrs in definitions.items():
        if component.startswith("_") or not isinstance(attrs, dict):
            continue
        names: set = set()
        for defn in attrs.values():
            if not isinstance(defn, dict):
                continue
            raw = defn.get("aliases") or []
            names.update(raw if isinstance(raw, list) else [raw])
        out[component] = names
    return out


def default_reason(gap, definitions: dict, aliases: dict) -> tuple:
    """`(reason, note)` for a gap that has never been triaged."""
    known = aliases.get(gap.component, set()) | aliases.get("common", set())
    if gap.attribute in known:
        return ("legacy", "alias — normalized to its canonical spelling before conversion")
    return ("unimplemented", None)


def render_ledger(gaps, existing=None, definitions=None) -> str:
    """Deterministic ledger JSON: one entry per attribute, platforms merged.

    Reasons and notes already recorded for an attribute are carried over, so
    regenerating after closing a gap never silently discards the triage.
    """
    existing = existing or {}
    aliases = alias_names(definitions or {})
    merged: dict = {}
    for gap in gaps:
        reason, note = default_reason(gap, definitions or {}, aliases)
        entry = merged.setdefault(
            gap.key,
            {
                "component": gap.component,
                "attribute": gap.attribute,
                "platforms": [],
                "reason": reason,
                **({"note": note} if note else {}),
            },
        )
        entry["platforms"].append(gap.platform)
        prior = existing.get((gap.key, gap.platform))
        if prior:
            entry["reason"] = prior.get("reason", entry["reason"])
            if prior.get("note"):
                entry["note"] = prior["note"]

    entries = []
    for key in sorted(merged):
        entry = merged[key]
        entry["platforms"] = [p for p in PLATFORMS if p in entry["platforms"]]
        entries.append(entry)

    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Declared attributes no platform converter reads. Hand-maintained: "
            "close a gap by implementing it (then delete the entry) or by "
            "narrowing platform/mode in attribute_definitions.json. "
            f"reason is one of: {', '.join(sorted(REASONS))}."
        ),
        "entries": entries,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def check(definitions: dict, repo_root, conformance_dir, platforms=None) -> CoverageResult:
    """Compare live gaps against the ledger."""
    platforms = tuple(platforms or PLATFORMS)
    reads = {
        platform: scan_reads(
            Path(repo_root) / SOURCE_ROOTS[platform], definitions, platform
        )
        for platform in platforms
    }
    gaps = [g for g in find_gaps(definitions, reads) if g.platform in platforms]
    ledger = load_ledger(coverage_path(conformance_dir))

    result = CoverageResult(gaps=gaps)
    result.checked = sum(
        len(applicable_platforms(defn))
        for component, attrs in definitions.items()
        if not component.startswith("_") and isinstance(attrs, dict)
        for attribute, defn in attrs.items()
        if in_scope(component, attribute, defn)
    )

    live = {(g.key, g.platform) for g in gaps}
    for gap in gaps:
        entry = ledger.get((gap.key, gap.platform))
        if entry is None:
            result.unrecorded.append(gap)
        else:
            reason = entry.get("reason", "unimplemented")
            result.by_reason[reason] = result.by_reason.get(reason, 0) + 1

    for (key, platform), _entry in sorted(ledger.items()):
        if platform not in platforms:
            continue
        if (key, platform) not in live:
            result.stale.append(f"{key} [{platform}]")

    return result
