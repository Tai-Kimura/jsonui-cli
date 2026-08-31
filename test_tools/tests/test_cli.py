"""Tests for the CLI module.

Doc generation (`generate doc` / `generate html`) moved out to `jsonui-doc`;
its CLI tests moved with it, to `document_tools/tests/test_test_doc_cli.py`.
What stays here is what `jsonui-test` still owns: `validate`, `generate test
screen|flow`, and `generate description`.
"""

import pytest
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import main


class TestCLIValidate:
    """Tests for validate command."""

    def test_validate_valid_file(self):
        """Test validating a valid file."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [
                {"name": "case1", "steps": [{"action": "tap", "id": "btn"}]}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['jsonui-test', 'validate', temp_path]):
                result = main()
                assert result == 0
        finally:
            Path(temp_path).unlink()

    def test_validate_invalid_file(self):
        """Test validating an invalid file."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "cases": [
                {"name": "case1", "steps": [{"action": "invalid_action"}]}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['jsonui-test', 'validate', temp_path]):
                result = main()
                assert result == 1
        finally:
            Path(temp_path).unlink()

    def test_validate_directory(self):
        """Test validating a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create valid test file
            test_data = {
                "type": "screen",
                "source": {"layout": "test.json"},
                "metadata": {"name": "test"},
                "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
            }

            test_file = Path(temp_dir) / "sample.test.json"
            with open(test_file, 'w') as f:
                json.dump(test_data, f)

            with patch('sys.argv', ['jsonui-test', 'validate', temp_dir]):
                result = main()
                assert result == 0

    def test_validate_nonexistent_file(self):
        """Test validating nonexistent file."""
        with patch('sys.argv', ['jsonui-test', 'validate', '/nonexistent/path.test.json']):
            result = main()
            assert result == 1

    def test_validate_verbose(self):
        """Test verbose output."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['jsonui-test', 'validate', '-v', temp_path]):
                result = main()
                assert result == 0
        finally:
            Path(temp_path).unlink()


class TestCLIHelp:
    """Tests for help and version."""

    def test_no_command_shows_help(self):
        """Test no command shows help."""
        with patch('sys.argv', ['jsonui-test']):
            result = main()
            assert result == 0

    def test_version(self):
        """Test version flag."""
        with patch('sys.argv', ['jsonui-test', '--version']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestCLIGenerateTestTemplates:
    """Tests for generate test template commands."""

    def test_generate_test_screen(self):
        """Test generating screen test template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "login.test.json"

            with patch('sys.argv', ['jsonui-test', 'generate', 'test', 'screen', 'Login', '--path', str(output_path)]):
                result = main()
                assert result == 0
                assert output_path.exists()

                content = json.loads(output_path.read_text())
                assert content["type"] == "screen"
                assert "Login" in content["metadata"]["name"]

    def test_generate_test_flow(self):
        """Test generating flow test template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "login_flow.test.json"

            with patch('sys.argv', ['jsonui-test', 'generate', 'test', 'flow', 'LoginFlow', '--path', str(output_path)]):
                result = main()
                assert result == 0
                assert output_path.exists()

                content = json.loads(output_path.read_text())
                assert content["type"] == "flow"
                assert "LoginFlow" in content["metadata"]["name"]

    def test_generate_test_with_platform(self):
        """Test generating test template with platform."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test.test.json"

            with patch('sys.argv', ['jsonui-test', 'generate', 'test', 'screen', 'Test', '--path', str(output_path), '-p', 'ios']):
                result = main()
                assert result == 0

                content = json.loads(output_path.read_text())
                assert content["platform"] == "ios"


class TestCLIGenerateDescription:
    """Tests for generate description command."""

    def test_generate_description_screen(self):
        """Test generating description for screen test."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "initial_display.json"

            with patch('sys.argv', ['jsonui-test', 'generate', 'description', 'screen', 'Login', 'initial_display', '--path', str(output_path)]):
                result = main()
                assert result == 0
                assert output_path.exists()

                content = json.loads(output_path.read_text())
                assert content["case_name"] == "initial_display"
                assert "summary" in content
                assert "preconditions" in content

    def test_generate_description_flow(self):
        """Test generating description for flow test."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "happy_path.json"

            with patch('sys.argv', ['jsonui-test', 'generate', 'description', 'flow', 'LoginFlow', 'happy_path', '--path', str(output_path)]):
                result = main()
                assert result == 0
                assert output_path.exists()

                content = json.loads(output_path.read_text())
                assert content["case_name"] == "happy_path"


class TestCLIValidateFlowTests:
    """Tests for validating flow tests via CLI."""

    def test_validate_valid_flow_test(self, capsys):
        """A flow test that is actually valid validates clean.

        Written as a bare temp file with a dangling `screens/login` reference,
        it passed on the return code while emitting two warnings, so it never
        pinned "valid" — only "not an error". The referenced screen test is
        real here, and the absence of warnings is asserted.

        Inline steps carry `screen`: the drivers' `isInlineStep` requires it,
        so a screen-less action step deserializes but never runs on device.
        """
        screen_test = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "login"},
            "cases": [{"name": "valid_login", "steps": [{"action": "back"}]}]
        }
        flow_test = {
            "type": "flow",
            "metadata": {"name": "login_flow"},
            "steps": [
                {"file": "login", "case": "valid_login"},
                {"screen": "home", "action": "waitFor", "id": "home_screen", "timeout": 5000},
                {"screen": "home", "assert": "visible", "id": "welcome_message"}
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            screens_dir = Path(temp_dir) / "screens"
            screens_dir.mkdir()
            (screens_dir / "login.test.json").write_text(json.dumps(screen_test))

            flow_path = Path(temp_dir) / "login_flow.test.json"
            flow_path.write_text(json.dumps(flow_test))

            with patch('sys.argv', ['jsonui-test', 'validate', str(flow_path)]):
                result = main()
                assert result == 0

        assert "[WARN]" not in capsys.readouterr().out

    def test_validate_invalid_flow_test(self):
        """Test validating an invalid flow test file."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "bad_flow"},
            "steps": [
                {"file": "", "case": "test"}  # Empty file reference
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['jsonui-test', 'validate', temp_path]):
                result = main()
                assert result == 1
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
