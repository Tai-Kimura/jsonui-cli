"""Tests for openapi normalization + diff.

The impl-side fixtures deliberately mimic FastAPI + Pydantic v2 output
(OpenAPI 3.1, anyOf-null Optionals, allOf ref wrappers, auto-422,
title on everything) — the false-positive sources review §3-1 calls out.
"""

import unittest

from jsonui_doc_cli.check.openapi_normalize import (
    DEFAULT_IGNORE_PATHS,
    DEFAULT_IGNORE_RESPONSE_CODES,
    _Resolver,
    normalize_path_key,
    normalize_schema,
    normalize_spec,
)
from jsonui_doc_cli.check.openapi_diff import diff_specs


class NormalizeSchemaTests(unittest.TestCase):
    def norm(self, schema, doc=None):
        return normalize_schema(schema, _Resolver(doc or {}))

    def test_pydantic_optional_anyof_null(self):
        out = self.norm({"anyOf": [{"type": "integer"}, {"type": "null"}],
                         "title": "Age"})
        self.assertEqual(out, {"type": "integer", "nullable": True})

    def test_31_type_array_null(self):
        out = self.norm({"type": ["string", "null"]})
        self.assertEqual(out, {"type": "string", "nullable": True})

    def test_nullable_30_equivalent(self):
        a = self.norm({"type": "integer", "nullable": True})
        b = self.norm({"anyOf": [{"type": "integer"}, {"type": "null"}]})
        self.assertEqual(a, b)

    def test_allof_single_ref_wrapper(self):
        doc = {"components": {"schemas": {
            "Role": {"type": "string", "enum": ["admin", "member"],
                     "title": "Role"},
        }}}
        wrapped = {"allOf": [{"$ref": "#/components/schemas/Role"}],
                   "default": "member", "title": "role"}
        plain = {"$ref": "#/components/schemas/Role"}
        self.assertEqual(self.norm(wrapped, doc), self.norm(plain, doc))

    def test_title_description_default_dropped(self):
        out = self.norm({"type": "string", "title": "X",
                         "description": "y", "default": "z",
                         "example": "w"})
        self.assertEqual(out, {"type": "string"})

    def test_integer_format_width_ignored(self):
        self.assertEqual(self.norm({"type": "integer", "format": "int64"}),
                         self.norm({"type": "integer", "format": "int32"}))

    def test_string_format_kept(self):
        out = self.norm({"type": "string", "format": "date-time"})
        self.assertEqual(out["format"], "date-time")

    def test_enum_null_member_folds_into_nullable(self):
        out = self.norm({"type": "string", "enum": ["a", None, "b"]})
        self.assertEqual(out["enum"], ["a", "b"])
        self.assertTrue(out["nullable"])

    def test_additional_properties_true_equals_absent(self):
        self.assertEqual(self.norm({"type": "object",
                                    "additionalProperties": True}),
                         self.norm({"type": "object"}))

    def test_circular_ref_guard(self):
        doc = {"components": {"schemas": {
            "Node": {"type": "object", "properties": {
                "next": {"$ref": "#/components/schemas/Node"}}},
        }}}
        out = self.norm({"$ref": "#/components/schemas/Node"}, doc)
        self.assertEqual(out["properties"]["next"],
                         {"$circular": "Node"})

    def test_path_key_normalization(self):
        self.assertEqual(normalize_path_key("/api/users/{user_id}"),
                         "/api/users/{}")
        self.assertEqual(normalize_path_key("/api/users/"), "/api/users")


DOC_SPEC = {
    "openapi": "3.0.3",
    "paths": {
        "/api/users/{id}": {
            "get": {
                "parameters": [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "string"}}],
                "responses": {"200": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/User"}}}}},
            },
            "delete": {
                "parameters": [{"name": "id", "in": "path", "required": True,
                                "schema": {"type": "string"}}],
                "responses": {"204": {"description": "gone"},
                              "404": {"description": "not found"}},
            },
        },
        "/api/users": {
            "post": {
                "requestBody": {"required": True, "content": {
                    "application/json": {"schema": {
                        "$ref": "#/components/schemas/CreateUser"}}}},
                "responses": {"201": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/User"}}}}},
            },
        },
        "/api/only-in-doc": {
            "get": {"responses": {"200": {"description": "ok"}}},
        },
        "/api/ping": {
            "get": {"responses": {"200": {"content": {"application/json": {
                "schema": {"type": "object", "required": ["status"],
                           "properties": {"status": {"type": "string"}}}}}}}},
        },
    },
    "components": {"schemas": {
        "User": {
            "type": "object",
            "required": ["id", "name", "role"],
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "age": {"type": "integer", "nullable": True},
                "role": {"type": "string", "enum": ["admin", "member"]},
            },
        },
        "CreateUser": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"},
                           "age": {"type": "integer", "nullable": True}},
        },
    }},
}

# FastAPI / Pydantic v2 flavored implementation export
IMPL_SPEC = {
    "openapi": "3.1.0",
    "paths": {
        "/api/users/{user_id}": {
            "get": {
                "parameters": [{"name": "user_id", "in": "path",
                                "required": True,
                                "schema": {"type": "string",
                                           "title": "User Id"}}],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {
                        "$ref": "#/components/schemas/UserOut"}}}},
                    "422": {"content": {"application/json": {"schema": {
                        "$ref": "#/components/schemas/HTTPValidationError"}}}},
                },
            },
            "delete": {
                "parameters": [{"name": "user_id", "in": "path",
                                "required": True,
                                "schema": {"type": "string"}}],
                "responses": {
                    "204": {"description": "ok"},
                    "422": {"description": "auto"},
                },
            },
        },
        "/api/users": {
            "post": {
                "requestBody": {"required": True, "content": {
                    "application/json": {"schema": {
                        "$ref": "#/components/schemas/CreateUserIn"}}}},
                "responses": {
                    "201": {"content": {"application/json": {"schema": {
                        "$ref": "#/components/schemas/UserOut"}}}},
                    "422": {"description": "auto"},
                },
            },
        },
        "/api/impl-only": {
            "get": {"responses": {"200": {"description": "ok"}}},
        },
        "/api/ping": {
            "get": {"responses": {
                "200": {"content": {"application/json": {
                    "schema": {"type": "object", "required": ["status"],
                               "title": "Ping",
                               "properties": {"status": {
                                   "type": "string", "title": "Status"}}}}}},
                "422": {"description": "auto"},
            }},
        },
        "/health": {
            "get": {"responses": {"200": {"description": "ok"}}},
        },
    },
    "components": {"schemas": {
        "UserOut": {
            "type": "object",
            "title": "UserOut",
            "required": ["id", "name", "role"],
            "properties": {
                "id": {"type": "string", "format": "uuid", "title": "Id"},
                "name": {"type": "string", "title": "Name"},
                "age": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                        "title": "Age"},
                # drift: impl dropped the "member" role
                "role": {"allOf": [{"$ref": "#/components/schemas/Role"}],
                         "default": "admin"},
            },
        },
        "Role": {"type": "string", "enum": ["admin"], "title": "Role"},
        "CreateUserIn": {
            "type": "object",
            "title": "CreateUserIn",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "title": "Name"},
                "age": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                        "title": "Age"},
            },
        },
        "HTTPValidationError": {"type": "object", "properties": {
            "detail": {"type": "array", "items": {"type": "object"}}}},
    }},
}


class DiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc = normalize_spec(DOC_SPEC, "doc")
        impl = normalize_spec(IMPL_SPEC, "impl")
        cls.results, cls.warnings = diff_specs(
            doc, impl,
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
        )
        cls.by_status = {}
        for r in cls.results:
            cls.by_status.setdefault(r.status, []).append(r)

    def targets(self, status):
        return [r.target for r in self.by_status.get(status, [])]

    def test_missing_in_impl(self):
        targets = self.targets("missing_in_impl")
        self.assertIn("GET /api/only-in-doc", targets)
        # doc declares 404 on DELETE; impl doesn't
        self.assertTrue(any("DELETE /api/users/{id} → 404" in t
                            for t in targets), targets)

    def test_missing_in_doc_excludes_ignored_paths(self):
        targets = self.targets("missing_in_doc")
        self.assertIn("GET /api/impl-only", targets)
        self.assertFalse(any("/health" in t for t in targets))

    def test_enum_drift_detected_on_every_referencing_operation(self):
        # User (with the drifted role enum) is returned by both GET .../{id}
        # and POST /api/users — the drift must surface on each operation.
        mismatches = self.by_status.get("mismatch", [])
        enum_hits = sorted(r.target for r in mismatches
                           if "role" in r.target and "enum" in r.target)
        self.assertEqual(enum_hits, [
            "GET /api/users/{id} → 200 body.role.enum",
            "POST /api/users → 201 body.role.enum",
        ], mismatches)

    def test_no_false_positives_from_pydantic_noise(self):
        """anyOf-null Optionals, allOf wrappers, titles, auto-422, int
        formats must produce zero mismatches."""
        noise = [r for r in self.results
                 if r.status in ("mismatch", "missing_in_impl",
                                 "missing_in_doc")
                 and "role" not in r.target
                 and "only-in-doc" not in r.target
                 and "impl-only" not in r.target
                 and "404" not in r.target]
        self.assertEqual(noise, [], [f"{r.status}: {r.target}" for r in noise])

    def test_fully_matching_operation_reports_ok(self):
        self.assertIn("GET /api/ping", self.targets("ok"))

    def test_param_name_difference_is_warning_not_mismatch(self):
        self.assertTrue(any("path parameter names differ" in w
                            for w in self.warnings), self.warnings)

    def test_declared_vs_live_disclaimer_absent_here(self):
        # the disclaimer is added by run_openapi_diff, not diff_specs
        self.assertFalse(any("DECLARED" in w for w in self.warnings))


class FastApiNoiseClassTests(unittest.TestCase):
    """Noise classes found while verifying against a real FastAPI backend."""

    def _diff(self, doc, impl):
        return diff_specs(
            normalize_spec(doc, "doc"), normalize_spec(impl, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
        )

    def test_undeclared_impl_response_schema_is_one_skipped(self):
        doc = {"openapi": "3.0.3", "paths": {"/x": {"post": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object", "required": ["a", "b"],
                "properties": {"a": {"type": "string"},
                               "b": {"type": "integer"}}}}}}}}}}}
        impl = {"openapi": "3.1.0", "paths": {"/x": {"post": {"responses": {
            "200": {"content": {"application/json": {"schema": {}}}}}}}}}
        results, _ = self._diff(doc, impl)
        skipped = [r for r in results if r.status == "skipped"]
        mismatches = [r for r in results if r.status == "mismatch"]
        self.assertEqual(len(skipped), 1)
        self.assertIn("does not declare a response schema",
                      skipped[0].message)
        self.assertEqual(mismatches, [])

    def test_query_param_nullable_noise_ignored(self):
        doc = {"openapi": "3.0.3", "paths": {"/x": {"get": {
            "parameters": [{"name": "q", "in": "query",
                            "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok"}}}}}}
        # FastAPI Optional[str] = None
        impl = {"openapi": "3.1.0", "paths": {"/x": {"get": {
            "parameters": [{"name": "q", "in": "query",
                            "schema": {"anyOf": [{"type": "string"},
                                                 {"type": "null"}],
                                       "title": "Q"}}],
            "responses": {"200": {"description": "ok"}}}}}}
        results, _ = self._diff(doc, impl)
        self.assertEqual([r.target for r in results if r.status != "ok"], [])

    def test_untyped_request_body_is_one_skipped(self):
        # FastAPI `body: dict` — impl declares no field-level shape;
        # per-field diff against the documented contract is impossible.
        doc = {"openapi": "3.0.3", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object", "required": ["title"],
                    "properties": {"title": {"type": "string"},
                                   "note": {"type": "string"}}}}}},
            "responses": {"200": {"description": "ok"}}}}}}
        impl = {"openapi": "3.1.0", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {"type": "object",
                                                "title": "Body"}}}},
            "responses": {"200": {"description": "ok"}}}}}}
        results, _ = self._diff(doc, impl)
        skipped = [r for r in results if r.status == "skipped"]
        self.assertEqual(len(skipped), 1, results)
        self.assertIn("untyped request body", skipped[0].message)
        self.assertEqual([r for r in results if r.status == "mismatch"], [])

    def test_nested_untyped_dict_field_is_one_skipped(self):
        # `changes: dict = Field(...)` inside a typed model: only that
        # subtree is unverifiable — siblings still get compared.
        doc = {"openapi": "3.0.3", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                        "changes": {"type": "object", "properties": {
                            "name": {"type": "string"},
                            "abv": {"type": "number"},
                            "age": {"type": "integer"}}}}}}}},
            "responses": {"200": {"description": "ok"}}}}}}
        impl = {"openapi": "3.1.0", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "integer"},        # real drift
                        "changes": {"type": "object"}}}}}},   # untyped
            "responses": {"200": {"description": "ok"}}}}}}
        results, _ = self._diff(doc, impl)
        skipped = [r for r in results if r.status == "skipped"]
        mismatches = [r for r in results if r.status == "mismatch"]
        self.assertEqual([r.target for r in skipped],
                         ["POST /x requestBody body.changes"])
        self.assertEqual(len(mismatches), 1, mismatches)
        self.assertIn("body.reason", mismatches[0].target)

    def test_untyped_array_items_is_one_skipped(self):
        # `crates: list[dict]` — array of bare objects.
        doc = {"openapi": "3.0.3", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object", "properties": {
                        "crates": {"type": "array", "items": {
                            "type": "object", "properties": {
                                "crate_type": {"type": "string"},
                                "ratio": {"type": "number"}}}}}}}}},
            "responses": {"200": {"description": "ok"}}}}}}
        impl = {"openapi": "3.1.0", "paths": {"/x": {"post": {
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": {
                    "type": "object", "properties": {
                        "crates": {"type": "array",
                                  "items": {"type": "object"}}}}}}},
            "responses": {"200": {"description": "ok"}}}}}}
        results, _ = self._diff(doc, impl)
        skipped = [r for r in results if r.status == "skipped"]
        self.assertEqual([r.target for r in skipped],
                         ["POST /x requestBody body.crates[]"])
        self.assertEqual([r for r in results if r.status == "mismatch"], [])


class IgnorePathsAllDirectionsTests(unittest.TestCase):
    """ignore_paths must exclude an endpoint in every direction: doc-only
    (missing_in_impl), impl-only (missing_in_doc), and both-sides compare.
    Use case: internal APIs kept in docs but hidden from the impl OpenAPI
    via include_in_schema=False."""

    @classmethod
    def setUpClass(cls):
        doc = normalize_spec(DOC_SPEC, "doc")
        impl = normalize_spec(IMPL_SPEC, "impl")
        cls.results, cls.warnings = diff_specs(
            doc, impl,
            ignore_paths=["/api/only-in-doc", "/api/impl-only",
                          "/api/ping", "/api/users*", "/health"],
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
        )

    def test_doc_only_endpoint_is_excluded(self):
        self.assertFalse(any("only-in-doc" in r.target for r in self.results),
                         [f"{r.status}: {r.target}" for r in self.results])

    def test_impl_only_endpoint_is_excluded(self):
        self.assertFalse(any("impl-only" in r.target for r in self.results))

    def test_both_sides_endpoints_are_excluded_from_compare(self):
        # /api/ping would be "ok", /api/users* would produce mismatches —
        # ignored paths must yield no result items at all
        self.assertFalse(any("/api/ping" in r.target or "/api/users" in r.target
                             for r in self.results),
                         [f"{r.status}: {r.target}" for r in self.results])

    def test_nothing_remains(self):
        self.assertEqual(self.results, [])


if __name__ == "__main__":
    unittest.main()
