"""`jui init` bootstraps a new sub-project inside a monorepo.

Double-init protection judged "is there a config already?" with the same
ancestor-walking resolver the read-side commands use, so a monorepo's
root config (a normal layout: one root config plus one per sub-project)
blocked `jui init` in a fresh sub-directory with "already exists at
<repo root>" — refusing to create the very file whose absence made the
walk reach the ancestor in the first place. The reporting consumer's
fourth sub-project had to be assembled by hand from a sibling's config.

Ancestor walking stays correct for read-side commands (declarations are
authoritative there); init is a creation command, so the only config
whose existence means "already initialized" is the one at the target
path itself.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jui_cli.commands.init_cmd import cmd_init


def _args(**overrides) -> argparse.Namespace:
    base = dict(project_name="sub", ios=None, ios_mode="swiftui",
                android=None, android_mode="compose", package_name=None,
                web=None, no_sync_tools=True)
    base.update(overrides)
    return argparse.Namespace(**base)


class InitInAMonorepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self._old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def _run_in(self, cwd: Path) -> tuple[int, str]:
        cwd.mkdir(parents=True, exist_ok=True)
        os.chdir(cwd)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmd_init(_args())
        return code, out.getvalue()

    def test_an_ancestor_config_does_not_block_a_new_sub_project(self):
        (self.root / "jui.config.json").write_text(
            json.dumps({"project_name": "backend"}), encoding="utf-8")
        code, out = self._run_in(self.root / "admin")

        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "admin" / "jui.config.json").exists())
        # The ancestor is acknowledged, not silently ignored — and it is
        # named as an ancestor, so the message cannot be read as "the
        # target directory already has a config".
        self.assertIn("ancestor", out)
        self.assertIn(str(self.root / "jui.config.json"), out)
        # The root config is untouched.
        root_cfg = json.loads(
            (self.root / "jui.config.json").read_text(encoding="utf-8"))
        self.assertEqual(root_cfg, {"project_name": "backend"})

    def test_a_config_in_the_target_directory_still_refuses(self):
        """The protection the fix must not remove, mirrored."""
        target = self.root / "admin"
        target.mkdir()
        (target / "jui.config.json").write_text(
            json.dumps({"project_name": "already"}), encoding="utf-8")
        code, out = self._run_in(target)

        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        self.assertIn(str(target / "jui.config.json"), out)
        kept = json.loads(
            (target / "jui.config.json").read_text(encoding="utf-8"))
        self.assertEqual(kept, {"project_name": "already"})

    def test_a_plain_directory_init_prints_no_ancestor_note(self):
        code, out = self._run_in(self.root / "solo")
        self.assertEqual(code, 0, out)
        self.assertNotIn("ancestor", out)


if __name__ == "__main__":
    unittest.main()
