"""`apiEndpoints[].request` / `.response` are objects, and saying so is the validator's job.

A consumer wrote a bare schema name (`"response": "MessageResponse"`). It reads
like a reference and is not one — nothing resolves it. The three checks
disagreed: `doc_validate_spec` passed with 0 errors, HTML rendered the name as
a quoted string, and markdown raised

    AttributeError: 'str' object has no attribute 'items'

naming neither the field nor the spec. The reporting lane rebuilt the traceback
by hand to find which of the file's many strings it was.

"A shape the validator accepts, the generators can render" is the property that
broke. It is restored from the validator's side, because that is where the
mistake was made and where a path can be named. The markdown generator also
stops raising — generation is reachable without validating, and a bare
AttributeError is the least useful form a diagnosis can take — but it does not
try to diagnose: it renders what HTML already renders, so the two agree.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_doc_cli.spec_doc.markdown_generator import (  # noqa: E402
    _format_json_schema,
    generate_spec_markdown,
)
from jsonui_doc_cli.spec_doc.validator import SpecValidator  # noqa: E402


def spec_with(endpoint: dict) -> dict:
    return {
        "metadata": {"name": "chat", "displayName": "Chat"},
        "dataFlow": {"apiEndpoints": [endpoint]},
    }


def endpoint_errors(endpoint: dict) -> list:
    result = SpecValidator().validate_data(spec_with(endpoint))
    return [e for e in result.errors if "apiEndpoints" in e.path]


class TestTheValidatorNamesTheField:
    @pytest.mark.parametrize("field", ["request", "response"])
    def test_a_bare_schema_name_is_an_error_that_names_the_path(self, field):
        errors = endpoint_errors(
            {"path": "/api/messages", "method": "POST", field: "MessageResponse"})
        assert len(errors) == 1, errors
        # The path is the whole point: the spec had many strings and the old
        # failure distinguished none of them.
        assert errors[0].path == f"dataFlow.apiEndpoints[0].{field}"
        assert "MessageResponse" in errors[0].message
        # And it says what to write instead.
        assert "object of field" in errors[0].message

    @pytest.mark.parametrize("value", [["a"], 3, True])
    def test_other_non_objects_are_caught_too(self, value):
        assert endpoint_errors(
            {"path": "/p", "method": "GET", "response": value}) != []

    def test_an_object_passes(self):
        assert endpoint_errors({
            "path": "/api/messages", "method": "POST",
            "request": {"body": "string"},
            "response": {"message": "string"},
        }) == []

    def test_absent_fields_pass(self):
        # Neither is required. Reding their absence would be a different
        # feature, and a wrong one.
        assert endpoint_errors({"path": "/p", "method": "GET"}) == []


class TestTheGeneratorsAgree:
    @pytest.mark.parametrize("value", ["MessageResponse", ["a"], 3])
    def test_markdown_renders_instead_of_raising(self, value):
        # Reachable without validating, so it must not crash. It renders the
        # value rather than diagnosing: two places explaining the same
        # mistake drift, and the validator is the one that can name the path.
        assert _format_json_schema(value)

    def test_the_whole_document_generates(self):
        out = generate_spec_markdown(spec_with(
            {"path": "/api/messages", "method": "POST",
             "response": "MessageResponse"}))
        assert "MessageResponse" in out

    def test_html_and_markdown_render_the_same_input(self):
        """The asymmetry that made this expensive: one accepted, one crashed."""
        from jsonui_doc_cli.spec_doc.html_generator import _format_json_html

        for value in ("MessageResponse", ["a"], 3):
            assert _format_json_html(value)
            assert _format_json_schema(value)

    def test_objects_are_unaffected(self):
        rendered = _format_json_schema({"message": "string", "code": "int"})
        assert '"message": "string"' in rendered
        assert rendered.startswith("{")
