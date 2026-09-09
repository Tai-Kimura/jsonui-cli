"""A `document:` is resolved from the app that declared the test.

The base used to be the directory the run was pointed at. For a single-app run
those are the same thing; for every other run they are not, and a page that
exists only under its own app was reported missing because the run's input was
a different app's tree. Measured on a four-face consumer tree: one face
declared six documents and five of them printed `Document not found` while the
files sat exactly where that face's own root says they should. (That was the
spelling at the time; since 2026-09-10 the line reads
`WARNING [doc-missing]: document not found`, so do not grep this file's prose
for the current output.)

The map is not a new declaration. `roots` already pairs each declared test
directory with the app that declared it — v1.8.63 built it — and this call
site simply was not reading it. That is the same shape as the defect v1.8.63
repaired one function away, which is why the family was enumerated before
anything was changed: four sites derive a base from the run's input
(`docs_base`, the per-group flow base, `figma_dir`, and this one).

⚠️ WHAT THIS DOES NOT FIX, and the arms here must not appear to. Two apps
declaring the SAME relative path still collapse into one slot: the dict is
keyed by the path alone, so the last declarer wins the entry before any
resolution happens. That has its own ticket. `TheCollapseIsStillHere` pins the
unfixed behaviour deliberately — if it starts failing, the other ticket landed
and this file's claim about scope is out of date.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import (
    _report_document_slot_collisions,
    generate_html_directory,
)

TITLE = re.compile(r"<title>(.*?)</title>", re.S)


def _site(root: Path, docs: dict[str, str]) -> tuple[Path, str]:
    """Build a two-app tree. `docs` maps app name -> declared relative path.

    Each app's own copy of the page carries its name in the body, because the
    only way to see WHICH original landed is to make the originals differ. A
    fixture whose two sides are identical cannot show a resolution defect at
    all — both answers look the same.
    """
    apps = []
    for app, doc in docs.items():
        app_docs = root / "docs" / app
        (app_docs / "screens" / "json").mkdir(parents=True)
        tests = root / app / "tests"
        tests.mkdir(parents=True)
        page = root / app / doc
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            f"<html><head><title>ORIGINAL {app}</title></head>"
            f"<body>{app} body</body></html>", encoding="utf-8")
        (tests / "t.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios",
            "source": {"layout": "s", "document": doc},
            "metadata": {"name": f"{app} test", "description": "d"},
            "cases": [{"name": "c", "description": "c",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        apps.append({"name": app, "docs_path": str(app_docs)})

    out = root / "out"
    out.mkdir()
    buf = io.StringIO()
    with redirect_stdout(buf):
        # The run is pointed at ONE app's tests. That is the whole point: the
        # other app's documents must still resolve from its own root.
        generate_html_directory(
            root / next(iter(docs)) / "tests", out, "T", apps=apps,
            test_roots=[{"app": a["name"],
                         "root": str(root / a["name"] / "tests")} for a in apps],
        )
    return out, buf.getvalue()


class _Tree(unittest.TestCase):
    def build(self, docs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return _site(Path(tmp.name), docs)

    def body_owner(self, page: Path) -> str:
        text = page.read_text(encoding="utf-8")
        for app in ("alpha", "beta"):
            if f"{app} body" in text:
                return app
        return "none"


class ADocumentResolvesFromItsOwnAppsRoot(_Tree):
    OWN = {"alpha": "docs/screens/html/alpha_only.html",
           "beta": "docs/screens/html/beta_only.html"}

    def test_the_app_the_run_was_not_pointed_at_still_resolves(self):
        out, log = self.build(self.OWN)
        page = out / "beta" / self.OWN["beta"]
        self.assertTrue(page.is_file(),
                        "beta's document was not written; the base was still "
                        "the run's input")
        self.assertEqual(self.body_owner(page), "beta")

    def test_the_run_s_own_app_still_resolves(self):
        """The control for the arm above — but NOT for the reason first
        written here.

        It was labelled "an implementation that resolves only from the map and
        forgets the run itself passes the arm above". That is false: the run's
        own input IS in the map, as the `None` key, so this case goes through
        the same lookup as every other app. A mutation that dropped the
        separate `input_path` fallback left all six arms green, and the honest
        reading was that the fallback was redundant, not that the arm was
        weak. It was removed rather than defended.

        What this still controls is narrower and worth keeping: a resolver
        that only ever answers for NON-owner apps would fail here.
        """
        out, _ = self.build(self.OWN)
        page = out / "alpha" / self.OWN["alpha"]
        self.assertTrue(page.is_file())
        self.assertEqual(self.body_owner(page), "alpha")

    #: The two arms below are a PAIR, and they must share this predicate.
    #: 2026-09-10 the message was respelled `Document not found` ->
    #: `WARNING [doc-missing]: document not found`, and only the positive arm
    #: was updated — which left the negative one asserting the absence of a
    #: string that no longer appears at all. It passed, for the wrong reason,
    #: and its own control could no longer catch that because the control is
    #: the other arm. Case-folded, and named once.
    MISSING_MARKER = "document not found"

    def _reports_missing(self, text: str) -> bool:
        return self.MISSING_MARKER in text.lower()

    def test_nothing_is_reported_missing(self):
        _, log = self.build(self.OWN)
        self.assertFalse(self._reports_missing(log))

    def test_a_genuinely_missing_document_still_warns(self):
        """The control for the arm above. A run that reports nothing missing
        because it stopped looking would satisfy it just as well."""
        out, log = self.build({"alpha": "docs/screens/html/alpha_only.html",
                               "beta": "docs/screens/html/beta_only.html"})
        # Re-run with beta's file removed.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        out, log = _site(root, self.OWN)
        (root / "beta" / self.OWN["beta"]).unlink()
        out2 = root / "out2"
        out2.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_html_directory(
                root / "alpha" / "tests", out2, "T",
                apps=[{"name": a, "docs_path": str(root / "docs" / a)}
                      for a in ("alpha", "beta")],
                test_roots=[{"app": a, "root": str(root / a / "tests")}
                            for a in ("alpha", "beta")],
            )
        self.assertTrue(self._reports_missing(buf.getvalue()))

    def test_the_warning_names_every_base_it_tried(self):
        # "not found" with one path in it sends the reader to move a file that
        # is already in the right place.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        _site(root, self.OWN)
        (root / "beta" / self.OWN["beta"]).unlink()
        out = root / "out3"
        out.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_html_directory(
                root / "alpha" / "tests", out, "T",
                apps=[{"name": a, "docs_path": str(root / "docs" / a)}
                      for a in ("alpha", "beta")],
                test_roots=[{"app": a, "root": str(root / a / "tests")}
                            for a in ("alpha", "beta")],
            )
        log = buf.getvalue()
        self.assertIn("Owner: beta", log)
        self.assertIn("Tried:", log)


class ASharedSlotIsCountedAndItsClaimantsNamed(_Tree):
    """A slot is the FILE a declaration lands on, and every test naming it is listed.

    🔻 Inverted 2026-09-10. Until the app segment landed, the slot was the
    declared path alone, so two apps naming one path collided and this class
    named a winner and losers. Since then each app's page is written under its
    own segment: two apps naming one path are two files, and a report keyed on
    the bare path was announcing SHARED SLOT for pairs that share nothing —
    while the manifest beside it said `collisions: 0`, a different quantity
    under the same word. The key is now `document_output_rel_path`, the
    function that decides where the page goes.

    🔻 "kept / overwritten" is gone with it. The page is generated from the
    document alone, so same owner + same path = same source = same bytes;
    whichever declaration is processed last, nothing any test said is lost.
    The faces went looking for the overwritten content and found identical
    files. What is true, and actionable, is that several tests name one page
    — so all of them are listed, none as a loser.

    🔻 THE ZERO IS PRINTED TOO. Without it, "we looked and found none" reads
    exactly like "nobody looked".
    """

    SHARED = {"alpha": "docs/screens/html/login.html",
              "beta": "docs/screens/html/login.html"}
    OWN = {"alpha": "docs/screens/html/alpha_only.html",
           "beta": "docs/screens/html/beta_only.html"}

    def test_two_apps_naming_one_path_are_two_files_not_a_shared_slot(self):
        # The inverted arm. Red again means either the segment stopped being
        # applied or the report stopped asking the writer where pages go.
        _, log = self.build(self.SHARED)
        self.assertIn("0 shared by more than one test", log)
        self.assertNotIn("SHARED SLOT", log)

    def test_the_count_is_printed_when_it_is_zero(self):
        _, log = self.build(self.OWN)
        self.assertIn("0 shared by more than one test", log,
                      "a run with no shared slots says nothing, so silence "
                      "cannot be told from not looking")

    def test_the_count_follows_the_file_not_the_declared_path(self):
        """The 1->0 arm, on the function rather than the whole run."""
        two_apps_one_path = [("alpha", "p.html", "a"), ("beta", "p.html", "b")]
        one_app_one_path_twice = [("alpha", "p.html", "a"), ("alpha", "p.html", "b")]
        one_app_two_paths = [("alpha", "p.html", "a"), ("alpha", "q.html", "b")]
        self.assertEqual(_report_document_slot_collisions(two_apps_one_path), 0)
        self.assertEqual(_report_document_slot_collisions(one_app_one_path_twice), 1)
        self.assertEqual(_report_document_slot_collisions(one_app_two_paths), 0)

    def test_two_tests_in_ONE_app_still_share_one_file(self):
        """The segment separates apps; it does nothing inside one.

        Measured on a consumer tree — 201 declarations over 30 paths, 29
        shared, 171 folded, and every one of the 29 inside a single app. The
        first version of this reporter was handed a dict keyed by (owner,
        path), which had already merged them, and announced "1 declaration,
        0 shared" for three colliding tests. It counted the survivors.
        """
        same_app = [("alpha", "p.html", "one"),
                    ("alpha", "p.html", "two"),
                    ("alpha", "p.html", "three")]
        self.assertEqual(_report_document_slot_collisions(same_app), 1)

    def test_every_test_naming_the_page_is_listed_and_none_is_a_loser(self):
        import contextlib
        import io as _io
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            _report_document_slot_collisions(
                [("alpha", "p.html", "one"), ("alpha", "p.html", "two"),
                 ("alpha", "p.html", "three")])
        log = out.getvalue()
        self.assertIn("from 3 declaration(s)", log)
        self.assertIn("SHARED SLOT alpha/p.html", log)
        self.assertIn("3 test(s) resolve to this page", log)
        for name in ("one", "two", "three"):
            self.assertRegex(log, rf"\n\s+{name} \(alpha\)\n")
        # The removed wording. Same bytes whichever declaration lands last, so
        # there is no loser to name; naming one sent readers to look for
        # content that was never lost.
        self.assertNotIn("overwritten", log)
        self.assertNotIn("kept:", log)

    def test_the_slot_is_spelled_as_the_writer_spells_it(self):
        """The report and the writer must agree on what "the same file" means."""
        import contextlib
        import io as _io
        from jsonui_doc_cli.test_doc.generator import document_output_rel_path
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            _report_document_slot_collisions(
                [("beta", "docs/beta/x.html", "one"),
                 ("beta", "docs/beta/x.html", "two")])
        self.assertIn(
            f"SHARED SLOT {document_output_rel_path('beta', 'docs/beta/x.html')}",
            out.getvalue())

    def test_the_denominators_are_both_reported(self):
        # paths AND declarations: 2 declarations over 2 files is a different
        # tree from 2 over 1, and only the pair says which.
        _, log = self.build(self.SHARED)
        self.assertRegex(log, r"Document slots: 2 path\(s\) from 2 declaration\(s\)")


class ThePageKeepsItsOwnTitle(_Tree):
    """The page's title is the page's, not the name of a test that mentions it.

    `generate_document_html` already reads the source's own `<title>` when it
    is passed none. The generator passed a test name, so whichever declaration
    won the slot also named the page — and on a real tree that put a test's
    name on a page whose own title says which screen it documents.

    ⚠️ NO ARM PINNED THIS BEFORE. Changing it left 962 green, which is how the
    override survived: the value was carried through three functions and
    asserted nowhere. The count of passing tests said nothing about it.
    """

    OWN = {"alpha": "docs/screens/html/alpha_only.html",
           "beta": "docs/screens/html/beta_only.html"}

    def title_of(self, page: Path) -> str:
        m = TITLE.search(page.read_text(encoding="utf-8"))
        return m.group(1).strip() if m else ""

    def test_the_title_comes_from_the_source_document(self):
        out, _ = self.build(self.OWN)
        self.assertEqual(self.title_of(out / "alpha" / self.OWN["alpha"]),
                         "ORIGINAL alpha")

    def test_it_is_not_the_name_of_the_test_that_declared_it(self):
        # The control: the fixture's test names are distinct from its page
        # titles, so an implementation that still passes the test name fails
        # here rather than coinciding.
        out, _ = self.build(self.OWN)
        self.assertNotEqual(self.title_of(out / "beta" / self.OWN["beta"]), "beta test")
        self.assertEqual(self.title_of(out / "beta" / self.OWN["beta"]), "ORIGINAL beta")

    def test_a_contested_page_is_still_titled_by_a_source_not_by_a_test(self):
        """Twelve declarations used to mean twelve possible titles, decided by
        iteration order.

        🚫 THIS DOES NOT SAY THE CONTEST IS RESOLVED. One slot is still
        written and the last declarer still wins it, so which source names the
        page still depends on order — the first version of this arm asserted
        `alpha` and was simply wrong about who wins. What the arm can say, and
        all it says, is that the winner is a SOURCE and never a test name.
        The remaining half is the output path, which is a separate item on the
        same ticket and not yet done.
        """
        out, _ = self.build({"alpha": "docs/screens/html/login.html",
                             "beta": "docs/screens/html/login.html"})
        title = self.title_of(out / "alpha" / "docs/screens/html/login.html")
        self.assertIn(title, {"ORIGINAL alpha", "ORIGINAL beta"})
        self.assertNotIn("test", title)


class TheCollapseIsGone(_Tree):
    """Was `TheCollapseIsStillHere`, and it did the job it was left for.

    It pinned the unfixed behaviour — two apps declaring one relative path
    producing one file — so the scope claim in this file could not go stale in
    silence. When the output path learned to carry the declaring app, this arm
    failed with "the collapse was repaired", which is the only reason the
    docstring above is not still describing a defect that no longer exists.

    An arm on an unfixed thing is worth writing for exactly that: it is the
    only kind of note that reads itself.
    """

    SHARED = {"alpha": "docs/screens/html/login.html",
              "beta": "docs/screens/html/login.html"}

    def test_two_apps_sharing_a_path_get_a_page_each(self):
        out, _ = self.build(self.SHARED)
        slots = sorted(p.relative_to(out).as_posix()
                       for p in out.rglob("login.html"))
        self.assertEqual(slots, ["alpha/docs/screens/html/login.html",
                                 "beta/docs/screens/html/login.html"])

    def test_each_page_carries_its_own_app_s_body(self):
        # Two files is not the claim; two RIGHT files is. Splitting the slot
        # while both copies rendered one app's source would satisfy the arm
        # above and none of the point.
        out, _ = self.build(self.SHARED)
        self.assertEqual(
            self.body_owner(out / "alpha/docs/screens/html/login.html"), "alpha")
        self.assertEqual(
            self.body_owner(out / "beta/docs/screens/html/login.html"), "beta")

    def test_a_run_with_nothing_declared_gets_no_segment(self):
        """The absent segment is the honest rendering of an absent
        declaration, not a hole to fill with a made-up name."""
        from jsonui_doc_cli.test_doc.generator import document_output_rel_path
        self.assertEqual(document_output_rel_path(None, "a/b.html"), "a/b.html")
        self.assertEqual(document_output_rel_path("", "a/b.html"), "a/b.html")
        self.assertEqual(document_output_rel_path("bar", "a/b.html"),
                         "bar/a/b.html")

    def test_the_nav_points_where_the_page_was_written(self):
        # A page moved without its links is worse than the collision it
        # replaces: that one was at least visible in the output.
        out, _ = self.build(self.SHARED)
        index = (out / "index.html").read_text(encoding="utf-8")
        for app in ("alpha", "beta"):
            self.assertIn(f"{app}/docs/screens/html/login.html", index)


if __name__ == "__main__":
    unittest.main()
