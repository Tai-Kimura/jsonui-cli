"""Schema definitions for JsonUI test files."""

# Supported platform values
# - "ios": Generic iOS (auto-detects SwiftUI/UIKit, uses fallback)
# - "ios-swiftui": iOS with SwiftUI (uses accessibilityIdentifier pattern for tabs)
# - "ios-uikit": iOS with UIKit (uses UITabBarController directly)
# - "android": Android (Compose with testTag)
# - "web": Web (React with HTML id attribute)
# - "all": All platforms
SUPPORTED_PLATFORMS = ["ios", "ios-swiftui", "ios-uikit", "android", "web", "all"]

# Platform values allowed in condition objects (when / repeat.while)
CONDITION_PLATFORMS = ["ios", "android", "web", "all"]
# Platform values allowed inside a condition platform array (no "all")
CONDITION_PLATFORM_ARRAY_ITEMS = ["ios", "android", "web"]

# Named responsive size-class buckets (condition 'responsive' / case-level 'responsive').
# Canonical vocabulary is the render-side SSoT — shared/core/responsive_resolver.rb
# (jsonui-cli) / attribute_definitions.json 'responsive' attribute: compact / medium /
# regular / landscape + hyphenated orientation combos. Each driver resolves a named
# bucket the way its platform's renderer does; do NOT add names the renderer never emits.
RESPONSIVE_BUCKETS = [
    "compact", "medium", "regular", "landscape",
    "compact-landscape", "medium-landscape", "regular-landscape"
]

# Keys allowed in a responsive constraint object (the width-based escape hatch).
# Widths/heights are numbers >= 0 in dp (Android) / pt (iOS) / logical px (web).
RESPONSIVE_CONSTRAINT_KEYS = ["minWidth", "maxWidth", "minHeight", "maxHeight", "orientation"]

# Valid orientation values (responsive constraint 'orientation' / setOrientation action)
RESPONSIVE_ORIENTATIONS = ["portrait", "landscape"]

# Cross-platform supported actions and their required/optional parameters
SUPPORTED_ACTIONS = {
    "tap": {
        "description": "Tap on an element",
        "required": ["id"],
        "optional": ["text", "retryTapIfNoChange", "timeout"]
    },
    "doubleTap": {
        "description": "Double tap on an element",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "longPress": {
        "description": "Long press on an element",
        "required": ["id"],
        "optional": ["duration", "timeout"]
    },
    "input": {
        "description": "Input text into a field",
        "required": ["id", "value"],
        "optional": ["timeout"]
    },
    "typeText": {
        "description": "Type text into the currently-focused field via the keyboard "
                       "(no element id; for focused-but-untargetable fields such as "
                       "invisible code-entry inputs)",
        "required": ["value"],
        "optional": ["timeout"]
    },
    "clear": {
        "description": "Clear text from an input field",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "scroll": {
        "description": "Scroll within an element",
        "required": ["id", "direction"],
        "optional": ["amount", "timeout"]
    },
    "scrollUntilVisible": {
        "description": "Scroll until the target element becomes visible",
        "required": ["id"],
        "optional": ["container", "direction", "timeout"]
    },
    "swipe": {
        "description": "Swipe gesture on an element",
        "required": ["id", "direction"],
        "optional": ["timeout"]
    },
    "waitFor": {
        "description": "Wait for an element to appear",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "waitForAny": {
        "description": "Wait for any of multiple elements to appear",
        "required": ["ids"],
        "optional": ["timeout"]
    },
    "wait": {
        "description": "Wait for a specified duration",
        "required": ["ms"],
        "optional": []
    },
    "back": {
        "description": "Navigate back",
        "required": [],
        "optional": []
    },
    "hideKeyboard": {
        "description": "Dismiss the soft keyboard if one is visible (no-op when none). "
                       "Needed when the keyboard covers the tap target and the field type "
                       "has no return key (e.g. number-pad).",
        "required": [],
        "optional": []
    },
    "screenshot": {
        "description": "Take a screenshot",
        "required": ["name"],
        "optional": []
    },
    "alertTap": {
        "description": "Tap a button in a native alert dialog",
        "required": ["button"],
        "optional": ["timeout"]
    },
    "selectOption": {
        "description": "Select an option from a select/dropdown element (Web: standard select, iOS/Android: SelectBox picker)",
        "required": ["id"],
        "optional": ["value", "label", "index", "timeout"]
    },
    "tapItem": {
        "description": "Tap an item at a specific index in a collection (CollectionView, List, etc.)",
        "required": ["id", "index"],
        "optional": ["timeout"]
    },
    "selectTab": {
        "description": "Select a tab by index in a TabView/TabBar (tab is resolved as {id}_tab_{index})",
        "required": ["id", "index"],
        "optional": ["timeout"]
    },
    "readText": {
        "description": "Read the element's text into a runtime variable (referenced later as @{name})",
        "required": ["id", "variable"],
        "optional": ["timeout"]
    },
    "repeat": {
        "description": "Repeat a block of steps ('times' and/or 'while' condition)",
        "required": ["steps"],
        "optional": ["times", "while"]
    },
    "retry": {
        "description": "Retry a block of steps when any step inside fails",
        "required": ["steps"],
        "optional": ["maxRetries"]
    },
    "setLocation": {
        "description": "Set the mock device/browser geolocation",
        "required": ["latitude", "longitude"],
        "optional": []
    },
    "addMedia": {
        "description": "Provide media/files to the app: Android inserts into the device "
                       "gallery (paths resolve against the on-device media fixtures dir); "
                       "iOS seeds the simulator photo library via PhotoKit (simulator only; "
                       "paths resolve inside the UITest bundle — use basenames; the runner "
                       "needs a photos-add pre-grant, see `jsonui-test pregrant`); "
                       "Web sets the files on a file input (step 'id' targets the "
                       "input or an element containing one; without 'id', the page's first "
                       "input[type=file]; paths resolve relative to the test file). "
                       "Seeding accumulates across runs — assert existence/app state, not counts.",
        "required": ["paths"],
        "optional": ["id", "timeout"]
    },
    "setMocks": {
        "description": "Switch API mock scenarios (map of operationId -> scenario name). "
                       "In flow tests, call before navigating so the next screen fetches the new response.",
        "required": ["mocks"],
        "optional": []
    },
    "setViewport": {
        "description": "Resize the viewport to sweep responsive breakpoints (Web only; "
                       "iOS/Android no-op with a warning — pair dependent asserts with "
                       "a matching 'when.responsive' so they skip cleanly)",
        "required": ["width", "height"],
        "optional": []
    },
    "setOrientation": {
        "description": "Rotate to the given orientation (iOS: XCUIDevice, Android: UiDevice, "
                       "Web: swaps viewport width/height in mobile-emulation contexts, else no-op with a warning)",
        "required": ["orientation"],
        "optional": []
    },
    "emitHook": {
        "description": "Call a browser-side hook the app registered on "
                       "window.__jsonuiTestHooks (e.g. an RTDB mock emitter): "
                       "hookArgs are passed positionally. Web only; iOS/Android "
                       "no-op with a warning — gate dependent steps with "
                       "'when.platform: web'.",
        "required": ["name"],
        "optional": ["hookArgs"]
    }
}

# Cross-platform supported assertions and their required/optional parameters
# All assertions accept an optional 'timeout' (auto-wait polling).
SUPPORTED_ASSERTIONS = {
    "visible": {
        "description": "Assert element is visible",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "notVisible": {
        "description": "Assert element is not visible",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "enabled": {
        "description": "Assert element is enabled",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "disabled": {
        "description": "Assert element is disabled",
        "required": ["id"],
        "optional": ["timeout"]
    },
    "text": {
        "description": "Assert element text matches",
        "required": ["id"],
        "optional": ["equals", "contains", "timeout"]
    },
    "count": {
        "description": "Assert element count",
        "required": ["id", "equals"],
        "optional": ["timeout"]
    },
    "state": {
        "description": "Assert ViewModel state value (requires a state provider)",
        "required": ["path", "equals"],
        "optional": ["timeout"]
    },
    "screenshot": {
        "description": "Visual regression: compare capture against a named baseline",
        "required": ["name"],
        "optional": ["cropId", "threshold", "timeout"]
    },
    "openedUrl": {
        "description": "Assert the most recent window.open call (recorded by the "
                       "runner's spy) — 'equals' or 'contains' is required. Web only; "
                       "gate with 'when.platform: web' in cross-platform tests.",
        "required": [],
        "optional": ["equals", "contains", "timeout"]
    },
    "screen": {
        "description": "Assert the named screen is displayed (matched through the "
                       "screen marker code generation emits). Does NOT assert "
                       "exclusivity: embedded screens, split panes and tab hosts "
                       "legitimately show several screens at once. The target is "
                       "'name' — the step-level 'screen' key says where the step "
                       "runs, and during a transition the two differ.",
        "required": ["name"],
        "optional": ["timeout"]
    }
}

# Valid direction values
VALID_DIRECTIONS = ["up", "down", "left", "right"]

# Common step attributes accepted on every action/assertion.
# NOTE: on selectOption, 'label' keeps its legacy meaning (option text to select).
COMMON_STEP_ATTRIBUTES = ["label", "optional", "when"]

# Valid keys in a condition object (when / repeat.while). Unknown keys are errors.
VALID_CONDITION_KEYS = ["visible", "notVisible", "platform", "responsive", "state"]

# Valid keys in a condition 'state' object
VALID_CONDITION_STATE_KEYS = ["path", "equals"]

# Valid keys in the root-level 'launch' object
VALID_LAUNCH_KEYS = ["clearState", "permissions", "arguments"]

# Cross-platform permission names for launch.permissions
VALID_PERMISSION_NAMES = [
    "camera", "microphone", "location", "notifications",
    "photos", "contacts", "calendar", "bluetooth"
]

# Valid permission values
VALID_PERMISSION_VALUES = ["allow", "deny", "unset"]

# Valid top-level keys, per test type. Each list mirrors the corresponding
# schema's top-level `properties` (additionalProperties: false there, so an
# unknown key is an error). The lists are deliberately separate: a key from
# the *other* type's list means the file is probably the wrong test type,
# which the validators report with a pointed message. test_schema_drift.py
# pins both lists to the vendored schemas.
VALID_SCREEN_TOP_LEVEL_KEYS = [
    "$schema", "type", "source", "metadata", "platform", "embeddedIn",
    "initialState", "launch", "mocks", "screenReady", "setup", "teardown",
    "cases"
]

# Minimum driver version per top-level key, mirroring `x-requires-driver` in
# the canonical schemas. The requirement lives beside the key it constrains so
# that adding a key means stating its runtime requirement in the same edit —
# a README sentence cannot be checked, and the failure it fails to prevent
# (an older driver ignoring the declaration in silence) surfaces as a timeout
# naming the screen, with nothing pointing at the declaration.
# test_schema_drift.py pins this to the schemas in both directions.
KEY_DRIVER_REQUIREMENTS = {
    "screenReady": {"web": "1.8.4"},
}

# `screenReady` string forms. The object form is {"marker": "<screen id>"}.
# A file declares this when waiting for its own screen would be wrong —
# a permission refusal rendered in the screen's place, a redirect to login —
# because the readiness gate would otherwise wait for a marker that is
# correctly never going to appear.
VALID_SCREEN_READY_VALUES = ["auto", "marker", "networkidle", "none"]
VALID_FLOW_TOP_LEVEL_KEYS = [
    "$schema", "type", "metadata", "platform", "initialState", "launch",
    "mocks", "setup", "teardown", "sources", "steps", "checkpoints",
    "descriptionFile"
]

# Top-level keys the canonical schemas mark `required`, per test type.
#
# The schemas declare two things about a document's shape, and only one of
# them was implemented: `additionalProperties: false` rejected unknown keys
# as errors, while `required` was enforced as warnings, or — for a flow
# test's `metadata` — not at all. A file holding nothing but `{"type":
# "screen"}` passed, which is a file that names no screen and asserts
# nothing.
#
# The half that worked made the other half look like it worked too: a
# reader who sees unknown keys rejected has no reason to suspect that
# missing ones are not. `test_required_fields_are_enforced` walks this map
# against the vendored schemas in both directions, so a field added to a
# schema's `required` cannot be declared here without being checked, or
# checked without being declared.
#
# `$schema` is never required — it is an editor affordance.
REQUIRED_TOP_LEVEL_KEYS = {
    "screen": ["type", "source", "metadata", "cases"],
    "flow": ["type", "metadata", "steps"],
}

# Valid keys in source object
VALID_SOURCE_KEYS = ["layout", "document"]

# Valid keys in test case
# - name: Test case name (required)
# - description: Inline description text
# - descriptionFile: Path to external file containing detailed description (relative to test file)
#   When specified, the generator reads this file and uses its content as the description.
#   Supports .md (Markdown) and .txt files.
# - args: Default argument values for variable substitution (@{varName} syntax)
#   Can be overridden when called from flow tests
VALID_CASE_KEYS = ["name", "description", "descriptionFile", "skip", "platform", "responsive", "initialState", "steps", "args"]

# Valid keys in test step
VALID_STEP_KEYS = [
    "action", "assert", "id", "ids", "value", "direction",
    "duration", "timeout", "ms", "name", "equals", "contains",
    "path", "amount", "screen", "text", "button", "label", "index",
    # Common step attributes
    "optional", "when",
    # New action parameters
    "container", "retryTapIfNoChange", "variable",
    "times", "while", "maxRetries",
    "latitude", "longitude", "paths",
    # setViewport / setOrientation parameters
    "width", "height", "orientation",
    # setMocks: switch mock scenarios mid-flow (map of operationId -> scenario)
    "mocks",
    # emitHook: positional arguments for the registered browser-side hook
    "hookArgs",
    # Screenshot assertion parameters
    "cropId", "threshold",
    # File reference step keys (for flow tests)
    "file", "case", "cases",
    # Args for overriding screen test default args (for flow tests)
    "args",
    # Block step keys (for flow tests - grouped inline steps)
    "block", "description", "descriptionFile", "steps"
]

# Valid keys in description file
VALID_DESCRIPTION_KEYS = [
    "$schema", "case_name", "summary", "preconditions",
    "test_procedure", "expected_results", "notes",
    "created_at", "updated_at"
]

# Parameter descriptions
PARAMETER_DESCRIPTIONS = {
    "id": "Element identifier (accessibilityIdentifier on iOS, resource-id on Android, data-testid on Web)",
    "ids": "Array of element identifiers for waitForAny",
    "value": "Text value for input actions. Supports @{varName} syntax for variable substitution",
    "direction": "Direction for scroll/swipe: up, down, left, right",
    "duration": "Duration in milliseconds (for longPress)",
    "timeout": "Maximum wait time in milliseconds (default: 5000)",
    "ms": "Wait duration in milliseconds",
    "name": "Name for screenshot file / baseline; on assert:screen the expected screen id",
    "equals": "Exact value to match. Supports @{varName} syntax for variable substitution",
    "contains": "Substring to match. Supports @{varName} syntax for variable substitution",
    "amount": "Scroll amount (platform-specific)",
    "screen": "Screen identifier (for flow tests)",
    "text": "Specific text portion to tap within element (for tap action)",
    "button": "Button text to tap in alert dialog (for alertTap action)",
    "label": "Human-readable step name for logs/reports. On selectOption: option label (visible text) to select",
    "index": "Item/option/tab index, 0-based",
    "args": "Arguments for variable substitution. In screen test cases, defines default values. In flow file references, overrides defaults",
    "optional": "When true, a failure of this step is recorded as a warning and execution continues",
    "when": "Pre-condition object; if not satisfied the step is skipped",
    "container": "Scrollable container id for scrollUntilVisible (default: window / first scrollable view)",
    "retryTapIfNoChange": "Re-tap once when the UI did not change after the tap (ghost-tap mitigation)",
    "variable": "Runtime variable name for readText (referenced later as @{name})",
    "times": "Iteration count for repeat (with 'while': acts as the cap)",
    "while": "Condition object; repeat loops while it holds",
    "maxRetries": "Number of retries after the first attempt (0-3, default 1)",
    "latitude": "Latitude for setLocation (-90 to 90)",
    "longitude": "Longitude for setLocation (-180 to 180)",
    "width": "Viewport width in logical pixels for setViewport (positive integer)",
    "height": "Viewport height in logical pixels for setViewport (positive integer)",
    "orientation": "Target orientation for setOrientation: portrait or landscape",
    "paths": "Media file paths for addMedia (Android: device media fixtures dir; "
             "iOS: UITest bundle, basenames recommended; Web: relative to test file)",
    "cropId": "Element id whose bounding box crops the screenshot before comparing",
    "threshold": "Required similarity percentage for screenshot assertion (0-100, default 98.0)",
    "hookArgs": "Positional arguments for emitHook, passed to the registered browser-side hook"
}
