"""`when.platform: "all"` runs the step everywhere, so it warns as an ungated
step does.

`"all"` is a legal condition platform (CONDITION_PLATFORMS), and the rule
the bundles are shaped by and the drivers filter with — install's
`_platform_matches` — lets it run on every target. The step warnings read
the gate as a set of words instead, in which `"all"` names no platform: the
step was warned as gated onto nothing the project builds ("the step runs
nowhere"), and the warnings on the mobile drivers' limits (addMedia's
two, emitHook's and openedUrl's web-only ones) were silenced as if it were
gated off both mobile drivers.

The ungated step is the reference: for every project declaration and every
platform-bound warning, `"all"` must give exactly its warnings. A web gate
is the control that the comparison can tell a narrowing apart.
"""
from __future__ import annotations

import pytest

from jsonui_test_cli.validation.models import ValidationResult
from jsonui_test_cli.validation.step import StepValidator, set_project_platforms

PDF = {"action": "addMedia", "paths": ["files/report.pdf"]}
NESTED = {"action": "addMedia", "paths": ["fixtures/icon.png"]}
HOOK = {"action": "emitHook", "name": "refresh"}
URL = {"assert": "openedUrl", "contains": "/files/"}

TYPE_W = "has an unsupported type"
DIR_W = "contains a directory"
HOOK_W = "emitHook is web-only"
URL_W = "openedUrl is web-only"
DEAD_W = "the step runs nowhere"

STEPS = {"addMedia-type": (PDF, TYPE_W), "addMedia-dir": (NESTED, DIR_W),
         "emitHook": (HOOK, HOOK_W), "openedUrl": (URL, URL_W)}
PROJECTS = {"undeclared": None, "ios+android": ["ios", "android"], "ios": ["ios"],
            "android": ["android"], "web": ["web"], "all three": ["ios", "android", "web"]}


def messages(step: dict) -> list[str]:
    result = ValidationResult("f.test.json")
    StepValidator().validate_step(dict(step), "s", result, is_flow=False)
    return [m.message for m in result.warnings]


def gated(step: dict, platform) -> dict:
    return {**step, "when": {"platform": platform}}


@pytest.mark.parametrize("project", PROJECTS.values(), ids=PROJECTS.keys())
@pytest.mark.parametrize("step", [s for s, _ in STEPS.values()], ids=STEPS.keys())
def test_all_warns_exactly_as_an_ungated_step(project, step):
    set_project_platforms(project)
    assert messages(gated(step, "all")) == messages(step)


@pytest.mark.parametrize("step,needle", STEPS.values(), ids=STEPS.keys())
def test_control_a_web_gate_is_told_apart_from_no_gate(step, needle):
    set_project_platforms(None)
    assert any(needle in m for m in messages(step))
    assert not any(needle in m for m in messages(gated(step, "web")))


def test_all_is_not_a_step_that_runs_nowhere_and_keeps_the_addmedia_warnings():
    set_project_platforms(["ios", "android"])
    for step, needle in ((PDF, TYPE_W), (NESTED, DIR_W)):
        warned = messages(gated(step, "all"))
        assert any(needle in m for m in warned), warned
        assert not any(DEAD_W in m for m in warned), warned


def test_control_a_web_gate_in_a_project_without_web_runs_nowhere():
    set_project_platforms(["ios", "android"])
    warned = messages(gated(PDF, "web"))
    assert any(DEAD_W in m and "gated onto web" in m for m in warned), warned
    assert not any(TYPE_W in m for m in warned), warned


def test_a_web_only_step_gated_all_is_told_to_gate_it_for_web():
    # The ungated remedy, not "gated onto <nothing>, where it does not run".
    set_project_platforms(None)
    [hook] = [m for m in messages(gated(HOOK, "all")) if HOOK_W in m]
    assert "gate it with 'when': {'platform': 'web'}" in hook
    assert "gated onto" not in hook
