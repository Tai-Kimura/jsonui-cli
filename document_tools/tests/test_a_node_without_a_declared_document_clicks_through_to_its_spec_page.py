"""A drawn node with no ``source.document`` clicks through to its spec page.

Filed 2026-09-10 (docs/bugs/doc-diagram-click-targets-vanish-when-no-test-
declares-a-document): the click target of a diagram node came only from a
screen test's ``source.document``, with no ``else``. A face that declares
none has no clickable node at all, and the faces that DID declare them
pointed at the Documents pages a ruling deleted the same day — so the link
went to a strict subset of the spec page it could have gone to.

The fallback is NOT unconditional. Emitting a href the site never wrote is
the same defect pointed the other way, so a node gets one only when the
writer actually wrote a page for it.

⚠️ The href is the page the WRITER produced, never ``<screen_id>.html``.
The two spellings agree in today's corpus (measured 2026-09-10: 0 of 96
specs across 3 faces differ) and that agreement is a coincidence of three
separate things:

    a  the page keeps the spec file's SUBDIRECTORY, the node id does not
    b  the page name is the spec file's stem, the node id is a screen id
    c  the node id is the CANONICAL id after the collision collapse, whose
       ranking is layout > app-owned > spec stem — so a layout spelled
       ``forgot_password`` wins over a spec named ``forgotpassword.json``
       and the page is ``forgotpassword.html``

``TheHrefIsTheWritersSpelling`` holds (c), the one that needs no unusual
tree to happen. The generator and the writer therefore share ONE expression
(``spec_page_name``) rather than each spelling the rule out.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonui_doc_cli.test_doc.generator import _generate_spec_pages
from jsonui_doc_cli.test_doc.mermaid.generator import build_diagram
from jsonui_doc_cli.test_doc.mermaid.spec_graph import spec_page_name, spec_page_path


class _Face:
    """The shape the report describes: specs, layouts, screen tests."""

    def __init__(self, root: Path):
        self.root = root
        self.specs = root / "docs" / "screens" / "json"
        self.layouts = root / "docs" / "screens" / "layouts"
        self.screens = root / "tests" / "screens"
        for d in (self.specs, self.layouts, self.screens):
            d.mkdir(parents=True, exist_ok=True)

    def spec(self, name: str, destinations: list[str], *, layout: str | None = None) -> None:
        (self.layouts / f"{layout or name}.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8")
        (self.specs / f"{name}.spec.json").write_text(json.dumps({
            "type": "screen_spec", "metadata": {},
            "transitions": [{"trigger": "t", "condition": "c", "destination": d}
                            for d in destinations],
        }, ensure_ascii=False), encoding="utf-8")

    def screen_test(self, name: str, layout: str, document: str | None = None) -> None:
        source = {"layout": f"Layouts/{layout}.json"}
        if document:
            source["document"] = document
        (self.screens / f"{name}.test.json").write_text(json.dumps(
            {"type": "screen", "metadata": {"name": name}, "source": source, "cases": []}),
            encoding="utf-8")

    def valid_spec(self, name: str, destinations: list[str], *, file_name: str | None = None) -> None:
        """A spec the validator accepts, so the writer really writes its page."""
        (self.layouts / f"{name}.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8")
        (self.specs / f"{file_name or name}.spec.json").write_text(json.dumps({
            "type": "screen_spec", "version": "1.0",
            "metadata": {"name": name.title().replace("_", ""), "displayName": name,
                         "description": "d"},
            "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                          "layout": {"root": "root", "children": []}},
            "transitions": [{"trigger": "t", "condition": "c", "destination": d}
                            for d in destinations],
        }), encoding="utf-8")

    def write_the_site(self, out: Path) -> None:
        _generate_spec_pages([self.specs], out)

    def nested_spec(self, subdir: str, name: str, destinations: list[str]) -> None:
        (self.layouts / f"{name}.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8")
        d = self.specs / subdir
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.spec.json").write_text(json.dumps({
            "type": "screen_spec", "metadata": {},
            "transitions": [{"trigger": "t", "condition": "c", "destination": x}
                            for x in destinations],
        }), encoding="utf-8")

    def pages_the_writer_would_write(self) -> set[str]:
        """Every ``specs/...`` href the site generator produces for this tree.

        Built the way the WRITER walks (``rglob``), not the way the diagram
        walks (``glob``), so the two can disagree and the arm still sees it.
        """
        return {f"specs/{spec_page_path(p, self.specs)}"
                for p in self.specs.rglob("*.spec.json")}

    def build(self, **kwargs):
        return build_diagram(self.specs, screens_dir=self.screens,
                             layouts_dir=self.layouts, **kwargs)

    def clicks(self, text: str) -> dict[str, str]:
        """node id -> href, read off the emitted mermaid."""
        out = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("click "):
                _kw, node, rest = line.split(" ", 2)
                out[node] = rest.split('"')[1]
        return out


class _Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.face = _Face(Path(self.tmp.name))


class ANodeWithNoDeclarationReachesItsSpecPage(_Case):
    def test_the_fallback_names_the_page_under_specs(self):
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        clicks = self.face.clicks(self.face.build().combined)
        self.assertEqual(clicks.get("mypage"), "specs/mypage.html")
        self.assertEqual(clicks.get("login"), "specs/login.html")

    def test_a_declared_document_still_wins(self):
        # The declaration is the author's choice; the fallback only fills a hole.
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        self.face.screen_test("login_smoke", "login", "docs/screens/html/login.html")
        clicks = self.face.clicks(self.face.build().combined)
        self.assertEqual(clicks.get("login"), "docs/screens/html/login.html")
        self.assertEqual(clicks.get("mypage"), "specs/mypage.html")

    def test_the_group_tabs_get_the_same_fallback(self):
        # Two emit sites, one rule. The group tabs were the site nobody read.
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        result = self.face.build()
        tabs = {k: v for k, v in result.diagrams.items() if v is not result.combined}
        self.assertTrue(tabs, "no group tab was produced, the arm would be vacuous")
        for name, text in tabs.items():
            with self.subTest(tab=name):
                clicks = self.face.clicks(text)
                self.assertTrue(clicks, f"tab {name!r} emitted no click line")
                for node, href in clicks.items():
                    self.assertEqual(href, f"specs/{node}.html")


class ANodeWithNoPageOfItsOwnGetsNoClick(_Case):
    def test_an_app_owned_screen_without_a_spec_is_left_unclickable(self):
        # The `licenses` shape: a real node (app_info --> licenses), declared
        # app-owned, so no spec and no page. A href here would 404 — the
        # defect this ticket is about, pointed the other way.
        self.face.spec("app_info", ["Licenses"])
        (self.face.root / "jui.config.json").write_text(json.dumps(
            {"test": {"appOwnedScreens": [{"id": "licenses"}]}}), encoding="utf-8")
        result = self.face.build(app_owned=["licenses"])
        clicks = self.face.clicks(result.combined)
        self.assertIn("licenses", result.combined,
                      "the specimen must DRAW the node, or the arm proves nothing")
        self.assertNotIn("licenses", clicks)
        # ...and it must not be green because nothing at all got a click.
        self.assertEqual(clicks.get("app_info"), "specs/app_info.html")


class TheHrefIsTheWritersSpelling(_Case):
    def test_the_page_name_comes_from_the_spec_file_not_the_node_id(self):
        # Collision collapse: the layout's id outranks the spec's stem, so the
        # node is `forgot_password` while the page written is
        # `forgotpassword.html`. `specs/<node id>.html` would 404.
        self.face.spec("login", ["Forgot password"])
        self.face.spec("forgotpassword", [], layout="forgot_password")
        clicks = self.face.clicks(self.face.build().combined)
        self.assertIn("forgot_password", clicks,
                      f"the collapse did not happen, specimen is wrong: {clicks}")
        self.assertEqual(clicks["forgot_password"], "specs/forgotpassword.html")
        # ...and say out loud that the two spellings differ here, so the arm
        # cannot pass by the coincidence that holds everywhere else (measured
        # 2026-09-10: 0 of 96 specs across three faces have stem != id).
        self.assertNotEqual(clicks["forgot_password"], "specs/forgot_password.html")

    def test_a_variant_spec_keeps_its_variant_in_the_page_name(self):
        # The other axis, and the only one where `spec_screen_id` and
        # `spec_page_name` actually disagree: `home@regular.spec.json` is an
        # alternate rendering of `home` (screen_identity: variantNormalization),
        # so the NODE is `home` and the PAGE is `home@regular.html`. Naming
        # the page from the id gives `specs/home.html`, which exists only if a
        # non-variant spec happens to sit beside it — here none does.
        #
        # Measured 2026-09-10: zero variant specs in the repository and zero
        # in the three-face corpus. The axis is in the code, not in any tree,
        # which is exactly why no corpus-derived arm can see it.
        self.face.spec("login", ["Home"])
        self.face.spec("home@regular", [], layout="home")
        clicks = self.face.clicks(self.face.build().combined)
        self.assertIn("home", clicks, f"the variant drew no node: {clicks}")
        self.assertEqual(clicks["home"], "specs/home@regular.html")
        self.assertNotEqual(clicks["home"], "specs/home.html")

    def test_the_writer_and_the_diagram_share_one_expression(self):
        # Two implementations of one rule drift while both stay green.
        self.assertEqual(spec_page_name(Path("a/b/login.spec.json")), "login.html")
        self.assertEqual(spec_page_name(Path("a/b/login.json")), "login.html")


class NoHrefPointsAtAPageTheWriterNeverWrote(_Case):
    """The invariant, held over a tree the two walks disagree about.

    ``iter_spec_files`` globs, the writer rglobs, so a nested spec has a page
    and no node today. Widening the walk is the obvious repair and would give
    those nodes a click — the arm must pass either way, so it asserts the
    property (no href outside the written set) instead of a node count.
    """

    def test_a_nested_spec_does_not_produce_a_href_outside_the_written_set(self):
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        self.face.nested_spec("chat", "chat_core", [])
        written = self.face.pages_the_writer_would_write()
        self.assertIn("specs/chat/chat_core.html", written,
                      "the specimen's nested spec is not nested, fixture is wrong")
        hrefs = set(self.face.clicks(self.face.build().combined).values())
        self.assertTrue(hrefs, "no click at all, the arm would be vacuous")
        self.assertEqual(hrefs - written, set(),
                         "a click points at a page the writer never wrote")

    def test_the_nested_page_keeps_its_subdirectory(self):
        # Held directly on the expression, so it stays true on the day the
        # diagram's walk widens and the node appears.
        self.assertEqual(
            spec_page_path(self.face.specs / "chat" / "chat_core.spec.json", self.face.specs),
            "chat/chat_core.html")
        self.assertEqual(
            spec_page_path(self.face.specs / "login.spec.json", self.face.specs),
            "login.html")


class EveryHrefResolvesToAFileTheRunWrote(_Case):
    """Condition 1, held against the pages a real run produced.

    The diagram is generated BEFORE the spec pages (generator.py: the mermaid
    call precedes every `_generate_spec_pages`), so it cannot look at what
    was written and cannot ask the validator without being a second
    validator. An invalid spec used to take the writer's `continue` with no
    page at all — a node, a href, and a 404. It now gets the placeholder that
    already exists for this purpose, so the set the diagram links into and
    the set the writer produces are the same set.
    """

    def test_a_spec_that_fails_validation_still_has_the_page_its_node_links_to(self):
        out = Path(self.tmp.name) / "html"
        self.face.valid_spec("login", ["Broken"])
        # valid JSON, invalid spec: the writer's `not is_valid` branch
        (self.face.layouts / "broken.json").write_text(
            json.dumps({"type": "View"}), encoding="utf-8")
        (self.face.specs / "broken.spec.json").write_text(
            json.dumps({"type": "screen_spec", "metadata": {}}), encoding="utf-8")
        self.face.write_the_site(out)
        clicks = self.face.clicks(self.face.build().combined)
        self.assertIn("broken", clicks,
                      "the invalid spec drew no node; the specimen proves nothing")
        for node, href in sorted(clicks.items()):
            with self.subTest(node=node):
                self.assertTrue((out / href).is_file(),
                                f"{node} links to {href}, which this run did not write")

    def test_the_arm_can_see_a_missing_page(self):
        # The control for the arm above: with the page removed it must fail.
        out = Path(self.tmp.name) / "html"
        self.face.valid_spec("login", ["Mypage"])
        self.face.valid_spec("mypage", [])
        self.face.write_the_site(out)
        self.assertTrue((out / "specs/mypage.html").is_file())
        (out / "specs" / "mypage.html").unlink()
        clicks = self.face.clicks(self.face.build().combined)
        missing = [h for h in clicks.values() if not (out / h).is_file()]
        self.assertEqual(missing, ["specs/mypage.html"])


class TheFallbackIsTheSameLinkOnSomeFacesAndANewOneOnOthers(_Case):
    """Two shapes, two meanings — the arm has to span both.

    Where a declaration already named the spec page, removing it changes
    nothing: the fallback lands on the same file. Where it named some other
    page, the fallback moves the link. An arm built on one shape alone cannot
    tell "the fallback works" from "nothing changed".

    ⚠️ Both shapes are constructed here, and NEITHER is a claim about a real
    face. A relay on 2026-09-10 said one face's deleted links pointed at the
    spec page itself; the face retracted it the same evening (five trees,
    five different byte counts — same spec, different renderings, one of them
    a strict subset). What the face had measured was a 1:1 of ORIGIN, read as
    identity. So on every face known today the fallback moves the link.
    """

    def test_where_the_declaration_named_the_spec_page_the_fallback_is_identical(self):
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        self.face.screen_test("login_smoke", "login", "specs/login.html")
        with_decl = self.face.clicks(self.face.build().combined)["login"]
        (self.face.screens / "login_smoke.test.json").unlink()
        without = self.face.clicks(self.face.build().combined)["login"]
        self.assertEqual(with_decl, without)
        self.assertEqual(without, "specs/login.html")

    def test_where_the_declaration_named_another_page_the_fallback_moves_the_link(self):
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        self.face.screen_test("login_smoke", "login", "docs/screens/html/login.html")
        with_decl = self.face.clicks(self.face.build().combined)["login"]
        (self.face.screens / "login_smoke.test.json").unlink()
        without = self.face.clicks(self.face.build().combined)["login"]
        self.assertNotEqual(with_decl, without)
        self.assertEqual(without, "specs/login.html")


class TheClosingLineSaysHowItCounted(_Case):
    def test_the_stats_carry_both_the_numerator_and_its_denominator(self):
        self.face.spec("login", ["Mypage"])
        self.face.spec("mypage", [])
        stats = self.face.build().stats
        self.assertEqual(stats.get("nodes"), 2)
        self.assertEqual(stats.get("click_targets"), 2)

    def test_zero_click_targets_is_reported_next_to_a_nonzero_denominator(self):
        # An empty output returns wearing the face of "no diagram at all".
        # N == 0 beside M > 0 is the shape that tells the two apart: a run
        # where the fallback goes silent must not look like a run with no
        # diagram. Every drawn node here is app-owned, so no page exists for
        # any of them and the correct answer is 0.
        (self.face.root / "jui.config.json").write_text(json.dumps(
            {"test": {"appOwnedScreens": [{"id": "a"}, {"id": "b"}]}}), encoding="utf-8")
        result = self.face.build(app_owned=["a", "b"],
                                 app_owned_transitions={"a": ["B"]})
        self.assertGreater(result.stats.get("nodes", 0), 0,
                           "no node was drawn, so M == 0 and the arm is vacuous")
        self.assertEqual(result.stats.get("click_targets"), 0)
        self.assertEqual(self.face.clicks(result.combined), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
