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

    def test_const_is_the_31_spelling_of_a_single_value_enum(self):
        for value in (True, "invited", 3):
            self.assertEqual(self.norm({"type": "string", "const": value}),
                             self.norm({"type": "string", "enum": [value]}))

    def test_const_folds_inside_the_31_optional_wrappers(self):
        self.assertEqual(
            self.norm({"anyOf": [{"type": "string", "const": "x"},
                                 {"type": "null"}]}),
            {"type": "string", "enum": ["x"], "nullable": True})
        self.assertEqual(
            self.norm({"allOf": [{"type": "string", "const": "x"}],
                       "default": "x"}),
            {"type": "string", "enum": ["x"]})

    def test_const_narrows_a_co_declared_enum(self):
        # Both keywords apply at once in JSON Schema, so the effective
        # constraint is the intersection — const is the narrower one.
        self.assertEqual(
            self.norm({"type": "string", "enum": ["a", "b"], "const": "a"}),
            {"type": "string", "enum": ["a"]})

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


class ComparisonKeySeverityTests(unittest.TestCase):
    """`ignore_schema_keys` / `downgrade_to_warning` (CheckDecl).

    A doc that is deliberately STRICTER than the implementation (`format:
    uuid` over FastAPI's bare `str`) produced one mismatch per documented
    field — 84% of findings in a real 178-path backend — burying the enum
    drift the checker exists to catch. Severity per comparison key is the
    lever: the project declares which comparisons gate, without loosening
    the docs or tightening the API's accepted values to quiet the tool.
    """

    DOC = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {
        "200": {"content": {"application/json": {"schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "mode": {"type": "string", "enum": ["daily", "time_slot"]},
            }}}}}}}}}}
    IMPL = {"openapi": "3.1.0", "paths": {"/x": {"get": {"responses": {
        "200": {"content": {"application/json": {"schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "mode": {"type": "string",
                         "enum": ["daily", "time_slot", "immediate"]},
            }}}}}}}}}}

    def _diff(self, **kwargs):
        return diff_specs(
            normalize_spec(self.DOC, "doc"), normalize_spec(self.IMPL, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
            **kwargs)

    def _by_key(self, results, suffix):
        return [r for r in results if r.target.endswith(suffix)]

    def test_baseline_both_gate(self):
        results, _ = self._diff()
        self.assertEqual(
            [r.status for r in self._by_key(results, ".format")], ["mismatch"])
        self.assertEqual(
            [r.status for r in self._by_key(results, ".enum")], ["mismatch"])

    def test_ignore_drops_the_comparison_entirely(self):
        results, _ = self._diff(ignore_keys=frozenset({"format"}))
        self.assertEqual(self._by_key(results, ".format"), [])
        # the finding the checker exists for survives untouched
        self.assertEqual(
            [r.status for r in self._by_key(results, ".enum")], ["mismatch"])

    def test_downgrade_keeps_the_finding_but_not_the_gate(self):
        results, _ = self._diff(warn_keys=frozenset({"format"}))
        fmt = self._by_key(results, ".format")
        self.assertEqual([r.status for r in fmt], ["warning"])
        # detail is preserved — that is the point over ignoring
        self.assertEqual(fmt[0].expected, "uuid")
        self.assertEqual(fmt[0].actual, "None")
        self.assertIn("downgrade_to_warning", fmt[0].message)

    def test_downgraded_only_operation_is_gating_clean(self):
        impl = {"openapi": "3.1.0", "paths": {"/x": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "mode": {"type": "string",
                             "enum": ["daily", "time_slot"]},
                }}}}}}}}}}
        results, _ = diff_specs(
            normalize_spec(self.DOC, "doc"), normalize_spec(impl, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
            warn_keys=frozenset({"format"}))
        statuses = {r.status for r in results}
        self.assertIn("warning", statuses)
        self.assertIn("ok", statuses)          # operation still reported ok
        self.assertNotIn("mismatch", statuses)

    def test_ignoring_a_key_cannot_hide_a_sibling_difference(self):
        # `type` differs AND `format` differs; ignoring format must not
        # swallow the type finding (the node still differs).
        doc = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"n": {"type": "string", "format": "uuid"}}}}}}}}}}}
        impl = {"openapi": "3.1.0", "paths": {"/x": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object",
                "properties": {"n": {"type": "integer"}}}}}}}}}}}
        results, _ = diff_specs(
            normalize_spec(doc, "doc"), normalize_spec(impl, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
            ignore_keys=frozenset({"format"}))
        self.assertEqual(
            [r.status for r in self._by_key(results, ".type")], ["mismatch"])


class ConstVsEnumTests(unittest.TestCase):
    """`Literal[X]` on the impl side vs `enum: [X]` in the docs.

    OpenAPI 3.0 has no `const`, so a hand-written docs side can only spell a
    single-value constraint as `enum: [X]`, while FastAPI + Pydantic v2 emit
    3.1 `const: X` for `Literal[X]`. Neither side can move: dropping the
    Literal loses real contract information, and `ignore_schema_keys:
    ["enum"]` would take the genuine enum drift down with the noise. In a
    real 178-path backend this one pattern was 37 of 96 mismatches, burying
    19 real ones.
    """

    def _diff(self, doc_schema, impl_schema, **kwargs):
        def spec(version, schema):
            return {"openapi": version, "paths": {"/x": {"get": {"responses": {
                "200": {"content": {"application/json": {
                    "schema": schema}}}}}}}}
        return diff_specs(
            normalize_spec(spec("3.0.3", doc_schema), "doc"),
            normalize_spec(spec("3.1.0", impl_schema), "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
            **kwargs)[0]

    def test_literal_response_flag_is_not_a_difference(self):
        results = self._diff(
            {"type": "object", "required": ["ok"],
             "properties": {"ok": {"type": "boolean", "enum": [True]}}},
            {"type": "object", "required": ["ok"],
             "properties": {"ok": {"type": "boolean", "const": True,
                                   "title": "Ok"}}})
        self.assertEqual([r.status for r in results], ["ok"], results)

    def test_it_is_not_boolean_specific(self):
        results = self._diff(
            {"type": "object",
             "properties": {"status": {"type": "string",
                                       "enum": ["invited"]}}},
            {"type": "object",
             "properties": {"status": {"type": "string",
                                       "const": "invited"}}})
        self.assertEqual([r.status for r in results], ["ok"], results)

    def test_a_drifted_literal_still_gates(self):
        # The half the report did not ask for: before the fold, `const` was
        # compared by nothing at all, so two DIFFERENT const values passed
        # as ok. Equivalence must not become blindness.
        results = self._diff(
            {"type": "object",
             "properties": {"status": {"type": "string",
                                       "enum": ["invited"]}}},
            {"type": "object",
             "properties": {"status": {"type": "string",
                                       "const": "active"}}})
        hit = [r for r in results if r.target.endswith("body.status.enum")]
        self.assertEqual([r.status for r in hit], ["mismatch"], results)
        self.assertEqual(hit[0].expected, "invited")

    def test_two_different_consts_are_not_equal(self):
        # Nothing compared `const` before the fold, so a 3.1 doc side and a
        # 3.1 impl side pinning DIFFERENT literals reported ok. Folding both
        # into enum is what makes that difference visible at all.
        def spec(literal):
            return {"openapi": "3.1.0", "paths": {"/x": {"get": {"responses": {
                "200": {"content": {"application/json": {"schema": {
                    "type": "object",
                    "properties": {"s": {"type": "string",
                                         "const": literal}}}}}}}}}}}
        results, _ = diff_specs(
            normalize_spec(spec("invited"), "doc"),
            normalize_spec(spec("active"), "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES))
        hit = [r for r in results if r.target.endswith("body.s.enum")]
        self.assertEqual([r.status for r in hit], ["mismatch"], results)

    def test_a_widened_impl_still_gates(self):
        # docs pin one value, impl accepts a set — the union widened.
        results = self._diff(
            {"type": "object",
             "properties": {"s": {"type": "string", "enum": ["a"]}}},
            {"type": "object",
             "properties": {"s": {"type": "string", "enum": ["a", "b"]}}})
        hit = [r for r in results if r.target.endswith("body.s.enum")]
        self.assertEqual([r.status for r in hit], ["mismatch"], results)

    def test_const_answers_to_the_enum_comparison_key(self):
        # A const difference surfaces under `enum`, so the closed key set
        # from 1.6.10 keeps covering it — no sixth key to declare.
        results = self._diff(
            {"type": "object",
             "properties": {"s": {"type": "string", "enum": ["a"]}}},
            {"type": "object",
             "properties": {"s": {"type": "string", "const": "b"}}},
            ignore_keys=frozenset({"enum"}))
        self.assertEqual([r.status for r in results], ["ok"], results)


class FormatPresenceVsValueTests(unittest.TestCase):
    """`format` splits into two findings that wear the same word.

    One side carrying a format the other omits is an ANNOTATION difference
    (`format_presence`): same type, same wire, same generated DTO — what a
    docs side written stricter than the implementation looks like. Both
    sides declaring a format and DISAGREEING (`format`) is a contradiction
    about what the value is and belongs on the gate. Silencing the first
    must not blind a project to the second.
    """

    def _spec(self, fmt):
        prop = {"type": "string"}
        if fmt is not None:
            prop["format"] = fmt
        return {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {
            "200": {"content": {"application/json": {"schema": {
                "type": "object", "properties": {"v": prop}}}}}}}}}}

    def _diff(self, doc_fmt, impl_fmt, **kwargs):
        results, _ = diff_specs(
            normalize_spec(self._spec(doc_fmt), "doc"),
            normalize_spec(self._spec(impl_fmt), "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES),
            **kwargs)
        return [r for r in results if r.target.endswith(".format")]

    # --- default: both kinds still gate, exactly as before the split ---
    def test_one_sided_gates_by_default(self):
        self.assertEqual([r.status for r in self._diff("uuid", None)],
                         ["mismatch"])

    def test_conflicting_values_gate_by_default(self):
        self.assertEqual([r.status for r in self._diff("date-time", "uuid")],
                         ["mismatch"])

    # --- the point of the split ---
    def test_presence_downgrade_leaves_conflicting_values_gating(self):
        self.assertEqual(
            [r.status for r in self._diff("uuid", None,
                                          warn_keys=frozenset({"format_presence"}))],
            ["warning"])
        self.assertEqual(
            [r.status for r in self._diff("date-time", "uuid",
                                          warn_keys=frozenset({"format_presence"}))],
            ["mismatch"])

    def test_presence_ignore_leaves_conflicting_values_gating(self):
        self.assertEqual(
            self._diff("uuid", None, ignore_keys=frozenset({"format_presence"})), [])
        self.assertEqual(
            [r.status for r in self._diff("date-time", "uuid",
                                          ignore_keys=frozenset({"format_presence"}))],
            ["mismatch"])

    def test_impl_side_only_format_is_also_presence(self):
        # EmailStr adds `format: email` the docs never claimed — same class.
        self.assertEqual(
            [r.status for r in self._diff(None, "email",
                                          warn_keys=frozenset({"format_presence"}))],
            ["warning"])

    # --- backward compatibility: `format` remains the umbrella ---
    def test_umbrella_downgrade_still_covers_both_kinds(self):
        # Configs written before the split must not change meaning; a
        # re-gated 500-finding class would turn a consumer's CI red.
        for doc_fmt, impl_fmt in [("uuid", None), ("date-time", "uuid")]:
            self.assertEqual(
                [r.status for r in self._diff(doc_fmt, impl_fmt,
                                              warn_keys=frozenset({"format"}))],
                ["warning"], f"{doc_fmt} vs {impl_fmt}")

    def test_umbrella_ignore_still_covers_both_kinds(self):
        for doc_fmt, impl_fmt in [("uuid", None), ("date-time", "uuid")]:
            self.assertEqual(
                self._diff(doc_fmt, impl_fmt, ignore_keys=frozenset({"format"})),
                [], f"{doc_fmt} vs {impl_fmt}")
