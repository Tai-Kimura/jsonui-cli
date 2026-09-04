"""A spec that raises must be REPORTED, not take the run down with it.

`_generate_spec_pages` records a page failure and carries on, so one
unreadable spec costs one page. Its handler passes the page's output path to
`record_page_failure`, which writes a placeholder there — and that path is
assigned only after the `collect_only` early return.

So on the collect pass, which is the FIRST of the two passes
`generate_html_directory` runs, the name was never bound: any spec that raised
came back as `UnboundLocalError` from the whole run, and the real error — the
one naming the file and what was wrong with it — was never printed.

The same binding is a loop variable, which is the quieter half. A later
iteration that fails before the assignment still holds the PREVIOUS spec's
path, and the placeholder lands on top of a page that generated fine. Hence
the reset is per iteration, and the second test here fails if it is hoisted
out of the loop.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import (
    _generate_spec_pages,
    get_page_failures,
    reset_page_failures,
)


def _valid(name: str) -> dict:
    return {
        "type": "screen_spec",
        "version": "1.0",
        "metadata": {"screenName": name, "name": "Ok", "displayName": "Ok",
                     "description": "A spec that generates."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}},
    }


def _raises(name: str) -> dict:
    # `structure` is read with .get(), so a string raises AttributeError
    # partway through — the shape that produced the original report.
    spec = _valid(name)
    spec["structure"] = "not-an-object"
    return spec


class SpecPageErrorHandler(unittest.TestCase):
    def setUp(self):
        reset_page_failures()
        self.addCleanup(reset_page_failures)

    def _run(self, specs: dict[str, dict], collect_only: bool):
        # mkdtemp + cleanup rather than a `with` block: the caller inspects
        # the written pages, and a context manager would delete them on the
        # way out of this helper — which reads exactly like the page never
        # having been written.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        docs = root / "screens" / "json"
        docs.mkdir(parents=True)
        for name, spec in specs.items():
            (docs / f"{name}.spec.json").write_text(
                json.dumps(spec), encoding="utf-8")
        out = root / "out"
        out.mkdir()
        _generate_spec_pages([docs], out, collect_only=collect_only)
        return out

    def test_a_spec_that_raises_on_the_collect_pass_is_reported_not_crashed(self):
        # Before the fix this raised UnboundLocalError out of the whole run.
        self._run({"broken": _raises("broken")}, collect_only=True)
        failures = get_page_failures()
        self.assertEqual(len(failures), 1, failures)
        self.assertEqual(failures[0]["kind"], "screen spec")
        self.assertIn("broken", str(failures[0]["source"]))

    def test_the_collect_pass_reports_without_writing_a_placeholder(self):
        # No output path is known on the collect pass, so there is nowhere a
        # placeholder could correctly go — and writing one anyway is what the
        # unassigned name would have done had it held a stale value.
        out = self._run({"broken": _raises("broken")}, collect_only=True)
        self.assertEqual(sorted(p.name for p in out.rglob("*.html")), [])

    def test_a_failure_does_not_overwrite_an_earlier_specs_page(self):
        # 'a_ok' sorts first and generates; 'b_broken' then fails BEFORE its
        # own output path is computed. With the reset hoisted out of the loop
        # the handler still holds a_ok's path and drops a placeholder on it.
        out = self._run({"a_ok": _valid("a_ok"), "b_broken": _raises("b_broken")},
                        collect_only=False)
        self.assertEqual(len(get_page_failures()), 1, get_page_failures())
        page = out / "specs" / "a_ok.html"
        self.assertTrue(page.is_file(), "the good page should exist")
        body = page.read_text(encoding="utf-8")
        self.assertNotIn("b_broken", body)
        self.assertIn("Ok", body)

    def test_a_good_spec_alongside_a_bad_one_still_generates(self):
        out = self._run({"a_ok": _valid("a_ok"), "b_broken": _raises("b_broken")},
                        collect_only=False)
        self.assertTrue((out / "specs" / "a_ok.html").is_file())


if __name__ == "__main__":
    unittest.main()
