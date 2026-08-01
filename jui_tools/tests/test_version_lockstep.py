"""Version lockstep: every version the toolchain reports comes from one file.

The single source of truth is ``<repo>/VERSION`` (plan 06 §1). The Python side
derives from it at run/install time (``jui_cli.version``, ``setup.py``); the
Ruby tools carry literal constants because their consumer-project copies must
work without the root file. Those literals are what this test locks: a bump
that misses one of them fails here instead of shipping a toolchain that
reports different versions depending on which binary you ask.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from jui_cli.version import toolchain_version

REPO_ROOT = Path(__file__).resolve().parents[2]

RUBY_VERSION_RE = re.compile(r"VERSION\s*=\s*'([^']+)'")


def _ruby_constant(relative: str) -> str:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    match = RUBY_VERSION_RE.search(text)
    if match is None:
        raise AssertionError(f"no VERSION constant found in {relative}")
    return match.group(1)


class VersionLockstepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    def test_root_version_is_semver(self) -> None:
        self.assertRegex(self.root_version, r"^\d+\.\d+\.\d+$")

    def test_python_side_derives_from_root(self) -> None:
        self.assertEqual(toolchain_version(REPO_ROOT), self.root_version)

    def test_setup_py_has_no_version_literal(self) -> None:
        text = (REPO_ROOT / "jui_tools" / "setup.py").read_text(encoding="utf-8")
        self.assertIn("version=_VERSION", text)
        self.assertNotRegex(text, r"version\s*=\s*[\"']\d")

    def test_sjui_constant_matches_root(self) -> None:
        self.assertEqual(_ruby_constant("sjui_tools/lib/cli/version.rb"), self.root_version)

    def test_kjui_constant_matches_root(self) -> None:
        self.assertEqual(_ruby_constant("kjui_tools/lib/cli/version.rb"), self.root_version)

    def test_rjui_version_file_matches_root(self) -> None:
        rjui = (REPO_ROOT / "rjui_tools" / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(rjui, self.root_version)


if __name__ == "__main__":
    unittest.main()
