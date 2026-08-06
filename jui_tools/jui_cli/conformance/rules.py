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

import re
from dataclasses import dataclass, field
from typing import Any

CLASS_ASSERTABLE = "assertable"
CLASS_VISUAL = "visual"
CLASS_UNTESTABLE = "untestable"
#: Generated, loaded and compiled — but deliberately not photographed.
#:
#: See :func:`is_uikit_only`. A fixture in this class still proves its
#: declaration is legal and that the host renders the screen without falling
#: over; it makes no claim about pixels, so it carries no control and takes no
#: screenshot, and it is not counted as visual coverage.
CLASS_DECLARATION_ONLY = "declaration-only"

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
    # contentType is the autofill HINT: iOS sets `.textContentType`, web sets
    # the `autoComplete` attribute, Android picks a keyboard variant. None of
    # the three puts a pixel in the captured frame, so every one of its 39
    # enum fixtures would be counted as "identical to control, investigate" —
    # the same false-positive block 34 cleared on web (39 of 235).
    "contentType",
    # --- lane A §5(3), the six A named explicitly ------------------------- #
    # Validation and semantics that live in the DOM/a11y layer, never in the
    # frame: the submit/reset role of a button, an image's alt text, an input's
    # length cap and validation pattern and required flag, a view's drag
    # affordance. The codegen probe still measures every one of them — this
    # only stops the SCREENSHOT check from filing "identical to its control"
    # against something a camera cannot see.
    "buttonType",
    "alt",
    "maxLength",
    "pattern",
    "required",
    "draggable",
    # --- lane F family-B group A1, the ones that hold on every host --------- #
    # A press-state background, with no press in a still capture.
    "tapBackground",
    # Scroll indicators fade out when the view is idle, which is exactly when
    # the screenshot is taken.
    "showsVerticalScrollIndicator",
}

#: Same contract as :data:`NON_OBSERVABLE_ATTRS`, but scoped to one component.
#:
#: Needed because most of these names ARE observable somewhere else:
#: `Slider.tintColor` paints a track, `Switch.value` is a checked state,
#: `Segment.items` are the visible tabs. Only the listed pairing is off-frame.
#:
#: Source: lane F's family-B read (46/46), group A1 — "a static screenshot
#: cannot photograph this", as distinct from "the fixture is shaped wrong".
#: Changing the fixture does not help, and re-measuring does not either; what
#: was missing was the ledger entry.
NON_OBSERVABLE_BY_SECTION: set[tuple[str, str]] = {
    # Press states. The capture is taken at rest, with no finger on the screen.
    ("Button", "highlightColor"),
    # tint IS the caret, and an unfocused field has no caret.
    ("TextField", "tintColor"),
    # --- lane A §5(3), the six `is_non_observable()` did not already cover -- #
    # A ran the predicate over all 22 rather than reading the tables, and 15
    # were already registered.
    #
    # `highlightBackground` is SECTION-scoped on purpose, and this is the whole
    # reason the scoped table exists: paired with `highlighted: true` it paints
    # in the resting state and photographs perfectly well — A fixed exactly
    # that emit in §5(1). A bare name here would switch off `View.highlighted`,
    # which is a fixture that works.
    #
    # `tapBackground` stays bare by contrast: nothing declares a `tapped`
    # state, so it only ever reaches the `active:` path and is unreachable in a
    # still capture on every host.
    ("Button", "highlightBackground"),
    ("common", "highlightBackground"),
    # The old spelling of Button.highlightColor, same press state.
    ("Button", "hilightColor"),
    # A fetch hint the browser acts on; no pixels either way.
    ("Image", "loading"),
    ("NetworkImage", "loading"),
    # The iframe permission policy.
    ("Web", "allow"),
    # A radio's group is the mutual-exclusion key and its value is what gets
    # submitted. Neither draws. (`CheckBox.value` / `Switch.value` DO — they
    # are the checked state — which is why this is scoped.)
    ("Radio", "group"),
    ("Radio", "value"),
    # Everything below is inside the picker SHEET; the fixture photographs the
    # closed control. `items` additionally only reaches the closed label
    # through `initialSelectedIndex`, which the fixture does not declare, and
    # both `selectItemType` faces render their initial empty string.
    ("SelectBox", "items"),
    ("SelectBox", "selectItemType"),
    ("SelectBox", "datePickerStyle"),
    ("SelectBox", "minuteInterval"),
    ("SelectBox", "dateStringFormat"),
    # An in-flight image exists for the length of a request. A still capture
    # has no duration, so the loading face cannot be photographed however the
    # fixture is shaped — the request either has not started or has already
    # failed by the time the shutter opens. The ERROR face is a resting state
    # and stays photographed; only this one is timing.
    #
    # Deliberately here and not in UNSHAPEABLE_FIXTURES: that table is for what
    # the generator cannot build yet, and this fixture builds fine. The codegen
    # probe still measures it — measured reading the spelling on both mobile
    # converters — which is exactly the split this table is for.
    ("NetworkImage", "loadingImage"),
}


def is_non_observable(section: str, attribute: str) -> bool:
    """True when no static capture can show this attribute, at any value."""
    return (
        attribute in NON_OBSERVABLE_ATTRS
        or (section, attribute) in NON_OBSERVABLE_BY_SECTION
    )


#: Required pixel size of every bundled conformance asset, on every host.
#:
#: The contract used to name the assets and say nothing about their size, and
#: the three hosts drifted: ios 64x64, web 96x96, android 128x128 (measured
#: 2026-08-05). Size is not cosmetic here — it decides whether `contentMode` is
#: measurable at all. Against the 140x80 Image frame:
#:
#:   64   fits INSIDE the frame, so top / center / bottom can only move 8pt
#:        apart and the position values are nearly indistinguishable
#:   96   overflows vertically, so each position crops different content
#:   128  overflows further, same effect
#:
#: 96 is the smallest size that overflows, and `conformance_sample_alt` is
#: already 96 on all three, so aligning on it is the one-file change.
#:
#: The hosts own their asset directories (ios F, android G, web A), so this
#: constant is the contract, not the fix.
CONFORMANCE_ASSET_PIXELS = 96

#: Attributes that reference a bundled image asset. Platform host apps
#: (plans 02/03/04) must bundle an asset with this name, at
#: :data:`CONFORMANCE_ASSET_PIXELS` square.
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
    # The SSoT types hintFont as a bare string, so the generic fallback
    # ("sample") applied — but the converters match it against the WEIGHT
    # vocabulary (`json_data['hintFont'] == 'bold'`), and a value outside the
    # vocabulary can only ever render nothing. Same value as its siblings.
    "hintFont": "bold",
    # `sans-serif` is Android's DEFAULT family, so the fixture asked for the
    # face the platform already draws — and it is not a real font name on iOS
    # either, where it has always fallen back to the system font. `serif` is a
    # genuine CSS generic on web, and Compose resolves it once G's
    # `resolveFontFamily` mapping lands. Strictly better than the old value on
    # every platform, and the same "representative == platform default" shape
    # as GradientView.locations. (Lane G.)
    #
    # NOTE for whoever reads the 3PF result: android stays inert until G's
    # mapping is in, and iOS depends on SwiftJsonUI resolving generic family
    # names at all — which is an open question, raised with F/B.
    "fontFamily": "serif",
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
    # A fixture that writes the value its own base already supplies is not a
    # fixture: layout and control come out byte-identical, so "inert" says
    # nothing about the attribute (plan 41 measured six of these at the
    # codegen stage — all six turned out to be read correctly everywhere the
    # moment the values differed). Same rule as the state images below: the
    # value under test must differ from the base's.
    ("Segment", "items"): ["Alpha", "Beta", "Gamma"],
    ("SelectBox", "items"): ["Alpha", "Beta", "Gamma"],
    ("GradientView", "gradient"): ["#00AA00", "#FFAA00"],
    # `[0.0, 1.0]` IS the default stop set of a two-colour linear gradient, so
    # the fixture asked for the picture its control already draws. Lane F's
    # family-B read, group A2. Off-centre stops squeeze the blend into the
    # middle half, which no default produces.
    ("GradientView", "locations"): [0.25, 0.75],
    # Above the content the freed box falls to (40pt children), so the floor
    # actually lifts. The generic 50 would have worked too; 150 matches the
    # ceiling fixtures' scale and leaves no doubt which side of the content it
    # is on.
    ("common", "minWidth"): 150,
    ("common", "minHeight"): 150,
    ("Image", "src"): IMAGE_ALT_ASSET_NAME,
    ("NetworkImage", "defaultImage"): IMAGE_ALT_ASSET_NAME,
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
    # Collection's containerInset is declared `array`; the name-keyed value is
    # the scalar TextView.containerInset (a number) and writing it here made
    # the fixture fail the sjui validator on every build. Same shape as the
    # Collection insets/contentInsets overrides.
    ("Collection", "containerInset"): [8, 8, 8, 8],
    # `value` is Slider/Progress vocabulary in the name-keyed fallback table
    # (0.5), but Switch declares it as its boolean state alias — 0.5 is not a
    # boolean, the Compose codegen host cannot even compile it
    # (`checked = 0.5`), and a non-boolean state fixture can never assert the
    # attribute it exists for.
    ("Switch", "value"): True,
    ("SelectBox", "selectedItem"): "Two",
    ("SelectBox", "selectedValue"): "Two",
    # Three tabs, none of them the base's two — see the base-supplies-the-value
    # note above (the base already writes One/Two, so the old override made the
    # fixture and its control byte-identical).
    ("TabView", "tabs"): [{"title": "Alpha"}, {"title": "Beta"}, {"title": "Gamma"}],
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
    # `partialAttributes` was skipped as "composite value (no representative
    # static value)", so a declared attribute whose semantics the SSoT pins
    # down precisely had no fixture at all. The declaration is specific enough
    # to write one: an array range is [start, end) with the end exclusive,
    # resolved at runtime against the resolved string. "Sample" is the Label
    # base text, so [0, 3) styles "Sam" and leaves "ple" alone — visible on
    # every platform and independent of localisation.
    ("Label", "partialAttributes"): [
        {"range": [0, 3], "fontColor": "#FF0000", "underline": True},
    ],
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
    # --- plan 49-D round (2026-08-05): values outside the attribute's own
    # --- domain, which no converter can read however correctly it is written.
    #
    # `return unless value > 0 && value <= 1.0` (sjui collection_converter.rb:
    # 1713) — the name-keyed fallback DEFAULT_NUMBER (8) is outside the domain,
    # so the fixture could only ever measure the guard. And within the domain,
    # 0.5 was the companion in disguise: fed0d27 folds the weight into a
    # column count, round(1/0.5) = 2 = the companion's own `columns: 2`, so
    # control, representative and the derived second value (1.5 - out of
    # domain, ignored) all drew a 2-column grid. 0.25 asks for FOUR columns
    # against the companion's two (B's arithmetic, probe-confirmed:
    # count: 4 vs count: 2).
    ("Collection", "itemWeight"): 0.25,
    # `value` is Slider/Progress vocabulary in the name-keyed table (0.5), but
    # CheckBox/Radio declare it as `any`: the checked state's associated value.
    # sjui reads `@component['value'] == true` for the checkbox seed, so 0.5
    # can never be the checked state; Radio's is the option's IDENTITY within
    # the group (`radio_value = @component['value'] || id`), i.e. a name.
    ("CheckBox", "value"): True,
    ("Radio", "value"): "optionB",
    # `selectedValue` names WHICH option of the group is selected, so it has to
    # be one of the group's items or it selects nothing — see the `items`
    # companion below.
    ("Radio", "selectedValue"): "Beta",
    # Radio icons are BOTH an asset name and a vocabulary, and neither face
    # can serve as the other's representative. sjui resolves the string as an
    # asset (`Image(name)`), so the SF-Symbol spellings that used to sit here
    # named assets no host bundles and every icon fixture drew the same empty
    # glyph — icon ≡ selectedIcon, value discrimination gone (lane F, 5th
    # run). kjui instead matches the string against SF-Symbol spellings
    # (radio_component.rb:209-236, map_icon_name:423-437) and drops anything
    # else to the same `Icons.Outlined.Star`, so two asset names emit
    # byte-identical text. The PRIMARY takes the bundled asset (ios draws it,
    # kjui's Star arm still differs from the vocabulary arms) and the
    # vocabulary face lives on in EXTRA_CASES. No row needed here: `icon`
    # falls back to IMAGE_ASSET_NAME via IMAGE_ATTRS, and selectedIcon's
    # distinct-asset rows are declared with the other state images above.
    # --- representative == platform default, non-enum half (lane A §5) ------ #
    #
    # Same defect as PREFERRED_PRIMARY_CASE below, for attributes with no enum
    # to reorder: the name-keyed fallback happened to pick the value the
    # platform already uses, so the fixture rendered its control.
    #
    # Booleans whose platform default is ON — the indicator spins, the
    # scrollbars show, the tabs are labelled, the text view is editable and
    # selectable, the iframe is sandboxed — so `true` was a no-op.
    ("Collection", "showsHorizontalScrollIndicator"): False,
    ("Collection", "showsVerticalScrollIndicator"): False,
    ("ScrollView", "showsHorizontalScrollIndicator"): False,
    ("ScrollView", "showsVerticalScrollIndicator"): False,
    ("TabView", "showLabels"): False,
    ("TextView", "editable"): False,
    ("TextView", "selectable"): False,
    ("Web", "sandbox"): False,
    ("Indicator", "animating"): False,
    ("Indicator", "hidesWhenStopped"): False,
    # DEFAULT_NUMBER (8) is also the cross-platform default gap.
    ("CheckBox", "spacing"): 16,
    # Same fallback, one component along, and the A §5(2) round only caught the
    # CheckBox: `radio_spacing_dp` is `json_data['spacing'] || 8`
    # (kjui radio_component.rb:534), so the generic 8 was the default spelled
    # out. Read out of the implementation rather than inferred from the number
    # happening to match CheckBox's.
    ("Radio", "spacing"): 16,
    # rjui's own fallback is `attributes['minimumScaleFactor'] || 0.5`, so the
    # generic 0.5 was the default spelled out.
    ("Label", "minimumScaleFactor"): 0.25,
    # A slider's floor defaults to 0. Kept below the companion `value: 0.5` so
    # the thumb still has somewhere to sit.
    ("Slider", "minimum"): 0.25,
}

#: Extra representative values appended AFTER the primary case, for attributes
#: whose converters branch on a closed vocabulary the SSoT does not enumerate.
#:
#: One value can only ever prove "the spelling is read"; proving the VALUE is
#: read needs a second one that lands in a DIFFERENT branch. Without it
#: `codegen_effect` derives its second value by appending to the first
#: (`circle` -> `circleTwo`), which falls straight back to the vocabulary's
#: default arm and emits identical text — the C2 "presence-only" verdict.
EXTRA_CASES: dict[tuple[str, str], list[Any]] = {
    # The VOCABULARY face of the Radio icons (see the representative-value
    # comment above): the primary is the bundled asset, and this second value
    # is the SF-Symbol spelling that reaches kjui's Checkbox arm — a different
    # arm from the fallback Star the asset name lands on, so the value stays
    # provably read on Compose. `circle`/`checkmark.circle.fill` are NOT
    # cases: kjui maps them to the arm an icon-less radio already renders,
    # i.e. the default in disguise.
    ("Radio", "icon"): ["square"],
    ("Radio", "selectedIcon"): ["checkmark.square.fill"],
    ("Radio", "selected_icon"): ["checkmark.square.fill"],
    # A second LITERAL, so the codegen differential's "second value" is not the
    # bound case. Both of these plan exactly one literal, and with a bound case
    # appended the probe compared `"Beta"` against `@{boundSelectedValue}` —
    # which kjui DOES read (it reads only bindings), so the pair looked
    # different and the real android finding disappeared. Masking a defect is
    # the worse direction of the same artifact that filed nine false ones.
    # Values are drawn from each fixture's own `items`.
    ("Radio", "selectedValue"): ["Gamma"],
    ("SelectBox", "selectedValue"): ["One"],
    # The NUMERIC face of a union-typed attribute. `fontWeight` is declared
    # `["string", "number"]` and every fixture wrote `"bold"`, so the numeric
    # spelling — legal, and named in the attribute's own description — was
    # untested on all three platforms. It is not a hypothetical, though the
    # crash is narrower than first recorded here: a numeric fontWeight
    # ALONGSIDE `partialAttributes` killed `sjui build` with a NoMethodError,
    # because the partial path reached label_converter's private copy of the
    # weight vocabulary and called `.downcase` on an Integer (B, fixed in
    # 2b58e99). B isolated it by controlled experiment against the pre-fix
    # tools, where a numeric weight ON ITS OWN generated all 708 layouts.
    #
    # So this case proves the value is READ; the build failure needs the pair,
    # and that lives in VARIANT_CASES (`fontWeight__*_with_partial`).
    #
    # No new table needed. A union's second type is another literal value, and
    # EXTRA_CASES is where an attribute's extra literals go — same as Radio's
    # icon vocabulary above. `600` is semibold in every platform's table.
    ("Label", "fontWeight"): [600],
    ("Button", "fontWeight"): [600],
    # The faces F measured making the node DISAPPEAR on the dynamic path —
    # the same mechanism as the wave's first finding (`fontSize: "@{x}"`
    # deleting a Label). The object shapes are the declared properties
    # (underline: color/lineOffset/lineStyle, strikethrough: color/lineStyle).
    # Unlike onclick's array face, these do not kill any generator (measured:
    # all three emit and differ from control), so they ship rather than hold.
    ("Label", "underline"): [
        ("styled", {"color": "#FF0000", "lineStyle": "Single", "lineOffset": 2}),
    ],
    ("Label", "strikethrough"): [
        ("styled", {"color": "#FF0000", "lineStyle": "Single"}),
    ],
    # The string spelling of a weight. "2" also differs from the numeric
    # case's 1, so the two faces are distinguishable from each other too.
    ("common", "weight"): [("as_string", "2")],
}

#: Attributes that get a BOUND case: the value under test written as
#: ``@{...}`` instead of a literal, with the data property declared.
#:
#: The suite had 30 bound fixtures and all of them were on attributes where
#: binding is the FIRST-CLASS spelling — `text`, the callbacks, `visibility`.
#: Coverage of the `bound-*` defect family (168 findings across the eight
#: lane queues) was zero: dimensions, colours, enums and numbers, where
#: binding is the exception, had not one bound fixture between them. So the
#: 176 fixes A/B/C are landing in this wave were unprotected the moment they
#: landed, and the render stage could not have caught a regression.
#:
#: The value is the DATA CLASS of the property, and it is load-bearing: the
#: three codegen hosts compile these layouts, and kjui passes an unknown
#: class straight through into Kotlin. Only `String` / `Int` / `Double` /
#: `Boolean` (and `CollectionDataSource`) survive all three.
#:
#: Derived from the eight `bound-*` queues, not hand-listed. Three of the 84
#: pairs are absent because E removed or alias-folded them (`SelectBox.text`,
#: `Slider.minValue`, `Slider.maxValue`).
BOUND_CASE_CLASSES: dict[tuple[str, str], str] = {
    # --- String (36) ---
    ('Button', 'disabledFontColor'): 'String',
    ('Button', 'highlightColor'): 'String',
    ('CheckBox', 'font'): 'String',
    ('Collection', 'lazy'): 'String',
    ('Image', 'contentMode'): 'String',
    ('Label', 'font'): 'String',
    ('Label', 'fontFamily'): 'String',
    ('Label', 'highlightColor'): 'String',
    ('Label', 'textAlign'): 'String',
    ('NetworkImage', 'contentMode'): 'String',
    ('Radio', 'font'): 'String',
    ('SelectBox', 'hintColor'): 'String',
    ('Switch', 'thumbTintColor'): 'String',
    ('Switch', 'tint'): 'String',
    ('TabView', 'tabBarBackground'): 'String',
    ('TextField', 'contentType'): 'String',
    ('TextField', 'font'): 'String',
    ('TextField', 'fontFamily'): 'String',
    ('TextField', 'hintColor'): 'String',
    ('TextView', 'font'): 'String',
    ('TextView', 'fontFamily'): 'String',
    ('TextView', 'hintColor'): 'String',
    ('common', 'disabledBackground'): 'String',
    ('common', 'highlightBackground'): 'String',
    ('common', 'tapBackground'): 'String',
    ('IconLabel', 'text'): 'String',
    ('Radio', 'label'): 'String',
    ('Radio', 'text'): 'String',
    ('CheckBox', 'label'): 'String',
    ('CheckBox', 'text'): 'String',
    ('common', 'tintColor'): 'String',
    ('Label', 'hintColor'): 'String',
    ('Radio', 'selectedValue'): 'String',
    ('SelectBox', 'maximumDate'): 'String',
    ('SelectBox', 'minimumDate'): 'String',
    ('SelectBox', 'selectedValue'): 'String',
    # --- Int (30) ---
    ('CheckBox', 'fontSize'): 'Int',
    ('CheckBox', 'spacing'): 'Int',
    ('Label', 'fontSize'): 'Int',
    ('Label', 'lineSpacing'): 'Int',
    ('Radio', 'fontSize'): 'Int',
    ('Radio', 'spacing'): 'Int',
    ('Slider', 'maximum'): 'Int',
    ('TextField', 'fontSize'): 'Int',
    ('TextView', 'fontSize'): 'Int',
    ('View', 'spacing'): 'Int',
    ('common', 'cornerRadius'): 'Int',
    ('common', 'padding'): 'Int',
    ('common', 'weight'): 'Int',
    ('Button', 'fontWeight'): 'Int',
    ('Label', 'lines'): 'Int',
    ('common', 'bottomPadding'): 'Int',
    ('common', 'leftPadding'): 'Int',
    ('common', 'rightPadding'): 'Int',
    ('common', 'topPadding'): 'Int',
    ('common', 'borderWidth'): 'Int',
    ('common', 'maxHeight'): 'Int',
    ('common', 'maxWidth'): 'Int',
    ('common', 'minHeight'): 'Int',
    ('common', 'minWidth'): 'Int',
    ('common', 'paddingBottom'): 'Int',
    ('common', 'paddingEnd'): 'Int',
    ('common', 'paddingLeft'): 'Int',
    ('common', 'paddingRight'): 'Int',
    ('common', 'paddingStart'): 'Int',
    ('common', 'paddingTop'): 'Int',
    # --- Double (3) ---
    ('Label', 'lineHeightMultiple'): 'Double',
    ('Slider', 'minimum'): 'Double',
    ('Label', 'minimumScaleFactor'): 'Double',
    # --- Boolean (12) ---
    ('Label', 'linkable'): 'Boolean',
    ('common', 'alignBottom'): 'Boolean',
    ('common', 'alignLeft'): 'Boolean',
    ('common', 'alignRight'): 'Boolean',
    ('common', 'alignTop'): 'Boolean',
    ('common', 'centerHorizontal'): 'Boolean',
    ('common', 'centerInParent'): 'Boolean',
    ('common', 'centerVertical'): 'Boolean',
    ('common', 'clipToBounds'): 'Boolean',
    ('Radio', 'checked'): 'Boolean',
    ('TextField', 'secure'): 'Boolean',
    ('CheckBox', 'enabled'): 'Boolean',
}


#: Bound cases held back because the fixture would break the codegen HOST.
#:
#: A fixture that does not compile does not measure its own attribute badly —
#: it stops that platform's ENTIRE run, because the host is one build. So a
#: bound case whose emitted source does not build is declared here instead of
#: shipped.
#:
#: This is a HOLD, not a decision. Each entry names who owns the defect, what
#: the defect is, and — the load-bearing part — WHAT TO RUN to find out whether
#: it is still true. The gate checks the `verify` axes it can execute itself
#: and reports the rest as unverified holds rather than failing on them: a
#: non-empty table is normal operation, because it means somebody found a
#: defect and wrote it down. What the gate fails on is an entry with no owner,
#: or one whose `verify` says it is already clear.
#:
#: Known `verify` axes, both of them established by having actually happened:
#:
#:   codegen-effect:bound-uncompilable
#:       `jui conformance codegen-effect` reports the pair in that class.
#:       Cleared 26 entries when A/B/C fixed the raw `Modifier.width(@{v}.dp)`
#:       interpolation family.
#:   web-host-typecheck
#:       regenerate `conformance/hosts/web` and run `tsc --noEmit`.
#:       Cleared the last 6 — and the differential said nothing about them,
#:       because it only asks whether `@{` survived into the output, never
#:       whether the output typechecks. One axis would have missed them.
#:
#: Empty today. It stays in the file precisely because it is empty: the next
#: bound fixture that stops a host from building needs somewhere to be declared
#: with its reason, rather than quietly deleted.
BOUND_CASES_BLOCKED: dict[tuple[str, str], dict[str, str]] = {
    # ("Label", "textAlign"): {
    #     "owner": "A",
    #     "reason": "React.CSSProperties['textAlign'] is a literal union; a "
    #               "plain string does not assign",
    #     "verify": "web-host-typecheck",
    # },
}

#: Declared types whose fixture is held back because EMITTING it breaks the
#: generator. Same three fields as the other holds.
#:
#: An attribute typed `string|array` whose array face nothing has ever written
#: is not a hypothetical gap: measured on all three, writing
#: `onclick: ["confPush", "confPop"]` gives
#:
#:   ios      both selectors emitted — the codegen is right, and F's finding is
#:            that the DYNAMIC path invokes neither
#:   android  generation dies: NoMethodError, undefined method `match?' for
#:            Array (kjui get_event_handler_call, reached from
#:            modifier_builder.rb:732 and button_component.rb:71)
#:   web      emits `onClick={data.["confPush", "confPop"]}` — TS1003,
#:            not valid syntax
#:
#: Two of three cannot build, and a fixture that stops a host building takes
#: that platform's whole run with it. So the fixture is written and held, the
#: same way the bound cases were: each entry names what has to be true for it
#: to come out, and it comes out the moment that is true.
ARRAY_FACE_BLOCKED: dict[tuple[str, str], dict[str, str]] = {
    ("common", "onclick"): {
        "owner": "C + A",
        "reason": "kjui raises NoMethodError (`match?` on an Array) and rjui "
                  "emits `data.[...]`, which is not syntax; ios emits both "
                  "selectors correctly",
        "verify": "codegen-probe:all-three-emit",
    },
}


def _check_array_face_blocked() -> None:
    for pair, hold in ARRAY_FACE_BLOCKED.items():
        missing = [f for f in BOUND_HOLD_FIELDS if not hold.get(f)]
        if missing:
            raise ValueError(
                f"ARRAY_FACE_BLOCKED[{pair!r}] is missing {missing!r}"
            )


#: Fixture pairs that are EXPECTED to render identically to each other.
#:
#: The visual check compares each fixture to its control, and nothing compares
#: two declared values to one another. So "both differ from the control, and
#: are identical to each other" passes everything — which is exactly what
#: `distribution`'s four values do. The manifest now carries a `peerGroup` so a
#: gate can make that comparison; this is where the exceptions are declared,
#: because some values legitimately draw the same picture.
#:
#: `borderStyle__solid` is the shape to keep in mind: `solid` IS the declared
#: default, so it drawing what the default draws is correct, and a bare
#: pairwise-distinct rule would file the correct implementation as a defect.
#: A device that turns adjudicated-correct behaviour red is worse than no
#: device — it trains people to ignore it.
#:
#: Empty on purpose. Populating it from guesses would pre-declare exceptions
#: nobody has measured; the entries belong to whoever runs the comparison and
#: sees a pair come back identical. Same three fields as the other ledgers.
PEER_EXPECTED_IDENTICAL: dict[tuple[str, str, str, str], dict[str, str]] = {
    # ("common", "borderStyle", "solid", "dashed"): {
    #     "owner": "E",
    #     "reason": "…",
    #     "verify": "…",
    # },
}


def _check_peer_exceptions() -> None:
    for key, entry in PEER_EXPECTED_IDENTICAL.items():
        missing = [f for f in BOUND_HOLD_FIELDS if not entry.get(f)]
        if missing:
            raise ValueError(
                f"PEER_EXPECTED_IDENTICAL[{key!r}] is missing {missing!r} — an "
                "expected-identical pair without a reason is indistinguishable "
                "from a defect nobody looked at"
            )


#: Attributes reachable only through UIKit, which nothing in the conformance
#: suite renders — and which, by the 2026-08-05 user ruling, nothing will.
#:
#: Neither iOS path can photograph them, for two independent reasons:
#:
#:   codegen host   UIKit attributes are applied by the Swift runtime and
#:                  never pass through a Ruby converter (the same fact
#:                  MODE_PLATFORM_MAP records: `uikit` maps to no codegen).
#:   dynamic host   it is the SwiftUI dynamic renderer, not the UIKit one
#:                  (INTERACTIVE_HOST_CONTRACT.md:56).
#:
#: 61 fixtures sat in this position calling themselves `visual`: generated,
#: control-bearing, counted as visual coverage, and never once captured. Only
#: three ever surfaced, because only those three happened to be in a baseline;
#: the rest were absorbed by the no_baseline / missing_artifact ratchets.
#:
#: The ruling is to stop measuring them, and the class is where that has to be
#: recorded — a ledger entry alone would leave 61 fixtures still claiming
#: coverage they do not have, which is the failure this wave exists to remove.
#: A decision not to measure has to show up in the numbers.
#:
#: The fixtures STAY. A `mode: uikit` attribute is a legal iOS layout and the
#: fixture proves the declaration survives generation; what changes is that it
#: stops pretending to be a photograph.
#:
#: Deliberately NOT `is_non_observable`, which means "no still capture could
#: ever show this". These could be shown — by a UIKit host. The reason is that
#: we chose not to point a camera at them, and the two reasons should not be
#: filed under one name.
def is_uikit_only(defn: dict) -> bool:
    """True when ``mode`` names UIKit and nothing else."""
    raw = defn.get("mode")
    modes = raw if isinstance(raw, list) else ([raw] if raw else [])
    return bool(modes) and set(modes) == {"uikit"}


#: Attributes whose fixture cannot be SHAPED to observe them yet, with what is
#: missing. Same three fields as the bound-hold table: who owns it, what the
#: obstacle is, and what would settle it.
#:
#: Deliberately NOT wired into `is_non_observable`. That table says "no still
#: capture can ever show this", which is a permanent claim; these are the
#: opposite — the attribute is observable in principle and the generator simply
#: cannot build the fixture that would show it today. Declaring them
#: unobservable would be the mistake A caught over `disabledBackground`:
#: pronouncing something unmeasurable when a fix would reveal it.
#:
#: So the fixtures stay, keep their controls, and go on reporting inert. This
#: table is what stops that inert from being read as a defect — and what tells
#: the next person which single mechanism unlocks it.
UNSHAPEABLE_FIXTURES: dict[tuple[str, str], dict[str, str]] = {
    # Empty, and every entry it ever held came out the way the table was meant
    # to work: the `verify` condition was written down, somebody else met it,
    # and the row went. `Blur.blurRadius` and `common.indexAbove` needed a
    # root-children mechanism, which turned out to be two `root.` companions;
    # `Collection.scrollAnchor` needed a scrollTo data class that compiles on
    # three hosts, which E made a plain value (9930e18) and B unblocked by
    # replacing sjui's `.throttle` with `.onChange` (8c41e3e).
    #
    # Keep the table. The next fixture the generator cannot shape needs
    # somewhere to be declared with its owner and its release condition,
    # instead of being called "next wave".
}


def _check_unshapeable() -> None:
    for pair, entry in UNSHAPEABLE_FIXTURES.items():
        missing = [f for f in BOUND_HOLD_FIELDS if not entry.get(f)]
        if missing:
            raise ValueError(
                f"UNSHAPEABLE_FIXTURES[{pair!r}] is missing {missing!r} — an "
                "unmeasurable fixture without an owner is just an unexplained "
                "inert result"
            )


#: `verify` values the gate knows how to act on. A hold naming anything else is
#: still legal — it just cannot be checked automatically, so it surfaces in the
#: report as an unverified hold instead of being silently trusted.
BOUND_HOLD_VERIFY_AXES = frozenset(
    {"codegen-effect:bound-uncompilable", "web-host-typecheck"}
)

#: Fields every hold must carry. Enforced at import: a hold that loses its
#: owner stops being a hold and becomes an unexplained gap in the suite.
BOUND_HOLD_FIELDS = ("owner", "reason", "verify")

def _check_bound_holds() -> None:
    for pair, hold in BOUND_CASES_BLOCKED.items():
        missing = [f for f in BOUND_HOLD_FIELDS if not hold.get(f)]
        if missing:
            raise ValueError(
                f"BOUND_CASES_BLOCKED[{pair!r}] is missing {missing!r} — a hold "
                "without an owner and a way to verify it is an unexplained gap"
            )


_check_bound_holds()
_check_unshapeable()
_check_peer_exceptions()
_check_array_face_blocked()


#: Name of the data property a bound case binds to, per attribute.
BOUND_PROP_PREFIX = "bound"


def bound_prop_name(attribute: str) -> str:
    """`fontSize` -> `boundFontSize`. Prefixed so it cannot collide with a
    companion binding (`inputText`, `pickedDate`) or a host data property."""
    return f"{BOUND_PROP_PREFIX}{attribute[:1].upper()}{attribute[1:]}"


#: Suffix marking the bound case in a fixture id.
BOUND_CASE_SUFFIX = "binding"


def bound_case_for(
    section: str, attribute: str, assertions: tuple[dict, ...] = ()
) -> CasePlan | None:
    """The bound case for this attribute, or None if it does not get one.

    *assertions* is carried over from the literal case on assertable
    attributes: the bound property is seeded with the same value, so the
    fixture must satisfy the same assertion — and it only can if the binding
    actually resolved. Without them the test is a `waitFor` and nothing else.
    """
    cls = BOUND_CASE_CLASSES.get((section, attribute))
    if cls is None or (section, attribute) in BOUND_CASES_BLOCKED:
        return None
    prop = bound_prop_name(attribute)
    return CasePlan(
        name=BOUND_CASE_SUFFIX,
        value=f"@{{{prop}}}",
        written_key=attribute,
        assertions=assertions,
    )


#: Enum value promoted to the FRONT of an attribute's case list.
#:
#: Every enum value still gets its own fixture; this only decides which one is
#: the attribute's *representative* — the value the alias probe mirrors and the
#: codegen differential calls `primary`. When the first value in the SSoT enum
#: is one the converters deliberately ignore, the representative measures the
#: rejection instead of the attribute.
PREFERRED_PRIMARY_CASE: dict[tuple[str, str], Any] = {
    # `return '' unless %w[graphical inline].include?(style)` (rjui
    # select_box_converter.rb:487). The enum leads with `automatic`, which is
    # exactly the arm that emits nothing.
    ("SelectBox", "datePickerStyle"): "graphical",
    # --- representative == platform default (lane A §5, 2026-08-05) --------- #
    #
    # These enums lead with the value the platform already renders when the
    # attribute is absent, so the fixture and its control come out identical
    # and the visual check reads "identical to control, investigate" — a false
    # positive that looks exactly like a dropped attribute. Every value still
    # gets its own fixture; this only moves the REPRESENTATIVE off the default.
    # The replacements are the machine's own second value (`codegen-effect`
    # `representativeValueCandidates`), not hand-picked.
    # `medium` IS the circular style an indeterminate ProgressView already
    # draws, so the emit was correct (C0 passes) and the picture was the
    # control's. `large` adds `.scaleEffect(1.5)` and discriminates. Measured
    # by B, same family as GradientView.locations.
    ("Indicator", "indicatorStyle"): "large",
    # Progress has the same pair and the same trap, one component along:
    # `medium` is the size an indeterminate ProgressView already draws, so the
    # fixture asked for its control. B measured it as value-is-default.
    ("Progress", "indicatorStyle"): "large",
    # `Vertical` is the default gradient axis, so the direction fixture drew
    # what a gradient with no direction draws. Now that the fixture has a
    # gradient at all (this round), the representative has to be off the
    # default for the attribute to show.
    ("View", "gradientDirection"): "Horizontal",
    ("Collection", "defaultScrollAnchor"): "center",
    ("Collection", "layout"): "horizontal",
    ("Collection", "lazy"): "eager",
    ("GradientView", "gradientDirection"): "Horizontal",
    ("IconLabel", "iconPosition"): "Right",
    ("Image", "contentMode"): "fill",
    ("Image", "renderingMode"): "template",
    ("Label", "lineBreakMode"): "Clip",
    ("ScrollView", "scrollMode"): "window",
    ("SelectBox", "datePickerMode"): "time",
    ("SelectBox", "selectItemType"): "Date",
    ("Switch", "labelPosition"): "trailing",
    ("TextView", "lineBreakMode"): "Clip",
    ("TextView", "resize"): "both",
    ("View", "direction"): "bottomToTop",
    ("View", "distribution"): "fillEqually",
    ("common", "alignment"): "top",
    ("common", "distribution"): "fillEqually",
    # Radio icon/selectedIcon rows (promote `square` over `circle`) were
    # removed when the primary became the bundled asset: an SF-Symbol
    # representative names an asset ios cannot resolve, and its empty glyph
    # sits exactly on the icon-less control — the inert false positive this
    # table exists to prevent.
}

#: Text-ish string attributes that read better with a hint payload.
HINT_ATTRS = {"hint", "placeholder"}
HINT_TEXT = "Conformance Hint"

#: Text long enough to wrap several times inside the 200pt text hosts, for
#: attributes that only act once there is MORE content than fits (line caps,
#: break modes). The one-word base text made every such value render the same
#: pixels as its control.
#: Text with a URL in it, for `linkable`: the attribute turns URLs in the body
#: into links, and the plain sample text contains none, so it had nothing to
#: turn (lane F family-B, group A3).
LINK_TEXT = "See https://example.com/conformance for details"

LONG_TEXT = (
    "Sample text long enough to wrap onto several lines inside the "
    "two hundred point wide conformance hosts"
)

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
    # selectedValue is the GROUP's selection binding, and every platform only
    # has a group to select from when the radio declares `items`: sjui takes
    # the group path on `items.any?` (radio_converter.rb:13) and kjui reads the
    # spelling only inside generate_radio_group_with_items
    # (radio_component.rb:293-295). A single radio has no selection to name —
    # its own identity is `value` — so the old `{value: "sample"}` companion
    # was answering a different question. The representative value is one of
    # these items (VALUE_OVERRIDES_BY_SECTION: "Beta").
    "Radio.selectedValue": {"items": ["Alpha", "Beta", "Gamma"]},
    "CheckBox.checkedColor": {"checked": True},
    "Radio.checkedColor": {"checked": True},
    # onTintColor colors the ON track — the switch must be on to show it.
    "Switch.onTintColor": {"isOn": True},
    # --- plan 34 fixture-observability round (2026-08-04) ------------------ #
    # Every converter reads `text || label`, and the Radio base supplies
    # `text` — so `label` lost the coin toss on all three platforms and the
    # fixture measured inert everywhere. Dropping the mask does NOT make the
    # fixture pass: sjui's radio_converter never reads `label` at all (grep:
    # zero hits), so iOS stays inert. That is the point — the mask was hiding
    # a real single-platform gap behind a uniform one.
    "Radio.label": {"text": None},
    # `placeholder` is declared as an ALIAS of `hint`, and the base injects
    # `hint` — so the fixture carried both spellings, the primary won, and the
    # alias could never move a pixel however correctly it resolved. Same for
    # Label, whose hint only shows "when empty" and whose base supplies text.
    #
    # Dropping the text is necessary but NOT sufficient (49-D re-measure): the
    # canonical Label hint contract — UIKit SJUILabel, mirrored by all three
    # codegens — requires BOTH keys, `hint` AND `hintAttributes`
    # (rjui label_converter.rb:89 `return nil unless attrs.is_a?(Hash) …`,
    # sjui label_converter.rb:392 label_hint_config, kjui text_component.rb:
    # 457). With no hintAttributes the styled-hint swap never happens and the
    # fixture emitted an empty label on every platform. `hintAttributes` here
    # carries NO fontColor on purpose, so `hintColor` is the one that decides
    # the colour (`attrs['fontColor'] || hintColor`).
    "Label.hint": {"text": None, "hintAttributes": {"fontSize": 12}},
    "Label.placeholder": {"text": None, "hintAttributes": {"fontSize": 12}},
    # hintColor styles the HINT, so the hint has to be the thing rendering:
    # drop the base text (a non-empty Label never shows its hint) AND supply
    # the hint itself, or the fixture is an empty label with a colour setting.
    "Label.hintColor": {
        "text": None,
        "hint": HINT_TEXT,
        "hintAttributes": {"fontSize": 12},
    },
    # minimumScaleFactor is the FLOOR of the auto-shrink, read only inside
    # `if attributes['autoShrink']` (rjui label_converter.rb:450). Without the
    # switch there is no shrinking for a floor to bound.
    "Label.minimumScaleFactor": {"autoShrink": True, "text": LONG_TEXT},
    "TextField.placeholder": {"hint": None},
    "TextView.placeholder": {"hint": None},
    # placeholderColor styles the PLACEHOLDER, so the placeholder spelling has
    # to be the one rendering — with the base hint present, hintColor governs.
    "TextField.placeholderColor": {"hint": None, "placeholder": HINT_TEXT},
    # Range attributes move the thumb only if there IS a thumb position: with
    # no value declared the thumb sits at an end on every platform and the
    # range can be anything (ios pinned it at min, android at max, web at the
    # midpoint — all three inert). Same reason Slider.tintColor already has it.
    "Slider.maximum": {"value": 0.5},
    "Slider.maxValue": {"value": 0.5},
    "Slider.minimum": {"value": 0.5},
    "Slider.minValue": {"value": 0.5},
    "Slider.step": {"value": 0.5},
    "Slider.trackTintColor": {"value": 0.5},
    "Slider.progressTintColor": {"value": 0.5},
    # iconColor maps to the CHECKMARK (kjui: Material checkmarkColor, sjui:
    # the glyph tint) — an unchecked box draws no checkmark to tint.
    "CheckBox.iconColor": {"checked": True},
    # `selected` chooses icon_on over icon_off and selectedFontColor over
    # fontColor (SSoT), so both alternatives must exist for the swap to show;
    # and selectedFontColor is only in force while selected.
    "IconLabel.selected": {
        "icon_off": IMAGE_ASSET_NAME,
        "icon_on": IMAGE_ALT_ASSET_NAME,
        "selectedFontColor": "#FF0000",
    },
    "IconLabel.selectedFontColor": {"selected": True},
    # Label.selected switches the label to highlightAttributes (SSoT) — with
    # none declared there is nothing to switch TO.
    "Label.selected": {"highlightAttributes": {"fontColor": "#FF0000"}},
    # Disabled skins need the disabled state, which IS reachable in a static
    # capture (unlike pressed/tapped).
    "disabledBackground": {"enabled": False},
    "disabledFontColor": {"enabled": False},
    # secure masks TEXT; the base is hint-only, so there was nothing to mask.
    "TextField.secure": {"text": "Sample"},
    # columnSpacing is the gap BETWEEN columns — the default single-column
    # collection has no gap to size.
    # A safe-area inset is PADDING, and padding does not move the outside of a
    # box that is already pinned to both parent edges — `matchParent x
    # matchParent` is the same rectangle whatever is inset inside it. Fixing
    # the size lets the inset show on the outline. F measured it: at 200x200 a
    # local smoke gives distance 10 where matchParent gives 0.
    #
    # Scoped to SafeAreaView: `View.safeAreaInsetPositions` sits on the View
    # base, which is already a fixed 200x200 square.
    "SafeAreaView.safeAreaInsetPositions": {
        "width": 200,
        "height": 200,
    },
    # `align*OfView` places the target OUTSIDE the anchor's edge, so the target
    # needs that much room between the anchor and the screen edge. With the
    # 200pt View base and the anchor 60pt in, `alignTopOfView` put the target
    # at y = -140..60 and `alignLeftOfView` at x = -140..60: off-screen, so
    # BOTH the dynamic and the codegen host drew nothing, parity read the two
    # blanks as agreement, and inert-complete saw no difference either. Two
    # empty pictures agreeing is the most convincing kind of nothing. (Lane G.)
    #
    # A 50pt target with the anchor 120pt in puts all four directions on
    # screen — top/left at 70..120, bottom/right at 170..220, against a control
    # at 0..50 — which fits the narrowest host (a ~390pt phone) with room to
    # spare and leaves a 70pt shift to see. Checked arithmetically for 50 / 100
    # / 200 before writing it down; 100 fits but only shifts 20pt, and 200 does
    # not fit at all.
    # `backdrop-filter` blurs what is BEHIND the element, and the root is an
    # overlay — so an earlier sibling sits underneath the target. A flat colour
    # blurs to the same flat colour, which is why every radius rendered its
    # control; stripes give the blur something to smear.
    "Blur.blurRadius": {
        "root.backdrop": [
            {"type": "View", "id": "backdrop", "width": 100, "height": 100,
             "background": "#FF0000", "orientation": "horizontal", "child": [
                 {"type": "View", "id": "stripe_a", "width": 20, "height": 100,
                  "background": "#FFFFFF"},
                 {"type": "View", "id": "stripe_b", "width": 20, "height": 100,
                  "background": "#0000FF"},
                 {"type": "View", "id": "stripe_c", "width": 20, "height": 100,
                  "background": "#FFFFFF"},
                 {"type": "View", "id": "stripe_d", "width": 20, "height": 100,
                  "background": "#00AA00"},
             ]},
        ],
    },
    # The anchor goes LAST so the target starts underneath it and `indexAbove`
    # has somewhere to travel from. `indexBelow` needs no such thing — the
    # default order already puts the target on top, which is exactly why only
    # one of the pair was ever inert.
    "indexAbove": {"root.anchorLast": True},
    "alignTopOfView": {"width": 50, "height": 50},
    "alignBottomOfView": {"width": 50, "height": 50},
    "alignLeftOfView": {"width": 50, "height": 50},
    "alignRightOfView": {"width": 50, "height": 50},
    "Collection.columnSpacing": {"columns": 2},
    # `flow` is only distinguishable from `horizontal` once a row FILLS: the
    # three 60pt cells total 180pt, which fits the 200pt host in one row, so
    # flow never wrapped and the pair drew one picture (run 5, android/web).
    # 150pt forces flow into a 2+1 grid while horizontal keeps one scrolling
    # row — and vertical is untouched by width.
    "Collection.layout": {"width": 150},
    # `cols` and `rows` size a textarea in characters and lines, and an
    # explicit width/height overrides them everywhere. Dropping the base size
    # is what lets the attribute decide the box (lane A §5(4)).
    "TextView.cols": {"width": None},
    "TextView.rows": {"height": None},
    # A FLOOR only lifts a box that would otherwise be smaller than it, and the
    # View base is a fixed 200pt square — so `minWidth: 50` lost to the 200 and
    # the fixture measured the fixed width, not the floor. Freeing the axis lets
    # the box fall to its content (the overlaid 40pt children) so the floor has
    # something to lift it off. Lane F's family-B read, group A2, the last of
    # the six.
    #
    # `maxWidth` / `maxHeight` need no such treatment: a CEILING of 150 does
    # clamp a 200pt box, which is why only the floors were inert. The
    # matchParent-plus-ceiling case has its own bespoke fixtures
    # (conformance.bounds_fixtures).
    "minWidth": {"width": "wrapContent"},
    "minHeight": {"height": "wrapContent"},
    # clipToBounds needs something to clip: the stacked base children fit
    # inside the host, a horizontal row of them overflows it.
    "clipToBounds": {"orientation": "horizontal"},
    # A line CAP needs more lines than the cap: the one-word base text fits
    # on a single line, so any maximum renders the same pixels.
    "Label.lines": {"text": LONG_TEXT},
    "IconLabel.lines": {"text": LONG_TEXT},
    # --- lane F family-B, group A3 (2026-08-05) ---------------------------- #
    # "the fixture is too thin for the attribute to act on". Every Label
    # fixture was `text: "Sample"` in a 200pt box — one short line that fits —
    # and each of these attributes only exists once there is MORE than that.
    #
    # Line metrics need a second line to sit between.
    "Label.lineSpacing": {"text": LONG_TEXT},
    "Label.lineHeightMultiple": {"text": LONG_TEXT},
    # Truncation modes only choose WHERE to cut once something is being cut.
    "Label.lineBreakMode": {"text": LONG_TEXT},
    # Shrink-to-fit needs an overflow to shrink out of; the floor needs the
    # shrinking to be happening before it can bound it.
    "Label.autoShrink": {"text": LONG_TEXT},
    # A hint's line height needs a hint of more than one line.
    "TextView.hintLineHeightMultiple": {"hint": LONG_TEXT},
    # `linkable` turns URLs in the body into links. "Sample" has none.
    "Label.linkable": {"text": LINK_TEXT},
    # The no-source state shows `defaultImage` FIRST, so the state images
    # behind it were never displayed — same shape as Image.errorImage above.
    # An error image needs a REQUEST THAT FAILS, and every NetworkImage fixture
    # was in the no-src state — 19 of them, none carrying a url — so neither
    # the error nor the loading face had ever occurred (C, #19). kjui says so
    # at the point of the branch: an absent source is a NULL model that selects
    # the fallback, while a real URL routes through the request/error path.
    #
    # `.invalid` is reserved by RFC 2606 precisely so it can never resolve, so
    # this fails at DNS without leaving the machine and keeps the offline rule
    # the v1 fixtures are built on. `defaultImage` still goes, or the no-src
    # fallback would win before the request was ever made.
    "NetworkImage.errorImage": {
        "defaultImage": None,
        "url": "https://conformance.invalid/missing.png",
    },
    # Same failing request as errorImage: without a url there is no in-flight
    # state either, and the codegen DOES read the spelling once there is one
    # (measured on both mobile converters against a control on the same base).
    # What no still capture can hold is the MOMENT — see
    # NON_OBSERVABLE_BY_SECTION, where the screenshot is switched off and the
    # codegen probe goes on measuring it.
    "NetworkImage.loadingImage": {
        "defaultImage": None,
        "url": "https://conformance.invalid/missing.png",
    },
    "NetworkImage.placeholder": {"defaultImage": None},
    # A closed SelectBox draws `prompt` when there is one and the (initially
    # empty) selected text when there is not — so with no prompt declared
    # there were no glyphs for a colour to land on.
    "SelectBox.fontColor": {"prompt": "Choose"},
    "SelectBox.hintColor": {"prompt": "Choose"},
    # Same gap, same companion, two attributes further along: a weight and a
    # size need glyphs to apply to just as much as a colour does. The A3 round
    # caught the colours and stopped there, so `font` and `fontSize` kept
    # styling the closed box's empty selected text. Found by G while
    # registering the `selectedIndex` prediction — the point being that fixing
    # `selectedIndex` would not have moved these two either.
    "SelectBox.font": {"prompt": "Choose"},
    "SelectBox.fontSize": {"prompt": "Choose"},
    # Found by checking the siblings rather than reported: `labelAttributes`
    # declares font / fontSize / fontColor / textAlign and no text of its own,
    # so it styles the same empty closed label. `hint` and `placeholder` are
    # deliberately NOT here — they ARE the text under test, and a prompt would
    # win over them exactly the way the base `text` used to beat `Label.hint`.
    "SelectBox.labelAttributes": {"prompt": "Choose"},
    # Track/progress tints need a nonzero value or there is nothing to
    # paint (a zero-length active track is invisible on every platform).
    # Slider's canonical value attribute is `value`; Progress's is `progress`
    # (`value` is the undeclared legacy spelling there — see
    # shared/core/attribute_semantics.json → progressValue).
    "Slider.tintColor": {"value": 0.5},
    "Progress.color": {"progress": 0.5},
    "Progress.tintColor": {"progress": 0.5},
    "Progress.progressTintColor": {"progress": 0.5},
    "Progress.trackTintColor": {"progress": 0.5},
    # Flow attributes need a flex container. `horizontal` is the direction that
    # makes wrapping visible with the standard 6-box child set (240px of boxes
    # in a 200px host).
    "flexWrap": {"orientation": "horizontal"},
    # Distribution shares out FREE space, and six 40pt boxes in a 200pt row
    # leave none — they overflow it. A 300pt row leaves 60pt to share.
    "distribution": {"orientation": "horizontal", "width": 300},
    # Gravity positions CONTENT inside free space, so it needs slack on BOTH
    # axes — the six boxes overflow a 200pt row and the horizontal half of
    # every value was invisible (run 5: android rendered centerhorizontal,
    # left, top and right as one picture). 300pt leaves 60pt of horizontal
    # slack, the same lever distribution uses. left ≡ top survives this on
    # purpose: the unspecified axis defaults to top/start on every platform,
    # so both values name the top-left corner — that pair is recorded, not
    # fixtured away.
    "gravity": {"orientation": "horizontal", "width": 300},
    "spacing": {"orientation": "horizontal"},
    "padding": {"orientation": "horizontal"},
    "paddings": {"orientation": "horizontal"},
    "paddingTop": {"orientation": "horizontal"},
    "paddingLeft": {"orientation": "horizontal"},
    "paddingStart": {"orientation": "horizontal"},
    # The TRAILING edges need the box to be free, not merely flowing. In a
    # fixed 200x200 square the content sits in the top-left corner, so padding
    # added at the bottom or the right pushes against nothing and the picture
    # is unchanged. On a wrapContent box the padding grows the box itself,
    # which is visible on any edge. (Lane A §5(4). The leading edges above
    # already move the content and need no change.)
    "paddingBottom": {"orientation": "horizontal", "height": "wrapContent"},
    "bottomPadding": {"orientation": "horizontal", "height": "wrapContent"},
    "paddingRight": {"orientation": "horizontal", "width": "wrapContent"},
    "rightPadding": {"orientation": "horizontal", "width": "wrapContent"},
    "paddingEnd": {"orientation": "horizontal", "width": "wrapContent"},
    # A trailing MARGIN on the only child of a fixed parent has nothing behind
    # it to push away from. Parking the root's content against that same edge
    # gives it something to push off — the lever the top-left family uses,
    # pointed the other way.
    "bottomMargin": {"root.gravity": "bottom"},
    "rightMargin": {"root.gravity": "right"},
    "endMargin": {"root.gravity": "right"},
    # NO `borderStyle` companion here, deliberately. A border is drawn only
    # when `borderWidth` AND `borderColor` are both declared — there is no
    # default border colour — so `borderStyle` alone is CORRECTLY inert and its
    # fixture must stay a lone declaration. The ruling lives in
    # `shared/core/attribute_semantics.json` -> `semantics.border`
    # (`widthAlone: no-draw`, `styleAlone: no-draw`), and its own text records
    # that the gray-default direction was tried and withdrawn.
    #
    # A `{borderWidth: 1}` companion was added here on 2026-08-05 and taken
    # back the same day: it was reasoned from `attribute_definitions.json`
    # (only borderStyle declares `"default": "solid"`, so something must summon
    # the border and width looked like the summoner). The default proves style
    # is a MODIFIER; it says nothing about which key summons. **Read
    # attribute_semantics.json before inferring semantics from a type, an enum
    # or a default** — that is where rulings live (commit d119189).
    #
    # The "top-left family". `alignTop` / `alignLeft` pin the target to the
    # parent edge it is ALREADY at — the root stacks its children at the
    # top-start corner — so the attribute asked for the position the target
    # already had and nothing moved. G proved it from the distribution rather
    # than from the code: `alignBottom` / `alignRight` / `alignBottomView` /
    # `alignRightView` are absent from the android queue, i.e. their pixels DO
    # move, and an implementation defect has no reason to pick a direction.
    #
    # Pushing the root's content to the far edge gives the attribute somewhere
    # to travel from. The `root.` companion widens the control identically, so
    # the comparison still measures only the attribute.
    "alignTop": {"root.gravity": "bottom"},
    "alignLeft": {"root.gravity": "right"},
    # `highlighted` is the other half of a pair, like border/borderColor:
    # `return if highlight_bg.nil?` (sjui base_view_converter.rb:730), which
    # faithfully mirrors UIKit's SJUIView:187 — a highlighted state with no
    # highlight colour has nothing to draw. The probe wrote the flag alone and
    # read it as an unread spelling. (borderColor/borderWidth are the same
    # family and were closed on the device side by `--paired`; this one closes
    # with a base attribute.) Handed over by lane B.
    "View.highlighted": {"highlightBackground": "#FF0000"},
    # `direction` reverses the children of an ORIENTED container; with no
    # orientation the canonical answer is "no effect", so the fixture has to
    # supply one or it can never show anything. One orientation cannot serve
    # every value: the reversal only acts on its OWN axis, so the horizontal
    # values get a horizontal container via CASE_BASE_ATTRS below — on the
    # shared vertical base, `rightToLeft` was a designed no-op, and the only
    # thing its fixture ever caught was an ios dynamic missing the axis guard
    # (run 5: it reversed a vertical stack).
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
    # `dateStringFormat` is the shape the VIEWMODEL holds, so it is only
    # consulted while converting a BOUND value in and out of the input's ISO
    # spelling (rjui select_box_converter.rb:391 `if format` — inside the
    # `has_binding?(date_value)` arm). A date picker with no bound date has no
    # value to reformat, so the declared format was never read.
    "SelectBox.dateStringFormat": {
        "selectItemType": "Date",
        "selectedDate": "@{pickedDate}",
    },
    # minuteInterval is a step through minutes, so it needs a time-bearing mode.
    "SelectBox.minuteInterval": {"selectItemType": "Date", "datePickerMode": "time"},
    # Same date-branch gate, four attributes the earlier round missed.
    # `colorScheme` is consumed only by build_date_style_attr (rjui
    # select_box_converter.rb:426); the bounds and the mode are date-only on
    # all three platforms.
    "SelectBox.datePickerMode": {"selectItemType": "Date"},
    "SelectBox.colorScheme": {"selectItemType": "Date"},
    "SelectBox.minimumDate": {"selectItemType": "Date", "datePickerMode": "date"},
    "SelectBox.maximumDate": {"selectItemType": "Date", "datePickerMode": "date"},
    # scrollAnchor is the anchor OF a programmatic scroll and every platform
    # reads it only inside the scrollTo path. D withdrew this companion in an
    # earlier round for a reason that no longer holds: scrollTo's declared
    # class had to be `PassthroughSubject<Int, Never>` for sjui's
    # `data.<prop>.throttle(...)`, and no class satisfied all three hosts at
    # once. E made the canonical class a plain value (9930e18) and B dropped
    # the throttle for `.onChange` (8c41e3e), so `Int` now compiles everywhere.
    #
    # The withdrawal was right at the time and the entry said what would undo
    # it; both halves happened, so it goes in.
    "Collection.scrollAnchor": {"scrollTo": "@{scrollTarget}"},
    # itemWeight is the fraction of the container width ONE ITEM takes, which
    # is a grid concept: sjui folds it into the grid's column count
    # (fed0d27: round(1/weight) columns) and the default single-column
    # CollectionStackView path never consults it. The companion supplies the
    # grid; the REPRESENTATIVE (0.25, above) is what has to disagree with the
    # companion's own column count, or all three probe pictures collapse.
    #
    # `Collection.scrollAnchor` is the other half of this family and is NOT
    # fixable here — see the 49-D report. It needs `scrollTo` as a companion,
    # `scrollTo` is a `binding`, and the data property behind it has no class
    # that compiles on more than one codegen host (iOS wants
    # `PassthroughSubject<String, Never>`, Compose emits `raw.isEmpty()` /
    # `substringBefore` on it, i.e. String, and kjui's map_to_kotlin_type
    # passes an unknown class straight through). Handed to E + C.
    "Collection.itemWeight": {"columns": 2},
    # The horizontal indicator is only configurable on a horizontal scroller —
    # sjui gates both hosts on it (scrollview_converter.rb:58,
    # collection_converter.rb:1753). Unscoped: Collection and ScrollView both
    # declare the attribute and both have the gate.
    "showsHorizontalScrollIndicator": {"orientation": "horizontal"},
    # `errorImage` / `loadingImage` on a NON-network Image are fallback
    # imagery for a missing `src`, never an in-flight or failed state (kjui
    # image_component.rb:12-15 says so in its own words) — they are read only
    # in the `src`-absent arm (sjui image_converter.rb:36/42). The base
    # supplies `src`, so the fallback arm was unreachable.
    "Image.errorImage": {"src": None},
    "Image.loadingImage": {"src": None},
    # `hidesWhenStopped` decides what a STOPPED indicator does — keep its space
    # or collapse out of the layout — so it is only ever read on the
    # `animating == false` branch (sjui indicator_converter.rb:23, kjui
    # indicator_component.rb:13). `animating` defaults to true, and Indicator
    # has no BASE_ATTRS entry, so the fixture was always a spinning indicator
    # and the branch was unreachable. Unblocked by E declaring `animating`
    # (the attribute existed in three converters and in no schema).
    "Indicator.hidesWhenStopped": {"animating": False},
    # kjui puts the label on whichever side `labelPosition` names, but only on
    # the labelled path (switch_component.rb:144/170) — and a Switch's label is
    # `labelAttributes.text`. Switch has no BASE_ATTRS entry at all, so there
    # was no label to place.
    "Switch.labelPosition": {"labelAttributes": {"text": "Sample"}},
    # SwiftUI has no maximum-length primitive, so sjui enforces maxLength by
    # truncating on change and writing BACK — which needs somewhere to write:
    # `return unless raw.is_a?(String) && is_binding?(raw)` on the text
    # (textfield_converter.rb:519, and its own comment at 511-513). The base is
    # hint-only, with no bound text.
    "TextField.maxLength": {"text": "@{inputText}"},
    # Same parent-axis rule as `weight` below, and the same fix: B measured
    # that all three read these once the parent has an orientation. They were
    # filed as "the codegen does not read the spelling" when the fixture was
    # not letting it.
    # A gradient DIRECTION needs a gradient to point. B measured it: with no
    # `gradient` the converter emits nothing at all; with one it emits
    # `.background(LinearGradient(colors: [...], startPoint:, endPoint:))`.
    "View.gradientDirection": {"gradient": ["#FF0000", "#0000FF"]},
    "widthWeight": {"root.orientation": "horizontal"},
    # `height: 0` is not decoration — it is how you say "the weight decides
    # this axis". kjui spells the rule out: `explicit_height` is false only
    # when `heightWeight && height == 0`, and an explicit height wins over the
    # weight branch entirely (modifier_builder.rb:404-421). With the base's
    # 200pt height the weight branch was unreachable on Compose, which is why
    # iOS cleared on the orientation alone and android did not.
    # NOTE `height: 0` was here and had to come out. kjui needs it — an
    # explicit height beats the weight branch entirely — but it only means
    # "the weight decides this axis" WHEN A WEIGHT IS PRESENT, and the control
    # by definition has no `heightWeight`. sjui says so exactly:
    # `should_ignore_height` is `height == 0 AND (weight || heightWeight)`
    # (frame_helper.rb:127), so on the control the zero survived into a real
    # frame request and the control drew nothing — parity distance 35 between
    # the two iOS paths, and every comparison against that control inherited
    # it.
    #
    # A control that renders differently from every fixture it controls is
    # worse than a weaker fixture: it moves the baseline the other comparisons
    # subtract. The android C1/C2 finding this was chasing is owned by C
    # anyway (`build_weight` never reads `heightWeight`), so the fixture gives
    # up nothing real by dropping it.
    "heightWeight": {"root.orientation": "vertical"},
    "maxWidthWeight": {"root.orientation": "horizontal"},
    "minWidthWeight": {"root.orientation": "horizontal"},
    "maxHeightWeight": {"root.orientation": "vertical"},
    "minHeightWeight": {"root.orientation": "vertical"},
    # `weight` is a share of the PARENT's main axis, and every platform gates
    # it on that parent being a Row/Column (kjui modifier_builder.rb:105
    # `parent_orientation`, sjui view_converter.rb:160). The fixture root is a
    # plain View — an overlay — so there was no axis to take a share of. The
    # `root.` prefix puts the orientation on the ROOT node rather than on the
    # target (see `split_root_attrs`).
    #
    # A share also needs a COMPETITOR: a lone weighted child takes all the
    # leftover space whatever its weight says, so 1 and '2' drew one picture
    # on all three platforms (run 5). The backdrop sibling holds weight 1
    # against the target's value; its width is 0 — the width-0-plus-weight
    # pairing every platform special-cases — so the boundary between the two
    # is set by the ratio alone. The target's own 200pt width is untouched:
    # the control has no weight, and a zero-size control draws nothing (the
    # heightWeight lesson).
    "weight": {
        "root.orientation": "horizontal",
        "root.backdrop": [
            {"type": "View", "id": "rival", "width": 0, "height": 200,
             "weight": 1, "background": "#334455"},
        ],
    },
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


#: Extra cases that carry their OWN base attributes, keyed by
#: ``(section, attribute)`` -> ``{case_suffix: extra_base}``.
#:
#: A plain :data:`EXTRA_CASES` value shares the attribute's base, which is the
#: right default. This is for the case where the SAME attribute has to be
#: measured under two different declarations at once — and the existing fixture
#: must keep its name, because `attribute_semantics.json#observable` records a
#: verdict PER FIXTURE NAME. Rewriting a fixture in place would leave the
#: ledger quietly asserting the old verdict about the new layout.
VARIANT_CASES: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
    # `borderStyle` alone draws nothing — a border is summoned by the
    # borderWidth+borderColor pair — so the lone fixtures are correctly inert
    # and `observable` records them as `uniformly-inert`. That left the three
    # implementations landed in this wave (B: iOS dashed/dotted, C: android,
    # A: web TailwindMapper#map_border_style) with NO fixture that could show
    # them working: the suite would report "inert on all three", the ledger
    # would agree, and nothing would ever contradict it.
    #
    # The `_with_border` variant declares the pair, so the style has a border
    # to modify. Both live side by side under different names, so both verdicts
    # stay true. E owns the `observable` entry for the active side.
    ("common", "borderStyle"): {
        "with_border": {"borderWidth": 2, "borderColor": "#FF0000"},
    },
    # A LONE radio behaves the same however `checked` is prioritised against
    # the group's selection state, so the existing fixture sees nothing; the
    # behaviours only diverge once the radio belongs to a group. The failure is
    # loud — `checked: true` with a group produced a radio that never switched
    # again.
    #
    # What this fixture guards is the RENDER stage, not the codegen priority:
    # C pinned all five orderings in `radio_component_spec.rb` (133ff58), so a
    # reverted priority fails a unit spec immediately. What a unit pin cannot
    # see is whether the LIBRARY honours the expression the codegen emitted —
    # the dynamic side of the same question G fixed with `value ?? id`. That is
    # the parity this pair measures.
    ("Radio", "checked"): {
        "with_group": {"group": "conformance_group"},
    },
    # B isolated the real crash and it is narrower than either of us wrote
    # down: a numeric `fontWeight` alone generates fine, `partialAttributes`
    # alone generates fine, and only the PAIR raised NoMethodError — the
    # partial path reached label_converter's private copy of the weight
    # vocabulary and called `.downcase` on an Integer (fixed in 2b58e99).
    #
    # `fontWeight__600` proves the numeric value is READ. It does not
    # reproduce the build failure; only this variant does. Both faces get the
    # pairing, because `"bold"` with partials is the control for it.
    ("Label", "fontWeight"): {
        "with_partial": {
            "partialAttributes": [
                {"range": [0, 3], "fontColor": "#FF0000"},
            ],
        },
    },
}

#: A SECOND bound case for an attribute, declared under a different data class.
#:
#: Union-typed attributes are read one way by the generated Data type and
#: another by the view — B found `Button.fontWeight` holding an Int while the
#: view matched a string vocabulary, and two more like it, one of which failed
#: the build. B then put the adjudication in a single place, and reported that
#: the generalisation changed not one byte of output, "because no fixture
#: declares a numeric property as String". This is that fixture.
#:
#: One representative is the point, not coverage: crossing "attribute" with
#: "declared class" multiplies the suite, and the defect only needs a fixture
#: that would notice it coming back.
BOUND_UNION_CASES: dict[tuple[str, str], str] = {
    # `weight` is declared `["number", "string", "binding"]`, so a String-typed
    # property holding "1" is a legal spelling — and the exact shape that had
    # the Data type and the view disagreeing.
    ("common", "weight"): "String",
}

#: Case name and seed for the union probe above.
BOUND_UNION_CASE_SUFFIX = "binding_as_string"
BOUND_UNION_SEED = "1"


def bound_union_case_for(section: str, attribute: str) -> CasePlan | None:
    """The union-typed bound case, or None."""
    if (section, attribute) not in BOUND_UNION_CASES:
        return None
    prop = f"{bound_prop_name(attribute)}Str"
    return CasePlan(
        name=BOUND_UNION_CASE_SUFFIX,
        value=f"@{{{prop}}}",
        written_key=attribute,
    )


def bound_union_data_entry(section: str, attribute: str) -> dict[str, Any] | None:
    """The ``data`` declaration the union probe needs."""
    cls = BOUND_UNION_CASES.get((section, attribute))
    if cls is None:
        return None
    return {
        "name": f"{bound_prop_name(attribute)}Str",
        "class": cls,
        "defaultValue": BOUND_UNION_SEED,
    }


def variant_bases_for(section: str, attribute: str) -> dict[str, dict[str, Any]]:
    """``{case_suffix: extra_base}`` declared for this attribute."""
    return VARIANT_CASES.get((section, attribute), {})


#: Extra base attributes for ONE case of an attribute, keyed by
#: ``(section, attribute, case_name)``.
#:
#: :data:`VARIANT_CASES` repeats every case under a suffix; this replaces the
#: base of a case that already exists. Needed when the values of a single enum
#: want incompatible fixtures — which `distribution` does, in a way that is
#: geometric rather than incidental:
#:
#:   fill / fillEqually    are instructions to the CHILD's axis, and E's `size`
#:                         adjudication orders explicit > bounds > fill, so a
#:                         child with an explicit width correctly ignores them.
#:                         They need children with no declared width.
#:   equalSpacing /        distribute the space BETWEEN children, so the
#:   equalCentering        children have to occupy space to be spaced apart.
#:                         They need the explicit-width boxes.
#:
#: One child set cannot serve both. And children of EQUAL intrinsic width
#: cannot separate `fill` from `fillEqually` either — both end up thirds of the
#: row — so the fill children are Labels of different text lengths: `fill`
#: consumes the axis while keeping their proportions, `fillEqually` flattens
#: them to equal shares.
_FILL_CHILDREN = [
    {"type": "Label", "id": "box_a", "text": "A", "background": "#FF0000"},
    {"type": "Label", "id": "box_b", "text": "BBBB", "background": "#0000FF"},
    {"type": "Label", "id": "box_c", "text": "CCCCCCCC", "background": "#00AA00"},
]

CASE_BASE_ATTRS: dict[tuple[str, str, str], dict[str, Any]] = {
    ("common", "distribution", "fill"): {"child": _FILL_CHILDREN},
    ("common", "distribution", "fillequally"): {"child": _FILL_CHILDREN},
    ("View", "distribution", "fill"): {"child": _FILL_CHILDREN},
    ("View", "distribution", "fillequally"): {"child": _FILL_CHILDREN},
    # The horizontal direction values act on a horizontal axis (the canonical
    # UIKit contract reverses along the orientation axis only), so they get a
    # row: on the shared vertical base both were designed no-ops, and the
    # value pair bottomToTop/rightToLeft could only ever be told apart by an
    # implementation that ignores the axis — which is a library bug to catch
    # in the library's tests, not a picture this suite can hold once each
    # value sits on its own axis.
    ("View", "direction", "righttoleft"): {"orientation": "horizontal"},
    ("View", "direction", "lefttoright"): {"orientation": "horizontal"},
}


def base_attrs_for(host: str, attribute: str, case_name: str = "") -> dict[str, Any]:
    """Extra base attributes that make `attribute` observable on `host`.

    Keys are either scoped to a component (`Label.highlightColor`) or apply to
    the attribute wherever it appears (`flexWrap`); scoped wins. The scoping
    matters when two components share an attribute name and only one has the
    driver — injecting `selected` into a Button fixture would put an attribute
    Button does not declare into the layout.

    A value of ``None`` REMOVES the base key instead of adding one — see
    :func:`apply_base_overrides`.

    *case_name* selects a :data:`VARIANT_CASES` overlay when the case is one of
    the attribute's variant cases; the overlay is merged ON TOP of the shared
    extras, so a variant inherits whatever the attribute already needed.
    """
    scoped = BASE_ATTRS_BY_ATTRIBUTE.get(f"{host}.{attribute}")
    shared = scoped if scoped is not None else BASE_ATTRS_BY_ATTRIBUTE.get(attribute, {})

    if not case_name:
        return shared
    # A case-scoped base replaces the shared one for that case only.
    for section in (host, "common" if host == DEFAULT_COMMON_HOST else host):
        case_extra = CASE_BASE_ATTRS.get((section, attribute, case_name))
        if case_extra is not None:
            return {**shared, **case_extra}
    # `View` hosts both its own section and `common`, so both keys are checked.
    for section in (host, "common" if host == DEFAULT_COMMON_HOST else host):
        for suffix, overlay in VARIANT_CASES.get((section, attribute), {}).items():
            if case_name == suffix or case_name.endswith(f"_{suffix}"):
                return {**shared, **overlay}
    return shared


#: Prefix marking a companion that belongs on the ROOT node, not the target.
ROOT_ATTR_PREFIX = "root."


def apply_base_overrides(base: dict[str, Any], extra: dict[str, Any] | None) -> None:
    """Merge *extra* into *base*, treating ``None`` as "drop this base key".

    Adding attributes is not always what makes a fixture observable —
    sometimes the base is what hides it. `TextField.placeholder` is declared
    as an alias of `hint`, and the base injects `hint: "Sample"`, so the
    fixture carried both spellings: the primary won and the alias could never
    move a pixel however correctly it resolved. Removal is the fix, and it
    has to travel with the CONTROL too, or the pair stops being comparable.

    ``root.``-prefixed keys are skipped here: they configure the fixture's
    ROOT node (see :func:`split_root_attrs`), not the component under test.
    """
    for key, value in (extra or {}).items():
        if key.startswith(ROOT_ATTR_PREFIX):
            continue
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value


#: `root.` keys that describe the root's CHILDREN rather than its attributes.
#: Handled structurally by the layout builders; never written as JSON keys.
ROOT_STRUCTURE_KEYS = ("backdrop", "anchorLast")


def root_backdrop(extra: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Nodes to place BEHIND the target, in the root's own child list.

    A root with no orientation is an overlay, so an earlier sibling sits
    underneath. `Blur` needs one: `backdrop-filter` blurs what is behind the
    element, and a flat colour blurs to the same flat colour — the fixture and
    its control came out identical no matter what radius was asked for.
    """
    return [dict(n) for n in (split_root_attrs(extra).get("backdrop") or [])]


def root_anchor_last(extra: dict[str, Any] | None) -> bool:
    """True when the anchor must be emitted AFTER the target.

    `indexAbove` raises the target above the referenced view, and the anchor is
    normally emitted first — so the target was already on top and raising it
    changed nothing. Emitting the anchor last is what gives the attribute
    somewhere to travel from. (`indexBelow` works precisely because of the
    default order, which is why only one of the pair was ever inert.)
    """
    return bool(split_root_attrs(extra).get("anchorLast"))


def split_root_attrs(extra: dict[str, Any] | None) -> dict[str, Any]:
    """The ``root.``-prefixed companions in *extra*, with the prefix stripped.

    Some attributes are read off the PARENT rather than off the node that
    declares them — `weight` is a share of the parent's main axis, and every
    platform ignores it unless that parent is a Row/Column. Nothing the
    fixture writes on the target can create that condition, so the companion
    has to land on the root.

    They ride the same table (and therefore the same shape name) as the target
    companions, so a fixture whose root was widened is still compared against a
    control widened the same way.
    """
    return {
        key[len(ROOT_ATTR_PREFIX):]: value
        for key, value in (extra or {}).items()
        if key.startswith(ROOT_ATTR_PREFIX)
    }


def root_node_attrs(extra: dict[str, Any] | None) -> dict[str, Any]:
    """:func:`split_root_attrs` minus the structural keys.

    Only these belong in the root node's own JSON; `backdrop` and `anchorLast`
    describe its children and are consumed by the builders.
    """
    return {
        k: v
        for k, v in split_root_attrs(extra).items()
        if k not in ROOT_STRUCTURE_KEYS
    }


#: ``@{name}`` binding companions whose data property is not a String.
#:
#: Empty today: every companion binding is String on all three codegen paths
#: (`data.inputText.count` / `String(newValue.prefix(n))` on iOS,
#: `data.pickedDate.toDate(format:)` for the date companion). A class outside
#: the narrow cross-platform vocabulary — `String` / `Int` / `Boolean` /
#: `CollectionDataSource` — does not survive kjui's `map_to_kotlin_type`,
#: which passes unknown classes through verbatim into Kotlin source.
BINDING_DATA_CLASSES: dict[str, str] = {
    # Collection.scrollTo carries a cell INDEX unless cellIdProperty names an
    # id, and the SSoT now says so in those words. `Int` is in the four-class
    # vocabulary that survives all three generators.
    "scrollTarget": "Int",
}


def _fits(value: Any, cls: str) -> bool:
    if cls == "Boolean":
        return isinstance(value, bool)
    if cls == "Int":
        return isinstance(value, int) and not isinstance(value, bool)
    if cls == "Double":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str)


def bound_data_entry(
    section: str, attribute: str, default: Any = None
) -> dict[str, Any] | None:
    """The ``data`` declaration a bound case needs, or None.

    Without it the generated view reads `data.<prop>` off a Data type that has
    no such member and the codegen host does not compile — kjui and sjui derive
    the type from this section alone.
    """
    cls = BOUND_CASE_CLASSES.get((section, attribute))
    if cls is None or (section, attribute) in BOUND_CASES_BLOCKED:
        return None
    # Seed the property with the LITERAL case's value, so the bound fixture is
    # asking for exactly what its literal twin asks for. A zero seed would make
    # every bound fixture render the platform default, i.e. its control — the
    # binding would resolve perfectly and still measure nothing.
    seed = default if _fits(default, cls) else _BINDING_DATA_DEFAULTS.get(cls, "")
    return {"name": bound_prop_name(attribute), "class": cls, "defaultValue": seed}

#: Binding companions that feed a TWO-WAY control, mapped to the class of the
#: change handler the generated code calls back into.
#:
#: Declaring a property in the layout's `data` section makes rjui use the
#: declaration verbatim and SKIP its own inference — so a companion that drives
#: a controlled input has to name both halves of the two-way pair or the
#: generated component calls `data.on<Prop>Change?.(...)` against a Data type
#: that has no such member (`tsc --noEmit`, 49-D round 3: Fx0326 / Fx0536).
#:
#: rjui infers the handler for TextField's text binding but not for SelectBox's
#: date binding — that asymmetry is reported to lane A. This table is the
#: fixture side of it, and stays correct either way: the handler belongs in the
#: declaration of a two-way binding.
BINDING_CHANGE_HANDLERS: dict[str, str] = {
    # SelectBox.selectedDate — `onChange` writes the reformatted string back.
    "pickedDate": "(String) -> Void",
}


def _change_handler_name(prop: str) -> str:
    """rjui's two-way partner for *prop*: ``pickedDate`` -> ``onPickedDateChange``."""
    return f"on{prop[:1].upper()}{prop[1:]}Change"

_BINDING_RE = re.compile(r"^@\{([A-Za-z_][A-Za-z0-9_]*)\}$")

#: Default class for an auto-declared binding companion.
BINDING_DATA_DEFAULT_CLASS = "String"

#: Default value per declared class, so the generated Data type compiles.
_BINDING_DATA_DEFAULTS: dict[str, Any] = {
    "String": "",
    "Int": 0,
    "Double": 0.0,
    "Boolean": False,
}


def binding_data_entries(
    attrs: dict[str, Any], already_declared: set[str]
) -> list[dict[str, Any]]:
    """``data`` entries for every ``@{name}`` companion in *attrs*.

    kjui and sjui derive the generated Data type from the layout's ``data``
    section ONLY — they never infer a property from a binding expression — so a
    companion like ``{"text": "@{inputText}"}`` produces a view that reads
    ``data.inputText`` off a class with no such property, and the codegen host
    does not compile. Declaring the property is what makes the companion
    usable at all.

    Only *companion* bindings are declared: the value under test comes from the
    case plan, and the static fixture suite never writes a binding there.
    """
    entries: list[dict[str, Any]] = []
    seen = set(already_declared)
    for value in attrs.values():
        if not isinstance(value, str):
            continue
        match = _BINDING_RE.match(value.strip())
        if match is None:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        cls = BINDING_DATA_CLASSES.get(name, BINDING_DATA_DEFAULT_CLASS)
        entries.append(
            {"name": name, "class": cls, "defaultValue": _BINDING_DATA_DEFAULTS.get(cls, "")}
        )
        handler_cls = BINDING_CHANGE_HANDLERS.get(name)
        if handler_cls is not None:
            handler = _change_handler_name(name)
            if handler not in seen:
                seen.add(handler)
                # No defaultValue: a handler is supplied at runtime, and the
                # codegens emit it as an optional callback member.
                entries.append({"name": handler, "class": handler_cls})
    return entries


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
    # Three boxes, not one: `orientation` chooses between a row and a column,
    # and one child renders the same picture either way (lane A §5(4)).
    "SafeAreaView": [
        {"type": "View", "id": "box_a", "width": 40, "height": 40, "background": "#FF0000"},
        {"type": "View", "id": "box_b", "width": 40, "height": 40, "background": "#0000FF"},
        {"type": "View", "id": "box_c", "width": 40, "height": 40, "background": "#00AA00"},
    ],
    # The tall block is what makes the scroller scroll; the two beside it are
    # what makes its orientation visible.
    "ScrollView": [
        {"type": "View", "id": "content", "width": 150, "height": 600, "background": "#FF0000"},
        {"type": "View", "id": "content_b", "width": 150, "height": 80, "background": "#0000FF"},
        {"type": "View", "id": "content_c", "width": 150, "height": 80, "background": "#00AA00"},
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
    # `effectStyle`'s enum IS the UIBlurEffect vocabulary — Light, Dark,
    # ExtraLight, systemThinMaterial … — and a bare View has no blur to style,
    # so the probe emitted nothing and the spelling read as unread. B measured
    # both hosts: View emits nothing, Blur emits `.preferredColorScheme(.dark)`.
    #
    # `Blur` already declares `effectStyle` in its own section, so the `common`
    # copy is a duplicate; whether the declaration should move there is E's
    # call, and hosting the common fixture on Blur is correct either way — a
    # blur effect style is only meaningful on something that blurs.
    "effectStyle": "Blur",
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
        # The array face of `onclick` is measurable and is NOT here — it is
        # held in ARRAY_FACE_BLOCKED, because emitting it breaks two of the
        # three generators outright. See that table.
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

    # The user ruling above: UIKit-only attributes are not photographed, so the
    # plan stops claiming visual coverage before anything downstream reads it —
    # the control, the screenshot step and the counts all follow from `cls`.
    if cls == CLASS_VISUAL and is_uikit_only(defn):
        cls = CLASS_DECLARATION_ONLY

    cases = _with_alias_cases(section, attribute, defn, cases)

    # The bound case goes last: it must never be the representative (`primary`
    # is the literal form, which is what the C0/C2 checks compare), and the
    # alias probes mirror the first case, not this one.
    bound = bound_case_for(
        section, attribute, cases[0].assertions if cls == CLASS_ASSERTABLE else ()
    )
    # A boolean attribute planned exactly ONE literal case, and which one
    # depended on whichever value the representative tables happened to pick.
    # That is thin on its own — half the attribute's domain untested — and it
    # bites in two specific ways:
    #
    #   * the codegen differential looks for its "second value" in the case
    #     list, so with one literal it landed on the bound case and compared a
    #     literal against a `@{...}` expression. That is the C1 question, not
    #     C2; it filed nine android booleans as "emits a constant" with nothing
    #     wrong with them, and it MASKED two real findings by going the other
    #     way.
    #   * a contract pinned to `__true` silently stops being checked when the
    #     representative flips to `false`. `TabView/showLabels__true` is
    #     recorded in `attribute_semantics.json#skinIdioms` and has not existed
    #     in the manifest since the representative round — a dead contract, and
    #     no number of measurement rounds would have surfaced it, because the
    #     fixture it names is not there to measure. (Found by E.)
    #
    # Both close the same way: a boolean plans both of its values, always.
    # Count only the BOOLEAN literals. Counting every literal made the rule
    # stop firing the moment an attribute gained a non-boolean extra case —
    # adding `underline__styled` silently deleted `underline__false`, which is
    # exactly the dead-contract shape this rule exists to prevent.
    bool_literals = [
        c for c in cases if c.alias_of is None and isinstance(c.value, bool)
    ]
    if len(bool_literals) == 1:
        cases.append(
            CasePlan(
                name=str(not bool_literals[0].value).lower(),
                value=not bool_literals[0].value,
                written_key=attribute,
                assertions=bool_literals[0].assertions,
            )
        )

    union = bound_union_case_for(section, attribute)
    if bound is not None:
        cases.append(bound)
    if union is not None:
        cases.append(union)

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


def _prefer_primary(section: str, attribute: str, cases: list[CasePlan]) -> list[CasePlan]:
    """Move the declared representative case to the front, if one is declared.

    The set of fixtures is unchanged — only which one is the attribute's
    representative (see :data:`PREFERRED_PRIMARY_CASE`).
    """
    preferred = PREFERRED_PRIMARY_CASE.get((section, attribute))
    if preferred is None:
        return cases
    index = next((i for i, c in enumerate(cases) if c.value == preferred), None)
    if index is None or index == 0:
        return cases
    return [cases[index]] + cases[:index] + cases[index + 1:]


def canonical_enum_values(defn: dict, enum_values: list[Any]) -> list[Any]:
    """*enum_values* with the ``valueAliases`` spellings removed.

    ``valueAliases`` maps a non-canonical spelling to the canonical one, and
    the L1 normalizer rewrites it before any converter sees it — so an alias
    fixture renders the canonical value's picture a second time. Nine spellings
    across three platforms is 27 screenshots of something already covered, and
    `Collection.layout` alone was shooting three of them.

    Alias RESOLUTION still gets its regression probe: `_with_alias_cases`
    covers the attribute-name aliases, and the value aliases are checked where
    they are implemented — in the normalizer, not the camera.
    """
    aliases = defn.get("valueAliases")
    if not isinstance(aliases, dict) or not aliases:
        return enum_values
    return [v for v in enum_values if v not in aliases]


def _visual_cases(section: str, attribute: str, defn: dict) -> list[CasePlan]:
    """Enum values expand into one case each; scalars get a single case."""
    base_types, enum_values = normalize_type(defn)
    enum_values = canonical_enum_values(defn, enum_values)
    cases: list[CasePlan] = []

    for name, value in dedupe_case_names(enum_values):
        cases.append(CasePlan(name=name, value=value, written_key=attribute))

    if enum_values and not ({"number", "boolean"} & base_types):
        # Enum fully covers string-typed attributes.
        return _with_variant_cases(
            section, attribute, _prefer_primary(section, attribute, cases)
        )

    found, value = representative_value(section, attribute, defn)
    if found:
        if isinstance(value, bool):
            # Name from the VALUE, not from the type. Hard-coding `True` here
            # meant a boolean attribute whose platform default is already true
            # could not be given a non-default representative at all — the
            # override was read and then thrown away, and the fixture went on
            # rendering exactly what its control rendered.
            cases.append(
                CasePlan(name=str(value).lower(), value=value, written_key=attribute)
            )
        else:
            cases.append(CasePlan(name="static", value=value, written_key=attribute))

    # Second (third...) value from a vocabulary the SSoT does not enumerate:
    # the case name is the value's own slug, so it stays greppable and stable.
    # A (name, value) tuple names the case explicitly — needed for dict values,
    # whose stringified slug would otherwise become the filename.
    declared = EXTRA_CASES.get((section, attribute), [])
    named = [v for v in declared if isinstance(v, tuple)]
    for name, extra in dedupe_case_names([v for v in declared if not isinstance(v, tuple)]):
        cases.append(CasePlan(name=name, value=extra, written_key=attribute))
    for name, extra in named:
        cases.append(CasePlan(name=name, value=extra, written_key=attribute))

    return _with_variant_cases(
        section, attribute, _prefer_primary(section, attribute, cases)
    )


def _with_variant_cases(
    section: str, attribute: str, cases: list[CasePlan]
) -> list[CasePlan]:
    """Repeat every case under each VARIANT_CASES suffix.

    Appended last so a variant never becomes the representative — `primary`
    still means the plain declaration.
    """
    out = list(cases)
    for suffix in variant_bases_for(section, attribute):
        for case in cases:
            if case.alias_of is not None:
                continue
            out.append(
                CasePlan(
                    name=f"{case.name}_{suffix}",
                    value=case.value,
                    written_key=case.written_key,
                    assertions=case.assertions,
                )
            )
    return out


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
