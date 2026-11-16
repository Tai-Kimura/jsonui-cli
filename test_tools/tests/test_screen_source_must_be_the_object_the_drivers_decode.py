"""Regression: jui-test-validate-accepts-string-source-that-both-drivers-reject.

A screen test whose `source` was a string — `"source": "docs/…/x.json"` —
validated PASSED, was installed into both drivers' bundles, and failed at
load on both (Android: kotlinx `Expected start of the object '{' … at path:
$.source`, TestModels.kt:31 TestSource; iOS: TestLoader.swift:99
invalidJSON). The screen validator read `source` behind
`if source and isinstance(source, dict):`, so anything that was not a
non-empty object skipped every check — the key check, the path check, and
any check that `layout` is there.

The contract these arms pin is the drivers': `source` is an object and
`layout` is a required string (TestSource on both platforms; `spec` is the
only optional key they read). Measured 2026-09-17 on the bar face with
jsonui-test 1.8.103: one full two-OS run lost to it.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validator import TestValidator  # noqa: E402


def _screen(source) -> dict:
    return {
        "type": "screen",
        "source": source,
        "metadata": {"name": "t", "description": "d"},
        "cases": [{"name": "c", "steps": [{"action": "tap", "id": "btn"}]}],
    }


def _source_errors(result) -> list:
    return [e for e in result.errors if "source" in str(e)]


class TestSourceShape:
    def setup_method(self):
        self.validator = TestValidator()

    # --- the ticket ---------------------------------------------------------

    def test_a_string_source_is_an_error_not_a_pass(self):
        """The reported file: `"source": "docs/screens/layouts/app_info.json"`."""
        result = self.validator.validate_data(_screen("docs/screens/layouts/app_info.json"))
        assert not result.is_valid
        errs = _source_errors(result)
        assert errs, [str(e) for e in result.errors]
        # The message names the shape the drivers decode, not just "invalid".
        assert any("object" in str(e) and "layout" in str(e) for e in errs), [str(e) for e in errs]

    @pytest.mark.parametrize("source", [
        pytest.param(["docs/x.json"], id="array"),
        pytest.param(3, id="number"),
        pytest.param(True, id="boolean"),
        pytest.param(None, id="null"),
    ])
    def test_any_non_object_source_is_an_error(self, source):
        result = self.validator.validate_data(_screen(source))
        assert not result.is_valid
        assert _source_errors(result), [str(e) for e in result.errors]

    # --- the boundary: an object, but not one the drivers can use ------------

    def test_an_empty_object_is_an_error_because_layout_is_required(self):
        """`{}` is a dict, so it passed the old guard — and TestSource.layout
        is non-optional on both drivers."""
        result = self.validator.validate_data(_screen({}))
        assert not result.is_valid
        assert any("layout" in str(e) for e in _source_errors(result)), [str(e) for e in result.errors]

    @pytest.mark.parametrize("layout", [
        pytest.param("", id="empty-string"),
        pytest.param("   ", id="blank"),
        pytest.param(7, id="number"),
        pytest.param(None, id="null"),
    ])
    def test_a_layout_that_is_not_a_non_empty_string_is_an_error(self, layout):
        result = self.validator.validate_data(_screen({"layout": layout}))
        assert not result.is_valid
        assert any("layout" in str(e) for e in _source_errors(result)), [str(e) for e in result.errors]

    # --- the controls ------------------------------------------------------------

    def test_the_object_form_is_unchanged_and_valid(self):
        """The good file beside the bad one on the reporting face."""
        result = self.validator.validate_data(_screen({"layout": "docs/screens/layouts/app_info.json"}))
        assert result.is_valid, [str(e) for e in result.errors]
        assert result.error_count == 0

    def test_an_absent_source_was_already_an_error_and_still_is(self):
        """The required-key check owns this case (schema `required`); this arm
        keeps the two checks from disagreeing about whose error it is."""
        data = _screen({"layout": "x.json"})
        del data["source"]
        result = self.validator.validate_data(data)
        assert not result.is_valid
        assert any("Missing required top-level key 'source'" in str(e) for e in result.errors)

    # --- flow: the sibling check already had this shape; pinned so it stays ---

    def test_flow_sources_null_is_an_error_like_a_string_is(self):
        flow = {
            "type": "flow",
            "metadata": {"name": "f"},
            "sources": None,
            "steps": [{"screen": "a", "action": "tap", "id": "x"}],
        }
        result = self.validator.validate_data(flow)
        assert not result.is_valid
        assert any("sources" in str(e) and "array" in str(e) for e in result.errors), [str(e) for e in result.errors]


class TestTheCommandStopsBeforeInstall:
    """The CLI, as the reporting face ran it: a directory holding the good
    and the bad file, `validate … --no-install`. PASSED / exit 0 is what
    shipped the bad file to two drivers."""

    def test_a_directory_with_a_string_source_file_fails(self, capsys):
        from jsonui_test_cli.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "good.test.json").write_text(json.dumps(_screen({"layout": "x.json"})))
            (d / "bad.test.json").write_text(json.dumps(_screen("x.json")))
            with patch("sys.argv", ["jsonui-test", "validate", str(d), "--no-install"]):
                rc = main()
            out = capsys.readouterr().out
            assert rc != 0, out
            assert "Result: FAILED" in out, out
            assert "bad.test.json" in out, out
