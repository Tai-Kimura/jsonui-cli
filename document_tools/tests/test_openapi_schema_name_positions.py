"""Regression: openapi-diff-schema-name-warning-computed-globally-not-positionally.

The schema-name warning used to be `set(doc component names) - set(impl
component names)`, which answers a question nobody asked. A consumer got 53
lines out of it and could act on 13; the rest were shapes the implementation
cannot name at that position at all (SSE bodies, error-only responses,
inline-expanded models) plus doc-side orphans.

Worse, and only visible once measured: the subtraction was ALSO blind. A name
present anywhere in the impl components satisfied it, so an endpoint whose
impl used a different name for that position stayed silent as long as the
doc's name existed somewhere else. On the reporter's corpus that hid 6 of the
8 real drifts.

Positional computation asks one question — "at this position, does the impl
use a different name?" — and both problems go away: what cannot be renamed is
never listed, and what is listed carries the impl-side name, which is the
half a rename actually needs.
"""

from __future__ import annotations

import unittest

from jsonui_doc_cli.check.openapi_diff import diff_specs
from jsonui_doc_cli.check.openapi_normalize import (
    DEFAULT_IGNORE_PATHS,
    DEFAULT_IGNORE_RESPONSE_CODES,
    normalize_spec,
)


def _spec(paths: dict, schemas: dict, version: str = "3.0.3") -> dict:
    return {"openapi": version, "paths": paths,
            "components": {"schemas": schemas}}


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _json(schema: dict) -> dict:
    return {"content": {"application/json": {"schema": schema}}}


OBJ = {"type": "object", "properties": {"a": {"type": "string"}}}


class SchemaNamePositionTests(unittest.TestCase):
    def diff(self, doc: dict, impl: dict, ignore_codes=None):
        results, _ = diff_specs(
            normalize_spec(doc, "doc"), normalize_spec(impl, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES) | set(ignore_codes or ()))
        return [r for r in results if r.status == "warning"]

    # ---- the finding it must report ---------------------------------- #

    def test_same_position_different_name_is_reported_with_both_names(self):
        doc = _spec({"/x": {"post": {"requestBody": _json(_ref("EmailLoginRequest")),
                                     "responses": {"200": {"description": "ok"}}}}},
                    {"EmailLoginRequest": OBJ})
        impl = _spec({"/x": {"post": {"requestBody": _json(_ref("LoginRequest")),
                                      "responses": {"200": {"description": "ok"}}}}},
                     {"LoginRequest": OBJ}, version="3.1.0")
        warnings = self.diff(doc, impl)
        self.assertEqual(len(warnings), 1, warnings)
        w = warnings[0]
        self.assertEqual(w.target, "POST /x requestBody body")
        self.assertEqual(w.expected, "EmailLoginRequest")
        # The impl-side name is the half a rename needs; the old set-based
        # warning never carried it.
        self.assertEqual(w.actual, "LoginRequest")

    def test_the_name_existing_elsewhere_in_impl_no_longer_hides_the_drift(self):
        """The false negative the set difference had.

        impl names the *user* endpoint's body `ResendCodeRequest` and the
        *partner* endpoint's `PartnerResendCodeRequest`; docs call both
        `ResendCodeRequest`. `doc_names - impl_names` is empty, so the old
        computation said nothing about the partner endpoint.
        """
        body = {"/api/auth/resend": {"post": {
                    "requestBody": _json(_ref("ResendCodeRequest")),
                    "responses": {"200": {"description": "ok"}}}},
                "/api/partner/auth/resend": {"post": {
                    "requestBody": _json(_ref("ResendCodeRequest")),
                    "responses": {"200": {"description": "ok"}}}}}
        doc = _spec(body, {"ResendCodeRequest": OBJ})
        impl = _spec({"/api/auth/resend": {"post": {
                          "requestBody": _json(_ref("ResendCodeRequest")),
                          "responses": {"200": {"description": "ok"}}}},
                      "/api/partner/auth/resend": {"post": {
                          "requestBody": _json(_ref("PartnerResendCodeRequest")),
                          "responses": {"200": {"description": "ok"}}}}},
                     {"ResendCodeRequest": OBJ, "PartnerResendCodeRequest": OBJ},
                     version="3.1.0")
        doc_names = set(normalize_spec(doc, "doc").operations)
        self.assertTrue(doc_names)  # sanity: both operations parsed
        warnings = self.diff(doc, impl)
        self.assertEqual([w.target for w in warnings],
                         ["POST /api/partner/auth/resend requestBody body"])

    def test_nested_positions_are_reported_with_their_location(self):
        doc = _spec({"/x": {"get": {"responses": {"200": _json({
                        "type": "object",
                        "properties": {"items": {"type": "array",
                                                 "items": _ref("LineItem")}}})}}}},
                    {"LineItem": OBJ})
        impl = _spec({"/x": {"get": {"responses": {"200": _json({
                         "type": "object",
                         "properties": {"items": {"type": "array",
                                                  "items": _ref("OrderLineItem")}}})}}}},
                     {"OrderLineItem": OBJ}, version="3.1.0")
        warnings = self.diff(doc, impl)
        self.assertEqual([w.target for w in warnings],
                         ["GET /x → 200 body.items[]"])

    def test_a_parameter_schema_name_is_a_position_too(self):
        doc = _spec({"/x": {"get": {
                        "parameters": [{"name": "sort", "in": "query",
                                        "schema": _ref("SortOrder")}],
                        "responses": {"200": {"description": "ok"}}}}},
                    {"SortOrder": {"type": "string", "enum": ["asc"]}})
        impl = _spec({"/x": {"get": {
                         "parameters": [{"name": "sort", "in": "query",
                                         "schema": _ref("Order")}],
                         "responses": {"200": {"description": "ok"}}}}},
                     {"Order": {"type": "string", "enum": ["asc"]}},
                     version="3.1.0")
        warnings = self.diff(doc, impl)
        self.assertEqual([w.target for w in warnings],
                         ["GET /x param query:sort schema"])

    def test_it_is_a_warning_and_never_gates(self):
        doc = _spec({"/x": {"post": {"requestBody": _json(_ref("A")),
                                     "responses": {"200": {"description": "ok"}}}}},
                    {"A": OBJ})
        impl = _spec({"/x": {"post": {"requestBody": _json(_ref("B")),
                                      "responses": {"200": {"description": "ok"}}}}},
                     {"B": OBJ}, version="3.1.0")
        results, _ = diff_specs(
            normalize_spec(doc, "doc"), normalize_spec(impl, "impl"),
            ignore_paths=list(DEFAULT_IGNORE_PATHS),
            ignore_codes=set(DEFAULT_IGNORE_RESPONSE_CODES))
        statuses = {r.status for r in results}
        self.assertEqual(statuses, {"ok", "warning"})
        # the operation still counts as ok — a name is not a contract break
        self.assertIn("POST /x", [r.target for r in results if r.status == "ok"])

    # ---- what it must NOT report -------------------------------------- #

    def test_a_shape_the_impl_never_named_is_not_listed(self):
        """SSE / StreamingResponse and inline-expanded models: the impl has
        no name at that position, so there is nothing to rename."""
        doc = _spec({"/x": {"get": {"responses": {"200": _json(_ref("StreamEvent"))}}}},
                    {"StreamEvent": OBJ})
        impl = _spec({"/x": {"get": {"responses": {"200": _json(dict(OBJ))}}}},
                     {}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])

    def test_an_error_only_schema_is_not_listed(self):
        """Non-2xx bodies are a presence check only. Listing a name there
        invites `responses={404: {"model": ErrorResponse}}` written purely to
        silence the warning — a declaration no comparison reads."""
        doc = _spec({"/x": {"get": {"responses": {
                        "200": {"description": "ok"},
                        "404": _json(_ref("ErrorResponse"))}}}},
                    {"ErrorResponse": OBJ})
        impl = _spec({"/x": {"get": {"responses": {
                         "200": {"description": "ok"},
                         "404": _json(_ref("HTTPError"))}}}},
                     {"HTTPError": OBJ}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])

    def test_a_doc_side_orphan_is_not_listed(self):
        """A component referenced from nowhere is docs-side hygiene, not
        drift against the implementation."""
        doc = _spec({"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
                    {"NeverReferenced": OBJ})
        impl = _spec({"/x": {"get": {"responses": {"200": {"description": "ok"}}}}},
                     {}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])

    def test_an_ignored_response_code_is_not_name_compared(self):
        doc = _spec({"/x": {"get": {"responses": {
                        "200": {"description": "ok"},
                        "201": _json(_ref("Created"))}}}},
                    {"Created": OBJ})
        impl = _spec({"/x": {"get": {"responses": {
                         "200": {"description": "ok"},
                         "201": _json(_ref("CreatedOut"))}}}},
                     {"CreatedOut": OBJ}, version="3.1.0")
        self.assertEqual([w.target for w in self.diff(doc, impl)],
                         ["GET /x → 201 body"])
        self.assertEqual(self.diff(doc, impl, ignore_codes={"201"}), [])

    def test_pydantic_input_output_split_is_not_a_rename(self):
        """Pydantic v2 emits `Name-Input` / `Name-Output` when a model's
        validation and serialization schemas differ, and the base name then
        does not exist. The docs cannot spell the split."""
        doc = _spec({"/x": {"put": {
                        "requestBody": _json(_ref("ScheduleSlot")),
                        "responses": {"200": _json(_ref("ScheduleSlot"))}}}},
                    {"ScheduleSlot": OBJ})
        impl = _spec({"/x": {"put": {
                         "requestBody": _json(_ref("ScheduleSlot-Input")),
                         "responses": {"200": _json(_ref("ScheduleSlot-Output"))}}}},
                     {"ScheduleSlot-Input": OBJ,
                      "ScheduleSlot-Output": OBJ}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])
        # ...but a genuinely different class still surfaces through the suffix
        impl["paths"]["/x"]["put"]["requestBody"] = _json(_ref("TimeWindow-Input"))
        impl["components"]["schemas"]["TimeWindow-Input"] = OBJ
        self.assertEqual([w.actual for w in self.diff(doc, impl)],
                         ["TimeWindow-Input"])

    def test_the_allOf_wrapper_reports_the_outer_name(self):
        """FastAPI wraps refs in `allOf` to carry defaults. The position is
        named by the outer component, not by whatever it resolves through."""
        doc = _spec({"/x": {"get": {"responses": {"200": _json(_ref("Wrapper"))}}}},
                    {"Wrapper": {"allOf": [_ref("Inner")]}, "Inner": OBJ})
        impl = _spec({"/x": {"get": {"responses": {"200": _json(_ref("Other"))}}}},
                     {"Other": {"allOf": [_ref("Inner")]}, "Inner": OBJ},
                     version="3.1.0")
        warnings = self.diff(doc, impl)
        self.assertEqual([(w.expected, w.actual) for w in warnings],
                         [("Wrapper", "Other")])

    def test_an_optional_ref_still_names_its_position(self):
        """`anyOf: [$ref, null]` is how FastAPI spells Optional[Model]; the
        null-fold must not lose the name."""
        doc = _spec({"/x": {"get": {"responses": {"200": _json({
                        "type": "object",
                        "properties": {"profile": _ref("Preferences")}})}}}},
                    {"Preferences": OBJ})
        impl = _spec({"/x": {"get": {"responses": {"200": _json({
                         "type": "object",
                         "properties": {"profile": {"anyOf": [
                             _ref("PreferencesOut"), {"type": "null"}]}}})}}}},
                     {"PreferencesOut": OBJ}, version="3.1.0")
        self.assertEqual([(w.target, w.actual) for w in self.diff(doc, impl)],
                         [("GET /x → 200 body.profile", "PreferencesOut")])

    def test_matching_names_say_nothing(self):
        doc = _spec({"/x": {"post": {"requestBody": _json(_ref("Same")),
                                     "responses": {"200": {"description": "ok"}}}}},
                    {"Same": OBJ})
        impl = _spec({"/x": {"post": {"requestBody": _json(_ref("Same")),
                                      "responses": {"200": {"description": "ok"}}}}},
                     {"Same": OBJ}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])

    def test_an_ignored_path_is_not_name_compared(self):
        doc = _spec({"/health": {"post": {"requestBody": _json(_ref("A")),
                                          "responses": {"200": {"description": "ok"}}}}},
                    {"A": OBJ})
        impl = _spec({"/health": {"post": {"requestBody": _json(_ref("B")),
                                           "responses": {"200": {"description": "ok"}}}}},
                     {"B": OBJ}, version="3.1.0")
        self.assertEqual(self.diff(doc, impl), [])


if __name__ == "__main__":
    unittest.main()
