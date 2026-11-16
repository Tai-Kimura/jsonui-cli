"""One display-text vocabulary for jui lint-strings and both converter scaffolds.

Ruling 2026-10-03 (kjui-custom-component-string-literal-prop-is-read-as-a-string-key):
a custom component's literal String prop is a strings.json key on iOS and
Android exactly when its NAME is in ``STRING_PROPERTIES`` — the list
``jui lint-strings`` checks — and ``accessibilityLabel`` joins that list. So the
three readers must see one list, not copies that drift:

- lint-strings parses ``STRING_PROPERTIES`` out of ``string_manager_core.rb``
  (load_string_props);
- the kjui and sjui converter scaffolds ask
  ``JsonUIShared::StringManagerCore.localized_prop?``, which reads the same
  constant, from each tool's copy of that file (byte-identical to
  shared/core by each tool's shared_core_mirror_spec).

This arm asks each reader for its list and compares them, and pins that the
scaffolds ask the predicate rather than spelling names of their own.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from jui_cli.commands.lint_strings_cmd import load_string_props

REPO = Path(__file__).resolve().parents[2]


def _ruby_vocabulary(tool: str) -> list[str]:
    lib = REPO / tool / "lib" / "core"
    script = (
        f"require {str(lib / 'string_manager_core.rb')!r}; "
        "v = JsonUIShared::StringManagerCore::STRING_PROPERTIES; "
        "abort 'predicate disagrees' unless v.all? { |n| JsonUIShared::StringManagerCore.localized_prop?(n) } "
        "&& !JsonUIShared::StringManagerCore.localized_prop?('variant'); "
        "puts v.join(' ')"
    )
    out = subprocess.run(["ruby", "-e", script], capture_output=True, text=True, check=True)
    return out.stdout.split()


class OneVocabularyTest(unittest.TestCase):
    def test_lint_strings_reads_accessibility_label(self):
        props = load_string_props(REPO / "shared" / "core" / "string_manager_core.rb")
        self.assertIn("accessibilityLabel", props)
        self.assertIn("label", props)

    @unittest.skipUnless(shutil.which("ruby"), "ruby not installed")
    def test_every_reader_sees_the_lint_strings_list(self):
        lint = load_string_props(REPO / "shared" / "core" / "string_manager_core.rb")
        for tool in ("kjui_tools", "sjui_tools", "rjui_tools"):
            with self.subTest(tool=tool):
                self.assertEqual(frozenset(_ruby_vocabulary(tool)), lint)

    def test_the_scaffolds_ask_the_predicate(self):
        # No scaffold may spell display-text names of its own: the
        # decision is the shared predicate, so a vocabulary change reaches
        # every converter scaffolded from this release on. rjui's joined
        # from 1.9.8 (rjui-custom-component-string-literal-prop-is-read-as-a-
        # string-key); its generated format_literal names the prop `name`.
        for path in ("kjui_tools/lib/compose/generators/converter_generator.rb",
                     "sjui_tools/lib/swiftui/generators/converter_generator.rb",
                     "rjui_tools/lib/react/generators/converter_generator.rb"):
            with self.subTest(path=path):
                source = (REPO / path).read_text()
                self.assertRegex(source, r"JsonUIShared::StringManagerCore\.localized_prop\?\((key|name)\)")
                self.assertNotIn("accessibilityLabel", source)


if __name__ == "__main__":
    unittest.main()
