"""Integration tests: generate html × multi-DB docs × check reports.

Covers the acceptance conditions from the impl plan:
- flat docs/db (single DB) keeps its historical output layout
- docs/db/{db_name}/ gets per-DB pages + per-DB ERD, and same-stem tables
  in different DBs no longer overwrite each other (the silent-collision bug)
- a .check-report.json artifact produces a contract-check page; its absence
  changes nothing; a broken artifact must not break generation
"""

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.check.report import (
    CheckReport,
    ResultItem,
    compute_input_hashes,
    save_report,
)
from jsonui_doc_cli.test_doc.generator import generate_html_directory


def table_json(name: str) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": name, "x-table-name": name.lower()},
        "paths": {},
        "components": {"schemas": {name: {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "x-primary-key": True},
                "name": {"type": "string"},
            },
        }}},
    }


class GenerateHtmlChecksTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tests_dir = self.root / "tests"
        self.tests_dir.mkdir()
        # generator requires at least one test file
        (self.tests_dir / "Smoke.test.json").write_text(json.dumps({
            "type": "screen",
            "source": {"layout": "Layouts/Smoke.json"},
            "metadata": {"name": "Smoke"},
            "cases": [{"name": "shows", "steps": [
                {"assert": "visible", "id": "root"}]}],
        }), encoding="utf-8")
        self.docs = self.root / "docs"
        self.out = self.root / "html"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, data: dict):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def generate(self):
        return generate_html_directory(self.tests_dir, self.out)


class FlatSingleDbTests(GenerateHtmlChecksTestBase):
    def test_flat_db_layout_unchanged(self):
        self.write("docs/db/users.json", table_json("Users"))
        self.write("docs/db/orders.json", table_json("Orders"))
        self.generate()
        self.assertTrue((self.out / "db" / "users.html").is_file())
        self.assertTrue((self.out / "db" / "orders.html").is_file())
        self.assertTrue((self.out / "db" / "erd.html").is_file())
        self.assertFalse((self.out / "db" / "contract-check.html").exists())

    def test_no_report_no_check_page_anywhere(self):
        self.write("docs/db/users.json", table_json("Users"))
        self.generate()
        found = list(self.out.rglob("contract-check.html"))
        self.assertEqual(found, [])


class MultiDbTests(GenerateHtmlChecksTestBase):
    def setUp(self):
        super().setUp()
        # Two databases, BOTH containing users.json (the collision case)
        self.write("docs/db/main/users.json", table_json("MainUsers"))
        self.write("docs/db/main/reservations.json", table_json("Reservations"))
        self.write("docs/db/analytics/users.json", table_json("AnalyticsUsers"))

    def test_per_db_pages_no_silent_overwrite(self):
        self.generate()
        main_users = self.out / "db" / "main" / "users.html"
        ana_users = self.out / "db" / "analytics" / "users.html"
        self.assertTrue(main_users.is_file())
        self.assertTrue(ana_users.is_file())
        self.assertIn("MainUsers", main_users.read_text())
        self.assertIn("AnalyticsUsers", ana_users.read_text())

    def test_per_db_erd(self):
        self.generate()
        self.assertTrue((self.out / "db" / "main" / "erd.html").is_file())
        self.assertTrue((self.out / "db" / "analytics" / "erd.html").is_file())
        # no merged top-level db ERD when everything lives in named DBs
        self.assertFalse((self.out / "db" / "erd.html").exists())

    def test_index_lists_both_dbs(self):
        self.generate()
        index = (self.out / "index.html").read_text()
        self.assertIn("DB: main", index)
        self.assertIn("DB: analytics", index)


class CheckReportPageTests(GenerateHtmlChecksTestBase):
    def _make_report(self, kind: str, name: str, mismatch: bool,
                     inputs: list[Path]) -> CheckReport:
        results = [ResultItem("t.ok", "ok", "proof")]
        if mismatch:
            results.append(ResultItem(
                "reservations.fee", "mismatch", "proof",
                expected="INT NULL", actual="INT NOT NULL",
                message="docs say nullable"))
        return CheckReport(
            checker=f"check-{name}",
            target_kind=kind,
            target_name=name,
            target_extra={"dialect": "mysql"} if kind == "db" else {},
            input_hashes=compute_input_hashes(inputs, self.root),
            results=results,
        )

    def test_db_report_renders_page_and_sidebar_entry(self):
        doc = self.write("docs/db/users.json", table_json("Users"))
        save_report(self._make_report("db", "default", True, [doc]), self.root)
        self.generate()
        page = self.out / "db" / "contract-check.html"
        self.assertTrue(page.is_file())
        content = page.read_text()
        self.assertIn("ズレが検出", content)
        self.assertIn("INT NOT NULL", content)
        # linked from the table page sidebar
        users_html = (self.out / "db" / "users.html").read_text()
        self.assertIn("contract-check.html", users_html)

    def test_named_db_report(self):
        doc = self.write("docs/db/main/users.json", table_json("Users"))
        save_report(self._make_report("db", "main", False, [doc]), self.root)
        self.generate()
        self.assertTrue(
            (self.out / "db" / "main" / "contract-check.html").is_file())

    def test_api_report_with_stale_flag(self):
        api = self.write("docs/api/service.json", {
            "openapi": "3.0.3",
            "info": {"title": "Service"},
            "paths": {"/ping": {"get": {"responses": {
                "200": {"description": "ok"}}}}},
        })
        save_report(self._make_report("api", "api", False, [api]), self.root)
        # mutate the doc AFTER the report → stale
        api.write_text(api.read_text().replace("Service", "Service2"))
        self.generate()
        content = (self.out / "api" / "contract-check.html").read_text()
        self.assertIn("古い可能性", content)

    def test_broken_report_does_not_break_generation(self):
        self.write("docs/db/users.json", table_json("Users"))
        report_path = self.root / "docs" / "db" / ".check-report.json"
        report_path.write_text("{ this is not json")
        self.generate()  # must not raise
        self.assertTrue((self.out / "db" / "users.html").is_file())
        self.assertFalse((self.out / "db" / "contract-check.html").exists())


if __name__ == "__main__":
    unittest.main()
