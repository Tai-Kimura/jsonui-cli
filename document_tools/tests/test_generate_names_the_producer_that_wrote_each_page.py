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

import inspect
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
        # 🚨 It must NOT promise a future that will not arrive. v1.8.58 said
        # "will carry it once rewritten" and a consumer lane found that false
        # for a directory it maintains with the single-file form.
        #
        # ⚠️ THIS COMMENT SAID "everything from `generate html` never gains a
        # mark" UNTIL 2026-09-09, AND THAT HAD BEEN FALSE SINCE v1.8.61.
        # c3c74f77 made `generate html` stamp the pages it pre-generates into
        # the source tree; the wording and this comment both kept the old
        # claim for two releases. The arm stayed green throughout, because an
        # arm pins behaviour and does not pin the sentence that explains it.
        # The distinction is pinned below, in its own class.
        assert "will not" in lines[0]
        assert "rewritten" not in lines[0]

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
        assert all("was written by `jsonui-doc:spec`" in l for l in lines)
        assert all("with `jsonui-doc:component` output" in l for l in lines)
        # ⚠️ The prefix must not double. The first draft of the family change
        # left the message saying "`jsonui-doc jsonui-doc:spec`", because the
        # sentence still prepended the tool name to a value that already
        # carried it.
        assert not any("jsonui-doc jsonui-doc" in l for l in lines)
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

        assert "<!-- jsonui-doc-producer: jsonui-doc:spec -->" in out
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

        assert read_producer(p) == "jsonui-doc:spec"

    def test_it_round_trips(self, tmp_path):
        p = tmp_path / "a.html"
        p.write_text(stamp_producer(_PAGE, "component-batch", ".html"), encoding="utf-8")

        assert read_producer(p) == "jsonui-doc:component"

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


class TestTheFamilyIsTheUnitTheCheckAsksAbout:
    """🚨 v1.8.58 STAMPED THE SUBCOMMAND, WHICH IS FINER THAN THE QUESTION.

    A consumer lane traced a 6-vs-5 discrepancy in its own uptake and found
    that `docs/components/md`, maintained with the SINGLE-FILE form, was
    permanently unmarked while the tool's own output told its reader the mark
    would arrive "once rewritten". Extending the mark to the single-file form
    then had no correct spelling:

        single-file says "component-batch"  -> the mark LIES about who wrote it
        single-file says "component"        -> the batch form rewriting it
                                               reports a FALSE COLLISION

    The check asks "is this my own output?", never "which subcommand?", so
    the mark names the family. Extra precision in an identifier does not add
    information here; it manufactures false positives.
    """

    def _page(self, d, name, producer):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(stamp_producer(_PAGE, producer, ".html"),
                              encoding="utf-8")
        return [d / name]

    @pytest.mark.parametrize("wrote,rewrites", [
        ("component", "component-batch"),
        ("component-batch", "component"),
        ("spec", "spec-batch"),
        ("spec-batch", "spec"),
    ])
    def test_the_two_forms_of_one_family_do_not_collide(self, tmp_path, wrote,
                                                        rewrites):
        planned = self._page(tmp_path, "a.html", wrote)

        assert report_overwrites_by_another_producer(
            tmp_path, planned, rewrites) == []

    def test_v1858s_spelling_still_reads_as_this_tools_own_output(self, tmp_path):
        """🚨 THE MIGRATION ARM. v1.8.58 shipped `spec-batch` /
        `component-batch` into 208 files on one face and 5 on another. Without
        this normalisation the rename would turn them into a foreign
        producer — a rename becoming a collision.

        ⚠️ THE BLAST RADIUS IS NARROWER THAN THIS LANE FIRST CLAIMED, and the
        receiving face measured it rather than accepting the claim. Three
        conditions must hold together:

            the output directory already holds marked files, AND
            the run does NOT delete before generating, AND
            those marks carry the old spelling

        The docs face `rm -rf`s its output first, so its 208 files never reach
        the comparison at all — measured there, and reproduced here:

            marked dir, regenerated in place   -> 0 lines (this arm)
            emptied dir, regenerated           -> 0 lines (nothing to compare)
            control: a foreign mark planted    -> 1 line (the check is alive)

        📌 This lane wrote "213 files would ring at once" from the shape of
        the code, not from how any face actually regenerates. The
        normalisation is still right — it protects every face that DOES
        overwrite in place — but the hazard was stated larger than measured.
        """
        legacy = '<meta name="jsonui-doc-producer" content="component-batch">'
        p = tmp_path / "a.html"
        p.write_text(_PAGE.replace("<head>", "<head>\n    " + legacy),
                     encoding="utf-8")

        assert read_producer(p) == "jsonui-doc:component"
        assert report_overwrites_by_another_producer(
            tmp_path, [p], "component-batch") == []

        # 🚨 SILENCE IS TWO FACTS HERE, AND ONLY ONE OF THEM IS THE GOOD ONE.
        # Raised by the receiving face when it planned this same check against
        # its 208 real files: "0 warnings" is produced BOTH by the
        # normalisation working AND by nothing having been rewritten at all.
        # So the arm counts the replacement in the same breath.
        rewritten = stamp_producer(p.read_text(encoding="utf-8"),
                                   "component-batch", ".html")

        assert "jsonui-doc:component" in rewritten
        assert "content=\"component-batch\"" not in rewritten, \
            "the legacy value survived a rewrite — it reads as ours but never migrates"

    def test_a_legacy_markdown_mark_is_replaced_too(self, tmp_path):
        """⚠️ The html half had an arm; the markdown half did not, and a
        mutation that stopped removing the markdown mark stayed green. Two
        formats are two mouths — count the arms per mouth, which is the same
        lesson this release opened with."""
        legacy = "# t\n\nbody\n\n<!-- jsonui-doc-producer: spec-batch -->\n"

        out = stamp_producer(legacy, "spec", ".md")

        assert "jsonui-doc:spec" in out
        assert "spec-batch" not in out, \
            "the legacy markdown mark survived a rewrite"
        assert out.count("jsonui-doc-producer") == 1, \
            "a second mark was appended instead of replacing the first"

    def test_the_removal_touches_only_this_tools_own_mark(self):
        """🚨 The over-cut control. A mutation widening the pattern to any
        `<meta …>` stayed green — the removal could have been eating the
        charset and viewport tags and no arm would have said so."""
        page = ('<!DOCTYPE html>\n<html>\n<head>\n'
                '    <meta charset="utf-8">\n'
                '    <meta name="jsonui-doc-producer" content="spec-batch">\n'
                '    <meta name="viewport" content="width=device-width">\n'
                '</head>\n<body>x</body>\n</html>\n')

        out = stamp_producer(page, "spec", ".html")

        assert '<meta charset="utf-8">' in out
        assert '<meta name="viewport" content="width=device-width">' in out
        assert 'content="spec-batch"' not in out
        assert out.count("jsonui-doc-producer") == 1

    def test_the_control_a_rewrite_of_an_unmarked_file_adds_the_mark(self, tmp_path):
        """⚠️ Pairs with the arm above: proves `stamp_producer` is what puts
        the value there, rather than the fixture having carried it."""
        plain = _PAGE

        assert "jsonui-doc-producer" not in plain
        assert "jsonui-doc:component" in stamp_producer(plain, "component", ".html")

    def test_the_control_a_different_family_still_collides(self, tmp_path):
        """⚠️ Without this, every arm above passes over a check that stopped
        reporting collisions entirely."""
        planned = self._page(tmp_path, "a.html", "spec")

        lines = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")

        assert len(lines) == 1
        assert "`jsonui-doc:spec`" in lines[0]

    def test_the_single_file_forms_stamp_too(self):
        """The gap the report named: v1.8.58 stamped only the batch forms."""
        import ast

        import jsonui_doc_cli.cli as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for name, family in (("cmd_generate_spec", "spec"),
                             ("cmd_generate_component", "component")):
            [fn] = [n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == name]
            seg = ast.get_source_segment(src, fn)
            assert f'stamp_producer(\n                    content, "{family}"' in seg, \
                f"{name} writes pages that name no producer"


class TestTheTwoGenerateHtmlPopulationsAreNotOne:
    """`generate html` stamps what it pre-generates, and not its own -o site.

    🚨 THE SAME DEFECT AS THE TICKET, IN THE OTHER DIRECTION. v1.8.58 promised
    a mark that would never arrive; v1.8.59 fixed that by asserting the
    opposite for `generate html` as a whole; c3c74f77 (v1.8.61) then made
    `generate html` stamp the pages it pre-generates, and the wording stayed
    for two releases.

    ⚠️ The second direction is the worse one. "No mark here is normal" CLOSES
    the reader's search, and after v1.8.61 an unmarked page under
    `<docs>/screens/html` may be one the stamping missed.

    Measured by RUNNING the command, not by reading it (2026-09-09): of the 8
    html/md files one `generate html` run wrote, 4 carried the mark
    (`<docs>/screens/{html,md}`, `<docs>/components/{html,md}`) and 4 did not
    (everything under `-o`). Stripping the mark from one of the 4 and
    re-running put it back — so "will not gain one" was false for it twice
    over.
    """

    def _msg(self, tmp_path):
        planned = _pages(tmp_path, ["c0.html"])
        lines = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")
        assert len(lines) == 1, lines
        return lines[0]

    def test_the_population_with_no_mark_is_named_by_where_it_is_written(
            self, tmp_path):
        assert "`-o` site directory" in self._msg(tmp_path)

    def test_the_population_that_does_carry_one_names_the_version(
            self, tmp_path):
        assert "since v1.8.61" in self._msg(tmp_path)

    def test_the_reader_is_told_to_look_there_not_to_stop(self, tmp_path):
        # The whole point: an unmarked file under the pre-generated paths is
        # NOT the expected state any more, so the notice must not close the
        # question the way it did for two releases.
        assert "worth looking at rather than expected" in self._msg(tmp_path)


class TestTheNoticeIsGreppableInTheSourceItShipsFrom:
    """A user quotes a line from the log; a maintainer greps the source for it.

    🚨 v1.8.59 split `will not gain one` across two f-string fragments
    (`"...will not " f"gain one..."`). THREE people independently grepped the
    shipped text and got 0 — one of them with "a phrase can break on a line
    wrap" written verbatim in their own index. A wording defect is also a
    SUPPORT-PATH defect: the person who can fix it cannot find it.

    ⚠️ This is a claim about the SOURCE, so it reads the source — and reads
    only the function's own body with comment lines removed, because a check
    that greps a file matches its own explanation otherwise.
    """

    def test_every_sentence_it_emits_appears_whole_on_one_source_line(
            self, tmp_path):
        planned = _pages(tmp_path, ["c0.html"])
        msg = report_overwrites_by_another_producer(
            tmp_path, planned, "component-batch")[0]

        src = inspect.getsource(report_overwrites_by_another_producer)
        code_lines = [l for l in src.splitlines()
                      if not l.lstrip().startswith("#")]

        # The first sentence interpolates the count and the directory, so it
        # cannot appear literally anywhere. Every other one can.
        _head, *rest = msg.split(". ")
        checked = 0
        for sentence in rest:
            sentence = sentence.strip().rstrip(".")
            if not sentence:
                continue
            checked += 1
            assert any(sentence in line for line in code_lines), (
                "a sentence this notice emits is split across source lines, "
                "so grepping the shipped text finds nothing: "
                f"{sentence!r}")
        assert checked >= 3, f"only {checked} sentence(s) were checked"
