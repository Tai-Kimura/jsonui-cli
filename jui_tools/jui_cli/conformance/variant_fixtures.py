"""Bespoke responsive variant-file conformance fixtures (06 track).

The variant-file mechanism (``home@regular.json``) is cross-file by
construction, so — like Embed — it cannot be exercised by the generic
per-attribute sweep. This module emits a semantic fixture family whose
layouts EMBED a companion screen shipped with size-class variants under
``fixtures/common/__screens/``. Each platform then exercises its real
resolution path: the web host's static build routes through the rjui
media-query dispatch, the mobile hosts route through the Dynamic
loaders' ``<name>@<tier>`` probing.

Lane tiers are fixed (iOS simulator = compact, Android pixel_tablet =
regular, web 1024x768 = regular). Each fixture carries ONE lane's
expectation and targets that lane via manifest ``platforms`` — the
mobile conformance hosts filter at the manifest level but do not apply
per-case ``platform`` gates, so a fixture never mixes lane-specific
cases. The web-only viewport fixtures cover the remaining tiers and the
live tier-switch via ``setViewport``.

Resolution table under test (06a-design.md D1):
- tier X renders ``<base>@X`` when present, else the base
- no cross-tier promotion (``@medium`` never shows on a regular window)
- iOS folds ``@medium`` into its compact tier (no medium size class on
  iOS — mirrors the shipped inline-responsive fold)
- VM/data-owned state survives the whole-tree swap
"""
from __future__ import annotations

from typing import Any

from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_SCREENS_DIR = "fixtures/common/__screens"

HOST_MARKER_ID = "variant-host-marker"
HOST_MARKER_TEXT = "host"
WHICH_ID = "variant-which"
ECHO_ID = "variant-echo"
# snake_case: TextField ids feed the focus-field identifier derivation in
# the web codegen (camelized into TS identifiers — hyphens don't survive)
STATE_INPUT_ID = "variant_state_input"

# Fixed lane tiers (see module docstring). Regular-tier lanes see the
# @regular variant; the compact-tier lane sees @compact / the iOS medium
# fold. Keep in sync with conformance-mobile.yml device choices.
_REGULAR_LANES = ["android", "web"]
_COMPACT_LANES = ["ios"]


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _screen(source_label: str, which_text: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "variant_screen_container",
        "width": "matchParent",
        "height": "wrapContent",
        "orientation": "vertical",
        "child": [
            {"type": "Label", "id": WHICH_ID, "text": which_text},
        ],
    }


def _echo_screen(source_label: str, which_text: str) -> dict:
    """Companion screen for the state fixture: shows which tree rendered
    and echoes the params-driven value (base declares the data contract;
    variants must not carry a ``data`` section)."""
    screen = {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "variant_state_container",
        "width": "matchParent",
        "height": "wrapContent",
        "orientation": "vertical",
        "child": [
            {"type": "Label", "id": WHICH_ID, "text": which_text},
            {"type": "Label", "id": ECHO_ID, "text": "@{fieldValue}"},
        ],
    }
    if which_text == "base":
        screen["data"] = [
            {"name": "fieldValue", "class": "String", "defaultValue": ""}
        ]
    return screen


def _host_layout(
    source_label: str,
    *,
    screen: str,
    params: dict | None = None,
    data: list | None = None,
    extra_children: list[dict] | None = None,
) -> dict:
    embed: dict[str, Any] = {
        "type": "Embed",
        "id": "variant-pane",
        "width": "matchParent",
        "height": "wrapContent",
        "screen": screen,
        "navigationMode": "delegate",
    }
    if params:
        embed["params"] = params
    layout: dict[str, Any] = {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "root",
        "width": "matchParent",
        "height": "matchParent",
        "orientation": "vertical",
    }
    if data:
        layout["data"] = data
    layout["child"] = [
        {"type": "Label", "id": HOST_MARKER_ID, "text": HOST_MARKER_TEXT},
        *(extra_children or []),
        embed,
    ]
    return layout


def _test(
    *,
    attribute: str,
    case: str,
    layout_rel: str,
    cases: list[dict],
) -> dict:
    description = (
        f"Responsive variant-file semantic fixture ({case}). Companion "
        f"screens with @-suffixed variants live under {_SCREENS_DIR}/ — "
        f"see manifest 'companions'."
    )
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance common.{attribute} ({case})",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "variantfile", "common"],
        },
        "platform": "all",
        "cases": cases,
    }


def _case(name: str, steps: list[dict], platform: list[str] | None = None) -> dict:
    case: dict[str, Any] = {
        "name": name,
        "description": f"variant-file: {name}",
        "steps": [{"action": "waitFor", "id": "root"}] + steps,
    }
    if platform is not None:
        case["platform"] = platform
    return case


def _entry(
    *,
    attribute: str,
    case: str,
    value: Any,
    layout_rel: str,
    test_rel: str,
    companions: list[str],
    platforms: list[str],
    state: dict | None = None,
) -> dict:
    return {
        "id": f"common/{attribute}__{case}",
        "component": "common",
        "attribute": attribute,
        "case": case,
        "class": "interactive" if state else "assertable",
        "host": "View",
        "writtenKey": attribute,
        "aliasOf": None,
        "value": value,
        "platforms": platforms,
        "mode": None,
        "deprecated": None,
        "layout": layout_rel,
        "test": test_rel,
        "state": state,
        "promotedFrom": None,
        "companions": companions,
    }


def build_variant_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Return ``(files, manifest_entries)`` — deterministic."""
    files: list[tuple[str, dict]] = [
        (f"{_SCREENS_DIR}/variant_host.layout.json", _screen(source_label, "base")),
        (f"{_SCREENS_DIR}/variant_host@regular.layout.json", _screen(source_label, "regular")),
        (f"{_SCREENS_DIR}/variant_host_c.layout.json", _screen(source_label, "base")),
        (f"{_SCREENS_DIR}/variant_host_c@compact.layout.json", _screen(source_label, "compact")),
        (f"{_SCREENS_DIR}/variant_host_m.layout.json", _screen(source_label, "base")),
        (f"{_SCREENS_DIR}/variant_host_m@medium.layout.json", _screen(source_label, "medium")),
        (f"{_SCREENS_DIR}/variant_state.layout.json", _echo_screen(source_label, "base")),
        (f"{_SCREENS_DIR}/variant_state@regular.layout.json", _echo_screen(source_label, "regular")),
    ]
    entries: list[dict] = []

    def _add(
        *,
        attribute: str,
        case: str,
        value: Any,
        layout: dict,
        cases: list[dict],
        companions: list[str],
        platforms: list[str],
        state: dict | None = None,
    ) -> None:
        layout_rel = f"fixtures/common/{attribute}__{case}.layout.json"
        test_rel = f"fixtures/common/{attribute}__{case}.test.json"
        files.append((layout_rel, layout))
        files.append((
            test_rel,
            _test(attribute=attribute, case=case, layout_rel=layout_rel, cases=cases),
        ))
        entries.append(_entry(
            attribute=attribute,
            case=case,
            value=value,
            layout_rel=layout_rel,
            test_rel=test_rel,
            companions=companions,
            platforms=platforms,
            state=state,
        ))

    host_companions = [
        f"{_SCREENS_DIR}/variant_host.layout.json",
        f"{_SCREENS_DIR}/variant_host@regular.layout.json",
    ]

    compact_companions = [
        f"{_SCREENS_DIR}/variant_host_c.layout.json",
        f"{_SCREENS_DIR}/variant_host_c@compact.layout.json",
    ]
    medium_companions = [
        f"{_SCREENS_DIR}/variant_host_m.layout.json",
        f"{_SCREENS_DIR}/variant_host_m@medium.layout.json",
    ]

    # @regular resolution: regular-tier lanes render the variant, the
    # compact-tier lane keeps the base (no promotion downward either).
    _add(
        attribute="variantfile",
        case="regular_on_regular_tier",
        value="@regular",
        layout=_host_layout(source_label, screen="variant_host"),
        cases=[_case("resolves_regular_tier", [
            {"assert": "text", "id": WHICH_ID, "equals": "regular"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ])],
        companions=host_companions,
        platforms=_REGULAR_LANES,
    )
    _add(
        attribute="variantfile",
        case="regular_on_compact_tier",
        value="@regular",
        layout=_host_layout(source_label, screen="variant_host"),
        cases=[_case("base_on_compact_tier", [
            {"assert": "text", "id": WHICH_ID, "equals": "base"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ])],
        companions=host_companions,
        platforms=_COMPACT_LANES,
    )

    # @compact resolution: mirror image of the pair above.
    _add(
        attribute="variantfile",
        case="compact_on_compact_tier",
        value="@compact",
        layout=_host_layout(source_label, screen="variant_host_c"),
        cases=[_case("resolves_compact_tier", [
            {"assert": "text", "id": WHICH_ID, "equals": "compact"},
        ])],
        companions=compact_companions,
        platforms=_COMPACT_LANES,
    )
    _add(
        attribute="variantfile",
        case="compact_on_regular_tier",
        value="@compact",
        layout=_host_layout(source_label, screen="variant_host_c"),
        cases=[_case("base_on_regular_tier", [
            {"assert": "text", "id": WHICH_ID, "equals": "base"},
        ])],
        companions=compact_companions,
        platforms=_REGULAR_LANES,
    )

    # @medium: never promoted to the regular tier; iOS (no medium size
    # class) folds it into the compact tier — the shipped inline
    # responsive fold, mirrored by the variant mechanism.
    _add(
        attribute="variantfile",
        case="medium_no_promotion",
        value="@medium",
        layout=_host_layout(source_label, screen="variant_host_m"),
        cases=[_case("no_promotion_to_regular", [
            {"assert": "text", "id": WHICH_ID, "equals": "base"},
        ])],
        companions=medium_companions,
        platforms=_REGULAR_LANES,
    )
    _add(
        attribute="variantfile",
        case="medium_fold_ios",
        value="@medium",
        layout=_host_layout(source_label, screen="variant_host_m"),
        cases=[_case("medium_folds_into_ios_compact", [
            {"assert": "text", "id": WHICH_ID, "equals": "medium"},
        ])],
        companions=medium_companions,
        platforms=_COMPACT_LANES,
    )

    # Live tier switch (web only — the only lane with a resizable window):
    # 1024 → regular variant, 390 → base, 800 (medium tier, no @medium
    # shipped) → base, 1280 → regular again.
    _add(
        attribute="variantfile",
        case="viewport_switch",
        value="@regular",
        layout=_host_layout(source_label, screen="variant_host"),
        cases=[
            _case("switches_with_viewport", [
                {"assert": "text", "id": WHICH_ID, "equals": "regular"},
                {"action": "setViewport", "width": 390, "height": 844},
                {"assert": "text", "id": WHICH_ID, "equals": "base"},
                {"action": "setViewport", "width": 800, "height": 600},
                {"assert": "text", "id": WHICH_ID, "equals": "base"},
                {"action": "setViewport", "width": 1280, "height": 800},
                {"assert": "text", "id": WHICH_ID, "equals": "regular"},
            ]),
        ],
        companions=host_companions,
        platforms=["web"],
    )

    # State contract: a host-VM value typed before the swap must survive
    # the whole-tree replacement (the swapped trees re-bind it through the
    # embed params plumbing). Web only — setViewport drives the swap.
    _add(
        attribute="variantfile",
        case="state_vm_survives",
        value="@regular",
        layout=_host_layout(
            source_label,
            screen="variant_state",
            params={"fieldValue": "@{conformanceText}"},
            data=[{"name": "conformanceText", "class": "String", "defaultValue": ""}],
            extra_children=[
                {"type": "TextField", "id": STATE_INPUT_ID, "text": "@{conformanceText}"},
            ],
        ),
        cases=[
            _case("vm_state_survives_swap", [
                {"assert": "text", "id": WHICH_ID, "equals": "regular"},
                {"action": "input", "id": STATE_INPUT_ID, "value": "persisted"},
                {"assert": "text", "id": ECHO_ID, "equals": "persisted"},
                {"action": "setViewport", "width": 390, "height": 844},
                {"assert": "text", "id": WHICH_ID, "equals": "base"},
                {"assert": "text", "id": ECHO_ID, "equals": "persisted"},
                {"action": "setViewport", "width": 1280, "height": 800},
                {"assert": "text", "id": WHICH_ID, "equals": "regular"},
                {"assert": "text", "id": ECHO_ID, "equals": "persisted"},
            ]),
        ],
        companions=[
            f"{_SCREENS_DIR}/variant_state.layout.json",
            f"{_SCREENS_DIR}/variant_state@regular.layout.json",
        ],
        platforms=["web"],
        state={
            "vars": [
                {"name": "conformanceText", "class": "String", "defaultValue": ""}
            ],
            "handlers": [],
        },
    )

    return files, entries
