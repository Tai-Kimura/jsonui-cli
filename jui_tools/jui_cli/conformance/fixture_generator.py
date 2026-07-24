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
ANCHOR_NODE: dict[str, Any] = {
    "type": "View",
    "id": rules.ANCHOR_ID,
    "width": 50,
    "height": 50,
    "background": "#CCCCCC",
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
    base = rules.BASE_ATTRS.get(plan.host, {})

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

    return {
        "_generated": json_marker(source=source_label, generator=GENERATOR_NAME),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "child": root_children,
    }


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


def build_interactive_layout(
    plan: InteractivePlan, spec: InteractiveSpec, *, source_label: str
) -> dict:
    """Root View + standard ``data`` section + target (+ mirror Label).

    The ``data`` section is the cross-runtime initial-value mechanism;
    handlers are *not* declared here — they are injected by the host per the
    manifest ``state.handlers`` contract (INTERACTIVE_HOST_CONTRACT.md).
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
        # data-section defaults path).
        "data": [
            {"name": v.name, "class": v.cls, "defaultValue": v.default} for v in spec.vars
        ]
        + [
            {"name": v.name, "class": v.cls, "defaultValue": v.default}
            for v in spec.data_vars
        ],
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
    return {
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
    }


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
            "skipped": summary.skipped_count,
            "promoted": {k: promoted[k] for k in sorted(promoted)},
        },
        "fixtures": fixture_entries,
        "skipped": skipped_entries,
    }
    summary.manifest_path.write_text(_dump_json(manifest), encoding="utf-8")
    summary.files_written += 1

    return summary
