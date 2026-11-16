"""v1.8.64 shipped two defects that a consumer face measured 10 minutes later.

🚨 WHY THIS FILE EXISTS. Both were produced BY the fix for an earlier ticket,
and neither was visible from this side:

  1. The app segment was prepended unconditionally, so a face whose
     declarations are already app-scoped got `user/docs/user/…` — and its 30
     pages at the old URLs stayed behind, still serving the title the release
     had just repaired.
  2. That leftover WAS reported. The face read "warning 0" for three
     consecutive releases because it grepped `WARNING` (upper case) while this
     module spelled it `Warning:` — and the module already used `WARNING [doc]:`
     in three other places, so the two spellings sat in one file.

The arms below are therefore about a shape, not about one path: a segment that
duplicates a name the path already carries, and a warning nobody can count.
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jsonui_doc_cli.test_doc.generator import (  # noqa: E402
    _report_stale_pages,
    document_output_rel_path,
)

GENERATOR = (Path(__file__).resolve().parents[1]
             / "jsonui_doc_cli" / "test_doc" / "generator.py")

#: The rulebook's own expression, quoted from `jui build`'s docstring, which
#: calls it "the only thing that counts". Arms here use it verbatim rather
#: than a spelling of their own — an arm with its own predicate is a third
#: opinion about what a warning looks like.
COUNTING_RE = re.compile(r"warning \[|warning:|\[warn|⚠", re.I)


class TheSegmentIsNotAddedTwice(unittest.TestCase):
    """腕① — the test is whether THIS path already names THIS owner."""

    def test_a_path_under_docs_owner_is_left_alone(self):
        self.assertEqual(
            document_output_rel_path("user", "docs/user/screens/html/x.html"),
            "docs/user/screens/html/x.html")

    def test_a_path_starting_with_the_owner_is_left_alone(self):
        self.assertEqual(
            document_output_rel_path("user", "user/screens/html/x.html"),
            "user/screens/html/x.html")

    def test_a_path_that_does_not_name_the_owner_still_gets_the_segment(self):
        # The behaviour v1.8.64 shipped, for the case it was shipped for.
        self.assertEqual(
            document_output_rel_path("user", "docs/screens/html/login.html"),
            "user/docs/screens/html/login.html")

    def test_the_owner_in_a_middle_segment_is_not_app_scoping(self):
        # 🚫 DELIBERATE. `user` here is a directory that happens to share the
        # name. Treating it as app-scoping would let two apps whose paths
        # differ only in a middle segment collide again — the exact defect the
        # segment exists to stop. The safe direction is a redundant segment.
        self.assertEqual(
            document_output_rel_path("user", "docs/screens/user/x.html"),
            "user/docs/screens/user/x.html")

    def test_no_owner_means_no_segment(self):
        self.assertEqual(
            document_output_rel_path(None, "docs/screens/html/x.html"),
            "docs/screens/html/x.html")

    def test_two_apps_declaring_one_path_still_separate(self):
        # The property the whole function exists for, restated as an arm so a
        # future narrowing of the "already names it" test cannot quietly undo
        # it while the cases above stay green.
        a = document_output_rel_path("bar", "docs/screens/html/login.html")
        b = document_output_rel_path("client", "docs/screens/html/login.html")
        self.assertNotEqual(a, b)


class TheLeftoverWarningCanBeCounted(unittest.TestCase):
    """腕② — the report is only a report if the reader's expression finds it."""

    def _run_with_a_leftover(self) -> str:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "leftover.html").write_text("<html></html>", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                # started_at in the future so the existing file is untouched
                # by "this run" and therefore a leftover.
                _report_stale_pages(out, started_at=2 ** 31)
            return buf.getvalue()

    def test_the_leftover_is_reported(self):
        self.assertIn("leftover.html", self._run_with_a_leftover())

    def test_the_canonical_expression_matches_the_report(self):
        self.assertTrue(COUNTING_RE.search(self._run_with_a_leftover()))

    def test_an_upper_case_grep_also_matches_now(self):
        # The face's own predicate, which returned 0 for three releases.
        self.assertIn("WARNING", self._run_with_a_leftover())

    def test_the_run_ships_the_count_not_the_counting_expression(self):
        # Inverted 2026-09-10. The recipe line matched the very expression it
        # quoted (`warning \[` is in it), so a reader who ran it over this log
        # counted the instruction to count as a warning. The number now ships
        # on the closing line (`warnings N`, see run_log); the expression is
        # the gate's business. A recipe reappearing here would be a second,
        # self-inflating count beside the tool's own.
        self.assertNotIn("grep -icE", self._run_with_a_leftover())

    def test_a_clean_output_dir_says_nothing(self):
        # 陰性対照: without this, an arm that always printed would pass above.
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with redirect_stdout(buf):
                _report_stale_pages(Path(d), started_at=2 ** 31)
            self.assertEqual(buf.getvalue(), "")


class OneSpellingPerModule(unittest.TestCase):
    """The two spellings sat in one file; nothing said they had to agree."""

    def _print_lines(self) -> list[str]:
        # Only lines that PRINT. A source scan that counts every occurrence
        # matches this file's own prose about the old spelling — the arm would
        # then be reading its own explanation.
        # `warn(` since 2026-09-10: every warning goes through `run_log.warn`,
        # which is how the closing line can count them. A scan that only knew
        # `print(` would have let the positive control below go vacuous.
        return [ln for ln in GENERATOR.read_text(encoding="utf-8").splitlines()
                if "print(" in ln or "warn(" in ln or ln.strip().startswith('f"')]

    def test_no_printed_warning_uses_the_old_spelling(self):
        offenders = [ln.strip() for ln in self._print_lines()
                     if "Warning:" in ln]
        self.assertEqual(offenders, [], f"still mixed: {offenders}")

    def test_the_module_does_print_warnings(self):
        # 陽性対照: the arm above passes trivially on a module that warns
        # about nothing. Measured: this module has several.
        tagged = [ln for ln in self._print_lines() if "WARNING [" in ln]
        self.assertGreaterEqual(len(tagged), 5, "the scan found no warnings")

    def test_every_tag_is_lower_case_kebab(self):
        tags = re.findall(r"WARNING \[([^\]]+)\]",
                          GENERATOR.read_text(encoding="utf-8"))
        self.assertTrue(tags)
        bad = [t for t in tags if not re.fullmatch(r"[a-z][a-z-]*", t)]
        self.assertEqual(bad, [], f"tags not kebab-case: {bad}")


if __name__ == "__main__":
    unittest.main()
