"""Bespoke Embed conformance fixtures (04 embed-isolated track).

Embed stays in ``rules.UNTESTABLE_SECTIONS`` for the generic per-attribute
sweep — a single-file fixture cannot exercise a cross-file screen
reference. Instead this module emits a small semantic fixture family with
**companion embedded-screen layouts** under ``fixtures/Embed/__screens/``:

- ``navigationMode__delegate_baseline`` — delegate embed renders its root
- ``navigationMode__isolated_root``     — isolated embed renders its root
  (the private-stack wrapper must not change root rendering)
- ``params__nested_leaf``               — nested literal params reach the
  embedded screen and resolve via dot-path bindings
- ``params__nested_leaf_binding``       — a nested leaf ``@{binding}``
  against the host VM resolves before hand-off

Programmatic push/pop semantics are covered by runtime unit tests
(EmbedNavigator on iOS/Android + the web template stack). Tap-driven
push/pop conformance needs a host-side mechanism for reaching the embed's
navigator from injected handlers (the ``state.handlers`` contract injects
closures at the HOST screen scope, which cannot see the embed-ambient
navigator) — tracked in docs/plans/2026-07-24-v1-unsupported/04a-design.md
as the Step-4c host-wiring item.

Manifest entries carry a ``companions`` list (repo-relative layout paths);
hosts must make those layouts loadable by bare screen name (e.g.
``DynamicLayoutLoader.loadLayout("embed_root")``) before running the
fixture.
"""
from __future__ import annotations

from typing import Any

from ..core.generated_marker import json_marker

GENERATOR_NAME = "jui conformance generate"
TEST_GENERATED_BY = "@generated jui conformance generate — DO NOT EDIT"

_SCREENS_DIR = "fixtures/Embed/__screens"

HOST_MARKER_ID = "host-marker"
HOST_MARKER_TEXT = "host"
ROOT_LABEL_ID = "embed-root-label"
ROOT_LABEL_TEXT = "embed-root"
PARAMS_NAME_ID = "embed-params-name"
PARAMS_AGE_ID = "embed-params-age"


def _marker(source_label: str) -> dict:
    return json_marker(source=source_label, generator=GENERATOR_NAME)


def _companion_root(source_label: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "embed_root_container",
        "width": "matchParent",
        "height": "wrapContent",
        "orientation": "vertical",
        "child": [
            {"type": "Label", "id": ROOT_LABEL_ID, "text": ROOT_LABEL_TEXT},
        ],
    }


def _companion_params(source_label: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "embed_params_container",
        "width": "matchParent",
        "height": "wrapContent",
        "orientation": "vertical",
        "child": [
            {"type": "Label", "id": PARAMS_NAME_ID, "text": "@{profile.name}"},
            {"type": "Label", "id": PARAMS_AGE_ID, "text": "@{profile.meta.age}"},
        ],
    }


def _host_layout(
    source_label: str,
    *,
    screen: str,
    navigation_mode: str,
    params: dict | None = None,
    data: list | None = None,
) -> dict:
    embed: dict[str, Any] = {
        "type": "Embed",
        "id": "pane",
        "width": "matchParent",
        "height": "wrapContent",
        "screen": screen,
        "navigationMode": navigation_mode,
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
        embed,
    ]
    return layout


def _test(
    *,
    attribute: str,
    case: str,
    layout_rel: str,
    asserts: list[dict],
) -> dict:
    case_id = f"{attribute}__{case}"
    description = (
        f"Embed semantic conformance fixture ({case}). Companion embedded "
        f"screens live under {_SCREENS_DIR}/ — see manifest 'companions'."
    )
    return {
        "type": "screen",
        "source": {"layout": layout_rel},
        "metadata": {
            "name": f"conformance Embed.{attribute} ({case})",
            "description": description,
            "generatedBy": TEST_GENERATED_BY,
            "tags": ["conformance", "embed", "Embed"],
        },
        "platform": "all",
        "cases": [
            {
                "name": case_id,
                "description": description,
                "steps": [{"action": "waitFor", "id": "root"}] + asserts,
            }
        ],
    }


def _entry(
    *,
    attribute: str,
    case: str,
    value: Any,
    layout_rel: str,
    test_rel: str,
    companions: list[str],
) -> dict:
    return {
        "id": f"Embed/{attribute}__{case}",
        "component": "Embed",
        "attribute": attribute,
        "case": case,
        "class": "assertable",
        "host": "Embed",
        "writtenKey": attribute,
        "aliasOf": None,
        "value": value,
        "platforms": ["ios", "android", "web"],
        "mode": None,
        "deprecated": False,
        "layout": layout_rel,
        "test": test_rel,
        "state": None,
        "promotedFrom": None,
        "companions": companions,
    }


def build_embed_fixtures(source_label: str) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Return ``(files, manifest_entries)``.

    ``files`` is a list of ``(repo_relative_path, json_payload)`` covering
    companion screens plus each fixture's layout/test pair. Deterministic —
    same input, same output.
    """
    files: list[tuple[str, dict]] = [
        (f"{_SCREENS_DIR}/embed_root.layout.json", _companion_root(source_label)),
        (f"{_SCREENS_DIR}/embed_params.layout.json", _companion_params(source_label)),
    ]
    entries: list[dict] = []

    root_companion = [f"{_SCREENS_DIR}/embed_root.layout.json"]
    params_companion = [f"{_SCREENS_DIR}/embed_params.layout.json"]

    def _add(
        *,
        attribute: str,
        case: str,
        value: Any,
        layout: dict,
        asserts: list[dict],
        companions: list[str],
    ) -> None:
        layout_rel = f"fixtures/Embed/{attribute}__{case}.layout.json"
        test_rel = f"fixtures/Embed/{attribute}__{case}.test.json"
        files.append((layout_rel, layout))
        files.append((
            test_rel,
            _test(attribute=attribute, case=case, layout_rel=layout_rel, asserts=asserts),
        ))
        entries.append(_entry(
            attribute=attribute,
            case=case,
            value=value,
            layout_rel=layout_rel,
            test_rel=test_rel,
            companions=companions,
        ))

    base_asserts = [
        {"assert": "text", "id": ROOT_LABEL_ID, "equals": ROOT_LABEL_TEXT},
        {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
    ]

    _add(
        attribute="navigationMode",
        case="delegate_baseline",
        value="delegate",
        layout=_host_layout(
            source_label, screen="embed_root", navigation_mode="delegate",
        ),
        asserts=base_asserts,
        companions=root_companion,
    )
    _add(
        attribute="navigationMode",
        case="isolated_root",
        value="isolated",
        layout=_host_layout(
            source_label, screen="embed_root", navigation_mode="isolated",
        ),
        asserts=base_asserts,
        companions=root_companion,
    )
    _add(
        attribute="params",
        case="nested_leaf",
        value={"profile": {"name": "Ada", "meta": {"age": "36"}}},
        layout=_host_layout(
            source_label,
            screen="embed_params",
            navigation_mode="delegate",
            params={"profile": {"name": "Ada", "meta": {"age": "36"}}},
        ),
        asserts=[
            {"assert": "text", "id": PARAMS_NAME_ID, "equals": "Ada"},
            {"assert": "text", "id": PARAMS_AGE_ID, "equals": "36"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=params_companion,
    )
    _add(
        attribute="params",
        case="nested_leaf_binding",
        value={"profile": {"name": "@{hostValue}"}},
        layout=_host_layout(
            source_label,
            screen="embed_params",
            navigation_mode="delegate",
            params={"profile": {"name": "@{hostValue}"}},
            data=[{"name": "hostValue", "class": "String", "defaultValue": "from-host"}],
        ),
        asserts=[
            {"assert": "text", "id": PARAMS_NAME_ID, "equals": "from-host"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=params_companion,
    )

    return files, entries
