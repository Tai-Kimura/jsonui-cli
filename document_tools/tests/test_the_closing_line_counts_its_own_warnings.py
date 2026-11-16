"""Regression: the summary line's warning count "disappeared" between 1.8.63 and 1.8.65.

Measured before anything was changed: `generation_summary_line` is
byte-identical between v1.8.63 and HEAD, and never carried a warning count.
What the face read as "warning 5" was its own grep over the log; five lines
were then respelled `Warning:` → `WARNING [doc-…]:` and the face's expression
matched only the old spelling, so its count went to 0 while the warnings kept
printing. From the log alone, "0 warnings" and "the counter is gone" are the
same sentence — which is the defect, and a grep recipe printed beside the
warnings did not close it (the recipe matched itself).

So the tool counts. Every warning goes through `run_log.warn`, and the closing
line prints `warnings N`, 0 included. The arms below pin three things a
half-done version would fail differently: the count is printed at zero; the
count equals the gate's own expression applied to the run's output (so the two
cannot drift); and every emitted line is spelled so that expression counts it.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli import run_log  # noqa: E402
from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402
from test_the_app_segment_is_not_doubled_and_warnings_share_one_spelling import (  # noqa: E402
    COUNTING_RE as RULEBOOK_RE,
)

CLOSING = re.compile(r"warnings (\d+)\)")


def _screen_test(document: str | None = None) -> dict:
    t = {"type": "screen", "platform": "ios", "source": {"layout": "s"},
         "metadata": {"name": "s", "description": "d"},
         "cases": [{"name": "c", "description": "c",
                    "steps": [{"action": "tap", "id": "x"}]}]}
    if document:
        t["source"]["document"] = document
    return t


def _run(root: Path, *, missing_document: bool = False, leftover: bool = False) -> tuple[str, str]:
    """Run `generate html` over a one-test tree; return (log, closing line)."""
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "s.test.json").write_text(json.dumps(_screen_test(
        "docs/nowhere/missing.html" if missing_document else None)), encoding="utf-8")
    out = root / "out"
    out.mkdir(exist_ok=True)
    if leftover:
        stale = out / "leftover.html"
        stale.write_text("<html></html>", encoding="utf-8")
        # Aged explicitly. A leftover is a page untouched since the run began,
        # and a file written microseconds before `started_at` is not reliably
        # "before" it — the first draft of this fixture produced one warning
        # where it meant two, and the arm below was red for the fixture's
        # reason rather than the tool's.
        old = stale.stat().st_mtime - 3600
        os.utime(stale, (old, old))
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(tests, out, "T")
        closing = gen.generation_summary_line()
    return buf.getvalue(), closing


def test_a_clean_run_says_warnings_zero(tmp_path):
    _, closing = _run(tmp_path)
    assert CLOSING.search(closing), closing
    assert CLOSING.search(closing).group(1) == "0"


def test_one_warning_is_counted_as_one(tmp_path):
    log, closing = _run(tmp_path, missing_document=True)
    assert "WARNING [doc-missing]" in log
    assert CLOSING.search(closing).group(1) == "1", (closing, log)


def test_the_count_equals_the_gates_expression_over_the_output(tmp_path):
    """Two kinds of warning in one run; the tally and the rulebook must agree.

    The rulebook expression is the one `jui build` documents as "the only
    thing that counts", quoted by the one-spelling test file rather than by
    this module's own code, so this arm is not the tool checking itself.
    """
    log, closing = _run(tmp_path, missing_document=True, leftover=True)
    by_gate = sum(1 for ln in log.splitlines() if RULEBOOK_RE.search(ln))
    assert by_gate >= 2, log
    assert int(CLOSING.search(closing).group(1)) == by_gate, (closing, log)


def test_every_emitted_line_is_spelled_so_the_gate_counts_it(tmp_path):
    _run(tmp_path, missing_document=True, leftover=True)
    lines = run_log.emitted()
    assert lines, "the run emitted nothing through the tally"
    unseen = [ln for ln in lines if not RULEBOOK_RE.search(ln)]
    assert unseen == [], f"warnings the gate's expression would not count: {unseen}"


def test_the_tally_quotes_the_rulebook_expression_verbatim():
    assert run_log.COUNTING_RE.pattern == RULEBOOK_RE.pattern


def test_the_recipe_no_longer_inflates_the_count(tmp_path):
    """The removed line — `count these with: grep -icE 'warning \\[|…'` —
    matched its own expression. Its absence is what lets the arm above hold."""
    log, _ = _run(tmp_path, leftover=True)
    assert "count these with" not in log
