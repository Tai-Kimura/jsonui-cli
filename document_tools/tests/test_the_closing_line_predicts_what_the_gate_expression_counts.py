"""Regression: the closing line's `warnings N` and the gate's grep disagreed on a face whose DATA carried the token.

`warnings N` counts what `run_log.warn` emitted, and B2 pinned that N equals
the rulebook's expression — `grep -iE 'warning \\[|warning:|\\[warn|⚠'` —
applied to the run's output. It held on every fixture and on one whole face,
and broke on the next: a test NAME containing "warning:" was printed by the
shared-slot listing, the reader's grep counted it, and the log said 2 where
the closing line said 1. Every arm was green because no fixture's name
carried a token — the broken property hid behind the fixtures' vocabulary
(ticket doc-closing-line-tally-and-the-gate-expression-diverge-when-printed-
data-carries-the-token, 2026-09-10).

Renaming the face's test is not the remedy: bending data so that an
expression misses it dulls the instrument. The tool instead applies the
reader's expression to its own printed output and SAYS how many lines the
gate will count that are not warnings, on the closing line, so the reader's
2 is explained by the line that says 1. N itself does not change.

The fixture's names carry the tokens deliberately and are not the face's —
a public fixture never copies a ticket's reproduction vocabulary.
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli import cli, run_log  # noqa: E402
from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402
from test_the_app_segment_is_not_doubled_and_warnings_share_one_spelling import (  # noqa: E402
    COUNTING_RE as RULEBOOK_RE,
)

# `warnings N[ (M structural: kinds)] / gate expression matches G (K printed data, not warnings)`
CLOSING = re.compile(
    r"warnings (?P<n>\d+)(?: \((?P<m>\d+) structural: [a-z, -]+\))?"
    r"(?: / gate expression matches (?P<g>\d+) \((?P<k>\d+) printed data, not warnings\))?\)$"
)

TOKEN_NAMES = ("Inventory alert (threshold warning: banner shown)", "Sync status ⚠ offline banner")
PLAIN_NAMES = ("Inventory alert (threshold banner shown)", "Sync status offline banner")
SHARED_DOCUMENT = "docs/notes/shared.html"


def _screen_test(name: str, document: str | None) -> dict:
    t = {"type": "screen", "platform": "ios", "source": {"layout": "s"},
         "metadata": {"name": name, "description": "d"},
         "cases": [{"name": "c", "description": "c",
                    "steps": [{"action": "tap", "id": "x"}]}]}
    if document:
        t["source"]["document"] = document
    return t


def _tree(root: Path, names: tuple[str, str]) -> Path:
    """Three screen tests; the first two declare ONE document, so the run's
    shared-slot listing prints both names (the mouth that echoed the face's
    token-bearing name). The third carries a warning of the tool's own — a
    missing document — so the arms can tell a warning from printed data."""
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "a.test.json").write_text(json.dumps(_screen_test(names[0], SHARED_DOCUMENT)), encoding="utf-8")
    (tests / "b.test.json").write_text(json.dumps(_screen_test(names[1], SHARED_DOCUMENT)), encoding="utf-8")
    (tests / "c.test.json").write_text(json.dumps(_screen_test("Plain screen", "docs/nowhere/missing.html")), encoding="utf-8")
    (root / "out").mkdir(exist_ok=True)
    return tests


def _run_command(root: Path) -> tuple[str, str]:
    """`jsonui-doc generate html` in-process — the command owns the tally, so
    the window the reader's grep sees is the window the tool measures."""
    buf = io.StringIO()
    argv = ["jsonui-doc", "generate", "html", str(root / "tests"), "-o", str(root / "out")]
    with patch("sys.argv", argv), redirect_stdout(buf), redirect_stderr(buf):
        try:
            cli.main()
        except SystemExit:
            pass
    log = buf.getvalue()
    closing = [ln for ln in log.splitlines() if ln.startswith("Generated ") and "HTML files" in ln]
    assert len(closing) == 1, log
    return log, closing[0]


def _gate_count(log: str, closing: str) -> int:
    """What the reader's grep returns over the whole log, the closing line aside."""
    return sum(1 for ln in log.splitlines() if ln != closing and RULEBOOK_RE.search(ln))


def _names_were_printed(log: str, names: tuple[str, str]) -> None:
    # The fixture's claim about the implementation: the listing printed the
    # names. Without this, a listing that went quiet would turn the arms
    # below green for the fixture's reason.
    assert "SHARED SLOT" in log, log
    for name in names:
        assert name in log, (name, log)


def test_the_closing_line_says_what_the_gate_expression_will_count(tmp_path):
    log, closing = _run_command(_tree(tmp_path, TOKEN_NAMES).parent)
    _names_were_printed(log, TOKEN_NAMES)
    m = CLOSING.search(closing)
    assert m and m.group("g") is not None, closing
    n, gate, printed = int(m.group("n")), int(m.group("g")), int(m.group("k"))
    assert n >= 1, closing                      # the tool's own warning (missing document) is there
    assert printed == 2, closing                # the two token-bearing names, not the warning
    assert gate == n + printed, closing
    assert gate == _gate_count(log, closing), (closing, log)


def test_the_tokens_in_the_names_do_not_change_n(tmp_path):
    _, plain = _run_command(_tree(tmp_path / "plain", PLAIN_NAMES).parent)
    _, token = _run_command(_tree(tmp_path / "token", TOKEN_NAMES).parent)
    assert CLOSING.search(plain).group("n") == CLOSING.search(token).group("n"), (plain, token)


def test_plain_names_leave_the_closing_line_as_it_was(tmp_path):
    log, closing = _run_command(_tree(tmp_path, PLAIN_NAMES).parent)
    _names_were_printed(log, PLAIN_NAMES)
    m = CLOSING.search(closing)
    assert m and m.group("g") is None, closing
    assert "gate expression" not in closing
    # B2's equality, unchanged where the data carries no token.
    assert int(m.group("n")) == _gate_count(log, closing), (closing, log)


def test_the_clause_is_not_itself_a_line_the_gate_counts(tmp_path):
    _, closing = _run_command(_tree(tmp_path, TOKEN_NAMES).parent)
    assert "gate expression matches" in closing, closing
    assert not RULEBOOK_RE.search(closing), closing


def test_without_the_command_tally_there_is_no_clause_and_no_crash(tmp_path):
    """The library entry cannot see the reader's stream (only the command
    wraps it), so it makes no claim about it — and does not fail."""
    tests = _tree(tmp_path, TOKEN_NAMES)
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(tests, tmp_path / "out", "T")
        closing = gen.generation_summary_line()
    assert "gate expression" not in closing, closing
    assert CLOSING.search(closing), closing
    assert run_log.data_hits() == []
