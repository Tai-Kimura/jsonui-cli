"""`-o` pointing at another generator's output says so before writing.

A delivery lane pointed `generate component -o` at a directory holding
`generate html`'s pages and lost 2755 lines — sidebar and styles replaced by
a different format, caught only because the diff was reviewed before commit.
Nothing in the tool looked at what was already there.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.cli import report_foreign_output  # noqa: E402


def _touch(d: Path, *names):
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_text("x", encoding="utf-8")
    return [d / n for n in names]


class TestItNamesWhatThisRunWillNotWrite:
    def test_a_foreign_producers_pages_are_named(self, tmp_path):
        out = tmp_path / "components"
        _touch(out, "picker.html", "chrome.html", "sidebar.html")
        planned = [out / "picker.html"]          # this run writes only one
        lines = report_foreign_output(out, planned, ".html")
        assert len(lines) == 1
        assert "2 file(s)" in lines[0], lines[0]
        assert "chrome.html" in lines[0] and "sidebar.html" in lines[0]
        assert "picker.html" not in lines[0], "a file this run writes is not foreign"

    def test_the_control_rerunning_over_its_own_output_is_silent(self, tmp_path):
        """⚠️ The arm that keeps the discriminator from being "non-empty".
        Re-running a generator over its own output is the normal case and it
        must not warn, or the warning becomes noise and stops being read."""
        out = tmp_path / "components"
        planned = _touch(out, "a.html", "b.html")
        assert report_foreign_output(out, planned, ".html") == []

    def test_the_control_an_empty_directory_is_silent(self, tmp_path):
        out = tmp_path / "components"
        out.mkdir()
        assert report_foreign_output(out, [out / "a.html"], ".html") == []

    def test_a_missing_directory_is_silent(self, tmp_path):
        assert report_foreign_output(tmp_path / "nope", [], ".html") == []

    def test_only_this_runs_suffix_is_considered(self, tmp_path):
        """A markdown run must not report the HTML pages beside it."""
        out = tmp_path / "components"
        _touch(out, "a.html", "b.html", "a.md")
        assert report_foreign_output(out, [out / "a.md"], ".md") == []

    def test_it_never_deletes_and_says_so(self, tmp_path):
        out = tmp_path / "components"
        kept = _touch(out, "foreign.html")
        report_foreign_output(out, [out / "mine.html"], ".html")
        assert kept[0].is_file(), "the report must not remove anything"
        line = report_foreign_output(out, [out / "mine.html"], ".html")[0]
        assert "Nothing is deleted" in line


class TestBothDirectionsAreGuarded:
    """⚠️ Fixing one direction leaves the other symptomless.

    The reported case was component-over-html. The same shape exists for
    spec-over-component, so both batch commands carry the call.
    """

    def test_both_batch_commands_call_it(self):
        src = (Path(__file__).resolve().parents[1] / "jsonui_doc_cli"
               / "cli.py").read_text(encoding="utf-8")
        import re
        for fn in ("cmd_generate_spec_batch", "cmd_generate_component_batch"):
            body = src[src.index(f"def {fn}("):]
            body = body[:body.index("\ndef ")] if "\ndef " in body else body
            assert "report_foreign_output(" in body, f"{fn} does not call it"

    def test_the_call_happens_before_any_file_is_written(self):
        src = (Path(__file__).resolve().parents[1] / "jsonui_doc_cli"
               / "cli.py").read_text(encoding="utf-8")
        for fn in ("cmd_generate_spec_batch", "cmd_generate_component_batch"):
            body = src[src.index(f"def {fn}("):]
            body = body[:body.index("\ndef ")] if "\ndef " in body else body
            # `report_foreign_output(` — the call, not the docstring mention.
            assert body.index("report_foreign_output(") < body.index("open(output_path"), \
                f"{fn} warns after it has started writing"
