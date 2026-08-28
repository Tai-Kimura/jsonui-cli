"""A project that targets one platform can silence the other platforms' warnings.

Every platform-constraint warning here is about a driver the project may not
build for at all. A single-platform project could only reach zero warnings by
writing `when: {'platform': 'web'}` on every affected step — a gate that is
always true there, and that reads to the next person as though other platforms
exist.

Two narrowings now decide whether a warning survives, and a platform must pass
both: the step's own gate, and the project's declared `platforms`. Either being
absent means "no limit from that side", so a project that declares nothing
behaves exactly as it did before.

The case worth stating is where they contradict — a step gated onto iOS in a
web-only project. That step runs nowhere, and the temptation is to treat the
declaration as permission to say nothing. Staying quiet there would repeat the
defect these warnings just had: reading a gate as evidence the author knew what
they were doing, and so going silent in the one case worth a word.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.step import (
    PLATFORM_CONSTRAINT,
    StepValidator,
    set_project_platforms,
)

PDF = {"action": "addMedia", "paths": ["files/report.pdf"]}
NESTED = {"action": "addMedia", "paths": ["fixtures/icon.png"]}
HOOK = {"action": "emitHook", "name": "refresh"}
URL = {"assert": "openedUrl", "contains": "/files/"}

TYPE_W = "has an unsupported type"
DIR_W = "contains a directory"
HOOK_W = "emitHook is web-only"
URL_W = "openedUrl is web-only"
DEAD_W = "the step runs nowhere"


def messages(step: dict) -> list[str]:
    validator = StepValidator()
    result = ValidationResult("f.test.json")
    validator.validate_step(dict(step), "s", result, is_flow=False)
    return [m.message for m in result.warnings]


def kinds(step: dict) -> list[str]:
    validator = StepValidator()
    result = ValidationResult("f.test.json")
    validator.validate_step(dict(step), "s", result, is_flow=False)
    return [m.kind for m in result.warnings]


def warned(step, needle):
    return any(needle in m for m in messages(step))


def gated(step, platform):
    return {**step, "when": {"platform": platform}}


class TestUndeclaredIsUnchanged:
    """Absence must mean "warn", never "assume web"."""

    def test_every_warning_still_fires_without_a_declaration(self):
        set_project_platforms(None)
        assert warned(PDF, TYPE_W)
        assert warned(NESTED, DIR_W)
        assert warned(HOOK, HOOK_W)
        assert warned(URL, URL_W)

    def test_an_empty_declaration_is_treated_as_absent(self):
        set_project_platforms([])
        assert warned(PDF, TYPE_W)
        assert warned(HOOK, HOOK_W)


class TestWebOnlyProject:
    """The reported case: no iOS or Android target exists."""

    def setup_method(self):
        set_project_platforms(["web"])

    def test_the_extension_matrix_is_silent(self):
        assert not warned(PDF, TYPE_W)

    def test_the_flat_bundle_rule_is_silent(self):
        assert not warned(NESTED, DIR_W)

    def test_emit_hook_is_silent(self):
        assert not warned(HOOK, HOOK_W)

    def test_opened_url_is_silent(self):
        assert not warned(URL, URL_W)

    def test_no_step_gate_is_needed_to_get_there(self):
        """The point of the feature: silence without `when` on every step."""
        assert messages(PDF) == []
        assert messages(HOOK) == []


class TestCrossPlatformProjectIsUnaffected:
    """Declaring all three must change nothing at all."""

    def setup_method(self):
        set_project_platforms(["ios", "android", "web"])

    def test_warnings_fire_as_before(self):
        assert warned(PDF, TYPE_W)
        assert warned(NESTED, DIR_W)
        assert warned(HOOK, HOOK_W)
        assert warned(URL, URL_W)

    def test_step_gates_still_work(self):
        assert not warned(gated(PDF, "web"), TYPE_W)
        assert not warned(gated(HOOK, "web"), HOOK_W)


class TestPartialDeclaration:
    """A project may target some mobile platforms and not others."""

    def test_an_android_only_project_keeps_the_shared_matrix(self):
        set_project_platforms(["android"])
        assert warned(PDF, TYPE_W)

    def test_an_android_only_project_silences_the_ios_bundle_rule(self):
        """The flat bundle is iOS packaging, so Android alone does not keep it."""
        set_project_platforms(["android"])
        assert not warned(NESTED, DIR_W)

    def test_an_ios_only_project_keeps_both(self):
        set_project_platforms(["ios"])
        assert warned(PDF, TYPE_W)
        assert warned(NESTED, DIR_W)


class TestContradictionIsReported:
    """A step gated onto a platform the project does not build runs nowhere."""

    def setup_method(self):
        set_project_platforms(["web"])

    def test_it_warns(self):
        assert warned(gated(HOOK, "ios"), DEAD_W)

    def test_it_names_the_gate_and_the_targets(self):
        message = next(m for m in messages(gated(HOOK, "ios")) if DEAD_W in m)
        assert "gated onto ios" in message
        assert "builds web" in message

    def test_it_is_reported_once_for_a_step_with_two_platform_checks(self):
        """addMedia carries both platform warnings; the note is not doubled."""
        dead = [m for m in messages(gated(PDF, "ios")) if DEAD_W in m]
        assert len(dead) == 1

    def test_it_is_the_only_thing_said_about_that_step(self):
        """The platform warnings correctly fall silent: nothing is reachable.

        Split out of the tag test below, which asserted this as a side effect
        of comparing the whole list — a red-check took it down for a reason
        that had nothing to do with tagging, which is how the overlap showed.
        """
        said = messages(gated(HOOK, "ios"))
        assert len(said) == 1, said
        assert DEAD_W in said[0]

    def test_an_agreeing_gate_says_nothing(self):
        assert not warned(gated(HOOK, "web"), DEAD_W)

    def test_a_partially_agreeing_gate_says_nothing(self):
        assert not warned(gated(HOOK, ["ios", "web"]), DEAD_W)

    def test_it_is_silent_when_the_project_declares_nothing(self):
        set_project_platforms(None)
        assert not warned(gated(HOOK, "ios"), DEAD_W)


class TestWarningsAreTagged:
    """The CLI must find these without matching on wording."""

    def test_platform_warnings_carry_the_tag(self):
        set_project_platforms(None)
        assert PLATFORM_CONSTRAINT in kinds(PDF)
        assert PLATFORM_CONSTRAINT in kinds(HOOK)
        assert PLATFORM_CONSTRAINT in kinds(URL)

    def test_the_contradiction_note_carries_the_tag(self):
        set_project_platforms(["web"])
        note = [k for k, m in zip(kinds(gated(HOOK, "ios")),
                                  messages(gated(HOOK, "ios"))) if DEAD_W in m]
        assert note == [PLATFORM_CONSTRAINT]

    def test_unrelated_warnings_do_not(self):
        set_project_platforms(None)
        step = {"action": "tap", "id": "b", "bogusKey": 1}
        assert kinds(step) == [""]
