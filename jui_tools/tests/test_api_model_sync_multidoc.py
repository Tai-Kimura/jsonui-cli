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

from jui_cli.core.api_model_sync import collect_docs, plan_android, plan_ios, plan_web
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


class CrossDocUnionDedupTests(unittest.TestCase):
    """Union files ride the same dedup path as DTOs (plan 02, carry-over
    item 5 from plan 01): shared union emitted once, first doc wins;
    same-name unions with different bodies halt."""

    _PET_UNION = {
        "oneOf": [
            {"$ref": "#/components/schemas/Dog"},
            {"$ref": "#/components/schemas/Cat"},
        ],
        "discriminator": {
            "propertyName": "pet_type",
            "mapping": {
                "dog": "#/components/schemas/Dog",
                "cat": "#/components/schemas/Cat",
            },
        },
    }
    _DOG = {"type": "object", "properties": {"bark_volume": {"type": "integer"}}}
    _CAT = {"type": "object", "properties": {"lives_left": {"type": "integer"}}}

    def test_shared_union_emitted_once_first_doc_wins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_project(Path(tmpdir), {
                "a.json": _swagger({
                    "Pet": self._PET_UNION, "Dog": self._DOG, "Cat": self._CAT,
                    "OwnerA": {
                        "type": "object",
                        "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
                    },
                }),
                "b.json": _swagger({
                    "Pet": self._PET_UNION, "Dog": self._DOG, "Cat": self._CAT,
                    "OwnerB": {
                        "type": "object",
                        "properties": {"pet": {"$ref": "#/components/schemas/Pet"}},
                    },
                }),
            })
            docs = collect_docs(cfg)
            plan = plan_ios(cfg, {"root": "ios"}, docs)
            files = {path.name: source for path, source in plan.expected_files.items()}
            scaffolds = {path.name for path in plan.domain_scaffolds}
        self.assertIn("PetDto.swift", files)
        self.assertIn("a.json", files["PetDto.swift"])
        self.assertNotIn("b.json", files["PetDto.swift"])
        # Union Domain scaffold planned alongside object scaffolds.
        self.assertIn("Pet.swift", scaffolds)

    def test_conflicting_same_name_union_halts_at_collect(self):
        other_union = dict(self._PET_UNION)
        other_union["discriminator"] = {
            "propertyName": "kind",
            "mapping": {
                "dog": "#/components/schemas/Dog",
                "cat": "#/components/schemas/Cat",
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_project(Path(tmpdir), {
                "a.json": _swagger({
                    "Pet": self._PET_UNION, "Dog": self._DOG, "Cat": self._CAT,
                }),
                "b.json": _swagger({
                    "Pet": other_union, "Dog": self._DOG, "Cat": self._CAT,
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


_ATTACHMENT = {
    "type": "object",
    "required": ["id", "data"],
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "data": {"type": "string", "format": "binary"},
        "created_at": {"type": "string", "format": "date-time"},
    },
}


def _build_format_project(
    root: Path,
    api_files: dict[str, dict],
    *,
    api_extra: dict | None = None,
) -> ConfigManager:
    """All-platform project with an ``api`` config block (plan 03 tests)."""
    (root / "jui.config.json").write_text(json.dumps({
        "api_directory": "docs/api",
        "api": api_extra or {},
        "platforms": {
            "ios": {"root": "ios"},
            "android": {"root": "android"},
            "web": {"root": "web"},
        },
    }), encoding="utf-8")
    (root / "ios").mkdir()
    (root / "ios" / "sjui.config.json").write_text(
        json.dumps({"source_directory": ""}), encoding="utf-8"
    )
    (root / "android").mkdir()
    (root / "web").mkdir()
    api_dir = root / "docs" / "api"
    api_dir.mkdir(parents=True)
    for name, data in api_files.items():
        (api_dir / name).write_text(json.dumps(data), encoding="utf-8")
    return ConfigManager(root / "jui.config.json")


class FormatMappingConfigTests(unittest.TestCase):
    """ConfigManager.api_format_mapping — defaults + parsing."""

    def _cfg(self, api_block: dict) -> ConfigManager:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "jui.config.json").write_text(
            json.dumps({"api": api_block}), encoding="utf-8"
        )
        self.addCleanup(self._tmp.cleanup)
        return ConfigManager(root / "jui.config.json")

    def test_default_off(self):
        enabled, excluded = self._cfg({}).api_format_mapping()
        self.assertFalse(enabled)
        self.assertEqual(excluded, frozenset())

    def test_enabled_with_exclude(self):
        enabled, excluded = self._cfg({
            "format_mapping": True,
            "format_mapping_exclude": ["legacy.json"],
        }).api_format_mapping()
        self.assertTrue(enabled)
        self.assertEqual(excluded, frozenset({"legacy.json"}))

    def test_malformed_exclude_ignored(self):
        enabled, excluded = self._cfg({
            "format_mapping": True,
            "format_mapping_exclude": "legacy.json",
        }).api_format_mapping()
        self.assertTrue(enabled)
        self.assertEqual(excluded, frozenset())


class FormatSupportFilePlanTests(unittest.TestCase):
    """Shared support files enter the plan exactly when a mapped doc uses
    the format (plan 03) — per-doc opt-out keeps an excluded doc from
    forcing them in."""

    def _plan_names(self, plan) -> set[str]:
        return {p.name for p in plan.expected_files}

    def test_support_files_planned_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_format_project(
                Path(tmpdir),
                {"a.json": _swagger({"Attachment": _ATTACHMENT})},
                api_extra={
                    "format_mapping": True,
                    "platforms": {"android": {"serializer": "kotlinx"}},
                },
            )
            docs = collect_docs(cfg)
            android = plan_android(cfg, {"root": "android"}, docs)
            web = plan_web(cfg, {"root": "web"}, docs)
            ios = plan_ios(cfg, {"root": "ios"}, docs)
        self.assertIn("Uuid.kt", self._plan_names(android))
        self.assertIn("Base64ByteArraySerializer.kt", self._plan_names(android))
        self.assertIn("Uuid.ts", self._plan_names(web))
        self.assertIn("Base64Data.ts", self._plan_names(web))
        # iOS maps to Foundation types — no support files
        self.assertEqual(
            {n for n in self._plan_names(ios) if not n.endswith(".swift")}, set()
        )
        ios_src = next(
            src for p, src in ios.expected_files.items() if p.name == "AttachmentDto.swift"
        )
        self.assertIn("let createdAt: Date?", ios_src)

    def test_support_files_absent_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_format_project(
                Path(tmpdir),
                {"a.json": _swagger({"Attachment": _ATTACHMENT})},
                api_extra={"platforms": {"android": {"serializer": "kotlinx"}}},
            )
            docs = collect_docs(cfg)
            android = plan_android(cfg, {"root": "android"}, docs)
            web = plan_web(cfg, {"root": "web"}, docs)
        for name in ("Uuid.kt", "Base64ByteArraySerializer.kt"):
            self.assertNotIn(name, self._plan_names(android))
        for name in ("Uuid.ts", "Base64Data.ts"):
            self.assertNotIn(name, self._plan_names(web))

    def test_excluded_doc_does_not_force_support_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = _build_format_project(
                Path(tmpdir),
                {"legacy.json": _swagger({"Attachment": _ATTACHMENT})},
                api_extra={
                    "format_mapping": True,
                    "format_mapping_exclude": ["legacy.json"],
                    "platforms": {"android": {"serializer": "kotlinx"}},
                },
            )
            docs = collect_docs(cfg)
            android = plan_android(cfg, {"root": "android"}, docs)
            web = plan_web(cfg, {"root": "web"}, docs)
            ios = plan_ios(cfg, {"root": "ios"}, docs)
        self.assertNotIn("Uuid.kt", self._plan_names(android))
        self.assertNotIn("Uuid.ts", self._plan_names(web))
        ios_src = next(
            src for p, src in ios.expected_files.items() if p.name == "AttachmentDto.swift"
        )
        self.assertNotIn("Date", ios_src)


if __name__ == "__main__":
    unittest.main()
