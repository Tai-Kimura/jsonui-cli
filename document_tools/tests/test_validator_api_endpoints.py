"""Tests for the spec endpoint <-> API canonical (OpenAPI) check.

Design source: docs/plans/2026-08-24-spec-endpoint-canonical-check-design.md.

The check runs through validate_file() because it needs the spec's location
to find jui.config.json and, through it, api_directory. A spec validated
without a path on disk (validate_data) has no canonical to compare against
and is therefore left alone — that is the structural opt-in, and it is
asserted here rather than assumed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonui_doc_cli.spec_doc.validator import SpecValidator

CANONICAL = {
    "openapi": "3.0.0",
    "info": {"title": "Canonical", "version": "1.0.0"},
    "paths": {
        "/api/items": {"get": {}, "post": {}},
        "/api/items/{item_id}": {"get": {}, "put": {}},
        "/api/items/{item_id}/notes": {"post": {}},
    },
}


def _spec(*, methods=None, api_endpoints=None):
    data_flow = {
        "viewModel": {"description": "VM", "methods": [], "vars": []},
    }
    if methods is not None:
        data_flow["repositories"] = [{
            "name": "ItemRepository",
            "methods": methods,
        }]
    if api_endpoints is not None:
        data_flow["apiEndpoints"] = api_endpoints
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "ItemDetail",
            "displayName": "Item detail",
            "description": "Item detail screen.",
            "layoutFile": "item_detail",
        },
        "structure": {"components": [], "layout": {}},
        "dataFlow": data_flow,
        "stateManagement": {"uiVariables": [], "eventHandlers": []},
    }


def _method(name, endpoint):
    return {"name": name, "returnType": "Item", "endpoint": endpoint}


class ApiEndpointCanonicalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "screens").mkdir(parents=True)
        (self.root / "jui.config.json").write_text(
            json.dumps({
                "spec_directory": "docs/screens",
                "api_directory": "docs/api",
            }),
            encoding="utf-8",
        )
        self._write_canonical(CANONICAL)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_canonical(self, doc, filename="canonical.json"):
        (self.root / "docs" / "api" / filename).write_text(
            json.dumps(doc), encoding="utf-8"
        )

    def _validate(self, spec, *, validator=None):
        path = self.root / "docs" / "screens" / "item_detail.spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return (validator or SpecValidator()).validate_file(path)

    def _endpoint_warnings(self, result):
        return [
            w for w in result.warnings
            if "Endpoint" in w.message or "endpoint" in w.message
        ]

    def test_matching_endpoint_is_clean(self):
        result = self._validate(_spec(methods=[
            _method("fetchItem", "GET /api/items/{item_id}"),
            _method("addNote", "POST /api/items/{item_id}/notes"),
        ]))
        self.assertEqual([], self._endpoint_warnings(result))

    def test_parameter_spelling_difference_warns_with_both_spellings(self):
        result = self._validate(_spec(methods=[
            _method("fetchItem", "GET /api/items/{itemId}"),
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("{itemId}", warnings[0].message)
        self.assertIn("{item_id}", warnings[0].message)
        self.assertIn("methods[0].endpoint", warnings[0].path)

    def test_colon_parameter_notation_warns_against_canonical(self):
        result = self._validate(_spec(methods=[
            _method("fetchItem", "GET /api/items/:itemId"),
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn(":itemId", warnings[0].message)
        self.assertIn("{item_id}", warnings[0].message)

    def test_unknown_path_warns(self):
        result = self._validate(_spec(methods=[
            _method("fetchCrate", "GET /api/crates/{crate_id}"),
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("not declared in any OpenAPI document", warnings[0].message)

    def test_known_path_with_undeclared_verb_lists_declared_verbs(self):
        result = self._validate(_spec(methods=[
            _method("deleteItem", "DELETE /api/items/{item_id}"),
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("not for DELETE", warnings[0].message)
        self.assertIn("GET, PUT", warnings[0].message)

    def test_non_http_transport_declaration_is_left_alone(self):
        # Realtime-database / socket / GraphQL declarations use the same
        # field and are legal — the OpenAPI documents do not describe them.
        result = self._validate(_spec(methods=[
            _method("observeStates", "RTDB onValue(item_states/{uuid})"),
            _method("subscribe", "WS /ws/items"),
        ]))
        self.assertEqual([], self._endpoint_warnings(result))

    def test_query_string_is_ignored_when_matching(self):
        result = self._validate(_spec(methods=[
            _method("listItems", "GET /api/items?limit=20"),
        ]))
        self.assertEqual([], self._endpoint_warnings(result))

    def test_api_endpoints_section_is_checked_too(self):
        result = self._validate(_spec(api_endpoints=[
            {"path": "/api/items/{itemId}", "method": "GET"},
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("dataFlow.apiEndpoints[0]", warnings[0].path)

    def test_project_without_api_documents_is_skipped(self):
        for doc in (self.root / "docs" / "api").iterdir():
            doc.unlink()
        result = self._validate(_spec(methods=[
            _method("fetchCrate", "GET /api/crates/{crate_id}"),
        ]))
        # Updated: this used to assert silence. Silence here compared nothing
        # and looked exactly like a project whose routes all match — the
        # warning count simply dropped to zero. What the test is really about
        # is that no *route* finding comes from this path, which is what it
        # asserts now.
        warnings = self._endpoint_warnings(result)
        self.assertTrue(all("were not checked" in w.message for w in warnings),
                        [w.message for w in warnings])

    def test_non_openapi_json_under_api_directory_is_ignored(self):
        for doc in (self.root / "docs" / "api").iterdir():
            doc.unlink()
        (self.root / "docs" / "api" / ".check-report.json").write_text(
            json.dumps({"paths": {"/api/items": {"get": {}}}}), encoding="utf-8"
        )
        result = self._validate(_spec(methods=[
            _method("fetchItem", "GET /api/items/{item_id}"),
        ]))
        # Updated: this used to assert silence. Silence here compared nothing
        # and looked exactly like a project whose routes all match — the
        # warning count simply dropped to zero. What the test is really about
        # is that no *route* finding comes from this path, which is what it
        # asserts now.
        warnings = self._endpoint_warnings(result)
        self.assertTrue(all("were not checked" in w.message for w in warnings),
                        [w.message for w in warnings])

    def test_spec_validated_without_a_path_has_nothing_to_compare(self):
        result = SpecValidator().validate_data(_spec(methods=[
            _method("fetchCrate", "GET /api/crates/{crate_id}"),
        ]))
        # Updated: this used to assert silence. Silence here compared nothing
        # and looked exactly like a project whose routes all match — the
        # warning count simply dropped to zero. What the test is really about
        # is that no *route* finding comes from this path, which is what it
        # asserts now.
        warnings = self._endpoint_warnings(result)
        self.assertTrue(all("were not checked" in w.message for w in warnings),
                        [w.message for w in warnings])

    def test_canonical_index_is_cached_per_api_directory(self):
        validator = SpecValidator()
        spec = _spec(methods=[_method("fetchItem", "GET /api/items/{itemId}")])
        first = self._validate(spec, validator=validator)
        # Deleting the documents must not change the second verdict: the
        # index was already read once for this api_directory.
        for doc in (self.root / "docs" / "api").iterdir():
            doc.unlink()
        second = self._validate(spec, validator=validator)
        self.assertEqual(1, len(self._endpoint_warnings(first)))
        self.assertEqual(1, len(self._endpoint_warnings(second)))

    def test_yaml_canonical_is_read_when_pyyaml_is_available(self):
        for doc in (self.root / "docs" / "api").iterdir():
            doc.unlink()
        (self.root / "docs" / "api" / "canonical.yaml").write_text(
            "openapi: 3.0.0\npaths:\n  /api/items/{item_id}:\n    get: {}\n",
            encoding="utf-8",
        )
        result = self._validate(_spec(methods=[
            _method("fetchItem", "GET /api/items/{itemId}"),
        ]))
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("{item_id}", warnings[0].message)

    def test_unreadable_yaml_skips_the_check_instead_of_reporting_absence(self):
        (self.root / "docs" / "api" / "extra.yaml").write_text(
            "openapi: 3.0.0\npaths: {}\n", encoding="utf-8"
        )
        spec = _spec(methods=[
            _method("fetchCrate", "GET /api/crates/{crate_id}"),
        ])
        validator = SpecValidator()
        with mock.patch.dict(sys.modules, {"yaml": None}):
            result = self._validate(spec, validator=validator)
        warnings = self._endpoint_warnings(result)
        self.assertEqual(1, len(warnings))
        self.assertIn("skipped", warnings[0].message)
        self.assertIn("PyYAML", warnings[0].message)
        # The route that could not be checked is NOT reported as missing.
        self.assertNotIn("not declared", warnings[0].message)

    def test_yaml_skip_notice_is_reported_once_per_validator(self):
        (self.root / "docs" / "api" / "extra.yaml").write_text(
            "openapi: 3.0.0\npaths: {}\n", encoding="utf-8"
        )
        spec = _spec(methods=[_method("fetchCrate", "GET /api/crates/{id}")])
        validator = SpecValidator()
        with mock.patch.dict(sys.modules, {"yaml": None}):
            first = self._validate(spec, validator=validator)
            second = self._validate(spec, validator=validator)
        self.assertEqual(1, len(self._endpoint_warnings(first)))
        self.assertEqual([], self._endpoint_warnings(second))


if __name__ == "__main__":
    unittest.main()
