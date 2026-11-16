"""A screen test can declare that each case starts from a freshly opened screen.

All three drivers run a screen test file's setup once, every case in one
shared screen state, and teardown once — a case inherits the previous case's
scroll position and navigation. `caseIsolation: "reopen"` opts a file into
re-opening the screen (and running setup / teardown) around each case;
"shared" is the default and today's behaviour.

The validator's job: accept both values, and catch a misspelling at validate
time — the drivers would otherwise reject it at load (or an older one ignore
it), and a file that meant "reopen" would never run that way.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import (  # noqa: E402
    KEY_DRIVER_REQUIREMENTS,
    VALID_CASE_ISOLATION_VALUES,
    VALID_SCREEN_TOP_LEVEL_KEYS,
)
from jsonui_test_cli.validator import TestValidator  # noqa: E402

FIXTURES = Path(__file__).parent / "schema_fixtures"


def screen_test(**extra) -> dict:
    return {
        "type": "screen",
        "source": {"layout": "layouts/list.json"},
        "metadata": {"name": "List"},
        "cases": [
            {"name": "scrolls", "steps": [{"action": "scrollUntilVisible", "id": "footer"}]},
            {"name": "top is shown", "steps": [{"assert": "visible", "id": "header"}]},
        ],
        **extra,
    }


def errors_for(data: dict) -> list[str]:
    return [m.message for m in TestValidator().validate_data(data).errors]


def test_it_is_a_known_top_level_key():
    assert "caseIsolation" in VALID_SCREEN_TOP_LEVEL_KEYS


def test_both_values_validate():
    for value in ("shared", "reopen"):
        assert errors_for(screen_test(caseIsolation=value)) == [], value


def test_a_file_without_it_is_unchanged():
    assert errors_for(screen_test()) == []


def test_an_unknown_value_is_an_error_naming_the_alternatives():
    errors = errors_for(screen_test(caseIsolation="reOpen"))
    assert len(errors) == 1
    assert "reOpen" in errors[0]
    assert "shared" in errors[0] and "reopen" in errors[0]


def test_a_non_string_is_an_error():
    assert len(errors_for(screen_test(caseIsolation=True))) == 1


def test_the_values_match_the_canonical_schema_enum():
    schema = json.loads((FIXTURES / "screen-test.schema.json").read_text("utf-8"))
    prop = schema["properties"]["caseIsolation"]
    assert prop["enum"] == VALID_CASE_ISOLATION_VALUES
    assert prop["default"] == "shared"


def test_it_names_the_driver_releases_that_read_it():
    # An older driver ignores the key and runs the file as 'shared'; the
    # floor is what lets `validate` say so instead of staying silent.
    assert set(KEY_DRIVER_REQUIREMENTS["caseIsolation"]) == {"android", "ios", "web"}


def test_a_flow_does_not_accept_it():
    flow = {
        "type": "flow",
        "metadata": {"name": "F"},
        "caseIsolation": "reopen",
        "steps": [{"file": "list", "case": "scrolls"}],
    }
    assert any("caseIsolation" in m for m in errors_for(flow))
