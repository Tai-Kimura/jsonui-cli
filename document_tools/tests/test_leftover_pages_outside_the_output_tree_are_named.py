"""Regression: doc-leftover-pages-outside-the-output-tree-are-never-scanned-so-a-rename-leaves-a-page-nobody-names.

The stale-page scan covered `-o` only. A face's own docs directory — which
the run rewrites in place, outside `-o` — was never scanned, so a renamed
spec's old pages (html and md) stayed behind with nothing naming them while
the site carried both names; and a site run copies each face's docs into the
output, so the orphan opens from the site index too (triage, on a second
face and a second spec).

The directories the run wrote outside `-o` are scanned with the same
predicate (not written by this run, untouched since it started); the count
is printed per directory with any site copy named; and each face's manifest
records the leftovers under ITS scope as an explicit number — zero included.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _manifest(root: Path) -> dict:
    return json.loads((root / ".jsonui-cli" / "generation-manifest.json").read_text(encoding="utf-8"))


@pytest.fixture()
def run(tmp_path, monkeypatch):
    """Two faces; the run wrote one page into each face's docs and copied
    face a's docs into the site; face a also holds an old page (html + md)
    nothing wrote this time — a renamed spec's leftover — and the site copy
    of that old page was written by this run along with the rest."""
    site = tmp_path / "site"
    out = site / "out"
    out.mkdir(parents=True)
    docs = {}
    written = set()
    for name in ("a", "b"):
        d = site / "docs" / name / "screens" / "html"
        d.mkdir(parents=True)
        page = d / "new_name.html"
        page.write_text("<html></html>", encoding="utf-8")
        written.add(page.resolve())
        (site / name).mkdir()
        docs[name] = site / "docs" / name
    old = time.time() - 3600
    orphan = site / "docs" / "a" / "screens" / "html" / "old_name.html"
    orphan.write_text("<html>old</html>", encoding="utf-8"); os.utime(orphan, (old, old))
    md_dir = site / "docs" / "a" / "screens" / "md"; md_dir.mkdir()
    orphan_md = md_dir / "old_name.md"
    orphan_md.write_text("# old", encoding="utf-8"); os.utime(orphan_md, (old, old))
    site_copy = out / "docs" / "a" / "screens" / "html" / "old_name.html"
    site_copy.parent.mkdir(parents=True)
    site_copy.write_text("<html>old</html>", encoding="utf-8"); written.add(site_copy.resolve())
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    monkeypatch.setattr(gen, "_written_outside_output",
                        {site / "docs" / "a" / "screens" / "html", site / "docs" / "b" / "screens" / "html", md_dir})
    return site, out, docs, orphan, orphan_md, site_copy


def test_the_renamed_faces_old_pages_are_named_per_directory_with_their_site_copy(run, capsys):
    site, out, docs, orphan, orphan_md, site_copy = run
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    assert {p for p, _c in pairs} == {orphan, orphan_md}
    assert dict(pairs)[orphan] == [site_copy] and dict(pairs)[orphan_md] == []
    printed = capsys.readouterr().out
    assert "WARNING [doc-stale]: 2 page(s) outside" in printed
    assert f"{orphan.parent}: 1" in printed and "old_name.html" in printed
    assert f"also copied into the site: {site_copy}" in printed


def test_each_face_records_the_leftovers_under_its_own_scope(run):
    site, out, docs, orphan, orphan_md, site_copy = run
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    targets = [{"app": "a", "root": site / "a", "docs": docs["a"]},
               {"app": "b", "root": site / "b", "docs": docs["b"]}]
    gen._record_generation_manifest(out, targets, [], {}, stale_outside=pairs)
    a = _manifest(site / "a")["summary"]["run"]
    b = _manifest(site / "b")["summary"]["run"]
    assert a["leftoversOutside"] == 2
    assert set(a["leftoverOutsidePaths"]) == {str(orphan), str(orphan_md)}
    assert a["leftoverOutsideSiteCopies"] == [str(site_copy)]
    # Explicit zero on the face with none — an answer, not an absence.
    assert b["leftoversOutside"] == 0 and b["leftoverOutsidePaths"] == [] and b["leftoverOutsideSiteCopies"] == []


def test_no_leftover_is_zero_and_silent(run, capsys):
    site, out, docs, orphan, orphan_md, site_copy = run
    orphan.unlink(); orphan_md.unlink()
    assert gen._report_stale_pages_outside(out, started_at=time.time()) == []
    assert "doc-stale" not in capsys.readouterr().out
    gen._record_generation_manifest(out, site / "a", [], {}, stale_outside=[])
    assert _manifest(site / "a")["summary"]["run"]["leftoversOutside"] == 0


def test_a_page_this_run_touched_is_not_a_leftover_even_if_the_tally_missed_it(run):
    """The second condition of the predicate, kept from the -o scanner."""
    site, out, docs, orphan, orphan_md, site_copy = run
    now = time.time()
    os.utime(orphan, (now, now))
    pairs = gen._report_stale_pages_outside(out, started_at=now)
    assert [p for p, _c in pairs] == [orphan_md]


def test_directories_under_the_output_tree_are_left_to_the_other_scanner(run):
    site, out, docs, orphan, orphan_md, site_copy = run
    inside = out / "x"; inside.mkdir()
    old = time.time() - 3600
    p = inside / "left.html"; p.write_text("x", encoding="utf-8"); os.utime(p, (old, old))
    gen._written_outside_output.add(inside)
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    assert p not in {q for q, _c in pairs}
