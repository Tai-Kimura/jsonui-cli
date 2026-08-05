"""``jui conformance codegen-effect`` — the codegen-stage differential (plan 41).

The render-stage conformance suite proves that a fixture keeps looking the way
it looked last time. It cannot prove that a fixture is *discriminating*: an
attribute whose value is never read produces the same picture as the control,
and an attribute whose bound form is silently dropped produces the same picture
as a fixture that never declared it. Two shipped defects came out of exactly
that blind spot:

- plan 36 — rjui handed a bound ``height`` to a Tailwind arbitrary-value
  mapper whose else-branch returned ``''``. Class, style and warning all
  vanished; every bar in a consumer's chart rendered at height 0. The
  dimension fixtures only ever wrote *static* values, so the lane was green.
- plan 34 — the SSoT spelled the slider tint ``progressTintColor`` and no
  converter read that spelling. The fixture's thumb sat at the minimum, so the
  painted track had zero width and *no* value of the attribute could have
  changed a pixel. Unmeasurable by construction.

Both are obvious in the emitted source text. This module compares that text
instead of pixels, which is a stronger check and a far cheaper one — no
device, no threshold, no geometry mask, and no fixture: the production
converter is called directly with a layout hash, the way each tool's own specs
call it.

Three judgements per (component, attribute, platform), all mechanical:

===== ==================================== ==================================
C0    ``emit(attr=v1) != emit(control)``   nothing reads the spelling
C1    ``emit(attr="@{v}") != emit(control)``  the bound form is dropped
      and the output names the bound var
C2    ``emit(attr=v1) != emit(attr=v2)``   a fixed value is emitted regardless
C3    ``emit(attr=10) == emit(attr="10")`` a numeric STRING takes a different
                                           path than the number
===== ==================================== ==================================

C3 is the one that compares for EQUALITY, and it exists because plan 43 found
that the defect it had just fixed for a bound margin fired on ``"10"`` too —
`"10" - 0` raises exactly what `"@{v}" - 0` raises. A number attribute can be
written three ways (number, numeric string, binding) and a lane split two ways
misses the one in the middle. Two spellings of the same value have no reason
to emit different text, so a difference — and certainly a crash on one side
only — is a defect.

Scope. This is the *codegen* stage and says so: it proves the converter reads
the attribute and puts it in the output, never that the library then honours
it. Plan 34's `matchParent` collapse and plan 39's symmetric margin were both
emitted correctly and ignored downstream; those belong to the render stage.
The value of splitting them is ordering — once the codegen stage is green, a
render-stage difference has already been narrowed to the library or the
dynamic path.

Two structural blind spots, both inherited from what a Ruby codegen *is*:

- **UIKit.** The UIKit path applies attributes in the SwiftJsonUI Swift
  runtime straight off the layout JSON; the Ruby side emits no text to
  compare. `coverage.MODE_TAGS` already maps ``uikit`` to no platform, and
  this module scopes those attributes out through the same function rather
  than reporting every one of them as a failure.
- **dynamic.** The dynamic renderers interpret the JSON at run time and have
  no codegen output at all. A defect found here has to be checked by hand
  against the dynamic path — see plan 39, where the same defect existed in
  both and only the codegen one was obvious.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import coverage as cov
from . import fixture_generator as fg
from . import rules

#: Report schema version; bump when the entry shape changes.
SCHEMA_VERSION = 1

PLATFORMS = cov.PLATFORMS

#: Property name written into every bound probe. Distinctive enough that
#: finding it in the emitted text is proof the binding reached the output, and
#: not a substring of anything a converter emits on its own.
BINDING_VAR = "juiProbeValue"
BOUND_VALUE = f"@{{{BINDING_VAR}}}"

#: platform -> (tool directory, probe script relative to it).
PROBES: dict[str, tuple[str, str]] = {
    "ios": ("sjui_tools", "tools/codegen_probe.rb"),
    "android": ("kjui_tools", "tools/codegen_probe.rb"),
    "web": ("rjui_tools", "tools/codegen_probe.rb"),
}

#: The mode each platform's probe drives, recorded in the report so the
#: coverage claim is never read wider than it is. Both omissions are
#: structural, not backlog: see the module docstring (UIKit) and the KJUI
#: XML-mode freeze of 2026-07-03 (Compose-only, XML defects are won't-fix).
PROBE_MODES: dict[str, str] = {
    "ios": "swiftui",
    "android": "compose",
    "web": "react",
}

CHECKS = ("C0", "C1", "C2", "C3")

#: Why a (component, attribute, platform) is not probed at all. Recorded
#: rather than dropped — the campaign's premise is that a silent omission is
#: how both specimen defects survived.
OUT_OF_SCOPE_REASONS = {
    # rules.plan_attribute refused to fixture it; the reason string is the
    # rules module's own (callback / metadata / structural / …).
    "unfixturable",
    # Declared only for a mode with no Ruby codegen (uikit / dynamic-only), or
    # deprecated on every platform.
    "no-codegen-platform",
    # Alias case: the canonical spelling owns the probe.
    "alias-case",
}


# --------------------------------------------------------------------------- #
# Second representative value
# --------------------------------------------------------------------------- #
#
# `rules.representative_value` picks the ONE value the fixture suite writes.
# C2 needs a second one, and it lives here rather than next to its sibling
# because `rules.py` is shared with two other in-flight plans; the primary
# value, the case plan, the host and the platform scope are all imported from
# there, so there is still exactly one truth about what a fixture looks like.
#
# The render stage needed a second value COARSE enough to cross a pixel
# threshold. The codegen stage does not: one differing bit changes the text.

#: Colour used as the second value wherever the first is the standard red.
SECONDARY_COLOR = "#0000FF"
#: …and the fallback when the first is already blue.
SECONDARY_COLOR_ALT = "#00FF00"

#: Suffix appended to free-form strings. Deliberately alphanumeric: a value
#: that has to survive a slug/identifier round-trip in some converter should
#: not fail for punctuation reasons and read as a defect.
STRING_SUFFIX = "Two"


def _second_number(primary: Any, defn: dict) -> Any:
    """A number that differs from *primary* and still satisfies min/max.

    Doubling is the natural choice but collapses under a `max` (an `opacity`
    of 0.5 doubles to 1.0 and clamps back), so the candidates walk outward and
    then inward, and the first one that survives clamping is used.
    """
    is_int = isinstance(primary, int) and not isinstance(primary, bool)
    candidates = [primary * 2 + 1, primary + 1, primary - 1, primary / 2, 0, 1]
    for candidate in candidates:
        value = rules._clamp(candidate, defn)
        if is_int and isinstance(value, float) and value.is_integer():
            value = int(value)
        if value != primary:
            return value
    return None


def _second_scalar(attribute: str, primary: Any, defn: dict) -> Any:
    """Second value for one scalar, or ``None`` when none can be derived."""
    if isinstance(primary, bool):
        return not primary
    if isinstance(primary, (int, float)):
        return _second_number(primary, defn)
    if isinstance(primary, str):
        if primary.startswith("#"):
            return SECONDARY_COLOR if primary.upper() != SECONDARY_COLOR else SECONDARY_COLOR_ALT
        if attribute in rules.IMAGE_ATTRS:
            # The suite bundles exactly two assets; a name outside them would
            # make the probe measure "unknown resource" instead of the swap.
            return (
                rules.IMAGE_ALT_ASSET_NAME
                if primary != rules.IMAGE_ALT_ASSET_NAME
                else rules.IMAGE_ASSET_NAME
            )
        return f"{primary}{STRING_SUFFIX}"
    return None


def secondary_value(section: str, attribute: str, defn: dict, primary: Any) -> tuple[bool, Any]:
    """Return ``(found, value)`` — a second value C2 can compare against.

    Composite values recurse into their leaves so a list or object attribute
    (``paddings``, ``highlightAttributes``, ``gradient``) still gets a probe;
    if no leaf can move, the attribute has no C2 lane and is recorded as such.
    """
    if attribute in rules.VIEW_REF_ATTRS:
        # The fixture layout carries exactly one anchor sibling, so there is no
        # second view to point at. C0 still applies.
        return False, None

    if isinstance(primary, list):
        out = [_second_scalar(attribute, item, defn) for item in primary]
        if any(v is None for v in out) or out == primary:
            return False, None
        return True, out

    if isinstance(primary, dict):
        out = {}
        changed = False
        for key, value in primary.items():
            second = _second_scalar(key, value, defn)
            out[key] = primary[key] if second is None else second
            changed = changed or second is not None
        if not changed:
            return False, None
        return True, out

    value = _second_scalar(attribute, primary, defn)
    if value is None or value == primary:
        return False, None
    return True, value


# --------------------------------------------------------------------------- #
# Job table
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Probe:
    """One (component, attribute, platform) and the emits it needs."""

    component: str
    attribute: str
    platform: str
    host: str
    control_id: str
    primary: Any
    secondary: Any
    has_secondary: bool
    secondary_source: str  # "enum-case" | "derived" | "" when absent
    bindable: bool
    #: The numeric value C3 writes both ways, or None when the attribute has
    #: no numeric case at all. Taken from the case plan rather than re-derived,
    #: so it is a value the fixture suite actually writes.
    numeric: Any = None
    #: True when the representative value is the generic string fallback —
    #: the SSoT declared a bare `string` with no enum, no default, no override
    #: and no companion base attribute, so nothing says what values this
    #: attribute accepts. `keyboardType: "sample"` is the shape: the
    #: comparison is sound, but a converter that ignores an out-of-vocabulary
    #: value looks exactly like one that ignores the attribute, and the first
    #: repair is an enum in attribute_definitions.json.
    #:
    #: A companion base attribute clears the flag, because it means the
    #: fixture was deliberately shaped to make this value meaningful —
    #: `Radio.selectedValue` gets `value: "sample"` so the probe value names
    #: the selected option, and there a constant emit IS a converter defect.
    weak_value: bool = False
    #: True when the host's base attributes already write the primary value,
    #: so the "control" carries the attribute under test and C0 cannot decide
    #: anything. `Image.src` is the clearest case: the base needs a source to
    #: render at all, and the representative value for `src` is that same
    #: bundled asset, so fixture and control are the same layout.
    control_carries_primary: bool = False

    @property
    def key(self) -> str:
        return f"{self.component}.{self.attribute}"

    def job_id(self, kind: str) -> str:
        return f"{self.component}|{self.attribute}|{kind}"


@dataclass(frozen=True)
class OutOfScope:
    component: str
    attribute: str
    scope_reason: str
    detail: str


@dataclass
class JobTable:
    probes: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    #: platform -> [{"id":…, "layout":…}] fed to that platform's probe script
    jobs: dict = field(default_factory=dict)
    #: (component, attribute) -> CompanionSpec actually applied. Empty on a
    #: plain run; the report prints it so a paired verdict always carries the
    #: ledger statement its companions were derived from.
    paired: dict = field(default_factory=dict)


#: Label written into the `_generated` marker of every probe layout. The
#: layouts are never persisted, but `build_layout` stamps one and a stable
#: string keeps the emitted text byte-identical between runs.
SOURCE_LABEL = "conformance codegen-effect probe"

#: Sentinel for "the control layout does not write this key at all".
_MISSING = object()


def _as_numeric_string(value) -> str:
    """`10` -> `"10"`, `1.5` -> `"1.5"` — the same number, hand-written.

    A float that happens to be integral renders without its `.0`, because
    that is how someone writing the layout by hand would type it and the
    point of C3 is the spelling a human produces.
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _target_node(layout: dict) -> dict:
    """The component under test inside a probe layout (always the last child)."""
    children = layout.get("child") or []
    return children[-1] if children else {}


#: `@{` cannot legally appear in emitted Swift, Kotlin or TSX — every binding
#: is supposed to have been resolved into a property access by the converter.
#: Finding it in the output is proof the expression leaked into the source.
_RAW_BINDING = re.compile(r"@\{")


def _leak_line(text: str):
    """`(line, match)` for the first `@{...}` leak in an emit, or `(None, None)`."""
    for line in text.splitlines():
        match = _RAW_BINDING.search(line)
        if match:
            return line, match
    return None, None


def _leak_context(text: str, width: int = 90) -> str:
    """The emitted line the `@{...}` leak sits on, for the report."""
    line, _ = _leak_line(text)
    if line is None:
        return ""
    stripped = line.strip()
    return stripped[:width] + (" …" if len(stripped) > width else "")


def _leak_is_literal(text: str) -> bool:
    """Whether the leak sits INSIDE a string literal rather than in code.

    The distinction is the whole severity split, so it is measured rather than
    assumed. `Text("@{v}")` compiles — and then shows the user the characters
    `@{v}`. `fontSize = @{v}.sp` does not compile at all. Both are defects;
    only the second stops the build, so they are reported as different classes
    and must not be merged into one scary number.

    Counting unescaped quotes before the match is enough for generated code:
    the emitters produce one statement per line and never leave a string open
    across lines.
    """
    line, match = _leak_line(text)
    if line is None:
        return False
    prefix = line[: match.start()]
    for quote in ('"', "'", "`"):
        if (prefix.count(quote) - prefix.count("\\" + quote)) % 2 == 1:
            return True
    return False


def _apply_companions(node: tuple, companions: dict) -> tuple:
    """Write the companion attributes onto a probe layout's target node.

    Applied to the control AND to every case alike, so the companions cancel
    in the comparison and the only difference left is the attribute under
    test. This is what makes a pair-required attribute judgeable at all —
    see `companions` for where the pairs come from.
    """
    layout, data = node
    target = _target_node(layout)
    for key, value in companions.items():
        target[key] = value
    return layout, data


# The probe converts the WHOLE fixture layout — root wrapper, anchor sibling
# and target — not the target node alone. Converting the node alone was tried
# and is wrong for every attribute whose meaning IS its context: a view
# reference (`alignTopOfView: "anchor"`) has no sibling to point at, and the
# parent-relative constraints (`alignTop`, `centerInParent`, `weight`) are
# resolved by the parent. All of them emitted nothing and read as "the
# spelling is unread" — 38 findings that said more about the probe than about
# any converter.
#
# The root wrapper is byte-identical on both sides of every comparison, so it
# contributes context and nothing else. What converting it could have cost is
# completeness, because part of a converter's emission leaves OUT OF BAND —
# sjui pushes `@State` declarations into `state_variables` and kjui collects
# imports on the builder, and neither appears in the returned snippet. It does
# not cost it: `child_renderer` / `child_rendering_helper` concatenate every
# child's `state_variables` into the parent's, and kjui's import set is
# per-build rather than per-node, so both aggregate upward on their own. Each
# probe returns the root emission plus that aggregated out-of-band output.


def _control_node(host: str, needs_anchor: bool, extra: dict | None) -> tuple[dict, list]:
    layout = fg.build_control_layout(host, needs_anchor, extra, source_label=SOURCE_LABEL)
    layout.pop("_generated", None)
    return layout, layout.get("data") or []


def _case_node(plan: rules.AttributePlan, value: Any) -> tuple[dict, list]:
    case = rules.CasePlan(name="probe", value=value, written_key=plan.attribute)
    layout = fg.build_layout(plan, case, source_label=SOURCE_LABEL)
    layout.pop("_generated", None)
    return layout, layout.get("data") or []


def build_jobs(definitions: dict, platforms=PLATFORMS, companion_specs: dict | None = None) -> JobTable:
    """Plan every probe and the per-platform emit jobs they need.

    The plan (host, base attributes, representative value, platform scope) is
    imported from `rules` / `fixture_generator` wholesale — this module adds
    only the second value and the bound form.

    *companion_specs* (``{(component, attribute): CompanionSpec}``) turns the
    run into the PAIRED probe: the companions are written on the control and
    on every case, so they cancel and the attribute under test is again the
    only difference. Attributes with no spec are probed exactly as before, so
    the paired run is a superset rather than a separate lane.
    """
    table = JobTable(jobs={p: [] for p in platforms})
    seen_jobs: dict[str, set] = {p: set() for p in platforms}

    for section, attrs in (definitions or {}).items():
        if section.startswith("_") or not isinstance(attrs, dict):
            continue
        if isinstance(attrs.get("_alias_of"), str):
            table.out_of_scope.append(
                OutOfScope(section, "*", "alias-case", rules.REASON_COMPONENT_ALIAS)
            )
            continue

        for attribute, defn in attrs.items():
            plan = rules.plan_attribute(section, attribute, defn)
            if isinstance(plan, rules.SkippedAttribute):
                table.out_of_scope.append(
                    OutOfScope(section, attribute, "unfixturable", plan.reason)
                )
                continue

            # `coverage.applicable_platforms` is the right scope here, not
            # `rules._platforms`: this check asks whose *Ruby converter* must
            # read the attribute, which is the question `coverage` answers
            # (and the reason it maps `uikit` to nothing).
            applicable = [p for p in cov.applicable_platforms(defn) if p in platforms]
            if not applicable:
                table.out_of_scope.append(
                    OutOfScope(
                        section,
                        attribute,
                        "no-codegen-platform",
                        f"mode={defn.get('mode')!r} platform={defn.get('platform')!r} "
                        f"deprecated={defn.get('deprecated')!r}",
                    )
                )
                continue

            cases = [c for c in plan.cases if c.alias_of is None]
            if not cases:
                table.out_of_scope.append(
                    OutOfScope(section, attribute, "alias-case", "no canonical case")
                )
                continue

            primary = cases[0].value
            secondary_source = ""
            has_secondary = False
            secondary: Any = None
            for case in cases[1:]:
                if case.value != primary:
                    secondary, has_secondary, secondary_source = case.value, True, "enum-case"
                    break
            if not has_secondary:
                has_secondary, secondary = secondary_value(section, attribute, defn, primary)
                secondary_source = "derived" if has_secondary else ""

            extra = rules.base_attrs_for(plan.host, attribute)
            control_id = fg.control_id(
                plan.host, plan.needs_anchor, fg.control_shape(plan.host, attribute)
            )

            control_node, control_data = _control_node(plan.host, plan.needs_anchor, extra)
            probe_nodes = {
                "primary": _case_node(plan, primary),
                "control": (control_node, control_data),
            }
            control_carries_primary = (
                _target_node(control_node).get(attribute, _MISSING) == primary
            )
            if has_secondary:
                probe_nodes["secondary"] = _case_node(plan, secondary)
            bindable = cov.declares_binding(defn)
            if bindable:
                probe_nodes["bound"] = _case_node(plan, BOUND_VALUE)

            # C3 needs a number the fixture suite actually writes. `width`
            # leads with its enum cases (`matchParent`), so the numeric case
            # is looked for across the whole plan rather than taken from the
            # front — the numeric spelling of a dimension is exactly what
            # plan 43 crashed on.
            numeric = next(
                (
                    c.value
                    for c in cases
                    if isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
                ),
                None,
            )
            if numeric is not None:
                if numeric != primary:
                    probe_nodes["numeric"] = _case_node(plan, numeric)
                probe_nodes["numeric_string"] = _case_node(plan, _as_numeric_string(numeric))

            # Paired probe. Applied last so it covers every node built above,
            # control included — the companions have to cancel, or the probe
            # would be measuring the companion instead of the attribute.
            spec = (companion_specs or {}).get((section, attribute))
            if spec is not None:
                probe_nodes = {
                    name: _apply_companions(node, spec.companions)
                    for name, node in probe_nodes.items()
                }
                table.paired[(section, attribute)] = spec
                control_carries_primary = (
                    _target_node(probe_nodes["control"][0]).get(attribute, _MISSING) == primary
                )

            probe = Probe(
                component=section,
                attribute=attribute,
                platform="",
                host=plan.host,
                control_id=control_id,
                primary=primary,
                secondary=secondary,
                has_secondary=has_secondary,
                secondary_source=secondary_source,
                bindable=bindable,
                control_carries_primary=control_carries_primary,
                weak_value=(
                    secondary_source != "enum-case"
                    and primary == rules.DEFAULT_STRING
                    and not extra
                ),
                numeric=numeric,
            )

            for platform in applicable:
                table.probes.append(
                    Probe(
                        component=probe.component,
                        attribute=probe.attribute,
                        platform=platform,
                        host=probe.host,
                        control_id=probe.control_id,
                        primary=probe.primary,
                        secondary=probe.secondary,
                        has_secondary=probe.has_secondary,
                        secondary_source=probe.secondary_source,
                        bindable=probe.bindable,
                        control_carries_primary=probe.control_carries_primary,
                        weak_value=probe.weak_value,
                        numeric=probe.numeric,
                    )
                )
                for kind, (node, data) in probe_nodes.items():
                    job_id = (
                        f"__control|{control_id}"
                        if kind == "control"
                        else f"{section}|{attribute}|{kind}"
                    )
                    if job_id in seen_jobs[platform]:
                        continue
                    seen_jobs[platform].add(job_id)
                    table.jobs[platform].append(
                        {"id": job_id, "node": node, "data": data}
                    )

    return table


# --------------------------------------------------------------------------- #
# Running the probes
# --------------------------------------------------------------------------- #


class ProbeError(RuntimeError):
    """The probe script could not be run at all (missing Ruby, syntax error…)."""


def run_probe(repo_root, platform: str, jobs: list, ruby: str = "ruby") -> dict:
    """Run one platform's probe and return ``{job id: result dict}``.

    The probe writes to a file rather than stdout: every one of these trees
    logs to stdout somewhere, and a single stray line would corrupt the
    protocol in a way that looks like a converter defect.
    """
    tool_dir, script = PROBES[platform]
    cwd = Path(repo_root) / tool_dir
    script_path = cwd / script
    if not script_path.is_file():
        raise ProbeError(f"probe script not found: {script_path}")

    with tempfile.TemporaryDirectory(prefix="jui-codegen-effect-") as tmp:
        jobs_path = Path(tmp) / "jobs.json"
        out_path = Path(tmp) / "results.json"
        jobs_path.write_text(
            json.dumps({"platform": platform, "jobs": jobs}, ensure_ascii=False),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [ruby, script, str(jobs_path), str(out_path)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not out_path.is_file():
            cmd = " ".join(shlex.quote(p) for p in [ruby, script, "<jobs>", "<results>"])
            raise ProbeError(
                f"{platform} probe failed (exit {proc.returncode}) in {cwd}\n"
                f"  $ {cmd}\n{proc.stderr.strip()[:2000]}"
            )
        payload = json.loads(out_path.read_text(encoding="utf-8"))

    return {entry["id"]: entry for entry in payload.get("results", [])}


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #


#: What a failing judgement MEANS once the three checks are read together.
#:
#: C0 on its own cannot separate "no converter reads this spelling" from "the
#: representative value happens to produce the default output" — plan 34 hit
#: exactly this and recorded `value-is-default` as *not machine-derivable*
#: from the SSoT (only 5 attributes declare a `default`, none of them
#: matching). At the codegen stage it becomes derivable, because C2 answers it
#: from the other side: if two different values emit different text, the
#: converter demonstrably reads the attribute, so a C0 failure can only be the
#: value coinciding with the default. That pairing is the whole reason the
#: three checks are run together rather than shipped as three lanes.
FINDING_CLASSES = {
    # C0 fails and C2 fails: the attribute changes nothing, whatever you set.
    # This is the plan-34 Slider-tint shape and the strongest signal here.
    "unread-spelling",
    # C0 fails, C2 has no second value to compare: same suspicion, unconfirmed.
    "unread-spelling-unconfirmed",
    # C0 fails but C2 passes: the converter DOES read it; the representative
    # value simply emits what the control already emits. A fixture-value
    # finding, not an implementation one — it says the FIXTURE discriminates
    # nothing, and giving `representative_value()` a different value restores
    # it. Reported separately from the defect queue and deliberately kept OUT
    # of any ledger (2026-08-04 adjudication): it is re-derived from C2 on
    # every run, so recording it would make every entry go stale the moment a
    # representative value changed, and a two-way ratchet would misfire.
    "value-is-default",
    # C0 passes, C2 fails: the converter reacts to the attribute being present
    # but emits the same text for every value.
    "presence-only",
    # C1: the bound form emits EXACTLY the control. The attribute vanishes;
    # the layout renders as if it had never been written (plan 36's shape).
    "bound-dropped",
    # C1: the bound form emits something, but the value did not travel — the
    # converter evaluated the `@{...}` STRING as a boolean / number / enum and
    # baked the result in as a constant. Ruby's type looseness is the whole
    # mechanism: `"@{x}"` is truthy, `"@{x}".to_i` is 0, and `"@{x}" != 'none'`
    # is true. This is WORSE than dropped and is why it is counted separately
    # (2026-08-04 orchestrator adjudication, third new class after 34's
    # `instrument-limited` and 43's `numeric-string`): dropping leaves the
    # layout bare, freezing produces code that compiles, runs, and renders a
    # wrong constant — and the SSoT says the value is legal, so no validator
    # warns.
    "bound-frozen",
    # C1: the `@{...}` text reached the generated source VERBATIM, in CODE
    # position. Not a wrong constant — not a program. `.border(@{v}.dp, …)` is
    # not Kotlin and the build dies on it, which puts this at plan 43's
    # severity rather than `bound-frozen`'s. Detected structurally: `@{` can
    # never legally appear in emitted Swift/Kotlin/TSX.
    "bound-uncompilable",
    # C1: the same leak, but INSIDE a string literal — `Text("@{v}")`,
    # `className="text-[@{v}px]"`. It compiles, so the build stays green, and
    # then the characters `@{v}` are what the user sees (or a Tailwind class
    # that matches nothing). Split from `bound-uncompilable` because "the
    # build dies" and "the build passes and the screen is wrong" are different
    # failures and merging them would inflate one scary number.
    "bound-literal-leak",
    # C3: `10` and `"10"` emit different text. Advisory, not a defect
    # (2026-08-04 user ruling): a numeric string is not a number, every
    # platform's validator says so on that exact attribute, and `jui build` at
    # zero warnings is the project rule — so the input cannot reach a build.
    # Measured all 68 against each platform's own validator before the ruling;
    # every one is warned. What the lane still buys is the CRASH: a converter
    # that raises aborts the build BEFORE the warning is printed, which is the
    # one way invalid input escapes the rule, and is what plan 43 fixed. That
    # side stays a hard failure through `errors`.
    "numeric-string-divergence",
    # C0 or C2 fails, but the SSoT declares a bare `string` with no enum, so
    # the probe values are the generic fallback and nothing says what the
    # attribute accepts (`keyboardType`, `contentType`,
    # `autocapitalizationType`). The comparison is sound; the conclusion is
    # not "the converter is broken" but "declare the vocabulary, then the
    # comparison means something" — a converter rejecting an unknown token
    # and a converter ignoring the attribute are indistinguishable here.
    "unenumerated-vocabulary",
}


@dataclass(frozen=True)
class Finding:
    """One failed judgement, with the evidence that produced it."""

    component: str
    attribute: str
    platform: str
    check: str
    host: str
    detail: str
    finding_class: str = ""
    primary: Any = None
    secondary: Any = None
    #: Emitted text, truncated. The whole point of the codegen stage is that
    #: the evidence is readable, so it travels with the finding.
    evidence: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.component}.{self.attribute}"

    def __str__(self) -> str:
        label = f"{self.check}/{self.finding_class}" if self.finding_class else self.check
        return f"{label} {self.key} [{self.platform}] — {self.detail}"


#: Finding classes that are NOT defects and never gate. Both are re-derived
#: from the checks on every run, so they belong in the report and nowhere
#: else — a stored entry would go stale the moment a representative value
#: changed. See the notes on each in FINDING_CLASSES.
ADVISORY_CLASSES = frozenset({"value-is-default", "numeric-string-divergence"})


@dataclass
class EffectResult:
    probes: int = 0
    checks_run: int = 0
    findings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    #: check -> number of (component, attribute, platform) the check ran on
    per_check: dict = field(default_factory=dict)
    #: reasons a check was not applicable, for the "no silent drop" ledger
    not_applicable: dict = field(default_factory=dict)
    out_of_scope: list = field(default_factory=list)

    @property
    def defects(self) -> list:
        """Findings that name something to fix. What a gate would look at."""
        return [f for f in self.findings if f.finding_class not in ADVISORY_CLASSES]

    @property
    def advisories(self) -> list:
        """Findings that say the FIXTURE discriminates nothing, not the code.

        `representative_value()` picked a value that emits what the control
        already emits; a different value restores the fixture's discriminating
        power. Reported every run, never ledgered.
        """
        return [f for f in self.findings if f.finding_class in ADVISORY_CLASSES]

    def advised(self, finding_class: str) -> list:
        """Advisories of one class. Each has its own reason for not gating."""
        return [f for f in self.findings if f.finding_class == finding_class]

    @property
    def ok(self) -> bool:
        return not self.defects and not self.errors


#: How much emitted text a finding carries. Long enough for a container's
#: whole modifier chain, short enough that a 700-entry report stays readable.
EVIDENCE_LIMIT = 400


def _clip(text: str) -> str:
    if text is None:
        return ""
    return text if len(text) <= EVIDENCE_LIMIT else text[:EVIDENCE_LIMIT] + " …"


def evaluate(table: JobTable, outputs: dict) -> EffectResult:
    """Apply C0/C1/C2 to the probe outputs. ``outputs`` is platform -> id -> result."""
    result = EffectResult(out_of_scope=list(table.out_of_scope))
    result.per_check = {c: 0 for c in CHECKS}

    for probe in table.probes:
        result.probes += 1
        per_platform = outputs.get(probe.platform, {})

        def fetch(kind: str):
            job_id = (
                f"__control|{probe.control_id}"
                if kind == "control"
                else f"{probe.component}|{probe.attribute}|{kind}"
            )
            return per_platform.get(job_id)

        emits = {
            kind: fetch(kind)
            for kind in ("control", "primary", "secondary", "bound", "numeric", "numeric_string")
        }

        failed_emit = False
        for kind in ("control", "primary"):
            entry = emits[kind]
            if entry is None:
                result.errors.append(
                    Finding(
                        probe.component, probe.attribute, probe.platform, "probe",
                        probe.host, f"no probe result for the {kind} emit",
                    )
                )
                failed_emit = True
            elif not entry.get("ok"):
                result.errors.append(
                    Finding(
                        probe.component, probe.attribute, probe.platform, "probe",
                        probe.host,
                        f"converter raised on the {kind} emit: {entry.get('error')}",
                    )
                )
                failed_emit = True
        if failed_emit:
            continue

        control = emits["control"]["output"]
        primary = emits["primary"]["output"]

        # --- C2 first: its verdict is what makes C0 readable -------------- #
        c2_verdict = None  # True = passes (value is read), False = fails
        secondary = None
        if not probe.has_secondary:
            reason = (
                "view-reference attribute (the fixture layout has one anchor)"
                if probe.attribute in rules.VIEW_REF_ATTRS
                else "no second representative value could be derived"
            )
            result.not_applicable.setdefault("C2", {}).setdefault(reason, []).append(
                f"{probe.key} [{probe.platform}]"
            )
        else:
            entry = emits["secondary"]
            if entry is None or not entry.get("ok"):
                result.errors.append(
                    Finding(
                        probe.component, probe.attribute, probe.platform, "probe",
                        probe.host,
                        f"converter raised on the secondary emit: "
                        f"{(entry or {}).get('error', 'missing')}",
                    )
                )
            else:
                secondary = entry["output"]
                result.checks_run += 1
                result.per_check["C2"] += 1
                c2_verdict = secondary != primary

        # --- C0: is the spelling read at all? ---------------------------- #
        if probe.control_carries_primary:
            # The base attributes of this host already write the value under
            # test, so "fixture" and "control" are the same layout and the
            # comparison is vacuous. Recorded, not silently dropped: the
            # render-stage fixture has the identical defect and needs a
            # distinct value (the `srcName` / NetworkImage state images
            # already got one for this exact reason).
            result.not_applicable.setdefault("C0", {}).setdefault(
                "the host's base attributes already carry the value under test — "
                "the fixture and its control are the same layout", []
            ).append(f"{probe.key} [{probe.platform}]")
        else:
            result.checks_run += 1
            result.per_check["C0"] += 1
            if primary == control:
                if probe.weak_value:
                    cls, detail = (
                        "unenumerated-vocabulary",
                        "identical to the control, but the SSoT declares a bare "
                        "string with no enum, so the probe value is outside any "
                        "vocabulary the converter accepts — enumerate it first",
                    )
                elif c2_verdict is True:
                    cls, detail = (
                        "value-is-default",
                        "identical to the control, but two different values emit "
                        "differently (C2) — the converter reads the attribute and "
                        "the representative value coincides with the default",
                    )
                elif c2_verdict is False:
                    cls, detail = (
                        "unread-spelling",
                        "identical to the control AND identical for a second value "
                        "— nothing on this platform reads the spelling",
                    )
                else:
                    cls, detail = (
                        "unread-spelling-unconfirmed",
                        "identical to the control; no second value exists to "
                        "confirm whether the spelling is read at all",
                    )
                result.findings.append(
                    Finding(
                        probe.component, probe.attribute, probe.platform, "C0", probe.host,
                        detail,
                        finding_class=cls,
                        primary=probe.primary,
                        secondary=probe.secondary,
                        evidence={"control": _clip(control), "primary": _clip(primary)},
                    )
                )

        if c2_verdict is False:
            # Reported as its own judgement only when C0 has not already
            # claimed the pair — otherwise one root produces two queue items.
            already = primary == control and not probe.control_carries_primary
            if not already:
                result.findings.append(
                    Finding(
                        probe.component, probe.attribute, probe.platform, "C2", probe.host,
                        "two different values emit byte-identical text — the "
                        "converter emits a constant instead of reading the value"
                        + (
                            "; both values came from the generic string fallback, "
                            "so the SSoT owes this attribute an enum first"
                            if probe.weak_value
                            else ""
                        ),
                        finding_class=(
                            "unenumerated-vocabulary"
                            if probe.weak_value
                            else "presence-only"
                        ),
                        primary=probe.primary,
                        secondary=probe.secondary,
                        evidence={"primary": _clip(primary), "secondary": _clip(secondary)},
                    )
                )

        # --- C3: do `10` and `"10"` take the same path? ------------------- #
        #
        # Runs BEFORE C1 on purpose: the C1 block below short-circuits with
        # `continue`, and C3 must not be skipped for the attributes that
        # declare no binding — a number written as a string is legal input
        # whether or not the attribute is bindable.
        if probe.numeric is None:
            result.not_applicable.setdefault("C3", {}).setdefault(
                "no numeric value in the case plan — the attribute takes no number", []
            ).append(f"{probe.key} [{probe.platform}]")
        else:
            number = emits["numeric"] or emits["primary"]
            text = emits["numeric_string"]
            broken = [
                (kind, entry)
                for kind, entry in (("number", number), ("numeric string", text))
                if entry is None or not entry.get("ok")
            ]
            if broken:
                for kind, entry in broken:
                    result.errors.append(
                        Finding(
                            probe.component, probe.attribute, probe.platform, "probe",
                            probe.host,
                            f"converter raised on the {kind} emit "
                            f"({probe.numeric!r}): {(entry or {}).get('error', 'missing')}",
                        )
                    )
            else:
                result.checks_run += 1
                result.per_check["C3"] += 1
                if number["output"] != text["output"]:
                    result.findings.append(
                        Finding(
                            probe.component, probe.attribute, probe.platform, "C3",
                            probe.host,
                            f"{probe.numeric!r} and "
                            f"{_as_numeric_string(probe.numeric)!r} emit different "
                            f"text — the two spellings of one value take "
                            f"different paths (plan 43)",
                            finding_class="numeric-string-divergence",
                            primary=probe.numeric,
                            secondary=_as_numeric_string(probe.numeric),
                            evidence={
                                "number": _clip(number["output"]),
                                "numericString": _clip(text["output"]),
                            },
                        )
                    )

        # --- C1: does the BOUND form survive? ---------------------------- #
        if not probe.bindable:
            result.not_applicable.setdefault("C1", {}).setdefault(
                "the SSoT declares no `@{...}` form for this attribute", []
            ).append(f"{probe.key} [{probe.platform}]")
            continue

        entry = emits["bound"]
        if entry is None or not entry.get("ok"):
            result.errors.append(
                Finding(
                    probe.component, probe.attribute, probe.platform, "probe", probe.host,
                    f"converter raised on the bound emit: "
                    f"{(entry or {}).get('error', 'missing')}",
                )
            )
            continue

        bound = entry["output"]
        result.checks_run += 1
        result.per_check["C1"] += 1
        if bound == control:
            result.findings.append(
                Finding(
                    probe.component, probe.attribute, probe.platform, "C1", probe.host,
                    "the bound form emits exactly the control — the binding is "
                    "dropped without a class, a style or a warning (plan 36)",
                    finding_class="bound-dropped",
                    evidence={"control": _clip(control), "bound": _clip(bound)},
                )
            )
        elif _RAW_BINDING.search(bound):
            # The `@{...}` text is sitting in the generated source. Checked
            # BEFORE the name test because the probe variable IS named inside
            # the leaked expression: `.border(@{juiProbeValue}.dp, …)` contains
            # `juiProbeValue` and would otherwise read as a PASS. That is what
            # it did read as until 2026-08-04 — 85 C1 judgements were passing
            # on a leak.
            literal = _leak_is_literal(bound)
            result.findings.append(
                Finding(
                    probe.component, probe.attribute, probe.platform, "C1", probe.host,
                    (
                        "the `@{...}` expression reached the generated source "
                        "inside a STRING literal — this compiles, and then puts "
                        "the characters `@{...}` on screen (or into a dead "
                        "class name) instead of the bound value"
                        if literal else
                        "the `@{...}` expression reached the generated source "
                        "in CODE position — the emit is not a wrong program, it "
                        "is not a program, and the build dies on it"
                    ),
                    finding_class=(
                        "bound-literal-leak" if literal else "bound-uncompilable"
                    ),
                    evidence={
                        "control": _clip(control),
                        "bound": _clip(bound),
                        "leak": _leak_context(bound),
                    },
                )
            )
        elif BINDING_VAR not in bound:
            # The static and bound spellings are SUPPOSED to differ at this
            # stage (`h-[100px]` vs a style expression), so "differs from the
            # control" alone is not enough: the output has to actually name
            # the bound property, or something else moved and the value did
            # not travel. The picture-level equivalence is the render stage's
            # judgement, not this one's.
            result.findings.append(
                Finding(
                    probe.component, probe.attribute, probe.platform, "C1", probe.host,
                    f"the bound emit differs from the control but never names "
                    f"`{BINDING_VAR}` — the binding was evaluated as a value "
                    f"and frozen into the output as a constant",
                    finding_class="bound-frozen",
                    evidence={"control": _clip(control), "bound": _clip(bound)},
                )
            )

    return result


def check(
    definitions: dict,
    repo_root,
    platforms=PLATFORMS,
    ruby: str = "ruby",
    companion_specs: dict | None = None,
) -> EffectResult:
    """Build the job table, run the three probes, and judge the outputs."""
    table = build_jobs(definitions, platforms=platforms, companion_specs=companion_specs)
    outputs = {}
    for platform in platforms:
        outputs[platform] = run_probe(repo_root, platform, table.jobs[platform], ruby=ruby)
    return evaluate(table, outputs)


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def render_report(result: EffectResult, table: JobTable, platforms=PLATFORMS) -> dict:
    """The queue as JSON. A report, not a ledger — see plan 41 Phase 1/2."""
    per_platform: dict = {}
    per_check: dict = {}
    per_class: dict = {}
    for finding in result.defects:
        per_platform[finding.platform] = per_platform.get(finding.platform, 0) + 1
        per_check[finding.check] = per_check.get(finding.check, 0) + 1
        per_class[finding.finding_class] = per_class.get(finding.finding_class, 0) + 1

    def entry(f, with_evidence=True):
        return {
            "check": f.check,
            "class": f.finding_class,
            "component": f.component,
            "attribute": f.attribute,
            "platform": f.platform,
            "host": f.host,
            "detail": f.detail,
            **({"primary": f.primary} if f.primary is not None else {}),
            **({"secondary": f.secondary} if f.secondary is not None else {}),
            **({"evidence": f.evidence} if with_evidence else {}),
        }

    def ordered(findings):
        return sorted(
            findings, key=lambda f: (f.check, f.component, f.attribute, f.platform)
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "_comment": (
            "Codegen-stage differential (plan 41). For every declared "
            "(component, attribute, platform), the production converter is "
            "called four times with a layout hash and the emitted TEXT is "
            "compared: C0 attr-vs-control (is the spelling read), C1 "
            "bound-vs-control (does the `@{...}` form survive), C2 v1-vs-v2 "
            "(is the value read or is a constant emitted). No device, no "
            "threshold, no fixture. It proves the converter emits the "
            "attribute — NOT that the library then honours it; that split is "
            "the point, and the remainder belongs to the render stage. "
            "Generated by `jui conformance codegen-effect --json`."
        ),
        "platforms": list(platforms),
        "probeModes": {p: PROBE_MODES[p] for p in platforms},
        # Which attributes were probed WITH companions, and the ledger
        # statement each companion set was derived from. A paired verdict is
        # only as trustworthy as its pairing, so the derivation ships with it.
        "paired": [
            {
                "component": spec.component,
                "attribute": spec.attribute,
                "companions": spec.companions,
                "kind": spec.kind,
                "source": spec.source,
                **({"provisional": True, "reason": spec.reason} if spec.provisional else {}),
            }
            for spec in sorted(table.paired.values(), key=lambda s: s.key)
        ],
        "counts": {
            "probes": result.probes,
            "checksRun": result.checks_run,
            "perCheckRun": result.per_check,
            "findings": len(result.defects),
            "perCheck": per_check,
            "perClass": per_class,
            "perPlatform": per_platform,
            "representativeValueCandidates": len(result.advised("value-is-default")),
            "numericStringDivergences": len(
                result.advised("numeric-string-divergence")
            ),
            "probeErrors": len(result.errors),
            "outOfScope": len(result.out_of_scope),
        },
        "findings": [entry(f) for f in ordered(result.defects)],
        # Not defects and never ledgered: the converter reads the attribute
        # (C2 proves it) and the representative value happens to emit what the
        # control emits, so the FIXTURE discriminates nothing. Give
        # `rules.representative_value()` a different value and it does again.
        # Re-derived every run, which is exactly why it must not be recorded:
        # a stored entry would go stale the moment the value changed and a
        # two-way ratchet would misfire on it.
        "representativeValueCandidates": [
            entry(f, with_evidence=False)
            for f in ordered(result.advised("value-is-default"))
        ],
        # Also advisory, for a different reason: a numeric string is not a
        # number, every platform's validator warns on it, and `jui build` at
        # zero warnings keeps it out of a build (2026-08-04 ruling). Kept in
        # the report because the lane's crash side is a real gate — a
        # converter that RAISES aborts before the warning prints.
        "numericStringDivergences": [
            entry(f, with_evidence=False)
            for f in ordered(result.advised("numeric-string-divergence"))
        ],
        "probeErrors": [
            {
                "component": f.component,
                "attribute": f.attribute,
                "platform": f.platform,
                "host": f.host,
                "detail": f.detail,
            }
            for f in sorted(
                result.errors, key=lambda f: (f.component, f.attribute, f.platform)
            )
        ],
        "notApplicable": {
            check: {reason: sorted(items) for reason, items in reasons.items()}
            for check, reasons in sorted(result.not_applicable.items())
        },
        "outOfScope": [
            {
                "component": e.component,
                "attribute": e.attribute,
                "reason": e.scope_reason,
                "detail": e.detail,
            }
            for e in sorted(
                result.out_of_scope, key=lambda e: (e.component, e.attribute)
            )
        ],
    }


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #

#: Ledger schema version; bump when the entry shape changes.
LEDGER_SCHEMA_VERSION = 1

LEDGER_NAME = "codegen_effect.json"

#: Reason recorded by ``--update`` for defects nobody has reviewed yet. The
#: gate accepts it (it IS recorded) while the string keeps the backlog
#: grep-able — same convention as the parity ledger.
UNREVIEWED = "unreviewed-initial-measurement"

#: Fields every entry must carry. An accepted defect with no owner is how a
#: temporary exception becomes permanent: plan 50 measured that the
#: attribution column is the only thing that stops a frozen row from
#: outliving the reason it was frozen for.
REQUIRED_FIELDS = ("owner", "reason")


def ledger_path(conformance_dir) -> Path:
    return Path(conformance_dir) / LEDGER_NAME


def entry_key(finding: "Finding") -> tuple:
    """What makes two measurements the same defect.

    Deliberately NOT the finding class: a `bound-dropped` that becomes a
    `bound-frozen` is the same attribute still broken on the same platform,
    and rekeying it would drop the recorded reason on the floor. The class
    travels in the entry so a change is visible, not silent.
    """
    return (finding.component, finding.attribute, finding.platform, finding.check)


def load_ledger(path) -> dict:
    """``{(component, attribute, platform, check): entry}``."""
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict = {}
    for entry in raw.get("entries", []):
        key = (
            entry.get("component"),
            entry.get("attribute"),
            entry.get("platform"),
            entry.get("check"),
        )
        if all(key):
            out[key] = entry
    return out


def render_ledger(entries: dict) -> str:
    """Deterministic ledger JSON."""
    doc = {
        "schemaVersion": LEDGER_SCHEMA_VERSION,
        "_comment": (
            "Accepted codegen-differential defects, per (component, attribute, "
            "platform, check). An entry means the converter demonstrably fails "
            "that judgement and the failure is accepted FOR A STATED REASON — "
            "not that it is fine. Unrecorded defects fail `jui conformance gate "
            "--codegen-effect`; entries the measurement no longer supports are "
            "stale and fail too, so fixing a defect forces its row out (the "
            "one-directional version lets a fixed row sit here forever, which "
            "is how the previous freeze ledgers rotted). Advisory classes "
            "(value-is-default, numeric-string-divergence) are re-derived every "
            "run and are deliberately absent. Reason '" + UNREVIEWED + "' marks "
            "the initial-measurement backlog — consume it."
        ),
        "entries": [
            entries[key] for key in sorted(entries, key=lambda k: (k[2], k[0], k[1], k[3]))
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def update_ledger(existing: dict, result: EffectResult, platforms=PLATFORMS) -> dict:
    """Fold a measurement into the ledger.

    Only the measured platforms are rewritten: an ios run says nothing about
    android, and dropping android's rows because they were not measured would
    quietly widen what the gate accepts.
    """
    measured = set(platforms)
    merged = {key: entry for key, entry in existing.items() if key[2] not in measured}
    for finding in result.defects:
        key = entry_key(finding)
        prior = existing.get(key, {})
        merged[key] = {
            "component": finding.component,
            "attribute": finding.attribute,
            "platform": finding.platform,
            "check": finding.check,
            "class": finding.finding_class,
            "owner": prior.get("owner", UNREVIEWED),
            "reason": prior.get("reason", UNREVIEWED),
            "note": prior.get("note", ""),
        }
    return merged


@dataclass
class EffectCheck:
    """Pure ledger-vs-measurement verdict (consumed by the gate)."""

    unrecorded: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    incomplete: list = field(default_factory=list)  # entries missing owner/reason
    accepted: int = 0
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.unrecorded or self.stale or self.incomplete or self.errors)


def check_ledger(result: EffectResult, ledger: dict, platforms=PLATFORMS) -> EffectCheck:
    """Judge one measurement against the ledger. Pure.

    Probe errors are their own bucket and always fail: a converter that
    raised emitted nothing, so every judgement about it is vacuous — the
    ledger cannot accept a defect that was never measured.
    """
    verdict = EffectCheck(errors=[str(f) for f in result.errors])
    measured = {entry_key(f) for f in result.defects}

    for finding in result.defects:
        key = entry_key(finding)
        entry = ledger.get(key)
        if entry is None:
            verdict.unrecorded.append(str(finding))
            continue
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            verdict.incomplete.append(
                f"{finding.key} [{finding.platform}] {finding.check} — "
                f"missing {', '.join(missing)}"
            )
        else:
            verdict.accepted += 1

    for key in sorted(ledger):
        if key[2] not in set(platforms):
            continue  # not measured this run; says nothing either way
        if key not in measured:
            component, attribute, platform, check = key
            verdict.stale.append(f"{component}.{attribute} [{platform}] {check}")

    return verdict
