"""A screen test can declare that its screen is not supposed to render.

The web runner waits for the screen's own `data-screen` marker before setup.
That is right whenever the screen renders, and wrong for the tests whose
passing outcome is that it does not: a permission check that shows a refusal
in the screen's place, an expired session that lands on login. Their
`source.layout` correctly names the screen they are about, so the marker id
is derived correctly and the wait still cannot succeed — one project had
seven such files turn into seven timeouts.

`screenReady` is where a file says so. The validator's job here is that a
misspelling is caught at validate time: an unrecognised value would otherwise
fall through to the default gate at runtime, so the file waits for exactly the
marker it declared it would not wait for, and reports a timeout naming the
screen rather than the typo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.schema import (  # noqa: E402
    VALID_SCREEN_READY_VALUES,
    VALID_SCREEN_TOP_LEVEL_KEYS,
)
from jsonui_test_cli.validator import TestValidator  # noqa: E402


def screen_test(**extra) -> dict:
    return {
        "type": "screen",
        "source": {"layout": "layouts/admin_reservations.json"},
        "metadata": {"name": "AdminReservations (no permission)"},
        "cases": [{"name": "shows the refusal", "steps": [
            {"action": "waitFor", "id": "adminReservationsNoPermissionView"},
        ]}],
        **extra,
    }


def errors_for(data: dict) -> list[str]:
    return [m.message for m in TestValidator().validate_data(data).errors]


class TestTheKeyIsAccepted:
    def test_it_is_a_known_top_level_key(self):
        # Guards the cross-repo mirror from the consumer's side: the canonical
        # schema says additionalProperties: false, so a key the validator does
        # not know is an error rather than something ignored.
        assert "screenReady" in VALID_SCREEN_TOP_LEVEL_KEYS

    def test_each_string_form_validates(self):
        for value in VALID_SCREEN_READY_VALUES:
            assert errors_for(screen_test(screenReady=value)) == [], value

    def test_the_marker_form_validates(self):
        assert errors_for(screen_test(screenReady={"marker": "login"})) == []

    def test_a_file_without_it_is_unchanged(self):
        assert errors_for(screen_test()) == []


class TestAMisspellingIsCaughtHereRatherThanAtRuntime:
    def test_an_unknown_string_is_an_error(self):
        errors = errors_for(screen_test(screenReady="nome"))
        assert len(errors) == 1
        # The message carries the alternatives, because the reader reaching it
        # has just learned the feature exists.
        assert "nome" in errors[0]
        assert "none" in errors[0]
        assert "marker" in errors[0]

    def test_the_object_form_requires_a_marker(self):
        assert errors_for(screen_test(screenReady={})) != []
        assert errors_for(screen_test(screenReady={"marker": ""})) != []

    def test_an_unknown_object_key_is_an_error(self):
        errors = errors_for(screen_test(screenReady={"marker": "login",
                                                     "strategy": "none"}))
        assert len(errors) == 1
        assert "strategy" in errors[0]

    def test_a_wrong_type_is_an_error(self):
        for value in (True, 3, ["none"], None):
            assert errors_for(screen_test(screenReady=value)) != [], value


class TestTheDeclarationIsNotAnEscapeFromEverythingElse:
    def test_the_rest_of_the_file_is_still_validated(self):
        # Declaring the readiness gate away must not read as "skip this file".
        # A file that opts out of the gate is exactly the file most likely to
        # be doing something unusual elsewhere.
        errors = errors_for(screen_test(screenReady="none", bogusKey=1))
        assert any("bogusKey" in e for e in errors)
