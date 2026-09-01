"""Values a scenario may declare that the mock server then cannot honour.

Both were declared in `mock.schema.json` and read by nothing. Of the sixteen
constraints that file states, twelve were unenforced; these are the two whose
violation does something.

`delayMs` BELOW ZERO. The server runs `time.sleep(min(delay, 30000) / 1000.0)`
inside the request handler, before any response is written. Measured against a
live `mock serve`, one request per arm:

    no delayMs      -> HTTP 200
    delayMs 50      -> HTTP 200
    delayMs -5      -> the client HANGS until its own timeout

with `ValueError: sleep length must be non-negative` in the server log. The
caller does not receive an error; it receives nothing, which is the hardest
symptom to trace back to a mock file. Hence an error, not a warning.

`undeclaredStatus` IN ANY OTHER SHAPE. Only `{"reason": "<why>"}` with a
non-empty reason suppresses a borrowed-status finding. A bare `true` was
measured byte-identical in output to writing nothing at all, so an author who
declared it saw their scenario gate anyway and had no way to learn the shape
was wrong. A warning, because it breaks no run — and it reaches the case the
finding-side sentence cannot, a scenario whose status IS declared and which
therefore produces no finding to carry the sentence.

NEITHER GATES ANYTHING THAT EXISTS. Measured over every mock file on this
machine — 1189 files, 4560 scenarios, walked with a tool that does NOT honour
.gitignore, because the shell's `grep` here is shimmed to `ugrep
--ignore-files` and hides 83% of them (196 files visible of 1189). One
scenario sets `delayMs` at all and it is positive; none declares
`undeclaredStatus`. So the counts below are the plant-and-fire arms rather
than a corpus result: a zero corpus is not evidence that a net is alive.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.validator import TestValidator


def _messages(tmp_path, scenario):
    mock = tmp_path / "getX.mock.json"
    mock.write_text(json.dumps({
        "source": {"method": "GET", "path": "/api/x"},
        "scenarios": {"default": {"status": 200, "body": {}, **scenario}},
    }), encoding="utf-8")
    result = TestValidator().validate_file(mock)
    return ([str(e) for e in result.errors], [str(w) for w in result.warnings])


class TestNegativeDelayIsRejected:
    def test_a_negative_delay_is_an_error(self, tmp_path):
        errors, _ = _messages(tmp_path, {"delayMs": -5})

        assert any("must not be negative" in e for e in errors), errors

    def test_the_message_says_what_happens(self, tmp_path):
        """"Invalid" would send the reader to the schema. The reason this is
        worth gating is the symptom — a caller that hangs — and that is what
        someone debugging a hung request needs to recognise."""
        errors, _ = _messages(tmp_path, {"delayMs": -1})

        assert any("hangs" in e for e in errors), errors

    @pytest.mark.parametrize("delay", [0, 1, 50, 30000, 1.5])
    def test_a_usable_delay_is_accepted(self, tmp_path, delay):
        """The non-firing arm. Zero is included deliberately: it is the
        boundary, it is legal, and `if delay:` in the server skips the sleep
        entirely for it."""
        errors, warnings = _messages(tmp_path, {"delayMs": delay})

        assert errors == [] and warnings == []

    def test_a_non_number_is_still_rejected(self, tmp_path):
        """The check that was already there must survive the new one — the
        comparison `delay < 0` cannot run on a string, so the order of the
        two branches is load-bearing."""
        errors, _ = _messages(tmp_path, {"delayMs": "50"})

        assert any("must be a number" in e for e in errors), errors

    def test_a_bool_is_not_a_number(self, tmp_path):
        """`True < 0` is False in Python, so a bool would slip past the range
        check and reach `time.sleep(True/1000)`. It is not a delay anybody
        meant to write."""
        errors, _ = _messages(tmp_path, {"delayMs": True})

        assert any("must be a number" in e for e in errors), errors


class TestOnlyTheHonouredDeclarationIsSilent:
    def test_a_bare_true_is_named(self, tmp_path):
        _, warnings = _messages(tmp_path, {"undeclaredStatus": True})

        assert any("does not suppress" in w for w in warnings), warnings

    def test_an_empty_object_is_named(self, tmp_path):
        _, warnings = _messages(tmp_path, {"undeclaredStatus": {}})

        assert any("does not suppress" in w for w in warnings), warnings

    def test_a_blank_reason_is_named(self, tmp_path):
        """The same rule `contractViolations` carries: a suppression nobody
        can explain is usually one nobody fixed."""
        _, warnings = _messages(tmp_path, {"undeclaredStatus": {"reason": "   "}})

        assert any("does not suppress" in w for w in warnings), warnings

    def test_the_honoured_shape_is_silent(self, tmp_path):
        """The non-firing arm. A warning on the correct spelling would be the
        same defect one step over — telling an author who did it right that
        they did it wrong."""
        errors, warnings = _messages(
            tmp_path, {"undeclaredStatus": {"reason": "the twin owns it"}})

        assert errors == [] and warnings == []

    def test_a_scenario_without_the_key_is_silent(self, tmp_path):
        """The other non-firing arm: the check must key on the declaration
        being PRESENT, not on it being absent-or-wrong. Almost every scenario
        in every project omits it."""
        errors, warnings = _messages(tmp_path, {})

        assert errors == [] and warnings == []

    def test_the_message_names_the_shape_that_works(self, tmp_path):
        """Naming the defect without the spelling is what sent the reader to
        read the generator last time."""
        _, warnings = _messages(tmp_path, {"undeclaredStatus": True})

        assert any('"reason"' in w for w in warnings), warnings
