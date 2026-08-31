"""A hand-written scenario answering a status its operation does not declare.

There are three of these, and the obvious split gates the wrong two.

==== ====================================== ======= =======================
form what the rest of the contract says     weight  what the reader does
==== ====================================== ======= =======================
A    a realm twin declares it               gate    fix this op's swagger
B    no operation IN SCOPE declares it      warn    nothing (a premise)
C    others declare it, the twin does not   gate    check the impl branch
==== ====================================== ======= =======================

Gating "the contract has this code nowhere" is the natural-looking rule and
it inverts the result. Measured across two lanes: their only B findings were
`500`, deliberate and benign — one of them a fail-open regression scenario —
while the one incident anyone actually had was a mock answering `409` on a
path whose NEIGHBOUR declares 409. That incident is form C. The natural rule
fails the benign two and passes the real one.

A and C share a cause: a code that exists somewhere in the contract was
attached to an operation that does not declare it. That is invisible by
reading, because the code is real — it is just real somewhere else.

**Why A is a fixture and C is not.** A needs a realm twin, and the twin rule
is "same method, same segment count, exactly one segment differs, same
tail". A project whose realms are PREFIXES (`/api/bar/x` beside `/api/x`)
can never produce one — measured: 16 findings across two such projects, all
of them C, no A anywhere. A also gets rarer as a contract gets healthier,
since the asymmetry it detects is a bug a backend eventually fixes. Both
mean a real corpus is the wrong home for the A regression: the material is
neither representative nor permanent. C has 16 live examples and does not
need one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli.mock.generate import GATING_STATUS_FORMS, generate
from jsonui_test_cli.mock.scope import PathScope

JSON = {"content": {"application/json": {"schema": {
    "type": "object", "properties": {"id": {"type": "string"}}}}}}


def _op(operation_id, *statuses):
    return {"operationId": operation_id,
            "responses": {str(s): JSON for s in statuses}}


#: Realms that differ by one SEGMENT, which is what makes a twin.
TWIN_REALMS = {"openapi": "3.0.3", "paths": {
    "/api/admin/stalls/suspend": {"post": _op("adminSuspend", 200, 404)},
    "/api/partner/stalls/suspend": {"post": _op("partnerSuspend", 200)},
    "/api/admin/reports": {"get": _op("listReports", 200, 409)},
}}


def _project(tmp_path, spec=TWIN_REALMS):
    swagger = tmp_path / "swagger.json"
    swagger.write_text(json.dumps(spec), encoding="utf-8")
    return str(swagger), tmp_path / "mocks"


def _mock(mock_dir, rel, method, path, scenarios):
    target = mock_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": {"method": method, "path": path},
        "scenarios": scenarios,
    }), encoding="utf-8")
    return target


def _mock_every_other_route(mock_dir, spec, skip):
    """Mocks for the rest of the swagger, so `missing` is empty.

    Only for the tests that assert the check is GREEN: an incomplete fixture
    fails for its own reason, and "no drift" would then be measuring the
    wrong absence.
    """
    for path, methods in spec["paths"].items():
        if path == skip:
            continue
        for method, op in methods.items():
            _mock(mock_dir, f"rest/{op['operationId']}.mock.json",
                  method.upper(), path,
                  {f"s{code}": {"status": int(code), "body": {"id": "1"}}
                   for code in op["responses"]})


def _forms(report) -> list[str]:
    """The form letter of each undeclared-status finding, in order."""
    return [note.split("not declared [")[1][0] for note in report.unmatched]


# --------------------------------------------------------------------- #
# The precondition, asserted before anything is concluded from silence
# --------------------------------------------------------------------- #

def _assert_the_asymmetry_exists(spec):
    """Form A needs one realm to declare a status its twin does not.

    Asserted separately from the finding, because the two ways this test can
    go quiet are not the same thing: the implementation stopped classifying
    A, or the material stopped existing. In a fixture the material is fixed,
    so this reads as a guard against editing the fixture out from under the
    test. On the real corpus — where the same probe is run as a
    cross-check — it is load-bearing: a backend adding the missing response
    is DESIRABLE progress that silences the probe, and without this the
    silence would be read as a regression.

    When A's material does disappear from a project's corpus, this is what
    says so, and the probe moves here.
    """
    admin = spec["paths"]["/api/admin/stalls/suspend"]["post"]["responses"]
    partner = spec["paths"]["/api/partner/stalls/suspend"]["post"]["responses"]
    assert "404" in admin, "the twin no longer declares 404 — material gone"
    assert "404" not in partner, "the asymmetry is closed — material gone"


def test_the_precondition_guard_fires_when_the_asymmetry_is_closed():
    """The guard is itself a negative test, so it is itself fired.

    Without this, a guard that always returns true passes every test below
    while proving nothing — which is the shape this whole file exists to
    reject, one level up. (One level: nothing fires THIS test's own
    assertion, and that cut-off is deliberate rather than overlooked.)
    """
    closed = json.loads(json.dumps(TWIN_REALMS))
    closed["paths"]["/api/partner/stalls/suspend"]["post"][
        "responses"]["404"] = JSON

    with pytest.raises(AssertionError, match="asymmetry is closed"):
        _assert_the_asymmetry_exists(closed)


# --------------------------------------------------------------------- #
# The three forms
# --------------------------------------------------------------------- #

def test_form_a_names_the_twin_and_gates(tmp_path):
    _assert_the_asymmetry_exists(TWIN_REALMS)
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "not_found": {"status": 404, "body": {"id": "1"}}})

    report = generate([swagger], mocks, check=True)

    assert _forms(report) == ["A"]
    assert len(report.unmatched_borrowed) == 1
    [finding] = report.unmatched_borrowed
    # The twin, and the action — which is the opposite of C's.
    assert "POST /api/admin/stalls/suspend declares 404" in finding
    assert "fix the swagger" in finding
    assert report.has_drift


def test_form_c_says_the_code_was_borrowed_and_gates(tmp_path):
    """No twin declares 409; an unrelated operation does. The measured
    incident's shape."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "conflict": {"status": 409, "body": {"id": "1"}}})

    report = generate([swagger], mocks, check=True)

    assert _forms(report) == ["C"]
    assert len(report.unmatched_borrowed) == 1
    [finding] = report.unmatched_borrowed
    assert "confirm the implementation has this branch" in finding
    # Not A: naming a twin that is not one sends the reader to the wrong
    # repository.
    assert "fix the swagger" not in finding
    assert report.has_drift


def test_form_b_is_a_warning(tmp_path):
    """Nothing in the contract declares 500. Both lanes' B findings were
    exactly this, and both were deliberate."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "boom": {"status": 500, "body": {"id": "1"}}})
    _mock_every_other_route(mocks, TWIN_REALMS, "/api/partner/stalls/suspend")

    report = generate([swagger], mocks, check=True)

    assert _forms(report) == ["B"]
    assert report.unmatched_borrowed == []
    assert not report.has_drift
    # Still visible — a warning, not a silence.
    assert len(report.unmatched_notes) == 1


def test_the_natural_rule_would_have_inverted_this(tmp_path):
    """The two arms side by side, which is the whole argument. Gating "the
    contract has this nowhere" fails the 500 and passes the 409."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "boom": {"status": 500, "body": {"id": "1"}},
           "conflict": {"status": 409, "body": {"id": "1"}}})

    report = generate([swagger], mocks, check=True)

    gated = {note.split("  ")[1].split(":")[0]
             for note in report.unmatched_borrowed}
    assert gated == {"conflict"}
    assert "B" in _forms(report) and "C" in _forms(report)


def test_the_gating_forms_are_declared_not_spelled_out():
    assert set(GATING_STATUS_FORMS) == {"A", "C"}


# --------------------------------------------------------------------- #
# The scope, asked of this gate rather than inherited from a sibling fix
# --------------------------------------------------------------------- #

EXCLUDED = PathScope(exclude=("/api/partner/*",))


def test_an_out_of_scope_route_does_not_gate(tmp_path):
    """The fourth place a scope decision is made, and it ships in the same
    release as the fix to the third. A new gate that ignored the scope would
    fail the check on the very files `--check` prints as "outside this
    project's API paths, safe to delete" — so it is measured here rather
    than inferred from the sibling fix, which is inside `update_default` and
    cannot reach this path."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "conflict": {"status": 409, "body": {"id": "1"}}})

    scoped = generate([swagger], mocks, check=True, scope=EXCLUDED)
    unscoped = generate([swagger], mocks, check=True)

    assert unscoped.unmatched_borrowed, "the control arm found nothing"
    assert scoped.unmatched_borrowed == []


def test_the_b_denominator_is_the_scope_not_the_whole_swagger(tmp_path):
    """"No operation declares this" means no operation THIS PROJECT calls.

    A shared swagger is sliced per front-end. Measured on one: three
    operations declare 500, one of them inside one consumer's scope and none
    inside another's — so the same finding is a declaration debt for the
    first (gate) and a premise for the second (warning). Reading the whole
    swagger collapses them into one answer, and it is the wrong one for
    whichever project is looking.
    """
    spec = {"openapi": "3.0.3", "paths": {
        "/api/bar/orders": {"post": _op("createOrder", 200)},
        "/api/admin/users": {"get": _op("listUsers", 200, 500)},
    }}
    swagger, mocks = _project(tmp_path, spec)
    _mock(mocks, "bar/orders.mock.json", "POST", "/api/bar/orders",
          {"default": {"status": 200, "body": {"id": "1"}},
           "boom": {"status": 500, "body": {"id": "1"}}})

    bar_only = generate([swagger], mocks, check=True,
                        scope=PathScope(include=("/api/bar/*",)))
    everything = generate([swagger], mocks, check=True)

    # In scope, nothing declares 500 -> a premise, a warning.
    assert _forms(bar_only) == ["B"]
    assert not bar_only.has_drift
    # Across the whole swagger something does -> borrowed, and it gates.
    assert _forms(everything) == ["C"]
    assert everything.has_drift


def test_the_twin_search_still_crosses_the_scope(tmp_path):
    """Narrowed for B, not for the twin. The twin that answers "was this
    forgotten HERE?" is nearly always in the realm the scope filters out —
    that is why it is searched over every operation — so narrowing both
    would delete form A from every scoped project at once."""
    _assert_the_asymmetry_exists(TWIN_REALMS)
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "not_found": {"status": 404, "body": {"id": "1"}}})

    report = generate([swagger], mocks, check=True,
                      scope=PathScope(include=("/api/partner/*",)))

    assert _forms(report) == ["A"]
    assert "POST /api/admin/stalls/suspend declares 404" in \
        report.unmatched_borrowed[0]


# --------------------------------------------------------------------- #
# The way out
# --------------------------------------------------------------------- #

def test_a_declared_undeclared_status_does_not_gate(tmp_path):
    """A scenario that has to answer a borrowed code — a fail-open
    regression, an edge the contract will never state — says so. Without a
    way out, the gate has a state a project cannot leave, and a red that
    cannot be cleared is one people learn to read past."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "conflict": {"status": 409, "body": {"id": "1"},
                        "undeclaredStatus": {
                            "reason": "drives the fail-open regression; the "
                                      "contract will not state this"}}})
    _mock_every_other_route(mocks, TWIN_REALMS, "/api/partner/stalls/suspend")

    report = generate([swagger], mocks, check=True)

    assert report.unmatched_borrowed == []
    assert not report.has_drift
    # Still counted and still visible: declaring is not deleting.
    assert len(report.unmatched) == 1


def test_a_declaration_without_a_reason_does_not_silence_it(tmp_path):
    """The same rule `contractViolations` carries: a suppression nobody can
    explain is usually one nobody fixed."""
    swagger, mocks = _project(tmp_path)
    _mock(mocks, "partner/suspend.mock.json", "POST",
          "/api/partner/stalls/suspend",
          {"default": {"status": 200, "body": {"id": "1"}},
           "conflict": {"status": 409, "body": {"id": "1"},
                        "undeclaredStatus": {"reason": "   "}}})

    report = generate([swagger], mocks, check=True)

    assert len(report.unmatched_borrowed) == 1


def test_a_generated_mock_gates_whatever_the_form(tmp_path):
    """`generated/` is a pure function of the swagger, so an undeclared
    status there is impossible in every form — including B, which is a
    judgement about an author's intent and there is no author."""
    swagger, mocks = _project(tmp_path)
    generate([swagger], mocks)
    target = next(mocks.rglob("generated/**/partnerSuspend.mock.json"))
    doc = json.loads(target.read_text(encoding="utf-8"))
    doc["scenarios"]["boom"] = {"status": 500, "body": {"id": "1"}}
    target.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    report = generate([swagger], mocks, check=True)

    assert _forms(report) == ["B"]
    assert report.unmatched_generated
    assert report.unmatched_borrowed == []   # the generated bucket owns it
    assert report.has_drift


class TestFormBOffersNoInstructionItCannotHonour:
    """B's finding must not tell the reader to declare the scenario.

    It used to. `undeclaredStatus` is consulted on the gating path only —
    the ruling is that a code no operation declares is a premise, not a
    declarable — so a consumer who followed the instruction got output that
    did not change by a single byte, concluded they had written the key
    wrong, and went to read the generator.

    An instruction that does nothing is worse than none: the tool says
    nothing about being inapplicable, so the failure is attributed to the
    reader. Same defect as the `--update-default` remedy that could not fix
    a non-default scenario, which is the ticket that opened this release —
    shipped again inside the release that fixed it.

    A and C keep their instructions, and they are opposite (A: the swagger
    for this operation is short a response; C: the mock may be answering a
    branch the implementation does not have), so this is not "drop the
    advice", it is "do not advise where there is nothing to do".
    """

    def test_b_says_nothing_to_compare_and_stops_there(self):
        from jsonui_test_cli.mock.generate import _STATUS_FORM_REMEDY
        b = _STATUS_FORM_REMEDY["B"]
        assert "nothing to compare against" in b
        # Matched on the instruction, not on the word: the sentence still
        # says "no operation ... declares {status}", which is a statement of
        # fact. The first version of this assertion tripped on that
        # substring and read as a failure of the code.
        assert "declare it on the scenario" not in b, (
            "B takes no declaration, so it must not ask for one")
        assert "if it is deliberate" not in b

    def test_a_and_c_still_carry_their_opposite_remedies(self):
        # The control. Without it, "B has no instruction" and "no form has an
        # instruction" are the same result, and the whole point of the
        # remedy table is that A and C differ.
        from jsonui_test_cli.mock.generate import _STATUS_FORM_REMEDY
        assert "fix the swagger" in _STATUS_FORM_REMEDY["A"]
        assert "confirm the implementation" in _STATUS_FORM_REMEDY["C"]
