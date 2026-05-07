"""Tests for the generator module."""

import pytest
import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.generator import DocumentGenerator, generate_schema_reference


class TestDocumentGenerator:
    """Tests for DocumentGenerator."""

    def setup_method(self):
        self.generator = DocumentGenerator()

    def test_generate_markdown_basic(self):
        """Test basic markdown generation."""
        # Create a temp test file
        test_data = {
            "type": "screen",
            "source": {"layout": "layouts/test.json"},
            "metadata": {
                "name": "Sample Test",
                "description": "A sample test for documentation"
            },
            "platform": "ios",
            "cases": [
                {
                    "name": "initial_display",
                    "description": "Verify initial elements",
                    "steps": [
                        {"action": "waitFor", "id": "root_view", "timeout": 5000},
                        {"assert": "visible", "id": "title_label"}
                    ]
                }
            ]
        }

        # Write temp file
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="markdown")

            assert "# Sample Test" in content
            assert "A sample test for documentation" in content
            assert "initial_display" in content
            assert "`waitFor`" in content
            assert "`visible`" in content
            assert "root_view" in content
        finally:
            temp_path.unlink()

    def test_generate_html_basic(self):
        """Test basic HTML generation."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "HTML Test"},
            "cases": [
                {
                    "name": "test_case",
                    "steps": [{"action": "tap", "id": "button"}]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "<!DOCTYPE html>" in content
            assert "<title>HTML Test" in content
            assert "<code>tap</code>" in content
            assert "<code>button</code>" in content
        finally:
            temp_path.unlink()

    def test_generate_fails_on_invalid_file(self):
        """Test generation fails on invalid test file."""
        test_data = {
            "type": "screen",
            "cases": [
                {
                    "name": "bad_case",
                    "steps": [{"action": "unknown_action"}]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError):
                self.generator.generate(temp_path)
        finally:
            temp_path.unlink()

    def test_generate_with_output_file(self):
        """Test generation writes to output file."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "Output Test"},
            "cases": [
                {"name": "case1", "steps": [{"action": "back"}]}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            input_path = Path(f.name)

        output_path = Path(tempfile.mktemp(suffix='.md'))

        try:
            result = self.generator.generate(input_path, output_path, format="markdown")

            assert result is None  # Returns None when writing to file
            assert output_path.exists()

            content = output_path.read_text()
            assert "# Output Test" in content
        finally:
            input_path.unlink()
            if output_path.exists():
                output_path.unlink()

    def test_step_details_formatting(self):
        """Test step details are formatted correctly."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "Details Test"},
            "cases": [
                {
                    "name": "case1",
                    "steps": [
                        {"action": "input", "id": "field", "value": "test text"},
                        {"action": "scroll", "id": "list", "direction": "down"},
                        {"action": "waitFor", "id": "elem", "timeout": 10000},
                        {"assert": "text", "id": "label", "equals": "Expected"}
                    ]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="markdown")

            assert 'value: "test text"' in content
            assert "direction: down" in content
            assert "timeout: 10000ms" in content
            assert 'equals: "Expected"' in content
        finally:
            temp_path.unlink()


class TestSchemaReference:
    """Tests for schema reference generation."""

    def test_generate_schema_markdown(self):
        """Test schema reference markdown generation."""
        content = generate_schema_reference(format="markdown")

        # Check header
        assert "# JsonUI Test Schema Reference" in content

        # Check actions are documented
        assert "## Actions" in content
        assert "### `tap`" in content
        assert "### `waitFor`" in content
        assert "### `waitForAny`" in content

        # Check assertions are documented
        assert "## Assertions" in content
        assert "### `visible`" in content
        assert "### `text`" in content

        # Check examples are included
        assert "```json" in content
        assert '"action": "tap"' in content

    def test_generate_schema_to_file(self):
        """Test schema reference writes to file."""
        import tempfile

        output_path = Path(tempfile.mktemp(suffix='.md'))

        try:
            result = generate_schema_reference(output_path, format="markdown")

            assert result is None
            assert output_path.exists()

            content = output_path.read_text()
            assert "JsonUI Test Schema Reference" in content
        finally:
            if output_path.exists():
                output_path.unlink()


class TestFlowTestHtmlGeneration:
    """Tests for flow test HTML generation."""

    def setup_method(self):
        self.generator = DocumentGenerator()

    def test_generate_flow_html_basic(self):
        """Test basic flow test HTML generation."""
        test_data = {
            "type": "flow",
            "metadata": {
                "name": "login_flow",
                "description": "Login flow test"
            },
            "platform": "ios",
            "steps": [
                {"action": "waitFor", "id": "login_screen", "timeout": 5000},
                {"action": "tap", "id": "login_button"},
                {"assert": "visible", "id": "home_screen"}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "<!DOCTYPE html>" in content
            assert "Login flow test" in content
            assert "login_flow" in content
            assert "Type:</strong> flow" in content
            assert "Steps:</strong> 3" in content
            # Check flow step rendering
            assert "⚡ Action" in content or "Action" in content
            assert "✓ Assert" in content or "Assert" in content
        finally:
            temp_path.unlink()

    def test_generate_flow_html_with_file_references(self):
        """Test flow test HTML with file references."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "file_ref_flow"},
            "steps": [
                {"file": "screens/login", "case": "valid_login"},
                {"action": "waitFor", "id": "home_screen", "timeout": 5000},
                {"file": "screens/home", "cases": ["verify_display", "navigate"]}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            # Check file reference rendering
            assert "📁 File Reference" in content or "File Reference" in content
            assert "screens/login" in content
            assert "valid_login" in content
            assert "screens/home" in content
        finally:
            temp_path.unlink()

    def test_generate_flow_html_with_setup_teardown(self):
        """Test flow test HTML with setup and teardown."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "setup_teardown_flow"},
            "setup": [
                {"action": "waitFor", "id": "launch_screen", "timeout": 5000}
            ],
            "steps": [
                {"action": "tap", "id": "start_button"}
            ],
            "teardown": [
                {"action": "screenshot", "name": "final_state"}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "Setup" in content
            assert "Teardown" in content
            assert "Setup:</strong> 1 steps" in content
            assert "Teardown:</strong> 1 steps" in content
        finally:
            temp_path.unlink()

    def test_generate_flow_html_with_checkpoints(self):
        """Test flow test HTML with checkpoints."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "checkpoint_flow"},
            "steps": [
                {"action": "tap", "id": "login_button"},
                {"action": "waitFor", "id": "home_screen", "timeout": 5000}
            ],
            "checkpoints": [
                {"name": "After Login", "afterStep": 1, "screenshot": True},
                {"name": "Flow Complete", "afterStep": 2, "screenshot": False}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "Checkpoints" in content
            assert "Checkpoints:</strong> 2" in content
            assert "After Login" in content
            assert "Flow Complete" in content
            # Screenshot icon for checkpoint with screenshot=true
            assert "📷" in content
        finally:
            temp_path.unlink()

    def test_flow_html_sidebar_structure(self):
        """Test flow test HTML sidebar contains steps and checkpoints."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "sidebar_test"},
            "steps": [
                {"file": "screens/login", "case": "valid_login"},
                {"action": "waitFor", "id": "home"},
                {"assert": "visible", "id": "title"}
            ],
            "checkpoints": [
                {"name": "login_done", "afterStep": 1}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            # Check sidebar structure
            assert "class='sidebar'" in content
            assert "sidebar-section" in content
            assert "Steps" in content
            # Sidebar only shows file reference steps (step-1), not inline action/assert
            assert "href='#step-1'" in content
            # Main content shows file ref step with numbered id
            assert "id='step-1'" in content
            # Inline steps use 'step-inline' id (not numbered)
            assert "id='step-inline'" in content
        finally:
            temp_path.unlink()


class TestArgsHtmlGeneration:
    """Tests for args display in HTML generation."""

    def setup_method(self):
        self.generator = DocumentGenerator()

    def test_screen_case_args_in_html(self):
        """Test screen case args are displayed in HTML."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "login_test", "description": "Login screen test"},
            "cases": [
                {
                    "name": "input_case",
                    "description": "Test input with args",
                    "args": {
                        "userName": "testuser",
                        "password": "secret123"
                    },
                    "steps": [
                        {"action": "input", "id": "username_field", "value": "@{userName}"},
                        {"action": "input", "id": "password_field", "value": "@{password}"}
                    ]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            # Check args section is displayed
            assert "Default Args:" in content
            assert "case-args" in content
            assert "@{userName}" in content
            assert "testuser" in content
            assert "@{password}" in content
            assert "secret123" in content
        finally:
            temp_path.unlink()

    def test_screen_case_without_args_no_section(self):
        """Test screen case without args doesn't show args section."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "simple_test"},
            "cases": [
                {
                    "name": "simple_case",
                    "description": "Test without args",
                    "steps": [{"action": "tap", "id": "button"}]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "Default Args:" not in content
            # class='case-args' div should not exist (CSS may define it but no content uses it)
            assert "<div class='case-args'>" not in content
        finally:
            temp_path.unlink()

    def test_flow_file_step_args_in_html(self):
        """Test flow file step args are displayed in HTML."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "login_flow", "description": "Login flow test"},
            "steps": [
                {
                    "file": "login",
                    "case": "input",
                    "args": {
                        "userName": "flowuser",
                        "env": "staging"
                    }
                },
                {"action": "waitFor", "id": "home_screen", "timeout": 5000}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            # Check args section is displayed
            assert "Args (Override):" in content
            assert "step-args" in content
            assert "@{userName}" in content
            assert "flowuser" in content
            assert "@{env}" in content
            assert "staging" in content
        finally:
            temp_path.unlink()

    def test_flow_file_step_without_args_no_section(self):
        """Test flow file step without args doesn't show args section."""
        test_data = {
            "type": "flow",
            "metadata": {"name": "simple_flow"},
            "steps": [
                {"file": "login", "case": "display"},
                {"action": "tap", "id": "button"}
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            assert "Args (Override):" not in content
            # class='step-args' div should not exist (CSS may define it but no content uses it)
            assert "<div class='step-args'>" not in content
        finally:
            temp_path.unlink()

    def test_multiple_cases_with_different_args(self):
        """Test multiple cases with different args are displayed correctly."""
        test_data = {
            "type": "screen",
            "metadata": {"name": "multi_args_test"},
            "cases": [
                {
                    "name": "case_with_args",
                    "description": "Case with args",
                    "args": {"arg1": "value1"},
                    "steps": [{"action": "tap", "id": "btn"}]
                },
                {
                    "name": "case_without_args",
                    "description": "Case without args",
                    "steps": [{"action": "back"}]
                },
                {
                    "name": "case_with_other_args",
                    "description": "Case with other args",
                    "args": {"arg2": "value2", "arg3": 42},
                    "steps": [{"action": "tap", "id": "btn2"}]
                }
            ]
        }

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.test.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            content = self.generator.generate(temp_path, format="html")

            # Check first case args
            assert "@{arg1}" in content
            assert "value1" in content
            # Check third case args
            assert "@{arg2}" in content
            assert "value2" in content
            assert "@{arg3}" in content
            assert "42" in content
            # Count occurrences of case-args class (should be 2)
            assert content.count("class='case-args'") == 2
        finally:
            temp_path.unlink()


class TestHtmlDirectoryGeneration:
    """Tests for HTML directory generation with index."""

    def test_generate_html_directory_basic(self):
        """Test basic HTML directory generation."""
        from jsonui_test_cli.generator import generate_html_directory
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()

            # Create a screen test
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login_test", "description": "Login screen tests"},
                "cases": [{"name": "initial", "steps": [{"action": "back"}]}]
            }
            with open(input_dir / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create output directory
            output_dir = Path(temp_dir) / "html"

            # Generate
            files = generate_html_directory(input_dir, output_dir, "Test Docs")

            # Check results
            assert len(files) == 1
            assert (output_dir / "index.html").exists()
            assert (output_dir / "screens" / "login.test.html").exists()

            # Check index content
            index_content = (output_dir / "index.html").read_text()
            assert "Test Docs" in index_content
            assert "login_test" in index_content
            assert "Screen Tests" in index_content

    def test_generate_html_directory_with_flow_tests(self):
        """Test HTML directory generation with flow tests."""
        from jsonui_test_cli.generator import generate_html_directory
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()

            # Create a screen test
            screen_test = {
                "type": "screen",
                "metadata": {"name": "login_test"},
                "cases": [{"name": "initial", "steps": [{"action": "back"}]}]
            }
            with open(input_dir / "login.test.json", 'w') as f:
                json.dump(screen_test, f)

            # Create a flow test
            flow_test = {
                "type": "flow",
                "metadata": {"name": "login_flow", "description": "Login flow"},
                "steps": [{"action": "tap", "id": "btn"}]
            }
            with open(input_dir / "login_flow.test.json", 'w') as f:
                json.dump(flow_test, f)

            output_dir = Path(temp_dir) / "html"

            files = generate_html_directory(input_dir, output_dir, "Test Docs")

            assert len(files) == 2
            assert (output_dir / "screens" / "login.test.html").exists()
            assert (output_dir / "flows" / "login_flow.test.html").exists()

            # Check index has both categories
            index_content = (output_dir / "index.html").read_text()
            assert "Screen Tests" in index_content
            assert "Flow Tests" in index_content
            assert "login_test" in index_content
            assert "login_flow" in index_content

    def test_generate_html_directory_collapsible_categories(self):
        """Test HTML directory has collapsible categories."""
        from jsonui_test_cli.generator import generate_html_directory
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()

            screen_test = {
                "type": "screen",
                "metadata": {"name": "test"},
                "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
            }
            with open(input_dir / "test.test.json", 'w') as f:
                json.dump(screen_test, f)

            output_dir = Path(temp_dir) / "html"
            generate_html_directory(input_dir, output_dir, "Docs")

            index_content = (output_dir / "index.html").read_text()

            # Check for collapsible structure
            assert "toggleCategory" in index_content
            assert "category-header" in index_content
            assert "category-content" in index_content

    def test_generate_html_directory_sidebar(self):
        """Test HTML directory index has sidebar navigation."""
        from jsonui_test_cli.generator import generate_html_directory
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()

            screen_test = {
                "type": "screen",
                "metadata": {"name": "sidebar_test"},
                "cases": [{"name": "case1", "steps": [{"action": "back"}]}]
            }
            with open(input_dir / "test.test.json", 'w') as f:
                json.dump(screen_test, f)

            output_dir = Path(temp_dir) / "html"
            generate_html_directory(input_dir, output_dir, "Docs")

            index_content = (output_dir / "index.html").read_text()

            # Check for sidebar
            assert "class='sidebar'" in index_content
            assert "sidebar-section" in index_content

    def test_generate_html_directory_summary_stats(self):
        """Test HTML directory index has summary statistics."""
        from jsonui_test_cli.generator import generate_html_directory
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = Path(temp_dir) / "tests"
            input_dir.mkdir()

            # Create 2 screen tests
            for i in range(2):
                screen_test = {
                    "type": "screen",
                    "metadata": {"name": f"test_{i}"},
                    "cases": [
                        {"name": "case1", "steps": [{"action": "tap", "id": "btn"}]},
                        {"name": "case2", "steps": [{"action": "back"}]}
                    ]
                }
                with open(input_dir / f"test_{i}.test.json", 'w') as f:
                    json.dump(screen_test, f)

            output_dir = Path(temp_dir) / "html"
            generate_html_directory(input_dir, output_dir, "Docs")

            index_content = (output_dir / "index.html").read_text()

            # Check for summary stats
            assert "summary-value" in index_content
            assert "Test Files" in index_content
            assert "Test Cases" in index_content
            assert "Total Steps" in index_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
