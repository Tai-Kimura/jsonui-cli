"""Tests for jsonui_doc_cli.check.report (result-JSON contract)."""

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.check.report import (
    SCHEMA_VERSION,
    CheckReport,
    ReportValidationError,
    ResultItem,
    compute_input_hashes,
    is_stale,
    load_report,
    report_from_dict,
    report_path_for,
    save_report,
    validate_report_dict,
)


def make_report(**kw) -> CheckReport:
    defaults = dict(
        checker="db-main",
        target_kind="db",
        target_name="main",
        target_extra={"dialect": "mysql"},
        results=[
            ResultItem("reservations.id", "ok", "proof"),
            ResultItem(
                "reservations.fee", "mismatch", "proof",
                expected="INT NULL", actual="INT NOT NULL",
            ),
        ],
    )
    defaults.update(kw)
    return CheckReport(**defaults)


class ReportShapeTests(unittest.TestCase):
    def test_round_trip(self):
        rep = make_report()
        d = rep.to_dict()
        self.assertEqual(d["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(d["target"], {"kind": "db", "name": "main",
                                       "dialect": "mysql"})
        back = report_from_dict(d)
        self.assertEqual(back.checker, "db-main")
        self.assertEqual(back.target_extra, {"dialect": "mysql"})
        self.assertEqual(len(back.results), 2)

    def test_summary_and_mismatch_flag(self):
        rep = make_report()
        self.assertEqual(rep.summary["ok"], 1)
        self.assertEqual(rep.summary["mismatch"], 1)
        self.assertTrue(rep.has_mismatch)
        ok_only = make_report(results=[ResultItem("t.c", "ok", "proof")])
        self.assertFalse(ok_only.has_mismatch)

    def test_validate_rejects_missing_schema_version(self):
        d = make_report().to_dict()
        del d["schemaVersion"]
        self.assertTrue(any("schemaVersion" in p for p in validate_report_dict(d)))

    def test_validate_rejects_bad_status_and_confidence(self):
        d = make_report().to_dict()
        d["results"][0]["status"] = "meh"
        d["results"][1]["confidence"] = "vibes"
        problems = validate_report_dict(d)
        self.assertEqual(len(problems), 2)

    def test_from_dict_raises(self):
        with self.assertRaises(ReportValidationError):
            report_from_dict({"schemaVersion": 999})


class HashAndStaleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.doc = self.root / "docs" / "db" / "users.json"
        self.doc.parent.mkdir(parents=True)
        self.doc.write_text('{"openapi": "3.0.0"}')

    def tearDown(self):
        self._tmp.cleanup()

    def test_hashes_are_relative_and_prefixed(self):
        hashes = compute_input_hashes([self.doc], self.root)
        self.assertEqual(list(hashes), ["docs/db/users.json"])
        self.assertTrue(hashes["docs/db/users.json"].startswith("sha256:"))

    def test_stale_detection(self):
        rep = make_report(input_hashes=compute_input_hashes([self.doc], self.root))
        self.assertFalse(is_stale(rep, self.root))
        self.doc.write_text('{"openapi": "3.0.1"}')
        self.assertTrue(is_stale(rep, self.root))

    def test_stale_when_input_deleted(self):
        rep = make_report(input_hashes=compute_input_hashes([self.doc], self.root))
        self.doc.unlink()
        self.assertTrue(is_stale(rep, self.root))


class PathAndIoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_report_paths(self):
        self.assertEqual(
            report_path_for("api", "api", self.root),
            self.root / "docs" / "api" / ".check-report.json",
        )
        self.assertEqual(
            report_path_for("db", "default", self.root),
            self.root / "docs" / "db" / ".check-report.json",
        )
        self.assertEqual(
            report_path_for("db", "main", self.root),
            self.root / "docs" / "db" / "main" / ".check-report.json",
        )

    def test_save_and_load(self):
        rep = make_report()
        path = save_report(rep, self.root)
        self.assertTrue(path.is_file())
        loaded = load_report(path)
        self.assertEqual(loaded.checker, "db-main")
        # file is valid json with trailing newline
        raw = path.read_text()
        self.assertTrue(raw.endswith("\n"))
        json.loads(raw)

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_report(self.root / "nope.json"))


if __name__ == "__main__":
    unittest.main()
