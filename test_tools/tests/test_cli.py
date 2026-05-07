"""Tests for the CLI module."""

import pytest
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.cli import main, cmd_validate, cmd_generate


class TestCLIValidate:
    """Tests for validate command."""

    def test_validate_valid_file(self):
        """Test validating a valid file."""
        test_data = {
            "type": "screen",
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


class TestCLIGenerate:
    """Tests for generate command."""

    def test_generate_markdown(self):
        """Test generating markdown documentation."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            input_path = f.name

        output_path = tempfile.mktemp(suffix='.md')

        try:
            with patch('sys.argv', ['jsonui-test', 'generate', '-f', input_path, '-o', output_path]):
                result = main()
                assert result == 0
                assert Path(output_path).exists()
        finally:
            Path(input_path).unlink()
            if Path(output_path).exists():
                Path(output_path).unlink()

    def test_generate_html(self):
        """Test generating HTML documentation."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            input_path = f.name

        output_path = tempfile.mktemp(suffix='.html')

        try:
            with patch('sys.argv', ['jsonui-test', 'generate', '-f', input_path, '-o', output_path, '--format', 'html']):
                result = main()
                assert result == 0
                assert Path(output_path).exists()

                content = Path(output_path).read_text()
                assert "<!DOCTYPE html>" in content
        finally:
            Path(input_path).unlink()
            if Path(output_path).exists():
                Path(output_path).unlink()

    def test_generate_schema(self):
        """Test generating schema reference."""
        output_path = tempfile.mktemp(suffix='.md')

        try:
            with patch('sys.argv', ['jsonui-test', 'generate', '--schema', '-o', output_path]):
                result = main()
                assert result == 0
                assert Path(output_path).exists()

                content = Path(output_path).read_text()
                assert "JsonUI Test Schema Reference" in content
        finally:
            if Path(output_path).exists():
                Path(output_path).unlink()

    def test_generate_schema_stdout(self):
        """Test generating schema to stdout."""
        with patch('sys.argv', ['jsonui-test', 'generate', '--schema']):
            result = main()
            assert result == 0

    def test_generate_no_file_or_schema(self):
        """Test generate without file or schema shows help."""
        with patch('sys.argv', ['jsonui-test', 'generate']):
            result = main()
            assert result == 0  # Shows help when no subcommand given


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


class TestCLIGenerateHtml:
    """Tests for generate html command."""

    def test_generate_html_directory(self):
        """Test generating HTML directory with index."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "test", "description": "Test screen"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()
            output_dir = Path(temp_dir) / "html"

            # Create test file
            with open(input_dir / "test.test.json", 'w') as f:
                json.dump(test_data, f)

            with patch('sys.argv', ['jsonui-test', 'generate', 'html', str(input_dir), '-o', str(output_dir)]):
                result = main()
                assert result == 0
                assert (output_dir / "index.html").exists()
                assert (output_dir / "screens" / "test.test.html").exists()

    def test_generate_html_with_flow_tests(self):
        """Test generating HTML directory with flow tests."""
        screen_test = {
            "type": "screen",
            "metadata": {"name": "login_test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }
        flow_test = {
            "type": "flow",
            "metadata": {"name": "login_flow"},
            "steps": [{"action": "tap", "id": "btn"}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()
            output_dir = Path(temp_dir) / "html"

            with open(input_dir / "login.test.json", 'w') as f:
                json.dump(screen_test, f)
            with open(input_dir / "login_flow.test.json", 'w') as f:
                json.dump(flow_test, f)

            with patch('sys.argv', ['jsonui-test', 'generate', 'html', str(input_dir), '-o', str(output_dir)]):
                result = main()
                assert result == 0
                assert (output_dir / "screens" / "login.test.html").exists()
                assert (output_dir / "flows" / "login_flow.test.html").exists()

    def test_generate_html_with_title(self):
        """Test generating HTML with custom title."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()
            output_dir = Path(temp_dir) / "html"

            with open(input_dir / "test.test.json", 'w') as f:
                json.dump(test_data, f)

            with patch('sys.argv', ['jsonui-test', 'generate', 'html', str(input_dir), '-o', str(output_dir), '-t', 'My Test Docs']):
                result = main()
                assert result == 0

                index_content = (output_dir / "index.html").read_text()
                assert "My Test Docs" in index_content

    def test_generate_html_nonexistent_input(self):
        """Test generating HTML with nonexistent input directory."""
        with patch('sys.argv', ['jsonui-test', 'generate', 'html', '/nonexistent/path']):
            result = main()
            assert result == 1


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

    def test_validate_valid_flow_test(self):
        """Test validating a valid flow test file."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "login_flow"},
            "steps": [
                {"file": "screens/login", "case": "valid_login"},
                {"action": "waitFor", "id": "home_screen", "timeout": 5000},
                {"assert": "visible", "id": "welcome_message"}
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
