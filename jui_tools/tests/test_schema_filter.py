"""Tests for schema_filter — path/schema glob filter + transitive $ref resolve.

Covers v2 plan §4.1 unit test matrix.
"""
from __future__ import annotations

import unittest

from jui_cli.core.schema_filter import (
    SchemaFilterConfig,
    apply_filter,
)


def _doc(*, schemas: dict, paths: dict | None = None, components_extra: dict | None = None) -> dict:
    components = {"schemas": schemas}
    if components_extra:
        components.update(components_extra)
    return {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": paths or {},
        "components": components,
    }


def _ref(name: str, prefix: str = "schemas") -> dict:
    return {"$ref": f"#/components/{prefix}/{name}"}


class IsActiveTests(unittest.TestCase):
    def test_empty_config_is_inactive(self):
        cfg = SchemaFilterConfig()
        self.assertFalse(cfg.is_active())

    def test_any_dimension_active(self):
        self.assertTrue(
            SchemaFilterConfig(include_paths=("/x",)).is_active()
        )
        self.assertTrue(
            SchemaFilterConfig(exclude_schemas=("Foo*",)).is_active()
        )

    def test_skip_domain_alone_is_not_active_for_filter(self):
        """skip_domain doesn't filter schemas — it only affects scaffold emission.

        ``is_active`` returning False lets the loader bypass path/schema
        filtering entirely; skip_domain is still applied to the kept set.
        """
        cfg = SchemaFilterConfig(skip_domain=("Foo",))
        self.assertFalse(cfg.is_active())


class FromDictTests(unittest.TestCase):
    def test_missing_keys_default_empty(self):
        cfg = SchemaFilterConfig.from_dict({})
        self.assertEqual(cfg.include_paths, ())

    def test_empty_list_equivalent_to_missing(self):
        a = SchemaFilterConfig.from_dict({"include_paths": []})
        b = SchemaFilterConfig.from_dict({})
        self.assertEqual(a, b)

    def test_string_coerced_to_single_element_tuple(self):
        cfg = SchemaFilterConfig.from_dict({"include_paths": "/api/*"})
        self.assertEqual(cfg.include_paths, ("/api/*",))

    def test_none_value_treated_as_empty(self):
        cfg = SchemaFilterConfig.from_dict({"include_paths": None})
        self.assertEqual(cfg.include_paths, ())


class NoFilterPassthroughTests(unittest.TestCase):
    def test_inactive_filter_keeps_all_schemas(self):
        raw = _doc(schemas={
            "A": {"type": "object", "properties": {}},
            "B": {"type": "object", "properties": {}},
            "C": {"type": "object", "properties": {}},
        })
        result = apply_filter(raw, SchemaFilterConfig())
        self.assertEqual(result.kept, frozenset({"A", "B", "C"}))
        self.assertEqual(result.excluded, frozenset())


class IncludePathsTests(unittest.TestCase):
    def test_include_paths_only(self):
        raw = _doc(
            schemas={
                "User": {"type": "object"},
                "Bar": {"type": "object"},
                "Admin": {"type": "object"},
            },
            paths={
                "/api/user/me": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": _ref("User")}}}
                        },
                    },
                },
                "/api/bar/items": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": _ref("Bar")}}}
                        },
                    },
                },
                "/api/admin/grants": {
                    "post": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": _ref("Admin")}}}
                        },
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/user/*",)))
        self.assertEqual(result.kept, frozenset({"User"}))
        self.assertEqual(result.excluded, frozenset({"Bar", "Admin"}))

    def test_include_paths_star_matches_slash(self):
        """v2 §2.3: ``*`` matches any chars including ``/``.

        ``/api/bar/*`` should match ``/api/bar/items/{id}``, not just
        ``/api/bar/items``.
        """
        raw = _doc(
            schemas={"A": {"type": "object"}, "B": {"type": "object"}},
            paths={
                "/api/bar/items/{id}": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("A")}}}}
                    },
                },
                "/other": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("B")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/bar/*",)))
        self.assertEqual(result.kept, frozenset({"A"}))


class ExcludePathsTests(unittest.TestCase):
    def test_exclude_paths_subtracts_from_include(self):
        raw = _doc(
            schemas={
                "User": {"type": "object"},
                "Admin": {"type": "object"},
            },
            paths={
                "/api/user/me": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("User")}}}}
                    },
                },
                "/api/admin/grants": {
                    "post": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("Admin")}}}}
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(
            include_paths=("/api/*",),
            exclude_paths=("/api/admin/*",),
        )
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"User"}))

    def test_exclude_only_with_include_unset(self):
        """exclude_paths alone — initial set is all endpoints."""
        raw = _doc(
            schemas={"A": {"type": "object"}, "B": {"type": "object"}},
            paths={
                "/api/x/foo": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("A")}}}}
                    },
                },
                "/api/dev/scratch": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("B")}}}}
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(exclude_paths=("/api/dev/*",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"A"}))


class TransitiveResolveTests(unittest.TestCase):
    def test_ref_chain_followed(self):
        raw = _doc(
            schemas={
                "Order": {
                    "type": "object",
                    "properties": {"item": _ref("Item")},
                },
                "Item": {
                    "type": "object",
                    "properties": {"image": _ref("Image")},
                },
                "Image": {"type": "object", "properties": {"url": {"type": "string"}}},
                "Unrelated": {"type": "object"},
            },
            paths={
                "/api/orders": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("Order")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/orders",)))
        self.assertEqual(result.kept, frozenset({"Order", "Item", "Image"}))
        self.assertIn("Unrelated", result.excluded)

    def test_array_items_ref_followed(self):
        raw = _doc(
            schemas={
                "List": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": _ref("Item")}},
                },
                "Item": {"type": "object"},
            },
            paths={
                "/api/list": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("List")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/list",)))
        self.assertEqual(result.kept, frozenset({"List", "Item"}))

    def test_all_of_branches_followed(self):
        raw = _doc(
            schemas={
                "Base": {"type": "object"},
                "Mixin": {"type": "object"},
                "Combined": {"allOf": [_ref("Base"), _ref("Mixin")]},
            },
            paths={
                "/api/c": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("Combined")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/c",)))
        self.assertEqual(result.kept, frozenset({"Base", "Mixin", "Combined"}))

    def test_one_of_branches_followed_lenient(self):
        """Filter doesn't halt on oneOf — collects all branches' refs."""
        raw = _doc(
            schemas={
                "Success": {"type": "object"},
                "Error": {"type": "object"},
            },
            paths={
                "/api/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "oneOf": [_ref("Success"), _ref("Error")],
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/x",)))
        self.assertEqual(result.kept, frozenset({"Success", "Error"}))

    def test_typed_map_value_ref_followed(self):
        raw = _doc(
            schemas={
                "Holder": {
                    "type": "object",
                    "properties": {
                        "labels": {
                            "type": "object",
                            "additionalProperties": _ref("Tag"),
                        },
                    },
                },
                "Tag": {"type": "object"},
            },
            paths={
                "/api/h": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("Holder")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/h",)))
        self.assertEqual(result.kept, frozenset({"Holder", "Tag"}))


class CycleTests(unittest.TestCase):
    def test_direct_self_ref_does_not_loop(self):
        raw = _doc(
            schemas={
                "Node": {
                    "type": "object",
                    "properties": {"next": _ref("Node")},
                },
            },
            paths={
                "/api/n": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("Node")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/n",)))
        self.assertEqual(result.kept, frozenset({"Node"}))

    def test_mutual_recursion_does_not_loop(self):
        raw = _doc(
            schemas={
                "A": {"type": "object", "properties": {"b": _ref("B")}},
                "B": {"type": "object", "properties": {"a": _ref("A")}},
            },
            paths={
                "/api/a": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("A")}}}}
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/a",)))
        self.assertEqual(result.kept, frozenset({"A", "B"}))


class SharedComponentRefTests(unittest.TestCase):
    """v2 §2.2: components.{parameters, responses, requestBodies} should
    act as transitive intermediates."""

    def test_shared_parameter_ref_resolved(self):
        raw = _doc(
            schemas={
                "User": {"type": "object"},
                "PageMeta": {"type": "object"},
            },
            paths={
                "/api/users": {
                    "get": {
                        "parameters": [_ref("PageSize", "parameters")],
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("User")}}}},
                    },
                },
            },
            components_extra={
                "parameters": {
                    "PageSize": {
                        "in": "query",
                        "name": "page_size",
                        "schema": _ref("PageMeta"),
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/users",)))
        self.assertIn("User", result.kept)
        self.assertIn("PageMeta", result.kept)

    def test_shared_response_ref_resolved(self):
        raw = _doc(
            schemas={
                "Foo": {"type": "object"},
                "ErrorResponse": {"type": "object"},
            },
            paths={
                "/api/foo": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": _ref("Foo")}}},
                            "401": _ref("Unauthorized", "responses"),
                        },
                    },
                },
            },
            components_extra={
                "responses": {
                    "Unauthorized": {
                        "content": {"application/json": {"schema": _ref("ErrorResponse")}},
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/foo",)))
        self.assertIn("ErrorResponse", result.kept)

    def test_shared_request_body_ref_resolved(self):
        raw = _doc(
            schemas={
                "UserCreate": {"type": "object"},
                "User": {"type": "object"},
            },
            paths={
                "/api/users": {
                    "post": {
                        "requestBody": _ref("UserBody", "requestBodies"),
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("User")}}}},
                    },
                },
            },
            components_extra={
                "requestBodies": {
                    "UserBody": {
                        "content": {"application/json": {"schema": _ref("UserCreate")}},
                    },
                },
            },
        )
        result = apply_filter(raw, SchemaFilterConfig(include_paths=("/api/users",)))
        self.assertIn("UserCreate", result.kept)


class IncludeExcludeSchemaTests(unittest.TestCase):
    def test_include_schemas_adds_to_set(self):
        raw = _doc(
            schemas={
                "User": {"type": "object"},
                "ErrorResponse": {"type": "object"},
                "Unused": {"type": "object"},
            },
            paths={
                "/api/u": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("User")}}}}
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(
            include_paths=("/api/u",),
            include_schemas=("ErrorResponse",),
        )
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"User", "ErrorResponse"}))

    def test_include_schemas_alone_with_transitive(self):
        """include_schemas alone — no path filter, but transitive closure applies."""
        raw = _doc(
            schemas={
                "Parent": {
                    "type": "object",
                    "properties": {"child": _ref("Child")},
                },
                "Child": {"type": "object"},
                "Other": {"type": "object"},
            },
            paths={},
        )
        cfg = SchemaFilterConfig(include_schemas=("Parent",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"Parent", "Child"}))

    def test_exclude_schemas_glob_removes(self):
        raw = _doc(
            schemas={
                "BarItem": {"type": "object"},
                "BarOrder": {"type": "object"},
                "User": {"type": "object"},
            },
            paths={
                "/api/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "a": _ref("BarItem"),
                                                "b": _ref("BarOrder"),
                                                "u": _ref("User"),
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(
            include_paths=("/api/x",),
            exclude_schemas=("Bar*",),
        )
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"User"}))


class SkipDomainTests(unittest.TestCase):
    def test_skip_domain_glob_matches_kept(self):
        raw = _doc(
            schemas={
                "BarUserProfile": {"type": "object"},
                "BarOrder": {"type": "object"},
                "User": {"type": "object"},
            },
        )
        cfg = SchemaFilterConfig(skip_domain=("Bar*",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"BarUserProfile", "BarOrder", "User"}))
        self.assertEqual(result.skip_domain_matches, frozenset({"BarUserProfile", "BarOrder"}))

    def test_skip_domain_literal_name(self):
        raw = _doc(schemas={"User": {"type": "object"}, "Bar": {"type": "object"}})
        cfg = SchemaFilterConfig(skip_domain=("User",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.skip_domain_matches, frozenset({"User"}))

    def test_skip_domain_does_not_affect_kept(self):
        """skip_domain is independent of the include/exclude pipeline."""
        raw = _doc(
            schemas={"User": {"type": "object"}, "Other": {"type": "object"}},
            paths={
                "/api/u": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("User")}}}}
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(
            include_paths=("/api/u",),
            skip_domain=("User",),
        )
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset({"User"}))
        self.assertEqual(result.skip_domain_matches, frozenset({"User"}))


class EmptyKeptTests(unittest.TestCase):
    def test_no_matching_paths_yields_empty(self):
        raw = _doc(
            schemas={"A": {"type": "object"}, "B": {"type": "object"}},
            paths={
                "/api/x": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("A")}}}}
                    },
                },
            },
        )
        cfg = SchemaFilterConfig(include_paths=("/nonexistent/*",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset())
        self.assertEqual(result.excluded, frozenset({"A", "B"}))


class CaseSensitivityTests(unittest.TestCase):
    def test_path_pattern_case_sensitive(self):
        raw = _doc(
            schemas={"A": {"type": "object"}},
            paths={
                "/api/Bar/items": {
                    "get": {
                        "responses": {"200": {"content": {"application/json": {"schema": _ref("A")}}}}
                    },
                },
            },
        )
        # lowercase pattern shouldn't match capitalised path
        cfg = SchemaFilterConfig(include_paths=("/api/bar/*",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.kept, frozenset())

    def test_schema_pattern_case_sensitive(self):
        raw = _doc(
            schemas={"User": {"type": "object"}, "user": {"type": "object"}},
        )
        cfg = SchemaFilterConfig(skip_domain=("User",))
        result = apply_filter(raw, cfg)
        self.assertEqual(result.skip_domain_matches, frozenset({"User"}))


if __name__ == "__main__":
    unittest.main()
