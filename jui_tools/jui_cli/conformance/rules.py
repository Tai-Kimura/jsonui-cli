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
REASON_COMPONENT_ALIAS = "component alias (fixtures live on the canonical section)"

#: Attribute names (any section) that are pure metadata for parsers / codegen.
METADATA_ATTRS = {
    "id",
    "type",
    "generatedBy",
    "partial",
    # build directive consumed (and removed) at distribution time by
    # PlatformResolver — never reaches any renderer
    "platform",
    # layout-root screen classification, read by the screen-identity
    # resolver at build time — never reaches any renderer
    "role",
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
    # A container's disabled state is observable through the a11y tree —
    # `aria-disabled` on web, the `Disabled` semantics on Compose, SwiftUI's
    # `.disabled` on iOS. It was left out while the three codegens ignored
    # `enabled` on a View, which is the same reason the fixture was hosted on a
    # Button and the gap stayed invisible.
    "View",
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

#: Attributes whose entire effect is OFF the screen, so no screenshot can
#: show it. They configure the soft keyboard / IME, which is not part of the
#: captured frame (and does not exist at all in a headless browser).
#:
#: They still get fixtures — a converter that crashes or drops the key is worth
#: catching — but the fixture-vs-control check must not count them as
#: "identical to control, investigate". Without this they were the single
#: largest block of inert results on web (39 of 235) and pure noise.
NON_OBSERVABLE_ATTRS = {
    "returnKeyType",
    "input",
    "inputType",
    "keyboardType",
    "autocapitalizationType",
    "autocorrectionType",
    "autocapitalize",
    "enterKeyHint",
    "nextFocus",
}


#: Attributes that reference a bundled image asset. Platform host apps
#: (plans 02/03/04) must bundle an asset with this name.
IMAGE_ASSET_NAME = "conformance_sample"

#: Distinct second asset for STATE images (NetworkImage placeholder/hint/
#: loadingImage/errorImage). The control's base carries defaultImage with
#: the primary asset; giving state images the same asset made every state
#: transition unobservable — a hijacked no-src state rendered pixel-
#: identical to the correct one. Hosts must bundle this asset too.
IMAGE_ALT_ASSET_NAME = "conformance_sample_alt"
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
    # The UIKit pipe contract is exactly five fields
    # ('color|offsetX|offsetY|opacity|radius') — a four-field string is
    # invalid and draws nothing on every path.
    "shadow": "#000000|2|2|0.5|4",
    "edgeInset": [8, 8, 8, 8],
    "containerInset": 8,
    "contentSize": [200, 400],
    "contentOffset": [0, 50],
}

#: (section, attribute) overrides — beat VALUE_OVERRIDES.
VALUE_OVERRIDES_BY_SECTION: dict[tuple[str, str], Any] = {
    # The canonical shadow object (UIKit SJUILabel contract) — a generic
    # string value renders as invalid CSS on web and nothing anywhere, so
    # the fixture could never differ from its control.
    ("Label", "textShadow"): {"color": "#000000", "blur": 4, "offset": [2, 2]},
    ("IconLabel", "textShadow"): {"color": "#000000", "blur": 4, "offset": [2, 2]},
    ("Segment", "items"): ["One", "Two"],
    ("SelectBox", "items"): ["One", "Two"],
    # NetworkImage's hint is its PLACEHOLDER IMAGE NAME (SSoT: "Placeholder
    # image name (primary)"), not user-facing text — the generic hint text
    # produced painterResource(R.drawable.conformance_hint) on Compose, a
    # resource that cannot exist. State images get the DISTINCT alt asset:
    # the control's defaultImage uses the primary one, so a state image
    # hijacking the no-src display renders visibly different instead of
    # pixel-identical (canonical networkImage.noSrc = defaultImage).
    ("NetworkImage", "hint"): IMAGE_ALT_ASSET_NAME,
    ("NetworkImage", "placeholder"): IMAGE_ALT_ASSET_NAME,
    ("NetworkImage", "loadingImage"): IMAGE_ALT_ASSET_NAME,
    ("NetworkImage", "errorImage"): IMAGE_ALT_ASSET_NAME,
    # Selected-state icons swap against the base icon — same distinct-asset
    # rule as the NetworkImage state images.
    ("CheckBox", "selectedIcon"): IMAGE_ALT_ASSET_NAME,
    ("Radio", "selectedIcon"): IMAGE_ALT_ASSET_NAME,
    ("Radio", "selected_icon"): IMAGE_ALT_ASSET_NAME,
    # srcName overrides the base src — with the same asset the override is
    # unobservable; label overrides text the same way.
    ("Image", "srcName"): IMAGE_ALT_ASSET_NAME,
    ("CheckBox", "label"): "Alt label",
    # 8 equals the cross-platform default gap — indistinguishable from the
    # control on any platform that implements it.
    ("IconLabel", "iconMargin"): 16,
    # `value` is Slider/Progress vocabulary in the name-keyed fallback table
    # (0.5), but Switch declares it as its boolean state alias — 0.5 is not a
    # boolean, the Compose codegen host cannot even compile it
    # (`checked = 0.5`), and a non-boolean state fixture can never assert the
    # attribute it exists for.
    ("Switch", "value"): True,
    ("SelectBox", "selectedItem"): "Two",
    ("SelectBox", "selectedValue"): "Two",
    ("TabView", "tabs"): [{"title": "One"}, {"title": "Two"}],
    ("Collection", "insets"): [8, 8, 8, 8],
    ("Collection", "contentInsets"): [8, 8, 8, 8],
    ("common", "padding"): 8,
    ("common", "paddings"): [8, 8, 8, 8],
    ("common", "margins"): [8, 8, 8, 8],
    # Every declared key. `lineHeightMultiple` and `textAlign` were left out
    # while SJUILabel's creator still shared the BASE paragraph style with the
    # highlight dictionary and so ignored both; it builds its own copy now, and
    # Compose and web implement the swap too, so all four surfaces agree and the
    # fixture can assert the whole set.
    ("Label", "highlightAttributes"): {
        "font": "bold",
        "fontSize": 24,
        "fontColor": "#FF0000",
        "lineHeightMultiple": 1.5,
        "textAlign": "Center",
    },
    # `sample` is not a mode, and the converter refuses to guess one from an
    # unrecognised value, so the default string would render nothing. `always`
    # is the one mode a static screenshot can show — the editing-sensitive modes
    # need focus.
    ("TextField", "clearButtonMode"): "always",
    # Skipped as "no representative static value" until web implemented it.
    # NOTE the fixture cannot show a visual difference on web: `env(safe-area-
    # inset-*)` resolves to 0 in a headless desktop browser, so the padding is
    # zero and the screenshot matches its control. It still proves the emit, and
    # on iOS/Android the inset is real.
    ("SafeAreaView", "safeAreaInsetPositions"): ["top", "bottom"],
    ("View", "safeAreaInsetPositions"): ["top", "bottom"],
    # Skipped as "no representative static value" until web implemented it. The
    # four keys here are the ones that move pixels on a closed select, which is
    # what the label is.
    ("SelectBox", "labelAttributes"): {
        "font": "bold",
        "fontSize": 24,
        "fontColor": "#FF0000",
        "textAlign": "Center",
    },
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
    # Collections render their declared cells (F4 Phase 2): without them a
    # bare container is all any layout attribute (columns, itemSpacing,
    # insets...) has to act on, and every such fixture renders identically.
    # The cell view name doubles as the layout FILE stem — iOS dynamic loads
    # it verbatim, Android dynamic snake_cases it (identity here), the three
    # codegens PascalCase it — so it must stay snake_case. Item data arrives
    # through the layout root `data` section (BASE_DATA below), the one
    # channel all four render paths share (INTERACTIVE_HOST_CONTRACT.md §4).
    "Collection": {
        "width": 200,
        "height": 200,
        "background": "#DDDDDD",
        "sections": [{"cell": "conformance_cell"}],
        "items": "@{items}",
    },
    "TabView": {"width": "matchParent", "height": "matchParent", "tabs": [{"title": "One"}, {"title": "Two"}]},
    # An explicit width wider than the text is what makes `textAlign` /
    # `gravity` observable. On wrapContent these hosts are exactly as wide as
    # their content, so every alignment value renders the same pixels and the
    # fixture cannot tell a working implementation from a dropped attribute.
    "Label": {"text": "Sample", "width": 200},
    "IconLabel": {"text": "Sample", "width": 200},
    "Button": {"text": "Sample", "width": 200},
    "TextField": {"hint": "Sample", "width": 200},
    "TextView": {"hint": "Sample", "width": 200, "height": 100},
    "EditText": {"hint": "Sample", "width": 200},
    "Input": {"hint": "Sample", "width": 200},
    "Radio": {"text": "Sample", "width": 200},
    "CheckBox": {"text": "Sample", "width": 200},
    "Check": {"text": "Sample", "width": 200},
    "Segment": {"items": ["One", "Two"], "width": 200},
    "SelectBox": {"items": ["One", "Two"], "width": 200},
    "Slider": {"width": 200},
    "Progress": {"width": 200},
    # Deliberately NOT square: the bundled asset is 96x96, so in a square box
    # fit / fill / aspectFit / aspectFill / center all render the same image and
    # `contentMode` is untestable. A 140x80 box makes each mode distinguishable.
    "Image": {"src": IMAGE_ASSET_NAME, "width": 140, "height": 80},
    "NetworkImage": {"defaultImage": IMAGE_ASSET_NAME, "width": 140, "height": 80},
    "Web": {"html": "<p>Sample</p>", "width": 200, "height": 200},
}

#: Extra base attributes for specific attributes, so the fixture gives the
#: attribute under test something to act on.
#:
#: A View with no `orientation` is an OVERLAY: the converters stack children on
#: top of each other (web emits `relative` + `absolute inset-0`). Nothing that
#: depends on flow — wrapping, distribution, gravity, padding reflow, child
#: order — can be observed in that mode, and the fixture-vs-control check
#: measured exactly that: `flexWrap`, `distribution`, `gravity` and `padding`
#: all rendered pixel-identical to a fixture without them.
#:
#: Overlay mode is worth testing, but not by the fixture for a flow attribute.
BASE_ATTRS_BY_ATTRIBUTE: dict[str, dict[str, Any]] = {
    # Text-styling attributes need TEXT to style: the TextField/TextView base
    # is hint-only, so font/fontColor/... rendered nothing to look at and the
    # 33 cross-effect sweep measured platform-dependent placeholder
    # inheritance instead of the attribute (fixture-observability family).
    "TextView.font": {"text": "Sample"},
    "TextView.fontColor": {"text": "Sample"},
    "TextView.fontFamily": {"text": "Sample"},
    "TextView.fontSize": {"text": "Sample"},
    "TextField.font": {"text": "Sample"},
    "TextField.fontColor": {"text": "Sample"},
    "TextField.fontFamily": {"text": "Sample"},
    # iconPosition/iconMargin need an ICON to position (base is text-only).
    "IconLabel.iconPosition": {"icon_off": IMAGE_ASSET_NAME},
    "IconLabel.iconMargin": {"icon_off": IMAGE_ASSET_NAME},
    # Checked-state skins need the checked state to exist, and a BASE icon
    # distinct from the selected one — with a single asset the state swap
    # renders identically whichever image wins (33: single-asset
    # unobservability, the NetworkImage alt-asset precedent).
    "CheckBox.selectedIcon": {"checked": True, "icon": IMAGE_ASSET_NAME},
    # Radio.icon is 2P-scoped while selected_icon is 3P — the checked
    # state alone makes the swap observable (ALT image vs default glyph).
    "Radio.selectedIcon": {"checked": True},
    "Radio.selected_icon": {"checked": True},
    "CheckBox.checkedColor": {"checked": True},
    "Radio.checkedColor": {"checked": True},
    # onTintColor colors the ON track — the switch must be on to show it.
    "Switch.onTintColor": {"isOn": True},
    # Track/progress tints need a nonzero value or there is nothing to
    # paint (a zero-length active track is invisible on every platform).
    "Slider.tintColor": {"value": 0.5},
    "Progress.tintColor": {"value": 0.5},
    "Progress.progressTintColor": {"value": 0.5},
    "Progress.trackTintColor": {"value": 0.5},
    # Flow attributes need a flex container. `horizontal` is the direction that
    # makes wrapping visible with the standard 6-box child set (240px of boxes
    # in a 200px host).
    "flexWrap": {"orientation": "horizontal"},
    "distribution": {"orientation": "horizontal"},
    "gravity": {"orientation": "horizontal"},
    "spacing": {"orientation": "horizontal"},
    "padding": {"orientation": "horizontal"},
    "paddings": {"orientation": "horizontal"},
    "paddingTop": {"orientation": "horizontal"},
    "paddingBottom": {"orientation": "horizontal"},
    "paddingLeft": {"orientation": "horizontal"},
    "paddingRight": {"orientation": "horizontal"},
    "paddingStart": {"orientation": "horizontal"},
    "paddingEnd": {"orientation": "horizontal"},
    # `direction` reverses the children of an ORIENTED container; with no
    # orientation the canonical answer is "no effect", so the fixture has to
    # supply one or it can never show anything.
    "direction": {"orientation": "vertical"},
    # The highlight attribute sets only take effect while the label is
    # selected — that is the whole contract (UIKit: `selected ?
    # highlightAttributes : attributes`). Without this the fixture renders its
    # base styling, matches the control exactly, and reads as inert.
    #
    # Scoped to Label on purpose: Button declares `highlightColor` too but has
    # no `selected`, and its highlight is a press state that a static
    # screenshot cannot show anyway.
    "Label.highlightAttributes": {"selected": True},
    "Label.highlightColor": {"selected": True},
    # UIKit hides the clear button while the field is empty — there is nothing
    # to clear — so an empty fixture field renders no button at all.
    "TextField.clearButtonMode": {"text": "Clear me"},
    # The date-picker attributes only reach their code path when the SelectBox
    # IS a date picker; without this the fixture renders the ordinary
    # options list and the attribute is never consulted.
    "SelectBox.datePickerStyle": {"selectItemType": "Date"},
    "SelectBox.dateStringFormat": {"selectItemType": "Date"},
    # minuteInterval is a step through minutes, so it needs a time-bearing mode.
    "SelectBox.minuteInterval": {"selectItemType": "Date", "datePickerMode": "time"},
    # The ON-state colours are invisible on an off switch, so the fixture
    # rendered pixel-identical to its control and read as inert.
    "Switch.tint": {"isOn": True},
    "Switch.tintColor": {"isOn": True},
    "Switch.onTintColor": {"isOn": True},
    "Toggle.tint": {"isOn": True},
    "Toggle.tintColor": {"isOn": True},
    "Toggle.onTintColor": {"isOn": True},
    # systemIcon is a BOOLEAN ("interpret `src` as an SF Symbol name") — the
    # fixture needs `src` to actually be one, or the reinterpretation renders
    # a missing symbol. The old string-valued fixture ("systemIcon": "star")
    # was invalid input: the dynamic decoder fail-louded on it while codegen
    # silently ignored it, which is a fixture bug, not a parity signal.
    "Image.systemIcon": {"src": "star"},
}


def base_attrs_for(host: str, attribute: str) -> dict[str, Any]:
    """Extra base attributes that make `attribute` observable on `host`.

    Keys are either scoped to a component (`Label.highlightColor`) or apply to
    the attribute wherever it appears (`flexWrap`); scoped wins. The scoping
    matters when two components share an attribute name and only one has the
    driver — injecting `selected` into a Button fixture would put an attribute
    Button does not declare into the layout.
    """
    scoped = BASE_ATTRS_BY_ATTRIBUTE.get(f"{host}.{attribute}")
    if scoped is not None:
        return scoped
    return BASE_ATTRS_BY_ATTRIBUTE.get(attribute, {})


#: Children injected into container hosts so layout attributes are observable.
BASE_CHILDREN: dict[str, list[dict[str, Any]]] = {
    # Six 40px boxes total 240px inside a 200px host, i.e. they OVERFLOW one
    # row. Two boxes fitted comfortably, which left `flexWrap` nothing to wrap,
    # `distribution` no free space to distribute, and `padding` no reflow to
    # cause — all three rendered pixel-identical to a fixture without them.
    "View": [
        {"type": "View", "id": "box_a", "width": 40, "height": 40, "background": "#FF0000"},
        {"type": "View", "id": "box_b", "width": 40, "height": 40, "background": "#0000FF"},
        {"type": "View", "id": "box_c", "width": 40, "height": 40, "background": "#00AA00"},
        {"type": "View", "id": "box_d", "width": 40, "height": 40, "background": "#FFAA00"},
        {"type": "View", "id": "box_e", "width": 40, "height": 40, "background": "#AA00AA"},
        {"type": "View", "id": "box_f", "width": 40, "height": 40, "background": "#00AAAA"},
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

# --------------------------------------------------------------------------- #
# Collection cell supply (F4 Phase 2 — INTERACTIVE_HOST_CONTRACT.md §4)
# --------------------------------------------------------------------------- #

#: Layout root ``data`` section entries injected per host. The shorthand
#: CollectionDataSource shape (bare cell array = one section) pairs with the
#: ``sections``/``items`` base attrs above; each render path materializes it
#: through its own production channel (generated Data-class defaults on the
#: codegen paths, host-side materialization on the dynamic paths).
BASE_DATA: dict[str, list[dict[str, Any]]] = {
    "Collection": [
        {
            "name": "items",
            "class": "CollectionDataSource",
            "defaultValue": [
                {"title": "Alpha"},
                {"title": "Beta"},
                {"title": "Gamma"},
            ],
        },
    ],
}

#: Companion layouts (conformance-root-relative) recorded on every manifest
#: entry whose host needs them. Companions ride the SAME distribution channel
#: as the Embed screens: each host mirrors every manifest ``companions`` path
#: into the directory its production loader reads (assets/Layouts on Android,
#: Resources/Layouts on iOS, Layouts/pages on web) under the bare file name.
BASE_COMPANIONS: dict[str, list[str]] = {
    "Collection": ["fixtures/Collection/__cells/conformance_cell.layout.json"],
}

#: Companion layout payloads the generator writes once per run, keyed by
#: their conformance-root-relative path. Fixed 60x28 cells keep grid effects
#: (columns, spacing, insets) visible inside the 200x200 host without the
#: infinite-constraint edge cases a matchParent cell hits in horizontal and
#: flow layouts.
#:
#: The ``data`` section is load-bearing: kjui/sjui Data generation derives
#: properties from it ONLY (no binding inference), so without it the
#: generated cell view reads ``data.title`` off a Data class that has no
#: such property and the codegen host does not compile. rjui and the
#: dynamic renderers infer/resolve the binding either way; the declared
#: empty default is overridden by each rendered cell's data.
SUPPORT_LAYOUTS: dict[str, dict[str, Any]] = {
    "fixtures/Collection/__cells/conformance_cell.layout.json": {
        "type": "View",
        "id": "cell_root",
        "width": 60,
        "height": 28,
        "background": "#3366CC",
        "data": [
            {"name": "title", "class": "String", "defaultValue": ""}
        ],
        "child": [
            {
                "type": "Label",
                "id": "cell_title",
                "text": "@{title}",
                "fontSize": 11,
                "fontColor": "#FFFFFF",
                "padding": 4,
            }
        ],
    },
}

#: Hosts for ``common`` attributes that only make sense on an interactive
#: component. Default host for common attributes is ``View``.
#:
#: `enabled` is deliberately NOT here. It used to be hosted on Button, on the
#: assumption that only an interactive component can be disabled — but a View
#: with an onClick is interactive, and hosting the fixture on a Button is what
#: hid the fact that `enabled` did nothing on a View: the Button emits a real
#: `disabled` attribute, so the fixture passed while three codegens ignored the
#: attribute on every container. The View host asserts through the a11y tree
#: (`aria-disabled` on web, the `Disabled` semantics on Compose), which is the
#: only thing a UI test can observe on a non-input element.
COMMON_HOST_OVERRIDES: dict[str, str] = {
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


#: `mode` tag -> the platforms an attribute is VALID on.
#:
#: Not the same mapping as `coverage.MODE_TAGS`, which answers "whose Ruby
#: converter must read this" and maps `uikit` to nothing because UIKit applies
#: attributes in the Swift runtime with no Ruby codegen involved. A UIKit
#: attribute is still legal in an iOS layout, so a fixture for it belongs on
#: iOS — and nowhere else.
MODE_PLATFORM_MAP: dict[str, set[str]] = {
    "uikit": {"ios"},
    "swiftui": {"ios"},
    "compose": {"android"},
    "react": {"web"},
}


def _platforms(defn: dict) -> tuple[str, ...]:
    """Platforms a fixture for this attribute should run on.

    Honours `mode` as well as `platform`. Ignoring `mode` gave every
    Compose-only attribute a three-platform fixture: `Collection.reverseLayout`
    and `View.onAppear` were rendered on iOS and web, where the attribute is not
    declared at all, so the layout was invalid there and the screenshot could
    only ever match its control.
    """
    scope: set[str] | None = None

    raw = defn.get("platform")
    if raw is not None:
        tags = raw if isinstance(raw, list) else [raw]
        unknown = [t for t in tags if t not in PLATFORM_MAP]
        if unknown:
            # A silently-dropped token either shrinks the declared surface
            # (partial typo) or WIDENS it to all platforms (all tokens
            # unknown -> scope None). Both corrupt the coverage universe
            # without a trace — writing "web" instead of "react" did exactly
            # that. Fail loudly instead.
            raise ValueError(
                f"unknown platform token(s) {unknown!r} in attribute "
                f"definition (known: {sorted(PLATFORM_MAP)})"
            )
        mapped = {PLATFORM_MAP[t] for t in tags}
        scope = mapped or None

    raw_mode = defn.get("mode")
    if raw_mode is not None:
        tags = raw_mode if isinstance(raw_mode, list) else [raw_mode]
        mode_scope: set[str] = set()
        for tag in tags:
            # An unknown or deliberately broad tag (`dynamic-only`) does not
            # narrow: it says how the attribute is applied, not where.
            mode_scope |= MODE_PLATFORM_MAP.get(tag, set(ALL_PLATFORMS))
        scope = mode_scope if scope is None else (scope & mode_scope)

    if scope is None:
        return ALL_PLATFORMS
    # Preserve the canonical ios/android/web order.
    ordered = tuple(p for p in ALL_PLATFORMS if p in scope)
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
