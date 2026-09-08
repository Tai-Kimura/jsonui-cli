"""An embedded body links to the pages this run wrote, and the run names what
it wrote outside `-o`.

Two rulings from 2026-09-08, both on `generate html`.

FOUR-1. A test file's `document:` names a page in the SOURCE tree
(`docs/<app>/screens/html/<screen>.html`). The site regenerates that page at
the same relative path and embeds the source body — whose own
`../../components/html/<name>.html` was correct where it came from and points
at a directory the site never writes. The site's component pages are at
`<app>/components/<name>.html`.

This is the third time the same defect has been repaired: 1.8.50 for the unit
back-links, 1.8.51 for the spec page's own component table, and now for the
embedded body. Each time the repair is the same — build the link from the
pages this run WROTE — and each time it needed an ordering change, because a
link cannot be built from pages that do not exist yet. `_generate_document_pages`
now runs after every other page writer.

⚠️ Resolution is by basename among written pages, and only when exactly one
matches. Zero leaves the link alone rather than pointing it somewhere
plausible; more than one means the name is ambiguous across apps, and a wrong
link that resolves is worse than a dangling one that fails when clicked.

FOUR-2. `generate html` also regenerates the per-spec html/md in the SOURCE
tree, for the root scope and for EVERY `--app` in the same invocation. Two
lanes pointing `-o` at different directories are therefore not isolated: one
run rewrites both apps' trees. Two lanes measured against that assumption for
a whole release cycle before a mtime experiment found it. Nothing named it, so
the run names it now — from what was written, not from a rule about where it
would go.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import generate_html_directory

HREF = re.compile(r"""href\s*=\s*(['"])(.*?)\1""", re.I | re.S)
NAV = re.compile(r"<nav\b.*?</nav>", re.I | re.S)

COMPONENT_FILE = "picker.component.json"


def _component_spec(name: str = "Picker") -> dict:
    return {
        "type": "component_spec", "version": "1.0",
        "metadata": {"name": name, "displayName": name,
                     "description": "Picks a range.", "category": "input"},
        "props": {},
        "structure": {
            "components": [{"type": "View", "id": "root", "description": "r"}],
            "layout": {"root": "root", "children": []},
        },
    }


def _screen_spec(screen: str, component_file: str | None) -> dict:
    spec = {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": screen, "name": "S", "displayName": "S",
                     "description": "A screen."},
        "structure": {
            "components": [{"type": "View", "id": "root", "description": "r"}],
            "layout": {"root": "root", "children": []},
        },
    }
    if component_file:
        spec["structure"]["customComponents"] = [{
            "name": "Picker", "specFile": component_file,
            "description": "Picks a range.",
        }]
    return spec


class _Site(unittest.TestCase):
    APP = "user"
    SCREEN = "booking"

    def build(self, *, with_component_spec: bool = True,
              second_app: bool = False) -> tuple[Path, str]:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        tests_dir = root / "tests"
        tests_dir.mkdir()
        # The `document:` value is the site-relative path of the page, and the
        # source tree path it is read from. That double duty is what carries
        # the body into a tree it was not written for.
        doc = f"docs/{self.APP}/screens/html/{self.SCREEN}.html"
        (tests_dir / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios",
            # ⚠️ `document` lives under `source`, not at the top level.
            "source": {"layout": "s", "document": doc},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        (root / "jui.config.json").write_text(json.dumps({
            "spec_directory": f"docs/{self.APP}/screens/json",
            "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                  "testModule": "App"}},
        }), encoding="utf-8")

        apps = []
        for app in ([self.APP, "admin"] if second_app else [self.APP]):
            docs = root / "docs" / app
            (docs / "screens" / "json").mkdir(parents=True)
            (docs / "components" / "json").mkdir(parents=True)
            (docs / "screens" / "json" / f"{self.SCREEN}.spec.json").write_text(
                json.dumps(_screen_spec(self.SCREEN, COMPONENT_FILE)),
                encoding="utf-8")
            if with_component_spec:
                (docs / "components" / "json" / COMPONENT_FILE).write_text(
                    json.dumps(_component_spec()), encoding="utf-8")
            apps.append({"name": app, "docs_path": str(docs)})

        out = root / "out"
        out.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_html_directory(tests_dir, out, "T", apps=apps)
        return out, buf.getvalue()

    def body_of(self, page: Path) -> str:
        self.assertTrue(page.is_file(), f"{page} was not generated")
        return NAV.sub("", page.read_text(encoding="utf-8"))

    def component_hrefs(self, body: str) -> list[str]:
        return [m.group(2) for m in HREF.finditer(body)
                if "components" in m.group(2) and m.group(2).endswith(".html")]


class TheEmbeddedBodyPointsAtPagesThisRunWrote(_Site):

    def test_the_component_link_resolves_to_a_file_this_run_wrote(self):
        out, _ = self.build()
        page = out / "docs" / self.APP / "screens" / "html" / f"{self.SCREEN}.html"
        hrefs = self.component_hrefs(self.body_of(page))
        self.assertTrue(hrefs, "the embedded body carried no component link")
        for h in hrefs:
            resolved = Path(os.path.normpath(page.parent / h))
            self.assertTrue(
                resolved.is_file(),
                f"document page emits href={h!r} -> {resolved}, which this run "
                "never wrote. The body was correct in the source tree; it is "
                "embedded here at a different depth in a different tree.")

    def test_it_points_at_the_sites_own_component_page(self):
        # Resolution alone would accept a link to any existing html file.
        out, _ = self.build()
        page = out / "docs" / self.APP / "screens" / "html" / f"{self.SCREEN}.html"
        written = out / self.APP / "components" / "picker.html"
        self.assertTrue(written.is_file(), "the site's component page is missing")
        resolved = {Path(os.path.normpath(page.parent / h))
                    for h in self.component_hrefs(self.body_of(page))}
        self.assertIn(written, resolved)

    def test_a_component_with_no_page_is_left_alone(self):
        # ⚠️ The arm that separates this from "always emit something". With no
        # component spec the run writes no component page, and pointing the
        # link at a plausible path would produce a link that resolves to
        # nothing — the defect being repaired, reintroduced by the repair.
        #
        # 🚨 RE-POINTED 2026-09-08. This used to assert the ORIGINAL href was
        # still present — and that contradicted the comment above it. The href
        # it was observing came from the legacy `../../components/html/<name>`
        # template, i.e. from a link that resolves to nothing: exactly what
        # this arm says must not be produced. It only looked harmless because
        # the rewriter left it alone rather than making it worse.
        #
        # `_pre_generate_spec_docs` now supplies `component_links`, so a
        # declared component with no spec file renders as TEXT instead. The
        # subject is unchanged — nothing may point at a page this run did not
        # write — so the assertion now states that directly, and passes for
        # both "no link" and "a link that resolves", while the old form passed
        # only for the dangling case.
        out, _ = self.build(with_component_spec=False)
        page = out / "docs" / self.APP / "screens" / "html" / f"{self.SCREEN}.html"
        for h in self.component_hrefs(self.body_of(page)):
            self.assertTrue(
                (page.parent / h).resolve().is_file(),
                f"{h} resolves to {(page.parent / h).resolve()}, which this "
                f"run did not write — a component with no spec must render as "
                f"text, not as a link nobody can follow")

    def test_a_name_carried_by_two_apps_is_left_alone(self):
        # Two apps declare a component of the same name, so the basename does
        # not identify one page. A link that resolves to the WRONG app is
        # worse than one that fails when clicked.
        out, _ = self.build(second_app=True)
        page = out / "docs" / self.APP / "screens" / "html" / f"{self.SCREEN}.html"
        for h in self.component_hrefs(self.body_of(page)):
            self.assertIn("components/html/", h)

    def test_both_quote_spellings_are_rewritten(self):
        # The generator writes `'` in the nav and `"` in the component table.
        # A rewriter that handles one spelling silently leaves the other —
        # which is exactly how the body links were reported as absent on
        # 2026-09-08, from a scan that only counted one of them.
        from jsonui_doc_cli.test_doc.generator import _component_body_rewriter
        from jsonui_doc_cli.test_doc.generator import note_page_generated, reset_page_failures
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        target = root / "user" / "components" / "picker.html"
        target.parent.mkdir(parents=True)
        target.write_text("x", encoding="utf-8")
        reset_page_failures()
        note_page_generated(target)
        page = root / "docs" / "user" / "screens" / "html" / "booking.html"
        rewrite = _component_body_rewriter(page, root)
        out = rewrite(
            '<a href="../../components/html/picker.html">d</a>'
            "<a href='../../components/html/picker.html'>s</a>")
        self.assertEqual(out.count("../../../../user/components/picker.html"), 2,
                         f"only one spelling was rewritten: {out}")
        reset_page_failures()

    def test_a_non_component_link_in_the_body_is_untouched(self):
        from jsonui_doc_cli.test_doc.generator import _component_body_rewriter
        from jsonui_doc_cli.test_doc.generator import reset_page_failures
        reset_page_failures()
        rewrite = _component_body_rewriter(Path("/a/b/c.html"), Path("/a"))
        body = '<a href="../other/thing.html">x</a><a href=\'#anchor\'>y</a>'
        self.assertEqual(rewrite(body), body)


class TheRunNamesWhatItWroteOutsideOutput(_Site):

    def test_the_directories_outside_o_are_named(self):
        _, printed = self.build(second_app=True)
        self.assertIn("Also written OUTSIDE", printed)
        # ⚠️ The point is the SECOND app: one run rewrites every --app tree,
        # which is what broke two lanes' isolation while each believed its own
        # -o kept it separate.
        self.assertIn("docs/user/screens/html", printed)
        self.assertIn("docs/admin/screens/html", printed)
        self.assertIn("not isolated", printed)

    def test_it_says_nothing_when_there_is_nothing_outside(self):
        # The complement. A line that prints on every run is a line nobody
        # reads, and this one exists to be noticed.
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        tests_dir = root / "tests"
        tests_dir.mkdir()
        (tests_dir / "s.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s"},
            "metadata": {"name": "s", "description": "d"},
            "cases": [{"name": "opens", "description": "opens",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        out = root / "out"
        out.mkdir()
        buf = io.StringIO()
        with redirect_stdout(buf):
            generate_html_directory(tests_dir, out, "T")
        self.assertNotIn("Also written OUTSIDE", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
