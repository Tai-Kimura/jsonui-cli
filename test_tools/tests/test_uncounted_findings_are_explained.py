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
        cli._print_uncounted_footnote(uncounted)
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
