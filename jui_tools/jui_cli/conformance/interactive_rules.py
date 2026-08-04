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
- ``callback_fire``    — runner ``tap``/``input``/``selectOption``/``longPress``/
  ``swipe`` fires the handler -> mirror Label text changes
- ``binding_<enum>``   — enum value sweep through a binding, reusing the
  existing assertion mapping (``visibility`` -> visible / notVisible)

All values are deterministic constants; there is no randomness or time.
Every generated test stays inside the jsonui-test-runner schema (no schema
extension was needed: ``tap``/``input``/``longPress``/``selectOption``/
``swipe``/``waitFor`` + ``text``/``visible``/``notVisible`` assertions
suffice).
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

# Binding-resolution measurement vocabulary (renderer SSoT track 15-5).
# These fixtures measure shared/core/binding_semantics.json semantics on the
# real runtimes; each mirrors a shared vector (binding_vectors.json id noted
# on the spec). Layout-only seeds (DataVar) carry native JSON values through
# the standard `data` section WITHOUT a manifest state.vars declaration —
# state.vars stays the String-typed host contract surface.
PROFILE_VAR = "conformanceProfile"
PROFILE_DEFAULT = {"name": "Grace", "meta": {"age": 36}}
ITEMS_VAR = "conformanceItems"
ITEMS_OBJECTS = [{"title": "First"}, {"title": "Second"}]
ITEMS_SCALARS = ["alpha", "beta"]
COUNT_VAR = "conformanceCount"
COUNT_DEFAULT = 5
FLAG_VAR = "conformanceFlag"
MISSING_KEY = "conformanceMissing"  # deliberately never provisioned
DEFAULT_LITERAL = "Guest"


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
    """One host-injected closure: invoking it sets ``var`` to ``value``.

    ``cls`` is the closure type the layout ``data`` section declares for the
    handler. A handler name is a data property exactly as ``@{name}`` is —
    the generated code reads ``data.<name>`` either way — so a layout that
    never declares it hands the codegen a property its Data type has no room
    for (plan 44: 10 of the web host's type errors were exactly this).

    The signature is the value the RENDERER passes, not the platform event:
    every converter unwraps the event and calls the handler with the changed
    value (``e.target.value`` / ``e.target.checked``). ``(Event) -> Void``
    would resolve through type_mapping.json to the event type instead and
    contradict every call site.
    """

    name: str
    var: str
    value: str
    cls: str = "() -> Void"


#: Sentinel ``DataVar.default`` meaning "declare the name, provision nothing".
#: The declaration gives the codegens a typed property; the absent
#: ``defaultValue`` key keeps the value unresolved at runtime — every
#: dynamic path skips an entry that has no ``defaultValue``
#: (SwiftJsonUI ``if let defaultValue = dict["defaultValue"]``, KotlinJsonUI
#: ``obj.get("defaultValue") ?: return@forEach``), and rjui emits
#: ``undefined``. That is what the ``??``-default and unresolved-binding
#: fixtures measure, so declaring the key must NOT provision it.
NO_DEFAULT: Any = object()


@dataclass(frozen=True)
class DataVar:
    """One layout-only ``data``-section entry with a native JSON default.

    Unlike :class:`StateVar`, a DataVar is NOT declared in the manifest
    ``state.vars`` (that surface is String-typed by host contract — the iOS
    host decodes ``defaultValue`` as String and exposes Binding<String>).
    A DataVar rides the standard production data-section defaults path of
    each runtime instead: SwiftJsonUI ``DynamicView.mergeDataDefaults``,
    KotlinJsonUI ``applyDataSectionDefaults``, rjui ``create<View>Data()``.
    This is the vehicle for nested objects / arrays / typed scalars that the
    binding-resolution fixtures (track 15-5) resolve dot paths against.
    """

    name: str
    cls: str
    default: Any


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
    data_vars: tuple[DataVar, ...] = ()  # layout-only data-section seeds


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


def _swipe_target(direction: str = "left") -> dict:
    """A swipe IS a pan: press, move, release over the element. All three
    drivers synthesize it (web: mouse drag → pointermove with buttons held;
    ios: XCUIElement.swipe*; android: UiAutomator swipe), so it can fire an
    onPan handler deterministically. Direction is irrelevant to the
    assertion — any drag over the target fires the handler."""
    return {"action": "swipe", "id": rules.TARGET_ID, "direction": direction}


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

# Declared closure types for `conformanceFire`, by what the converters hand it.
HANDLER_VOID = "() -> Void"  # tap/lifecycle: the handler takes no payload
HANDLER_TEXT = "(String) -> Void"  # text + option change: the new string
HANDLER_BOOL = "(Boolean) -> Void"  # toggle change: the new checked state
HANDLER_EVENT = "(Any) -> Void"  # gesture: the platform's own event object


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


def _callback_fire(
    host: str,
    attribute: str,
    value: str,
    trigger: dict | None,
    handler_cls: str = HANDLER_VOID,
) -> InteractiveSpec:
    """Trigger action fires the handler -> mirror Label text flips.

    ``trigger=None`` covers lifecycle callbacks that fire without runner
    interaction (``onAppear``): the fixture only asserts the post state.

    ``handler_cls`` is the closure type declared for ``conformanceFire`` in
    the layout ``data`` section — the arity/type the converters call it with
    (see :class:`StateHandler`).
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
        handlers=(StateHandler(FIRE_HANDLER, RESULT_VAR, RESULT_AFTER, handler_cls),),
        steps=steps,
        mirror_var=RESULT_VAR,
    )


def _binding_text(
    case: str,
    template: str,
    expected: str,
    *,
    vars: tuple[StateVar, ...] = (),
    data_vars: tuple[DataVar, ...] = (),
) -> InteractiveSpec:
    """One Label.text binding-resolution fixture: template in, exact text out.

    Statically assertable (waitFor + text equals) — no handlers, no mirror.
    Unresolved-expectation templates wrap the expression in literal parens so
    the Label never renders fully empty (a zero-size text node is not reliably
    addressable by every platform driver).
    """
    return InteractiveSpec(
        case=case,
        host="Label",
        target_attrs=(("text", template),),
        vars=vars,
        handlers=(),
        steps=(_text_equals(rules.TARGET_ID, expected),),
        data_vars=data_vars,
    )


#: Binding-resolution fixtures for Label.text (binding_semantics.json `text`
#: context). Comments name the shared vector each case mirrors.
_TEXT_STATE = (StateVar(TEXT_VAR, "String", BOUND_INITIAL),)
_PROFILE_DATA = (DataVar(PROFILE_VAR, "Object", PROFILE_DEFAULT),)
#: `conformanceMissing` is declared but never provisioned — see NO_DEFAULT.
_MISSING_DATA = (DataVar(MISSING_KEY, "String", NO_DEFAULT),)
#: Same key, declared as the node shape the dot-path expression traverses:
#: `@{conformanceMissing.name}` reads a child off it, which a String has no
#: room for. The declaration describes the shape the binding ASSUMES; the
#: fixture measures what happens when nothing is there to traverse.
_MISSING_NODE_DATA = (DataVar(MISSING_KEY, "Object", NO_DEFAULT),)

_BINDING_SEMANTICS_TEXT: tuple[InteractiveSpec, ...] = (
    # text_flat_basic — mixed-text interpolation
    _binding_text(
        "binding_mixed",
        f"Hello @{{{TEXT_VAR}}}!",
        f"Hello {BOUND_INITIAL}!",
        vars=_TEXT_STATE,
    ),
    # text_dot_path — nested object traversal
    _binding_text(
        "binding_dot_path",
        f"@{{{PROFILE_VAR}.name}}",
        "Grace",
        data_vars=_PROFILE_DATA,
    ),
    # text_deep_dot_path — 3-segment path + integral-number stringification
    _binding_text(
        "binding_deep_path",
        f"@{{{PROFILE_VAR}.meta.age}}",
        "36",
        data_vars=_PROFILE_DATA,
    ),
    # text_bracket_index — bracket index into array of objects
    _binding_text(
        "binding_bracket_index",
        f"@{{{ITEMS_VAR}[0].title}}",
        "First",
        data_vars=(DataVar(ITEMS_VAR, "Array", ITEMS_OBJECTS),),
    ),
    # text_bracket_index_scalar — bracket index to a scalar element
    _binding_text(
        "binding_bracket_scalar",
        f"@{{{ITEMS_VAR}[1]}}",
        "beta",
        data_vars=(DataVar(ITEMS_VAR, "Array", ITEMS_SCALARS),),
    ),
    # text_default_double_quotes — `??` default, double-quoted, missing key
    _binding_text(
        "binding_default_double",
        f'@{{{MISSING_KEY} ?? "{DEFAULT_LITERAL}"}}',
        DEFAULT_LITERAL,
        data_vars=_MISSING_DATA,
    ),
    # text_default_single_quotes — `??` default, single-quoted (canonical-new)
    _binding_text(
        "binding_default_single",
        f"@{{{MISSING_KEY} ?? '{DEFAULT_LITERAL}'}}",
        DEFAULT_LITERAL,
        data_vars=_MISSING_DATA,
    ),
    # text_default_number — `??` typed number default stringified
    _binding_text(
        "binding_default_number",
        f"@{{{MISSING_KEY} ?? 42}}",
        "42",
        data_vars=_MISSING_DATA,
    ),
    # text_default_resolved_wins / fallbackPrecedence 1 over 2 — the
    # data-section defaultValue resolves, so the inline default never applies
    _binding_text(
        "binding_default_resolved",
        f"@{{{TEXT_VAR} ?? '{DEFAULT_LITERAL}'}}",
        BOUND_INITIAL,
        vars=_TEXT_STATE,
    ),
    # text_unresolved_flat — unresolved flat key -> empty string (parens keep
    # the Label addressable)
    _binding_text(
        "binding_unresolved_flat",
        f"(@{{{MISSING_KEY}}})",
        "()",
        data_vars=_MISSING_DATA,
    ),
    # text_unresolved_intermediate — missing intermediate node -> empty string
    _binding_text(
        "binding_unresolved_path",
        f"(@{{{MISSING_KEY}.name}})",
        "()",
        data_vars=_MISSING_NODE_DATA,
    ),
    # text_number_integer — '5', never '5.0'
    _binding_text(
        "binding_number_int",
        f"@{{{COUNT_VAR}}}",
        "5",
        data_vars=(DataVar(COUNT_VAR, "Int", COUNT_DEFAULT),),
    ),
    # text_bool_true — bool stringification 'true'
    _binding_text(
        "binding_bool_text",
        f"@{{{FLAG_VAR}}}",
        "true",
        data_vars=(DataVar(FLAG_VAR, "Bool", True),),
    ),
)


def _negation_hidden() -> InteractiveSpec:
    """value_bool_negation_false — `hidden: "@{!flag}"` with flag=false.

    The assertive direction: !false => hidden=true => notVisible. An
    unresolved expression falls back to the attribute default (hidden=false,
    visible), so a resolution failure cannot pass by accident.
    """
    return InteractiveSpec(
        case="binding_negation",
        host="View",
        target_attrs=(("hidden", f"@{{!{FLAG_VAR}}}"),),
        vars=(),
        handlers=(),
        steps=(_target_not_visible(),),
        data_vars=(DataVar(FLAG_VAR, "Bool", False),),
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
    ("Label", "text"): (_binding_initial("Label"),) + _BINDING_SEMANTICS_TEXT,
    ("Button", "text"): (_binding_initial("Button"),),
    ("TextField", "text"): (_binding_twoway("TextField"),),
    ("TextView", "text"): (_binding_twoway("TextView"),),
    ("common", "visibility"): _visibility_sweep(),
    ("common", "hidden"): (_negation_hidden(),),
    # --- promotions out of `untestable: callback` --- #
    ("common", "onclick"): (_callback_fire("Button", "onclick", FIRE_HANDLER, _tap_target()),),
    ("common", "onClick"): (_callback_fire("Button", "onClick", _FIRE_BINDING, _tap_target()),),
    ("common", "onLongPress"): (
        _callback_fire("Button", "onLongPress", _FIRE_BINDING, _long_press_target()),
    ),
    # View host on purpose: a pan surface is normally a container, and the
    # 200x200 BASE_ATTRS View gives the swipe a real bounding box. The payload
    # is ignored by the host contract, but the web converter still HANDS one
    # over (`data.conformanceFire?.(e)` with the pointer event), so the
    # declared closure has to accept it.
    ("common", "onPan"): (
        _callback_fire("View", "onPan", _FIRE_BINDING, _swipe_target(), HANDLER_EVENT),
    ),
    ("common", "onAppear"): (_callback_fire("View", "onAppear", FIRE_HANDLER, None),),
    ("TextField", "onTextChange"): (
        _callback_fire(
            "TextField", "onTextChange", _FIRE_BINDING, _input_target(TYPED_TEXT), HANDLER_TEXT
        ),
    ),
    ("TextView", "onTextChange"): (
        _callback_fire(
            "TextView", "onTextChange", _FIRE_BINDING, _input_target(TYPED_TEXT), HANDLER_TEXT
        ),
    ),
    # Toggle / Check are `_alias_of` pointer sections (B1) — their plans
    # never form, so only the canonical Switch / CheckBox rules exist.
    ("Switch", "onValueChange"): (
        _callback_fire("Switch", "onValueChange", _FIRE_BINDING, _tap_target(), HANDLER_BOOL),
    ),
    ("CheckBox", "onValueChange"): (
        _callback_fire("CheckBox", "onValueChange", _FIRE_BINDING, _tap_target(), HANDLER_BOOL),
    ),
    ("SelectBox", "onValueChange"): (
        _callback_fire(
            "SelectBox", "onValueChange", _FIRE_BINDING, _select_target("Two"), HANDLER_TEXT
        ),
    ),
    ("SelectBox", "onValueChanged"): (
        _callback_fire(
            "SelectBox", "onValueChanged", _FIRE_BINDING, _select_target("Two"), HANDLER_TEXT
        ),
    ),
}
# Not promoted (kept as v1 skips, with the blocking gap):
# - binding-only attrs (`bind`/`binding`/`bindingScript`, Collection scrollTo/
#   currentPage): binding *wiring* without a runner-observable text surface —
#   boolean/checked mirrors need a `checked` assertion the runner lacks.
# - Slider/Segment/TabView/Collection value callbacks: no runner action can
#   deterministically drive them (`swipe` is direction-only — it cannot drag a
#   thumb to a specific value; segment items and tab headers are not
#   individually addressable by element id).
# - common.onPinch: implemented on all three platforms, but no runner action
#   synthesizes a two-pointer gesture (`swipe` is single-pointer), so the
#   handler cannot be fired deterministically. Needs a `pinch` action in the
#   runner vocabulary; onPan is promoted precisely because `swipe` IS a pan.
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
