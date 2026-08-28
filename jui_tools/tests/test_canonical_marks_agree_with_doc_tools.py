"""`jui build` and `jsonui-doc` must expand `@canonical` to the same list.

The two tools read the same spec fields for different purposes — one
generates repository stubs, the other validates and renders the doc site — so
a mark that expanded to one signature here and another there would put
generated code out of step with the document describing it, in a way neither
tool could detect on its own.

Hence one implementation in `shared/core/openapi_canonical.py` and two thin
adapters. This is the test that keeps it one: it resolves the same fixture
through both entry points and compares. It fails the moment either tool grows
its own copy of the walk, the lookup, the naming rule, or the directory
search — each of which existed as a second copy before this feature and was
removed by it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "jui_tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "jui_tools"))

from jui_cli.core.spec_extractor import (  # noqa: E402
    CanonicalMarkError, extract_screen_spec,
)

# document_tools is a separate distribution; when it is not beside this
# checkout the cross-tool half is skipped rather than silently dropped.
HAVE_DOC_TOOLS = (REPO_ROOT / "document_tools").is_dir()
if HAVE_DOC_TOOLS and str(REPO_ROOT / "document_tools") not in sys.path:
    sys.path.insert(1, str(REPO_ROOT / "document_tools"))
HAVE_DOC_TOOLS = HAVE_DOC_TOOLS and importlib.util.find_spec(
    "jsonui_doc_cli") is not None

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {"/api/venues/{venue_id}/items": {"get": {
        "parameters": [
            {"name": "venue_id", "in": "path", "required": True,
             "schema": {"type": "string"}},
            {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            {"name": "tags", "in": "query",
             "schema": {"type": "array", "items": {"type": "string"}}},
        ],
        "responses": {"200": {"content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/ItemListResponse"}}}}},
    }}},
    "components": {"schemas": {"ItemListResponse": {"type": "object"}}},
}

METHOD = {
    "name": "getVenueItems",
    "endpoint": "GET /api/venues/{venueId}/items",     # spelt the spec's way
    "params": ["@canonical", {"name": "onProgress", "type": "((Int) -> Void)?"}],
    "returnType": "@canonical.wire",
    "isAsync": True,
}

SPEC = {
    "type": "screen",
    "metadata": {"name": "VenueDetail", "description": "Fixture.",
                 "screen": "venue_detail"},
    "dataFlow": {"repositories": [
        {"name": "VenueRepository", "methods": [METHOD]}]},
}


class BothToolsAgreeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "docs" / "screens").mkdir(parents=True)
        self.spec_path = self.root / "docs" / "screens" / "b.spec.json"
        self.spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
        (self.root / "jui.config.json").write_text(
            json.dumps({"spec": {"canonical_param_case": "camelCase"}}),
            encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def build_side(self):
        spec = extract_screen_spec(json.loads(self.spec_path.read_text()),
                                   self.spec_path)
        m = spec.repositories[0].methods[0]
        return [(p.name, p.type) for p in m.params], m.return_type

    def doc_side(self):
        from jsonui_doc_cli.spec_doc.validator import (
            SpecValidationResult, SpecValidator,
        )
        data = json.loads(self.spec_path.read_text())
        v = SpecValidator()
        v._spec_file_path = self.spec_path
        result = SpecValidationResult()
        v._resolve_canonical_marks(data, result)
        self.assertEqual([m.message for m in result.errors], [])
        m = data["dataFlow"]["repositories"][0]["methods"][0]
        return [(p["name"], p["type"]) for p in m["params"]], m["returnType"]

    def test_the_build_side_resolves_the_mark(self):
        params, return_type = self.build_side()
        self.assertEqual(params, [
            ("venueId", "String"),        # required in the document
            ("limit", "Int?"),
            ("tags", "[String]?"),
            ("onProgress", "((Int) -> Void)?"),
        ])
        self.assertEqual(return_type, "ItemListResponse")

    @unittest.skipUnless(HAVE_DOC_TOOLS, "document_tools not importable here")
    def test_both_tools_produce_the_same_signature(self):
        self.assertEqual(self.build_side(), self.doc_side())

    def test_a_spec_spelt_path_still_finds_the_operation(self):
        """`{venueId}` against the canon's `{venue_id}`: a finding about the
        declaration, not a reason to miss the operation it obviously names."""
        params, _ = self.build_side()
        self.assertIn("venueId", [p for p, _t in params])


class UnexpandedMarksAreLoudTests(unittest.TestCase):
    """Forgetting to thread the context must not generate an empty signature.

    This is the failure the rest of this codebase keeps finding in other
    shapes: a check or a value that silently shrinks to nothing and leaves a
    result indistinguishable from one that had nothing to say.
    """

    def test_no_path_means_an_error_not_an_empty_parameter_list(self):
        with self.assertRaises(CanonicalMarkError) as caught:
            extract_screen_spec(json.loads(json.dumps(SPEC)))
        self.assertIn("needs the spec's path", str(caught.exception))

    def test_an_unresolvable_endpoint_is_an_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "api").mkdir(parents=True)
            (root / "docs" / "api" / "s.json").write_text(
                json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
            (root / "jui.config.json").write_text("{}", encoding="utf-8")
            (root / "docs" / "screens").mkdir(parents=True)
            p = root / "docs" / "screens" / "b.spec.json"
            p.write_text(json.dumps(SPEC), encoding="utf-8")
            with self.assertRaises(CanonicalMarkError) as caught:
                extract_screen_spec(json.loads(p.read_text()), p)
            self.assertIn("not declared in any OpenAPI document",
                          str(caught.exception))

    def test_a_spec_with_no_marks_needs_no_canon_at_all(self):
        """The false-positive boundary: this must not become a new dependency
        for every project that does not use the feature."""
        plain = json.loads(json.dumps(SPEC))
        m = plain["dataFlow"]["repositories"][0]["methods"][0]
        m["params"] = [{"name": "venueId", "type": "String"}]
        m["returnType"] = "ItemList"
        spec = extract_screen_spec(plain)          # no path, no canon, no error
        self.assertEqual(
            [p.name for p in spec.repositories[0].methods[0].params],
            ["venueId"])


if __name__ == "__main__":
    unittest.main()
