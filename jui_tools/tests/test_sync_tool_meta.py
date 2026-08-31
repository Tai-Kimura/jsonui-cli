"""Tests for ``jui sync_tool``'s toolchain-coordinate stamp (plan 06 §1).

``_write_sync_meta`` records version + source SHA of the sync source into
``<project>/.jsonui-cli/sync-meta.json`` so consumer bug reports can name the
exact toolchain their generated code came from. The source of those
coordinates is the root ``VERSION`` file plus the ``SOURCE_SHA`` stamp
(``installer/bootstrap.sh`` writes it before deleting ``.git``; a dev
checkout answers from git directly).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jui_cli.commands.sync_tool_cmd import (
    SYNC_META_DIRNAME,
    SYNC_META_FILENAME,
    _write_sync_meta,
)

SHA = "0123456789abcdef0123456789abcdef01234567"


def _make_source(root: Path, *, version: str | None = "1.1.0", sha: str | None = SHA) -> Path:
    root.mkdir(parents=True)
    if version is not None:
        (root / "VERSION").write_text(f"{version}\n")
    if sha is not None:
        (root / "SOURCE_SHA").write_text(f"{sha}\n")
    return root


def _read_meta(project_root: Path) -> dict:
    path = project_root / SYNC_META_DIRNAME / SYNC_META_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


class WriteSyncMetaTest(unittest.TestCase):
    def test_stamps_version_and_sha_per_platform(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "project"
            project.mkdir()

            path, changed = _write_sync_meta(
                project, source, {"ios": "sjui_tools", "web": "rjui_tools"}, dry_run=False
            )

            self.assertTrue(changed)
            self.assertEqual(path, project / SYNC_META_DIRNAME / SYNC_META_FILENAME)
            meta = _read_meta(project)
            self.assertEqual(sorted(meta["platforms"]), ["ios", "web"])
            ios = meta["platforms"]["ios"]
            self.assertEqual(ios["tool"], "sjui_tools")
            self.assertEqual(ios["version"], "1.1.0")
            self.assertEqual(ios["sourceSha"], SHA)

    def test_merge_preserves_other_platform_entries(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_old = _make_source(root / "old", version="1.0.0", sha="a" * 40)
            source_new = _make_source(root / "new", version="1.1.0", sha="b" * 40)
            project = root / "project"
            project.mkdir()

            _write_sync_meta(project, source_old, {"ios": "sjui_tools"}, dry_run=False)
            _write_sync_meta(project, source_new, {"web": "rjui_tools"}, dry_run=False)

            meta = _read_meta(project)
            # ios keeps the coordinates it was actually synced at…
            self.assertEqual(meta["platforms"]["ios"]["version"], "1.0.0")
            self.assertEqual(meta["platforms"]["ios"]["sourceSha"], "a" * 40)
            # …and web records the newer source.
            self.assertEqual(meta["platforms"]["web"]["version"], "1.1.0")
            self.assertEqual(meta["platforms"]["web"]["sourceSha"], "b" * 40)

    def test_second_identical_sync_reports_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "project"
            project.mkdir()

            _, first = _write_sync_meta(project, source, {"ios": "sjui_tools"}, dry_run=False)
            _, second = _write_sync_meta(project, source, {"ios": "sjui_tools"}, dry_run=False)
            self.assertTrue(first)
            self.assertFalse(second)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "project"
            project.mkdir()

            path, changed = _write_sync_meta(
                project, source, {"ios": "sjui_tools"}, dry_run=True
            )
            self.assertTrue(changed)
            self.assertFalse(path.exists())

    def test_unstamped_source_records_unknowns(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src", version=None, sha=None)
            project = root / "project"
            project.mkdir()

            _write_sync_meta(project, source, {"android": "kjui_tools"}, dry_run=False)
            entry = _read_meta(project)["platforms"]["android"]
            self.assertEqual(entry["version"], "unknown")
            self.assertIsNone(entry["sourceSha"])

    def test_corrupt_existing_meta_is_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "project"
            meta_dir = project / SYNC_META_DIRNAME
            meta_dir.mkdir(parents=True)
            (meta_dir / SYNC_META_FILENAME).write_text("{not json")

            _, changed = _write_sync_meta(project, source, {"ios": "sjui_tools"}, dry_run=False)
            self.assertTrue(changed)
            self.assertEqual(_read_meta(project)["platforms"]["ios"]["version"], "1.1.0")

    def test_content_is_deterministic_apart_from_the_stamp(self):
        """Two fresh projects agree on everything except `syncedAt`.

        The stamp is wall-clock, so this compared equal only while both
        writes landed inside the same second — it passed, and would have
        started failing at a second boundary. Determinism is now claimed of
        the coordinates, which is what the property was for: a consumer's
        git status must not churn because two syncs ran at different times.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            p1, p2 = root / "p1", root / "p2"
            p1.mkdir()
            p2.mkdir()

            _write_sync_meta(p1, source, {"ios": "sjui_tools"}, dry_run=False)
            _write_sync_meta(p2, source, {"ios": "sjui_tools"}, dry_run=False)
            a = _read_meta(p1)["platforms"]["ios"]
            b = _read_meta(p2)["platforms"]["ios"]
            self.assertEqual({k: v for k, v in a.items() if k != "syncedAt"},
                             {k: v for k, v in b.items() if k != "syncedAt"})
            self.assertIn("syncedAt", a)

    def test_a_resync_of_the_same_coordinates_keeps_the_stamp(self):
        """`syncedAt` answers "when did THIS version arrive".

        Refreshing it on every sync would churn the consumer's git status on
        every run, which is the property the file was written not to have.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "p"
            project.mkdir()
            _write_sync_meta(project, source, {"ios": "sjui_tools"}, dry_run=False)
            first = _read_meta(project)["platforms"]["ios"]["syncedAt"]

            _, changed = _write_sync_meta(project, source, {"ios": "sjui_tools"},
                                          dry_run=False)
            self.assertFalse(changed, "same coordinates must not rewrite")
            self.assertEqual(
                _read_meta(project)["platforms"]["ios"]["syncedAt"], first)

    def test_a_new_version_moves_the_stamp(self):
        """The control: without it, "the stamp is stable" and "the stamp is
        never written" are the same observation."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = _make_source(root / "src")
            project = root / "p"
            project.mkdir()
            meta_dir = project / SYNC_META_DIRNAME
            meta_dir.mkdir(parents=True)
            old = "2020-01-01T00:00:00+00:00"
            (meta_dir / SYNC_META_FILENAME).write_text(json.dumps({"platforms": {
                "ios": {"tool": "sjui_tools", "version": "0.0.1",
                        "sourceSha": "deadbeef", "sourceRoot": "~/x",
                        "syncedAt": old}}}))

            _, changed = _write_sync_meta(project, source, {"ios": "sjui_tools"},
                                          dry_run=False)
            self.assertTrue(changed)
            entry = _read_meta(project)["platforms"]["ios"]
            self.assertNotEqual(entry["syncedAt"], old)


if __name__ == "__main__":
    unittest.main()
