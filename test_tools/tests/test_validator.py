"""Tests for the validator module."""

import pytest
import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validator import TestValidator, ValidationResult


class TestValidatorBasics:
    """Basic validator tests."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_valid_screen_test(self):
        """Test validation of a valid screen test."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "platform": "ios",
            "cases": [
                {
                    "name": "test_case",
                    "steps": [
                        {"action": "waitFor", "id": "element_id", "timeout": 5000},
                        {"assert": "visible", "id": "element_id"}
                    ]
                }
            ]
        }

        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.error_count == 0

    def test_missing_type(self):
        """Test validation fails without type."""
        data = {
            "metadata": {"name": "test"},
            "cases": []
        }

        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert result.error_count > 0

    def test_unknown_type(self):
        """Test validation fails with unknown type."""
        data = {
            "type": "unknown_type",
            "cases": []
        }

        result = self.validator.validate_data(data)
        assert not result.is_valid


class TestActionValidation:
    """Tests for action validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_test(self, steps: list) -> dict:
        return {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": steps}]
        }

    def test_valid_tap_action(self):
        """Test valid tap action."""
        data = self._make_test([{"action": "tap", "id": "button_id"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_tap_missing_id(self):
        """Test tap action without id fails."""
        data = self._make_test([{"action": "tap"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'id'" in str(e) for e in result.errors)

    def test_valid_input_action(self):
        """Test valid input action."""
        data = self._make_test([{"action": "input", "id": "text_field", "value": "hello"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_input_missing_value(self):
        """Test input action without value fails."""
        data = self._make_test([{"action": "input", "id": "text_field"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_valid_scroll_action(self):
        """Test valid scroll action."""
        data = self._make_test([{"action": "scroll", "id": "list_view", "direction": "down"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_scroll_invalid_direction(self):
        """Test scroll with invalid direction fails."""
        data = self._make_test([{"action": "scroll", "id": "list_view", "direction": "diagonal"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_valid_waitFor_action(self):
        """Test valid waitFor action."""
        data = self._make_test([{"action": "waitFor", "id": "element_id", "timeout": 10000}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_waitForAny_action(self):
        """Test valid waitForAny action."""
        data = self._make_test([{"action": "waitForAny", "ids": ["elem1", "elem2"], "timeout": 5000}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_waitForAny_empty_ids(self):
        """Test waitForAny with empty ids fails."""
        data = self._make_test([{"action": "waitForAny", "ids": []}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_waitForAny_missing_ids(self):
        """Test waitForAny without ids fails."""
        data = self._make_test([{"action": "waitForAny"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_valid_wait_action(self):
        """Test valid wait action."""
        data = self._make_test([{"action": "wait", "ms": 1000}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_wait_negative_ms(self):
        """Test wait with negative ms fails."""
        data = self._make_test([{"action": "wait", "ms": -100}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_valid_screenshot_action(self):
        """Test valid screenshot action."""
        data = self._make_test([{"action": "screenshot", "name": "test_screenshot"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_back_action(self):
        """Test valid back action."""
        data = self._make_test([{"action": "back"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_unsupported_action(self):
        """Test unsupported action fails."""
        data = self._make_test([{"action": "unknown_action", "id": "elem"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_timeout_must_be_positive(self):
        """Test timeout must be positive integer."""
        data = self._make_test([{"action": "waitFor", "id": "elem", "timeout": 0}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_timeout_must_be_integer(self):
        """Test timeout must be integer."""
        data = self._make_test([{"action": "waitFor", "id": "elem", "timeout": "5000"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid


class TestAssertionValidation:
    """Tests for assertion validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_test(self, steps: list) -> dict:
        return {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": steps}]
        }

    def test_valid_visible_assertion(self):
        """Test valid visible assertion."""
        data = self._make_test([{"assert": "visible", "id": "element_id"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_notVisible_assertion(self):
        """Test valid notVisible assertion."""
        data = self._make_test([{"assert": "notVisible", "id": "element_id"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_enabled_assertion(self):
        """Test valid enabled assertion."""
        data = self._make_test([{"assert": "enabled", "id": "button_id"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_disabled_assertion(self):
        """Test valid disabled assertion."""
        data = self._make_test([{"assert": "disabled", "id": "button_id"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_text_assertion_equals(self):
        """Test valid text assertion with equals."""
        data = self._make_test([{"assert": "text", "id": "label_id", "equals": "Expected"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_text_assertion_contains(self):
        """Test valid text assertion with contains."""
        data = self._make_test([{"assert": "text", "id": "label_id", "contains": "partial"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_text_assertion_missing_equals_and_contains(self):
        """Test text assertion without equals or contains fails."""
        data = self._make_test([{"assert": "text", "id": "label_id"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_valid_count_assertion(self):
        """Test valid count assertion."""
        data = self._make_test([{"assert": "count", "id": "list_item", "equals": 5}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_count_assertion_missing_equals(self):
        """Test count assertion without equals fails."""
        data = self._make_test([{"assert": "count", "id": "list_item"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_unsupported_assertion(self):
        """Test unsupported assertion fails."""
        data = self._make_test([{"assert": "unknown_assertion", "id": "elem"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid


class TestStepValidation:
    """Tests for step structure validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_test(self, steps: list) -> dict:
        return {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": steps}]
        }

    def test_step_must_have_action_or_assert(self):
        """Test step must have action or assert."""
        data = self._make_test([{"id": "element_id"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_step_cannot_have_both_action_and_assert(self):
        """Test step cannot have both action and assert."""
        data = self._make_test([{"action": "tap", "assert": "visible", "id": "elem"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_unknown_step_key_warning(self):
        """Test unknown step key produces warning."""
        data = self._make_test([{"action": "tap", "id": "elem", "unknown_key": "value"}])
        result = self.validator.validate_data(data)
        assert result.is_valid  # Should pass with warning
        assert result.warning_count > 0


class TestFlowTestValidation:
    """Tests for flow test validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_valid_flow_test(self):
        """Test validation of valid flow test."""
        data = {
            "type": "flow",
            "sources": [{"layout": "layouts/screen1.json", "alias": "screen1"}],
            "metadata": {"name": "flow_test"},
            "steps": [
                {"screen": "screen1", "action": "tap", "id": "button_id"},
                {"screen": "screen1", "assert": "visible", "id": "result_id"}
            ]
        }

        result = self.validator.validate_data(data)
        assert result.is_valid


class TestCaseValidation:
    """Tests for test case validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_case_missing_name(self):
        """Test case without name fails."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"steps": [{"action": "tap", "id": "elem"}]}]
        }

        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_case_empty_steps_warning(self):
        """Test case with empty steps produces warning."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "empty_case", "steps": []}]
        }

        result = self.validator.validate_data(data)
        assert result.is_valid  # Should pass with warning
        assert result.warning_count > 0


class TestFlowTestFileReferenceValidation:
    """Tests for flow test file reference validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_flow_test(self, steps: list) -> dict:
        return {
            "type": "flow",
            "metadata": {"name": "flow_test"},
            "steps": steps
        }

    def test_valid_file_reference_with_case(self):
        """Test valid file reference with single case."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": "valid_login"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_file_reference_with_cases(self):
        """Test valid file reference with multiple cases."""
        data = self._make_flow_test([
            {"file": "screens/login", "cases": ["initial_display", "valid_login"]}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_file_reference_all_cases(self):
        """Test valid file reference without case (all cases)."""
        data = self._make_flow_test([
            {"file": "screens/login"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_file_reference_empty_file(self):
        """Test file reference with empty file fails."""
        data = self._make_flow_test([
            {"file": ""}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("non-empty string" in str(e) for e in result.errors)

    def test_file_reference_both_case_and_cases(self):
        """Test file reference with both case and cases fails."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": "one", "cases": ["two", "three"]}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("both 'case' and 'cases'" in str(e) for e in result.errors)

    def test_file_reference_empty_case(self):
        """Test file reference with empty case fails."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": ""}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_file_reference_empty_cases_array(self):
        """Test file reference with empty cases array fails."""
        data = self._make_flow_test([
            {"file": "screens/login", "cases": []}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("non-empty array" in str(e) for e in result.errors)

    def test_file_reference_cases_with_empty_string(self):
        """Test file reference with empty string in cases fails."""
        data = self._make_flow_test([
            {"file": "screens/login", "cases": ["valid_login", ""]}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_file_reference_unknown_key_warning(self):
        """Test file reference with unknown key produces warning."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": "valid_login", "unknown_key": "value"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count > 0

    def test_file_reference_not_allowed_in_screen_test(self):
        """Test file reference in screen test fails."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [
                {"name": "case1", "steps": [{"file": "screens/login"}]}
            ]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("only allowed in flow tests" in str(e) for e in result.errors)

    def test_mixed_file_ref_and_inline_steps(self):
        """Test flow with mixed file references and inline steps."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": "valid_login"},
            {"action": "waitFor", "id": "home_screen", "timeout": 5000},
            {"file": "screens/home", "cases": ["verify_display", "navigate_to_profile"]},
            {"assert": "visible", "id": "profile_title"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid


class TestFlowTestSetupTeardown:
    """Tests for flow test setup and teardown validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_flow_with_setup(self):
        """Test flow test with setup section."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_with_setup"},
            "setup": [
                {"action": "waitFor", "id": "launch_screen", "timeout": 5000}
            ],
            "steps": [
                {"action": "tap", "id": "start_button"}
            ]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_with_teardown(self):
        """Test flow test with teardown section."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_with_teardown"},
            "steps": [
                {"action": "tap", "id": "start_button"}
            ],
            "teardown": [
                {"action": "screenshot", "name": "final_state"}
            ]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_with_checkpoints(self):
        """Test flow test with checkpoints."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_with_checkpoints"},
            "steps": [
                {"action": "tap", "id": "login_button"},
                {"action": "waitFor", "id": "home_screen", "timeout": 5000}
            ],
            "checkpoints": [
                {"name": "after_login", "afterStep": 1, "screenshot": True}
            ]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_empty_steps_warning(self):
        """Test flow test with empty steps produces warning."""
        data = {
            "type": "flow",
            "metadata": {"name": "empty_flow"},
            "steps": []
        }
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count > 0


class TestDescriptionFileValidation:
    """Tests for description file validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_valid_description_file(self):
        """Test valid description file."""
        import tempfile
        import json

        desc_data = {
            "case_name": "initial_display",
            "summary": "Verify initial screen state",
            "preconditions": ["User is logged in", "App is launched"],
            "test_procedure": ["Open the screen", "Check elements"],
            "expected_results": ["Title is visible", "Button is enabled"],
            "notes": "Additional notes"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(desc_data, f)
            temp_path = Path(f.name)

        try:
            result = self.validator.validate_file(temp_path)
            assert result.is_valid
        finally:
            temp_path.unlink()

    def test_description_missing_case_name(self):
        """Test description file without case_name fails."""
        import tempfile
        import json

        desc_data = {
            "summary": "Some summary"
        }

        # Create in descriptions folder to trigger description validation
        with tempfile.TemporaryDirectory() as temp_dir:
            desc_dir = Path(temp_dir) / "descriptions"
            desc_dir.mkdir()
            desc_file = desc_dir / "test.json"

            with open(desc_file, 'w') as f:
                json.dump(desc_data, f)

            result = self.validator.validate_file(desc_file)
            assert not result.is_valid
            assert any("case_name" in str(e) for e in result.errors)

    def test_description_invalid_preconditions(self):
        """Test description file with invalid preconditions."""
        import tempfile
        import json

        desc_data = {
            "case_name": "test_case",
            "preconditions": "not an array"
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            desc_dir = Path(temp_dir) / "descriptions"
            desc_dir.mkdir()
            desc_file = desc_dir / "test.json"

            with open(desc_file, 'w') as f:
                json.dump(desc_data, f)

            result = self.validator.validate_file(desc_file)
            assert not result.is_valid


class TestArgsValidation:
    """Tests for args validation in screen tests and flow file steps."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_screen_test(self, case_args: dict | None = None) -> dict:
        case = {
            "name": "test_case",
            "description": "Test case with args",
            "steps": [
                {"action": "input", "id": "username_field", "value": "@{userName}"},
                {"assert": "text", "id": "welcome_label", "contains": "@{userName}"}
            ]
        }
        if case_args is not None:
            case["args"] = case_args
        return {
            "type": "screen",
            "metadata": {"name": "login_test"},
            "cases": [case]
        }

    def _make_flow_test(self, steps: list) -> dict:
        return {
            "type": "flow",
            "metadata": {"name": "flow_test"},
            "steps": steps
        }

    # Screen test args validation
    def test_screen_case_valid_args(self):
        """Test screen case with valid args."""
        data = self._make_screen_test({"userName": "testuser", "password": "secret123"})
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_screen_case_args_with_various_types(self):
        """Test screen case with various primitive types in args."""
        # Use a test without @{} placeholders to test various arg types
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Test with various arg types",
                "args": {
                    "stringArg": "hello",
                    "intArg": 42,
                    "floatArg": 3.14,
                    "boolArg": True
                },
                "steps": [{"action": "tap", "id": "button"}]
            }]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_screen_case_args_not_dict_fails(self):
        """Test screen case with non-dict args fails."""
        data = self._make_screen_test("invalid")
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must be an object/dictionary" in str(e) for e in result.errors)

    def test_screen_case_args_list_fails(self):
        """Test screen case with list args fails."""
        data = self._make_screen_test(["arg1", "arg2"])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must be an object/dictionary" in str(e) for e in result.errors)

    def test_screen_case_args_with_complex_value_fails(self):
        """Test screen case with complex value in args fails."""
        data = self._make_screen_test({
            "validArg": "value",
            "invalidArg": {"nested": "object"}
        })
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("primitive type" in str(e) for e in result.errors)

    def test_screen_case_args_with_list_value_fails(self):
        """Test screen case with list value in args fails."""
        data = self._make_screen_test({
            "invalidArg": ["item1", "item2"]
        })
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("primitive type" in str(e) for e in result.errors)

    def test_screen_case_args_with_none_value_fails(self):
        """Test screen case with None value in args fails."""
        data = self._make_screen_test({
            "nullArg": None
        })
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("primitive type" in str(e) for e in result.errors)

    def test_screen_case_empty_args_valid(self):
        """Test screen case with empty args (no placeholders used) is valid."""
        # Use a test without @{} placeholders
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Test without placeholders",
                "args": {},
                "steps": [{"action": "tap", "id": "button"}]
            }]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    # Flow file step args validation
    def test_flow_file_step_valid_args(self):
        """Test flow file step with valid args."""
        data = self._make_flow_test([
            {"file": "login", "case": "input", "args": {"userName": "flowuser"}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_file_step_args_with_various_types(self):
        """Test flow file step with various primitive types in args."""
        data = self._make_flow_test([
            {
                "file": "login",
                "case": "input",
                "args": {
                    "stringArg": "hello",
                    "intArg": 42,
                    "floatArg": 3.14,
                    "boolArg": False
                }
            }
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_file_step_args_not_dict_fails(self):
        """Test flow file step with non-dict args fails."""
        data = self._make_flow_test([
            {"file": "login", "case": "input", "args": "invalid"}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must be an object/dictionary" in str(e) for e in result.errors)

    def test_flow_file_step_args_with_complex_value_fails(self):
        """Test flow file step with complex value in args fails."""
        data = self._make_flow_test([
            {
                "file": "login",
                "case": "input",
                "args": {"nested": {"key": "value"}}
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("primitive type" in str(e) for e in result.errors)

    def test_flow_file_step_args_with_list_value_fails(self):
        """Test flow file step with list value in args fails."""
        data = self._make_flow_test([
            {
                "file": "login",
                "case": "input",
                "args": {"listArg": [1, 2, 3]}
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("primitive type" in str(e) for e in result.errors)

    def test_flow_file_step_empty_args_valid(self):
        """Test flow file step with empty args is valid."""
        data = self._make_flow_test([
            {"file": "login", "case": "input", "args": {}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_file_step_with_cases_and_args(self):
        """Test flow file step with multiple cases and args."""
        data = self._make_flow_test([
            {
                "file": "login",
                "cases": ["case1", "case2"],
                "args": {"userName": "shared_user"}
            }
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_mixed_steps_with_args(self):
        """Test flow with mixed file refs (with/without args) and inline steps."""
        data = self._make_flow_test([
            {"file": "login", "case": "display"},
            {"file": "login", "case": "input", "args": {"userName": "testuser"}},
            {"action": "waitFor", "id": "home", "timeout": 5000},
            {"file": "home", "args": {"welcomeText": "Hello"}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    # Undefined args validation (screen test)
    def test_screen_case_undefined_arg_fails(self):
        """Test screen case with undefined @{varName} fails."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Case with undefined arg",
                "args": {"userName": "test"},  # password is NOT defined
                "steps": [
                    {"action": "input", "id": "username_field", "value": "@{userName}"},
                    {"action": "input", "id": "password_field", "value": "@{password}"}
                ]
            }]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Undefined argument '@{password}'" in str(e) for e in result.errors)

    def test_screen_case_all_args_defined_passes(self):
        """Test screen case with all @{varName} defined passes."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Case with all args defined",
                "args": {"userName": "test", "password": "secret"},
                "steps": [
                    {"action": "input", "id": "username_field", "value": "@{userName}"},
                    {"action": "input", "id": "password_field", "value": "@{password}"}
                ]
            }]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_screen_case_no_args_no_placeholders_passes(self):
        """Test screen case without args and without placeholders passes."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Case without args",
                "steps": [
                    {"action": "input", "id": "username_field", "value": "literal_value"},
                    {"action": "tap", "id": "button"}
                ]
            }]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_screen_case_multiple_undefined_args(self):
        """Test screen case with multiple undefined args shows all errors."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Case with multiple undefined args",
                "steps": [
                    {"action": "input", "id": "field1", "value": "@{arg1}"},
                    {"action": "input", "id": "field2", "value": "@{arg2}"},
                    {"assert": "text", "id": "label", "equals": "@{arg3}"}
                ]
            }]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("@{arg1}" in str(e) for e in result.errors)
        assert any("@{arg2}" in str(e) for e in result.errors)
        assert any("@{arg3}" in str(e) for e in result.errors)

    def test_screen_case_arg_in_contains_undefined_fails(self):
        """Test screen case with undefined arg in contains fails."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{
                "name": "test_case",
                "description": "Case with undefined arg in contains",
                "steps": [
                    {"assert": "text", "id": "label", "contains": "@{searchText}"}
                ]
            }]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("@{searchText}" in str(e) for e in result.errors)


class TestFlowBlockStepValidation:
    """Tests for flow test block step validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_flow_test(self, steps: list) -> dict:
        return {
            "type": "flow",
            "metadata": {"name": "flow_test"},
            "steps": steps
        }

    def test_valid_block_step(self):
        """Test valid block step in flow test."""
        data = self._make_flow_test([
            {
                "block": "error_handling",
                "description": "Handle login errors",
                "steps": [
                    {"action": "tap", "id": "retry_button"},
                    {"assert": "visible", "id": "error_message"}
                ]
            }
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_block_step_without_description(self):
        """Test block step without description is valid."""
        data = self._make_flow_test([
            {
                "block": "simple_block",
                "steps": [
                    {"action": "tap", "id": "button"}
                ]
            }
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_block_step_empty_name_fails(self):
        """Test block step with empty name fails."""
        data = self._make_flow_test([
            {
                "block": "",
                "steps": [{"action": "tap", "id": "button"}]
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("non-empty string" in str(e) for e in result.errors)

    def test_block_step_missing_steps_fails(self):
        """Test block step without steps array fails."""
        data = self._make_flow_test([
            {
                "block": "my_block",
                "description": "A block"
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must have 'steps'" in str(e) for e in result.errors)

    def test_block_step_empty_steps_fails(self):
        """Test block step with empty steps array fails."""
        data = self._make_flow_test([
            {
                "block": "my_block",
                "steps": []
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("non-empty array" in str(e) for e in result.errors)

    def test_block_step_with_file_ref_inside_fails(self):
        """Test block step containing file reference fails."""
        data = self._make_flow_test([
            {
                "block": "my_block",
                "steps": [
                    {"file": "screens/login", "case": "test"}
                ]
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("not allowed inside block" in str(e) for e in result.errors)

    def test_nested_block_fails(self):
        """Test nested block step fails."""
        data = self._make_flow_test([
            {
                "block": "outer_block",
                "steps": [
                    {
                        "block": "inner_block",
                        "steps": [{"action": "tap", "id": "btn"}]
                    }
                ]
            }
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Nested blocks are not allowed" in str(e) for e in result.errors)

    def test_block_step_not_allowed_in_screen_test(self):
        """Test block step in screen test fails."""
        data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [
                {
                    "name": "case1",
                    "steps": [
                        {
                            "block": "my_block",
                            "steps": [{"action": "tap", "id": "btn"}]
                        }
                    ]
                }
            ]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("only allowed in flow tests" in str(e) for e in result.errors)

    def test_mixed_blocks_and_file_refs(self):
        """Test flow with mixed blocks, file refs, and inline steps."""
        data = self._make_flow_test([
            {"file": "screens/login", "case": "valid_login"},
            {
                "block": "error_handling",
                "description": "Handle errors",
                "steps": [
                    {"action": "tap", "id": "retry_button"},
                    {"assert": "visible", "id": "success_message"}
                ]
            },
            {"action": "waitFor", "id": "home_screen", "timeout": 5000},
            {"file": "screens/home", "case": "verify_display"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_block_unknown_key_warning(self):
        """Test block step with unknown key produces warning."""
        data = self._make_flow_test([
            {
                "block": "my_block",
                "unknown_key": "value",
                "steps": [{"action": "tap", "id": "btn"}]
            }
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count > 0


class TestFlowFileStepArgsValidation:
    """Tests for flow file step args validation against referenced screen tests."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_flow_file_step_with_undefined_arg_in_flow_fails(self):
        """Test flow file step passing arg not defined in screen fails."""
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create screen test with all args defined
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login"},
                "cases": [{
                    "name": "input",
                    "description": "Login input",
                    "args": {"userName": "default", "password": "default_pass"},
                    "steps": [
                        {"action": "input", "id": "username", "value": "@{userName}"},
                        {"action": "input", "id": "password", "value": "@{password}"}
                    ]
                }]
            }
            screen_path = Path(temp_dir) / "screens"
            screen_path.mkdir()
            with open(screen_path / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create flow test that tries to pass an arg not defined in screen
            flow_test = {
                "type": "flow",
                "metadata": {"name": "login_flow"},
                "steps": [
                    {"file": "login", "case": "input", "args": {"unknownArg": "value"}}
                ]
            }
            flow_path = Path(temp_dir) / "flows"
            flow_path.mkdir()
            flow_file = flow_path / "login_flow.test.json"
            with open(flow_file, 'w') as f:
                json.dump(flow_test, f)

            result = self.validator.validate_file(flow_file)
            assert not result.is_valid
            assert any("@{unknownArg}" in str(e) and "not defined in screen" in str(e) for e in result.errors)

    def test_flow_file_step_override_existing_arg_passes(self):
        """Test flow file step that overrides existing screen arg passes."""
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create screen test with all args defined
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login"},
                "cases": [{
                    "name": "input",
                    "description": "Login input",
                    "args": {"userName": "default", "password": "default_pass"},
                    "steps": [
                        {"action": "input", "id": "username", "value": "@{userName}"},
                        {"action": "input", "id": "password", "value": "@{password}"}
                    ]
                }]
            }
            screen_path = Path(temp_dir) / "screens"
            screen_path.mkdir()
            with open(screen_path / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create flow test that overrides existing arg
            flow_test = {
                "type": "flow",
                "metadata": {"name": "login_flow"},
                "steps": [
                    {"file": "login", "case": "input", "args": {"password": "override_pass"}}
                ]
            }
            flow_path = Path(temp_dir) / "flows"
            flow_path.mkdir()
            flow_file = flow_path / "login_flow.test.json"
            with open(flow_file, 'w') as f:
                json.dump(flow_test, f)

            result = self.validator.validate_file(flow_file)
            assert result.is_valid

    def test_flow_file_step_screen_has_all_defaults_passes(self):
        """Test flow file step referencing screen with all defaults passes."""
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create screen test with all args defined
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login"},
                "cases": [{
                    "name": "input",
                    "description": "Login input",
                    "args": {"userName": "default", "password": "default_pass"},
                    "steps": [
                        {"action": "input", "id": "username", "value": "@{userName}"},
                        {"action": "input", "id": "password", "value": "@{password}"}
                    ]
                }]
            }
            screen_path = Path(temp_dir) / "screens"
            screen_path.mkdir()
            with open(screen_path / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create flow test without args (uses screen defaults)
            flow_test = {
                "type": "flow",
                "metadata": {"name": "login_flow"},
                "steps": [
                    {"file": "login", "case": "input"}
                ]
            }
            flow_path = Path(temp_dir) / "flows"
            flow_path.mkdir()
            flow_file = flow_path / "login_flow.test.json"
            with open(flow_file, 'w') as f:
                json.dump(flow_test, f)

            result = self.validator.validate_file(flow_file)
            assert result.is_valid

    def test_flow_file_step_multiple_args_override_passes(self):
        """Test flow can override multiple existing args defined in screen."""
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create screen test with all args defined
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login"},
                "cases": [{
                    "name": "input",
                    "description": "Login input",
                    "args": {
                        "userName": "default_user",
                        "password": "default_pass",
                        "env": "production"
                    },
                    "steps": [
                        {"action": "input", "id": "username", "value": "@{userName}"},
                        {"action": "input", "id": "password", "value": "@{password}"},
                        {"action": "input", "id": "env", "value": "@{env}"}
                    ]
                }]
            }
            screen_path = Path(temp_dir) / "screens"
            screen_path.mkdir()
            with open(screen_path / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create flow test that overrides all three args
            flow_test = {
                "type": "flow",
                "metadata": {"name": "login_flow"},
                "steps": [
                    {
                        "file": "login",
                        "case": "input",
                        "args": {
                            "userName": "override_user",
                            "password": "secret",
                            "env": "staging"
                        }
                    }
                ]
            }
            flow_path = Path(temp_dir) / "flows"
            flow_path.mkdir()
            flow_file = flow_path / "login_flow.test.json"
            with open(flow_file, 'w') as f:
                json.dump(flow_test, f)

            result = self.validator.validate_file(flow_file)
            assert result.is_valid


class TestSourceValidation:
    """Tests for source object validation."""

    def setup_method(self):
        self.validator = TestValidator()

    def test_valid_source_with_layout_only(self):
        """Test valid source with layout only."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count == 0

    def test_valid_source_with_document(self):
        """Test valid source with document."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "document": "docs/screens/test.html"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count == 0

    def test_source_unknown_key_warning(self):
        """Test unknown key in source produces warning."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "unknownKey": "value"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid  # Should pass with warning
        assert result.warning_count > 0
        assert any("Unknown source key: unknownKey" in str(w) for w in result.warnings)

    def test_source_multiple_unknown_keys_warning(self):
        """Test multiple unknown keys in source produce warnings."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "foo": "bar", "baz": "qux"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert any("Unknown source key: foo" in str(w) for w in result.warnings)
        assert any("Unknown source key: baz" in str(w) for w in result.warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
