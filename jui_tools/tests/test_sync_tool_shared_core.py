"""Tests for ``jui sync_tool`` distributing CLI-root shared/core payloads.

Covers the font_weight_mapping.json distribution fix: the tool font helpers
resolve ``<tool_dir>/shared/core/font_weight_mapping.json`` first, but that
path is a SIBLING of the mirrored tool tree, so ``sync_tool`` must place it
explicitly. Without it, sjui rounds every looked-up weight to ``.regular`` in
consumers.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import (
    SHARED_CORE_PAYLOADS,
    _distribute_shared_core,
    _sync_one_tool,
)


def _make_source(root: Path) -> Path:
    """Build a minimal ~/.jsonui-cli-shaped source root with a tool + shared/core."""
    tool = root / "sjui_tools"
    (tool / "lib" / "swiftui" / "helpers").mkdir(parents=True)
    (tool / "lib" / "swiftui" / "helpers" / "font_helper.rb").write_text("# helper\n")
    core = root / "shared" / "core"
    core.mkdir(parents=True)
    (core / "font_weight_mapping.json").write_text('{"weights": {"bold": {"swift": ".bold"}}}\n')
    return root


class DistributeSharedCoreTest(unittest.TestCase):
    def test_font_weight_mapping_is_declared_payload(self):
        self.assertIn("font_weight_mapping.json", SHARED_CORE_PAYLOADS)

    def test_copies_shared_core_payload_into_tool(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = _make_source(root / "src")
            target_tool = root / "project" / "ios" / "sjui_tools"
            target_tool.mkdir(parents=True)

            changed = _distribute_shared_core(source_root, target_tool, dry_run=False)

            dst = target_tool / "shared" / "core" / "font_weight_mapping.json"
            self.assertEqual(changed, 1)
            self.assertTrue(dst.exists())
            self.assertEqual(
                dst.read_text(),
                (source_root / "shared" / "core" / "font_weight_mapping.json").read_text(),
            )

    def test_idempotent_second_run_copies_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = _make_source(root / "src")
            target_tool = root / "project" / "ios" / "sjui_tools"
            target_tool.mkdir(parents=True)

            _distribute_shared_core(source_root, target_tool, dry_run=False)
            changed = _distribute_shared_core(source_root, target_tool, dry_run=False)
            self.assertEqual(changed, 0)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = _make_source(root / "src")
            target_tool = root / "project" / "ios" / "sjui_tools"
            target_tool.mkdir(parents=True)

            changed = _distribute_shared_core(source_root, target_tool, dry_run=True)
            self.assertEqual(changed, 1)
            self.assertFalse((target_tool / "shared" / "core" / "font_weight_mapping.json").exists())

    def test_missing_source_payload_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # source without shared/core
            source_root = root / "src"
            source_root.mkdir()
            target_tool = root / "project" / "ios" / "sjui_tools"
            target_tool.mkdir(parents=True)

            changed = _distribute_shared_core(source_root, target_tool, dry_run=False)
            self.assertEqual(changed, 0)


class SyncOneToolSharedCoreTest(unittest.TestCase):
    def test_sync_one_tool_distributes_and_prune_preserves(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = _make_source(root / "src")
            src_tool = source_root / "sjui_tools"
            platform_root = root / "project" / "ios"
            platform_root.mkdir(parents=True)
            dst_tool = platform_root / "sjui_tools"

            counters = _sync_one_tool(
                src_tool, dst_tool, platform_root,
                prune=True, dry_run=False, source_root=source_root,
            )

            font = dst_tool / "shared" / "core" / "font_weight_mapping.json"
            self.assertEqual(counters["shared_core"], 1)
            self.assertTrue(font.exists())
            # The tool tree itself was mirrored too.
            self.assertTrue((dst_tool / "lib" / "swiftui" / "helpers" / "font_helper.rb").exists())

            # Second sync with prune must NOT delete the distributed shared/core
            # file even though it lives outside the mirrored tool tree.
            counters2 = _sync_one_tool(
                src_tool, dst_tool, platform_root,
                prune=True, dry_run=False, source_root=source_root,
            )
            self.assertEqual(counters2["shared_core"], 0)
            self.assertTrue(font.exists())

    def test_sync_one_tool_without_source_root_skips_distribution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = _make_source(root / "src")
            src_tool = source_root / "sjui_tools"
            platform_root = root / "project" / "ios"
            platform_root.mkdir(parents=True)
            dst_tool = platform_root / "sjui_tools"

            counters = _sync_one_tool(
                src_tool, dst_tool, platform_root,
                prune=False, dry_run=False, source_root=None,
            )
            self.assertEqual(counters["shared_core"], 0)
            self.assertFalse((dst_tool / "shared" / "core" / "font_weight_mapping.json").exists())


if __name__ == "__main__":
    unittest.main()
