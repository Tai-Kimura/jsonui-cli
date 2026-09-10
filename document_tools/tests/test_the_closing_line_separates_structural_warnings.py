"""Regression: on any `--app` run the closing line's `warnings N` could not reach 0.

`generate html` with `--app` writes into each app's source tree by design, and
says so: `⚠️ Also written OUTSIDE -o (N directories)`. The gate's counting
expression counts `⚠`, so the tally counts it too (B2 made the two agree on
purpose). The consequence, reported by a multi-app face after v1.8.66: N is at
least 1 on every such run, so "0 means clean" is a reading nobody there can
use. The notice itself is right — a write into another lane's tree must be
named — so the total must not shrink. What changes is the breakdown: the same
line now says how many of the N are structural and what kind, so `N − M == 0`
reads as clean while N still equals what the gate's expression counts.

Two things a half-done version would fail differently: the clause must be
absent when nothing structural fired (a single-app run stays `warnings 0`),
and only ONE mouth may declare itself structural — the declaration is an
argument at the emit site, not a list somewhere, and an AST scan pins the
count of such sites to one.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli import run_log  # noqa: E402
from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402
from test_document_page_links_and_writes_outside_output import (  # noqa: E402
    COMPONENT_FILE, _component_spec, _screen_spec,
)
from test_the_app_segment_is_not_doubled_and_warnings_share_one_spelling import (  # noqa: E402
    COUNTING_RE as RULEBOOK_RE,
)

PACKAGE = REPO / "document_tools" / "jsonui_doc_cli"
CLOSING = re.compile(r"warnings (\d+)(?: \((\d+) structural: ([a-z, -]+)\))?\)")


def _tree(root: Path, *, with_docs: bool) -> list[dict]:
    """A one-app tree. `with_docs=False` builds NO docs tree at all.

    ⚠️ "no `--app`" is not "no outside writes": the run's own root scope also
    pre-generates into `<input>/../docs/*/html|md` whenever that tree exists,
    and the first draft of the complement arm below built the docs tree and
    merely withheld `--app` — the notice fired (4 directories) and the arm was
    red for the fixture's reason. The complement needs the absence itself.
    """
    tests = root / "client" / "tests"
    tests.mkdir(parents=True)
    (tests / "s.test.json").write_text(json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": "s"},
        "metadata": {"name": "s", "description": "d"},
        "cases": [{"name": "c", "description": "c",
                   "steps": [{"action": "tap", "id": "x"}]}],
    }), encoding="utf-8")
    (root / "out").mkdir()
    if not with_docs:
        return []
    docs = root / "client" / "docs"
    (docs / "screens" / "json").mkdir(parents=True)
    (docs / "components" / "json").mkdir(parents=True)
    (docs / "screens" / "json" / "home.spec.json").write_text(
        json.dumps(_screen_spec("home", COMPONENT_FILE)), encoding="utf-8")
    (docs / "components" / "json" / COMPONENT_FILE).write_text(
        json.dumps(_component_spec()), encoding="utf-8")
    return [{"name": "client", "docs_path": str(docs)}]


def _run(root: Path, apps: list[dict]) -> tuple[str, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen.generate_html_directory(root / "client" / "tests", root / "out", "T",
                                    apps=apps or None)
        closing = gen.generation_summary_line()
    return buf.getvalue(), closing


def test_a_multi_app_run_names_its_structural_warnings_on_the_same_line(tmp_path):
    log, closing = _run(tmp_path, _tree(tmp_path, with_docs=True))
    m = CLOSING.search(closing)
    assert m, closing
    total, structural, kinds = int(m.group(1)), m.group(2), m.group(3)
    assert structural == "1" and kinds == "outside-writes", closing
    # The total still equals the gate's own count — the breakdown did not
    # shrink it.
    by_gate = sum(1 for ln in log.splitlines() if RULEBOOK_RE.search(ln))
    assert total == by_gate, (closing, log)


def test_with_nothing_else_wrong_the_structural_count_accounts_for_everything(tmp_path):
    """`N − M == 0` is the reading the face asked for."""
    _, closing = _run(tmp_path, _tree(tmp_path, with_docs=True))
    m = CLOSING.search(closing)
    assert m and m.group(2) is not None, closing
    assert int(m.group(1)) - int(m.group(2)) == 0, closing


def test_a_run_without_outside_writes_has_no_structural_clause(tmp_path):
    """The complement: the clause must not print when nothing structural fired."""
    log, closing = _run(tmp_path, _tree(tmp_path, with_docs=False))
    assert "Also written OUTSIDE" not in log
    assert "structural" not in closing, closing
    assert CLOSING.search(closing).group(1) == "0", closing


def test_the_tally_reports_structural_kinds_by_name():
    run_log.begin()
    try:
        with redirect_stdout(io.StringIO()):
            run_log.warn("  ⚠️ something structural", structural="outside-writes")
            run_log.warn("  WARNING [doc]: something ordinary")
        assert run_log.count() == 2
        assert run_log.structural() == {"outside-writes": 1}
    finally:
        run_log.end()


def test_exactly_one_emit_site_declares_itself_structural():
    """The declaration lives at the emit site. A second site claiming to be
    structural would let a real warning hide inside the 'clean' reading, so
    the count of such sites is pinned — and pinned by AST, not by a grep that
    a line wrap can dodge."""
    sites = []
    for f in PACKAGE.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "warn"
                    and any(k.arg == "structural" for k in node.keywords)):
                sites.append(f"{f.relative_to(PACKAGE)}:{node.lineno}")
    assert len(sites) == 1, sites
    assert sites[0].startswith("test_doc/generator.py:"), sites
