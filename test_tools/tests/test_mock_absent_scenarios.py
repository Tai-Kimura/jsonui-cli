"""A scenario that was deleted is in none of the buckets that walk the disk.

Every other finding in `mock generate --check` is produced by opening the
mock files and looking at what is in them, so all of them answer "of what
is on disk, how much was compared". A declared scenario that no longer
exists is not drift, not unmatched, not malformed — it is simply gone, and
the run's own total shrinks to match it.

Measured on a consumer: deleting a swagger-declared scenario from a
generated mock moved the contract line from 407 scenarios / 405 compared
to 406 / 404, with every bucket at zero, and both `validate` and
`mock generate --check` exited 0. The check was not blind — the same run
reported 16 `[NAME]` findings on the hand-written side — it was counting
against a denominator that had moved.

So this one bucket is sourced from the DECLARATION rather than from the
disk. Its reference is what generation PRODUCES, not what the swagger
declares: an operation declaring 200/204/302/409/500/default yields three
scenarios, and reading the denominator off `op.responses` would report
three absences on a healthy route.

Coverage is asked of the route, not of each file, because the overlay
model serves the union — generated/ is the base and a hand-written
scenario overrides it by name. Asking each file separately would report
every status a hand-written mock does not happen to cover, which is the
normal state of every hand-written mock in every project.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import GENERATED_DIR, generate

SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/sessions": {"post": {
            "operationId": "createSession",
            "responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"token": {"type": "string"}},
                    "required": ["token"]}}}},
                "423": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"error": {"type": "string"}},
                    "required": ["error"]}}}},
                "429": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"error": {"type": "string"}},
                    "required": ["error"]}}}},
            },
        }},
    },
}

#: Declared but not produced by generation: no body, or a non-JSON body.
#: Counting these would report absences on a route that is entirely correct.
SPEC_WITH_UNPRODUCED = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/ping": {"get": {
            "operationId": "ping",
            "responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"a": {"type": "string"}}}}}},
                "204": {"description": "no content"},
                "302": {"description": "redirect"},
                "default": {"content": {"application/json": {
                    "schema": {"type": "object"}}}},
            },
        }},
    },
}


@pytest.fixture
def project(tmp_path):
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    mocks.mkdir(parents=True)
    generate([str(spec)], mocks)
    return str(spec), mocks


def _generated(mocks: Path) -> Path:
    files = sorted((mocks / GENERATED_DIR).rglob("*.mock.json"))
    assert len(files) == 1, files
    return files[0]


def _drop(path: Path, scenario: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert scenario in data["scenarios"], sorted(data["scenarios"])
    data["scenarios"].pop(scenario)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --------------------------------------------------------------------- #
# The denominator
# --------------------------------------------------------------------- #

def test_a_healthy_tree_reports_no_absence(project):
    spec, mocks = project
    report = generate([spec], mocks, check=True)
    assert report.absent == []
    assert report.compared == 3
    assert report.scenarios_seen == 3


def test_the_total_does_not_shrink_when_a_scenario_is_deleted(project):
    """The defect in one line: `compared` fell and nothing rose."""
    spec, mocks = project
    before = generate([spec], mocks, check=True)
    _drop(_generated(mocks), "error_423")
    after = generate([spec], mocks, check=True)

    assert after.compared == before.compared - 1
    assert after.scenarios_seen == before.scenarios_seen
    assert len(after.absent) == 1


def test_the_contract_line_names_the_bucket(project):
    spec, mocks = project
    _drop(_generated(mocks), "error_423")
    summary = generate([spec], mocks, check=True).contract_summary
    assert "3 scenario(s)" in summary
    assert "2 compared" in summary
    assert "1 not compared (declared but absent)" in summary


def test_the_finding_names_the_status_and_the_file(project):
    spec, mocks = project
    _drop(_generated(mocks), "error_423")
    [msg] = generate([spec], mocks, check=True).absent
    assert "423" in msg
    assert "createSession" in msg


# --------------------------------------------------------------------- #
# Gating: generated/ is a pure function, hand-written is a choice
# --------------------------------------------------------------------- #

def test_an_absence_in_generated_fails_the_check(project):
    """There is no legitimate state in which a generated scenario is
    missing: the tree is a pure function of the swagger, so it was edited
    or a generation run was interrupted."""
    spec, mocks = project
    _drop(_generated(mocks), "error_423")
    report = generate([spec], mocks, check=True)

    assert report.has_drift
    assert len(report.absent_generated) == 1
    assert report.absent_handwritten == []


def test_an_absence_on_a_hand_written_only_route_is_reported_not_gated(tmp_path):
    """Absence there can be the author's choice — the ORPHAN convention."""
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    (mocks / "sessions").mkdir(parents=True)
    (mocks / "sessions" / "post_api-user-sessions.mock.json").write_text(
        json.dumps({
            "source": {"method": "POST", "path": "/api/user/sessions"},
            "activeScenario": "ok",
            "scenarios": {"ok": {"status": 200, "body": {"token": "t"}}},
        }), encoding="utf-8")

    report = generate([str(spec)], mocks, check=True)

    assert len(report.absent_handwritten) == 2  # 423 and 429
    assert report.absent_generated == []
    assert not report.has_drift


# --------------------------------------------------------------------- #
# The overlay union
# --------------------------------------------------------------------- #

def test_a_hand_written_scenario_covers_the_declared_status(tmp_path):
    """On the hand-written side, statuses are the identity rather than
    names — the same rule the body check uses. `locked` covers the declared
    423 that generation happens to call `error_423`, and a project that
    names its scenarios after its own domain owes nobody the generator's
    spelling.

    Hand-written only, deliberately. This used to reach the same state by
    deleting `error_423` out of `generated/` and letting a hand-written 423
    stand in for it — a state the overlay model cannot produce, because
    `generated/` is rewritten wholesale on every run. It is now the state
    the generated-side gate exists to catch, so the claim about names is
    made where it actually applies.
    """
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    (mocks / "sessions").mkdir(parents=True)
    (mocks / "sessions" / "post_api-user-sessions.mock.json").write_text(
        json.dumps({
            "source": {"method": "POST", "path": "/api/user/sessions"},
            "activeScenario": "ok",
            "scenarios": {
                "ok": {"status": 200, "body": {"token": "t"}},
                "locked": {"status": 423, "body": {"error": "locked"}},
                "slow_down": {"status": 429, "body": {"error": "rate"}},
            },
        }), encoding="utf-8")

    report = generate([str(spec)], mocks, check=True)

    assert report.absent == []
    assert not report.has_drift


# --------------------------------------------------------------------- #
# The reference set: the generator's scenarios, not its statuses
#
# The first version of this bucket read the denominator off the STATUSES
# generation produces, on both sides. That closes only the case where a
# status loses its LAST scenario. An operation declaring 200 twice —
# `default` and `empty` — kept answering "in sync" with `empty` deleted,
# because 200 was still served, and the run's own total shrank from 7 to 6
# to match: the generator's own output deleted, both gates green.
#
# The three arms below are the reporter's, one variable apart. The control
# is load-bearing: "the `empty` arm is red" and "every arm is red" are the
# same observation without it.
# --------------------------------------------------------------------- #

#: 200 twice: `default` and `empty` are both produced for the same status.
SPEC_WITH_TWO_200_SCENARIOS = {
    "openapi": "3.0.3",
    "paths": {
        "/api/items": {"get": {
            "operationId": "listItems",
            "responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "array", "items": {
                        "type": "object", "required": ["id"],
                        "properties": {"id": {"type": "string"}}}}}}},
                "403": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["error"],
                    "properties": {"error": {"type": "string"}}}}}},
            },
        }},
    },
}


@pytest.fixture
def two_hundreds(tmp_path):
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC_WITH_TWO_200_SCENARIOS), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    mocks.mkdir(parents=True)
    generate([str(spec)], mocks)
    assert set(json.loads(_generated(mocks).read_text("utf-8"))["scenarios"]) == {
        "default", "empty", "error_403"}
    return str(spec), mocks


def test_the_control_arm_is_green(two_hundreds):
    spec, mocks = two_hundreds
    report = generate([spec], mocks, check=True)
    assert report.absent == []
    assert not report.has_drift
    assert report.scenarios_seen == 3


def test_deleting_one_of_two_scenarios_for_a_status_is_caught(two_hundreds):
    """The reported hole. 200 is still served by `default`, so a
    status-keyed denominator sees nothing missing."""
    spec, mocks = two_hundreds
    _drop(_generated(mocks), "empty")

    report = generate([spec], mocks, check=True)

    assert report.has_drift
    assert len(report.absent_generated) == 1
    assert "empty" in report.absent_generated[0]


def test_the_total_holds_when_one_of_two_is_deleted(two_hundreds):
    """The denominator is the point: `compared` falls by one and the bucket
    rises by one, so the line does not read as a smaller, healthy run."""
    spec, mocks = two_hundreds
    before = generate([spec], mocks, check=True)
    _drop(_generated(mocks), "empty")
    after = generate([spec], mocks, check=True)

    assert after.compared == before.compared - 1
    assert after.scenarios_seen == before.scenarios_seen


def test_the_last_scenario_for_a_status_is_still_caught(two_hundreds):
    """The case the first version did close, kept."""
    spec, mocks = two_hundreds
    _drop(_generated(mocks), "error_403")

    report = generate([spec], mocks, check=True)

    assert report.has_drift
    assert len(report.absent_generated) == 1
    assert "error_403" in report.absent_generated[0]


def test_a_hand_written_mock_does_not_have_to_repeat_the_generators_names(
        two_hundreds):
    """Only `generated/` is held to the generator's scenario NAMES, and it
    is held to them on its own contents — so an overlay beside it, carrying
    one scenario under a name of its own, neither satisfies nor violates
    anything. (The hand-written side's own rule — statuses, not names — is
    measured on a hand-written-only route above, where it applies.)"""
    spec, mocks = two_hundreds
    (mocks / "items").mkdir(parents=True, exist_ok=True)
    (mocks / "items" / "listItems.mock.json").write_text(json.dumps({
        "source": {"method": "GET", "path": "/api/items"},
        "scenarios": {"two_rows": {"status": 200, "body": [{"id": "1"}]}},
    }), encoding="utf-8")

    report = generate([spec], mocks, check=True)

    assert report.absent == []
    assert not report.has_drift


# --------------------------------------------------------------------- #
# The other direction: a status the swagger no longer declares
#
# `absent` gated because generated/ is a pure function of the swagger and
# cannot legitimately be missing a scenario. Holding an EXTRA one is the
# same claim read the other way, and it went to a non-gating bucket. A
# consumer measured the cost: a mock answering 409 for a path the
# implementation had no branch for, with the end-to-end suite green
# against a case production cannot produce.
#
# The four predicates below are the reporter's, verbatim in intent. The
# second is the load-bearing one: without it, "only the generated side
# gates" is indistinguishable from "everything gates".
# --------------------------------------------------------------------- #

SPEC_WITHOUT_422 = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/sessions": {"post": {
            "operationId": "createSession",
            "responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"token": {"type": "string"}},
                    "required": ["token"]}}}},
                "429": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"error": {"type": "string"}},
                    "required": ["error"]}}}},
            },
        }},
    },
}


def _narrow_the_swagger(tmp_path: Path) -> str:
    """Rewrite the swagger without 423 — the backend deleting an
    over-declared response, which is what prompted this."""
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC_WITHOUT_422), encoding="utf-8")
    return str(spec)


def _hand_written(mocks: Path, scenarios: dict) -> None:
    path = mocks / "sessions" / "post_api-user-sessions.mock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source": {"method": "POST", "path": "/api/user/sessions"},
        "activeScenario": sorted(scenarios)[0],
        "scenarios": scenarios,
    }), encoding="utf-8")


def test_generated_holding_an_undeclared_status_fails_the_check(project,
                                                                tmp_path):
    """Predicate 1: narrow the swagger, and the generated leftover gates."""
    _, mocks = project
    spec = _narrow_the_swagger(tmp_path)

    report = generate([spec], mocks, check=True)

    assert report.has_drift
    assert len(report.unmatched_generated) == 1
    assert "423" in report.unmatched_generated[0]


def test_a_hand_written_extra_scenario_is_a_warning_not_a_failure(tmp_path):
    """Predicate 2, the load-bearing one. An extra scenario a person wrote
    can be deliberate. If this went red too, "only generated gates" would
    be indistinguishable from "everything gates" — the shape where a check
    looks effective because it fails on everything."""
    spec = _narrow_the_swagger(tmp_path)
    mocks = tmp_path / "tests" / "mocks"
    mocks.mkdir(parents=True)
    generate([spec], mocks)                      # generated/ has no 423
    _hand_written(mocks, {"ok": {"status": 200, "body": {"token": "t"}},
                          "legacy": {"status": 423, "body": {"e": "x"}}})

    report = generate([spec], mocks, check=True)

    assert report.unmatched_generated == []
    assert any("423" in u for u in report.unmatched)   # still reported
    assert not report.has_drift                        # but does not gate


def test_the_absence_direction_still_gates(project):
    """Predicate 3: the direction shipped earlier is unchanged."""
    spec, mocks = project
    _drop(_generated(mocks), "error_423")

    report = generate([spec], mocks, check=True)

    assert report.has_drift and len(report.absent_generated) == 1


def test_the_denominator_closes_in_both_directions(project, tmp_path):
    """Predicate 4."""
    spec, mocks = project
    before = generate([spec], mocks, check=True)
    assert before.scenarios_seen == 3

    narrowed = _narrow_the_swagger(tmp_path)
    after = generate([narrowed], mocks, check=True)
    # The leftover is still one of the scenarios the run opened; it moved
    # buckets rather than vanishing from the total.
    assert after.scenarios_seen == 3
    assert after.compared == 2 and len(after.unmatched) == 1


def test_the_rebuild_trigger_removes_the_leftover_first(project, tmp_path,
                                                        monkeypatch):
    """Measured, and worth pinning: on the `validate` path the rebuild runs
    BEFORE the check, so a narrowed swagger regenerates the tree and the
    leftover is gone by the time anything looks. The gate above therefore
    fires on the direct `mock generate --check` path — which is where the
    report observed it — rather than on every run."""
    import time
    from jsonui_test_cli.cli import _regenerate_stale_mocks

    spec, mocks = project
    root = Path(spec).parent
    (root / "jui.config.json").write_text(json.dumps(
        {"mock": {"swagger": ["swagger.json"], "mockDir": "tests/mocks"}}),
        encoding="utf-8")
    time.sleep(0.01)
    _narrow_the_swagger(root)
    monkeypatch.chdir(root)

    _regenerate_stale_mocks(None)

    assert "error_423" not in json.loads(
        _generated(mocks).read_text())["scenarios"]
    assert not generate([spec], mocks, check=True).has_drift


def test_declared_responses_generation_does_not_produce_are_not_absences(tmp_path):
    """204, 302 and `default` are declared and yield no scenario. Reading
    the denominator off `op.responses` reports three absences here — a
    check that invents findings on healthy input is switched off before it
    ever finds a real one."""
    spec = tmp_path / "swagger.json"
    spec.write_text(json.dumps(SPEC_WITH_UNPRODUCED), encoding="utf-8")
    mocks = tmp_path / "tests" / "mocks"
    mocks.mkdir(parents=True)
    generate([str(spec)], mocks)

    report = generate([str(spec)], mocks, check=True)

    assert report.absent == []
    assert not report.has_drift


def test_the_finding_does_not_claim_an_unserved_status(two_hundreds):
    """The line has to stay true after identity moved from status to scenario.

    The wording was inherited from the status-keyed check, where "status 200
    is declared but this file does not serve it" was true whenever the bucket
    fired. Scenario identity breaks that: drop `empty` while `default`
    remains and both answer 200, and the sentence is refuted by the same file
    it names, two lines up. A gate a reader can disprove by opening the file
    is one they stop reading — the failure mode a consumer named for the
    remedy line in the same release.
    """
    spec, mocks = two_hundreds
    _drop(_generated(mocks), "empty")

    [msg] = generate([spec], mocks, check=True).absent_generated

    served = {s["status"] for s
              in json.loads(_generated(mocks).read_text("utf-8"))
              ["scenarios"].values()}
    assert 200 in served, "precondition: `default` still answers 200"
    assert "empty" in msg
    assert "does not serve" not in msg


def test_the_finding_still_reads_correctly_for_a_wholly_absent_status(
        two_hundreds):
    """The other arm: nothing in the file answers 403 once `error_403` goes.

    Both arms must name the scenario. One wording for both is the point —
    branching on "is this status still served" would put the two sentences
    back on a condition, which is how they drifted apart the first time.
    """
    spec, mocks = two_hundreds
    _drop(_generated(mocks), "error_403")

    [msg] = generate([spec], mocks, check=True).absent_generated

    assert "error_403" in msg
    assert "403" in msg
    assert "does not serve" not in msg
