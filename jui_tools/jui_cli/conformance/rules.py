"""Declarative classification rules for conformance fixture generation.

Every attribute in ``attribute_definitions.json`` is classified into one of
three classes (see plan §3.1):

- ``assertable`` — machine-verifiable with the cross-platform assertions the
  jsonui-test-runner supports (visible / notVisible / enabled / disabled /
  text equals / contains / count).
- ``visual`` — only observable in rendered output (colors, padding, fonts...).
  A fixture is still generated, but the test only takes a ``screenshot``
  (artifact capture; pixel comparison is a non-goal in v1).
- ``untestable`` — callbacks, binding-only attributes, metadata, and
  attributes that cannot be expressed as a single-file static fixture.
  These are *recorded with a reason* in the manifest (silent drop is
  forbidden by plan §7.1).

The tables in this module are the single place where attribute names are
special-cased; :mod:`fixture_generator` stays purely mechanical.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CLASS_ASSERTABLE = "assertable"
CLASS_VISUAL = "visual"
CLASS_UNTESTABLE = "untestable"

#: id given to the component under test in every generated layout.
TARGET_ID = "target"
#: id of the sibling view generated for view-reference attributes.
ANCHOR_ID = "anchor"

#: attribute_definitions.json platform tags -> test-runner platform names.
PLATFORM_MAP = {
    "swift": "ios",
    "kotlin": "android",
    "react": "web",
}
ALL_PLATFORMS = ("ios", "android", "web")


# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CasePlan:
    """One concrete fixture: a case name + the value written into the layout."""

    name: str
    value: Any
    written_key: str
    assertions: tuple[dict, ...] = ()
    alias_of: str | None = None  # canonical fixture id when this is an alias probe


@dataclass(frozen=True)
class AttributePlan:
    """All fixtures generated for one (section, attribute) pair."""

    section: str  # top-level key in attribute_definitions.json ("common", "Label", ...)
    attribute: str
    cls: str  # CLASS_ASSERTABLE | CLASS_VISUAL
    host: str  # component type instantiated as the target node
    cases: tuple[CasePlan, ...]
    platforms: tuple[str, ...]
    mode: str | list | None = None
    deprecated: str | list | None = None
    needs_anchor: bool = False


@dataclass(frozen=True)
class SkippedAttribute:
    """An attribute intentionally not turned into a fixture, with the reason."""

    section: str
    attribute: str
    reason: str


# --------------------------------------------------------------------------- #
# Untestable rule tables
# --------------------------------------------------------------------------- #

# Reasons are stable strings: the manifest exposes them and tests assert on them.
REASON_CALLBACK = "callback"
REASON_BINDING_ONLY = "binding-only"
REASON_METADATA = "metadata (not rendered)"
REASON_STRUCTURAL = "structural (child container attribute)"
REASON_CROSS_FILE = "cross-file reference (not expressible in a single-file fixture)"
REASON_BEHAVIORAL = "behavioral (no visual or assertable effect in v1)"
REASON_COMPOSITE = "composite value (no representative static value in v1)"
REASON_NETWORK = "network resource (v1 fixtures are offline)"
REASON_RUNTIME_DATA = "requires runtime data / cell template (v1 static fixtures only)"
REASON_DEFINITION_META = "definition metadata, not an attribute"

#: Attribute names (any section) that are pure metadata for parsers / codegen.
METADATA_ATTRS = {
    "id",
    "type",
    "generatedBy",
    "partial",
    # build directive consumed (and removed) at distribution time by
    # PlatformResolver — never reaches any renderer
    "platform",
    "propertyName",
    "binding_id",
    "binding_group",
    "tag",
    "className",
    "testId",
    "data",
    "responsive",
    "shared_data",
    "variables",
    "rect",
    "frame",
    "widthRaw",
    "heightRaw",
    "config",
}

#: Binding wiring attributes (the *mechanism*, not a bindable value).
BINDING_ATTRS = {"binding", "bind", "bindingScript"}

#: Script / event-map attributes (callback family, but not `on*`-named).
SCRIPT_ATTRS = {"scripts", "events", "valueChange"}

#: ``on``-prefixed attributes that are NOT callbacks (checked-state values).
CALLBACK_NAME_EXCEPTIONS = {"onTintColor", "onSrc"}

#: Structural child containers.
STRUCTURAL_ATTRS = {"child", "children"}

#: References to other layout / style files.
CROSS_FILE_ATTRS = {"include", "style"}

#: Behavioral attributes with no observable effect in a static screenshot
#: and no cross-platform assertion in the v1 runner vocabulary.
BEHAVIORAL_ATTRS = {
    "canTap",
    "userInteractionEnabled",
    "touchDisabledState",
    "touchEnabledViewIds",
    "keyBottomView",
    "keyTopView",
    "keyLeftView",
    "keyRightView",
    "keyboardAvoidance",
    "keyboardDismissMode",
    "scrollsToTop",
    "bounces",
    "paging",
    "decelerationRate",
    "scrollEnabled",
    "nextFocus",
    "canBack",
    "confirmationDialog",
    "momentary",
    "setTargetAsDelegate",
    "setTargetAsDataSource",
    "autoChangeTrackingId",
    "scrollTo",
    "scrollAnimated",
    "hideOnFocused",
    "includePromptWhenDataBinding",
    "contentInsetAdjustmentBehavior",
    "allowsBackForwardNavigationGestures",
    "allowsLinkPreview",
    "allowsEditingTextAttributes",
    "dataDetectorTypes",
    "maxZoom",
    "minZoom",
    "onAppear",  # also matched by the on* rule; listed for clarity
    "onDisappear",
}

#: (section, attribute) pairs that need network access at render time.
NETWORK_ATTRS = {
    ("NetworkImage", "src"),
    ("NetworkImage", "url"),
    ("NetworkImage", "headers"),
    ("NetworkImage", "cachePolicy"),
    ("NetworkImage", "timeout"),
    ("Web", "url"),
}

#: (section, attribute) pairs that need runtime data / cell templates.
RUNTIME_DATA_ATTRS = {
    ("Collection", "items"),
    ("Collection", "sections"),
    ("Collection", "cellClasses"),
    ("Collection", "headerClasses"),
    ("Collection", "footerClasses"),
    ("Collection", "cellIdProperty"),
    ("Collection", "currentPage"),
    ("SelectBox", "selectedDate"),
}

#: Whole sections excluded from the generic per-attribute sweep.
UNTESTABLE_SECTIONS = {
    "Embed": (
        "cross-file reference — attribute sweep skipped; semantic Embed "
        "fixtures (navigationMode/params + companion screens) are emitted "
        "bespoke by conformance.embed_fixtures"
    ),
}

# --------------------------------------------------------------------------- #
# Assertable rule table
# --------------------------------------------------------------------------- #

#: Components whose rendered text content is queryable through the runner's
#: ``text`` assertion on every platform.
TEXT_ASSERTABLE_COMPONENTS = {
    "Label",
    "Button",
    "TextField",
    "TextView",
    "EditText",
    "Input",
    "IconLabel",
    "Radio",
    "CheckBox",
    "Check",
}

#: Components on which the enabled/disabled assertion is meaningful.
ENABLED_ASSERTABLE_COMPONENTS = {
    "Button",
    "TextField",
    "TextView",
    "EditText",
    "Input",
    "Switch",
    "Toggle",
    "CheckBox",
    "Check",
    "SelectBox",
    "Slider",
    "Segment",
}

#: Deterministic text payload used by text fixtures + assertions.
CONFORMANCE_TEXT = "Conformance Text"

# --------------------------------------------------------------------------- #
# Representative values
# --------------------------------------------------------------------------- #

#: Attributes whose value must be a view id; a sibling anchor view is added.
VIEW_REF_ATTRS = {
    "alignTopOfView",
    "alignBottomOfView",
    "alignLeftOfView",
    "alignRightOfView",
    "alignTopView",
    "alignBottomView",
    "alignLeftView",
    "alignRightView",
    "alignCenterVerticalView",
    "alignCenterHorizontalView",
    "toView",
    "indexBelow",
    "indexAbove",
    "inView",
    "referenceView",
}

#: Attributes that reference a bundled image asset. Platform host apps
#: (plans 02/03/04) must bundle an asset with this name.
IMAGE_ASSET_NAME = "conformance_sample"
IMAGE_ATTRS = {
    "src",
    "srcName",
    "highlightSrc",
    "highlightSrcName",
    "loadingImage",
    "errorImage",
    "defaultImage",
    "image",
    "icon",
    "selectedIcon",
    "selected_icon",
    "onSrc",
    "icon_on",
    "icon_off",
    "progressImage",
    "trackImage",
    "minimumValueImage",
    "maximumValueImage",
}

#: Per-attribute value overrides (fallback table, any section).
VALUE_OVERRIDES: dict[str, Any] = {
    "width": 100,
    "height": 100,
    "minWidth": 50,
    "maxWidth": 150,
    "minHeight": 50,
    "maxHeight": 150,
    "idealWidth": 120,
    "idealHeight": 120,
    "aspectWidth": 4,
    "aspectHeight": 3,
    "weight": 1,
    "widthWeight": 1,
    "heightWeight": 1,
    "minWidthWeight": 0.25,
    "maxWidthWeight": 0.75,
    "minHeightWeight": 0.25,
    "maxHeightWeight": 0.75,
    "fontSize": 20,
    "cornerRadius": 8,
    "borderWidth": 2,
    "opacity": 0.5,
    "alpha": 0.5,
    "lines": 2,
    "minimumScaleFactor": 0.5,
    "lineHeightMultiple": 1.5,
    "font": "bold",
    "fontWeight": "bold",
    "fontFamily": "sans-serif",
    "text": CONFORMANCE_TEXT,
    "html": "<p>Conformance Sample</p>",
    "gradient": ["#FF0000", "#0000FF"],
    "locations": [0.0, 1.0],
    "systemIcon": "star",
    "maxLength": 5,
    "pattern": "[0-9]*",
    "doneText": "Done",
    "prompt": "Choose",
    "dateStringFormat": "yyyy-MM-dd",
    "minimumDate": "2020-01-01",
    "maximumDate": "2030-12-31",
    "minuteInterval": 15,
    "step": 1,
    "value": 0.5,
    "progress": 0.5,
    "minimum": 0,
    "maximum": 10,
    "minValue": 0,
    "maxValue": 10,
    "selectedIndex": 1,
    "rows": 3,
    "cols": 20,
    "columns": 2,
    "columnCount": 2,
    "size": 3,
    "shadow": "#000000|2|2|4",
    "edgeInset": [8, 8, 8, 8],
    "containerInset": 8,
    "contentSize": [200, 400],
    "contentOffset": [0, 50],
}

#: (section, attribute) overrides — beat VALUE_OVERRIDES.
VALUE_OVERRIDES_BY_SECTION: dict[tuple[str, str], Any] = {
    ("Segment", "items"): ["One", "Two"],
    ("SelectBox", "items"): ["One", "Two"],
    ("SelectBox", "selectedItem"): "Two",
    ("SelectBox", "selectedValue"): "Two",
    ("TabView", "tabs"): [{"title": "One"}, {"title": "Two"}],
    ("Collection", "insets"): [8, 8, 8, 8],
    ("Collection", "contentInsets"): [8, 8, 8, 8],
    ("common", "padding"): 8,
    ("common", "paddings"): [8, 8, 8, 8],
    ("common", "margins"): [8, 8, 8, 8],
}

#: Text-ish string attributes that read better with a hint payload.
HINT_ATTRS = {"hint", "placeholder"}
HINT_TEXT = "Conformance Hint"

#: Fallback representative values by scalar type.
DEFAULT_NUMBER = 8
DEFAULT_STRING = "sample"
DEFAULT_COLOR = "#FF0000"

# --------------------------------------------------------------------------- #
# Host component / base attribute tables
# --------------------------------------------------------------------------- #

#: Base attributes merged into the target node so it renders something
#: meaningful (text content, sizes, required attrs...). The attribute under
#: test overrides its base entry when the keys collide.
BASE_ATTRS: dict[str, dict[str, Any]] = {
    "View": {"width": 200, "height": 200, "background": "#DDDDDD"},
    "SafeAreaView": {"width": "matchParent", "height": "matchParent", "background": "#DDDDDD"},
    "ScrollView": {"width": 200, "height": 200, "background": "#DDDDDD"},
    "CircleView": {"width": 100, "height": 100, "background": "#DDDDDD"},
    "GradientView": {"width": 100, "height": 100, "gradient": ["#FF0000", "#0000FF"]},
    "Blur": {"width": 100, "height": 100},
    "Collection": {"width": 200, "height": 200, "background": "#DDDDDD"},
    "TabView": {"width": "matchParent", "height": "matchParent", "tabs": [{"title": "One"}, {"title": "Two"}]},
    "Label": {"text": "Sample"},
    "IconLabel": {"text": "Sample"},
    "Button": {"text": "Sample"},
    "TextField": {"hint": "Sample", "width": 200},
    "TextView": {"hint": "Sample", "width": 200, "height": 100},
    "EditText": {"hint": "Sample", "width": 200},
    "Input": {"hint": "Sample", "width": 200},
    "Radio": {"text": "Sample"},
    "CheckBox": {"text": "Sample"},
    "Check": {"text": "Sample"},
    "Segment": {"items": ["One", "Two"]},
    "SelectBox": {"items": ["One", "Two"], "width": 200},
    "Slider": {"width": 200},
    "Progress": {"width": 200},
    "Image": {"src": IMAGE_ASSET_NAME, "width": 100, "height": 100},
    "NetworkImage": {"defaultImage": IMAGE_ASSET_NAME, "width": 100, "height": 100},
    "Web": {"html": "<p>Sample</p>", "width": 200, "height": 200},
}

#: Children injected into container hosts so layout attributes are observable.
BASE_CHILDREN: dict[str, list[dict[str, Any]]] = {
    "View": [
        {"type": "View", "id": "box_a", "width": 40, "height": 40, "background": "#FF0000"},
        {"type": "View", "id": "box_b", "width": 40, "height": 40, "background": "#0000FF"},
    ],
    "SafeAreaView": [
        {"type": "View", "id": "box_a", "width": 40, "height": 40, "background": "#FF0000"},
    ],
    "ScrollView": [
        {"type": "View", "id": "content", "width": 150, "height": 600, "background": "#FF0000"},
    ],
    "CircleView": [],
    "Collection": [],
    "TabView": [],
}

#: Hosts for ``common`` attributes that only make sense on an interactive
#: component. Default host for common attributes is ``View``.
COMMON_HOST_OVERRIDES: dict[str, str] = {
    "enabled": "Button",
    "tapBackground": "Button",
    "highlightBackground": "Button",
    "disabledBackground": "Button",
    "defaultBackground": "Button",
}
DEFAULT_COMMON_HOST = "View"


# --------------------------------------------------------------------------- #
# Type normalization
# --------------------------------------------------------------------------- #


def normalize_type(defn: dict) -> tuple[set[str], list[Any]]:
    """Return ``(base_types, enum_values)`` for one attribute definition.

    ``type`` may be a string, or a list mixing strings and ``{"enum": [...]}``
    objects (e.g. ``width``). A sibling ``enum`` key contributes values too.
    """
    base_types: set[str] = set()
    enum_values: list[Any] = []

    raw = defn.get("type")
    entries = raw if isinstance(raw, list) else [raw]
    for entry in entries:
        if isinstance(entry, str):
            base_types.add(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("enum"), list):
            enum_values.extend(entry["enum"])

    sibling = defn.get("enum")
    if isinstance(sibling, list):
        for v in sibling:
            if v not in enum_values:
                enum_values.append(v)

    return base_types, enum_values


def _slugify(value: Any) -> str:
    """Filesystem-safe, lowercase case-name for an enum value."""
    text = str(value)
    safe = "".join(c if c.isalnum() or c in "_-" else "-" for c in text)
    return safe.lower() or "empty"


def dedupe_case_names(values: list[Any]) -> list[tuple[str, Any]]:
    """Assign unique, case-insensitively distinct case names to enum values.

    macOS filesystems are case-insensitive, and several enums list both
    spellings (``Left`` / ``left``); the second occurrence gets a ``_2``
    (``_3``...) suffix in definition order — fully deterministic.
    """
    seen: dict[str, int] = {}
    out: list[tuple[str, Any]] = []
    for v in values:
        slug = _slugify(v)
        count = seen.get(slug, 0) + 1
        seen[slug] = count
        out.append((slug if count == 1 else f"{slug}_{count}", v))
    return out


# --------------------------------------------------------------------------- #
# Representative value selection
# --------------------------------------------------------------------------- #


def _clamp(value: float, defn: dict) -> Any:
    lo = defn.get("min")
    hi = defn.get("max")
    if isinstance(lo, (int, float)) and value < lo:
        value = lo
    if isinstance(hi, (int, float)) and value > hi:
        value = hi
    return value


def representative_value(section: str, attribute: str, defn: dict) -> tuple[bool, Any]:
    """Pick the single deterministic non-enum representative value.

    Returns ``(found, value)``; ``found`` is False when no static value can be
    derived (composite object/array without an override).
    """
    if (section, attribute) in VALUE_OVERRIDES_BY_SECTION:
        return True, VALUE_OVERRIDES_BY_SECTION[(section, attribute)]
    if attribute in VIEW_REF_ATTRS:
        return True, ANCHOR_ID
    if attribute in IMAGE_ATTRS:
        return True, VALUE_OVERRIDES.get(attribute, IMAGE_ASSET_NAME)
    if attribute in VALUE_OVERRIDES:
        return True, VALUE_OVERRIDES[attribute]
    if attribute in HINT_ATTRS:
        return True, HINT_TEXT

    base_types, _ = normalize_type(defn)

    if "boolean" in base_types:
        return True, True
    if "number" in base_types:
        if "default" in defn and isinstance(defn["default"], (int, float)):
            return True, defn["default"]
        return True, _clamp(DEFAULT_NUMBER, defn)
    if "color" in base_types or _is_color_name(attribute):
        return True, DEFAULT_COLOR
    if "string" in base_types:
        if isinstance(defn.get("default"), str) and defn["default"]:
            return True, defn["default"]
        return True, DEFAULT_STRING
    return False, None


def _is_color_name(attribute: str) -> bool:
    lower = attribute.lower()
    return "color" in lower or lower.endswith("background") or lower == "tint"


# --------------------------------------------------------------------------- #
# Assertion builders
# --------------------------------------------------------------------------- #


def _visible() -> dict:
    return {"assert": "visible", "id": TARGET_ID}


def _not_visible() -> dict:
    return {"assert": "notVisible", "id": TARGET_ID}


def _enabled() -> dict:
    return {"assert": "enabled", "id": TARGET_ID}


def _disabled() -> dict:
    return {"assert": "disabled", "id": TARGET_ID}


def _text_equals(expected: str) -> dict:
    return {"assert": "text", "id": TARGET_ID, "equals": expected}


def _assertable_cases(section: str, attribute: str, host: str, defn: dict) -> tuple[CasePlan, ...] | None:
    """Return assertion-bearing cases when the attribute is assertable, else None."""
    if attribute == "visibility":
        _, enum_values = normalize_type(defn)
        assert_map = {
            "visible": (_visible(),),
            "invisible": (_not_visible(),),
            "gone": (_not_visible(),),
        }
        cases = []
        for name, value in dedupe_case_names(enum_values):
            assertions = assert_map.get(str(value))
            if assertions is None:
                assertions = (_visible(),)
            cases.append(CasePlan(name=name, value=value, written_key=attribute, assertions=assertions))
        return tuple(cases)

    if attribute == "hidden":
        return (
            CasePlan(name="true", value=True, written_key=attribute, assertions=(_not_visible(),)),
            CasePlan(name="false", value=False, written_key=attribute, assertions=(_visible(),)),
        )

    if attribute == "enabled" and host in ENABLED_ASSERTABLE_COMPONENTS:
        return (
            CasePlan(name="true", value=True, written_key=attribute, assertions=(_visible(), _enabled())),
            CasePlan(name="false", value=False, written_key=attribute, assertions=(_visible(), _disabled())),
        )

    if attribute == "text" and host in TEXT_ASSERTABLE_COMPONENTS:
        return (
            CasePlan(
                name="static",
                value=CONFORMANCE_TEXT,
                written_key=attribute,
                assertions=(_visible(), _text_equals(CONFORMANCE_TEXT)),
            ),
        )

    return None


# --------------------------------------------------------------------------- #
# Main entry: plan one attribute
# --------------------------------------------------------------------------- #


def _untestable_reason(section: str, attribute: str, defn: dict) -> str | None:
    """Return the skip reason for untestable attributes, or None."""
    if attribute.startswith("_"):
        return REASON_DEFINITION_META
    if section in UNTESTABLE_SECTIONS:
        return UNTESTABLE_SECTIONS[section]

    base_types, enum_values = normalize_type(defn)

    if "callback" in base_types:
        return REASON_CALLBACK
    if attribute in SCRIPT_ATTRS:
        return REASON_CALLBACK
    if (
        len(attribute) > 2
        and attribute.startswith("on")
        and attribute[2].isupper()
        and attribute not in CALLBACK_NAME_EXCEPTIONS
    ):
        return REASON_CALLBACK
    if attribute == "onclick":
        return REASON_CALLBACK
    if attribute in BINDING_ATTRS:
        return REASON_BINDING_ONLY
    if base_types == {"binding"}:
        return REASON_BINDING_ONLY
    if attribute in METADATA_ATTRS or attribute.startswith("$"):
        # $-prefixed names are harness/normalizer markers (e.g. $jui).
        return REASON_METADATA
    if attribute in STRUCTURAL_ATTRS:
        return REASON_STRUCTURAL
    if attribute in CROSS_FILE_ATTRS:
        return REASON_CROSS_FILE
    if attribute in BEHAVIORAL_ATTRS:
        return REASON_BEHAVIORAL
    if (section, attribute) in NETWORK_ATTRS:
        return REASON_NETWORK
    if (section, attribute) in RUNTIME_DATA_ATTRS:
        return REASON_RUNTIME_DATA
    return None


def _platforms(defn: dict) -> tuple[str, ...]:
    raw = defn.get("platform")
    if raw is None:
        return ALL_PLATFORMS
    tags = raw if isinstance(raw, list) else [raw]
    mapped = [PLATFORM_MAP[t] for t in tags if t in PLATFORM_MAP]
    # Preserve the canonical ios/android/web order.
    ordered = tuple(p for p in ALL_PLATFORMS if p in mapped)
    return ordered or ALL_PLATFORMS


def host_for(section: str, attribute: str) -> str:
    """Component type used as the target node for a fixture."""
    if section == "common":
        return COMMON_HOST_OVERRIDES.get(attribute, DEFAULT_COMMON_HOST)
    return section


def plan_attribute(
    section: str, attribute: str, defn: Any
) -> AttributePlan | SkippedAttribute:
    """Classify one attribute and produce its fixture plan (or a skip record)."""
    if not isinstance(defn, dict):
        return SkippedAttribute(section, attribute, REASON_DEFINITION_META)

    reason = _untestable_reason(section, attribute, defn)
    if reason is not None:
        return SkippedAttribute(section, attribute, reason)

    host = host_for(section, attribute)
    needs_anchor = attribute in VIEW_REF_ATTRS

    assertable = _assertable_cases(section, attribute, host, defn)
    if assertable is not None:
        cases = list(assertable)
        cls = CLASS_ASSERTABLE
    else:
        cases = _visual_cases(section, attribute, defn)
        if not cases:
            return SkippedAttribute(section, attribute, REASON_COMPOSITE)
        cls = CLASS_VISUAL

    cases = _with_alias_cases(section, attribute, defn, cases)

    return AttributePlan(
        section=section,
        attribute=attribute,
        cls=cls,
        host=host,
        cases=tuple(cases),
        platforms=_platforms(defn),
        mode=defn.get("mode"),
        deprecated=defn.get("deprecated"),
        needs_anchor=needs_anchor,
    )


def _visual_cases(section: str, attribute: str, defn: dict) -> list[CasePlan]:
    """Enum values expand into one case each; scalars get a single case."""
    base_types, enum_values = normalize_type(defn)
    cases: list[CasePlan] = []

    for name, value in dedupe_case_names(enum_values):
        cases.append(CasePlan(name=name, value=value, written_key=attribute))

    if enum_values and not ({"number", "boolean"} & base_types):
        # Enum fully covers string-typed attributes.
        return cases

    found, value = representative_value(section, attribute, defn)
    if found:
        if isinstance(value, bool):
            cases.append(CasePlan(name="true", value=True, written_key=attribute))
        else:
            cases.append(CasePlan(name="static", value=value, written_key=attribute))
    return cases


def _with_alias_cases(
    section: str, attribute: str, defn: dict, cases: list[CasePlan]
) -> list[CasePlan]:
    """Append one alias fixture per alias, mirroring the first canonical case.

    Writing the same value under the alias key and expecting the identical
    result is the regression probe for pillar B/C alias resolution.
    """
    aliases = defn.get("aliases")
    if not isinstance(aliases, list) or not cases:
        return cases
    first = cases[0]
    canonical_id = f"{section}/{attribute}__{first.name}"
    for alias in aliases:
        cases.append(
            CasePlan(
                name=f"alias_{alias}",
                value=first.value,
                written_key=str(alias),
                assertions=first.assertions,
                alias_of=canonical_id,
            )
        )
    return cases
