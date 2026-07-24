"""Sync-layer tests for multi-doc emission (plan 2026-07-24-v1-unsupported/01).

Covers the build-layer half of the Q12 lift:

- cross-doc dedup: a shared schema referenced from several docs is emitted
  exactly once, first doc in sorted order wins (deterministic source
  comment)
- split/inline equivalence (E2E): a 2-file fixture (main + fragment)
  produces byte-identical plan output to the inlined 1-file version
- conflicting same-name schemas across docs halt at collect time
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.api_model_sync import collect_docs, plan_ios
from jui_cli.core.config_manager import ConfigManager
from jui_cli.core.openapi_loader import OpenAPILoadError


def _swagger(schemas: dict) -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Test", "version": "1.0.0"},
        "components": {"schemas": schemas},
    }


_MONEY = {
    "type": "object",
    "properties": {
        "amount": {"type": "integer"},
        "currency": {"type": "string"},
    },
}


def _build_project(root: Path, api_files: dict[str, dict]) -> ConfigManager:
    """Minimal iOS-only project with the given docs/api contents."""
    (root / "jui.config.json").write_text(json.dumps({
        "api_directory": "docs/api",
        "platforms": {"ios": {"root": "ios"}},
    }), encoding="utf-8")
    (root / "ios").mkdir()
    (root / "ios" / "sjui.config.json").write_text(
        json.dumps({"source_directory": ""}), encoding="utf-8"
    )
    api_dir = root / "docs" / "api"
    api_dir.mkdir(parents=True)
    for name, data in api_files.items():
        (api_dir / name).write_text(json.dumps(data), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


def _plan_by_basename(config_mgr: ConfigManager) -> dict[str, str]:
    docs = collect_docs(config_mgr)
    plan = plan_ios(config_mgr, {"root": "ios"}, docs)
    return {path.name: source for path, source in plan.expected_files.items()}


class CrossDocDedupTests(unittest.TestCase):
    def test_shared_schema_emitted_once_first_doc_wins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_project(Path(tmpdir), {
                "a.json": _swagger({
                    "OrderA": {
                        "type": "object",
                        "properties": {
                            "m": {"$ref": "./common.json#/components/schemas/Money"},
                        },
                    },
                }),
                "b.json": _swagger({
                    "OrderB": {
                        "type": "object",
                        "properties": {
                            "m": {"$ref": "./common.json#/components/schemas/Money"},
                        },
                    },
                }),
                "common.json": {"components": {"schemas": {"Money": _MONEY}}},
            })
            files = _plan_by_basename(cfg)
        self.assertEqual(
            set(files), {"OrderADto.swift", "OrderBDto.swift", "MoneyDto.swift"}
        )
        # Deterministic first-win: the shared DTO's Source: comment points
        # at the first doc in sorted order (a.json), not the last one.
        self.assertIn("a.json", files["MoneyDto.swift"])
        self.assertNotIn("b.json", files["MoneyDto.swift"])

    def test_conflicting_same_name_halts_at_collect(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_project(Path(tmpdir), {
                "a.json": _swagger({
                    "User": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                    },
                }),
                "b.json": _swagger({
                    "User": {
                        "type": "object",
                        "properties": {"uid": {"type": "integer"}},
                    },
                }),
            })
            with self.assertRaises(OpenAPILoadError) as ctx:
                collect_docs(cfg)
            self.assertEqual(ctx.exception.code, "cross-doc-schema-conflict")


class SplitInlineEquivalenceTests(unittest.TestCase):
    def test_two_file_fixture_matches_inlined_single_file(self):
        """E2E acceptance for P2: `jui build` plan output of the split
        fixture is byte-identical to the inlined one-file version."""
        order_split = {
            "Order": {
                "type": "object",
                "required": ["total"],
                "properties": {
                    "total": {"$ref": "./common.json#/components/schemas/Money"},
                    "note": {"type": "string"},
                },
            },
        }
        order_inline = {
            "Order": {
                "type": "object",
                "required": ["total"],
                "properties": {
                    "total": {"$ref": "#/components/schemas/Money"},
                    "note": {"type": "string"},
                },
            },
            "Money": _MONEY,
        }
        with tempfile.TemporaryDirectory() as d_split, \
                tempfile.TemporaryDirectory() as d_inline:
            cfg_split = _build_project(Path(d_split), {
                "main.json": _swagger(order_split),
                "common.json": {"components": {"schemas": {"Money": _MONEY}}},
            })
            cfg_inline = _build_project(Path(d_inline), {
                "main.json": _swagger(order_inline),
            })
            files_split = _plan_by_basename(cfg_split)
            files_inline = _plan_by_basename(cfg_inline)
        self.assertEqual(files_split, files_inline)


if __name__ == "__main__":
    unittest.main()
