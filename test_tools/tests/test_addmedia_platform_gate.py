"""`when.platform` and the two addMedia warnings, which are about different platforms.

Both warnings concern a mobile driver's limits, so both should be silent on a
step that never reaches that driver. They were not: the extension-matrix
warning consulted no gate at all, so a web-only project had no way to reach
zero warnings and could not run "did the count go up" as a check. The
directory warning next to it already consulted one.

The fix is not "make them agree" — they are about different platforms, and
collapsing them would trade one wrong answer for another:

    extension matrix   iOS and Android share it -> only a step gated off BOTH
                       is exempt; an Android-gated step still hits it
    flat bundle path   an iOS packaging property -> an Android-gated step is
                       exempt

So the interesting assertions here are the ones where the two disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.step import StepValidator

TYPE_WARNING = "has an unsupported type"
DIRECTORY_WARNING = "contains a directory"


def warnings_for(step: dict) -> list[str]:
    validator = StepValidator()
    result = ValidationResult("f.test.json")
    validator.validate_step(dict(step), "s", result, is_flow=False)
    return [m.message for m in result.warnings]


def gated(step: dict, platform) -> dict:
    return {**step, "when": {"platform": platform}}


UNSUPPORTED = {"action": "addMedia", "paths": ["files/report.pdf"]}
NESTED_PNG = {"action": "addMedia", "paths": ["fixtures/icon.png"]}


def has(step, needle):
    return any(needle in m for m in warnings_for(step))


class TestExtensionMatrixGate:
    """The matrix belongs to both mobile drivers, so both must be excluded."""

    def test_an_ungated_step_warns(self):
        assert has(UNSUPPORTED, TYPE_WARNING)

    def test_a_web_only_step_is_silent(self):
        """The reported case: a web project uploading a PDF."""
        assert not has(gated(UNSUPPORTED, "web"), TYPE_WARNING)

    def test_an_android_gated_step_still_warns(self):
        """Android shares the matrix, so gating onto it changes nothing.

        The distinction the fix turns on. Reusing the neighbouring iOS-only
        gate would wrongly silence this.
        """
        assert has(gated(UNSUPPORTED, "android"), TYPE_WARNING)

    def test_an_ios_gated_step_still_warns(self):
        assert has(gated(UNSUPPORTED, "ios"), TYPE_WARNING)

    def test_a_step_reaching_ios_among_others_still_warns(self):
        assert has(gated(UNSUPPORTED, ["ios", "web"]), TYPE_WARNING)

    def test_a_step_gated_off_both_mobile_drivers_is_silent(self):
        assert not has(gated(UNSUPPORTED, ["web"]), TYPE_WARNING)

    def test_a_supported_extension_never_warns(self):
        assert not has({"action": "addMedia", "paths": ["a.png"]}, TYPE_WARNING)


class TestFlatBundleGate:
    """The directory rule is iOS packaging, so Android does not keep it alive."""

    def test_an_ungated_step_warns(self):
        assert has(NESTED_PNG, DIRECTORY_WARNING)

    def test_a_web_only_step_is_silent(self):
        assert not has(gated(NESTED_PNG, "web"), DIRECTORY_WARNING)

    def test_an_android_gated_step_is_silent(self):
        """Where the two warnings deliberately disagree.

        Same gate, same step shape: the extension matrix would still fire
        here (Android shares it) and this one must not (iOS alone has the
        flat bundle).
        """
        assert not has(gated(NESTED_PNG, "android"), DIRECTORY_WARNING)

    def test_an_ios_gated_step_warns(self):
        assert has(gated(NESTED_PNG, "ios"), DIRECTORY_WARNING)

    def test_an_absolute_path_never_warns(self):
        assert not has({"action": "addMedia", "paths": ["/tmp/a.png"]},
                       DIRECTORY_WARNING)


class TestTheTwoGatesAreNotTheSameGate:
    """One step, one gate, two answers — the property a shared flag would lose."""

    def test_android_splits_them(self):
        step = gated({"action": "addMedia", "paths": ["files/report.pdf"]},
                     "android")
        messages = warnings_for(step)
        assert any(TYPE_WARNING in m for m in messages), messages
        assert not any(DIRECTORY_WARNING in m for m in messages), messages

    def test_web_silences_both(self):
        step = gated({"action": "addMedia", "paths": ["files/report.pdf"]}, "web")
        assert warnings_for(step) == []


class TestGateShapes:
    def test_a_when_without_a_platform_key_does_not_gate(self):
        """`when` carries other conditions; only `platform` bears on this."""
        step = {**UNSUPPORTED, "when": {"state": {"loggedIn": True}}}
        assert has(step, TYPE_WARNING)

    def test_an_absent_when_does_not_gate(self):
        assert has(UNSUPPORTED, TYPE_WARNING)
