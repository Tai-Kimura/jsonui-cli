"""Declarative rules for the v2 ``interactive`` conformance class.

conformance v1 covered only static rendering; every ``@{}`` binding and
callback attribute was recorded as an ``untestable`` skip. v2 promotes a
curated subset into class ``interactive`` fixtures built around one
platform-neutral host mechanism — the **conformanceState contract**
(documented in ``conformance/INTERACTIVE_HOST_CONTRACT.md``):

- the fixture layout declares its variables in the standard JsonUI ``data``
  section (``{"name", "class", "defaultValue"}``) — every runtime already
  provisions initial values from it (SwiftJsonUI ``DynamicView.mergeDataDefaults``,
  KotlinJsonUI ``applyDataSectionDefaults``, rjui ``create<View>Data()``),
- the manifest declares the handlers the host must inject: each handler is a
  closure registered under its name in the state dict that, when invoked,
  sets exactly one variable to a literal value (any callback payload is
  ignored). Hosts implement this *once*; no per-fixture code.

Fixture case types (plan 12 §2.1):

- ``binding_initial``  — ``@{var}`` + ``data`` default -> initial value rendered
- ``binding_twoway``   — runner ``input`` into a bound field -> mirror Label follows
- ``callback_fire``    — runner ``tap``/``input``/``selectOption``/``longPress``
  fires the handler -> mirror Label text changes
- ``binding_<enum>``   — enum value sweep through a binding, reusing the
  existing assertion mapping (``visibility`` -> visible / notVisible)

All values are deterministic constants; there is no randomness or time.
Every generated test stays inside the jsonui-test-runner schema (no schema
extension was needed: ``tap``/``input``/``longPress``/``selectOption``/
``waitFor`` + ``text``/``visible``/``notVisible`` assertions suffice).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import rules

CLASS_INTERACTIVE = "interactive"

#: id of the mirror Label bound to the observed variable.
MIRROR_ID = "mirror"

#: Skip reasons that interactive fixtures may promote out of the skip list.
PROMOTABLE_REASONS = (rules.REASON_CALLBACK, rules.REASON_BINDING_ONLY)

# Deterministic state vocabulary (shared across all interactive fixtures so
# hosts and humans see one small, predictable surface).
TEXT_VAR = "conformanceText"
RESULT_VAR = "conformanceResult"
VISIBILITY_VAR = "conformanceVisibility"
FIRE_HANDLER = "conformanceFire"

BOUND_INITIAL = "Bound Initial"
TWOWAY_INITIAL = "Initial Text"
TYPED_TEXT = "Typed Text"
RESULT_BEFORE = "ready"
RESULT_AFTER = "fired"


# --------------------------------------------------------------------------- #
# Contract dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StateVar:
    """One ``data``-section variable. v2 keeps the type surface at String —
    the most portable ``defaultValue`` representation across the three
    runtimes (see INTERACTIVE_HOST_CONTRACT.md)."""

    name: str
    cls: str
    default: str


@dataclass(frozen=True)
class StateHandler:
    """One host-injected closure: invoking it sets ``var`` to ``value``."""

    name: str
    var: str
    value: str


@dataclass(frozen=True)
class InteractiveSpec:
    """One concrete interactive fixture for a (section, attribute) pair."""

    case: str  # fixture case name (binding_initial / callback_fire / ...)
    host: str  # component type of the target node
    target_attrs: tuple[tuple[str, Any], ...]  # written onto the target node
    vars: tuple[StateVar, ...]
    handlers: tuple[StateHandler, ...]
    steps: tuple[dict, ...]  # test steps appended after `waitFor root`
    mirror_var: str | None = None  # append a mirror Label bound to this var


@dataclass(frozen=True)
class InteractivePlan:
    """All interactive fixtures for one (section, attribute) pair."""

    section: str
    attribute: str
    specs: tuple[InteractiveSpec, ...]
    platforms: tuple[str, ...]
    mode: str | list | None
    deprecated: str | list | None
    promoted_from: str | None  # skip reason this attribute was promoted out of


# --------------------------------------------------------------------------- #
# Step builders
# --------------------------------------------------------------------------- #


def _tap_target() -> dict:
    return {"action": "tap", "id": rules.TARGET_ID}


def _long_press_target() -> dict:
    return {"action": "longPress", "id": rules.TARGET_ID}


def _input_target(value: str) -> dict:
    return {"action": "input", "id": rules.TARGET_ID, "value": value}


def _select_target(label: str) -> dict:
    return {"action": "selectOption", "id": rules.TARGET_ID, "label": label}


def _text_equals(element_id: str, expected: str) -> dict:
    return {"assert": "text", "id": element_id, "equals": expected}


def _target_visible() -> dict:
    return {"assert": "visible", "id": rules.TARGET_ID}


def _target_not_visible() -> dict:
    return {"assert": "notVisible", "id": rules.TARGET_ID}


# --------------------------------------------------------------------------- #
# Spec factories
# --------------------------------------------------------------------------- #

_RESULT_STATE = (StateVar(RESULT_VAR, "String", RESULT_BEFORE),)
_FIRE_HANDLERS = (StateHandler(FIRE_HANDLER, RESULT_VAR, RESULT_AFTER),)


def _binding_initial(host: str) -> InteractiveSpec:
    """`text: "@{var}"` + data default -> the default is rendered."""
    return InteractiveSpec(
        case="binding_initial",
        host=host,
        target_attrs=(("text", f"@{{{TEXT_VAR}}}"),),
        vars=(StateVar(TEXT_VAR, "String", BOUND_INITIAL),),
        handlers=(),
        steps=(_text_equals(rules.TARGET_ID, BOUND_INITIAL),),
    )


def _binding_twoway(host: str) -> InteractiveSpec:
    """Two-way text binding: runner input -> mirror Label follows."""
    return InteractiveSpec(
        case="binding_twoway",
        host=host,
        target_attrs=(("text", f"@{{{TEXT_VAR}}}"),),
        vars=(StateVar(TEXT_VAR, "String", TWOWAY_INITIAL),),
        handlers=(),
        steps=(
            _text_equals(MIRROR_ID, TWOWAY_INITIAL),
            _input_target(TYPED_TEXT),
            _text_equals(MIRROR_ID, TYPED_TEXT),
        ),
        mirror_var=TEXT_VAR,
    )


def _callback_fire(host: str, attribute: str, value: str, trigger: dict | None) -> InteractiveSpec:
    """Trigger action fires the handler -> mirror Label text flips.

    ``trigger=None`` covers lifecycle callbacks that fire without runner
    interaction (``onAppear``): the fixture only asserts the post state.
    """
    if trigger is None:
        steps: tuple[dict, ...] = (_text_equals(MIRROR_ID, RESULT_AFTER),)
    else:
        steps = (
            _text_equals(MIRROR_ID, RESULT_BEFORE),
            trigger,
            _text_equals(MIRROR_ID, RESULT_AFTER),
        )
    return InteractiveSpec(
        case="callback_fire",
        host=host,
        target_attrs=((attribute, value),),
        vars=_RESULT_STATE,
        handlers=_FIRE_HANDLERS,
        steps=steps,
        mirror_var=RESULT_VAR,
    )


_FIRE_BINDING = f"@{{{FIRE_HANDLER}}}"

#: visibility enum value -> assertion (mirrors rules._assertable_cases).
_VISIBILITY_ASSERTS = {
    "visible": _target_visible,
    "invisible": _target_not_visible,
    "gone": _target_not_visible,
}


def _visibility_sweep() -> tuple[InteractiveSpec, ...]:
    """Enum full-value sweep of ``visibility`` *through a binding*."""
    specs = []
    for value, make_assert in _VISIBILITY_ASSERTS.items():
        specs.append(
            InteractiveSpec(
                case=f"binding_{value}",
                host="View",
                target_attrs=(("visibility", f"@{{{VISIBILITY_VAR}}}"),),
                vars=(StateVar(VISIBILITY_VAR, "String", value),),
                handlers=(),
                steps=(make_assert(),),
            )
        )
    return tuple(specs)


# --------------------------------------------------------------------------- #
# The rule table
# --------------------------------------------------------------------------- #

#: (section, attribute) -> interactive fixture specs.
#:
#: Only attributes with a cross-platform trigger in the runner vocabulary are
#: listed; everything else keeps its v1 skip reason. Selector-format
#: attributes (``onclick``/``onAppear`` — typed ``string``) are written as a
#: bare handler name; binding-typed attributes use ``@{...}``.
INTERACTIVE_SPECS: dict[tuple[str, str], tuple[InteractiveSpec, ...]] = {
    # --- binding fixtures on already-testable attributes (not promotions) --- #
    ("Label", "text"): (_binding_initial("Label"),),
    ("Button", "text"): (_binding_initial("Button"),),
    ("TextField", "text"): (_binding_twoway("TextField"),),
    ("TextView", "text"): (_binding_twoway("TextView"),),
    ("common", "visibility"): _visibility_sweep(),
    # --- promotions out of `untestable: callback` --- #
    ("common", "onclick"): (_callback_fire("Button", "onclick", FIRE_HANDLER, _tap_target()),),
    ("common", "onClick"): (_callback_fire("Button", "onClick", _FIRE_BINDING, _tap_target()),),
    ("common", "onLongPress"): (
        _callback_fire("Button", "onLongPress", _FIRE_BINDING, _long_press_target()),
    ),
    ("common", "onAppear"): (_callback_fire("View", "onAppear", FIRE_HANDLER, None),),
    ("TextField", "onTextChange"): (
        _callback_fire("TextField", "onTextChange", _FIRE_BINDING, _input_target(TYPED_TEXT)),
    ),
    ("TextView", "onTextChange"): (
        _callback_fire("TextView", "onTextChange", _FIRE_BINDING, _input_target(TYPED_TEXT)),
    ),
    ("Switch", "onValueChange"): (
        _callback_fire("Switch", "onValueChange", _FIRE_BINDING, _tap_target()),
    ),
    ("Toggle", "onValueChange"): (
        _callback_fire("Toggle", "onValueChange", _FIRE_BINDING, _tap_target()),
    ),
    ("CheckBox", "onValueChange"): (
        _callback_fire("CheckBox", "onValueChange", _FIRE_BINDING, _tap_target()),
    ),
    ("Check", "onValueChange"): (
        _callback_fire("Check", "onValueChange", _FIRE_BINDING, _tap_target()),
    ),
    ("SelectBox", "onValueChange"): (
        _callback_fire("SelectBox", "onValueChange", _FIRE_BINDING, _select_target("Two")),
    ),
    ("SelectBox", "onValueChanged"): (
        _callback_fire("SelectBox", "onValueChanged", _FIRE_BINDING, _select_target("Two")),
    ),
}
# Not promoted (kept as v1 skips, with the blocking gap):
# - binding-only attrs (`bind`/`binding`/`bindingScript`, Collection scrollTo/
#   currentPage): binding *wiring* without a runner-observable text surface —
#   boolean/checked mirrors need a `checked` assertion the runner lacks.
# - Slider/Segment/TabView/Collection value callbacks: no runner action can
#   deterministically drive them (no drag/slide vocabulary; segment items and
#   tab headers are not individually addressable by element id).
# - TextField focus/editing callbacks (onFocus/onBlur/onBeginEditing/...):
#   need a focus-shift vocabulary; revisit with the iOS/Android round.


def specs_for(section: str, attribute: str) -> tuple[InteractiveSpec, ...]:
    """Interactive specs for one attribute (empty tuple when none)."""
    return INTERACTIVE_SPECS.get((section, attribute), ())


def plan_interactive(
    section: str, attribute: str, defn: dict, promoted_from: str | None
) -> InteractivePlan | None:
    """Build the InteractivePlan for one attribute, or None."""
    specs = specs_for(section, attribute)
    if not specs:
        return None
    return InteractivePlan(
        section=section,
        attribute=attribute,
        specs=specs,
        platforms=rules._platforms(defn),
        mode=defn.get("mode"),
        deprecated=defn.get("deprecated"),
        promoted_from=promoted_from,
    )


def state_payload(spec: InteractiveSpec) -> dict:
    """Manifest ``state`` object — the exact contract a host must satisfy."""
    return {
        "vars": [
            {"name": v.name, "class": v.cls, "defaultValue": v.default} for v in spec.vars
        ],
        "handlers": [
            {"name": h.name, "set": {"var": h.var, "value": h.value}} for h in spec.handlers
        ],
    }
