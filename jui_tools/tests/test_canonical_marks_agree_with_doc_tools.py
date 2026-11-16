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


class BothToolsAgreeInASplitTreeTests(unittest.TestCase):
    """The fixture above cannot see the failure this class is about.

    It builds a single tree, so the two tools reach the same config no matter
    where they are invoked from — and the claim "a fourth copy of the
    resolution makes this red" was false for exactly the case that produced
    one. In a split tree the specs sit in a documentation tree and the build
    config in the app, and the two commands run from different directories:
    `jui build` from the app, `jsonui-doc` from the repository root. Each
    reached a different config for the same spec, and only one of them
    declared the naming convention.

    Measured on the real layout: `camelCase` from the app, nothing from the
    root, in the same tree. Reported by the lane that adopted the feature,
    after the release that claimed to have unified the resolution — it had
    unified expansion, and left the config lookup with two answers.

    So the specs' ancestry is what identifies the face, and a stub config on
    that ancestry names its owner with `extends`. The consumers were already
    writing that pointer as a human-readable `_note`.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        # The repository root holds the canon and declares no convention.
        (self.root / "jui.config.json").write_text(
            json.dumps({"api_directory": "docs/api"}), encoding="utf-8")
        # The app holds the build config, and the convention with it.
        self.app = self.root / "web"
        self.app.mkdir()
        (self.app / "jui.config.json").write_text(json.dumps(
            {"api_directory": "../docs/api",
             "spec": {"canonical_param_case": "camelCase"}}), encoding="utf-8")
        # The specs sit in the documentation tree, beside a stub that names
        # the app config as its owner.
        specs = self.root / "docs" / "web" / "screens" / "json"
        specs.mkdir(parents=True)
        (specs.parent.parent / "jui.config.json").write_text(
            json.dumps({"extends": "../../web/jui.config.json"}),
            encoding="utf-8")
        self.spec_path = specs / "s.spec.json"
        self.spec_path.write_text(json.dumps(SPEC), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _in(self, cwd, fn):
        import os
        previous = os.getcwd()
        os.chdir(cwd)
        try:
            return fn()
        finally:
            os.chdir(previous)

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

    @unittest.skipUnless(HAVE_DOC_TOOLS, "document_tools not importable here")
    def test_the_two_tools_agree_from_their_own_directories(self):
        """Each run from where it is actually run from. This is the failure:
        both halves were individually defensible and disagreed."""
        build = self._in(self.app, self.build_side)
        doc = self._in(self.root, self.doc_side)
        self.assertEqual(build, doc)

    @unittest.skipUnless(HAVE_DOC_TOOLS, "document_tools not importable here")
    def test_neither_tool_depends_on_where_it_was_invoked(self):
        """The stronger property, and the one that stops the next variant:
        the spec decides, not the shell."""
        for cwd in (self.root, self.app, self.root / "docs"):
            self.assertEqual(self._in(cwd, self.build_side),
                             self._in(cwd, self.doc_side))
            self.assertEqual(self._in(cwd, self.build_side),
                             self._in(self.app, self.build_side))

    def test_the_convention_is_the_app_config_from_anywhere(self):
        params, _rt = self._in(self.root, self.build_side)
        self.assertEqual([n for n, _t in params][:1], ["venueId"])
