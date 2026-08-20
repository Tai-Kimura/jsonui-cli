"""Version lockstep: every version the toolchain reports comes from one file.

The single source of truth is ``<repo>/VERSION`` (plan 06 §1). The Python side
derives from it at run/install time (``jui_cli.version``, ``setup.py``); the
Ruby tools carry literal constants because their consumer-project copies must
work without the root file. Those literals are what this test locks: a bump
that misses one of them fails here instead of shipping a toolchain that
reports different versions depending on which binary you ask.

The same rule covers the one place a package here INSTALLS a sibling by
version: ``jsonui-doc-cli`` reaches ``jsonui-test-cli`` through a direct git
URL, and an unpinned one resolved to the default branch even when the
install itself named a tag — so a consumer CI that pinned the tool by tag
still got a moving tool (reported 2026-08-20).
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from jui_cli.version import toolchain_version

REPO_ROOT = Path(__file__).resolve().parents[2]

RUBY_VERSION_RE = re.compile(r"VERSION\s*=\s*'([^']+)'")

SIBLING_URL = "git+https://github.com/Tai-Kimura/jsonui-cli.git"
# "...jsonui-cli.git@v1.2.3#subdirectory=test_tools"
PINNED_URL_RE = re.compile(
    re.escape(SIBLING_URL) + r"@(?P<rev>[^#\s\"']+)#subdirectory=")


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


class SiblingGitPinTests(unittest.TestCase):
    """The in-repo git dependency ships at the same tag as its dependent."""

    def setUp(self) -> None:
        self.expected_rev = "v" + (REPO_ROOT / "VERSION").read_text(
            encoding="utf-8").strip()

    def _declarations(self) -> list[tuple[str, str]]:
        """(file, line) for every tracked declaration of this repo's URL."""
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "-z"], cwd=REPO_ROOT, check=True,
                capture_output=True, text=True, timeout=60).stdout.split("\0")
        except (OSError, subprocess.SubprocessError):
            self.skipTest("not a git checkout")
        found = []
        for name in tracked:
            if not name or not re.search(r"\.(toml|txt|cfg)$", name):
                continue
            try:
                text = (REPO_ROOT / name).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line in text.splitlines():
                if SIBLING_URL in line and not line.lstrip().startswith("#"):
                    found.append((name, line.strip()))
        return found

    def test_doc_cli_pins_its_sibling_to_the_root_version(self) -> None:
        decls = self._declarations()
        self.assertTrue(
            any(name == "document_tools/pyproject.toml" for name, _ in decls),
            f"jsonui-doc-cli no longer declares the sibling: {decls}")
        for name, line in decls:
            match = PINNED_URL_RE.search(line)
            self.assertIsNotNone(
                match,
                f"{name} declares this repo's git URL with no rev, so it "
                f"resolves to the default branch:\n  {line}")
            self.assertEqual(
                match.group("rev"), self.expected_rev,
                f"{name} pins {match.group('rev')} but VERSION says "
                f"{self.expected_rev} — a release bump has to move this pin "
                "too, or the tag ships a sibling from another release")


if __name__ == "__main__":
    unittest.main()
