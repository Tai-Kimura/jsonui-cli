"""CLI tests for doc generation.

Moved here from `test_tools/tests/test_cli.py`: `generate doc` (formerly the
bare `generate -f/-o/--schema`) and `generate html` moved to `jsonui-doc` when
doc generation left `jsonui-test`. The argument shapes did not change, only
the command word, so these are the original assertions repointed.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_doc_cli.cli import main


class TestGenerateDoc:
    """Tests for `jsonui-doc generate doc`."""

    def test_generate_markdown(self):
        """Test generating markdown documentation."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            input_path = f.name

        output_path = tempfile.mktemp(suffix='.md')

        try:
            with patch('sys.argv', ['jsonui-doc', 'generate', 'doc', '-f', input_path, '-o', output_path]):
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
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            input_path = f.name

        output_path = tempfile.mktemp(suffix='.html')

        try:
            with patch('sys.argv', ['jsonui-doc', 'generate', 'doc', '-f', input_path, '-o', output_path, '--format', 'html']):
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
            with patch('sys.argv', ['jsonui-doc', 'generate', 'doc', '--schema', '-o', output_path]):
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
        with patch('sys.argv', ['jsonui-doc', 'generate', 'doc', '--schema']):
            result = main()
            assert result == 0

    def test_generate_no_file_or_schema(self):
        """Test generate without file or schema shows help."""
        with patch('sys.argv', ['jsonui-test', 'generate']):
            result = main()
            assert result == 0  # Shows help when no subcommand given



class TestGenerateHtml:
    """Tests for `jsonui-doc generate html`."""

    def test_generate_html_directory(self):
        """Test generating HTML directory with index."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
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

            with patch('sys.argv', ['jsonui-doc', 'generate', 'html', str(input_dir), '-o', str(output_dir)]):
                result = main()
                assert result == 0
                assert (output_dir / "index.html").exists()
                assert (output_dir / "screens" / "test.test.html").exists()

    def test_generate_html_with_flow_tests(self):
        """Test generating HTML directory with flow tests."""
        screen_test = {
            "type": "screen",
            "source": {"layout": "login_test.json"},
            "metadata": {"name": "login_test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }
        flow_test = {
            "type": "flow",
            "metadata": {"name": "login_flow"},
            "steps": [{"screen": "login", "action": "tap", "id": "btn"}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()
            output_dir = Path(temp_dir) / "html"

            with open(input_dir / "login.test.json", 'w') as f:
                json.dump(screen_test, f)
            with open(input_dir / "login_flow.test.json", 'w') as f:
                json.dump(flow_test, f)

            with patch('sys.argv', ['jsonui-doc', 'generate', 'html', str(input_dir), '-o', str(output_dir)]):
                result = main()
                assert result == 0
                assert (output_dir / "screens" / "login.test.html").exists()
                assert (output_dir / "flows" / "login_flow.test.html").exists()

    def test_generate_html_with_title(self):
        """Test generating HTML with custom title."""
        test_data = {
            "type": "screen",
            "source": {"layout": "test.json"},
            "metadata": {"name": "test"},
            "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()
            output_dir = Path(temp_dir) / "html"

            with open(input_dir / "test.test.json", 'w') as f:
                json.dump(test_data, f)

            with patch('sys.argv', ['jsonui-doc', 'generate', 'html', str(input_dir), '-o', str(output_dir), '-t', 'My Test Docs']):
                result = main()
                assert result == 0

                index_content = (output_dir / "index.html").read_text()
                assert "My Test Docs" in index_content

    def test_generate_html_nonexistent_input(self):
        """Test generating HTML with nonexistent input directory."""
        with patch('sys.argv', ['jsonui-doc', 'generate', 'html', '/nonexistent/path']):
            result = main()
            assert result == 1
