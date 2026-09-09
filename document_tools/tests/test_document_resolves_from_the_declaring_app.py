"""A `document:` is resolved from the app that declared the test.

The base used to be the directory the run was pointed at. For a single-app run
those are the same thing; for every other run they are not, and a page that
exists only under its own app was reported missing because the run's input was
a different app's tree. Measured on a four-face consumer tree: one face
declared six documents and five of them printed `Document not found` while the
files sat exactly where that face's own root says they should.

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
        page = out / self.OWN["beta"]
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
        page = out / self.OWN["alpha"]
        self.assertTrue(page.is_file())
        self.assertEqual(self.body_owner(page), "alpha")

    def test_nothing_is_reported_missing(self):
        _, log = self.build(self.OWN)
        self.assertNotIn("Document not found", log)

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
        self.assertIn("Document not found", buf.getvalue())

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


class ASharedSlotIsCountedAndItsLoserNamed(_Tree):
    """The collision is reported before it is repaired.

    Two apps declaring one relative path land on one file and the last writer
    keeps it. Nothing said so — no warning, one page, and a successful run.
    The count comes first because a silent collision and no collision are the
    same observation, and because the repair (every page under its declaring
    app's segment) is waiting on a separate question.

    🔻 THE ZERO IS PRINTED TOO. Without it, "we looked and found none" reads
    exactly like "nobody looked", which is the shape this whole family keeps
    producing.
    """

    SHARED = {"alpha": "docs/screens/html/login.html",
              "beta": "docs/screens/html/login.html"}
    OWN = {"alpha": "docs/screens/html/alpha_only.html",
           "beta": "docs/screens/html/beta_only.html"}

    def test_a_shared_slot_is_reported_with_both_claimants(self):
        _, log = self.build(self.SHARED)
        self.assertIn("SHARED SLOT docs/screens/html/login.html", log)
        self.assertIn("overwritten:", log)
        self.assertIn("kept:", log)

    def test_the_loser_is_named_not_just_counted(self):
        # "1 collision" sends nobody anywhere. The declaration that lost is
        # the thing a person has to go and change.
        _, log = self.build(self.SHARED)
        self.assertRegex(log, r"overwritten:\s+alpha test")
        self.assertRegex(log, r"kept:\s+beta test")

    def test_the_count_is_printed_when_it_is_zero(self):
        _, log = self.build(self.OWN)
        self.assertIn("0 shared by more than one test", log,
                      "a run with no collisions says nothing, so silence "
                      "cannot be told from not looking")

    def test_the_count_follows_its_input(self):
        """The 1->0 arm, on the function rather than the whole run."""
        two = [("alpha", "p.html", "a"), ("beta", "p.html", "b")]
        one = [("alpha", "p.html", "a"), ("beta", "q.html", "b")]
        self.assertEqual(_report_document_slot_collisions(two), 1)
        self.assertEqual(_report_document_slot_collisions(one), 0)

    def test_two_tests_in_ONE_app_collide_just_as_hard(self):
        """Crossing apps was never a precondition, and the first version of
        this reporter reproduced that assumption.

        The entry key is the path alone, so two tests in one app collapse
        identically. The reporter was handed a dict keyed by (owner, path),
        which had already merged them, and it duly announced "1 declaration,
        0 shared" for three colliding tests. It counted the survivors.

        Measured on a second consumer tree — 201 declarations over 30 paths,
        29 shared, 171 lost, and every one of the 29 inside a single app. The
        first tree had one collision of each kind, which is how "it needs two
        apps" got written down and stayed there.
        """
        same_app = [("alpha", "p.html", "one"),
                    ("alpha", "p.html", "two"),
                    ("alpha", "p.html", "three")]
        self.assertEqual(_report_document_slot_collisions(same_app), 1)

    def test_a_same_app_collision_names_both_losers(self):
        import contextlib
        import io as _io
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            _report_document_slot_collisions(
                [("alpha", "p.html", "one"), ("alpha", "p.html", "two"),
                 ("alpha", "p.html", "three")])
        log = out.getvalue()
        self.assertIn("from 3 declaration(s)", log)
        self.assertEqual(log.count("overwritten:"), 2)
        self.assertIn("kept:      three", log)

    def test_the_denominators_are_both_reported(self):
        # paths AND declarations: 12 declarations over 10 paths is a different
        # tree from 10 over 10, and only the pair says which.
        _, log = self.build(self.SHARED)
        self.assertRegex(log, r"Document slots: 1 path\(s\) from 2 declaration\(s\)")


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
        self.assertEqual(self.title_of(out / self.OWN["alpha"]),
                         "ORIGINAL alpha")

    def test_it_is_not_the_name_of_the_test_that_declared_it(self):
        # The control: the fixture's test names are distinct from its page
        # titles, so an implementation that still passes the test name fails
        # here rather than coinciding.
        out, _ = self.build(self.OWN)
        self.assertNotEqual(self.title_of(out / self.OWN["beta"]), "beta test")
        self.assertEqual(self.title_of(out / self.OWN["beta"]), "ORIGINAL beta")

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
        title = self.title_of(out / "docs/screens/html/login.html")
        self.assertIn(title, {"ORIGINAL alpha", "ORIGINAL beta"})
        self.assertNotIn("test", title)


class TheCollapseIsStillHere(_Tree):
    """The OTHER ticket, pinned as unfixed on purpose.

    Two apps declaring one relative path still produce one slot. This arm
    exists so that the scope claim in this file's docstring cannot go stale
    silently: when the collapse is repaired, this fails and says so.
    """

    SHARED = {"alpha": "docs/screens/html/login.html",
              "beta": "docs/screens/html/login.html"}

    def test_two_apps_sharing_a_path_still_collapse_to_one_slot(self):
        out, _ = self.build(self.SHARED)
        slots = sorted(p.relative_to(out).as_posix()
                       for p in out.rglob("login.html"))
        self.assertEqual(len(slots), 1,
                         "the collapse was repaired — update this file's "
                         "docstring, which says it was not")


if __name__ == "__main__":
    unittest.main()
