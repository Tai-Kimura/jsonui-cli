"""Tests for structure.embeds[] validation (Embed view type).

Exercises _validate_embeds_section + _validate_embed in SpecValidator
through the public validate_data() entry point so error paths match the
real CLI flow.

See specification-rules.md (5) and docs/plans/2026-05-14-embed-mcp-agents.md.
"""
from __future__ import annotations

import unittest

from jsonui_doc_cli.spec_doc.validator import SpecValidator


def _base_spec(embeds, *, vm_methods=None, vm_vars=None, ui_vars=None, handlers=None):
    """Build a minimal valid screen_spec wrapping the given embeds list."""
    spec = {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {
            "name": "Dashboard",
            "displayName": "Dashboard",
            "description": "Tablet dashboard hosting embedded panes.",
            "layoutFile": "dashboard",
        },
        "structure": {
            "components": [],
            "layout": {},
            "embeds": embeds,
        },
        "dataFlow": {
            "viewModel": {
                "description": "Dashboard VM",
                "methods": vm_methods or [],
                "vars": vm_vars or [],
            },
        },
        "stateManagement": {
            "uiVariables": ui_vars or [],
            "eventHandlers": handlers or [],
        },
    }
    return spec


def _errors_at(result, path_substr):
    return [e for e in result.errors if path_substr in e.path]


class EmbedValidEntry(unittest.TestCase):
    def test_minimal_valid_embed_passes(self):
        spec = _base_spec(
            [{"regionId": "detailPane", "screen": "order_detail"}]
        )
        v = SpecValidator()
        result = v.validate_data(spec)
        embed_errors = _errors_at(result, "structure.embeds")
        self.assertEqual(embed_errors, [],
                         f"unexpected embed errors: {embed_errors}")

    def test_full_valid_embed_with_params_events_passes(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "params": {"orderId": "@{selectedOrderId}"},
                "events": {"onOrderUpdated": "handleOrderUpdated"},
                "navigationMode": "delegate",
            }],
            vm_methods=[
                {"name": "handleOrderUpdated",
                 "params": [{"name": "id", "type": "String"}],
                 "returnType": "Void"},
            ],
            ui_vars=[
                {"name": "selectedOrderId", "type": "String",
                 "description": "Currently selected order id."},
            ],
        )
        v = SpecValidator()
        result = v.validate_data(spec)
        embed_errors = _errors_at(result, "structure.embeds")
        self.assertEqual(embed_errors, [],
                         f"unexpected embed errors: {embed_errors}")


class EmbedRequiredFields(unittest.TestCase):
    def test_missing_screen_is_error(self):
        spec = _base_spec([{"regionId": "detailPane"}])
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].screen")
        self.assertTrue(errs, "expected error on missing screen")
        self.assertIn("screen", errs[0].message)

    def test_missing_region_id_is_error(self):
        spec = _base_spec([{"screen": "order_detail"}])
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].regionId")
        self.assertTrue(errs, "expected error on missing regionId")


class EmbedNamingConventions(unittest.TestCase):
    def test_screen_pascal_case_is_rejected(self):
        spec = _base_spec(
            [{"regionId": "detailPane", "screen": "OrderDetail"}]
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].screen")
        self.assertTrue(errs, "expected error on PascalCase screen value")
        self.assertIn("snake_case", errs[0].message)

    def test_region_id_snake_case_is_rejected(self):
        # regionId must be camelCase (matches Layout JSON id convention).
        spec = _base_spec(
            [{"regionId": "detail_pane", "screen": "order_detail"}]
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].regionId")
        self.assertTrue(errs, "expected error on snake_case regionId")
        self.assertIn("camelCase", errs[0].message)

    def test_params_key_non_camel_is_rejected(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "params": {"Order_Id": "literal"},
            }],
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].params.Order_Id")
        self.assertTrue(errs, "expected error on non-camelCase params key")

    def test_events_key_without_on_prefix_is_rejected(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "events": {"orderUpdated": "handleOrderUpdated"},
            }],
            vm_methods=[{"name": "handleOrderUpdated", "returnType": "Void"}],
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].events.orderUpdated")
        self.assertTrue(errs, "expected error on event key missing on prefix")


class EmbedReferenceResolution(unittest.TestCase):
    def test_unknown_binding_var_is_rejected(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "params": {"orderId": "@{noSuchVar}"},
            }],
            ui_vars=[
                {"name": "selectedOrderId", "type": "String",
                 "description": "."},
            ],
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].params.orderId")
        self.assertTrue(errs, "expected error on unknown binding var")
        self.assertIn("noSuchVar", errs[0].message)

    def test_unknown_event_handler_is_rejected(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "events": {"onOrderUpdated": "handleSomethingElse"},
            }],
            vm_methods=[{"name": "handleOrderUpdated", "returnType": "Void"}],
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].events.onOrderUpdated")
        self.assertTrue(errs, "expected error on unknown handler name")

    def test_known_binding_resolves(self):
        spec = _base_spec(
            embeds=[{
                "regionId": "detailPane",
                "screen": "order_detail",
                "params": {"orderId": "@{selectedOrderId}"},
            }],
            ui_vars=[
                {"name": "selectedOrderId", "type": "String",
                 "description": "."},
            ],
        )
        result = SpecValidator().validate_data(spec)
        self.assertEqual(_errors_at(result, "structure.embeds[0].params"), [])


class EmbedNavigationMode(unittest.TestCase):
    def test_invalid_navigation_mode_is_rejected(self):
        spec = _base_spec(
            [{"regionId": "detailPane", "screen": "order_detail",
              "navigationMode": "shared"}]
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].navigationMode")
        self.assertTrue(errs, "expected error on invalid navigationMode")

    def test_isolated_navigation_mode_is_rejected_in_v1(self):
        # 'isolated' is deferred to v1.5; v1 accepts 'delegate' only.
        spec = _base_spec(
            [{"regionId": "detailPane", "screen": "order_detail",
              "navigationMode": "isolated"}]
        )
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0].navigationMode")
        self.assertTrue(errs,
                        "expected error on 'isolated' navigationMode (v1)")

    def test_default_navigation_mode_omitted_is_ok(self):
        spec = _base_spec(
            [{"regionId": "detailPane", "screen": "order_detail"}]
        )
        result = SpecValidator().validate_data(spec)
        self.assertEqual(_errors_at(result, "navigationMode"), [])


class EmbedUniqueness(unittest.TestCase):
    def test_duplicate_region_id_is_rejected(self):
        spec = _base_spec([
            {"regionId": "detailPane", "screen": "order_detail"},
            {"regionId": "detailPane", "screen": "customer_detail"},
        ])
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[1].regionId")
        self.assertTrue(errs, "expected duplicate-regionId error")
        self.assertIn("Duplicate", errs[0].message)


class EmbedStructuralErrors(unittest.TestCase):
    def test_embeds_not_array_is_rejected(self):
        spec = _base_spec([])
        spec["structure"]["embeds"] = {"regionId": "detailPane"}  # not a list
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds")
        self.assertTrue(errs)

    def test_embed_entry_not_object_is_rejected(self):
        spec = _base_spec(["not-an-object"])
        result = SpecValidator().validate_data(spec)
        errs = _errors_at(result, "structure.embeds[0]")
        self.assertTrue(errs)


if __name__ == "__main__":
    unittest.main()
