"""`jui lint-strings` — the localize invariant as a machine check.

Of the four workflow invariants, "jsonui-localize ran" was the only one
with no build-time gate: it could not be verified after the fact, so it
degraded into a ritual. This command closes that hole by scanning the
shared Layout JSON for user-visible string attributes whose value is a
raw literal that does NOT resolve through ``strings.json`` — the exact
condition under which the three platform builders inline an
unlocalizable string.

What counts as "user-visible" is derived from the SSoT, not hardcoded
here:

- The attribute-name vocabulary is ``STRING_PROPS`` in
  ``shared/core/plural_validator.rb`` — the existing single authority on
  "layout string attributes the three builders resolve against". Reading
  it at runtime means extending that list (a shared/core change) extends
  this lint automatically, and the two checks cannot drift.
- The per-component attribute sets come from
  ``attribute_definitions.json`` via the same lookup the normalizer uses
  (exact section match, then cross-platform type synonyms), so only
  attributes a component actually declares are linted.

Resolution mirrors the platform builders (sjui StringManagerHelper /
kjui ResourceResolver): a literal is "localized" when it is a bare key
in a strings.json section the layout OWNS (its own spellings plus those
of every transitive includer — the builders inline included partials
under the includer's namespace context), a full ``{group}_{key}``
spelling, or an exact match of a registered value. A bare key that only
foreign sections declare is a finding: the builders treat it as a
collision, not a reference. Bindings (``@{...}`` / ``${...}``), empty
strings and letterless values (icon glyphs, "100%", "12:34") are out of
scope.

Layouts are read at the authoring root and normalized before judgment:
alias spellings are canonicalized and style-declared values are merged
in (the plan's "L2" requirement is exactly the style merge — include
expansion is deliberately NOT applied, because every included file is
linted once as itself and expansion would double-report each literal
under unstable paths).

Intentional non-localized literals (brand names, URLs shown verbatim,
format scaffolding) go in the allowlist ledger, ``.jui-strings-allowlist.json``
at the project root (override: ``lint.stringsAllowlist``). Entries are
per (layout, path, value) and MUST carry a reason. Like the conformance
coverage ledger, it fails in both directions: an unlisted raw literal is
a finding, and a stale entry whose literal no longer exists is a finding
too — the ledger stays a reviewed statement of fact, not a suppression
dump.

A second class of finding is about ``strings.json`` itself: one text
declared under two sections. The builders take the first section that
matches and do not agree on how sections are named (sjui basename, kjui
relative path), so a duplicate compiles to a different key per platform
and section order decides the winner. That is a forked SSoT by
construction, so it is not allowlistable.

Exit codes:

    0  clean
    1  the command could not run (no jui.config.json, SSoT assets not
       found, unreadable allowlist)
    2  findings — raw literal, forked declaration, stale allowlist entry,
       or allowlist entry with no reason

``jui build`` runs the same scan when opted in (``--lint-strings`` or
``"lint": {"strings": true}`` in jui.config.json) and reports findings
through the build warning stream, where the zero-warnings invariant
makes them gate. The default build path never invokes this module.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config_manager import ConfigManager
from ..core.normalizer import AliasTable, Canonicalizer, StyleMerger

ALLOWLIST_FILENAME = ".jui-strings-allowlist.json"

# The vocabulary source, in the same preference order the alias table
# uses for attribute_definitions.json: full checkout first, then the
# per-platform vendored copies of a project-local install.
_STRING_PROPS_RELPATHS = (
    Path("shared") / "core" / "plural_validator.rb",
    Path("kjui_tools") / "lib" / "core" / "plural_validator.rb",
    Path("sjui_tools") / "lib" / "core" / "plural_validator.rb",
    Path("rjui_tools") / "lib" / "core" / "plural_validator.rb",
)

_STRING_PROPS_RE = re.compile(r"STRING_PROPS\s*=\s*%w\[([^\]]*)\]")

# Node keys whose value is a `{scope: {attr: value}}` patch map applied
# to the enclosing component (platform overrides / responsive size
# classes). Patched values are as user-visible as the base ones.
_PATCH_MAP_KEYS = ("platform", "responsive")


class LintStringsSetupError(RuntimeError):
    """The lint cannot run — a required asset is missing or unreadable."""


# ----------------------------------------------------------------------
# SSoT derivation


def _locate_ssot_file(relpaths) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        for relpath in relpaths:
            candidate = parent / relpath
            if candidate.exists():
                return candidate
    return None


def load_string_props(path: Path | None = None) -> frozenset[str]:
    """The user-visible attribute-name vocabulary, from
    ``plural_validator.rb``'s ``STRING_PROPS`` (see module docstring)."""
    resolved = path or _locate_ssot_file(_STRING_PROPS_RELPATHS)
    if resolved is None or not resolved.exists():
        raise LintStringsSetupError(
            "plural_validator.rb not found near the installed jui_tools — "
            "cannot derive the user-visible attribute vocabulary"
        )
    match = _STRING_PROPS_RE.search(resolved.read_text(encoding="utf-8"))
    if not match or not match.group(1).split():
        raise LintStringsSetupError(
            f"STRING_PROPS not found in {resolved} — the SSoT vocabulary "
            "moved or changed shape; update lint_strings_cmd to follow it"
        )
    return frozenset(match.group(1).split())


def _declares_binding(spec: dict[str, Any]) -> bool:
    declared = spec.get("type")
    types = declared if isinstance(declared, list) else [declared]
    return "binding" in types


def visible_attrs_by_component(
    definitions: dict[str, Any], vocabulary: frozenset[str]
) -> dict[str, frozenset[str]]:
    """``{definition key: attrs ∩ vocabulary}`` — which declared
    attributes of each component carry user-visible text.

    A vocabulary name alone is not proof of text: NetworkImage declares
    ``hint`` / ``placeholder`` as *image names*. The discriminator, still
    derived from the SSoT, is bindability — every text-bearing component
    declares at least one vocabulary attribute typed ``["string",
    "binding"]`` (Label.text, Radio.label, SelectBox.text, ...), while a
    component whose vocabulary attrs are all plain ``string`` is using
    the names for resource references. Calibrated against the downstream-find
    consumers (NetworkImage.placeholder="downstream_placeholder" was the
    false-positive class this removes)."""
    out: dict[str, frozenset[str]] = {}
    for comp, attrs in definitions.items():
        if comp.startswith("_") or not isinstance(attrs, dict):
            continue
        vocab_specs = {
            name: spec
            for name, spec in attrs.items()
            if isinstance(spec, dict) and name in vocabulary
        }
        text_bearing = any(_declares_binding(spec) for spec in vocab_specs.values())
        out[comp] = frozenset(vocab_specs) if text_bearing else frozenset()
    return out


# ----------------------------------------------------------------------
# strings.json resolution (mirrors sjui StringManagerHelper /
# kjui ResourceResolver.find_string_key)


def _normalize_section_segment(segment: str) -> str:
    """One path segment as it names a strings.json section — the rjui
    generator's component-name snake_case (camel boundaries split, every
    non-alphanumeric folded to underscore). Mirror of
    StringManagerCore.normalize_section_segment."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", segment)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def namespace_candidates(layout: str) -> tuple[str, ...]:
    """The strings.json section spellings a layout owns.

    Python mirror of StringManagerCore.namespace_candidates:
    ``member_list/member_cell.json`` owns
    ``member_cell`` and ``member_list_member_cell``.
    Variant suffixes (``home@regular.json``) fold into the base screen.

    Normalized spellings come first — jsonui-localize writes sections in
    the builders' snake_case spelling, so a kebab-case layout
    (``tools/test-runner.json``) owns ``test_runner`` /
    ``tools_test_runner``; matching the raw path made every bare key in
    such a file a false foreign finding (840 findings / 36 files,
    2026-08-11). Raw spellings stay as trailing candidates for sections
    the sjui extractor named by the raw basename.
    """
    cleaned = layout.replace("\\", "/")
    if cleaned.endswith(".json"):
        cleaned = cleaned[:-5]
    cleaned = re.sub(r"@[^/]*$", "", cleaned)
    segments = [s for s in cleaned.split("/") if s]
    if not segments:
        return ()
    normalized = [_normalize_section_segment(s) for s in segments]
    return tuple(
        dict.fromkeys(
            (
                normalized[-1],
                "_".join(normalized),
                segments[-1],
                "_".join(segments),
            )
        )
    )


class StringsTable:
    """Loaded strings.json with the builders' three resolution forms."""

    def __init__(self, data: dict[str, Any] | None):
        self._groups: dict[str, dict[str, Any]] = {}
        for group, entries in (data or {}).items():
            if isinstance(entries, dict):
                self._groups[group] = entries
        # Bare keys are kept PER SECTION: the builders resolve a bare key
        # only within the sections the referencing layout owns (a bare key
        # hitting a foreign section is a collision, not a reference), so
        # a flat global key set declared bare-foreign references clean —
        # one shipped a raw key to a Release face before this was scoped
        # (asymmetric-resolution filing, 2026-08-11).
        self._keys_by_section: dict[str, set[str]] = {}
        self._full_keys: set[str] = set()
        self._values: set[str] = set()
        for group, entries in self._groups.items():
            section_keys = self._keys_by_section.setdefault(group, set())
            for key, value in entries.items():
                section_keys.add(key)
                self._full_keys.add(f"{group}_{key}")
                if isinstance(value, str):
                    self._values.add(value)
                elif isinstance(value, dict):
                    # Language map — plural sub-objects are VM-only and
                    # never inlined into a layout, so only plain string
                    # language values participate in value matching.
                    for lang_value in value.values():
                        if isinstance(lang_value, str):
                            self._values.add(lang_value)

    @classmethod
    def load(cls, path: Path | None) -> "StringsTable":
        if path is None or not path.exists():
            return cls({})
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            raise LintStringsSetupError(f"unreadable strings.json ({path}): {e}")

    def resolves(self, text: str, own_sections: tuple[str, ...] = ()) -> bool:
        """Whether the builders resolve ``text`` for a layout owning
        ``own_sections``. Full keys name their section and values reverse-
        look-up globally; a bare key resolves only within the layout's own
        sections — the builders' shared ruling."""
        if text in self._full_keys or text in self._values:
            return True
        return any(
            text in self._keys_by_section.get(section, ())
            for section in own_sections
        )

    def sections_declaring_bare(self, text: str) -> list[str]:
        """Every section that declares ``text`` as a bare key."""
        return sorted(
            section
            for section, keys in self._keys_by_section.items()
            if text in keys
        )

    def duplicate_declarations(self) -> list["Duplicate"]:
        """Texts declared by more than one section.

        The builders resolve a literal by walking the sections and taking
        the first match, and they do not agree on how a section is named
        — sjui uses the layout's basename, kjui its relative path — so a
        text declared twice compiles to a DIFFERENT key on each platform,
        and reordering strings.json silently repoints the generated code.
        A duplicate is a forked SSoT by construction, which is why this
        needs no allowlist: there is no legitimate reason to declare one
        string under two sections.

        Reported per (text, sections) rather than per referencing layout —
        the defect is in strings.json, and one entry is one fix.
        """
        by_value: dict[str, list[tuple[str, str]]] = {}
        for group, entries in self._groups.items():
            for key, value in entries.items():
                if isinstance(value, str):
                    by_value.setdefault(value, []).append((group, key))
        return [
            Duplicate(value=value, sites=tuple(sorted(sites)))
            for value, sites in sorted(by_value.items())
            if len({group for group, _ in sites}) > 1
        ]


def default_strings_path(config_mgr: ConfigManager) -> Path | None:
    explicit = config_mgr.strings_file
    if explicit is not None:
        return explicit
    return config_mgr.layouts_directory / "Resources" / "strings.json"


# ----------------------------------------------------------------------
# Scanning


@dataclass(frozen=True)
class Duplicate:
    """One text declared by several strings.json sections."""

    value: str
    sites: tuple[tuple[str, str], ...]  # (section, key) pairs

    def sections(self) -> list[str]:
        return sorted({group for group, _ in self.sites})


@dataclass(frozen=True)
class Finding:
    layout: str  # layouts_directory-relative posix path
    path: str  # attribute path inside the layout (e.g. "child[2].text")
    attribute: str
    value: str
    # Extra context for the report line (e.g. "declared in section X" for a
    # bare key that only foreign sections hold). Not part of the allowlist
    # identity.
    hint: str | None = None

    def key(self) -> tuple[str, str, str]:
        return (self.layout, self.path, self.value)


def _collect_include_targets(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        target = node.get("include")
        if isinstance(target, str) and target:
            out.add(target.replace("\\", "/"))
        for value in node.values():
            _collect_include_targets(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_include_targets(item, out)


def _own_sections_map(trees: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    """Section scope per layout: its own spellings plus those of every
    (transitive) includer.

    The builders inline an included partial under the INCLUDER's
    begin_layout context — a bare key inside ``item_detail/hero_section.json``
    included by ``item_detail.json`` resolves against ``item_detail``'s
    sections at build time, and the extractor registered its strings there
    in the first place. Judging the partial with only its own spellings
    would flag every such key as unresolvable."""
    includers: dict[str, set[str]] = {rel: set() for rel in trees}
    by_stem = {
        (rel[:-5] if rel.endswith(".json") else rel): rel for rel in trees
    }
    for rel, tree in trees.items():
        targets: set[str] = set()
        _collect_include_targets(tree, targets)
        for target in targets:
            target_rel = by_stem.get(target)
            if target_rel is not None:
                includers[target_rel].add(rel)

    result: dict[str, tuple[str, ...]] = {}
    for rel in trees:
        own = list(namespace_candidates(rel))
        seen = {rel}
        queue = list(includers.get(rel, ()))
        while queue:
            parent = queue.pop()
            if parent in seen:
                continue
            seen.add(parent)
            own.extend(namespace_candidates(parent))
            queue.extend(includers.get(parent, ()))
        result[rel] = tuple(dict.fromkeys(own))
    return result


def is_lintable_literal(value: Any) -> bool:
    """True when *value* is a string the localize gate should judge."""
    if not isinstance(value, str):
        return False
    if not value.strip():
        return False
    if "@{" in value or value.startswith("${"):
        return False  # binding / interpolation — dynamic, not a layout literal
    if not any(ch.isalpha() for ch in value):
        return False  # numbers, glyphs, punctuation-only
    return True


class LayoutScanner:
    """Walks one normalized layout tree and yields raw-literal findings."""

    def __init__(
        self,
        alias_table: AliasTable,
        visible_map: dict[str, frozenset[str]],
        vocabulary: frozenset[str],
        strings: StringsTable,
    ):
        self._alias_table = alias_table
        self._visible_map = visible_map
        self._vocabulary = vocabulary
        self._strings = strings
        self._own_sections: tuple[str, ...] = ()

    def scan(
        self,
        tree: Any,
        layout: str,
        own_sections: tuple[str, ...] | None = None,
    ) -> list[Finding]:
        findings: list[Finding] = []
        # The sections scoping bare-key resolution for every node in the
        # tree. Callers with an include graph pass the union of the file's
        # own spellings and its (transitive) includers' — the builders
        # inline an included partial under the INCLUDER's namespace context.
        # Instance state is safe: one scan at a time.
        self._own_sections = (
            own_sections if own_sections is not None else namespace_candidates(layout)
        )
        self._walk(tree, layout, "", findings)
        return findings

    # -- internals

    def _visible_attrs_for(self, component_type: Any) -> frozenset[str]:
        key = None
        if isinstance(component_type, str):
            key = self._alias_table.definition_key_for(component_type)
        if key is not None and key in self._visible_map:
            return self._visible_map[key]
        # Unknown / custom component: fall back to the name vocabulary —
        # custom converters follow the same attribute naming convention.
        return self._vocabulary

    def _check_node(
        self,
        node: dict[str, Any],
        component_type: Any,
        layout: str,
        path: str,
        findings: list[Finding],
    ) -> None:
        visible = self._visible_attrs_for(component_type)
        for attr in sorted(visible):
            value = node.get(attr)
            if not is_lintable_literal(value):
                continue
            if self._strings.resolves(value, self._own_sections):
                continue
            attr_path = f"{path}.{attr}" if path else attr
            # A bare key that only foreign sections declare is the
            # actionable sub-case: the fix is a move or a fully-qualified
            # spelling, not a new registration.
            foreign = [
                section
                for section in self._strings.sections_declaring_bare(value)
                if section not in self._own_sections
            ]
            hint = (
                "declared only in foreign section(s) "
                + ", ".join(foreign)
                + " — move the key to this layout's own section or use the "
                + "fully-qualified '<section>_<key>' spelling"
                if foreign
                else None
            )
            findings.append(
                Finding(
                    layout=layout,
                    path=attr_path,
                    attribute=attr,
                    value=value,
                    hint=hint,
                )
            )

    def _walk(self, node: Any, layout: str, path: str, findings: list[Finding]) -> None:
        if isinstance(node, dict):
            if "type" in node:
                self._check_node(node, node.get("type"), layout, path, findings)
                # platform / responsive patch maps override attributes of
                # THIS node — judge patched values in the same context.
                for patch_key in _PATCH_MAP_KEYS:
                    patches = node.get(patch_key)
                    if not isinstance(patches, dict):
                        continue
                    for scope, patch in patches.items():
                        if isinstance(patch, dict):
                            self._check_node(
                                patch,
                                node.get("type"),
                                layout,
                                f"{path}.{patch_key}.{scope}" if path else f"{patch_key}.{scope}",
                                findings,
                            )
            for key, value in node.items():
                if key in _PATCH_MAP_KEYS:
                    continue  # judged above, in the owning node's context
                child_path = f"{path}.{key}" if path else key
                self._walk(value, layout, child_path, findings)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                self._walk(item, layout, f"{path}[{index}]", findings)


# ----------------------------------------------------------------------
# Allowlist ledger (two-way ratchet)


@dataclass
class Allowlist:
    path: Path
    entries: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Allowlist":
        if not path.exists():
            return cls(path=path, entries=[])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise LintStringsSetupError(f"unreadable allowlist ({path}): {e}")
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise LintStringsSetupError(
                f"allowlist {path} must be an object with an 'entries' array"
            )
        return cls(path=path, entries=[e for e in entries if isinstance(e, dict)])

    def save(self) -> None:
        payload = {
            "_comment": (
                "jui lint-strings allowlist — intentional non-localized "
                "layout literals, one entry per (layout, path, value), "
                "reason required. The check fails in BOTH directions: an "
                "unlisted raw literal, and a stale entry whose literal no "
                "longer exists."
            ),
            "entries": self.entries,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def key_of(self, entry: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(entry.get("layout", "")),
            str(entry.get("path", "")),
            str(entry.get("value", "")),
        )


@dataclass
class LintReport:
    findings: list[Finding] = field(default_factory=list)  # not allowlisted
    allowed: list[Finding] = field(default_factory=list)  # covered by ledger
    stale_entries: list[dict[str, Any]] = field(default_factory=list)
    missing_reason: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    scanned_layouts: int = 0

    @property
    def clean(self) -> bool:
        return not (
            self.findings
            or self.stale_entries
            or self.missing_reason
            or self.duplicates
        )

    def warning_lines(self) -> list[str]:
        """Findings rendered for the `jui build` warning stream."""
        lines: list[str] = []
        for f in self.findings:
            base = (
                f"{f.layout} {f.path}: raw literal {f.value!r} does not "
                f"resolve via strings.json — register a key (jsonui-localize) "
                f"or allowlist it with a reason"
            )
            lines.append(f"{base} ({f.hint})" if f.hint else base)
        for entry in self.stale_entries:
            lines.append(
                f"allowlist entry is stale (literal no longer present): "
                f"{entry.get('layout')} {entry.get('path')} value "
                f"{entry.get('value')!r} — remove it from the ledger"
            )
        for entry in self.missing_reason:
            lines.append(
                f"allowlist entry has no reason: {entry.get('layout')} "
                f"{entry.get('path')} value {entry.get('value')!r} — the "
                f"ledger records WHY a literal stays unlocalized"
            )
        for dup in self.duplicates:
            sites = ", ".join(f"{group}.{key}" for group, key in dup.sites)
            lines.append(
                f"strings.json declares {dup.value!r} in "
                f"{len(dup.sections())} sections ({sites}) — each platform "
                f"resolves it to a different key and section order decides "
                f"the winner; keep one declaration"
            )
        return lines


def collect_findings(
    config_mgr: ConfigManager,
    allowlist_path: Path | None = None,
    *,
    definitions_path: Path | None = None,
    string_props_path: Path | None = None,
) -> LintReport:
    """Run the full scan for a project. Raises LintStringsSetupError when
    a required asset is missing. The two SSoT paths are injectable for
    tests; production callers rely on the installed-tree lookup."""
    # AliasTable.from_file degrades to an empty table on a missing file;
    # for a lint that must not silently pass, resolve and check explicitly.
    from ..core.normalizer.alias_table import default_definitions_path

    resolved_defs = definitions_path or default_definitions_path()
    if resolved_defs is None or not Path(resolved_defs).exists():
        raise LintStringsSetupError(
            "attribute_definitions.json not found near the installed "
            "jui_tools — cannot derive per-component visible attributes"
        )
    try:
        definitions = json.loads(Path(resolved_defs).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise LintStringsSetupError(
            f"unreadable attribute_definitions.json ({resolved_defs}): {e}"
        )

    vocabulary = load_string_props(string_props_path)
    alias_table = AliasTable(definitions)
    visible_map = visible_attrs_by_component(definitions, vocabulary)
    strings = StringsTable.load(default_strings_path(config_mgr))

    config = config_mgr.load()
    lint_cfg = config.get("lint") or {}
    if allowlist_path is None:
        configured = (
            lint_cfg.get("stringsAllowlist") if isinstance(lint_cfg, dict) else None
        )
        allowlist_path = (
            config_mgr.project_root / configured
            if configured
            else config_mgr.project_root / ALLOWLIST_FILENAME
        )
    allowlist = Allowlist.load(allowlist_path)

    scanner = LayoutScanner(alias_table, visible_map, vocabulary, strings)
    canonicalizer = Canonicalizer(alias_table)
    styles_dir = config_mgr.styles_directory
    style_merger = StyleMerger(styles_dir) if styles_dir.exists() else None

    layouts_dir = config_mgr.layouts_directory
    skip_prefixes = {"Resources"}
    if styles_dir.exists() and layouts_dir in styles_dir.parents:
        skip_prefixes.add(styles_dir.relative_to(layouts_dir).parts[0])

    report = LintReport()
    # A forked declaration is a property of strings.json, so it is judged
    # once here rather than per referencing layout.
    report.duplicates = strings.duplicate_declarations()
    all_findings: list[Finding] = []
    if layouts_dir.exists():
        # Pass 1: load every tree, so the include graph can be built before
        # any file is judged. Each file is still scanned once, as itself —
        # includes are NOT expanded — but bare-key scoping needs to know who
        # includes whom (see _own_sections_map).
        trees: dict[str, Any] = {}
        for src_file in sorted(layouts_dir.rglob("*.json")):
            rel = src_file.relative_to(layouts_dir)
            if rel.parts[0] in skip_prefixes:
                continue
            try:
                tree = json.loads(src_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # jui build validates JSON health; not this lint's job
            if not isinstance(tree, dict):
                continue
            trees[rel.as_posix()] = tree

        own_sections_by_layout = _own_sections_map(trees)

        # Pass 2: judge each file with its full section scope.
        for rel_posix in sorted(trees):
            tree = trees[rel_posix]
            # Canonicalize aliases, merge style-declared values, then
            # canonicalize once more — styles may use alias spellings.
            working, _ = canonicalizer.canonicalize(
                tree, source=rel_posix, add_marker=False
            )
            if style_merger is not None:
                working = style_merger.resolve(copy.deepcopy(working))
                working, _ = canonicalizer.canonicalize(
                    working, source=rel_posix, add_marker=False
                )
            all_findings.extend(
                scanner.scan(working, rel_posix, own_sections_by_layout[rel_posix])
            )
            report.scanned_layouts += 1

    allowed_keys: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in allowlist.entries:
        allowed_keys[allowlist.key_of(entry)] = entry

    matched_entries: set[tuple[str, str, str]] = set()
    for finding in all_findings:
        entry = allowed_keys.get(finding.key())
        if entry is None:
            report.findings.append(finding)
            continue
        matched_entries.add(finding.key())
        if str(entry.get("reason") or "").strip():
            report.allowed.append(finding)
        else:
            report.missing_reason.append(entry)

    for key, entry in allowed_keys.items():
        if key not in matched_entries:
            report.stale_entries.append(entry)

    return report


# ----------------------------------------------------------------------
# CLI


def register_lint_strings_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "lint-strings",
        help="Flag user-visible layout literals that don't resolve via strings.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON (findings, stale entries, counts)",
    )
    parser.add_argument(
        "--update-allowlist",
        action="store_true",
        help=(
            "Write the current raw-literal set into the allowlist ledger, "
            "preserving reasons of entries that already exist. New entries "
            "get an empty reason and keep the lint failing until documented."
        ),
    )
    parser.add_argument(
        "--allowlist",
        type=str,
        default=None,
        help=f"Ledger path (default: {ALLOWLIST_FILENAME} at the project root, "
        "or lint.stringsAllowlist from jui.config.json)",
    )
    parser.set_defaults(func=cmd_lint_strings)


EXIT_OK = 0
EXIT_SETUP = 1
EXIT_FINDINGS = 2


def cmd_lint_strings(args: argparse.Namespace) -> int:
    config_mgr = ConfigManager()
    if not config_mgr.exists():
        print("ERROR: jui.config.json not found. Run 'jui init' first.")
        return EXIT_SETUP

    allowlist_path = (
        config_mgr.project_root / args.allowlist if args.allowlist else None
    )

    try:
        report = collect_findings(config_mgr, allowlist_path=allowlist_path)
    except LintStringsSetupError as e:
        print(f"ERROR [lint-strings]: {e}")
        return EXIT_SETUP

    if args.update_allowlist:
        return _update_allowlist(config_mgr, args, report)

    if args.json:
        print(
            json.dumps(
                {
                    "scannedLayouts": report.scanned_layouts,
                    "findings": [f.__dict__ for f in report.findings],
                    "allowed": len(report.allowed),
                    "staleEntries": report.stale_entries,
                    "missingReason": report.missing_reason,
                    "duplicateDeclarations": [
                        {
                            "value": d.value,
                            "sites": [
                                {"section": group, "key": key} for group, key in d.sites
                            ],
                        }
                        for d in report.duplicates
                    ],
                    "clean": report.clean,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK if report.clean else EXIT_FINDINGS

    print(
        f"lint-strings: scanned {report.scanned_layouts} layout(s), "
        f"{len(report.allowed)} allowlisted literal(s)"
    )
    if report.clean:
        print("lint-strings: clean")
        return EXIT_OK
    for line in report.warning_lines():
        print(f"  WARNING [lint-strings]: {line}")
    print(
        f"\nlint-strings: {len(report.findings)} raw literal(s), "
        f"{len(report.duplicates)} forked declaration(s), "
        f"{len(report.stale_entries)} stale allowlist entr(ies), "
        f"{len(report.missing_reason)} without a reason"
    )
    return EXIT_FINDINGS


def _update_allowlist(
    config_mgr: ConfigManager, args: argparse.Namespace, report: LintReport
) -> int:
    """--update-allowlist: current raw literals become the ledger, reasons
    already recorded are preserved, stale entries drop out."""
    path = (
        config_mgr.project_root / args.allowlist
        if args.allowlist
        else None
    )
    if path is None:
        config = config_mgr.load()
        lint_cfg = config.get("lint") or {}
        configured = (
            lint_cfg.get("stringsAllowlist") if isinstance(lint_cfg, dict) else None
        )
        path = (
            config_mgr.project_root / configured
            if configured
            else config_mgr.project_root / ALLOWLIST_FILENAME
        )

    try:
        existing = Allowlist.load(path)
    except LintStringsSetupError as e:
        print(f"ERROR [lint-strings]: {e}")
        return EXIT_SETUP
    reasons = {
        existing.key_of(entry): str(entry.get("reason") or "")
        for entry in existing.entries
    }

    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in report.findings + report.allowed:
        key = finding.key()
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "layout": finding.layout,
                "path": finding.path,
                "value": finding.value,
                "reason": reasons.get(key, ""),
            }
        )
    entries.sort(key=lambda e: (e["layout"], e["path"], e["value"]))

    ledger = Allowlist(path=path, entries=entries)
    ledger.save()
    undocumented = sum(1 for e in entries if not e["reason"].strip())
    rel = path.relative_to(config_mgr.project_root)
    print(f"Allowlist written: {rel} ({len(entries)} entries)")
    if undocumented:
        print(
            f"  {undocumented} entr(ies) have an empty reason — fill them in; "
            f"the lint keeps failing until every entry documents WHY"
        )
        return EXIT_FINDINGS
    return EXIT_OK


# ----------------------------------------------------------------------
# jui build integration (opt-in; the enabled check lives in build_cmd so
# the default build path never imports this module)


def run_for_build(config_mgr: ConfigManager) -> list[str]:
    """Scan and return warning lines for the build output. Setup errors
    surface as a warning too — an opted-in gate must not silently pass."""
    try:
        report = collect_findings(config_mgr)
    except LintStringsSetupError as e:
        return [f"lint-strings could not run: {e}"]
    return report.warning_lines()
