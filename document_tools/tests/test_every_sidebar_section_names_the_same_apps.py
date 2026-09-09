"""Acceptance arms: docsite-sidebar-screens-and-flows-are-not-per-app.

`generate_index_sidebar` groups every artefact under its app. The three
PAGE-level sidebars do not agree with it:

    generate_spec_sidebar    per-app  (test_spec_sidebar_opens_the_page_s_own_app)
    generate_screen_sidebar  NOT      <- flat `Screen Tests`
    generate_flow_sidebar    NOT      <- flat `Flow Tests`

⚠️ THE SECTIONS DISAGREE INSIDE ONE RENDERED PAGE. `_render_tests_sidebar_section`
already nests by `group`, and `units` entries carry one, so a unit page shows
`Unit Tests` split per app while `Screen Tests` and `Flow Tests` next to it are
one flat list of another app's pages. The renderer is not the defect; the nav
entries for screens/flows are.

🚨 WHY BOTH SECTIONS. Measured on the reporting face: flows 61 and screens 15
were BOTH flat. Fixing `screens` alone reproduces the shape this ticket is
about — one of a set of sibling call sites updated, counted as "done".
See `feedback: count arms per call site, not per rule`.

🔻 THE ASSERTION IS A SET, NOT A COUNT. "three sidebars, one is per-app" is a
count; a count is satisfied by making any two agree. The property is that the
set of apps named by each section is the SAME set, derived from what the run
declares (`--app`), not from how many sections happen to render subsections.
"""

from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.cli import _resolve_test_roots
from jsonui_doc_cli.test_doc import generate_html_directory


def _spec(screen: str, target: str) -> dict:
    return {
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screenName": screen, "name": "S", "displayName": "S",
                     "description": "d."},
        "structure": {"components": [{"type": "View", "id": "root", "description": "r"}],
                      "layout": {"root": "root", "children": []}},
        "unitContracts": {"target": target,
                          "cases": [{"name": "c1", "intent": "i", "platforms": ["ios"]}]},
    }


def _test_json(kind: str, name: str) -> str:
    if kind == "flow":
        return json.dumps({"type": "flow", "metadata": {"name": name}, "steps": []})
    return json.dumps({
        "type": "screen", "platform": "ios", "source": {"layout": name},
        "metadata": {"name": name, "description": "d"},
        "cases": [{"name": "o", "description": "o",
                   "steps": [{"action": "tap", "id": "x"}]}]})


def _section_apps(html: str, section_id: str) -> set[str]:
    """The app names a section renders as subsections.

    🔻 Read off the RENDERED page, not off the nav dict. A nav entry carrying
    `group` proves nothing about whether the section used it — that is the
    difference between the data being right and the page being right.
    """
    m = re.search(
        rf"id='{section_id}-list'>(.*?)\n      </div>", html, re.S)
    if not m:
        return set()
    out = set()
    for raw in re.findall(r"<div class='sidebar-subtitle[^']*'[^>]*>(.*?)</div>",
                          m.group(1), re.S):
        # ⚠️ The arrow and the count live in spans INSIDE the subtitle. Stripping
        # tags alone leaves "\u25bc Bar 1", which is not the app's name — the
        # positive control below is what caught that, by asserting the one
        # section that already works.
        raw = re.sub(r"<span class='(?:arrow|count)'>.*?</span>", "", raw, flags=re.S)
        out.add(" ".join(re.sub(r"<[^>]+>", "", raw).split()))
    return out


class _Run(unittest.TestCase):
    APPS = ("bar", "client")

    def build(self, apps=APPS, per_app_test_dirs=False, declare=True):
        """A run that DECLARES apps. Tests are flat unless asked otherwise.

        ⚠️ Flat is the reported shape: `_test_group` reads the app off the test
        file's path, so a repo that keeps all tests in one directory gives
        every screen/flow `group == ''` while `units` still gets its app from
        the declaration. The two sources disagree, and only one of them is the
        thing the run was told.
        """
        root = Path(TemporaryDirectory().__enter__()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        app_args, roots = [], []
        for app in apps:
            base = root / app
            (base / "docs" / "screens" / "json").mkdir(parents=True)
            (base / "ios" / "Tests").mkdir(parents=True)
            (base / "jui.config.json").write_text(json.dumps({
                "spec_directory": "docs/screens/json",
                "test": {"src": "tests"},
                "platforms": {"ios": {"root": "ios", "unitTestsDir": "Tests",
                                      "testModule": "App"}}}), encoding="utf-8")
            (base / "docs" / "screens" / "json" / "s.spec.json").write_text(
                json.dumps(_spec(f"s_{app}", f"{app.title()}Handler")), encoding="utf-8")
            (base / "ios" / "Tests" / f"{app.title()}HandlerContractTests.swift").write_text(
                "import XCTest\n@testable import App\n"
                f"final class {app.title()}HandlerContractTests: XCTestCase "
                "{ func test_c1() throws {} }\n", encoding="utf-8")
            app_args.append({"name": app, "docs_path": base / "docs"})
            roots.append({"app": app, "root": base})
            # 🚨 THE APP'S TESTS LIVE IN THE DIRECTORY ITS OWN CONFIG NAMES.
            # An earlier version of this fixture put every app's tests in the
            # run's shared `tests/` directory, so every app's tests were
            # scanned no matter what — which made the fixture unable to show
            # the reported defect at all (two apps' tests had NO PAGE). The
            # arms were red for a different reason than the site was wrong.
            # `test.src` is read from the config, not guessed from `<app>/tests`.
            sub = (base / "tests" / app) if per_app_test_dirs else (base / "tests")
            sub.mkdir(parents=True, exist_ok=True)
            (sub / f"{app}_s.test.json").write_text(_test_json("screen", f"{app}_s"),
                                                    encoding="utf-8")
            (sub / f"{app}_f.test.json").write_text(_test_json("flow", f"{app}_f"),
                                                    encoding="utf-8")
        # The run's own input directory. Its tests belong to no declared app,
        # so under the ruling they stay ungrouped — that is not a gap.
        own = root / "tests"
        own.mkdir(parents=True, exist_ok=True)
        # Both kinds, so the flat arm can assert on a flows section that
        # EXISTS. With only a screen test there is no flows section, and
        # "no subsections" would have been true of an absent section.
        own.joinpath("run_own.test.json").write_text(
            _test_json("screen", "run_own"), encoding="utf-8")
        own.joinpath("run_own_f.test.json").write_text(
            _test_json("flow", "run_own_f"), encoding="utf-8")
        out = root / "out"
        out.mkdir()
        # 🔻 Resolved the way the CLI resolves it, from each app's `test.src`,
        # rather than hand-built here. A hand-built list would pass even if
        # `_resolve_test_roots` stopped reading the config — the arm would be
        # testing the fixture's guess instead of the shipped resolution.
        test_roots = _resolve_test_roots(app_args) if declare else None
        with redirect_stdout(io.StringIO()):
            generate_html_directory(
                root / "tests", out, "T",
                # 🔻 `declare=False` is the UNDECLARED run: the same files on
                # disk, with nothing telling the run they belong to apps.
                apps=app_args if declare else None,
                unit_roots=roots if declare else None,
                test_roots=test_roots)
        return out

    def any_test_page(self, out: Path) -> str:
        """A screen-test page. An undeclared run produces no unit pages."""
        pages = [p for p in sorted(out.rglob("*.html"))
                 if p.name != "index.html" and "/specs/" not in p.as_posix()
                 and "/components/" not in p.as_posix()]
        self.assertTrue(pages, "the run must produce a test page to read")
        return pages[0].read_text(encoding="utf-8")

    def unit_page(self, out: Path) -> str:
        pages = sorted(out.rglob("unit/**/*.html"))
        self.assertTrue(pages, "the run must produce a unit page to read")
        return pages[0].read_text(encoding="utf-8")


class TheSectionsMustNameTheSameApps(_Run):

    def test_the_instrument_can_see_subsections_at_all(self):
        """🔻 Positive control, and it is the section that already works.

        Without this, a red arm below is indistinguishable from a reader that
        cannot find subsections in this markup at all.
        """
        html = self.unit_page(self.build())
        self.assertEqual(_section_apps(html, "units"), {"Bar", "Client"})

    def test_screen_tests_names_the_same_apps_as_unit_tests(self):
        html = self.unit_page(self.build())
        self.assertEqual(_section_apps(html, "screens"),
                         _section_apps(html, "units"),
                         "the screens section must name the run's apps, not one app's set")

    def test_flow_tests_names_the_same_apps_as_unit_tests(self):
        """⚠️ Kept separate from screens on purpose: fixing one and shipping is
        the shape being pinned, and one assertion covering both would go green
        the moment either half landed."""
        html = self.unit_page(self.build())
        self.assertEqual(_section_apps(html, "flows"),
                         _section_apps(html, "units"),
                         "the flows section must name the run's apps too")

    def test_a_run_that_declares_no_apps_stays_flat(self):
        """🔻 Negative control, REWRITTEN 2026-09-09 by the ruling below.

        ⚠️ IT USED TO SAY "a single-APP run stays flat" and passed. That arm
        encoded rule B (decide by how many apps there are). The ruling picked
        rule C — decide by whether the run DECLARES apps — so the old arm was
        asserting the losing rule and had to be inverted rather than deleted.

        Ruling 2026-09-09 (user, via the release train). Why C over B:
          * one rule for all three sections; no "how many apps" special case
          * `group` comes from the DECLARATION (`--app` / unit_roots), never
            from where a test file happens to sit — which is the same defect
            the sibling arms below pin
          * it makes today's `units` behaviour correct as written, and makes
            `_render_tests_sidebar_section`'s docstring true for the runs it
            was actually describing: the undeclared ones

        🚫 Do not "restore" the old expectation. A single declared app nests;
        that is the ruling, and this arm is what stops it being un-decided by
        accident. See `feedback: invert the spec that encoded the removed
        behaviour` — deleting it would let the old shape return in silence.
        """
        html = self.any_test_page(self.build(apps=("client",), declare=False))
        for section in ("screens", "flows"):
            # 🚨 GUARD FIRST. "no subsections" is also what an ABSENT section
            # returns, so without this the arm goes green the day the fixture
            # stops rendering these sections at all — for the opposite reason
            # to the one it is testing. Measured when written: 1 link each.
            self.assertIn(f"id='{section}-list'>", html,
                          f"the {section} section must exist to be called flat")
            self.assertRegex(html, rf"(?s)id='{section}-list'>.*?<a href",
                             f"the {section} section must hold entries")
            self.assertEqual(_section_apps(html, section), set(),
                             f"{section} must stay flat when the run declares no apps")

    def test_one_declared_app_still_nests(self):
        """A declared app is an app, even when it is the only one.

        ⚠️ Filed 2026-09-09 as "measured, not decided": `units` nested here
        while `screens`/`flows` did not, and the two rules shipped in one
        sidebar. The ruling made THIS the intended behaviour for all three
        sections, so what was a record of a disagreement is now the property.

        🔻 It still costs something, and the cost is why it needed a ruling
        rather than a patch: a face that declares exactly one app gains a level
        of nesting on `screens`/`flows` that it did not have. There was no
        option that changed nothing.
        """
        html = self.unit_page(self.build(apps=("client",)))
        self.assertEqual(_section_apps(html, "units"), {"Client"})

    def test_the_two_single_app_shapes_disagree_on_purpose(self):
        """🚨 The pair is the point: same files, different declaration.

        Without this, `test_a_run_that_declares_no_apps_stays_flat` and
        `test_one_declared_app_still_nests` read as two unrelated facts, and a
        later change could satisfy both by keying on something else entirely
        (the app count, a path, a file name). Asserting they differ pins that
        the DECLARATION is what moved the output.
        """
        declared = self.unit_page(self.build(apps=("client",)))
        undeclared = self.any_test_page(self.build(apps=("client",), declare=False))
        self.assertNotEqual(_section_apps(declared, "units"),
                            _section_apps(undeclared, "screens"),
                            "declaring an app must change the rendering")


class WhatTheUndeclaredRunCannotDo(_Run):
    """🔻 A CONSTRAINT, not an unimplemented feature. Ruling 2026-09-09.

    The rule is "use the declaration if there is one, otherwise the path".
    That leaves one shape that cannot be made to agree, and it is not a gap
    waiting on someone:

        screens / flows   have a path, so an undeclared run groups them by it
        units             come from each app's CONFIG. There is no path to
                          fall back to, so an undeclared run cannot group them

    🚫 Do not file this as a defect and do not write "until this is fixed" in
    these arms. The train returned it to the user as a constraint. What makes
    it safe is that it is WRITTEN DOWN HERE — an unnamed asymmetry gets
    re-reported by the next reader as a new bug, which happened three times in
    one day on this ticket alone.
    """

    def test_an_undeclared_run_groups_screens_by_path_but_has_no_units(self):
        out = self.build(per_app_test_dirs=True, declare=False)
        html = self.any_test_page(out)
        self.assertEqual(_section_apps(html, "screens"), set(),
                         "the run's own tests sit in one directory, so no path groups")
        self.assertNotIn("id='units-list'>", html,
                         "units cannot appear without a declaration — the constraint")


class TheGroupingMustNotDependOnWhereTestsSit(_Run):
    """🚨 The app is what the run DECLARES, not where a file happens to live.

    `_test_group` reads the app off the test path. A repo that keeps its tests
    in per-app subdirectories therefore looks correct today, and the same repo
    with a flat tests/ directory does not — the defect is invisible to whoever
    has the first layout. The declaration is the same in both.
    """

    def test_both_layouts_name_the_same_apps(self):
        flat = self.unit_page(self.build(per_app_test_dirs=False))
        nested = self.unit_page(self.build(per_app_test_dirs=True))
        self.assertEqual(_section_apps(flat, "screens"),
                         _section_apps(nested, "screens"),
                         "a flat tests/ dir must not change which apps are named")


if __name__ == "__main__":
    unittest.main()
