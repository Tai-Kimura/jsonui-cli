"""The closing count carries its denominator.

`Generated N HTML files` says how many pages were written and nothing about
how much was read, so an empty input, a mistyped path, a project that declares
no contracts, and a half-updated install all end the same way: a small number
and exit 0. The reader cannot tell which happened, which is the same family as
a test runner reporting success for a filter that matched nothing.

Three states this pins apart, because collapsing any two of them is what made
the original line useless:

    read K, found U     the ordinary case — U is only meaningful beside K.
                        ⚠️ U is a different unit from K and D — U counts
                        TARGETS, K and D both count spec FILES — and the
                        words have to say so: the first reader of this line
                        took K for screens and D for targets and published
                        both numbers wrong. K and D share a unit on purpose,
                        so that D <= K reads as true
    read 0              a scan that ran and found nothing. WARNING, in the
                        spelling the zero-warnings gate counts, because a
                        wrong `spec_directory` produces exactly this
    not read at all     no usable config. NOT "0" — a scan that did not
                        happen is a different fact from one that found
                        nothing, and printing 0 for it is the confusion the
                        line exists to remove
"""
from __future__ import annotations

import unittest

from jsonui_doc_cli.test_doc.generator import (
    generation_summary_line,
    generation_warnings,
    note_generation_counts,
    note_page_generated,
    reset_page_failures,
)

WARNING_RE = r"warning \[|warning:|\[warn|⚠"


class SummaryLine(unittest.TestCase):
    def setUp(self):
        reset_page_failures()
        self.addCleanup(reset_page_failures)

    def _pages(self, n: int):
        for i in range(n):
            with _quiet():
                note_page_generated(f"/tmp/does-not-matter-{i}.html")

    def test_it_names_what_was_read_beside_what_was_written(self):
        self._pages(7)
        note_generation_counts(screens=3, flows=1, unit_targets=5,
                               unit_scanned=True, specs_read=21,
                               specs_declaring=5)
        line = generation_summary_line()
        self.assertIn("Generated 7 HTML files", line)
        self.assertIn("screens 3", line)
        self.assertIn("flows 1", line)
        self.assertIn("unit targets 5 from 21 spec file(s) scanned", line)
        self.assertIn("5 spec file(s) declaring unitContracts", line)
        self.assertEqual(generation_warnings(), [])

    def test_zero_specs_read_is_a_counted_warning(self):
        self._pages(2)
        note_generation_counts(screens=1, flows=0, unit_targets=0,
                               unit_scanned=True, specs_read=0,
                               specs_declaring=0)
        self.assertIn("from 0 spec file(s) scanned", generation_summary_line())
        warnings = generation_warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertRegex(warnings[0].lower(), WARNING_RE)

    def test_a_scan_that_did_not_run_is_not_reported_as_zero(self):
        # The whole point: "not read" and "read, found none" are different
        # facts, and only one of them means the project declares none.
        self._pages(2)
        note_generation_counts(screens=1, flows=0, unit_targets=0,
                               unit_scanned=False, specs_read=0,
                               specs_declaring=0)
        line = generation_summary_line()
        self.assertIn("unitContracts not read", line)
        self.assertNotIn("spec file(s) scanned", line)
        # It is not a warning here: the CLI already warned about the missing
        # config, and saying it twice trains the reader to skip both.
        self.assertEqual(generation_warnings(), [])

    def test_declaring_zero_is_information_not_a_warning(self):
        # A project may legitimately declare no contracts. That must not warn,
        # or the gate's zero-warning invariant becomes unmeetable for it.
        self._pages(3)
        note_generation_counts(screens=2, flows=0, unit_targets=0,
                               unit_scanned=True, specs_read=12,
                               specs_declaring=0)
        self.assertIn("0 spec file(s) declaring unitContracts", generation_summary_line())
        self.assertEqual(generation_warnings(), [])

    def test_a_spec_that_could_not_be_read_is_named(self):
        # K counts every file looked at, unreadable included; D counts only
        # files read AND declaring. So a spec that will not parse widens
        # K - D by one and changes nothing else — from the line alone it is
        # identical to a file that simply declares nothing, which is the pair
        # this whole line exists to keep apart.
        self._pages(3)
        note_generation_counts(screens=1, flows=0, unit_targets=1,
                               unit_scanned=True, specs_read=2,
                               specs_declaring=1, specs_unreadable=1,
                               unreadable_files=["broken.spec.json"])
        warnings = generation_warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertRegex(warnings[0].lower(), WARNING_RE)
        self.assertIn("broken.spec.json", warnings[0])

    def test_no_unreadable_specs_means_no_such_warning(self):
        self._pages(3)
        note_generation_counts(screens=1, flows=0, unit_targets=1,
                               unit_scanned=True, specs_read=2,
                               specs_declaring=1, specs_unreadable=0,
                               unreadable_files=[])
        self.assertEqual(generation_warnings(), [])

    def test_without_counts_the_line_is_the_bare_one(self):
        # A caller that never recorded counts still gets a valid sentence
        # rather than a parenthesis full of zeroes it did not measure.
        self._pages(4)
        self.assertEqual(generation_summary_line(), "Generated 4 HTML files")


class _quiet:
    """`note_page_generated` prints; these tests are about the tally."""

    def __enter__(self):
        import contextlib, io
        self._c = contextlib.redirect_stdout(io.StringIO())
        self._c.__enter__()

    def __exit__(self, *a):
        return self._c.__exit__(*a)


if __name__ == "__main__":
    unittest.main()
