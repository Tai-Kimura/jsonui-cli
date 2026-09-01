"""`Warnings:` says what it counts, and the summary says what it does not.

Two labels' worth of `[WARN]` reach one `validate` run, and only some move
the counter. Measured, the ONLY thing separating them on screen was whether
the label was followed by one space or four — and those four are padding to
align with `[OPTIONAL]`/`[STATUS]`, put there for columns rather than for
weight. An accident was carrying the distinction, which is why a lane
running "keep Warnings at zero" could not predict from a line whether its
gate would break.

A summary key (`Unactionable: 93`) was the other candidate and was not
taken: it creates a new thing to grep and a permanently non-zero NUMBER,
which invites the zero discipline onto a count that can never be zero. The
footnote carries the same number without becoming a field, so every
existing baseline stays exactly where it is — asserted here end to end.

THE REASONS ARE NOT ONE REASON, and finding the third is why this file
exists. The design memo that led to it claimed every uncounted finding was
either impossible or undesirable to clear. That was wrong: a scenario with
NO STATUS is uncounted and perfectly clearable. It had been folded in with
"no remedy exists" and was invisible to everyone, including the two people
who wrote the folding down.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from jsonui_test_cli import cli
from jsonui_test_cli.mock.generate import (
    UNMATCHED_NOTE_CLASSES, classify_unmatched_note, generate,
)

_OK = {"description": "d",
       "content": {"application/json": {"schema": {"type": "object"}}}}


def _swagger(tmp_path, *, sibling_declares_409: bool):
    spec = tmp_path / "api.json"
    paths = {"/b": {"post": {"operationId": "opB", "responses": {"200": _OK}}}}
    if sibling_declares_409:
        paths["/a"] = {"post": {"operationId": "opA",
                                "responses": {"200": _OK, "409": _OK}}}
    spec.write_text(json.dumps({
        "openapi": "3.0.0", "info": {"title": "t", "version": "1"},
        "paths": paths,
    }), encoding="utf-8")
    return spec


def _run(tmp_path, scenarios, *, sibling_declares_409=False):
    spec = _swagger(tmp_path, sibling_declares_409=sibling_declares_409)
    out = tmp_path / "mocks"
    out.mkdir()
    generate([spec], out)
    hand = out / "b" / "opB.mock.json"
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text(json.dumps({
        "source": {"operationId": "opB", "method": "POST", "path": "/b"},
        "scenarios": {"default": {"status": 200, "body": {}}, **scenarios},
    }), encoding="utf-8")

    report = generate([spec], out, check=True)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        uncounted = cli._print_uncompared(report)
        cli._print_uncounted_footnote(uncounted, command="validate")
    return uncounted, buffer.getvalue()


class TestEachReasonIsReachableAndSeparate:
    """Every clause has to be reachable, or it is a sentence that reassures
    the reader about a case that never occurs."""

    def test_a_status_no_one_declares_has_no_remedy(self, tmp_path):
        uncounted, out = _run(tmp_path, {"teapot": {"status": 418, "body": {}}})

        assert uncounted["no-remedy"] == 1
        assert "no remedy" in out

    def test_a_scenario_declaring_its_own_status_should_not_be_cleared(
            self, tmp_path):
        """Form A/C reach the uncounted set exactly when the author declared
        `undeclaredStatus`, so this needs a sibling operation that owns the
        code — without one the form is B and this clause never fires."""
        uncounted, out = _run(
            tmp_path,
            {"conflict": {"status": 409, "body": {},
                          "undeclaredStatus": {"reason": "the sibling owns it"}}},
            sibling_declares_409=True)

        assert uncounted["declared"] == 1
        assert "on purpose" in out

    def test_a_scenario_with_no_status_can_be_cleared(self, tmp_path):
        """The one the blanket rule hid. It is uncounted like the other two
        and unlike them it has a remedy, so it must not be described with
        the words that mean 'nothing can be done'."""
        uncounted, out = _run(tmp_path, {"weird": {"body": {}}})

        assert uncounted["actionable"] == 1
        assert "CAN be cleared" in out
        assert "no remedy" not in out

    def test_the_three_do_not_share_a_sentence(self, tmp_path):
        """All at once. Folded into one phrase, a reader takes 'should not'
        for 'cannot' and waits for a release that makes it fixable — and
        never learns the third is theirs to fix today."""
        uncounted, out = _run(
            tmp_path,
            {"weird": {"body": {}},
             "teapot": {"status": 418, "body": {}},
             "conflict": {"status": 409, "body": {},
                          "undeclaredStatus": {"reason": "sibling"}}},
            sibling_declares_409=True)

        assert uncounted == {"actionable": 1, "no-remedy": 1, "declared": 1}
        assert "3 finding(s) above are not counted" in out
        for phrase in ("no remedy", "on purpose", "CAN be cleared"):
            assert phrase in out, phrase

    def test_nothing_uncounted_prints_nothing(self, tmp_path):
        """A footnote on every run is the standing line that a new one hides
        behind — the thing this whole distinction exists to avoid."""
        uncounted, out = _run(tmp_path, {})

        assert sum(uncounted.values()) == 0
        assert out.strip() == ""


class TestTheClassifierLivesWithItsProducer:
    def test_every_note_shape_lands_in_exactly_one_class(self, tmp_path):
        """The classifier reads strings the generator builds. It lives in
        that module for this reason, but proximity is not agreement — so
        every note a real run produces is classified, and 'unclassified'
        would show up as a KeyError rather than as a quiet miscount."""
        uncounted, _ = _run(
            tmp_path,
            {"weird": {"body": {}},
             "teapot": {"status": 418, "body": {}},
             "conflict": {"status": 409, "body": {},
                          "undeclaredStatus": {"reason": "sibling"}}},
            sibling_declares_409=True)

        assert set(uncounted) == set(UNMATCHED_NOTE_CLASSES)
        assert sum(uncounted.values()) == 3

    @pytest.mark.parametrize("note,expected", [
        ("m.json  weird: no status", "actionable"),
        ("m.json  x: status 418 not declared [B] — nothing to compare", "no-remedy"),
        ("m.json  x: status 409 not declared [A] — sibling declares", "declared"),
        ("m.json  x: status 409 not declared [C] — borrowed", "declared"),
    ])
    def test_the_shapes_it_reads(self, note, expected):
        assert classify_unmatched_note(note) == expected


class TestTheBaselineDoesNotMove:
    """The promise made when this was chosen over a summary key."""

    def _project(self, tmp_path, scenarios):
        docs = tmp_path / "docs" / "api"
        docs.mkdir(parents=True)
        (docs / "spec.json").write_text(json.dumps({
            "openapi": "3.0.0",
            "paths": {"/api/x": {"get": {
                "operationId": "getX", "responses": {"200": _OK}}}},
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        (proj / "tests" / "mocks").mkdir(parents=True)
        (proj / "tests" / "sample.test.json").write_text(json.dumps({
            "type": "screen", "source": {"layout": "test.json"},
            "metadata": {"name": "sample_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": "../docs/api/spec.json",
                     "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        mock = proj / "tests" / "mocks" / "x" / "getX.mock.json"
        mock.parent.mkdir(parents=True)
        mock.write_text(json.dumps({
            "source": {"operationId": "getX", "method": "GET", "path": "/api/x"},
            "scenarios": {"default": {"status": 200, "body": {}}, **scenarios},
        }), encoding="utf-8")
        return proj

    def test_warnings_stays_zero_with_uncounted_findings_present(
            self, tmp_path, monkeypatch, capsys):
        """End to end, because this is the claim consumers were given. A
        lane at `Warnings: 0` with a permanent form B keeps its baseline;
        the footnote appears beside it rather than in it."""
        import argparse
        proj = self._project(tmp_path, {"teapot": {"status": 418, "body": {}}})
        monkeypatch.chdir(proj)

        cli.cmd_validate(argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=False, no_install=True, strict=False))
        out = capsys.readouterr().out

        # ONE summary line, and it says zero. `"Warnings: 0" in out` was
        # the first version and it is too weak: a change that leaves the
        # original line alone and prints a second, corrected one satisfies
        # it. That is not hypothetical — the first mutation written to
        # red-check this test did exactly that, and the test stayed green
        # while the run reported two different counts.
        counts = [line for line in out.splitlines() if line.startswith("Files:")]
        assert len(counts) == 1, out
        assert "Warnings: 0" in counts[0], counts[0]

        assert "not counted in Warnings:" in out
        assert "no remedy" in out


class TestTheFourExits:
    """Where a finding can come out, counted as four places rather than one.

    Every wrong sentence written about this file came from checking one exit
    and then saying something about "output":

      1 denominator   the `mock contract:` line (`contract_summary`)
      2 printers      `_print_uncompared` / `_print_drift_findings`
      3 counter       `Warnings:` / `Errors:`
      4 exit code

    `a10c5f56` said the actionable mock warnings were excluded from the
    COUNTER — exit 3 alone. The correction to it said `validate` never
    PRINTS them — exit 2 alone, and also wrong, because exit 1 names stale
    bodies and a consumer had that line on screen throughout. The same
    mistake twice from opposite directions, because both answered "does it
    show up" with one predicate.

    A footnote written from exit 2 then contradicted the line one row above
    it, in the same output. That is what these pin.
    """

    def _project(self, tmp_path):
        """No hand-written mock, unlike the fixture above.

        The first draft reused it and measured nothing: a hand-written mock
        OVERLAYS the route, so the generated copy is not compared and
        editing it produces no stale finding at all. The test failed with
        `2 compared` and no stale count — the fixture was wrong, not the
        code, which is the third time today a probe measured its own setup.
        """
        docs = tmp_path / "docs" / "api"
        docs.mkdir(parents=True)
        (docs / "spec.json").write_text(json.dumps({
            "openapi": "3.0.0",
            "paths": {"/api/x": {"get": {"operationId": "getX", "responses": {
                "200": {"description": "d", "content": {"application/json": {
                    "schema": {"type": "object", "required": ["id"],
                               "properties": {"id": {"type": "string"}}}}}}}}}},
        }), encoding="utf-8")
        proj = tmp_path / "proj"
        (proj / "tests" / "mocks").mkdir(parents=True)
        (proj / "tests" / "sample.test.json").write_text(json.dumps({
            "type": "screen", "source": {"layout": "test.json"},
            "metadata": {"name": "sample_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": "../docs/api/spec.json",
                     "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        return proj

    def _stale(self, tmp_path, monkeypatch, capsys):
        import argparse
        proj = self._project(tmp_path)
        monkeypatch.chdir(proj)
        args = lambda: argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=False, no_install=True, strict=False)
        cli.cmd_validate(args())
        capsys.readouterr()

        generated = next(p for p in (proj / "tests" / "mocks").rglob(
            "getX.mock.json") if "generated" in str(p))
        data = json.loads(generated.read_text(encoding="utf-8"))
        data["scenarios"]["default"]["body"] = {"wrong": 1}
        generated.write_text(json.dumps(data), encoding="utf-8")

        rc = cli.cmd_validate(args())
        return rc, capsys.readouterr().out

    def test_the_denominator_line_names_a_stale_generated_body(
            self, tmp_path, monkeypatch, capsys):
        _, out = self._stale(tmp_path, monkeypatch, capsys)

        denominator = [l for l in out.splitlines()
                       if l.startswith("mock contract:")]
        assert len(denominator) == 1, out
        assert "stale" in denominator[0], denominator

    def test_the_footnote_does_not_contradict_the_line_above_it(
            self, tmp_path, monkeypatch, capsys):
        """The regression this replaces, exactly: the footnote said stale
        bodies "appear only in `mock generate --check`" while the line one
        row above was naming one."""
        _, out = self._stale(tmp_path, monkeypatch, capsys)

        footnote = [l for l in out.splitlines() if "appear only in" in l]
        assert len(footnote) == 1, out
        assert "stale" not in footnote[0], footnote[0]

    def test_it_is_reported_but_neither_counted_nor_failed(
            self, tmp_path, monkeypatch, capsys):
        """Exits 3 and 4. Non-gating is DELIBERATE — regenerating clears
        them, so they follow the ORPHAN convention."""
        rc, out = self._stale(tmp_path, monkeypatch, capsys)

        assert rc == 0
        summary = [l for l in out.splitlines() if l.startswith("Files:")]
        assert len(summary) == 1 and "Warnings: 0" in summary[0], summary

    def test_the_convention_is_readable_beside_the_number(
            self, tmp_path, monkeypatch, capsys):
        """A consumer read the count, ran `mock generate --check` to chase
        it, found that green too, and took the pair for a bug. Saying "does
        not fail, by convention" turns two green exits into a rule."""
        _, out = self._stale(tmp_path, monkeypatch, capsys)

        assert "does NOT fail this check" in out
        assert "jsonui-test mock generate" in out

    def test_the_convention_line_is_absent_when_nothing_is_stale(
            self, tmp_path, monkeypatch, capsys):
        """A standing line is the one a new finding hides behind."""
        import argparse
        proj = self._project(tmp_path)
        monkeypatch.chdir(proj)
        cli.cmd_validate(argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=False, no_install=True, strict=False))

        assert "does NOT fail this check" not in capsys.readouterr().out


class TestTheMockLineSaysWhatItIsLookingAt:
    def test_it_names_the_two_findings_it_really_does_not_carry(
            self, tmp_path, monkeypatch, capsys):
        """Kept only for the two that survived measurement. Both fixtures
        were checked against the report object first — an absent line
        proves nothing about a finding that never occurred — and both
        produce a `misnamed` entry and a note-only body while `validate`
        stays silent about them."""
        import argparse
        proj = TestTheBaselineDoesNotMove()._project(tmp_path, {})
        monkeypatch.chdir(proj)

        cli.cmd_validate(argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=False, no_install=True, strict=False))
        out = capsys.readouterr().out

        assert "mock generate --check" in out
        assert "misnamed files" in out
        assert "optional-field omissions" in out


class TestWhichCommandEachClassCanReach:
    """The footnote had to move to where its findings are.

    `_print_uncounted_footnote` was printed by `validate` alone, and one of
    its three clauses cannot occur there. Measured on both sides — a
    hand-written mock and a `generated/` one — a scenario with no status is
    ITSELF a validation error, and the mock gate runs only `if total_errors
    == 0`, so the run that would produce the finding exits 1 several screens
    earlier.

    That is structural, not a property of one fixture: the note is built on
    `status is None`, the validator errors on anything that is not an int in
    100..599, and the first set is a strict subset of the second — over the
    same files, since both sides walk `_resolve_mock_dir()` for
    `*.mock.json`. Two modules have to change together to open it.

    Meanwhile `mock generate --check`, where all three classes DO appear,
    printed them as three identical `[WARN]` lines and classified nothing:
    it carried its own copy of the printer, and only the other copy ever
    learned to classify. So one command could not see the class, and the
    other did not explain it.

    Every test here has a NON-FIRING half, and a non-firing half is only
    meaningful against a control — "no line appeared" says nothing about a
    finding that never occurred, so the same tree is first run through a
    command that does produce it.
    """

    #: A realm twin declaring 409 turns a 409 scenario from form B ("no
    #: operation declares it", a premise) into form C ("borrowed", a gate).
    #: Without it the `declared` class is unreachable: form B never consults
    #: `undeclaredStatus`, so nothing can land in that bucket. The first
    #: draft of these tests omitted the twin and measured form B three times
    #: while claiming to measure three different things.
    def _project(self, tmp_path, scenarios, *, twin=False):
        docs = tmp_path / "docs" / "api"
        docs.mkdir(parents=True)
        paths = {"/api/x": {"get": {"operationId": "getX",
                                    "responses": {"200": _OK}}}}
        if twin:
            paths["/api/y"] = {"get": {"operationId": "getY",
                                       "responses": {"200": _OK, "409": _OK}}}
        (docs / "spec.json").write_text(json.dumps(
            {"openapi": "3.0.0", "paths": paths}), encoding="utf-8")
        proj = tmp_path / "proj"
        (proj / "tests" / "mocks").mkdir(parents=True)
        (proj / "tests" / "sample.test.json").write_text(json.dumps({
            "type": "screen", "source": {"layout": "test.json"},
            "metadata": {"name": "sample_test", "description": "d"},
            "cases": [{"name": "c", "description": "d",
                       "steps": [{"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        (proj / "jui.config.json").write_text(json.dumps({
            "mock": {"swagger": "../docs/api/spec.json",
                     "mockDir": "tests/mocks"},
        }), encoding="utf-8")
        mock = proj / "tests" / "mocks" / "x" / "getX.mock.json"
        mock.parent.mkdir(parents=True)
        mock.write_text(json.dumps({
            "source": {"operationId": "getX", "method": "GET", "path": "/api/x"},
            "scenarios": {"default": {"status": 200, "body": {}}, **scenarios},
        }), encoding="utf-8")
        if twin:
            # The twin gets a mock too. Without one the route is `missing`,
            # the check fails on THAT, and an arm asserting a clean exit
            # reads as the declaration having failed to silence anything.
            twin_mock = proj / "tests" / "mocks" / "y" / "getY.mock.json"
            twin_mock.parent.mkdir(parents=True)
            twin_mock.write_text(json.dumps({
                "source": {"operationId": "getY", "method": "GET",
                           "path": "/api/y"},
                "scenarios": {"default": {"status": 200, "body": {}},
                              "conflict": {"status": 409, "body": {}}},
            }), encoding="utf-8")
        return proj

    def _validate(self, proj, monkeypatch, capsys):
        import argparse
        monkeypatch.chdir(proj)
        rc = cli.cmd_validate(argparse.Namespace(
            files=["tests"], verbose=False, quiet=False, config=None,
            no_mock_check=False, no_install=True, strict=False))
        return rc, capsys.readouterr().out

    def _check(self, proj, monkeypatch, capsys):
        import argparse
        monkeypatch.chdir(proj)
        rc = cli.cmd_mock_generate(argparse.Namespace(
            swagger=None, out=None, check=True, config=None, strict=False,
            update_default=False, update=False, force=False))
        return rc, capsys.readouterr().out

    # -- actionable ----------------------------------------------------- #

    def test_check_shows_the_clearable_class_and_says_it_is_clearable(
            self, tmp_path, monkeypatch, capsys):
        rc, out = self._check(
            self._project(tmp_path, {"weird": {"body": {}}}),
            monkeypatch, capsys)

        assert "weird: no status" in out
        assert "CAN be cleared" in out
        assert rc == 0

    def test_validate_cannot_reach_that_class_at_all(
            self, tmp_path, monkeypatch, capsys):
        """The non-firing half, with its control.

        The reader is not left with nothing — they get the `[ERROR]` naming
        the same scenario and the same key — which is why the answer was to
        move the footnote rather than to relax the validator.
        """
        proj = self._project(tmp_path, {"weird": {"body": {}}})
        # CONTROL: this tree really does produce the finding.
        _, control = self._check(proj, monkeypatch, capsys)
        assert "weird: no status" in control, control

        rc, out = self._validate(proj, monkeypatch, capsys)

        assert rc == 1
        assert "CAN be cleared" not in out
        assert "not counted in Warnings:" not in out
        # The gate never ran, so its denominator is absent too: the finding
        # is not merely unexplained here, it is unmeasured.
        assert "mock contract:" not in out
        assert "'status' must be an HTTP status int" in out

    # -- no-remedy ------------------------------------------------------ #

    def test_no_remedy_fires_for_a_status_no_operation_declares(
            self, tmp_path, monkeypatch, capsys):
        _, out = self._check(
            self._project(tmp_path, {"teapot": {"status": 418, "body": {}}}),
            monkeypatch, capsys)

        assert "no remedy" in out

    def test_no_remedy_does_not_fire_for_a_borrowed_code(
            self, tmp_path, monkeypatch, capsys):
        """The non-firing half. A form A/C scenario with no declaration is
        GATED, so it leaves `unmatched_notes` for `[STATUS]` — uncounted and
        unexplained are different states, and a gating finding is neither."""
        proj = self._project(
            tmp_path, {"conflict": {"status": 409, "body": {}}}, twin=True)

        rc, out = self._check(proj, monkeypatch, capsys)

        # CONTROL: the finding exists, under the other label.
        assert "[STATUS]" in out and "409" in out, out
        assert rc == 1
        assert "no remedy" not in out
        assert "do not fail this check:" not in out

    # -- declared ------------------------------------------------------- #

    def test_declared_fires_for_the_object_form(
            self, tmp_path, monkeypatch, capsys):
        proj = self._project(
            tmp_path,
            {"conflict": {"status": 409, "body": {},
                          "undeclaredStatus": {"reason": "the twin owns it"}}},
            twin=True)

        rc, out = self._check(proj, monkeypatch, capsys)

        assert rc == 0
        assert "made on purpose" in out

    def test_declared_does_not_fire_for_a_bare_true(
            self, tmp_path, monkeypatch, capsys):
        """The non-firing half, and the trap it documents.

        Only the object form silences the gate. Measured before this was
        written: a bare `true` produced output BYTE-IDENTICAL to writing
        nothing at all, so the tool could not distinguish "did not declare"
        from "declared in a shape that does nothing" — see
        `_declaration_clause`, which is what broke the tie.
        """
        proj = self._project(
            tmp_path,
            {"conflict": {"status": 409, "body": {},
                          "undeclaredStatus": True}},
            twin=True)

        rc, out = self._check(proj, monkeypatch, capsys)

        assert rc == 1
        assert "made on purpose" not in out
        # Nor is it silently ignored, which is the other half: the finding
        # says the declaration is not the shape it needs.
        assert "does not suppress this finding" in out


class TestOnePrinterForBothCommands:
    """The duplication that let one command learn and the other not.

    `--check` carried its own copy of `  [WARN]    {note} — not compared`,
    byte-for-byte identical to the one in `_print_uncompared`, and only the
    latter was taught to classify. Two copies of a line, one of which
    learned something: the shape `GATING_BUCKETS` and `PATH_KINDS` exist to
    prevent.
    """

    def _both(self, tmp_path, monkeypatch, capsys, scenarios):
        reach = TestWhichCommandEachClassCanReach()
        proj = reach._project(tmp_path, scenarios)
        _, validate_out = reach._validate(proj, monkeypatch, capsys)
        _, check_out = reach._check(proj, monkeypatch, capsys)
        return validate_out, check_out

    def _warn_lines(self, out):
        return [l for l in out.splitlines()
                if l.startswith("  [WARN]    ") and "not compared" in l]

    def test_the_same_note_prints_identically_on_both(
            self, tmp_path, monkeypatch, capsys):
        validate_out, check_out = self._both(
            tmp_path, monkeypatch, capsys,
            {"teapot": {"status": 418, "body": {}}})

        lines = self._warn_lines(validate_out)
        assert len(lines) == 1, validate_out
        assert self._warn_lines(check_out) == lines

    def test_the_lead_names_the_count_that_command_actually_prints(
            self, tmp_path, monkeypatch, capsys):
        """`--check` prints no `Warnings:` line, so the `validate` wording
        would send its reader looking for one that is not there."""
        validate_out, check_out = self._both(
            tmp_path, monkeypatch, capsys,
            {"teapot": {"status": 418, "body": {}}})

        assert "not counted in Warnings:" in validate_out
        assert "do not fail this check:" not in validate_out
        assert "do not fail this check:" in check_out
        assert "not counted in Warnings:" not in check_out

    def test_every_lead_is_declared_rather_than_defaulted(self):
        """A table, not a default: a third caller has to answer the question
        rather than inherit the first caller's answer."""
        assert set(cli.UNCOUNTED_LEAD) == {"validate", "check"}
        for lead in cli.UNCOUNTED_LEAD.values():
            assert lead.format(total=3).startswith("3 finding(s)")

    def test_an_unknown_command_is_a_failure_not_a_silent_default(self):
        with pytest.raises(KeyError):
            cli._print_uncounted_footnote({"no-remedy": 1}, command="serve")


class TestCheckSaysWhatItMeasured:
    """`--check` had no denominator at all.

    It listed findings and closed with "No drift: mocks are in sync with
    swagger." — so a tree with scenarios nobody compared printed the
    sentence a fully-compared tree prints. Same shape as `copied 0` and
    `Warnings: 0`: a run that did not look, reported in the words of a run
    that looked and found nothing.
    """

    def _check(self, tmp_path, monkeypatch, capsys, scenarios):
        reach = TestWhichCommandEachClassCanReach()
        return reach._check(reach._project(tmp_path, scenarios),
                            monkeypatch, capsys)

    def test_the_contract_line_is_printed(self, tmp_path, monkeypatch, capsys):
        _, out = self._check(tmp_path, monkeypatch, capsys,
                             {"teapot": {"status": 418, "body": {}}})

        lines = [l for l in out.splitlines() if l.startswith("mock contract:")]
        assert len(lines) == 1, out
        assert "not compared" in lines[0]

    def test_the_verdict_does_not_claim_what_was_not_compared(
            self, tmp_path, monkeypatch, capsys):
        _, out = self._check(tmp_path, monkeypatch, capsys,
                             {"teapot": {"status": 418, "body": {}}})

        assert "in sync with swagger" not in out
        assert "1 scenario(s) were not compared" in out

    def test_a_fully_compared_tree_still_says_in_sync(
            self, tmp_path, monkeypatch, capsys):
        """The non-firing half. The qualified sentence must not become the
        standing line the next uncompared scenario hides behind."""
        _, out = self._check(tmp_path, monkeypatch, capsys, {})

        assert "No drift: mocks are in sync with swagger." in out
        assert "were not compared" not in out
        assert "do not fail this check:" not in out
