"""Regression: doc-html-generation-swallows-page-errors.

A page that failed to render used to vanish silently — exit 0, nav still
linking to it, and nobody the wiser until a human clicked the dead link.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.test_doc import (
    generate_html_directory,
    get_page_failures,
    get_pages_written,
)
from jsonui_doc_cli.test_doc.html.schema import (
    SchemaExtensionError,
    _render_custom_validations,
)


def _db_doc(table: str, custom_validations) -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": table, "x-table-name": table},
        "components": {
            "schemas": {
                table: {
                    "type": "object",
                    "x-custom-validations": custom_validations,
                    "properties": {"id": {"type": "integer"}},
                }
            }
        },
    }


class PageFailureAccountingTests(unittest.TestCase):
    def _site(self, tmp: Path, *, broken: bool) -> Path:
        tests_dir = tmp / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "sample.test.json").write_text(
            json.dumps({"name": "sample", "cases": []}), encoding="utf-8"
        )
        db_dir = tmp / "db"
        db_dir.mkdir()
        (db_dir / "ok_table.json").write_text(
            json.dumps(_db_doc("ok_table", [
                {"name": "n", "conditions": "c", "description": "d"}
            ])),
            encoding="utf-8",
        )
        bad = ["id IS NOT NULL"] if broken else [
            {"name": "n", "conditions": "c", "description": "d"}
        ]
        (db_dir / "broken_table.json").write_text(
            json.dumps(_db_doc("broken_table", bad)), encoding="utf-8"
        )
        out = tmp / "html"
        generate_html_directory(tests_dir, out, "repro", [db_dir])
        return out

    def test_failure_is_recorded_not_swallowed(self):
        with TemporaryDirectory() as td:
            self._site(Path(td), broken=True)
            failures = get_page_failures()
            self.assertEqual(len(failures), 1, failures)
            self.assertEqual(failures[0]["kind"], "API doc")

    def test_failure_names_the_input_file(self):
        # The display name alone ("broken_table") does not say which of the
        # 48 files to open.
        with TemporaryDirectory() as td:
            self._site(Path(td), broken=True)
            source = get_page_failures()[0]["source"]
            self.assertIsNotNone(source)
            self.assertTrue(source.endswith("broken_table.json"), source)

    def test_placeholder_keeps_the_link_alive(self):
        with TemporaryDirectory() as td:
            out = self._site(Path(td), broken=True)
            page = out / "db" / "broken_table.html"
            self.assertTrue(page.exists(), "nav links here; it must not 404")
            body = page.read_text(encoding="utf-8")
            self.assertIn("could not be generated", body)
            self.assertIn("x-custom-validations", body)

    def test_index_still_links_to_the_failed_page(self):
        with TemporaryDirectory() as td:
            out = self._site(Path(td), broken=True)
            index = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("db/broken_table.html", index)

    def test_clean_input_records_nothing(self):
        with TemporaryDirectory() as td:
            self._site(Path(td), broken=False)
            self.assertEqual(get_page_failures(), [])

    def test_page_count_covers_every_written_page(self):
        # The old count reported the test pages only — a smaller number than
        # the lines printed above it, so it could not signal a gap.
        with TemporaryDirectory() as td:
            out = self._site(Path(td), broken=False)
            on_disk = len(list(out.rglob("*.html")))
            self.assertEqual(get_pages_written(), on_disk)
            self.assertGreater(on_disk, 1)

    def test_state_resets_between_runs(self):
        with TemporaryDirectory() as td:
            self._site(Path(td), broken=True)
            self.assertEqual(len(get_page_failures()), 1)
        with TemporaryDirectory() as td:
            self._site(Path(td), broken=False)
            self.assertEqual(get_page_failures(), [])


class CustomValidationDiagnosticTests(unittest.TestCase):
    def test_string_entry_names_key_index_and_expected_shape(self):
        with self.assertRaises(SchemaExtensionError) as ctx:
            _render_custom_validations(["id IS NOT NULL"], "broken_table")
        msg = str(ctx.exception)
        self.assertIn("x-custom-validations[0]", msg)
        self.assertIn("broken_table", msg)
        self.assertIn("{name, conditions, description}", msg)
        # the raw AttributeError text is what this replaces
        self.assertNotIn("object has no attribute", msg)

    def test_non_list_value_is_diagnosed_too(self):
        with self.assertRaises(SchemaExtensionError) as ctx:
            _render_custom_validations({"name": "n"}, "t")
        self.assertIn("expected a list", str(ctx.exception))

    def test_valid_entries_render(self):
        out = _render_custom_validations(
            [{"name": "n", "conditions": "c", "description": "d"}], "t"
        )
        self.assertTrue(any("custom-validations" in line for line in out))


if __name__ == "__main__":
    unittest.main()
