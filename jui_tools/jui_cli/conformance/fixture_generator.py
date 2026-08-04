"""Generate conformance fixtures (layout + screen test + manifest).

Input: ``shared/core/attribute_definitions.json`` (attribute SSoT).
Output layout (all under the top-level ``conformance/`` directory):

```
conformance/
├── fixtures/<Section>/<attr>__<case>.layout.json   # @generated
├── fixtures/<Section>/<attr>__<case>.test.json     # @generated
├── manifest.json                                   # @generated
└── results/                                        # written by platform runners
```

Hard requirements (plan §7):

- Deterministic: no timestamps / randomness; two runs produce zero diff.
- No silent drops: every attribute is either a fixture or a ``skipped``
  manifest entry with a reason.
- Generated test JSON conforms to the jsonui-test-runner screen-test schema.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.generated_marker import json_marker
from . import interactive_rules, rules
from .interactive_rules import InteractivePlan, InteractiveSpec
from .rules import AttributePlan, CasePlan, SkippedAttribute

GENERATOR_NAME = "jui conformance generate"

#: Sentinel string embedded in test JSON metadata (``metadata.generatedBy`` is
#: a schema-legal field, so the marker survives ``jsonui-test validate`` with
#: zero warnings while staying greppable via ``@generated``).
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

MANIFEST_SCHEMA_VERSION = 2

#: Anchor sibling emitted for view-reference attributes.
#:
#: The margins are load-bearing. With the anchor at the origin, `alignTopView`
#: and `alignLeftView` asked the target to move to the corner it was already
#: in — the root stacks its children at top-start — so the two fixtures were
#: permanently inert and indistinguishable from a dropped attribute. Offsetting
#: the anchor gives every edge, not just bottom and right, somewhere to travel
#: from. The control carries the same anchor, so the comparison is unaffected
#: for the view-ref attributes that already worked.
ANCHOR_NODE: dict[str, Any] = {
    "type": "View",
    "id": rules.ANCHOR_ID,
    "width": 50,
    "height": 50,
    "background": "#CCCCCC",
    "topMargin": 60,
    "leftMargin": 60,
}


@dataclass
class GenerationSummary:
    """What one ``jui conformance generate`` run produced."""

    out_dir: Path
    manifest_path: Path
    fixture_count: int = 0
    assertable_count: int = 0
    visual_count: int = 0
    interactive_count: int = 0
    #: control fixtures (base attributes only) each visual fixture is diffed against
    control_count: int = 0
    skipped_count: int = 0
    files_written: int = 0
    skipped: list[dict] = field(default_factory=list)
    promoted: dict = field(default_factory=dict)  # skip reason -> promoted attr count


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


def plan_definitions(
    definitions: dict,
) -> tuple[list[AttributePlan | InteractivePlan], list[SkippedAttribute]]:
    """Classify every attribute of every section, in definition-file order.

    v2: attributes with an interactive rule are additionally planned as
    ``interactive`` fixtures. When the static classification skipped the
    attribute as ``callback`` / ``binding-only``, the interactive plan
    *promotes* it out of the skip list (``promoted_from`` records the reason).
    """
    plans: list[AttributePlan | InteractivePlan] = []
    skipped: list[SkippedAttribute] = []
    for section, attrs in definitions.items():
        if section == "_comment" or not isinstance(attrs, dict):
            continue
        if isinstance(attrs.get("_alias_of"), str):
            # Component alias (`_alias_of` pointer section, B1): carries no
            # attribute copies, so there is nothing to fixture — the
            # canonical section owns the coverage. One ledger entry keeps
            # the no-silent-drops contract.
            skipped.append(
                SkippedAttribute(section, "*", rules.REASON_COMPONENT_ALIAS)
            )
            continue
        for attribute, defn in attrs.items():
            result = rules.plan_attribute(section, attribute, defn)
            if isinstance(result, SkippedAttribute):
                promotable = result.reason in interactive_rules.PROMOTABLE_REASONS
                interactive = (
                    interactive_rules.plan_interactive(
                        section, attribute, defn, promoted_from=result.reason
                    )
                    if promotable and isinstance(defn, dict)
                    else None
                )
                if interactive is not None:
                    plans.append(interactive)
                else:
                    skipped.append(result)
            else:
                plans.append(result)
                interactive = interactive_rules.plan_interactive(
                    section, attribute, defn, promoted_from=None
                )
                if interactive is not None:
                    plans.append(interactive)
    return plans, skipped


# --------------------------------------------------------------------------- #
# Layout / test JSON builders
# --------------------------------------------------------------------------- #


def build_layout(plan: AttributePlan, case: CasePlan, *, source_label: str) -> dict:
    """One minimal layout: root View + (anchor?) + target component."""
    extra = rules.base_attrs_for(plan.host, plan.attribute)
    base = dict(rules.BASE_ATTRS.get(plan.host, {}))
    rules.apply_base_overrides(base, extra)

    target: dict[str, Any] = {"type": plan.host, "id": rules.TARGET_ID}
    target["width"] = base.get("width", "wrapContent")
    target["height"] = base.get("height", "wrapContent")
    for key, value in base.items():
        if key in ("width", "height"):
            continue
        target[key] = value

    children = rules.BASE_CHILDREN.get(plan.host)
    if children:
        target["child"] = [dict(c) for c in children]

    # The attribute under test always wins over base attributes.
    target[case.written_key] = case.value

    root_children: list[dict] = []
    if plan.needs_anchor:
        root_children.append(dict(ANCHOR_NODE))
    root_children.append(target)

    layout: dict[str, Any] = {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        **rules.split_root_attrs(extra),
        "child": root_children,
    }
    _attach_data(layout, plan.host, base)
    return layout


def _attach_data(layout: dict, host: str, base: dict) -> None:
    """Write the layout's ``data`` section: host defaults + binding companions.

    Both are load-bearing for the codegen paths, which derive the generated
    Data type from this section alone.
    """
    entries = [dict(e) for e in (rules.BASE_DATA.get(host) or [])]
    entries.extend(
        rules.binding_data_entries(base, {e["name"] for e in entries})
    )
    if entries:
        layout["data"] = entries


def build_test(plan: AttributePlan, case: CasePlan, layout_rel: str) -> dict:
    """One screen-test JSON referencing *layout_rel* (conformance-root relative)."""
    case_id = f"{plan.attribute}__{case.name}"
    steps: list[dict] = [{"action": "waitFor", "id": "root"}]
    if plan.cls == rules.CLASS_ASSERTABLE:
        steps.extend(dict(a) for a in case.assertions)
    else:
        steps.append(
            {"action": "screenshot", "name": f"{plan.section}_{case_id}"}
        )

    platform: Any
    if plan.platforms == rules.ALL_PLATFORMS:
        platform = "all"
    else:
        platform = list(plan.platforms)

    description = (
        f"Conformance fixture for '{plan.attribute}' on {plan.host} "
        f"(section: {plan.section}, class: {plan.cls}). "
        f"Value under test: {json.dumps(case.value, ensure_ascii=False)}."
    )

    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {plan.section}.{plan.attribute} ({case.name})",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", plan.section],
        },
        "platform": platform,
        "cases": [
            {
                "name": case_id,
                "description": description,
                "steps": steps,
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Interactive layout / test JSON builders (v2)
# --------------------------------------------------------------------------- #


def _data_entry(name: str, cls: str, default: Any) -> dict:
    """One ``data``-section entry; ``NO_DEFAULT`` omits ``defaultValue``."""
    entry = {"name": name, "class": cls}
    if default is not interactive_rules.NO_DEFAULT:
        entry["defaultValue"] = default
    return entry


def build_interactive_layout(
    plan: InteractivePlan, spec: InteractiveSpec, *, source_label: str
) -> dict:
    """Root View + standard ``data`` section + target (+ mirror Label).

    The ``data`` section is the cross-runtime initial-value mechanism. It
    DECLARES the handlers too (name + closure type, no defaultValue) because
    the codegens derive the Data type from it; the closure VALUES are still
    injected by the host per the manifest ``state.handlers`` contract
    (INTERACTIVE_HOST_CONTRACT.md).
    """
    base = rules.BASE_ATTRS.get(spec.host, {})

    target: dict[str, Any] = {"type": spec.host, "id": rules.TARGET_ID}
    target["width"] = base.get("width", "wrapContent")
    target["height"] = base.get("height", "wrapContent")
    for key, value in base.items():
        if key in ("width", "height"):
            continue
        target[key] = value
    for key, value in spec.target_attrs:
        target[key] = value

    children: list[dict] = [target]
    if spec.mirror_var is not None:
        children.append(
            {
                "type": "Label",
                "id": interactive_rules.MIRROR_ID,
                "text": f"@{{{spec.mirror_var}}}",
            }
        )

    return {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        # A View without orientation overlays its children on every platform
        # (frame semantics) — the mirror Label would intercept taps on the
        # target. Interactive fixtures therefore stack vertically.
        "orientation": "vertical",
        # State vars (String-typed host contract surface, mirrored in the
        # manifest `state.vars`) first, then layout-only DataVar seeds
        # (native JSON defaults for binding-resolution fixtures; NOT part of
        # the manifest state contract — they ride each runtime's production
        # data-section defaults path), then the handlers.
        #
        # A handler is a data property too: the layout writes `@{name}` (or a
        # bare selector) and every codegen emits `data.<name>`, so the Data
        # type needs the declaration. The host injects the closure at runtime
        # through `state.handlers`; the declaration carries no defaultValue.
        "data": [
            {"name": v.name, "class": v.cls, "defaultValue": v.default} for v in spec.vars
        ]
        + [_data_entry(v.name, v.cls, v.default) for v in spec.data_vars]
        + [{"name": h.name, "class": h.cls} for h in spec.handlers],
        "child": children,
    }


def build_interactive_test(plan: InteractivePlan, spec: InteractiveSpec, layout_rel: str) -> dict:
    """Screen-test JSON for one interactive fixture (schema-native steps)."""
    case_id = f"{plan.attribute}__{spec.case}"
    steps: list[dict] = [{"action": "waitFor", "id": "root"}]
    steps.extend(dict(s) for s in spec.steps)

    platform: Any
    if plan.platforms == rules.ALL_PLATFORMS:
        platform = "all"
    else:
        platform = list(plan.platforms)

    description = (
        f"Interactive conformance fixture for '{plan.attribute}' on {spec.host} "
        f"(section: {plan.section}, case: {spec.case}). "
        "State contract: see manifest state / INTERACTIVE_HOST_CONTRACT.md."
    )

    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance {plan.section}.{plan.attribute} ({spec.case})",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "interactive", plan.section],
        },
        "platform": platform,
        "cases": [
            {
                "name": case_id,
                "description": description,
                "steps": steps,
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


def build_manifest_entry(
    plan: AttributePlan, case: CasePlan, layout_rel: str, test_rel: str
) -> dict:
    entry = {
        "id": f"{plan.section}/{plan.attribute}__{case.name}",
        "component": plan.section,
        "attribute": plan.attribute,
        "case": case.name,
        "class": plan.cls,
        "host": plan.host,
        "writtenKey": case.written_key,
        "aliasOf": case.alias_of,
        "value": case.value,
        "platforms": list(plan.platforms),
        "mode": plan.mode,
        "deprecated": plan.deprecated,
        "layout": layout_rel,
        "test": test_rel,
        "state": None,
        "promotedFrom": None,
        # The fixture this one must NOT look like. Visual fixtures only:
        # an assertable fixture already states its expectation, and an
        # off-screen effect (soft-keyboard configuration) cannot be compared.
        "control": (
            control_id(
                plan.host, plan.needs_anchor, control_shape(plan.host, plan.attribute)
            )
            if plan.cls == rules.CLASS_VISUAL
            and plan.attribute not in rules.NON_OBSERVABLE_ATTRS
            else None
        ),
    }
    companions = rules.BASE_COMPANIONS.get(plan.host)
    if companions:
        entry["companions"] = list(companions)
    return entry


# --------------------------------------------------------------------------- #
# Control fixtures
# --------------------------------------------------------------------------- #
#
# A visual fixture is compared against its own previous screenshot, so an
# attribute the platform silently drops renders the default, matches the
# default it recorded last time, and passes forever. That is how Button.image
# and View.flexWrap stayed broken with every gate green.
#
# The control closes it from the other side: the SAME layout with the
# attribute under test removed. If the fixture and its control render
# identically, nothing the attribute asked for happened. No baseline and no
# cross-platform comparison is involved — the two images come from the same
# run on the same device.
#
# One control serves every fixture that shares its shape. `build_layout`
# derives everything from `host` plus `needs_anchor`, so ~60 controls cover
# all 600 visual fixtures instead of doubling the suite.


def control_id(host: str, needs_anchor: bool, shape: str = "") -> str:
    """Identity of the control a fixture is compared against.

    `shape` distinguishes controls that carry different extra base attributes.
    A fixture whose base was widened (`flexWrap` gets an `orientation`) must be
    compared against a control with the SAME widening, or the comparison also
    measures the orientation and every such fixture reads as active for the
    wrong reason.
    """
    suffix = f"__{shape}" if shape else ""
    return f"__control/{host}{'__anchored' if needs_anchor else ''}{suffix}"


#: Anything outside this set is folded to `-` so a base-attribute value never
#: decides whether the control fixture's filename is shell- or path-safe.
_SHAPE_UNSAFE = re.compile(r"[^A-Za-z0-9.-]+")


#: Longest a single key-value part may render before it is replaced by a
#: digest. The shape name becomes a FILENAME (and, through it, a screenshot
#: name and a test id), so a base value like a paragraph of wrapping text
#: would otherwise produce a 100+ character path component.
_SHAPE_PART_MAX = 28


def _shape_part(key: str, value) -> str:
    """One `key-value` fragment, sanitised and length-bounded."""
    if value is None:
        # `None` REMOVES the base key (see rules.apply_base_overrides), and
        # "text-None" reads as "text set to the string None" — say what it is.
        return _SHAPE_UNSAFE.sub("-", f"no-{key}").strip("-")
    part = _SHAPE_UNSAFE.sub("-", f"{key}-{value}").strip("-")
    if len(part) <= _SHAPE_PART_MAX:
        return part
    digest = hashlib.sha1(f"{key}={value!r}".encode("utf-8")).hexdigest()[:8]
    return f"{_SHAPE_UNSAFE.sub('-', key).strip('-')}-{digest}"


def shape_name(extra: dict | None) -> str:
    """Stable name for a set of extra base attributes."""
    if not extra:
        return ""
    return "_".join(_shape_part(k, v) for k, v in sorted(extra.items()))


def control_shape(host: str, attribute: str) -> str:
    """Stable name for the extra-base variant an attribute's fixture uses."""
    return shape_name(rules.base_attrs_for(host, attribute))


def build_control_layout(
    host: str, needs_anchor: bool, extra: dict | None = None, *, source_label: str
) -> dict:
    """The target component with its base attributes and nothing else."""
    base = dict(rules.BASE_ATTRS.get(host, {}))
    rules.apply_base_overrides(base, extra)

    target: dict[str, Any] = {"type": host, "id": rules.TARGET_ID}
    target["width"] = base.get("width", "wrapContent")
    target["height"] = base.get("height", "wrapContent")
    for key, value in base.items():
        if key not in ("width", "height"):
            target[key] = value

    children = rules.BASE_CHILDREN.get(host)
    if children:
        target["child"] = [dict(c) for c in children]

    root_children: list[dict] = []
    if needs_anchor:
        root_children.append(dict(ANCHOR_NODE))
    root_children.append(target)

    layout: dict[str, Any] = {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        **rules.split_root_attrs(extra),
        "child": root_children,
    }
    _attach_data(layout, host, base)
    return layout


def build_control_test(
    host: str, needs_anchor: bool, layout_rel: str, shape: str = ""
) -> dict:
    cid = control_id(host, needs_anchor, shape)
    name = cid.split("/", 1)[1]
    description = (
        f"Control for {host}: base attributes only, no attribute under test. "
        "Every visual fixture on this host must render differently from it — "
        "an identical render means the attribute was dropped."
    )
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance control {host}",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "control"],
        },
        "platform": "all",
        "cases": [
            {
                "name": name,
                "description": description,
                "steps": [
                    {"action": "waitFor", "id": "root"},
                    {"action": "screenshot", "name": f"control_{name}"},
                ],
            }
        ],
    }


def build_control_manifest_entry(
    host: str, needs_anchor: bool, layout_rel: str, test_rel: str, shape: str = "",
    platforms: set | None = None,
) -> dict:
    # Canonical platform ordering, restricted to the consumers' union.
    platform_list = (
        [p for p in rules.ALL_PLATFORMS if p in platforms]
        if platforms else list(rules.ALL_PLATFORMS)
    )
    entry = {
        "id": control_id(host, needs_anchor, shape),
        "component": "__control",
        "attribute": None,
        "case": host,
        "class": rules.CLASS_VISUAL,
        "host": host,
        "writtenKey": None,
        "aliasOf": None,
        "value": None,
        "platforms": platform_list,
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": test_rel,
        "state": None,
        "promotedFrom": None,
        "control": None,
        "isControl": True,
    }
    companions = rules.BASE_COMPANIONS.get(host)
    if companions:
        entry["companions"] = list(companions)
    return entry


def build_interactive_manifest_entry(
    plan: InteractivePlan, spec: InteractiveSpec, layout_rel: str, test_rel: str
) -> dict:
    written_key, written_value = spec.target_attrs[0]
    return {
        "id": f"{plan.section}/{plan.attribute}__{spec.case}",
        "component": plan.section,
        "attribute": plan.attribute,
        "case": spec.case,
        "class": interactive_rules.CLASS_INTERACTIVE,
        "host": spec.host,
        "writtenKey": written_key,
        "aliasOf": None,
        "value": written_value,
        "platforms": list(plan.platforms),
        "mode": plan.mode,
        "deprecated": plan.deprecated,
        "layout": layout_rel,
        "test": test_rel,
        "state": interactive_rules.state_payload(spec),
        "promotedFrom": plan.promoted_from,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _source_label(definitions_path: Path) -> str:
    """Stable, machine-independent label for the definitions file."""
    parts = definitions_path.resolve().parts
    if len(parts) >= 3 and parts[-3:-1] == ("shared", "core"):
        return "shared/core/attribute_definitions.json"
    return definitions_path.name


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def generate_conformance(definitions_path: Path, out_dir: Path) -> GenerationSummary:
    """Generate fixtures + manifest under *out_dir*. Deterministic + idempotent.

    The ``fixtures/`` subtree and ``manifest.json`` are regenerated from
    scratch (stale fixtures cannot survive); ``results/`` and hand-written
    docs are left untouched.
    """
    definitions_path = Path(definitions_path)
    out_dir = Path(out_dir)
    definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
    source_label = _source_label(definitions_path)

    plans, skipped = plan_definitions(definitions)

    fixtures_dir = out_dir / "fixtures"
    if fixtures_dir.exists():
        shutil.rmtree(fixtures_dir)
    fixtures_dir.mkdir(parents=True)

    results_dir = out_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = results_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")

    summary = GenerationSummary(out_dir=out_dir, manifest_path=out_dir / "manifest.json")
    fixture_entries: list[dict] = []

    promoted: dict[str, int] = {}
    # (host, needs_anchor, shape) shapes that need a control fixture, mapped
    # to the union of their consumers' platforms — a control consumed only by
    # a platform-restricted fixture must not run anywhere else (an ios-only
    # SF-Symbol src broke the android codegen host as R.drawable.star).
    needed_controls: dict[tuple, set] = {}
    # macOS filesystems are case-insensitive; attribute names differing only
    # by case (onclick / onClick) must not share a fixture file path. The
    # suffix assignment follows definition order — fully deterministic.
    used_stems: dict[str, int] = {}

    def _unique_stem(section: str, stem: str) -> str:
        key = f"{section}/{stem}".lower()
        count = used_stems.get(key, 0) + 1
        used_stems[key] = count
        return stem if count == 1 else f"{stem}_{count}"

    for plan in plans:
        section_dir = fixtures_dir / plan.section
        section_dir.mkdir(exist_ok=True)
        if isinstance(plan, InteractivePlan):
            if plan.promoted_from is not None:
                promoted[plan.promoted_from] = promoted.get(plan.promoted_from, 0) + 1
            for spec in plan.specs:
                stem = _unique_stem(plan.section, f"{plan.attribute}__{spec.case}")
                layout_rel = f"fixtures/{plan.section}/{stem}.layout.json"
                test_rel = f"fixtures/{plan.section}/{stem}.test.json"

                layout = build_interactive_layout(plan, spec, source_label=source_label)
                test = build_interactive_test(plan, spec, layout_rel)

                (out_dir / layout_rel).write_text(_dump_json(layout), encoding="utf-8")
                (out_dir / test_rel).write_text(_dump_json(test), encoding="utf-8")
                summary.files_written += 2

                fixture_entries.append(
                    build_interactive_manifest_entry(plan, spec, layout_rel, test_rel)
                )
                summary.fixture_count += 1
                summary.interactive_count += 1
            continue
        for case in plan.cases:
            stem = _unique_stem(plan.section, f"{plan.attribute}__{case.name}")
            layout_rel = f"fixtures/{plan.section}/{stem}.layout.json"
            test_rel = f"fixtures/{plan.section}/{stem}.test.json"

            layout = build_layout(plan, case, source_label=source_label)
            test = build_test(plan, case, layout_rel)

            (out_dir / layout_rel).write_text(_dump_json(layout), encoding="utf-8")
            (out_dir / test_rel).write_text(_dump_json(test), encoding="utf-8")
            summary.files_written += 2

            fixture_entries.append(build_manifest_entry(plan, case, layout_rel, test_rel))
            summary.fixture_count += 1
            if plan.cls == rules.CLASS_ASSERTABLE:
                summary.assertable_count += 1
            else:
                summary.visual_count += 1
                if plan.attribute not in rules.NON_OBSERVABLE_ATTRS:
                    control_key = (plan.host, plan.needs_anchor, control_shape(plan.host, plan.attribute))
                    needed_controls.setdefault(control_key, set()).update(plan.platforms)

    # One control per shape the visual fixtures actually used. Generated after
    # the sweep so an unused host does not get a control nobody compares to.
    control_dir = fixtures_dir / "__control"
    # Keyed by shape, not by attribute: a shape is defined by its extras, and
    # the same extras may be reached from a scoped or an unscoped key.
    shape_extras = {
        shape_name(e): e for e in rules.BASE_ATTRS_BY_ATTRIBUTE.values()
    }
    for host, needs_anchor, shape in sorted(needed_controls.keys()):
        control_platforms = needed_controls[(host, needs_anchor, shape)]
        control_dir.mkdir(exist_ok=True)
        stem = control_id(host, needs_anchor, shape).split("/", 1)[1]
        layout_rel = f"fixtures/__control/{stem}.layout.json"
        test_rel = f"fixtures/__control/{stem}.test.json"

        extra = shape_extras.get(shape, {})
        layout = build_control_layout(
            host, needs_anchor, extra, source_label=source_label
        )
        test = build_control_test(host, needs_anchor, layout_rel, shape)

        (out_dir / layout_rel).write_text(_dump_json(layout), encoding="utf-8")
        (out_dir / test_rel).write_text(_dump_json(test), encoding="utf-8")
        summary.files_written += 2

        fixture_entries.append(
            build_control_manifest_entry(
                host, needs_anchor, layout_rel, test_rel, shape,
                platforms=control_platforms,
            )
        )
        summary.fixture_count += 1
        summary.control_count += 1

    # Companion support layouts declared by rules.SUPPORT_LAYOUTS (today: the
    # shared Collection cell). Written once; every manifest entry whose host
    # lists them in rules.BASE_COMPANIONS references them by this path.
    for rel_path, payload in rules.SUPPORT_LAYOUTS.items():
        target = out_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        support_layout = {
            "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
            **payload,
        }
        target.write_text(_dump_json(support_layout), encoding="utf-8")
        summary.files_written += 1

    # Bespoke Embed semantic fixtures (cross-file: companion embedded-screen
    # layouts under fixtures/Embed/__screens/). The generic per-attribute
    # sweep for Embed stays skipped — see embed_fixtures module docstring.
    from .embed_fixtures import build_embed_fixtures

    embed_files, embed_entries = build_embed_fixtures(source_label)
    for rel_path, payload in embed_files:
        target = out_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump_json(payload), encoding="utf-8")
        summary.files_written += 1
    fixture_entries.extend(embed_entries)
    summary.fixture_count += len(embed_entries)
    summary.assertable_count += sum(1 for e in embed_entries if e["class"] == "assertable")
    summary.interactive_count += sum(1 for e in embed_entries if e["class"] == "interactive")

    # Bespoke responsive variant-file semantic fixtures (06 track):
    # companion screens shipped with @-suffixed size-class variants under
    # fixtures/common/__screens/ — see variant_fixtures module docstring.
    from .variant_fixtures import build_variant_fixtures

    variant_files, variant_entries = build_variant_fixtures(source_label)
    for rel_path, payload in variant_files:
        target = out_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump_json(payload), encoding="utf-8")
        summary.files_written += 1
    fixture_entries.extend(variant_entries)
    summary.fixture_count += len(variant_entries)
    summary.assertable_count += sum(1 for e in variant_entries if e["class"] == "assertable")
    summary.interactive_count += sum(1 for e in variant_entries if e["class"] == "interactive")

    # Bespoke maxBounds clamp-fill fixtures (33 track): matchParent + a max
    # bound must clamp to min(parent, bound) — see bounds_fixtures module
    # docstring. Composite (two attributes), so outside the generic sweep.
    from .bounds_fixtures import build_bounds_fixtures

    bounds_files, bounds_entries = build_bounds_fixtures(source_label)
    for rel_path, payload in bounds_files:
        target = out_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_dump_json(payload), encoding="utf-8")
        summary.files_written += 1
    fixture_entries.extend(bounds_entries)
    summary.fixture_count += len(bounds_entries)
    summary.visual_count += sum(
        1 for e in bounds_entries if e["class"] == "visual" and not e.get("isControl")
    )
    summary.control_count += sum(1 for e in bounds_entries if e.get("isControl"))

    skipped_entries = [
        {"component": s.section, "attribute": s.attribute, "reason": s.reason}
        for s in skipped
    ]
    summary.skipped_count = len(skipped_entries)
    summary.skipped = skipped_entries
    summary.promoted = promoted

    manifest = {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "generatedFrom": _sha256_file(definitions_path),
        "counts": {
            "fixtures": summary.fixture_count,
            "assertable": summary.assertable_count,
            "visual": summary.visual_count,
            "interactive": summary.interactive_count,
            "control": summary.control_count,
            "skipped": summary.skipped_count,
            "promoted": {k: promoted[k] for k in sorted(promoted)},
        },
        "fixtures": fixture_entries,
        "skipped": skipped_entries,
    }
    summary.manifest_path.write_text(_dump_json(manifest), encoding="utf-8")
    summary.files_written += 1

    return summary
