"""What a gate actually reads: the printed line and the saved report.

The unit tests beside this one pin the counting. These pin the two surfaces a
consumer builds against — the summary line `jsonui-doc check` prints, and
`.check-report.json`. Both were countable-but-unreadable: `ok=136` with no
unit and no denominator, so a lane wrote its own denominator by inferring the
unit from the shape of `target` strings.

The exclusion case is driven through `ignore_paths` exactly as the reporting
project hit it — one added pattern, output still saying success.
"""

from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_doc_cli.check.runner import EXIT_OK, run_checks
from jsonui_doc_cli.project_config import load_checks

SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Svc"},
    "paths": {
        "/api/alpha": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/beta": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/internal/gamma": {
            "get": {"responses": {"200": {"description": "ok"}}}},
    },
}


class CoverageE2ETests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / ".jsonui" / "checks").mkdir(parents=True)
        (self.root / "docs" / "api" / "svc.json").write_text(
            json.dumps(SPEC), encoding="utf-8")
        script = self.root / ".jsonui" / "checks" / "impl.py"
        script.write_text("import json\nprint(json.dumps("
                          + repr(SPEC) + "))\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, ignore_paths=()):
        decl = {"name": "api", "type": "builtin:openapi-diff",
                "impl_openapi_command": "python3 .jsonui/checks/impl.py"}
        if ignore_paths:
            decl["ignore_paths"] = list(ignore_paths)
        code = run_checks(load_checks({"checks": [decl]}, self.root),
                          self.root, {})
        report = json.loads(
            (self.root / "docs" / "api" / ".check-report.json").read_text())
        return code, report

    # ---- the saved report ------------------------------------------- #

    def test_the_report_names_its_unit_and_denominator(self):
        _, report = self.run_check()
        s = report["summary"]
        self.assertEqual(s["unit"], "operation")
        self.assertEqual(s["declared"], 3)
        self.assertEqual(s["compared"], 3)

    def test_one_ignore_pattern_shows_up_as_excluded_not_as_a_smaller_total(self):
        """The reported failure: `ok=136` where 100 had silently left."""
        _, report = self.run_check(["/api/internal/*"])
        s = report["summary"]
        self.assertEqual(s["declared"], 3)
        self.assertEqual(s["compared"], 2)
        self.assertEqual(s["excluded"], 1)

    def test_the_arithmetic_closes(self):
        for patterns in ([], ["/api/internal/*"], ["/api/alpha"]):
            with self.subTest(patterns=patterns):
                _, report = self.run_check(patterns)
                s = report["summary"]
                self.assertNotIn("unaccounted", s)
                self.assertEqual(s["compared"] + s.get("excluded", 0),
                                 s["declared"])

    # ---- the endpoint ------------------------------------------------ #

    def test_excluding_everything_says_so_loudly(self):
        code, report = self.run_check(["/api/*"])
        self.assertEqual(report["summary"]["compared"], 0)
        self.assertTrue(
            any("NONE were compared" in w for w in report["warnings"]),
            report["warnings"])
        # The notice and the denominator are separate expressions over the
        # same count, so they are pinned together: a notice saying "3 are
        # declared" beside a summary saying `declared: 0` would be one of
        # them lying, and a red-check showed the two can be broken apart.
        self.assertEqual(report["summary"]["declared"], 3)
        self.assertTrue(any("3 operation(s) are declared" in w
                            for w in report["warnings"]), report["warnings"])

    def test_excluding_everything_does_not_change_the_exit_code(self):
        """Excluding everything is a legitimate configuration, so: loud, not fatal.

        Deliberate: the exit contract (0 ok / 1 mismatch / 2 error) is an
        invariant of this checker and is not moved by a reporting change.
        """
        code, _ = self.run_check(["/api/*"])
        self.assertEqual(code, EXIT_OK)

    def test_a_normal_run_does_not_carry_the_notice(self):
        _, report = self.run_check()
        self.assertFalse(any("NONE were compared" in w
                             for w in report["warnings"]), report["warnings"])

    # ---- provenance --------------------------------------------------- #

    def test_the_report_names_what_it_compared(self):
        _, report = self.run_check()
        inputs = report["inputs"]
        self.assertEqual(inputs["impl_command"],
                         ["python3", ".jsonui/checks/impl.py"])
        self.assertTrue(inputs["impl_openapi_sha256"].startswith("sha256:"))
        self.assertEqual(inputs["doc_files"], ["docs/api/svc.json"])

    def test_the_impl_hash_tracks_the_payload_that_was_compared(self):
        """Two runs against different implementations differ here.

        This is the fact the reporter wanted from `impl_source_rev`, and the
        one this tool can actually state: the implementation sits behind a
        command, so its revision is not observable, but the OpenAPI document
        that was compared is.
        """
        _, first = self.run_check()
        changed = json.loads(json.dumps(SPEC))
        changed["paths"]["/api/alpha"]["get"]["summary"] = "moved on"
        script = self.root / ".jsonui" / "checks" / "impl.py"
        script.write_text("import json\nprint(json.dumps("
                          + repr(changed) + "))\n", encoding="utf-8")
        _, second = self.run_check()
        self.assertNotEqual(first["inputs"]["impl_openapi_sha256"],
                            second["inputs"]["impl_openapi_sha256"])

    def test_no_revision_is_invented_when_the_tree_is_not_a_checkout(self):
        """Absent, not a plausible-looking wrong value."""
        _, report = self.run_check()
        self.assertNotIn("doc_source_rev", report["inputs"])

    def test_the_implementation_side_is_never_given_a_revision(self):
        """It runs behind an opaque command; a rev read here would be the docs'."""
        _, report = self.run_check()
        self.assertNotIn("impl_source_rev", report["inputs"])

    # ---- the printed line --------------------------------------------- #

    def test_the_printed_summary_carries_unit_and_denominator(self):
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            self.run_check(["/api/internal/*"])
        out = buf.getvalue()
        self.assertIn("[2/3 operation", out)
        self.assertIn("1 excluded by config", out)


if __name__ == "__main__":
    unittest.main()
