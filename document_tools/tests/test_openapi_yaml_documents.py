"""jsonui-doc's readers of an OpenAPI document take YAML as they take JSON (ticket 2026-10-23-jsonui-test-mock-
generate-yaml-traceback, its family table): `generate html` (docs/api, docs/db), the openapi-diff check and the db-schema
check took *.json only and passed a YAML document by without a word. A YAML document without PyYAML is said once,
through the run's warning tally.
"""
from __future__ import annotations

import builtins
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from jsonui_doc_cli import run_log
from jsonui_doc_cli.check.db_schema.doc_parser import parse_db_docs
from jsonui_doc_cli.check.openapi_diff import load_doc_side
from jsonui_doc_cli.test_doc.html.swagger import is_swagger_file, openapi_files, parse_swagger_file

API = {"openapi": "3.0.3", "info": {"title": "Items", "version": "1"},
       "paths": {"/api/items": {"get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}}}}}
TABLE = {"openapi": "3.0.3", "info": {"title": "users", "version": "1", "x-table-name": "users"},
         "components": {"schemas": {"User": {"type": "object", "properties": {"id": {"type": "string"}}}}}}


class YamlDocuments(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel, data, as_yaml=True):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(data) if as_yaml else json.dumps(data), encoding="utf-8")
        return p

    def test_generate_html_finds_and_parses_a_yaml_document(self):
        y = self._write("docs/api/items.yaml", API)
        j = self._write("docs/api/more.json", API, as_yaml=False)
        self._write("docs/api/.hidden.yml", API)
        self.assertEqual(openapi_files(self.root / "docs/api"), [y, j])   # sorted, the dot-file left out
        self.assertTrue(is_swagger_file(y))
        self.assertEqual(parse_swagger_file(y), API)

    def test_the_openapi_diff_check_reads_yaml(self):
        self._write("docs/api/items.yml", API)
        spec, files = load_doc_side(self.root / "docs/api")
        self.assertEqual([f.name for f in files], ["items.yml"])
        self.assertEqual(len(spec.operations), 1)

    def test_the_db_schema_check_reads_a_yaml_table(self):
        self._write("docs/db/users.yaml", TABLE)
        self.assertEqual(list(parse_db_docs(self.root / "docs/db")), ["users"])

    def test_without_pyyaml_a_yaml_document_is_said_through_the_tally(self):
        y = self._write("docs/api/items.yaml", API)
        real = builtins.__import__

        def fake(name, *a, **k):
            if name == "yaml" or name.startswith("yaml."):
                raise ImportError("No module named 'yaml'")
            return real(name, *a, **k)
        run_log.reset()
        builtins.__import__ = fake
        try:
            self.assertFalse(is_swagger_file(y))
        finally:
            builtins.__import__ = real
        said = run_log.emitted()
        self.assertEqual(said, [f"warning: {y}: a YAML OpenAPI document needs PyYAML (pip3 install pyyaml), or give its JSON form"])
        run_log.reset()


if __name__ == "__main__":
    unittest.main()
