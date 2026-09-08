"""The overwrite check that the reported incident would actually trip.

🚨 THE FIX THAT SHIPPED FIRST DID NOT CATCH THE CASE IT WAS WRITTEN FOR.
`report_foreign_output` reports SURPLUS — files in the output directory that
this run will not write. Measured on the tree the 2755-line clobber happened
on, before writing a line of this module:

    existing *.html in the output dir   8
    this run will write                 8
    surplus                             0   -> the check said NOTHING
    control: drop one planned file      -> it names that file

The site route writes one page per component spec and `generate component`
writes the same names, so a same-name clobber leaves no surplus at all. The
limit was written in a docstring and the limit was the incident.

Raised as a QUESTION by a consumer lane ("is the reported case not exactly
the invisible one?"), which is why it was measured rather than answered.

⚠️ TWO OUTCOMES, TWO WORDINGS, on that lane's insistence:

    a different mark  -> a collision that EXISTS. one line per file.
    no mark at all    -> this check knows nothing. ONE line per directory.

Same word for both floods every face's first run, and a reader shown one
flood stops reading the line that finally matters. It is the same shape as
`unstamped_platforms` in this release: a skipped comparison must not read
like agreement.

The mark carries the PRODUCER NAME ONLY. The three constraints came measured
from the docs face, which byte-compares 220 tracked generated files as a
gate: non-determinism makes that gate unpassable, a version in the mark
rewrites all 220 every release and hides real changes in the churn, and an
absolute path fails its public-repo pre-commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.cli import (  # noqa: E402
    producer_mark,
    read_producer,
    report_foreign_output,
    report_overwrites_by_another_producer,
    stamp_producer,
)

_PAGE = ("<!DOCTYPE html>\n<html>\n<head>\n<title>t</title>\n</head>\n"
         "<body>x</body>\n</html>\n")


def _pages(d, names, producer=None):
    for n in names:
        text = _PAGE if producer is None else stamp_producer(_PAGE, producer, ".html")
        (d / n).write_text(text, encoding="utf-8")
    return [d / n for n in names]


class TestTheShapeThatWasReported:
    """Eight unmarked pages, overwritten by eight identically-named ones."""

    def test_the_surplus_check_is_silent_here(self, tmp_path):
        """⚠️ The control that makes this module worth having: it pins the
        gap rather than describing it. If someone later makes the surplus
        check fire on this shape, this arm says so."""
        planned = _pages(tmp_path, [f"c{i}.html" for i in range(8)])

        assert report_foreign_output(tmp_path, planned, ".html") == []

    def test_the_producer_check_reports_it(self, tmp_path):
        planned = _pages(tmp_path, [f"c{i}.html" for i in range(8)])

        lines = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")

        assert len(lines) == 1, lines
        assert "8 file(s)" in lines[0]
        assert "no producer mark" in lines[0]
        assert "not a report of a collision" in lines[0]

    def test_the_unmarked_case_is_one_line_however_many_files(self, tmp_path):
        """🚨 The anti-flood arm. One line per unmarked file would be 220 on
        the docs face's first run, and a reader who has seen one flood stops
        reading."""
        planned = _pages(tmp_path, [f"c{i}.html" for i in range(40)])

        lines = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")

        assert len(lines) == 1
        assert "40 file(s)" in lines[0]


class TestACollisionThatExists:
    def test_one_line_per_file_written_by_another_command(self, tmp_path):
        planned = _pages(tmp_path, ["a.html", "b.html"], producer="spec-batch")

        lines = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")

        assert len(lines) == 2
        assert all("was written by `jsonui-doc spec-batch`" in l for l in lines)
        assert not any("no producer mark" in l for l in lines)

    def test_the_two_outcomes_do_not_share_wording(self, tmp_path):
        """⚠️ The arm that keeps the distinction real. Both branches saying
        the same sentence is the failure this module exists to prevent."""
        marked = _pages(tmp_path / "m", ["a.html"], producer="spec-batch") \
            if (tmp_path / "m").mkdir() or True else None
        plain = _pages(tmp_path / "p", ["a.html"]) \
            if (tmp_path / "p").mkdir() or True else None

        a = report_overwrites_by_another_producer(tmp_path / "m", marked, "component-batch")
        b = report_overwrites_by_another_producer(tmp_path / "p", plain, "component-batch")

        assert a and b and a[0] != b[0]


class TestTheControls:
    def test_rerunning_over_its_own_output_is_silent(self, tmp_path):
        """Re-running a command over what it wrote is normal and must stay
        quiet — the discriminator this whole check was rewritten around."""
        planned = _pages(tmp_path, ["a.html"], producer="component-batch")

        assert report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch") == []

    def test_a_file_that_does_not_exist_yet_is_not_reported(self, tmp_path):
        assert report_overwrites_by_another_producer(
            tmp_path, [tmp_path / "new.html"], "component-batch") == []

    def test_a_missing_directory_is_not_reported(self, tmp_path):
        d = tmp_path / "nope"

        assert report_overwrites_by_another_producer(d, [d / "a.html"], "x") == []


class TestTheMarkItself:
    """The three constraints the docs face measured and asked for."""

    def test_it_is_deterministic(self):
        assert (stamp_producer(_PAGE, "spec-batch", ".html")
                == stamp_producer(_PAGE, "spec-batch", ".html"))

    def test_it_is_idempotent(self):
        once = stamp_producer(_PAGE, "spec-batch", ".html")

        assert stamp_producer(once, "spec-batch", ".html") == once

    @pytest.mark.parametrize("suffix", [".html", ".md"])
    def test_it_carries_no_version_no_path_no_clock(self, suffix):
        """🚨 A version here rewrites 220 tracked files EVERY RELEASE on the
        docs face, and the real change then hides in the churn. A clock or a
        path makes their byte-comparison gate unpassable by construction."""
        mark = producer_mark("spec-batch", suffix)

        assert not re.search(r"\d+\.\d+\.\d+", mark)
        assert "/Users/" not in mark and "/home/" not in mark
        assert not re.search(r"\d{4}-\d{2}-\d{2}|pid|hostname", mark, re.I)

    def test_a_document_with_no_head_is_written_unchanged(self):
        """⚠️ Never mangle. An unmarked file is a state the caller already
        reports; a corrupted page is not."""
        assert stamp_producer("no head here", "spec-batch", ".html") == "no head here"

    def test_markdown_gets_a_comment_not_a_meta_tag(self):
        out = stamp_producer("# t\n", "spec-batch", ".md")

        assert "<!-- jsonui-doc-producer: spec-batch -->" in out
        assert "<meta" not in out

    def test_markdown_still_starts_with_its_own_first_line(self):
        """🚨 THE REGRESSION THIS ARM EXISTS FOR. The first draft PREPENDED
        the mark and broke `test_markdown_writes_markdown_content`, whose
        discriminator is that a markdown body starts with `#`. That arm was
        right: a producer mark must not change what the document IS. The gate
        caught it before the commit — an existing arm doing its job against a
        new feature."""
        out = stamp_producer("# Title\n\nbody\n", "spec-batch", ".md")

        assert out.lstrip().startswith("#")
        assert out.rstrip().endswith("-->")

    def test_a_marked_markdown_file_reads_back(self, tmp_path):
        """⚠️ The mark is at the END for markdown, so a reader that only
        looked at the head would call every marked file unmarked — the very
        silence this check removes, reintroduced by the fix for another one."""
        p = tmp_path / "a.md"
        p.write_text(stamp_producer("# t\n" + ("filler\n" * 3000),
                                    "spec-batch", ".md"), encoding="utf-8")

        assert read_producer(p) == "spec-batch"

    def test_it_round_trips(self, tmp_path):
        p = tmp_path / "a.html"
        p.write_text(stamp_producer(_PAGE, "component-batch", ".html"), encoding="utf-8")

        assert read_producer(p) == "component-batch"

    def test_an_unmarked_file_reads_as_none_not_as_a_producer(self, tmp_path):
        """🚨 None is "nothing to go on", never "someone else". The two are
        different facts and the caller says them differently."""
        p = tmp_path / "a.html"
        p.write_text(_PAGE, encoding="utf-8")

        assert read_producer(p) is None


class TestBothCommandsAreWiredToBoth:
    """One rule, two mouths — count the arms per mouth.

    ⚠️ This release already shipped a rule whose second mouth had zero arms.
    """

    @pytest.mark.parametrize("func,command", [
        ("cmd_generate_spec_batch", "spec-batch"),
        ("cmd_generate_component_batch", "component-batch"),
    ])
    def test_the_command_reports_and_stamps_with_its_own_name(self, func, command):
        import ast

        import jsonui_doc_cli.cli as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        [fn] = [n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == func]
        seg = ast.get_source_segment(src, fn)

        assert f'output_dir, _planned, "{command}")' in seg, \
            f"{func} does not ask about another producer's output"
        assert f'stamp_producer(content, "{command}"' in seg, \
            f"{func} writes pages that name no producer"
        for other in ("spec-batch", "component-batch"):
            if other != command:
                assert f'"{other}"' not in seg, \
                    f"{func} names {other} — the two mouths were crossed"
