"""Component links on a `generate spec` page point at pages that exist.

The path this replaces was a template — `../../components/html/<name>.html` —
built from the component's NAME and never checked. Measured across five
consumer trees on 2026-09-08: 11 component links in already-shipped generated
docs pointed at a page that exists at a DIFFERENT path in the same repository.

Three shapes, one missing step (nobody asked the disk):

  A  the page is a directory deeper, so `../../` leaves the spec tree
  B  there is no sibling `components/html/` at all, because the project keeps
     component specs in the same directory as its screen specs — that project's
     links were dead at EVERY depth, which is what showed the cause was not
     depth. The first report named only A, from a face that only had A.
  C  the page was never generated — already handled on the site path, which
     renders text instead of a link, and not handled here.

Arms are written so that A and B cannot both be satisfied by one fix that only
counts `../`.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.cli import (
    _component_links_for_page,
    _component_pages_on_disk,
)


def _write(p: Path, text: str = "<html></html>") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class ComponentPageDiscoveryTests(unittest.TestCase):
    """`_component_pages_on_disk` — what the run can actually see."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_legacy_sibling_layout_is_still_found(self):
        # Where the old template was right it must stay right — the defect was
        # presuming this layout, not this layout itself.
        _write(self.root / "components" / "html" / "codeblock.html")
        pages = _component_pages_on_disk(self.root / "html")
        self.assertIn("codeblock.component.json", pages)

    def test_a_page_that_does_not_exist_is_not_offered(self):
        # C. Nothing on disk, nothing in the map, so the emitter renders text.
        pages = _component_pages_on_disk(self.root / "html")
        self.assertEqual({}, pages)

    def test_a_missing_directory_is_not_an_error(self):
        pages = _component_pages_on_disk(self.root / "nowhere" / "html")
        self.assertEqual({}, pages)


class ComponentLinkRelativityTests(unittest.TestCase):
    """`_component_links_for_page` — the number of `../` is computed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.page = _write(self.root / "components" / "html" / "codeblock.html")
        self.pages = {"codeblock.component.json": self.page}

    def tearDown(self):
        self._tmp.cleanup()

    def _resolves_from(self, page_dir: Path) -> bool:
        links = _component_links_for_page(self.pages, page_dir)
        href = links["codeblock.component.json"]
        return os.path.isfile(os.path.normpath(os.path.join(page_dir, href)))

    def test_a_top_level_page_resolves(self):
        self.assertTrue(self._resolves_from(self.root / "screens" / "html"))

    def test_a_nested_page_resolves_too(self):
        # A. This is the arm the original report was about, and the one a
        # hard-coded `../../` fails. It must pass at more than one depth,
        # because a fix that hard-codes `../../../` passes depth 2 and fails 1.
        self.assertTrue(self._resolves_from(self.root / "screens" / "html" / "guides"))

    def test_and_at_three_levels_down(self):
        self.assertTrue(
            self._resolves_from(self.root / "screens" / "html" / "a" / "b"))

    def test_the_href_actually_differs_between_depths(self):
        # Guards against a fix that returns an absolute path, which would make
        # every arm above pass while producing a link that breaks when the
        # tree moves.
        one = _component_links_for_page(
            self.pages, self.root / "screens" / "html")["codeblock.component.json"]
        two = _component_links_for_page(
            self.pages, self.root / "screens" / "html" / "guides")["codeblock.component.json"]
        self.assertNotEqual(one, two)
        self.assertFalse(os.path.isabs(one), one)
        self.assertTrue(two.startswith("../"), two)


class EmittedPageTests(unittest.TestCase):
    """End to end: the row the reader sees."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _spec(self):
        return {
            "type": "screen_spec",
            "metadata": {"name": "Guides", "layoutFile": "guides"},
            "structure": {
                "components": [],
                "layout": {},
                "customComponents": [
                    {"name": "CodeBlock",
                     "specFile": "codeblock.component.json",
                     "description": "-"},
                ],
            },
        }

    def test_a_known_page_becomes_a_link_that_resolves(self):
        from jsonui_doc_cli.spec_doc import generate_spec_html
        page = _write(self.root / "components" / "html" / "codeblock.html")
        page_dir = self.root / "screens" / "html" / "guides"
        links = _component_links_for_page(
            {"codeblock.component.json": page}, page_dir)
        html = generate_spec_html(self._spec(), component_links=links)
        self.assertIn('class="component-link"', html)
        href = html.split('<a href="')[1].split('"')[0]
        self.assertTrue(
            os.path.isfile(os.path.normpath(os.path.join(page_dir, href))), href)

    def test_an_unknown_page_is_text_not_a_dangling_link(self):
        # B and C both land here: when the run cannot see a page, the reader
        # gets the file name rather than a link that goes nowhere. A dangling
        # link is worse than no link — it survives a check that counts links.
        from jsonui_doc_cli.spec_doc import generate_spec_html
        html = generate_spec_html(self._spec(), component_links={})
        self.assertNotIn('class="component-link"', html)
        self.assertIn("codeblock.component.json", html)


class ConfigDerivedRootTests(unittest.TestCase):
    """The `component_spec_directory` root — the half the first arms missed.

    ⚠️ These exist because the nine arms above were ALL GREEN while this root
    was returning None for every project: the helper named two attributes
    ConfigManager does not have, swallowed the exception, and every component
    reference rendered as text. No dangling link, no error — a run that looked
    exactly like the fix working. The arms above only ever exercised the other
    candidate root, so they could not tell the two apart.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.spec_dir = self.root / "docs" / "components" / "json"
        self.spec_dir.mkdir(parents=True)
        self.page_dir = self.root / "docs" / "components" / "html"
        self.page_dir.mkdir(parents=True)
        import jsonui_doc_cli.cli as cli
        self.cli = cli
        self._orig = cli._component_spec_dir_from_config
        cli._component_spec_dir_from_config = lambda: self.spec_dir

    def tearDown(self):
        self.cli._component_spec_dir_from_config = self._orig
        self._tmp.cleanup()

    def _component(self, name):
        (self.spec_dir / f"{name}.component.json").write_text("{}", encoding="utf-8")
        _write(self.page_dir / f"{name}.html")

    def test_a_page_beside_the_configured_spec_dir_is_found(self):
        # The layout the old template got wrong for every nested page: the
        # component tree is located from config, not guessed from the output.
        self._component("codeblock")
        pages = _component_pages_on_disk(self.root / "docs" / "screens" / "html")
        self.assertIn("codeblock.component.json", pages)

    def test_a_page_without_a_component_spec_beside_it_is_not_claimed(self):
        # The project whose component specs share a directory with its SCREEN
        # specs: without this guard, `login.html` next to `login.spec.json`
        # would be offered as the page for `login.component.json`.
        _write(self.page_dir / "login.html")
        pages = _component_pages_on_disk(self.root / "docs" / "screens" / "html")
        self.assertEqual({}, pages)

    def test_the_configured_root_wins_over_the_legacy_guess(self):
        # Both candidates exist and hold a page of the same name. The config is
        # the project's own statement about where components live; the legacy
        # path is an assumption about layout. The statement wins.
        self._component("codeblock")
        out = self.root / "docs" / "screens" / "html"
        legacy = self.root / "docs" / "screens" / "components" / "html"
        _write(legacy / "codeblock.html")
        pages = _component_pages_on_disk(out)
        self.assertEqual(self.page_dir / "codeblock.html",
                         pages["codeblock.component.json"])


class ConfigLookupTests(unittest.TestCase):
    """`_component_spec_dir_from_config` against a real jui.config.json.

    ⚠️ The class above monkeypatches this function, so it could not have caught
    the defect that lived INSIDE it — the arms would have stayed green with the
    lookup returning None for every project on earth. A test that replaces the
    thing that broke is a test of everything except the thing that broke.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "components" / "json").mkdir(parents=True)
        (self.root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "component_spec_directory": "docs/components/json",
            "layouts_directory": "docs/screens/layouts",
        }), encoding="utf-8")
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_the_configured_directory_is_returned(self):
        from jsonui_doc_cli.cli import _component_spec_dir_from_config
        got = _component_spec_dir_from_config()
        self.assertIsNotNone(
            got, "returned None with a config right here — this is the shape "
                 "the original defect had, and it is silent")
        self.assertEqual((self.root / "docs" / "components" / "json").resolve(),
                         Path(got).resolve())

    def test_the_result_is_usable_for_discovery_end_to_end(self):
        # Ties the lookup to the consumer: a page under the configured tree is
        # found without anyone monkeypatching anything.
        (self.root / "docs" / "components" / "json"
         / "codeblock.component.json").write_text("{}", encoding="utf-8")
        _write(self.root / "docs" / "components" / "html" / "codeblock.html")
        pages = _component_pages_on_disk(self.root / "docs" / "screens" / "html")
        self.assertIn("codeblock.component.json", pages)


class TheLinkMustNotDependOnWhereMinusOPoints(unittest.TestCase):
    """Reported 2026-09-08 against v1.8.53/54 by a face whose generated docs
    are tracked in a PUBLIC repository.

    The fix that made these links resolve at all gave `_component_pages_on_disk`
    two candidate roots, and one of them is an ABSOLUTE path in the source
    checkout (`spec_dir.parent / "html"`). For an in-place render that root and
    the output tree coincide, so the relative href is short and right. For a
    render anywhere else — a temp directory, a build area, the gate that
    renders and diffs against the tracked pages — only that root resolves, and
    `os.path.relpath` turns it into a chain that climbs to the filesystem root
    and back down through the user's home:

        href="../../../../../../../Users/<name>/…/components/html/topbar.html"

    Two consequences, and the second is why this is not cosmetic:
      1 a gate that renders to a temp directory can NEVER match the tracked
        pages, because the href depends on where `-o` happened to point;
      2 the OS username and the source tree layout are WRITTEN INTO an
        artifact the consumer commits.

    ⚠️ The depth arithmetic was never wrong. Only the base point was.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "docs" / "components" / "json").mkdir(parents=True)
        (self.root / "docs" / "components" / "json"
         / "topbar.component.json").write_text("{}", encoding="utf-8")
        _write(self.root / "docs" / "components" / "html" / "topbar.html")
        (self.root / "jui.config.json").write_text(json.dumps({
            "spec_directory": "docs/screens/json",
            "component_spec_directory": "docs/components/json",
        }), encoding="utf-8")
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self._elsewhere = tempfile.TemporaryDirectory()
        self.elsewhere = Path(self._elsewhere.name).resolve()

    def tearDown(self):
        os.chdir(self._cwd)
        self._elsewhere.cleanup()
        self._tmp.cleanup()

    def test_the_in_place_render_still_links(self):
        """The control. The fix must not silence the case that WORKS —
        deleting the source root entirely would pass every arm below."""
        out = self.root / "docs" / "screens" / "html"
        pages = _component_pages_on_disk(out)
        self.assertIn("topbar.component.json", pages)
        href = _component_links_for_page(pages, out)["topbar.component.json"]
        self.assertEqual(os.path.join("..", "..", "components", "html",
                                      "topbar.html"), href)

    def test_a_render_outside_the_source_tree_emits_no_source_path(self):
        """The defect. Rendering elsewhere must not reach back into the
        checkout — a link out of the generated site is never right."""
        out = self.elsewhere / "html"
        out.mkdir(parents=True)
        pages = _component_pages_on_disk(out)
        links = _component_links_for_page(pages, out)
        href = links.get("topbar.component.json")
        self.assertIsNone(
            href,
            f"rendering to {out} produced {href!r} — a component page from the "
            f"source checkout. With no page inside the output tree the emitter "
            f"must render text, not a path that leaves the site.")

    def test_the_leak_shape_itself_is_asserted(self):
        """Named separately from the arm above because THIS is what the
        consumer reported: not "the link is wrong" but "my source tree's
        absolute path is in a file I commit to a public repository". An
        implementation that returned some other wrong-but-relative href would
        satisfy nobody while passing a laxer test."""
        out = self.elsewhere / "x" / "y" / "z" / "html"
        out.mkdir(parents=True)
        links = _component_links_for_page(_component_pages_on_disk(out), out)
        for name, href in links.items():
            resolved = (out / href).resolve()
            self.assertTrue(
                str(resolved).startswith(str(self.elsewhere)),
                f"{name} -> {href!r} resolves to {resolved}, outside the "
                f"output tree and inside the source checkout")

    def test_the_output_in_source_tree_predicate_is_not_vacuous(self):
        """The predicate the fix turns on, driven directly.

        Without this, a fix that always returned False would pass the two
        arms above and quietly kill the in-place case — which the first arm
        catches, but only for one layout. This says the predicate discriminates.
        """
        from jsonui_doc_cli.cli import _output_is_in_the_source_tree
        spec_dir = self.root / "docs" / "components" / "json"
        self.assertTrue(_output_is_in_the_source_tree(
            self.root / "docs" / "screens" / "html", spec_dir))
        self.assertFalse(_output_is_in_the_source_tree(
            self.elsewhere / "html", spec_dir))
