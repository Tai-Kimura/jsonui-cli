"""`emitHook` / `openedUrl` warn whenever they can still reach a mobile driver.

Both are web-only: `emitHook` no-ops with a warning on iOS/Android, and the
mobile drivers reject `openedUrl` outright. Both used to key their warning on
`"when" not in step` — the mere presence of a gate, whatever it said.

That reads a gate as evidence the author understood the limit, which inverts
on the one gate where it matters. `{'platform': 'ios'}` says "run this on
iOS", which is precisely where the step does not run, and it was exactly then
that the warning went quiet. The warning was suppressed in the only case that
warranted it, and emitted in cases (`platform: web`) that did not.

So the condition is the same one the addMedia extension matrix uses: warn
unless the step is gated off BOTH mobile drivers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.step import StepValidator

EMIT_HOOK = {"action": "emitHook", "name": "refresh"}
OPENED_URL = {"assert": "openedUrl", "contains": "/files/"}

EMIT_NEEDLE = "emitHook is web-only"
URL_NEEDLE = "openedUrl is web-only"


def messages_for(step: dict) -> list[str]:
    validator = StepValidator()
    result = ValidationResult("f.test.json")
    validator.validate_step(dict(step), "s", result, is_flow=False)
    return [m.message for m in result.warnings]


def gated(step: dict, platform) -> dict:
    return {**step, "when": {"platform": platform}}


def warned(step, needle):
    return any(needle in m for m in messages_for(step))


class TestEmitHookGate:
    def test_an_ungated_step_warns(self):
        assert warned(EMIT_HOOK, EMIT_NEEDLE)

    def test_a_web_gated_step_is_silent(self):
        assert not warned(gated(EMIT_HOOK, "web"), EMIT_NEEDLE)

    def test_an_ios_gated_step_warns(self):
        """The inverted case: gating onto iOS used to silence it."""
        assert warned(gated(EMIT_HOOK, "ios"), EMIT_NEEDLE)

    def test_an_android_gated_step_warns(self):
        assert warned(gated(EMIT_HOOK, "android"), EMIT_NEEDLE)

    def test_a_step_reaching_ios_among_others_warns(self):
        assert warned(gated(EMIT_HOOK, ["ios", "web"]), EMIT_NEEDLE)

    def test_a_when_without_a_platform_key_still_warns(self):
        """A gate that says nothing about platform does not exempt anything.

        The old rule exempted it, because it only asked whether `when` existed.
        """
        step = {**EMIT_HOOK, "when": {"state": {"loggedIn": True}}}
        assert warned(step, EMIT_NEEDLE)


class TestOpenedUrlGate:
    def test_an_ungated_step_warns(self):
        assert warned(OPENED_URL, URL_NEEDLE)

    def test_a_web_gated_step_is_silent(self):
        assert not warned(gated(OPENED_URL, "web"), URL_NEEDLE)

    def test_an_ios_gated_step_warns(self):
        assert warned(gated(OPENED_URL, "ios"), URL_NEEDLE)

    def test_an_android_gated_step_warns(self):
        assert warned(gated(OPENED_URL, "android"), URL_NEEDLE)

    def test_a_step_reaching_android_among_others_warns(self):
        assert warned(gated(OPENED_URL, ["android", "web"]), URL_NEEDLE)


class TestTheRemedyMatchesTheSituation:
    """"Gate it for web" is the wrong advice for a step deliberately on iOS."""

    def test_an_ungated_step_is_told_to_gate_it(self):
        message = next(m for m in messages_for(EMIT_HOOK) if EMIT_NEEDLE in m)
        assert "gate it with" in message
        assert "gated onto" not in message

    def test_a_mobile_gated_step_is_told_where_it_will_not_run(self):
        message = next(m for m in messages_for(gated(EMIT_HOOK, "ios"))
                       if EMIT_NEEDLE in m)
        assert "gated onto ios, where it does not run" in message
        assert "gate it with" not in message

    def test_the_note_names_every_mobile_platform_it_reaches(self):
        message = next(m for m in messages_for(gated(EMIT_HOOK, ["ios", "android"]))
                       if EMIT_NEEDLE in m)
        assert "gated onto ios/android" in message

    def test_the_note_names_only_the_mobile_platforms(self):
        """`web` is in the gate but is not where the step fails to run."""
        message = next(m for m in messages_for(gated(OPENED_URL, ["ios", "web"]))
                       if URL_NEEDLE in m)
        assert "gated onto ios, where it does not run" in message
        assert "web" not in message.split(";")[-1]
