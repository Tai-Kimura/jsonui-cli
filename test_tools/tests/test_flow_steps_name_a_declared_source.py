"""Regression: test-a-flow-step-can-name-a-screen-its-own-sources-do-not-declare.

A flow step names its screen with `screen`. That string has TWO independent
consumers:

    runtime   screen -> ScreenMarker.tagFor(screen) -> a resource-id in the app
              (the driver never reads `sources`; `alias` appears once in its
              main sources, as the field declaration, and is never consumed)
    static    screen -> sources[].alias -> a layout path, which is how docs
              and audits know which screen a step runs on

🚫 So an undeclared alias does NOT break the test. The name is right, the
marker matches, the run passes. What is missing is a line in `sources[]`.
Stating it the other way sends the reader to rename a screen that is already
correct — which is why the message says "do not rename the screen".

Measured on a consumer face 2026-09-09: 26 of 916 flow steps, in two files,
both of which DO declare aliases (8 and 5) and are each short by one.
"""

from __future__ import annotations

import unittest

from jsonui_test_cli.validation.flow import FlowTestValidator
from jsonui_test_cli.validation.step import StepValidator
from jsonui_test_cli.validation.models import ValidationResult


def _validate(data: dict) -> ValidationResult:
    result = ValidationResult(file_path="f.test.json")
    FlowTestValidator(StepValidator()).validate(data, "$", result)
    return result


def _alias_warnings(result: ValidationResult) -> list[str]:
    return [m.message for m in result.warnings if "declares that alias" in m.message]


BASE = {
    "type": "flow", "version": "1.0",
    "metadata": {"name": "f", "description": "d"},
}


class AStepNamingAnUndeclaredAliasIsReported(unittest.TestCase):

    def test_it_warns_once_per_unresolved_name(self):
        # ⚠️ NEUTRAL FIXTURE NAMES ON PURPOSE. The first draft copied the
        # screen name straight out of the report and the leak guard stopped
        # the commit — a downstream identifier in a public test. What the
        # report contributes is the SHAPE (a file that declares aliases and
        # is short by exactly one, with the same name repeated across steps),
        # and the shape survives the rename intact.
        r = _validate({**BASE,
            "sources": [{"layout": "a.json", "alias": "home"}],
            "steps": [
                {"screen": "home", "action": "tap", "id": "x"},
                {"screen": "item_detail_sheet", "action": "tap", "id": "y"},
                {"screen": "item_detail_sheet", "action": "tap", "id": "z"},
            ]})
        warns = _alias_warnings(r)
        self.assertEqual(1, len(warns), f"expected one warning, got {warns}")
        self.assertIn("item_detail_sheet", warns[0])
        self.assertIn("home", warns[0], "the declared aliases must be named")

    def test_it_does_not_tell_the_reader_to_rename_the_screen(self):
        # 🚫 The most likely wrong fix. The runtime marker matches; the file
        # is short a `sources` entry. A message that reads as "this screen
        # does not exist" sends the reader to the wrong side.
        r = _validate({**BASE,
            "sources": [{"layout": "a.json", "alias": "home"}],
            "steps": [{"screen": "other", "action": "tap", "id": "x"}]})
        msg = _alias_warnings(r)[0]
        self.assertIn("The test still runs", msg)
        self.assertIn("do not rename the screen", msg)

    def test_setup_and_teardown_are_covered(self):
        r = _validate({**BASE,
            "sources": [{"layout": "a.json", "alias": "home"}],
            "setup": [{"screen": "s_only", "action": "tap", "id": "x"}],
            "steps": [{"screen": "home", "action": "tap", "id": "y"}],
            "teardown": [{"screen": "t_only", "action": "tap", "id": "z"}]})
        names = " ".join(_alias_warnings(r))
        self.assertIn("s_only", names)
        self.assertIn("t_only", names)

    def test_a_resolved_flow_is_silent(self):
        r = _validate({**BASE,
            "sources": [{"layout": "a.json", "alias": "home"},
                        {"layout": "b.json", "alias": "detail"}],
            "steps": [{"screen": "home", "action": "tap", "id": "x"},
                      {"screen": "detail", "action": "tap", "id": "y"}]})
        self.assertEqual([], _alias_warnings(r))


class TheFormsThisCheckCannotSpeakAbout(unittest.TestCase):
    """Silence here is "nothing to compare", not "they agree"."""

    def test_a_flow_with_no_sources_is_silent(self):
        # Legal: file-reference flows carry no sources. A check that fired
        # here would report on a shape it knows nothing about.
        r = _validate({**BASE,
            "steps": [{"screen": "home", "action": "tap", "id": "x"}]})
        self.assertEqual([], _alias_warnings(r))

    def test_sources_that_declare_no_alias_at_all_are_silent(self):
        # Not "every step fails" — there is nothing to resolve against, and
        # warning once per step would bury the files that are one line short.
        r = _validate({**BASE,
            "sources": [{"layout": "a.json"}],
            "steps": [{"screen": "home", "action": "tap", "id": "x"}]})
        self.assertEqual([], _alias_warnings(r))

    def test_a_step_with_no_screen_is_silent(self):
        r = _validate({**BASE,
            "sources": [{"layout": "a.json", "alias": "home"}],
            "steps": [{"action": "tap", "id": "x"}]})
        self.assertEqual([], _alias_warnings(r))


if __name__ == "__main__":
    unittest.main()
