"""Step validation for actions and assertions."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ValidationMessage, ValidationResult
from .mock import find_mock_index, validate_mock_reference
from ..schema import (
    CONDITION_PLATFORMS,
    CONDITION_PLATFORM_ARRAY_ITEMS,
    SUPPORTED_ACTIONS,
    SUPPORTED_ASSERTIONS,
    VALID_CONDITION_KEYS,
    VALID_CONDITION_STATE_KEYS,
    VALID_DIRECTIONS,
    VALID_STEP_KEYS,
)

# Pattern to match @{varName} placeholders
ARG_PLACEHOLDER_PATTERN = re.compile(r'@\{([^}]+)\}')


class StepValidator:
    """Validates test steps (actions and assertions)."""

    def __init__(self, test_file_path: Path | None = None):
        self._test_file_path = test_file_path

    def set_test_file_path(self, path: Path | None):
        """Set the test file path for resolving relative paths."""
        self._test_file_path = path

    def validate_step(self, step: dict, path: str, result: ValidationResult, is_flow: bool = False):
        """Validate a test step."""
        # Check for file reference step (flow tests only)
        if "file" in step:
            if not is_flow:
                result.errors.append(ValidationMessage(
                    path=path,
                    message="File reference steps are only allowed in flow tests"
                ))
                return
            self._validate_file_step(step, path, result)
            return

        # Check for block step (flow tests only)
        if "block" in step:
            if not is_flow:
                result.errors.append(ValidationMessage(
                    path=path,
                    message="Block steps are only allowed in flow tests"
                ))
                return
            self._validate_block_step(step, path, result)
            return

        # Check for unknown keys
        for key in step.keys():
            if key not in VALID_STEP_KEYS:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown step key: {key}",
                    level="warning"
                ))

        action = step.get("action")
        assertion = step.get("assert")

        if action and assertion:
            result.errors.append(ValidationMessage(
                path=path,
                message="Step cannot have both 'action' and 'assert'"
            ))
        elif action:
            self._validate_common_attributes(step, path, result)
            self._validate_action(step, path, result)
        elif assertion:
            self._validate_common_attributes(step, path, result)
            self._validate_assertion(step, path, result)
        else:
            result.errors.append(ValidationMessage(
                path=path,
                message="Step must have either 'action' or 'assert'"
            ))

    def _validate_common_attributes(self, step: dict, path: str, result: ValidationResult):
        """Validate common step attributes: label, optional, when."""
        # 'label' must be a string on every step.
        # On selectOption it keeps its legacy meaning (option text), which is also a string.
        if "label" in step and not isinstance(step["label"], str):
            result.errors.append(ValidationMessage(
                path=path,
                message=f"'label' must be a string, got: {type(step['label']).__name__}"
            ))

        if "optional" in step and not isinstance(step["optional"], bool):
            result.errors.append(ValidationMessage(
                path=path,
                message=f"'optional' must be a boolean, got: {type(step['optional']).__name__}"
            ))

        if "when" in step:
            self.validate_condition(step["when"], f"{path}.when", result)

    def validate_condition(self, condition, path: str, result: ValidationResult):
        """Validate a condition object (used by 'when' and 'repeat.while')."""
        if not isinstance(condition, dict):
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Condition must be an object, got: {type(condition).__name__}"
            ))
            return

        if len(condition) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message="Condition object must have at least one key (visible/notVisible/platform/state)"
            ))
            return

        for key in condition.keys():
            if key not in VALID_CONDITION_KEYS:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Unknown condition key: {key}. Must be one of: {VALID_CONDITION_KEYS}"
                ))

        for key in ("visible", "notVisible"):
            if key in condition:
                value = condition[key]
                if not isinstance(value, str) or not value.strip():
                    result.errors.append(ValidationMessage(
                        path=path,
                        message=f"Condition '{key}' must be a non-empty element id string"
                    ))

        if "platform" in condition:
            platform = condition["platform"]
            if isinstance(platform, str):
                if platform not in CONDITION_PLATFORMS:
                    result.errors.append(ValidationMessage(
                        path=path,
                        message=f"Invalid condition platform: {platform}. Must be one of: {CONDITION_PLATFORMS}"
                    ))
            elif isinstance(platform, list):
                if len(platform) == 0:
                    result.errors.append(ValidationMessage(
                        path=path,
                        message="Condition 'platform' array must not be empty"
                    ))
                for item in platform:
                    if item not in CONDITION_PLATFORM_ARRAY_ITEMS:
                        result.errors.append(ValidationMessage(
                            path=path,
                            message=f"Invalid condition platform: {item}. Must be one of: {CONDITION_PLATFORM_ARRAY_ITEMS}"
                        ))
            else:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Condition 'platform' must be a string or array, got: {type(platform).__name__}"
                ))

        if "state" in condition:
            state = condition["state"]
            if not isinstance(state, dict):
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Condition 'state' must be an object, got: {type(state).__name__}"
                ))
            else:
                for key in state.keys():
                    if key not in VALID_CONDITION_STATE_KEYS:
                        result.errors.append(ValidationMessage(
                            path=path,
                            message=f"Unknown condition state key: {key}. Must be one of: {VALID_CONDITION_STATE_KEYS}"
                        ))
                if not isinstance(state.get("path"), str) or not state.get("path", "").strip():
                    result.errors.append(ValidationMessage(
                        path=path,
                        message="Condition 'state' must have a non-empty string 'path'"
                    ))
                if "equals" not in state:
                    result.errors.append(ValidationMessage(
                        path=path,
                        message="Condition 'state' must have 'equals'"
                    ))

    def _validate_file_step(self, step: dict, path: str, result: ValidationResult):
        """Validate a file reference step in flow tests."""
        file_ref = step["file"]

        # Validate file reference format
        if not isinstance(file_ref, str) or not file_ref.strip():
            result.errors.append(ValidationMessage(
                path=path,
                message="'file' must be a non-empty string"
            ))
            return

        # Check for valid keys in file step
        valid_file_step_keys = {"file", "case", "cases", "args", "when"}
        for key in step.keys():
            if key not in valid_file_step_keys:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown key in file step: {key}",
                    level="warning"
                ))

        # Validate when condition if present
        if "when" in step:
            self.validate_condition(step["when"], f"{path}.when", result)

        # Validate args if present
        if "args" in step:
            args = step["args"]
            if not isinstance(args, dict):
                result.errors.append(ValidationMessage(
                    path=f"{path}.args",
                    message="'args' must be an object/dictionary"
                ))
            else:
                for key, value in args.items():
                    if not isinstance(key, str):
                        result.errors.append(ValidationMessage(
                            path=f"{path}.args",
                            message=f"Argument key must be a string, got: {type(key).__name__}"
                        ))
                    if not isinstance(value, (str, int, float, bool)):
                        result.errors.append(ValidationMessage(
                            path=f"{path}.args.{key}",
                            message=f"Argument value must be a primitive type (string, number, boolean), got: {type(value).__name__}"
                        ))

        # Cannot have both 'case' and 'cases'
        if "case" in step and "cases" in step:
            result.errors.append(ValidationMessage(
                path=path,
                message="File step cannot have both 'case' and 'cases'"
            ))

        # Validate 'case' is a string
        if "case" in step:
            if not isinstance(step["case"], str) or not step["case"].strip():
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'case' must be a non-empty string"
                ))

        # Validate 'cases' is a non-empty list of strings
        if "cases" in step:
            cases = step["cases"]
            if not isinstance(cases, list) or len(cases) == 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'cases' must be a non-empty array"
                ))
            elif not all(isinstance(c, str) and c.strip() for c in cases):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'cases' must be an array of non-empty strings"
                ))

        # Try to resolve the file path and validate it exists
        if self._test_file_path:
            resolved_path = self._resolve_file_reference(file_ref)
            if resolved_path and not resolved_path.exists():
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Referenced test file not found: {file_ref} (looked for {resolved_path})",
                    level="warning"
                ))
            elif resolved_path and resolved_path.exists():
                # Validate args against referenced screen test
                self._validate_file_step_args(step, path, result, resolved_path)

    def _validate_file_step_args(self, step: dict, path: str, result: ValidationResult, resolved_path: Path):
        """Validate that flow's args only override existing screen args (no new args allowed)."""
        try:
            with open(resolved_path, 'r', encoding='utf-8') as f:
                screen_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            # Skip validation if file can't be read
            return

        cases = screen_data.get("cases", [])
        if not cases:
            return

        flow_args = step.get("args", {}) if isinstance(step.get("args"), dict) else {}
        if not flow_args:
            # No flow args to validate
            return

        # Determine which cases to validate
        case_names_to_validate = []
        if "case" in step:
            case_names_to_validate = [step["case"]]
        elif "cases" in step:
            case_names_to_validate = step["cases"]
        else:
            # All cases
            case_names_to_validate = [c.get("name") for c in cases if c.get("name")]

        for case in cases:
            case_name = case.get("name")
            if case_name not in case_names_to_validate:
                continue

            # Get screen's defined args for this case
            screen_defined_args = set(case.get("args", {}).keys()) if isinstance(case.get("args"), dict) else set()

            # Check if flow is trying to add new args not defined in screen
            flow_arg_keys = set(flow_args.keys())
            undefined_in_screen = flow_arg_keys - screen_defined_args
            if undefined_in_screen:
                for arg_name in sorted(undefined_in_screen):
                    result.errors.append(ValidationMessage(
                        path=path,
                        message=f"Argument '@{{{arg_name}}}' passed in flow is not defined in screen case '{case_name}'. Flow can only override existing screen args."
                    ))

    def _extract_used_args(self, steps: list) -> set[str]:
        """Extract all @{varName} placeholders used in steps."""
        used_args: set[str] = set()
        for step in steps:
            self._extract_args_from_value(step, used_args)
        return used_args

    def _extract_args_from_value(self, obj, used_args: set[str]):
        """Recursively extract @{varName} from any string value in the object."""
        if isinstance(obj, str):
            matches = ARG_PLACEHOLDER_PATTERN.findall(obj)
            used_args.update(matches)
        elif isinstance(obj, dict):
            for value in obj.values():
                self._extract_args_from_value(value, used_args)
        elif isinstance(obj, list):
            for item in obj:
                self._extract_args_from_value(item, used_args)

    def _resolve_file_reference(self, file_ref: str) -> Path | None:
        """Resolve a file reference to an actual path."""
        if not self._test_file_path:
            return None

        base_dir = self._test_file_path.parent

        # Find tests root (parent of flows/ or screens/)
        tests_root = base_dir
        if base_dir.name == "flows" or base_dir.name == "screens":
            tests_root = base_dir.parent
        elif base_dir.parent.name == "flows" or base_dir.parent.name == "screens":
            tests_root = base_dir.parent.parent

        # Try different file locations
        candidates = [
            # Same directory as flow test
            base_dir / f"{file_ref}.test.json",
            base_dir / f"{file_ref}.json",
            base_dir / file_ref,
            # screens/{file_ref}/{file_ref}.test.json (standard screen test structure)
            tests_root / "screens" / file_ref / f"{file_ref}.test.json",
            # screens/{file_ref}.test.json (flat structure)
            tests_root / "screens" / f"{file_ref}.test.json",
            # flows/{file_ref}/{file_ref}.test.json
            tests_root / "flows" / file_ref / f"{file_ref}.test.json",
            # flows/{file_ref}.test.json
            tests_root / "flows" / f"{file_ref}.test.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Return the most likely location for error message
        return tests_root / "screens" / file_ref / f"{file_ref}.test.json"

    def _validate_block_step(self, step: dict, path: str, result: ValidationResult):
        """Validate a block step in flow tests."""
        block_name = step["block"]

        # Validate block name is non-empty string
        if not isinstance(block_name, str) or not block_name.strip():
            result.errors.append(ValidationMessage(
                path=path,
                message="'block' must be a non-empty string"
            ))
            return

        # Check for valid keys in block step
        valid_block_step_keys = {"block", "description", "descriptionFile", "steps", "when"}
        for key in step.keys():
            if key not in valid_block_step_keys:
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Unknown key in block step: {key}",
                    level="warning"
                ))

        # Validate when condition if present
        if "when" in step:
            self.validate_condition(step["when"], f"{path}.when", result)

        # Validate steps is required and non-empty
        if "steps" not in step:
            result.errors.append(ValidationMessage(
                path=path,
                message="Block step must have 'steps' array"
            ))
            return

        steps = step["steps"]
        if not isinstance(steps, list) or len(steps) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message="Block 'steps' must be a non-empty array"
            ))
            return

        # Validate each step in the block (inline steps only, no nested blocks/files)
        for i, inner_step in enumerate(steps):
            inner_step_path = f"{path}.steps[{i}]"
            # Block steps can only contain action/assert steps, not file references or nested blocks
            if "file" in inner_step:
                result.errors.append(ValidationMessage(
                    path=inner_step_path,
                    message="File references are not allowed inside block steps"
                ))
            elif "block" in inner_step:
                result.errors.append(ValidationMessage(
                    path=inner_step_path,
                    message="Nested blocks are not allowed inside block steps"
                ))
            else:
                self.validate_step(inner_step, inner_step_path, result, is_flow=False)

        # Validate descriptionFile if present
        if "descriptionFile" in step and self._test_file_path:
            desc_file_path = step["descriptionFile"]
            # Resolve relative to test file location
            if not Path(desc_file_path).is_absolute():
                desc_file_path = self._test_file_path.parent / desc_file_path

            desc_path = Path(desc_file_path)
            if not desc_path.exists():
                result.warnings.append(ValidationMessage(
                    path=path,
                    message=f"Description file not found: {step['descriptionFile']}",
                    level="warning"
                ))

    def _validate_action(self, step: dict, path: str, result: ValidationResult):
        """Validate an action step."""
        action = step["action"]

        if action not in SUPPORTED_ACTIONS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Unsupported action: {action}"
            ))
            return

        spec = SUPPORTED_ACTIONS[action]

        # Check required parameters
        for param in spec["required"]:
            if param not in step:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Missing required parameter '{param}' for action '{action}'"
                ))

        # Validate direction if present
        if "direction" in step and step["direction"] not in VALID_DIRECTIONS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Invalid direction: {step['direction']}. Must be one of: {VALID_DIRECTIONS}"
            ))

        # Validate timeout is positive
        if "timeout" in step:
            timeout = step["timeout"]
            if not isinstance(timeout, int) or timeout <= 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Timeout must be a positive integer (ms), got: {timeout}"
                ))

        # Validate ms is positive
        if "ms" in step:
            ms = step["ms"]
            if not isinstance(ms, int) or ms <= 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"ms must be a positive integer, got: {ms}"
                ))

        # Validate ids is a non-empty list of non-empty strings
        if "ids" in step:
            ids = step["ids"]
            if not isinstance(ids, list) or len(ids) == 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message="ids must be a non-empty array"
                ))
            elif not all(isinstance(i, str) and i.strip() for i in ids):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="ids must be an array of non-empty strings"
                ))

        # Validate index is a non-negative integer
        if "index" in step:
            index = step["index"]
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"index must be a non-negative integer, got: {index}"
                ))

        # Validate container is a non-empty string (scrollUntilVisible)
        if "container" in step:
            container = step["container"]
            if not isinstance(container, str) or not container.strip():
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'container' must be a non-empty element id string"
                ))

        # Validate retryTapIfNoChange is a boolean (tap)
        if "retryTapIfNoChange" in step and not isinstance(step["retryTapIfNoChange"], bool):
            result.errors.append(ValidationMessage(
                path=path,
                message=f"'retryTapIfNoChange' must be a boolean, got: {type(step['retryTapIfNoChange']).__name__}"
            ))

        # Action-specific validation
        if action == "readText":
            variable = step.get("variable")
            if variable is not None and (not isinstance(variable, str) or not variable.strip()):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="'variable' must be a non-empty string"
                ))
        elif action == "repeat":
            self._validate_repeat_action(step, path, result)
        elif action == "retry":
            self._validate_retry_action(step, path, result)
        elif action == "setLocation":
            self._validate_set_location_action(step, path, result)
        elif action == "addMedia":
            self._validate_add_media_action(step, path, result)
        elif action == "setMocks":
            index = find_mock_index(self._test_file_path)
            validate_mock_reference(step.get("mocks"), f"{path}.mocks", result, index)

    def _validate_repeat_action(self, step: dict, path: str, result: ValidationResult):
        """Validate a repeat control step."""
        if "times" not in step and "while" not in step:
            result.errors.append(ValidationMessage(
                path=path,
                message="repeat must have 'times' and/or 'while'"
            ))

        if "times" in step:
            times = step["times"]
            if not isinstance(times, int) or isinstance(times, bool) or times < 1:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"'times' must be an integer >= 1, got: {times}"
                ))

        if "while" in step:
            self.validate_condition(step["while"], f"{path}.while", result)

        self._validate_nested_steps(step, path, result, "repeat")

    def _validate_retry_action(self, step: dict, path: str, result: ValidationResult):
        """Validate a retry control step."""
        if "maxRetries" in step:
            max_retries = step["maxRetries"]
            if not isinstance(max_retries, int) or isinstance(max_retries, bool) or not (0 <= max_retries <= 3):
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"'maxRetries' must be an integer between 0 and 3, got: {max_retries}"
                ))

        self._validate_nested_steps(step, path, result, "retry")

    def _validate_nested_steps(self, step: dict, path: str, result: ValidationResult, action: str):
        """Validate the nested steps array of a repeat/retry control step."""
        if "steps" not in step:
            # Missing 'steps' is already reported as a missing required parameter
            return

        steps = step["steps"]
        if not isinstance(steps, list) or len(steps) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"{action} 'steps' must be a non-empty array"
            ))
            return

        for i, inner_step in enumerate(steps):
            inner_step_path = f"{path}.steps[{i}]"
            if not isinstance(inner_step, dict):
                result.errors.append(ValidationMessage(
                    path=inner_step_path,
                    message="Step must be an object"
                ))
            elif "file" in inner_step or "block" in inner_step:
                result.errors.append(ValidationMessage(
                    path=inner_step_path,
                    message=f"File references and blocks are not allowed inside {action} steps"
                ))
            else:
                # Nested repeat/retry are allowed; recurse as plain steps
                self.validate_step(inner_step, inner_step_path, result, is_flow=False)

    def _validate_set_location_action(self, step: dict, path: str, result: ValidationResult):
        """Validate a setLocation action."""
        ranges = {"latitude": (-90, 90), "longitude": (-180, 180)}
        for param, (low, high) in ranges.items():
            if param not in step:
                continue
            value = step[param]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not (low <= value <= high):
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"'{param}' must be a number between {low} and {high}, got: {value}"
                ))

    def _validate_add_media_action(self, step: dict, path: str, result: ValidationResult):
        """Validate an addMedia action."""
        if "paths" not in step:
            # Missing 'paths' is already reported as a missing required parameter
            return
        paths = step["paths"]
        if not isinstance(paths, list) or len(paths) == 0:
            result.errors.append(ValidationMessage(
                path=path,
                message="'paths' must be a non-empty array"
            ))
        elif not all(isinstance(p, str) and p.strip() for p in paths):
            result.errors.append(ValidationMessage(
                path=path,
                message="'paths' must be an array of non-empty strings"
            ))

    def _validate_assertion(self, step: dict, path: str, result: ValidationResult):
        """Validate an assertion step."""
        assertion = step["assert"]

        if assertion not in SUPPORTED_ASSERTIONS:
            result.errors.append(ValidationMessage(
                path=path,
                message=f"Unsupported assertion: {assertion}"
            ))
            return

        spec = SUPPORTED_ASSERTIONS[assertion]

        # Check required parameters
        for param in spec["required"]:
            if param not in step:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Missing required parameter '{param}' for assertion '{assertion}'"
                ))

        # Validate timeout (auto-wait) — allowed on all assertions
        if "timeout" in step:
            timeout = step["timeout"]
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Timeout must be a positive integer (ms), got: {timeout}"
                ))

        # For text assertion, must have equals or contains
        if assertion == "text":
            if "equals" not in step and "contains" not in step:
                result.errors.append(ValidationMessage(
                    path=path,
                    message="Text assertion must have 'equals' or 'contains'"
                ))

        # For count assertion, equals must be a non-negative integer
        if assertion == "count" and "equals" in step:
            equals = step["equals"]
            if not isinstance(equals, int) or isinstance(equals, bool) or equals < 0:
                result.errors.append(ValidationMessage(
                    path=path,
                    message=f"Count 'equals' must be a non-negative integer, got: {equals}"
                ))

        # For state assertion, path must be a non-empty string
        if assertion == "state" and "path" in step:
            state_path = step["path"]
            if not isinstance(state_path, str) or not state_path.strip():
                result.errors.append(ValidationMessage(
                    path=path,
                    message="State assertion 'path' must be a non-empty string"
                ))

        # For screenshot assertion, validate name/cropId/threshold
        if assertion == "screenshot":
            name = step.get("name")
            if name is not None and (not isinstance(name, str) or not name.strip()):
                result.errors.append(ValidationMessage(
                    path=path,
                    message="Screenshot assertion 'name' must be a non-empty string"
                ))
            if "cropId" in step:
                crop_id = step["cropId"]
                if not isinstance(crop_id, str) or not crop_id.strip():
                    result.errors.append(ValidationMessage(
                        path=path,
                        message="'cropId' must be a non-empty element id string"
                    ))
            if "threshold" in step:
                threshold = step["threshold"]
                if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not (0 <= threshold <= 100):
                    result.errors.append(ValidationMessage(
                        path=path,
                        message=f"'threshold' must be a number between 0 and 100, got: {threshold}"
                    ))
