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
        "description": "Insert media files into the device gallery (Android only)",
        "required": ["paths"],
        "optional": []
    },
    "setMocks": {
        "description": "Switch API mock scenarios (map of operationId -> scenario name). "
                       "In flow tests, call before navigating so the next screen fetches the new response.",
        "required": ["mocks"],
        "optional": []
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
    }
}

# Valid direction values
VALID_DIRECTIONS = ["up", "down", "left", "right"]

# Common step attributes accepted on every action/assertion.
# NOTE: on selectOption, 'label' keeps its legacy meaning (option text to select).
COMMON_STEP_ATTRIBUTES = ["label", "optional", "when"]

# Valid keys in a condition object (when / repeat.while). Unknown keys are errors.
VALID_CONDITION_KEYS = ["visible", "notVisible", "platform", "state"]

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

# Valid top-level keys in test file
VALID_TOP_LEVEL_KEYS = [
    "$schema", "type", "source", "metadata", "platform", "embeddedIn",
    "initialState", "launch", "mocks", "setup", "teardown", "cases",
    "sources", "steps", "checkpoints", "descriptionFile"
]

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
VALID_CASE_KEYS = ["name", "description", "descriptionFile", "skip", "platform", "initialState", "steps", "args"]

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
    # setMocks: switch mock scenarios mid-flow (map of operationId -> scenario)
    "mocks",
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
    "name": "Name for screenshot file / baseline",
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
    "paths": "Media file paths for addMedia (relative to test file)",
    "cropId": "Element id whose bounding box crops the screenshot before comparing",
    "threshold": "Required similarity percentage for screenshot assertion (0-100, default 98.0)"
}
