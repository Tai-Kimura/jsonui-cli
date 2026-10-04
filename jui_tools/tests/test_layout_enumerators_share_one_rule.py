"""Every layout enumerator reads one rule: a .json is no layout when a
directory between the layout root and it is one of the canon's
screenId.nonLayoutSubtrees (Resources, Styles).

Ticket layout-enumerators-count-resources-json-as-layouts: verify's
screen-id-space notice took every *.json from git status, lint-strings skipped
a top-level Resources only, lint-generated and build's isolated-embed check
looked at every part of the ABSOLUTE path, and the Ruby tools spelled
`file.include?('/Resources/')` (a Resources directory above the root hid every
layout; Styles counted as a layout) — each a copy of the rule, drifting.

The rule is the canon (shared/core/screen_identity.json). Python reads it at
import (jui_cli.core.screen_identity.non_layout_subtrees / is_layout_path).
The Ruby reader keeps a constant (shared/core/screen_index.rb, mirrored into
each platform tool, which ships without shared/core) and
ScreenIndex.layout_path?; this file holds that constant to the canon and the
enumerators to the readers.
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from jui_cli.core.screen_identity import is_layout_path, non_layout_subtrees

REPO = Path(__file__).resolve().parents[2]
CANON = json.loads((REPO / "shared/core/screen_identity.json").read_text(encoding="utf-8"))


class OneRule(unittest.TestCase):
    def test_python_reads_the_canon(self):
        self.assertEqual(non_layout_subtrees(), frozenset(CANON["screenId"]["nonLayoutSubtrees"]))

    def test_the_ruby_constant_is_the_canon_in_every_copy(self):
        for path in [REPO / "shared/core/screen_index.rb",
                     *[REPO / f"{t}_tools/lib/core/screen_index.rb" for t in ("kjui", "sjui", "rjui")]]:
            words = re.search(r"NON_LAYOUT_SUBTREES = %w\[([^\]]*)\]", path.read_text(encoding="utf-8")).group(1).split()
            self.assertEqual(set(words), set(CANON["screenId"]["nonLayoutSubtrees"]), str(path))

    def test_the_rule_is_relative_to_the_root_at_any_depth(self):
        self.assertTrue(is_layout_path("/p/Resources/layouts/home.json", "/p/Resources/layouts"))
        self.assertTrue(is_layout_path("/p/layouts/sheets/detail.json", "/p/layouts"))
        self.assertFalse(is_layout_path("/p/layouts/Resources/strings.json", "/p/layouts"))
        self.assertFalse(is_layout_path("/p/layouts/sheets/Styles/card.json", "/p/layouts"))

    def test_the_ruby_reader_answers_the_same(self):
        cases = [("/p/Resources/layouts", "/p/Resources/layouts/home.json", True),
                 ("/p/layouts", "/p/layouts/sheets/detail.json", True),
                 ("/p/layouts", "/p/layouts/Resources/strings.json", False),
                 ("/p/layouts/", "/p/layouts/sheets/Styles/card.json", False)]
        driver = ("require File.join(ARGV[0], 'layout_variant'); require File.join(ARGV[0], 'screen_index'); "
                  "ARGV.drop(1).each_slice(2) { |r, p| puts JsonUIShared::ScreenIndex.layout_path?(r, p) }")
        args = [str(REPO / "shared/core")] + [x for r, p, _ in cases for x in (r, p)]
        out = subprocess.run(["ruby", "-e", driver, *args], capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(out, [str(want).lower() for _, _, want in cases])
        for root, path, want in cases:
            self.assertEqual(is_layout_path(path, root), want, path)

    # The census, kept: no enumerator spells the rule itself again. (kjui's
    # XML mode is frozen and left as it is.)
    def test_no_hand_written_copy_of_the_rule_is_left(self):
        grep = subprocess.run(
            ["git", "-C", str(REPO), "grep", "-nE",
             r"""include\?\(['"]/(Resources|Styles)/|include\?\(File\.join\([^)]*'(Resources|Styles)'\)|start_with\?\('Resources/'|"Resources" in [a-z_]+\.parts|skip_prefixes = \{"Resources"\}\s*$|_is_resource_or_style""",
             "--", "jui_tools/jui_cli", "test_tools/jsonui_test_cli", "document_tools/jsonui_doc_cli",
             "kjui_tools/lib", "sjui_tools/lib", "rjui_tools/lib", "shared/core",
             ":!kjui_tools/lib/xml", ":!jui_tools/jui_cli/commands/build_cmd.py"],
            capture_output=True, text=True)
        hits = [l for l in grep.stdout.splitlines() if not re.match(r"^[^:]+:\d+:\s*#", l)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
