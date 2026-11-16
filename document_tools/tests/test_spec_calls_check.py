"""`calls` entries are checked against what the corpus declares.

Nothing read this field: the codegen ignores it, so build and verify stay
green whatever it says, while the HTML generator draws it as a reference.
A project declared a call that was never implemented, and the thing that
makes it worth a gate is how it decays — a vocabulary rename rewrites the
phantom along with everything real, so a stale-looking name becomes a
current-looking one and nobody suspects it again.

The arms below are the ones a half-built version fails differently:
  - a phantom is reported;
  - a call declared in ANOTHER spec resolves (the false positive that a
    file-scoped check produces, and the worst possible output here — a real
    declaration called a phantom);
  - an empty scan does not pass as clean.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.check.spec_calls import check_spec_calls, summary_line


def _spec(**flow) -> dict:
    return {"type": "screen_spec", "metadata": {"name": "S"},
            "dataFlow": flow}


class SpecCallsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.specs = self.root / "docs" / "screens" / "json"
        self.specs.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name: str, doc: dict) -> None:
        (self.specs / f"{name}.spec.json").write_text(
            json.dumps(doc, indent=2), encoding="utf-8")

    def _run(self):
        return check_spec_calls(self.root, self.specs)

    def test_a_resolvable_call_passes(self):
        self._write("login", _spec(
            repositories=[{"name": "UserRepository",
                           "methods": [{"name": "login"}]}],
            useCases=[{"name": "LoginUseCase",
                       "methods": [{"name": "run",
                                    "calls": ["UserRepository.login"]}]}],
        ))
        report = self._run()
        self.assertEqual(1, report.declared)
        self.assertEqual(1, report.compared)
        self.assertTrue(all(r.status == "ok" for r in report.results))

    def test_a_phantom_call_is_reported(self):
        self._write("logout", _spec(
            repositories=[{"name": "UserRepository",
                           "methods": [{"name": "logout"}]}],
            useCases=[{"name": "LogoutUseCase",
                       "methods": [{"name": "run", "calls": [
                           "UserRepository.unregisterDeviceToken"]}]}],
        ))
        report = self._run()
        bad = [r for r in report.results if r.status != "ok"]
        self.assertEqual(1, len(bad))
        # The message distinguishes "class unknown" from "class known,
        # method not" — different repairs.
        self.assertIn("no method", bad[0].actual)

    def test_a_call_declared_in_another_spec_resolves(self):
        # The false positive a file-scoped check produces. Calling a real
        # declaration a phantom is the worst output this gate can give, so
        # it is pinned separately from the happy path.
        self._write("profile", _spec(
            useCases=[{"name": "ProfileUseCase",
                       "methods": [{"name": "run", "calls": [
                           "UserRepository.registerInstallationId"]}]}],
        ))
        self._write("session", _spec(
            repositories=[{"name": "UserRepository", "methods": [
                {"name": "registerInstallationId"}]}],
        ))
        report = self._run()
        self.assertTrue(all(r.status == "ok" for r in report.results),
                        [r.actual for r in report.results if r.status != "ok"])

    def test_an_unknown_class_says_so(self):
        self._write("orders", _spec(
            useCases=[{"name": "OrderUseCase",
                       "methods": [{"name": "run",
                                    "calls": ["GhostRepository.fetch"]}]}],
        ))
        bad = [r for r in self._run().results if r.status != "ok"]
        self.assertEqual(1, len(bad))
        self.assertIn("no spec declares", bad[0].actual)

    def test_an_empty_scan_is_not_clean(self):
        # No specs at all: every count is zero and every call resolves
        # vacuously. Saying nothing here is the failure this whole family
        # of gates keeps producing.
        report = self._run()
        self.assertEqual(0, report.declared)
        self.assertTrue(report.warnings)
        self.assertIn("NOT the same as nothing being wrong", report.warnings[0])

    def test_specs_with_no_declarations_cannot_certify(self):
        # Files exist, but nothing declares a resolution target. A clean
        # result would be an artefact of the empty surface.
        self._write("plain", {"type": "screen_spec", "metadata": {"name": "P"}})
        report = self._run()
        self.assertTrue(report.warnings)
        self.assertIn("certifies nothing", report.warnings[0])

    def test_the_summary_names_its_denominator(self):
        self._write("login", _spec(
            repositories=[{"name": "R", "methods": [{"name": "m"}]}],
            useCases=[{"name": "U", "methods": [
                {"name": "run", "calls": ["R.m", "R.gone"]}]}],
        ))
        line = summary_line(self._run())
        self.assertIn("1 of 2 declared call(s) resolve", line)
        self.assertIn("spec file(s) scanned", line)

    def test_the_summary_carries_the_warning_when_nothing_was_scanned(self):
        line = summary_line(self._run())
        self.assertIn("0 of 0", line)
        self.assertIn("nothing", line)


if __name__ == "__main__":
    unittest.main()
