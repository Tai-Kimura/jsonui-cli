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
    # The run renders every markdown under the faces' docs into the site —
    # the stale one included. That rendered page is the orphan's site copy,
    # and its SOURCE is the orphan.
    monkeypatch.setattr(gen, "_page_sources", {})
    md_files = gen._collect_markdown_files([docs["a"], docs["b"]])
    gen._generate_markdown_pages([docs["a"], docs["b"]], out, None, md_files)
    written |= gen.get_written_pages()
    site_copy = (out / "md" / "screens" / "md" / "old_name.html").resolve()
    assert site_copy in written, "fixture: the stale markdown must have been rendered into the site"
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    monkeypatch.setattr(gen, "_written_outside_output",
                        {site / "docs" / "a" / "screens" / "html", site / "docs" / "b" / "screens" / "html", md_dir})
    return site, out, docs, orphan, orphan_md, site_copy


def test_the_renamed_faces_old_pages_are_named_per_directory_with_their_site_copy(run, capsys):
    site, out, docs, orphan, orphan_md, site_copy = run
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    assert {p for p, _c in pairs} == {orphan, orphan_md}
    # The html orphan has no page rendered FROM it; the md orphan has one.
    assert dict(pairs)[orphan] == [] and dict(pairs)[orphan_md] == [site_copy]
    printed = capsys.readouterr().out
    assert "WARNING [doc-stale]: 2 page(s) outside" in printed
    assert f"{orphan.parent}: 1" in printed and "old_name.html" in printed and "old_name.md" in printed
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


def test_another_faces_live_page_with_the_same_name_is_not_a_copy(run, monkeypatch):
    """Two faces share a screen name; only one renamed. The other face's live
    page — same file name, same parent directory name — has its own source
    and must not be named as the orphan's copy. This is the shape that
    produced the false positive (a tree where two faces both hold a screen
    of one name)."""
    site, out, docs, orphan, orphan_md, site_copy = run
    live_dir = docs["b"] / "screens" / "md"; live_dir.mkdir()
    live = live_dir / "old_name.md"; live.write_text("# live on face b", encoding="utf-8")
    monkeypatch.setattr(gen, "_page_sources", {})
    # Same relative path on both faces → one site slot; the live face renders
    # LAST, so the slot's source is the live file (the shared-slot report
    # covers the overwrite itself).
    md_files = gen._collect_markdown_files([docs["a"], docs["b"]])
    gen._generate_markdown_pages([docs["a"], docs["b"]], out, None, md_files)
    written = set(gen._pages_written) | {(docs["a"] / "screens" / "html" / "new_name.html").resolve(),
                                       (docs["b"] / "screens" / "html" / "new_name.html").resolve()}
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    pairs = dict(gen._report_stale_pages_outside(out, started_at=time.time()))
    live_pages = {page for page, src in gen._page_sources.items() if src == live.resolve()}
    assert live_pages, "fixture: face b's live markdown must have rendered"
    # By name the slot would be the orphan's copy; by source it is not.
    assert pairs[orphan_md] == []
    assert not (set(pairs[orphan_md]) & live_pages)
    assert live not in pairs  # b's live file is not a leftover


def test_both_faces_renamed_gives_each_orphan_its_own_copy(run, monkeypatch):
    """Positive control for the source rule: two orphans, two copies."""
    site, out, docs, orphan, orphan_md, site_copy = run
    md_b = docs["b"] / "components" / "md"; md_b.mkdir(parents=True)
    old = time.time() - 3600
    orphan_b = md_b / "gone.md"; orphan_b.write_text("# gone", encoding="utf-8"); os.utime(orphan_b, (old, old))
    monkeypatch.setattr(gen, "_page_sources", {})
    md_files = gen._collect_markdown_files([docs["a"], docs["b"]])
    gen._generate_markdown_pages([docs["a"], docs["b"]], out, None, md_files)
    written = set(gen._pages_written) | {(docs["a"] / "screens" / "html" / "new_name.html").resolve(),
                                       (docs["b"] / "screens" / "html" / "new_name.html").resolve()}
    monkeypatch.setattr(gen, "get_written_pages", lambda: set(written))
    gen._written_outside_output.add(md_b)
    pairs = dict(gen._report_stale_pages_outside(out, started_at=time.time()))
    assert pairs[orphan_md] == [site_copy]
    assert pairs[orphan_b] == [(out / "md" / "components" / "md" / "gone.html").resolve()]
    assert pairs[orphan] == []


def test_an_orphan_that_tests_still_name_is_reported_as_theirs_not_as_deletable(run, monkeypatch, capsys):
    """A renamed spec's old page can still be what five tests resolve their
    `source.document` to. Deleting it on the report's word would turn those
    five into doc-missing next run; the report says who still names it."""
    site, out, docs, orphan, orphan_md, site_copy = run
    monkeypatch.setattr(gen, "_document_referrers", {orphan.resolve(): ["Settings (email)", "Settings (withdraw)"]})
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    printed = capsys.readouterr().out
    assert "2 test(s) still name it as source.document" in printed and "Settings (email)" in printed
    targets = [{"app": "a", "root": site / "a", "docs": docs["a"]}]
    gen._record_generation_manifest(out, targets, [], {}, stale_outside=pairs)
    refs = _manifest(site / "a")["summary"]["run"]["leftoverOutsideReferencedBy"]
    assert refs[str(orphan)] == 2 and refs[str(orphan_md)] == 0


def test_the_document_writer_registers_its_source_and_its_referrers(tmp_path, monkeypatch):
    """The one writer that did not record its source now does, with the tests
    that name the document — from the writer itself, not from a stub."""
    site = tmp_path / "site"
    (site / "docs").mkdir(parents=True)
    doc = site / "docs" / "guide.html"
    doc.write_text("<html><body>guide</body></html>", encoding="utf-8")
    out = site / "out"; out.mkdir()
    monkeypatch.setattr(gen, "_page_sources", {})
    monkeypatch.setattr(gen, "_document_referrers", {})
    generated_files = [
        {"name": "Guide test one", "document": "docs/guide.html", "group": None},
        {"name": "Guide test two", "document": "docs/guide.html", "group": None},
    ]
    gen._generate_document_pages(site / "tests", out, generated_files, {"tests": []}, roots_by_app={None: site})
    assert gen._document_referrers.get(doc.resolve()) == ["Guide test one", "Guide test two"]
    assert doc.resolve() in set(gen._page_sources.values())


def test_a_scoped_zero_says_how_many_the_scan_found_outside_this_scope(run):
    """Regression: scoped-zero-hides-the-nonzero-the-scan-found-leftoversOutside.

    A single-root run's scope is the root alone, so leftovers in the face's
    docs — which the scan DID find and the console DID name — fall outside
    it and the block recorded 0. Under the one-convention-for-zero ruling
    (1.8.68) a 0 means "the run counted and found none", so that 0 was false
    by the tool's own rule. Reported 2026-09-10 by the face that had asked
    for that ruling: its console said 3 pages while its manifest said 0.
    Counted, not listed, like `outsideOutput.elsewhere`.

    ⚠️ This does not reproduce on a two-app run: there the scope holds each
    face's docs, so the leftovers land INSIDE it. The single-root shape is
    the only one that shows it.
    """
    site, out, docs, orphan, orphan_md, site_copy = run
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    assert len(pairs) == 2, "fixture: this is what the scan and the console found"

    # Single root: scope is `site/a` alone; the leftovers live under site/docs/a.
    gen._record_generation_manifest(out, site / "a", [], {}, stale_outside=pairs)
    run_block = _manifest(site / "a")["summary"]["run"]
    assert run_block["leftoversOutside"] == 0
    assert run_block["leftoverOutsidePaths"] == []
    # …and the 0 says the scan ran, through its denominator — not through a
    # run-wide complement. `leftoversOutsideElsewhere` carried the OTHER
    # faces' leftovers into this face's record and moved a tracked file on a
    # face with nothing of its own behind it (inverted 2026-09-11, ticket
    # doc-face-manifest-counts-other-faces-leftovers). The console's total
    # is the log's; the record says what is under this root.
    assert "leftoversOutsideElsewhere" not in run_block
    assert run_block["leftoversOutsideScanned"] >= 1


def test_a_scope_that_covers_the_leftovers_reports_none_elsewhere(run):
    """The control for the arm above: same run, same leftovers, a scope that
    holds them — and the face that holds none of them records none, with no
    run-wide key that would move its manifest for another face's page."""
    site, out, docs, orphan, orphan_md, site_copy = run
    pairs = gen._report_stale_pages_outside(out, started_at=time.time())
    targets = [{"app": "a", "root": site / "a", "docs": docs["a"]},
               {"app": "b", "root": site / "b", "docs": docs["b"]}]
    gen._record_generation_manifest(out, targets, [], {}, stale_outside=pairs)
    a = _manifest(site / "a")["summary"]["run"]
    b = _manifest(site / "b")["summary"]["run"]
    assert a["leftoversOutside"] == 2 and "leftoversOutsideElsewhere" not in a
    # Face b holds none of them: 0 under its scope, and NOTHING about what
    # the scan found under someone else's — that was the key that made b's
    # tracked manifest move when only a had changed.
    assert b["leftoversOutside"] == 0 and "leftoversOutsideElsewhere" not in b


def test_a_zero_says_whether_it_had_anything_to_scan(run):
    """triage's sharpening of the scoped-zero ticket, 2026-09-10.

    `leftoversOutside: 0` comes out of two different runs: one that walked
    four directories and found nothing, and one that had no directory
    registered to walk. The discriminator lived in the record already
    (`outsideOutput.directories`), but a reader gating on
    `leftoversOutside == 0` does not know that, and passes unconditionally
    on the second kind. So the scan's own denominator sits beside the count.
    """
    site, out, docs, orphan, orphan_md, site_copy = run
    orphan.unlink(); orphan_md.unlink()          # nothing stale, dirs still registered
    assert gen._report_stale_pages_outside(out, started_at=time.time()) == []
    gen._record_generation_manifest(out, site / "a", [], {}, stale_outside=[])
    looked = _manifest(site / "a")["summary"]["run"]
    assert looked["leftoversOutside"] == 0
    assert looked["leftoversOutsideScanned"] == 3, "the fixture registers three directories"

    # The other run that produces the same 0: nothing registered to scan.
    gen._written_outside_output.clear()
    gen._stale_outside_scanned = 0
    assert gen._report_stale_pages_outside(out, started_at=time.time()) == []
    gen._record_generation_manifest(out, site / "b", [], {}, stale_outside=[])
    blind = _manifest(site / "b")["summary"]["run"]
    assert blind["leftoversOutside"] == 0
    assert blind["leftoversOutsideScanned"] == 0
    # The two runs differ on the denominator and only on the denominator —
    # which is the whole claim.
    assert looked["leftoversOutside"] == blind["leftoversOutside"]
    assert looked["leftoversOutsideScanned"] != blind["leftoversOutsideScanned"]
