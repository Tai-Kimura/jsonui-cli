"""Bespoke Embed conformance fixtures (04 embed-isolated track).

Embed stays in ``rules.UNTESTABLE_SECTIONS`` for the generic per-attribute
sweep — a single-file fixture cannot exercise a cross-file screen
reference. Instead this module emits a small semantic fixture family with
**companion embedded-screen layouts** under ``fixtures/Embed/__screens/``:

- ``navigationMode__delegate_baseline`` — delegate embed renders its root
- ``navigationMode__isolated_root``     — isolated embed renders its root
  (the private-stack wrapper must not change root rendering)
- ``navigationMode__isolated_push``     — tapping a HOST-side button pushes
  onto the embed's private stack (host marker persists = push contained)
- ``navigationMode__isolated_pop_boundary`` — pop returns to the embed
  root and a second pop at the stack bottom is a bounded no-op (the embed
  never closes itself)
- ``params__nested_leaf``               — nested literal params reach the
  embedded screen and resolve via dot-path bindings
- ``params__nested_leaf_binding``       — a nested leaf ``@{binding}``
  against the host VM resolves before hand-off

The push/pop fixtures use the second ``state.handlers`` kind
(``embed: {id, action, screen?}`` — INTERACTIVE_HOST_CONTRACT.md): hosts
build the injected closures on top of the library's EmbedNavigatorRegistry
(embedId-keyed lookup of the mounted isolated embed's navigator), which is
how a host-scope closure reaches the embed-ambient navigator without any
Dynamic-runtime onclick changes.

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
SECOND_LABEL_ID = "embed-second-label"
SECOND_LABEL_TEXT = "embed-second"
PARAMS_NAME_ID = "embed-params-name"
PARAMS_AGE_ID = "embed-params-age"
PUSH_BUTTON_ID = "push-button"
POP_BUTTON_ID = "pop-button"

# state.handlers declarations (embed kind) for the tap-driven fixtures.
_PUSH_HANDLER = {
    "name": "confPush",
    "embed": {"id": "pane", "action": "push", "screen": "embed_second"},
}
_POP_HANDLER = {"name": "confPop", "embed": {"id": "pane", "action": "pop"}}


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


def _companion_second(source_label: str) -> dict:
    return {
        "_generated": _marker(source_label),
        "type": "View",
        "id": "embed_second_container",
        "width": "matchParent",
        "height": "wrapContent",
        "orientation": "vertical",
        "child": [
            {"type": "Label", "id": SECOND_LABEL_ID, "text": SECOND_LABEL_TEXT},
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
        # Declared so the web static codegen types the dot-path bindings
        # (class Object → Record<string, any>); the nested params tree
        # handed by the host replaces this default wholesale.
        "data": [
            {
                "name": "profile",
                "class": "Object",
                "defaultValue": {"name": "", "meta": {"age": ""}},
            }
        ],
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
    buttons: list[dict] | None = None,
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
        *(buttons or []),
        embed,
    ]
    return layout


def _test(
    *,
    attribute: str,
    case: str,
    layout_rel: str,
    steps: list[dict],
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
                "steps": [{"action": "waitFor", "id": "root"}] + steps,
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
    state: dict | None = None,
) -> dict:
    return {
        "id": f"Embed/{attribute}__{case}",
        "component": "Embed",
        "attribute": attribute,
        "case": case,
        "class": "interactive" if state else "assertable",
        "host": "Embed",
        "writtenKey": attribute,
        "aliasOf": None,
        "value": value,
        "platforms": ["ios", "android", "web"],
        "mode": None,
        "deprecated": False,
        "layout": layout_rel,
        "test": test_rel,
        "state": state,
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
        (f"{_SCREENS_DIR}/embed_second.layout.json", _companion_second(source_label)),
        (f"{_SCREENS_DIR}/embed_params.layout.json", _companion_params(source_label)),
    ]
    entries: list[dict] = []

    root_companion = [f"{_SCREENS_DIR}/embed_root.layout.json"]
    stack_companions = [
        f"{_SCREENS_DIR}/embed_root.layout.json",
        f"{_SCREENS_DIR}/embed_second.layout.json",
    ]
    params_companion = [f"{_SCREENS_DIR}/embed_params.layout.json"]

    def _add(
        *,
        attribute: str,
        case: str,
        value: Any,
        layout: dict,
        steps: list[dict],
        companions: list[str],
        state: dict | None = None,
    ) -> None:
        layout_rel = f"fixtures/Embed/{attribute}__{case}.layout.json"
        test_rel = f"fixtures/Embed/{attribute}__{case}.test.json"
        files.append((layout_rel, layout))
        files.append((
            test_rel,
            _test(attribute=attribute, case=case, layout_rel=layout_rel, steps=steps),
        ))
        entries.append(_entry(
            attribute=attribute,
            case=case,
            value=value,
            layout_rel=layout_rel,
            test_rel=test_rel,
            companions=companions,
            state=state,
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
        steps=base_asserts,
        companions=root_companion,
    )
    _add(
        attribute="navigationMode",
        case="isolated_root",
        value="isolated",
        layout=_host_layout(
            source_label, screen="embed_root", navigation_mode="isolated",
        ),
        steps=base_asserts,
        companions=root_companion,
    )
    # Tap-driven stack semantics. The buttons live in the HOST layout: the
    # injected closures reach the embed's private stack through the
    # library's EmbedNavigatorRegistry (embed handler kind). Push must show
    # the pushed screen while the host marker persists (containment); pop
    # must return to the embed root, and popping at the stack bottom is a
    # bounded no-op — the embed root and the host both stay up.
    _add(
        attribute="navigationMode",
        case="isolated_push",
        value="isolated",
        layout=_host_layout(
            source_label,
            screen="embed_root",
            navigation_mode="isolated",
            buttons=[
                {"type": "Button", "id": PUSH_BUTTON_ID, "text": "push", "onclick": "confPush"},
            ],
        ),
        steps=[
            {"assert": "text", "id": ROOT_LABEL_ID, "equals": ROOT_LABEL_TEXT},
            {"action": "tap", "id": PUSH_BUTTON_ID},
            {"action": "waitFor", "id": SECOND_LABEL_ID},
            {"assert": "text", "id": SECOND_LABEL_ID, "equals": SECOND_LABEL_TEXT},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=stack_companions,
        state={"vars": [], "handlers": [_PUSH_HANDLER]},
    )
    _add(
        attribute="navigationMode",
        case="isolated_pop_boundary",
        value="isolated",
        layout=_host_layout(
            source_label,
            screen="embed_root",
            navigation_mode="isolated",
            buttons=[
                {"type": "Button", "id": PUSH_BUTTON_ID, "text": "push", "onclick": "confPush"},
                {"type": "Button", "id": POP_BUTTON_ID, "text": "pop", "onclick": "confPop"},
            ],
        ),
        steps=[
            {"action": "tap", "id": PUSH_BUTTON_ID},
            {"action": "waitFor", "id": SECOND_LABEL_ID},
            {"assert": "text", "id": SECOND_LABEL_ID, "equals": SECOND_LABEL_TEXT},
            {"action": "tap", "id": POP_BUTTON_ID},
            {"action": "waitFor", "id": ROOT_LABEL_ID},
            {"assert": "text", "id": ROOT_LABEL_ID, "equals": ROOT_LABEL_TEXT},
            # Second pop at the stack bottom: bounded no-op — the embed
            # neither closes nor escapes into the host.
            {"action": "tap", "id": POP_BUTTON_ID},
            {"action": "waitFor", "id": ROOT_LABEL_ID},
            {"assert": "text", "id": ROOT_LABEL_ID, "equals": ROOT_LABEL_TEXT},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=stack_companions,
        state={"vars": [], "handlers": [_PUSH_HANDLER, _POP_HANDLER]},
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
        steps=[
            {"assert": "text", "id": PARAMS_NAME_ID, "equals": "Ada"},
            {"assert": "text", "id": PARAMS_AGE_ID, "equals": "36"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=params_companion,
    )
    # Mixed literal + binding tree: the params object must be complete
    # (meta included) because the embedded layout dereferences
    # profile.meta.age unconditionally — dot-chains over object-typed data
    # are not null-safe in generated code.
    _add(
        attribute="params",
        case="nested_leaf_binding",
        value={"profile": {"name": "@{hostValue}", "meta": {"age": "36"}}},
        layout=_host_layout(
            source_label,
            screen="embed_params",
            navigation_mode="delegate",
            params={"profile": {"name": "@{hostValue}", "meta": {"age": "36"}}},
            data=[{"name": "hostValue", "class": "String", "defaultValue": "from-host"}],
        ),
        steps=[
            {"assert": "text", "id": PARAMS_NAME_ID, "equals": "from-host"},
            {"assert": "text", "id": PARAMS_AGE_ID, "equals": "36"},
            {"assert": "text", "id": HOST_MARKER_ID, "equals": HOST_MARKER_TEXT},
        ],
        companions=params_companion,
    )

    return files, entries
