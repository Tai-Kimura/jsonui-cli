"""An app's own tests are documented, and grouped under the app that declared them.

🚨 THE SYMPTOM A READER REPORTS IS NOT THE DEFECT. On a three-app tree the
sidebar's Flow Tests (61) and Screen Tests (15) were the same on every app's
page, and a reader on one app's unit page was shown another app's screen
tests. Measured 2026-09-09, from the generated site: 61 + 15 = 76 = the input
directory's whole corpus, and the other two apps' 14 and 41 screen tests had
no page at all. Nothing was mis-grouped; those tests were never scanned.

⚠️ THREE DIAGNOSES BEFORE THIS ONE WERE WRONG, all read off the source rather
than off the output:

  "only one of three sidebar functions is per-app"  — the renderer is one
      function and already groups by `group`.
  "the nav does not pass `group`"                   — it does.
  "`_test_group` reads the app off the path, and the path has no app segment"
      — true, and still not why 55 pages were missing.

The counts settled it. An arm here therefore asserts on the GENERATED PAGES,
never on which functions mention an app.

The two-version discriminator, run on the fixture below:

    v1.8.62 (the shipped, pre-fix build)  1 page,  subsection []
    this tree                             6 pages, subsection ['alpha','beta']
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.cli import _resolve_test_roots  # noqa: E402


SPEC = {
    "type": "screen_spec", "version": "1.0",
    "metadata": {"name": "S", "displayName": "S", "description": "d"},
    "structure": {"components": [{"type": "View", "id": "root",
                                  "description": "r"}],
                  "layout": {"root": "root", "children": []}},
}


def _app(root: Path, name: str, n: int, *, test_src: str | None = "tests") -> None:
    (root / name / "docs" / "screens" / "json").mkdir(parents=True)
    (root / name / "docs" / "screens" / "json" / f"{name}.spec.json").write_text(
        json.dumps(SPEC), encoding="utf-8")
    cfg: dict = {} if test_src is None else {"test": {"src": test_src}}
    (root / name / "jui.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if test_src is not None:
        d = root / name / test_src / "screens"
        d.mkdir(parents=True)
        for i in range(n):
            d.joinpath(f"{name}_s{i}.test.json").write_text("{}", encoding="utf-8")


class TestTheRootComesFromTheAppsOwnDeclaration:
    """`test.src` in the app's config, not `<app>/tests`.

    ⚠️ Every app in the tree that exposed this uses `tests`, so a path guess
    would pass an arm written against that tree and would make this the second
    place the convention is enforced. The arm below names a directory the
    convention would NOT find.
    """

    def test_it_reads_test_src_and_not_the_conventional_name(self, tmp_path):
        _app(tmp_path, "alpha", 2, test_src="suites")
        roots = _resolve_test_roots(
            [{"name": "alpha", "docs_path": str(tmp_path / "alpha" / "docs")}])
        assert [r["app"] for r in roots] == ["alpha"]
        assert roots[0]["root"].name == "suites", roots

    def test_an_app_that_declares_no_tests_is_not_an_error(self, tmp_path):
        _app(tmp_path, "alpha", 0, test_src=None)
        assert _resolve_test_roots(
            [{"name": "alpha", "docs_path": str(tmp_path / "alpha" / "docs")}]) == []

    def test_a_declared_directory_that_does_not_exist_is_skipped(self, tmp_path):
        _app(tmp_path, "alpha", 1)
        (tmp_path / "alpha" / "jui.config.json").write_text(
            json.dumps({"test": {"src": "nowhere"}}), encoding="utf-8")
        assert _resolve_test_roots(
            [{"name": "alpha", "docs_path": str(tmp_path / "alpha" / "docs")}]) == []

    def test_the_control_the_conventional_layout_still_resolves(self, tmp_path):
        """If this ever fails, the arms above are measuring nothing."""
        _app(tmp_path, "alpha", 2)
        roots = _resolve_test_roots(
            [{"name": "alpha", "docs_path": str(tmp_path / "alpha" / "docs")}])
        assert len(roots) == 1 and roots[0]["root"].name == "tests"
