"""`@canonical` — the spec references the API canon instead of copying it.

Census that produced the design (four consumer faces, 2026-08-28): 320
dataFlow methods name an endpoint, 318 resolve against the project's OpenAPI
documents, and 205 of those (64%) carry a parameter list derivable from the
operation. 138 of the 205 differ from the canon by naming convention alone.

Three properties this pins, each of which a plausible implementation gets
wrong:

1. Absence is not the mark. `params` is already absent on five declarations
   and means "no parameters" there; only a written mark asks for resolution.
2. An unresolvable mark is an error, never an empty list. A silent fallback
   generates a method with no arguments on three platforms.
3. `returnType` takes `@canonical.wire`, not `@canonical`. A spec's return
   type is the domain type and the canon's is the wire type; the corpus has
   `[ItemSummary]` against `ItemSearchResponse`, and lifting the wire name over
   the domain one would be wrong 21 times out of 72 on one face alone.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli import shared_core
from jsonui_doc_cli.spec_doc.validator import SpecValidator, SpecValidationResult

canon = shared_core.openapi_canonical()

SWAGGER = {
    "openapi": "3.0.3",
    "paths": {
        "/api/user/bookmarks": {
            "get": {
                "parameters": [
                    {"name": "limit", "in": "query", "required": False,
                     "schema": {"type": "integer"}},
                    {"name": "category_id", "in": "query",
                     "schema": {"type": "string"}},
                ],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/BookmarkListResponse"}}}}},
            },
            "post": {
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/BookmarkCreate"}}}},
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"type": "object"}}}}},   # inline: no name to lift
            },
        },
        "/api/venues/{venue_id}": {
            "get": {"parameters": [
                {"name": "venue_id", "in": "path", "required": True,
                 "schema": {"type": "string"}}],
                "responses": {"200": {"description": "ok"}}},
        },
    },
    "components": {"schemas": {
        "BookmarkListResponse": {"type": "object"},
        "BookmarkCreate": {"type": "object",
                           "required": ["item_uuid"],
                           "properties": {"item_uuid": {"type": "string"},
                                          "note": {"type": "string"}}},
    }},
}


def _spec(method: dict) -> dict:
    return {
        "type": "screen",
        "metadata": {"name": "Fixture", "description": "Fixture.",
                     "screen": "fixture"},
        "dataFlow": {"repositories": [
            {"name": "UserRepository", "methods": [method]}]},
    }


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "api").mkdir(parents=True)
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(SWAGGER), encoding="utf-8")
        (self.root / "docs" / "screens").mkdir(parents=True)
        self.spec_path = self.root / "docs" / "screens" / "f.spec.json"
        # The canon is located through `jui.config.json` `api_directory`, the
        # same directory `jui` resolves; a project without one has no canon.
        self.config(None)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, spec_section=None):
        body = {"spec": spec_section} if spec_section else {}
        (self.root / "jui.config.json").write_text(json.dumps(body),
                                                   encoding="utf-8")

    def resolve(self, method: dict):
        data = _spec(method)
        self.spec_path.write_text(json.dumps(data), encoding="utf-8")
        v = SpecValidator()
        v._spec_file_path = self.spec_path
        result = SpecValidationResult()
        v._resolve_canonical_marks(data, result)
        resolved = data["dataFlow"]["repositories"][0]["methods"][0]
        return resolved, [m.message for m in result.errors]


class ParamsTests(_Fixture):
    def test_the_mark_expands_to_the_operations_parameters(self):
        m, errs = self.resolve({"name": "getBookmarks",
                                "endpoint": "GET /api/user/bookmarks",
                                "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]],
                         ["limit", "category_id"])
        # Not required in the document, so optional in the signature.
        self.assertEqual([p["type"] for p in m["params"]], ["Int?", "String?"])

    def test_request_body_properties_are_parameters_too(self):
        """The half a first census missed, and it changed the numbers."""
        m, errs = self.resolve({"name": "addBookmark",
                                "endpoint": "POST /api/user/bookmarks",
                                "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]],
                         ["item_uuid", "note"])
        # `required: [item_uuid]` on a required body, `note` is not.
        self.assertEqual([p["type"] for p in m["params"]], ["String", "String?"])

    def test_a_hand_written_entry_sits_beside_the_mark(self):
        """The whole reason the two mix: a client-side argument no OpenAPI
        document will ever declare."""
        m, errs = self.resolve({
            "name": "getBookmarks", "endpoint": "GET /api/user/bookmarks",
            "params": ["@canonical",
                       {"name": "onProgress", "type": "((Int) -> Void)?"}]})
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]],
                         ["limit", "category_id", "onProgress"])

    def test_the_mark_expands_where_it_sits(self):
        m, _ = self.resolve({
            "name": "getBookmarks", "endpoint": "GET /api/user/bookmarks",
            "params": [{"name": "token", "type": "String"}, "@canonical"]})
        self.assertEqual([p["name"] for p in m["params"]][0], "token")

    def test_a_hand_written_name_replaces_the_canonical_one(self):
        """Two parameters of one name is not a signature any platform emits."""
        m, _ = self.resolve({
            "name": "getBookmarks", "endpoint": "GET /api/user/bookmarks",
            "params": ["@canonical", {"name": "limit", "type": "Int"}]})
        names = [p["name"] for p in m["params"]]
        self.assertEqual(names.count("limit"), 1)
        self.assertEqual([p for p in m["params"] if p["name"] == "limit"][0]["type"],
                         "Int")

    def test_a_collision_modulo_case_is_still_a_collision(self):
        m, _ = self.resolve({
            "name": "getVenue", "endpoint": "GET /api/venues/{venue_id}",
            "params": ["@canonical", {"name": "venueId", "type": "String"}]})
        self.assertEqual([p["name"] for p in m["params"]], ["venueId"])


class CaseConventionTests(_Fixture):
    """43% of the corpus differs from the canon by nothing but this."""

    def test_the_canons_spelling_is_the_default(self):
        self.config(None)
        m, _ = self.resolve({"name": "getVenue",
                             "endpoint": "GET /api/venues/{venue_id}",
                             "params": "@canonical"})
        self.assertEqual([p["name"] for p in m["params"]], ["venue_id"])

    def test_camel_case_is_opt_in(self):
        self.config({"canonical_param_case": "camelCase"})
        m, _ = self.resolve({"name": "getVenue",
                             "endpoint": "GET /api/venues/{venue_id}",
                             "params": "@canonical"})
        self.assertEqual([p["name"] for p in m["params"]], ["venueId"])

    def test_snake_case_can_be_asked_for_explicitly(self):
        self.config({"canonical_param_case": "snake_case"})
        m, _ = self.resolve({"name": "getBookmarks",
                             "endpoint": "GET /api/user/bookmarks",
                             "params": "@canonical"})
        self.assertEqual([p["name"] for p in m["params"]],
                         ["limit", "category_id"])


class ReturnTypeTests(_Fixture):
    def test_canonical_wire_lifts_the_response_schema_name(self):
        m, errs = self.resolve({"name": "getBookmarks",
                                "endpoint": "GET /api/user/bookmarks",
                                "returnType": "@canonical.wire"})
        self.assertEqual(errs, [])
        self.assertEqual(m["returnType"], "BookmarkListResponse")

    def test_plain_canonical_is_not_a_return_type_mark(self):
        """A spec's return type is the domain type. `[ItemSummary]` against
        `ItemSearchResponse` is a real pair in the corpus, and neither is
        wrong — so the wire type is only ever taken when asked for by name."""
        m, errs = self.resolve({"name": "getBookmarks",
                                "endpoint": "GET /api/user/bookmarks",
                                "returnType": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual(m["returnType"], "@canonical")   # left alone

    def test_an_inline_response_body_has_no_name_to_lift(self):
        m, errs = self.resolve({"name": "addBookmark",
                                "endpoint": "POST /api/user/bookmarks",
                                "returnType": "@canonical.wire"})
        self.assertEqual(len(errs), 1)
        self.assertIn("no name to lift", errs[0])
        self.assertEqual(m["returnType"], "@canonical.wire")


class UnresolvableTests(_Fixture):
    """An unresolved mark is an error. Never an empty list."""

    def test_a_route_the_canon_does_not_declare(self):
        m, errs = self.resolve({"name": "x", "endpoint": "GET /api/nope",
                                "params": "@canonical"})
        self.assertEqual(len(errs), 1)
        self.assertIn("not declared in any OpenAPI document", errs[0])
        self.assertEqual(m["params"], "@canonical")   # not silently emptied

    def test_a_method_the_route_does_not_have(self):
        _m, errs = self.resolve({"name": "x",
                                 "endpoint": "DELETE /api/user/bookmarks",
                                 "params": "@canonical"})
        self.assertIn("not\nfor that method".replace("\n", " "), errs[0])

    def test_no_endpoint_at_all(self):
        _m, errs = self.resolve({"name": "x", "params": "@canonical"})
        self.assertIn("declares no 'endpoint'", errs[0])

    def test_a_non_http_transport_says_so_specifically(self):
        """Legal to declare, impossible to resolve — and the message has to
        distinguish that from a typo, because the fix is different."""
        _m, errs = self.resolve({"name": "x",
                                 "endpoint": "RTDB ui_states/{uuid}",
                                 "params": "@canonical"})
        self.assertIn("not an HTTP route", errs[0])


class AbsenceIsNotTheMarkTests(_Fixture):
    def test_omitting_params_resolves_nothing(self):
        """Five declarations in the corpus omit `params` and mean 'none'."""
        m, errs = self.resolve({"name": "getBookmarks",
                                "endpoint": "GET /api/user/bookmarks"})
        self.assertEqual(errs, [])
        self.assertNotIn("params", m)

    def test_a_written_out_list_is_left_exactly_as_written(self):
        m, errs = self.resolve({
            "name": "getBookmarks", "endpoint": "GET /api/user/bookmarks",
            "params": [{"name": "cursor", "type": "String?"}]})
        self.assertEqual(errs, [])
        self.assertEqual(m["params"], [{"name": "cursor", "type": "String?"}])


class PathNotationTests(unittest.TestCase):
    def test_three_notations_name_one_route(self):
        for written in ("/api/venues/{venue_id}", "/api/venues/{venueId}",
                        "/api/venues/:venueId"):
            self.assertEqual(canon.normalize_path(written), "/api/venues/{}")

    def test_a_query_string_is_not_part_of_the_route(self):
        self.assertEqual(canon.normalize_path("/api/x?limit=1"), "/api/x")


if __name__ == "__main__":
    unittest.main()


class MutedRequiredTests(_Fixture):
    """`schema.required` under a body that is not itself required.

    Zero occurrences across every consumer canon measured (81 + 76 + 119 request
    bodies), so this fixture is fabricated on purpose — a corpus with none of
    a case does not show that the net for it works. Reported by the backend
    lane that read `_operation_params` after being told the wrong thing about
    path renames, and found this on the way past.

    The expansion is correct: `requestBody.required: false` means the caller
    may omit the body, so nothing inside it can be an unconditional argument.
    It is warned about because the reason sits two levels from the symptom —
    "I wrote `required` and it generated `String?`".
    """

    def setUp(self):
        super().setUp()
        doc = json.loads(json.dumps(SWAGGER))
        doc["paths"]["/api/user/bookmarks"]["patch"] = {
            "requestBody": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/BookmarkCreate"}}}},
            "responses": {"200": {"description": "ok"}},
        }
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(doc), encoding="utf-8")

    def resolve_with_warnings(self, method):
        data = _spec(method)
        self.spec_path.write_text(json.dumps(data), encoding="utf-8")
        v = SpecValidator()
        v._spec_file_path = self.spec_path
        result = SpecValidationResult()
        v._resolve_canonical_marks(data, result)
        return (data["dataFlow"]["repositories"][0]["methods"][0],
                [m.message for m in result.errors],
                [m.message for m in result.warnings])

    def test_the_properties_expand_optional(self):
        m, errs, _w = self.resolve_with_warnings({
            "name": "patchBookmark", "endpoint": "PATCH /api/user/bookmarks",
            "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual([p["type"] for p in m["params"]], ["String?", "String?"])

    def test_and_it_says_why(self):
        _m, _e, warns = self.resolve_with_warnings({
            "name": "patchBookmark", "endpoint": "PATCH /api/user/bookmarks",
            "params": "@canonical"})
        self.assertEqual(len(warns), 1)
        self.assertIn("item_uuid", warns[0])
        self.assertIn("requestBody.required", warns[0])

    def test_it_does_not_gate(self):
        """The declaration is legal. Saying so is the whole intervention."""
        _m, errs, _w = self.resolve_with_warnings({
            "name": "patchBookmark", "endpoint": "PATCH /api/user/bookmarks",
            "params": "@canonical"})
        self.assertEqual(errs, [])

    def test_a_required_body_says_nothing(self):
        """The false-positive boundary — 197 of the 276 measured bodies."""
        _m, _e, warns = self.resolve_with_warnings({
            "name": "addBookmark", "endpoint": "POST /api/user/bookmarks",
            "params": "@canonical"})
        self.assertEqual(warns, [])

    def test_an_unmarked_method_says_nothing_either(self):
        """The warning belongs to expansion, not to the document."""
        _m, _e, warns = self.resolve_with_warnings({
            "name": "patchBookmark", "endpoint": "PATCH /api/user/bookmarks",
            "params": [{"name": "itemUuid", "type": "String"}]})
        self.assertEqual(warns, [])


class PathParametersAreArgumentsTests(_Fixture):
    """A path variable is an argument the caller supplies, so it expands.

    Which means **renaming a path variable moves every referencing spec's
    signature** — and that is easy to get backwards, because route matching
    normalizes path-variable spelling away. The same rename is invisible to
    resolution and load-bearing for expansion. I told a lane the opposite; they
    read the function and corrected me.
    """

    def test_a_path_parameter_is_in_the_expansion(self):
        m, errs = self.resolve({"name": "getVenue",
                                "endpoint": "GET /api/venues/{venue_id}",
                                "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]], ["venue_id"])
        self.assertEqual([p["type"] for p in m["params"]], ["String"])

    def test_and_the_case_convention_renames_it(self):
        self.config({"canonical_param_case": "camelCase"})
        m, _e = self.resolve({"name": "getVenue",
                              "endpoint": "GET /api/venues/{venue_id}",
                              "params": "@canonical"})
        self.assertEqual([p["name"] for p in m["params"]], ["venueId"])

    def test_route_matching_ignores_the_spelling_expansion_does_not(self):
        """Both halves in one place, because holding only the first is what
        produced the wrong advice."""
        m, errs = self.resolve({"name": "getVenue",
                                "endpoint": "GET /api/venues/{venueId}",
                                "params": "@canonical"})
        self.assertEqual(errs, [])                       # matched anyway
        self.assertEqual([p["name"] for p in m["params"]], ["venue_id"])


class MisplacedMarkTests(_Fixture):
    """A mark in a section nothing expands must not pass in silence.

    The schema allows the same method shape under `dataFlow.viewModel` as
    under `repositories`, so a mark can be written there. Nothing walked it:
    validation returned PASSED and the marker string survived as the value of
    `params` — a spec that looked converted and was not, which is worse than
    the empty list this module refuses to produce.

    Widening the walk was the other option and is wrong: a ViewModel does not
    call an API directly (specification-rules rule 14), so an endpoint there
    already means a repository is missing. The design question the reporting
    lane declined to decide had been decided; it just was not written down
    where the code could reach it.
    """

    def resolve_vm(self, vm_method, repo_method=None):
        data = {
            "type": "screen",
            "metadata": {"name": "F", "description": "F.", "screen": "f"},
            "dataFlow": {"viewModel": {"methods": [vm_method]}},
        }
        if repo_method is not None:
            data["dataFlow"]["repositories"] = [
                {"name": "R", "methods": [repo_method]}]
        self.spec_path.write_text(json.dumps(data), encoding="utf-8")
        v = SpecValidator()
        v._spec_file_path = self.spec_path
        result = SpecValidationResult()
        v._resolve_canonical_marks(data, result)
        return data, [m.message for m in result.errors]

    def test_a_mark_on_a_viewmodel_method_is_an_error(self):
        data, errs = self.resolve_vm({
            "name": "load", "endpoint": "GET /api/user/bookmarks",
            "params": "@canonical"})
        self.assertEqual(len(errs), 1)
        self.assertIn("does not declare a transport", errs[0])
        # And it is still not expanded — the mark stays visible.
        self.assertEqual(
            data["dataFlow"]["viewModel"]["methods"][0]["params"], "@canonical")

    def test_the_wire_mark_too(self):
        _d, errs = self.resolve_vm({
            "name": "load", "endpoint": "GET /api/user/bookmarks",
            "returnType": "@canonical.wire"})
        self.assertEqual(len(errs), 1)

    def test_a_repository_mark_beside_it_still_expands(self):
        """One misplaced mark must not stop the ones that are placed right."""
        data, errs = self.resolve_vm(
            {"name": "load", "params": "@canonical",
             "endpoint": "GET /api/user/bookmarks"},
            {"name": "fetch", "endpoint": "GET /api/user/bookmarks",
             "params": "@canonical"})
        self.assertEqual(len(errs), 1)
        self.assertEqual(
            [p["name"] for p in
             data["dataFlow"]["repositories"][0]["methods"][0]["params"]],
            ["limit", "category_id"])

    def test_a_viewmodel_method_without_a_mark_says_nothing(self):
        """The false-positive boundary: viewModel methods are ordinary."""
        _d, errs = self.resolve_vm({
            "name": "load", "params": [{"name": "id", "type": "String"}]})
        self.assertEqual(errs, [])


class TransportParametersAreNotArgumentsTests(_Fixture):
    """Header and cookie parameters are filled by the transport, not the caller.

    The corpus makes the case bluntly: its only two header parameters are
    `X-Client-Latitude` / `X-Client-Longitude`, geo values a client injects, and
    their names are not identifiers in any target language — expanding them
    produced a method signature that cannot compile. Reported by the lane that
    tried to convert the declaration.

    Measured before changing it: zero header or cookie parameters in the other
    two canons, so nothing already converted moves.
    """

    def setUp(self):
        super().setUp()
        doc = json.loads(json.dumps(SWAGGER))
        doc["paths"]["/api/geo"] = {"get": {
            "parameters": [
                {"name": "X-Client-Latitude", "in": "header",
                 "schema": {"type": "string"}},
                {"name": "session", "in": "cookie",
                 "schema": {"type": "string"}},
                {"name": "radius", "in": "query",
                 "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "ok"}}}}
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(doc), encoding="utf-8")

    def test_headers_and_cookies_are_left_out(self):
        m, errs = self.resolve({"name": "nearby", "endpoint": "GET /api/geo",
                                "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual([p["name"] for p in m["params"]], ["radius"])

    def test_a_header_only_operation_expands_to_nothing(self):
        """Empty, not an error: the operation genuinely takes no argument the
        caller supplies. An error here would refuse a legal declaration."""
        doc = json.loads((self.root / "docs" / "api" / "swagger.json").read_text())
        doc["paths"]["/api/geo"]["get"]["parameters"] = [
            {"name": "X-Client-Latitude", "in": "header",
             "schema": {"type": "string"}}]
        (self.root / "docs" / "api" / "swagger.json").write_text(
            json.dumps(doc), encoding="utf-8")
        m, errs = self.resolve({"name": "nearby", "endpoint": "GET /api/geo",
                                "params": "@canonical"})
        self.assertEqual(errs, [])
        self.assertEqual(m["params"], [])


class ParentSpecMayNotDeclareTests(unittest.TestCase):
    """A parent spec is a container; the merger builds its sections from subs.

    Everything else it declares is discarded silently. Measured on a real
    parent: nine repository-method declarations that changed nothing when
    edited, every gate green in both directions, and zero merge conflicts —
    because the parent was never a participant to conflict with. Two further
    sections, `branchContracts` and `error_handling`, were vanishing the same
    way and nobody had noticed those at all.
    """

    def check(self, spec: dict):
        rules = shared_core.load("parent_spec_rules")
        return [p for p, _m in rules.dropped_parent_declarations(spec)]

    def parent(self, **extra):
        base = {"type": "screen_parent_spec", "version": "1.0",
                "metadata": {"name": "P", "displayName": "P",
                             "description": "P."},
                "subSpecs": [{"file": "p/a.spec.json", "name": "A"}]}
        base.update(extra)
        return base

    def test_a_dataflow_list_is_refused(self):
        self.assertEqual(
            self.check(self.parent(dataFlow={"repositories": [{"name": "R"}]})),
            ["dataFlow.repositories"])

    def test_sections_the_merger_never_reads_are_refused(self):
        got = self.check(self.parent(branchContracts=[{"id": "x"}],
                                     error_handling={"a": 1}))
        self.assertEqual(got, ["branchContracts", "error_handling"])

    def test_a_pure_container_is_accepted(self):
        """The false-positive boundary — the shape a parent spec is for."""
        self.assertEqual(self.check(self.parent()), [])

    def test_what_the_merger_does_read_is_accepted(self):
        self.assertEqual(
            self.check(self.parent(
                relatedFiles=[{"type": "layout", "path": "p.json"}],
                notes="whatever",
                structure={"notes": "concept-level roots"})),
            [])

    def test_an_empty_declaration_says_nothing(self):
        """An empty list changes no output; deleting it is the author's call."""
        self.assertEqual(
            self.check(self.parent(dataFlow={"repositories": []},
                                   branchContracts=[])),
            [])

    def test_an_ordinary_screen_spec_is_untouched(self):
        """The rule is about parents. A screen spec declares all of this."""
        rules = shared_core.load("parent_spec_rules")
        self.assertEqual(rules.dropped_parent_declarations(
            {"type": "screen", "dataFlow": {"repositories": [{"name": "R"}]},
             "branchContracts": [{"id": "x"}]}), [])
