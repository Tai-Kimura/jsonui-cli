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
            "source": {"layout": "test.json"},
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

    def test_valid_typetext_action(self):
        """typeText types into the focused field — valid with only 'value' (no id)."""
        data = self._make_test([{"action": "typeText", "value": "123456"}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_typetext_missing_value(self):
        """typeText without value fails."""
        data = self._make_test([{"action": "typeText"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'value'" in str(e) for e in result.errors)

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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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


class TestFlowSourcesAndInlineScreenValidation:
    """Tests mirroring the driver models: sources must be an array of
    {layout, alias?, spec?}, and inline flow steps must name their screen."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_flow_test(self, **overrides) -> dict:
        data = {
            "type": "flow",
            "metadata": {"name": "flow_test"},
            "steps": [{"screen": "login", "action": "tap", "id": "button_id"}]
        }
        data.update(overrides)
        return data

    def test_sources_object_map_fails(self):
        """An object map for sources crashes driver deserialization — must error."""
        data = self._make_flow_test(sources={"login": "layouts/login.json"})
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must be an array" in str(e) for e in result.errors)

    def test_sources_empty_array_fails(self):
        data = self._make_flow_test(sources=[])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_sources_entry_missing_layout_fails(self):
        data = self._make_flow_test(sources=[{"alias": "login"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("'layout'" in str(e) for e in result.errors)

    def test_sources_entry_non_object_fails(self):
        data = self._make_flow_test(sources=["layouts/login.json"])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_sources_entry_non_string_alias_fails(self):
        data = self._make_flow_test(sources=[{"layout": "layouts/login.json", "alias": 1}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_sources_unknown_key_fails(self):
        """Schema says additionalProperties: false — unknown keys are errors, not warnings."""
        data = self._make_flow_test(sources=[{"layout": "layouts/login.json", "screen": "login"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Unknown key in source: screen" in str(e) for e in result.errors)

    def test_sources_document_is_canonical(self):
        data = self._make_flow_test(sources=[{"layout": "layouts/login.json", "document": "specs/Login.md", "alias": "login"}])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert result.warning_count == 0

    def test_sources_spec_is_deprecated_alias(self):
        """'spec' (the pre-rename key) still validates, with a deprecation warning."""
        data = self._make_flow_test(sources=[{"layout": "layouts/login.json", "spec": "specs/Login.md"}])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert any("'spec' is deprecated" in str(w) for w in result.warnings)

    def test_sources_spec_and_document_conflict_fails(self):
        data = self._make_flow_test(sources=[{"layout": "layouts/login.json", "spec": "a.md", "document": "b.md"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("deprecated alias" in str(e) for e in result.errors)

    def test_inline_step_without_screen_fails(self):
        data = self._make_flow_test(steps=[{"assert": "visible", "id": "app_title_label"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("'screen'" in str(e) for e in result.errors)

    def test_inline_step_with_empty_screen_fails(self):
        data = self._make_flow_test(steps=[{"screen": "  ", "action": "tap", "id": "button_id"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_setup_inline_step_without_screen_fails(self):
        data = self._make_flow_test(setup=[{"action": "waitFor", "id": "launch", "timeout": 5000}])
        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_block_inner_steps_do_not_need_screen(self):
        """Block inner steps execute directly (toTestStep) — no screen required."""
        data = self._make_flow_test(steps=[{
            "block": "login_block",
            "steps": [{"action": "tap", "id": "button_id"}]
        }])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_file_steps_do_not_need_screen(self):
        data = self._make_flow_test(steps=[{"file": "login", "case": "valid_login"}])
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
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [{"steps": [{"action": "tap", "id": "elem"}]}]
        }

        result = self.validator.validate_data(data)
        assert not result.is_valid

    def test_case_empty_steps_warning(self):
        """Test case with empty steps produces warning."""
        data = {
            "type": "screen",
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            {"screen": "home", "action": "waitFor", "id": "home_screen", "timeout": 5000},
            {"file": "screens/home", "cases": ["verify_display", "navigate_to_profile"]},
            {"screen": "profile", "assert": "visible", "id": "profile_title"}
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
                {"screen": "launch", "action": "waitFor", "id": "launch_screen", "timeout": 5000}
            ],
            "steps": [
                {"screen": "home", "action": "tap", "id": "start_button"}
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
                {"screen": "home", "action": "tap", "id": "start_button"}
            ],
            "teardown": [
                {"screen": "home", "action": "screenshot", "name": "final_state"}
            ]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    # Regression: test-web-script-step-for-browser-side-hooks — emitHook /
    # openedUrl are the web-only browser-hook vocabulary (Plan B: limited
    # API, not a raw script step).
    def _screen_with_steps(self, steps):
        return {
            "type": "screen",
            "source": {"layout": "layouts/test.json"},
            "metadata": {"name": "hook_test"},
            "cases": [{"name": "case", "steps": steps}]
        }

    def test_emit_hook_valid_with_platform_gate(self):
        data = self._screen_with_steps([
            {"action": "emitHook", "name": "rtdb", "hookArgs": ["op-1", "succeeded"],
             "when": {"platform": "web"}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert not any("emitHook is web-only" in w.message for w in result.warnings)

    def test_emit_hook_without_gate_warns(self):
        data = self._screen_with_steps([
            {"action": "emitHook", "name": "rtdb"}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert any("emitHook is web-only" in w.message for w in result.warnings)

    def test_emit_hook_missing_name_fails(self):
        data = self._screen_with_steps([
            {"action": "emitHook", "hookArgs": []}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'name'" in e.message for e in result.errors)

    def test_emit_hook_non_array_hook_args_fails(self):
        data = self._screen_with_steps([
            {"action": "emitHook", "name": "rtdb", "hookArgs": {"op": 1}}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("'hookArgs' must be an array" in e.message for e in result.errors)

    def test_opened_url_requires_matcher(self):
        data = self._screen_with_steps([
            {"assert": "openedUrl"}
        ])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must have 'equals' or 'contains'" in e.message for e in result.errors)

    def test_opened_url_valid_with_contains(self):
        data = self._screen_with_steps([
            {"assert": "openedUrl", "contains": "/files/", "when": {"platform": "web"}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_add_media_with_target_id_valid(self):
        data = self._screen_with_steps([
            {"action": "addMedia", "id": "icon_upload_input", "paths": ["fixtures/icon.png"]}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_with_file_level_mocks_valid(self):
        """Flow file-level mocks: a well-formed map validates (drivers apply it).

        Regression: test-flow-file-level-mocks-silently-ignored — file-level
        mocks used to pass validation but be silently dropped at runtime. Now
        the drivers apply them and the validator checks the map shape.
        """
        data = {
            "type": "flow",
            "metadata": {"name": "flow_with_mocks"},
            "mocks": {"listHistory": "real_id"},
            "steps": [
                {"screen": "home", "action": "tap", "id": "start_button"}
            ]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_flow_file_level_mocks_non_string_scenario_fails(self):
        """Flow file-level mocks with a non-string scenario is an error."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_bad_mocks"},
            "mocks": {"listHistory": 123},
            "steps": [
                {"screen": "home", "action": "tap", "id": "start_button"}
            ]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("scenario name must be a string" in e.message for e in result.errors)

    def test_flow_file_level_mocks_non_object_fails(self):
        """Flow file-level mocks that is not an object is an error."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_bad_mocks_type"},
            "mocks": ["listHistory"],
            "steps": [
                {"screen": "home", "action": "tap", "id": "start_button"}
            ]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("must be an object of operationId" in e.message for e in result.errors)

    def test_flow_with_checkpoints(self):
        """Test flow test with checkpoints."""
        data = {
            "type": "flow",
            "metadata": {"name": "flow_with_checkpoints"},
            "steps": [
                {"screen": "login", "action": "tap", "id": "login_button"},
                {"screen": "home", "action": "waitFor", "id": "home_screen", "timeout": 5000}
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            {"screen": "home", "action": "waitFor", "id": "home", "timeout": 5000},
            {"file": "home", "args": {"welcomeText": "Hello"}}
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    # Undefined args validation (screen test)
    def test_screen_case_undefined_arg_fails(self):
        """Test screen case with undefined @{varName} fails."""
        data = {
            "type": "screen",
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            "source": {"layout": "test.json"},
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
            {"screen": "home", "action": "waitFor", "id": "home_screen", "timeout": 5000},
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
                "source": {"layout": "test.json"},
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
                "source": {"layout": "test.json"},
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
                "source": {"layout": "test.json"},
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
                "source": {"layout": "test.json"},
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

    def test_source_unknown_key_fails(self):
        """Schema says additionalProperties: false — unknown keys are errors, not warnings."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "unknownKey": "value"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Unknown source key: unknownKey" in str(e) for e in result.errors)

    def test_source_multiple_unknown_keys_fail(self):
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "foo": "bar", "baz": "qux"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Unknown source key: foo" in str(e) for e in result.errors)
        assert any("Unknown source key: baz" in str(e) for e in result.errors)

    def test_source_spec_is_deprecated_alias(self):
        """'spec' was flow-test's canonical key pre-2026-08-01 and leaked into
        screen tests (3 of 4 shipped examples): warn, don't break."""
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "spec": "specs/Test.md"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert result.is_valid
        assert any("'spec' is deprecated" in str(w) for w in result.warnings)

    def test_source_spec_and_document_conflict_fails(self):
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json", "spec": "a.md", "document": "b.md"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}]
        }
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("deprecated alias" in str(e) for e in result.errors)


class TestTopLevelKeyValidation:
    """Per-type top-level key sets, unknown keys as errors.

    Same track as TestSourceValidation (the schemas say
    additionalProperties: false): before this, screen tests warned against the
    screen∪flow union — so flow-only keys passed silently — and flow tests had
    no top-level check at all."""

    def setup_method(self):
        self.validator = TestValidator()

    def _screen(self, **extra) -> dict:
        data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "Test case", "steps": [{"action": "tap", "id": "btn"}]}],
        }
        data.update(extra)
        return data

    def _flow(self, **extra) -> dict:
        data = {
            "type": "flow",
            "sources": [{"layout": "layouts/screen1.json", "alias": "screen1"}],
            "metadata": {"name": "flow_test"},
            "steps": [{"screen": "screen1", "action": "tap", "id": "button_id"}],
        }
        data.update(extra)
        return data

    def test_screen_unknown_top_level_key_fails(self):
        result = self.validator.validate_data(self._screen(futureKey="x"))
        assert not result.is_valid
        assert any("Unknown top-level key: futureKey" in str(e) for e in result.errors)

    def test_screen_with_flow_key_fails_with_type_hint(self):
        """The wrong-type mistake: flow keys in a screen test used to pass
        without even a warning (shared union set)."""
        result = self.validator.validate_data(
            self._screen(steps=[{"screen": "s", "action": "tap", "id": "b"}], checkpoints=[])
        )
        assert not result.is_valid
        assert any("'steps' is a flow-test key" in str(e) for e in result.errors)
        assert any("'checkpoints' is a flow-test key" in str(e) for e in result.errors)

    def test_flow_unknown_top_level_key_fails(self):
        """Flow tests previously had no top-level key check at all."""
        result = self.validator.validate_data(self._flow(futureKey="x"))
        assert not result.is_valid
        assert any("Unknown top-level key: futureKey" in str(e) for e in result.errors)

    def test_flow_with_screen_key_fails_with_type_hint(self):
        result = self.validator.validate_data(
            self._flow(cases=[], source={"layout": "layouts/test.json"})
        )
        assert not result.is_valid
        assert any("'cases' is a screen-test key" in str(e) for e in result.errors)
        assert any("'source' is a screen-test key" in str(e) for e in result.errors)

    def test_screen_full_key_set_passes(self):
        """Every schema-legal screen key at once — no top-level complaints."""
        data = self._screen(**{
            "$schema": "https://example.invalid/screen-test.schema.json",
            "platform": "ios",
            "embeddedIn": {"screen": "home"},
            "initialState": {},
            "launch": {"clearState": True},
            "setup": [],
            "teardown": [],
        })
        result = self.validator.validate_data(data)
        top_level = [m for m in result.errors + result.warnings
                     if "top-level" in str(m) or "not valid in" in str(m)]
        assert top_level == []

    def test_flow_full_key_set_passes(self):
        """Every schema-legal flow key at once — no top-level complaints
        (descriptionFile and checkpoints are flow-legal)."""
        data = self._flow(**{
            "$schema": "https://example.invalid/flow-test.schema.json",
            "platform": "ios",
            "initialState": {},
            "launch": {"clearState": True},
            "setup": [],
            "teardown": [],
            "checkpoints": [],
            "descriptionFile": "descriptions/flow.md",
        })
        result = self.validator.validate_data(data)
        top_level = [m for m in result.errors + result.warnings
                     if "top-level" in str(m) or "not valid in" in str(m)]
        assert top_level == []


class TestPlatformFieldValidation:
    """Tests for test-level and case-level 'platform' enum validation.

    The schema set is scalar ios|android|web|all or an array of ios|android|web
    ("all" is not a legal array item). Not SUPPORTED_PLATFORMS: ios-swiftui /
    ios-uikit are forbidden at test/case level.
    """

    def setup_method(self):
        self.validator = TestValidator()

    def _screen(self, platform=None, case_platform=None):
        case = {"name": "case1", "description": "d", "steps": [{"action": "back"}]}
        if case_platform is not None:
            case["platform"] = case_platform
        data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [case],
        }
        if platform is not None:
            data["platform"] = platform
        return data

    def _flow(self, platform):
        return {
            "type": "flow",
            "metadata": {"name": "test", "description": "Test"},
            "platform": platform,
            "steps": [{"screen": "home", "action": "back"}],
        }

    # --- test-level, screen ---

    def test_screen_valid_scalar_platforms(self):
        for platform in ["ios", "android", "web", "all"]:
            result = self.validator.validate_data(self._screen(platform=platform))
            assert result.is_valid, platform

    def test_screen_valid_array_platform(self):
        result = self.validator.validate_data(self._screen(platform=["ios", "web"]))
        assert result.is_valid

    def test_screen_invalid_scalar_platform(self):
        result = self.validator.validate_data(self._screen(platform="ios-swiftui"))
        assert not result.is_valid
        assert any("Invalid platform: ios-swiftui" in str(e) for e in result.errors)

    def test_screen_all_not_allowed_in_array(self):
        result = self.validator.validate_data(self._screen(platform=["all"]))
        assert not result.is_valid
        assert any("Invalid platform: all" in str(e) for e in result.errors)

    def test_screen_empty_platform_array(self):
        result = self.validator.validate_data(self._screen(platform=[]))
        assert not result.is_valid
        assert any("must not be empty" in str(e) for e in result.errors)

    def test_screen_platform_wrong_type(self):
        result = self.validator.validate_data(self._screen(platform=123))
        assert not result.is_valid
        assert any("must be a string or array" in str(e) for e in result.errors)

    # --- case-level, screen only ---

    def test_case_valid_platform(self):
        result = self.validator.validate_data(self._screen(case_platform="android"))
        assert result.is_valid
        result = self.validator.validate_data(self._screen(case_platform=["android", "web"]))
        assert result.is_valid

    def test_case_invalid_platform(self):
        result = self.validator.validate_data(self._screen(case_platform="ios-uikit"))
        assert not result.is_valid
        assert any("Invalid platform: ios-uikit" in str(e) for e in result.errors)

    def test_case_all_not_allowed_in_array(self):
        result = self.validator.validate_data(self._screen(case_platform=["all"]))
        assert not result.is_valid
        assert any("Invalid platform: all" in str(e) for e in result.errors)

    # --- test-level, flow ---

    def test_flow_valid_platforms(self):
        for platform in ["ios", "all", ["android", "web"]]:
            result = self.validator.validate_data(self._flow(platform))
            assert result.is_valid, platform

    def test_flow_invalid_scalar_platform(self):
        result = self.validator.validate_data(self._flow("ios-swiftui"))
        assert not result.is_valid
        assert any("Invalid platform: ios-swiftui" in str(e) for e in result.errors)

    def test_flow_all_not_allowed_in_array(self):
        result = self.validator.validate_data(self._flow(["all"]))
        assert not result.is_valid
        assert any("Invalid platform: all" in str(e) for e in result.errors)


class TestResponsiveConditionValidation:
    """Tests for the 'responsive' condition key (when / repeat.while).

    Value is a named size-class bucket from the render-side canonical
    vocabulary (compact/medium/regular/landscape + hyphenated combos) or a
    constraint object (minWidth/maxWidth/minHeight/maxHeight/orientation).
    """

    def setup_method(self):
        self.validator = TestValidator()

    def _screen_with_when(self, responsive):
        return {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{
                "name": "case1",
                "description": "d",
                "steps": [{"assert": "visible", "id": "sidebar", "when": {"responsive": responsive}}],
            }],
        }

    # --- valid ---

    def test_valid_named_buckets(self):
        for bucket in ["compact", "medium", "regular", "landscape",
                       "compact-landscape", "medium-landscape", "regular-landscape"]:
            result = self.validator.validate_data(self._screen_with_when(bucket))
            assert result.is_valid, bucket

    def test_valid_constraint_object(self):
        result = self.validator.validate_data(self._screen_with_when(
            {"minWidth": 768, "maxWidth": 1024, "orientation": "portrait"}))
        assert result.is_valid

    def test_valid_single_key_constraint(self):
        for constraint in [{"minWidth": 600}, {"maxHeight": 900.5}, {"orientation": "landscape"}]:
            result = self.validator.validate_data(self._screen_with_when(constraint))
            assert result.is_valid, constraint

    def test_valid_responsive_in_repeat_while(self):
        data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{
                "name": "case1",
                "description": "d",
                "steps": [{
                    "action": "repeat",
                    "while": {"responsive": "regular"},
                    "times": 3,
                    "steps": [{"action": "back"}],
                }],
            }],
        }
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_valid_responsive_anded_with_platform(self):
        result = self.validator.validate_data(self._screen_with_when("regular"))
        assert result.is_valid
        data = self._screen_with_when("regular")
        data["cases"][0]["steps"][0]["when"]["platform"] = "web"
        result = self.validator.validate_data(data)
        assert result.is_valid

    # --- malformed ---

    def test_unknown_bucket_expanded(self):
        # 'expanded' is Material-3 vocabulary the renderer never emits
        result = self.validator.validate_data(self._screen_with_when("expanded"))
        assert not result.is_valid
        assert any("Invalid responsive bucket: expanded" in str(e) for e in result.errors)

    def test_empty_constraint_object(self):
        result = self.validator.validate_data(self._screen_with_when({}))
        assert not result.is_valid
        assert any("at least one key" in str(e) for e in result.errors)

    def test_non_numeric_width(self):
        result = self.validator.validate_data(self._screen_with_when({"minWidth": "big"}))
        assert not result.is_valid
        assert any("'minWidth' must be a number >= 0" in str(e) for e in result.errors)

    def test_boolean_width_rejected(self):
        result = self.validator.validate_data(self._screen_with_when({"minWidth": True}))
        assert not result.is_valid
        assert any("'minWidth' must be a number >= 0" in str(e) for e in result.errors)

    def test_negative_height(self):
        result = self.validator.validate_data(self._screen_with_when({"maxHeight": -1}))
        assert not result.is_valid
        assert any("'maxHeight' must be a number >= 0" in str(e) for e in result.errors)

    def test_min_width_greater_than_max_width(self):
        result = self.validator.validate_data(self._screen_with_when({"minWidth": 1024, "maxWidth": 768}))
        assert not result.is_valid
        assert any("'minWidth' (1024) must not exceed 'maxWidth' (768)" in str(e) for e in result.errors)

    def test_min_height_greater_than_max_height(self):
        result = self.validator.validate_data(self._screen_with_when({"minHeight": 900, "maxHeight": 400}))
        assert not result.is_valid
        assert any("'minHeight' (900) must not exceed 'maxHeight' (400)" in str(e) for e in result.errors)

    def test_bad_orientation(self):
        result = self.validator.validate_data(self._screen_with_when({"orientation": "upside-down"}))
        assert not result.is_valid
        assert any("Invalid responsive orientation" in str(e) for e in result.errors)

    def test_unknown_constraint_key(self):
        result = self.validator.validate_data(self._screen_with_when({"minDepth": 3}))
        assert not result.is_valid
        assert any("Unknown responsive constraint key: minDepth" in str(e) for e in result.errors)

    def test_wrong_type(self):
        result = self.validator.validate_data(self._screen_with_when(768))
        assert not result.is_valid
        assert any("must be a bucket name string or constraint object" in str(e) for e in result.errors)


class TestCaseLevelResponsiveValidation:
    """Tests for case-level 'responsive' (screen tests only, parity with
    case-level 'platform'; flow tests have no case objects)."""

    def setup_method(self):
        self.validator = TestValidator()

    def _screen(self, case_responsive):
        return {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{
                "name": "case1",
                "description": "d",
                "responsive": case_responsive,
                "steps": [{"action": "back"}],
            }],
        }

    def test_case_valid_named_bucket(self):
        result = self.validator.validate_data(self._screen("regular-landscape"))
        assert result.is_valid

    def test_case_valid_constraint(self):
        result = self.validator.validate_data(self._screen({"minWidth": 840}))
        assert result.is_valid

    def test_case_valid_with_platform(self):
        data = self._screen("regular")
        data["cases"][0]["platform"] = "web"
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_case_unknown_bucket(self):
        result = self.validator.validate_data(self._screen("expanded"))
        assert not result.is_valid
        assert any("Invalid responsive bucket: expanded" in str(e) for e in result.errors)

    def test_case_empty_constraint(self):
        result = self.validator.validate_data(self._screen({}))
        assert not result.is_valid
        assert any("at least one key" in str(e) for e in result.errors)

    def test_case_contradictory_constraint(self):
        result = self.validator.validate_data(self._screen({"minWidth": 1000, "maxWidth": 10}))
        assert not result.is_valid
        assert any("must not exceed" in str(e) for e in result.errors)

    def test_case_responsive_path_in_error(self):
        result = self.validator.validate_data(self._screen("expanded"))
        assert any("cases[0].responsive" in str(e) for e in result.errors)


class TestSetViewportSetOrientationValidation:
    """Tests for the setViewport / setOrientation actions."""

    def setup_method(self):
        self.validator = TestValidator()

    def _make_test(self, steps: list) -> dict:
        return {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test", "description": "Test"},
            "cases": [{"name": "case1", "description": "d", "steps": steps}],
        }

    # --- setViewport ---

    def test_valid_set_viewport(self):
        data = self._make_test([{"action": "setViewport", "width": 375, "height": 812}])
        result = self.validator.validate_data(data)
        assert result.is_valid

    def test_set_viewport_missing_width(self):
        data = self._make_test([{"action": "setViewport", "height": 812}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'width'" in str(e) for e in result.errors)

    def test_set_viewport_missing_height(self):
        data = self._make_test([{"action": "setViewport", "width": 375}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'height'" in str(e) for e in result.errors)

    def test_set_viewport_zero_width(self):
        data = self._make_test([{"action": "setViewport", "width": 0, "height": 812}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("'width' must be a positive integer" in str(e) for e in result.errors)

    def test_set_viewport_non_integer_height(self):
        for bad in ["812", 812.5, True]:
            data = self._make_test([{"action": "setViewport", "width": 375, "height": bad}])
            result = self.validator.validate_data(data)
            assert not result.is_valid, bad
            assert any("'height' must be a positive integer" in str(e) for e in result.errors)

    def test_set_viewport_with_when_responsive(self):
        # Sweep segments self-gate with a matching when.responsive (plan §4 rule)
        data = self._make_test([
            {"action": "setViewport", "width": 1280, "height": 800, "when": {"platform": "web"}},
            {"assert": "visible", "id": "sidebar", "when": {"responsive": "regular"}},
        ])
        result = self.validator.validate_data(data)
        assert result.is_valid

    # --- setOrientation ---

    def test_valid_set_orientation(self):
        for orientation in ["portrait", "landscape"]:
            data = self._make_test([{"action": "setOrientation", "orientation": orientation}])
            result = self.validator.validate_data(data)
            assert result.is_valid, orientation

    def test_set_orientation_missing_orientation(self):
        data = self._make_test([{"action": "setOrientation"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required parameter 'orientation'" in str(e) for e in result.errors)

    def test_set_orientation_invalid_value(self):
        data = self._make_test([{"action": "setOrientation", "orientation": "sideways"}])
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Invalid orientation: 'sideways'" in str(e) for e in result.errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
