"""Regression: jui-screen-id-space-changes-escape-the-gates-their-author-runs.

Flow steps name screens by id. The gate that checks those references is
`jsonui-test validate`, which the author of a layout change has no reason to
run — a consumer declared one screen `"role": "cell"`, watched build, verify
and lint-strings stay green, and met the resulting errors later while
suspecting an unrelated toolchain update.

`jui verify` cannot check the references (where a screen id may appear inside
a test file is the test tool's business, and a second implementation would
drift from the first). It can say that the id space moved, and name the gate.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jui_cli.commands.verify_cmd import _screen_id_space_changes  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True)


def _layout(role: str | None = None) -> str:
    doc: dict = {"type": "SafeAreaView", "child": []}
    if role:
        doc["role"] = role
    return json.dumps(doc) + "\n"


class ScreenIdSpaceNoticeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.layouts = self.repo / "layouts"
        self.layouts.mkdir()
        # A tree outside the layout root, to prove the notice is scoped.
        (self.repo / "other").mkdir()
        (self.repo / "other" / "config.json").write_text("{}\n", encoding="utf-8")
        (self.layouts / "home.json").write_text(_layout(), encoding="utf-8")
        (self.layouts / "detail.json").write_text(_layout(), encoding="utf-8")
        _git(self.repo, "init", "-q", ".")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def changes(self) -> list[str]:
        return _screen_id_space_changes(self.layouts)

    def test_a_clean_tree_says_nothing(self):
        self.assertEqual(self.changes(), [])

    def test_a_role_declaration_is_a_move(self):
        (self.layouts / "detail.json").write_text(_layout("cell"), encoding="utf-8")
        self.assertEqual(self.changes(), ["detail (role changed)"])

    def test_an_added_layout_is_a_move(self):
        # Not `settings.json`: a global gitignore commonly covers that name,
        # and an ignored fixture reports a silence the code did not produce.
        (self.layouts / "profile.json").write_text(_layout(), encoding="utf-8")
        self.assertEqual(self.changes(), ["profile (added)"])

    def test_a_deleted_layout_is_a_move(self):
        (self.layouts / "detail.json").unlink()
        self.assertEqual(self.changes(), ["detail (deleted)"])

    def test_a_renamed_layout_is_a_move(self):
        _git(self.repo, "mv", "layouts/detail.json", "layouts/detail_page.json")
        self.assertEqual(self.changes(), ["detail_page (renamed)"])

    def test_editing_the_body_is_not_a_move(self):
        """Normal work must stay quiet, or the notice gets ignored."""
        doc = json.loads((self.layouts / "detail.json").read_text())
        doc["child"] = [{"type": "Label", "text": "x"}]
        (self.layouts / "detail.json").write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.changes(), [])

    def test_a_change_outside_the_layout_root_is_not_a_move(self):
        (self.repo / "other" / "config.json").write_text('{"a":1}\n', encoding="utf-8")
        self.assertEqual(self.changes(), [])

    def test_outside_a_repository_it_is_silent(self):
        """Not every project keeps its layouts in git, and guessing is worse."""
        with TemporaryDirectory() as plain:
            layouts = Path(plain) / "layouts"
            layouts.mkdir()
            (layouts / "a.json").write_text(_layout(), encoding="utf-8")
            self.assertEqual(_screen_id_space_changes(layouts), [])


if __name__ == "__main__":
    unittest.main()
