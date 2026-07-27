"""Cross-language agreement guard for screen identity.

Code generation runs in Ruby (sjui/kjui/rjui) while the diagram, the test
validator and the MCP snapshot run in Python, so the canon in
``shared/core/screen_identity.json`` necessarily has two readers:

* ``jui_tools/jui_cli/core/screen_identity.py``
* ``shared/core/screen_index.rb`` (mirrored into each tool's ``lib/core/``)

Two readers are only safe if something proves they agree. This module is
that proof: it classifies one fixture tree with both and compares the
result field by field, and it pins the three mirrored Ruby copies to the
canonical file so a fix applied to one tool cannot quietly skip the others.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jui_cli.core.screen_identity import build_screen_index

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_RUBY = REPO_ROOT / "shared" / "core" / "screen_index.rb"
LAYOUT_VARIANT_RUBY = REPO_ROOT / "shared" / "core" / "layout_variant.rb"
TOOL_DIRS = ("sjui_tools", "kjui_tools", "rjui_tools")

#: One tree exercising every branch of the classification order: an explicit
#: role that beats derivation, a cell reference, an include, a partial flag,
#: a nested layout, a variant file and a plain screen.
FIXTURE: dict[str, dict] = {
    "home.json": {
        "type": "View",
        "id": "root_view",
        "child": [
            {"type": "Collection", "cellClasses": ["item_cell"]},
            {"type": "View", "include": "shared_header"},
        ],
    },
    "home@regular.json": {"type": "View", "id": "root_view"},
    "settings.json": {"type": "View"},
    "item_cell.json": {"type": "View"},
    "shared_header.json": {"type": "View"},
    "legacy_partial.json": {"type": "View", "partial": True},
    # Explicitly a screen even though something references it as a cell.
    "dual_use.json": {"type": "View", "role": "screen"},
    "referencing.json": {"type": "List", "cell": "dual_use"},
    # Explicitly a cell even though nothing references it.
    "declared_cell.json": {"type": "View", "role": "cell"},
    "nested/detail.json": {"type": "View"},
    "nested/deep/profile.json": {"type": "View"},
}

RUBY_DRIVER = r"""
require 'json'
require_relative ARGV[0] + '/layout_variant.rb'
require_relative ARGV[0] + '/screen_index.rb'

index = JsonUIShared::ScreenIndex.build(ARGV[1], app_owned_screens: JSON.parse(ARGV[2]))
puts JSON.generate(
  'report' => index.classification_report.map { |row| row.reject { |k, _| k == 'path' } },
  'screen_ids' => index.screen_ids,
  'non_screen_ids' => index.non_screen_ids,
  'collisions' => index.collisions.keys.sort,
  'markers' => index.screen_ids.map { |id| index.marker_for(id) }
)
"""


def _ruby_available() -> bool:
    return shutil.which("ruby") is not None


def _write_fixture(root: Path) -> None:
    for rel, payload in FIXTURE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _python_result(layouts: Path, app_owned: list[str]) -> dict:
    index = build_screen_index(layouts, app_owned_screens=app_owned)
    return {
        "report": [
            {k: v for k, v in row.items() if k != "path"}
            for row in index.classification_report()
        ],
        "screen_ids": index.screen_ids,
        "non_screen_ids": index.non_screen_ids,
        "collisions": sorted(index.collisions),
        "markers": [index.entries[i].marker for i in index.screen_ids],
    }


def _ruby_result(layouts: Path, app_owned: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / "driver.rb"
        driver.write_text(RUBY_DRIVER, encoding="utf-8")
        proc = subprocess.run(
            [
                "ruby",
                str(driver),
                str(SHARED_RUBY.parent),
                str(layouts),
                json.dumps(app_owned),
            ],
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise AssertionError(f"ruby reader failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


class RubyMirrorTests(unittest.TestCase):
    """The per-tool copies must be byte-identical to the canonical file."""

    def test_every_tool_carries_the_canonical_copy(self):
        canonical = SHARED_RUBY.read_bytes()
        for tool in TOOL_DIRS:
            copy = REPO_ROOT / tool / "lib" / "core" / "screen_index.rb"
            with self.subTest(tool=tool):
                self.assertTrue(copy.is_file(), f"{tool} is missing screen_index.rb")
                self.assertEqual(
                    copy.read_bytes(),
                    canonical,
                    f"{tool}/lib/core/screen_index.rb drifted from shared/core/screen_index.rb",
                )


class CrossLanguageAgreementTests(unittest.TestCase):
    """The Ruby and Python readers must classify identically."""

    def setUp(self):
        if not _ruby_available():
            # Skipping locally is fine; skipping in CI would mean the guard
            # never actually runs, which is the failure mode it exists to
            # prevent.
            if os.environ.get("CI"):
                self.fail("ruby is required in CI to run the cross-language guard")
            self.skipTest("ruby not installed")
        self._tmp = tempfile.TemporaryDirectory()
        self.layouts = Path(self._tmp.name) / "Layouts"
        self.layouts.mkdir(parents=True)
        _write_fixture(self.layouts)

    def tearDown(self):
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def test_classification_matches(self):
        app_owned: list[str] = []
        self.assertEqual(
            _ruby_result(self.layouts, app_owned),
            _python_result(self.layouts, app_owned),
        )

    def test_app_owned_declarations_match(self):
        app_owned = ["tokushoho", "company", "home"]
        self.assertEqual(
            _ruby_result(self.layouts, app_owned),
            _python_result(self.layouts, app_owned),
        )

    def test_collisions_match(self):
        (self.layouts / "nested" / "settings.json").write_text("{}", encoding="utf-8")
        self.assertEqual(
            _ruby_result(self.layouts, []),
            _python_result(self.layouts, []),
        )

    def test_the_fixture_actually_exercises_every_reason(self):
        # A guard on the guard: if the fixture stops covering a branch, the
        # agreement test would pass without testing anything interesting.
        reasons = {row["reason"] for row in _python_result(self.layouts, [])["report"]}
        self.assertEqual(
            reasons, {"explicit", "referenced", "partial-flag", "default"}
        )


if __name__ == "__main__":
    unittest.main()
