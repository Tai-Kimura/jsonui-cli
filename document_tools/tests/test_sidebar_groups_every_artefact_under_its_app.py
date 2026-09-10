"""Regression: docsite-sidebar-is-not-multi-app.

The sidebar mixed two scopes. `Screen Specs` and `Components` were rendered
flat at the top AND again inside an app, because the root pass reads
``<input>/../docs`` and in a repo whose run is rooted at one app's tests that
IS that app's docs — so the flat copy carried the PROJECT's name while holding
ONE app's contents, and `docs/html/specs/` was a second copy on disk. Screen
and flow tests were never grouped at all, even though every nav entry already
carries its app in ``group``. The flow diagram was a single page built from one
app's flows and linked outside every app.

Measured on a four-app repo 2026-09-09: top-level `Screen Specs 55` and
`Components 8` were byte-for-byte the same set as the `client` app's, and the
other three apps had no diagram at all.
"""

from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonui_doc_cli.test_doc import generate_html_directory
from jsonui_doc_cli.test_doc.html.sidebar import (
    build_app_model,
    generate_index_sidebar,
)


def _flow_test(name: str) -> str:
    return json.dumps({"type": "flow", "metadata": {"name": name}, "steps": []})


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _titles(html: str) -> list[tuple[str, str]]:
    """(kind, text) for every sidebar heading, in document order."""
    out = []
    for m in re.finditer(
        r"<div class='sidebar-(title|subtitle)[^']*'[^>]*>(.*?)</div>", html, re.S
    ):
        text = " ".join(re.sub(r"<[^>]+>", "", m.group(2)).split())
        out.append((m.group(1), text))
    return out


class TestAppModel(unittest.TestCase):
    """The grouping is the fact the entries already state, not a new one."""

    def test_ungrouped_content_belongs_to_the_named_root_app(self):
        model = build_app_model(
            apps_nav={"client": {"specs": [{"name": "A", "path": "client/specs/a.html"}]}},
            flow_files=[{"name": "f", "path": "flows/f.html", "group": ""}],
            screen_files=[{"name": "s", "path": "screens/s.html", "group": ""}],
            spec_files=[], component_files=[],
            root_app="client",
        )
        self.assertEqual(list(model), ["client"])
        self.assertEqual(len(model["client"]["flows"]), 1)
        self.assertEqual(len(model["client"]["screens"]), 1)

    def test_a_group_that_names_an_app_lands_in_that_app(self):
        model = build_app_model(
            apps_nav={"client": {}, "bar": {}},
            flow_files=[
                {"name": "f1", "path": "flows/f1.html", "group": ""},
                {"name": "f2", "path": "flows/bar/f2.html", "group": "bar"},
            ],
            screen_files=[],
            root_app="client",
        )
        self.assertEqual([f["name"] for f in model["client"]["flows"]], ["f1"])
        self.assertEqual([f["name"] for f in model["bar"]["flows"]], ["f2"])

    def test_root_specs_are_dropped_when_an_app_already_owns_that_directory(self):
        # The generator skips writing them; the sidebar must not invent a
        # second entry for pages that were never written twice.
        model = build_app_model(
            apps_nav={"client": {"specs": [{"name": "A", "path": "client/specs/a.html"}]}},
            flow_files=[], screen_files=[],
            spec_files=[{"name": "DUP", "path": "specs/a.html"}],
            component_files=[{"name": "DUPC", "path": "components/c.html"}],
            root_app="client",
        )
        self.assertEqual([s["name"] for s in model["client"]["specs"]], ["A"])
        self.assertEqual(model["client"]["components"], [])

    def test_a_root_app_no_app_flag_declared_keeps_its_own_specs(self):
        model = build_app_model(
            apps_nav={},
            flow_files=[], screen_files=[],
            spec_files=[{"name": "A", "path": "specs/a.html"}],
            component_files=[{"name": "C", "path": "components/c.html"}],
            root_app="myapp",
        )
        self.assertEqual(list(model), ["myapp"])
        self.assertEqual([s["name"] for s in model["myapp"]["specs"]], ["A"])

    def test_an_app_holding_nothing_is_not_drawn(self):
        model = build_app_model(
            apps_nav={"empty": {}}, flow_files=[], screen_files=[], root_app=None)
        self.assertEqual(model, {})


class TestSidebarShape(unittest.TestCase):

    def _render(self, **kw):
        base = dict(
            title="Proj",
            flow_files=[{"name": "f1", "path": "flows/f1.html", "group": ""}],
            screen_files=[{"name": "s1", "path": "screens/s1.html", "group": ""}],
            spec_files=[{"name": "RootSpec", "path": "specs/r.html"}],
            component_files=[{"name": "RootComp", "path": "components/c.html"}],
            document_files=[{"name": "Doc", "path": "docs/d.html"}],
        )
        base.update(kw)
        return "\n".join(generate_index_sidebar(**base))

    def test_apps_come_first_each_holding_what_it_owns(self):
        html = self._render(
            apps_nav={
                "client": {"specs": [{"name": "A", "path": "client/specs/a.html"}],
                           "components": [{"name": "C", "path": "client/components/c.html"}]},
                "bar": {"specs": [{"name": "B", "path": "bar/specs/b.html"}]},
            },
            root_app="client",
            app_diagrams={"client": "diagram.html", "bar": "bar/diagram.html"},
        )
        titles = _titles(html)
        self.assertEqual(
            titles,
            [
                ("title", "▼client 4"),
                ("subtitle", "▼ Screen Specs 1"),
                ("subtitle", "▼ Components 1"),
                ("subtitle", "▼ Screen Tests 1"),
                ("subtitle", "▼ Flow Tests 1"),
                ("title", "▼bar 1"),
                ("subtitle", "▼ Screen Specs 1"),
                ("title", "▼Documents 1"),
            ],
        )

    def test_no_flat_copy_survives_beside_the_app_that_owns_it(self):
        html = self._render(
            apps_nav={"client": {"specs": [{"name": "A", "path": "client/specs/a.html"}]}},
            root_app="client",
        )
        flat = [t for kind, t in _titles(html)
                if kind == "title" and ("Screen Specs" in t or "Components" in t
                                        or "Flow Tests" in t or "Screen Tests" in t)]
        self.assertEqual(flat, [], f"a flat copy is still rendered: {flat}")

    def test_a_single_app_project_gets_the_same_shape(self):
        # The shape must not change with the number of apps, or the reader
        # learns a different site each time one is added.
        html = self._render(apps_nav={}, root_app="myapp",
                            app_diagrams={"myapp": "diagram.html"})
        titles = _titles(html)
        self.assertEqual(titles[0], ("title", "▼myapp 4"))
        self.assertIn(("subtitle", "▼ Screen Specs 1"), titles)
        self.assertIn(("subtitle", "▼ Flow Tests 1"), titles)

    def test_the_diagram_is_inside_the_app_and_one_per_app(self):
        html = self._render(
            apps_nav={"client": {}, "bar": {}},
            flow_files=[{"name": "f1", "path": "flows/f1.html", "group": ""},
                        {"name": "f2", "path": "flows/bar/f2.html", "group": "bar"}],
            root_app="client",
            app_diagrams={"client": "diagram.html", "bar": "bar/diagram.html"},
        )
        self.assertEqual(
            re.findall(r"sidebar-diagram-link'><a href='([^']+)'", html),
            ["diagram.html", "bar/diagram.html"],
        )

    def test_project_wide_sections_stay_outside_the_apps(self):
        html = self._render(
            apps_nav={"client": {}}, root_app="client",
            api_doc_categories={"db": [{"name": "T", "path": "db/t.html", "subdir": ""}]},
        )
        kinds = [t for kind, t in _titles(html) if kind == "title"]
        self.assertEqual(kinds[0], "▼client 2")
        self.assertTrue(any("Documents" in k for k in kinds))
        self.assertTrue(any("Db" in k or "DB" in k for k in kinds))


class TestGeneratorRouting(unittest.TestCase):
    """What the sidebar cannot say: which directories were written."""

    def test_the_duplicate_root_pass_is_skipped_and_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "proj" / "docs"
            _write(docs / "screens" / "json" / "x.spec.json", "{}")
            _write(root / "proj" / "tests" / "flows" / "f.test.json", _flow_test("F"))
            out = root / "out"
            buf = io.StringIO()
            with redirect_stdout(buf):
                generate_html_directory(
                    root / "proj" / "tests", out, title="Proj",
                    apps=[{"name": "client", "docs_path": str(docs)}],
                )
            self.assertIn("root specs/components are client's", buf.getvalue())
            self.assertFalse((out / "specs").exists(),
                             "the root pass wrote a second copy of the specs")
            self.assertFalse((out / "components").exists())

    def test_one_diagram_is_attempted_per_app_naming_its_owner(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "tests" / "flows" / "a.test.json", _flow_test("A"))
            _write(root / "tests" / "bar" / "flows" / "b.test.json", _flow_test("B"))
            # Since 2026-09-10 the diagram is drawn from SPECS, so an owner is
            # a spec directory: the root's and the app's.
            _write(root / "docs" / "screens" / "json" / "a.spec.json",
                   json.dumps({"type": "screen_spec", "transitions": []}))
            _write(root / "docs" / "bar" / "screens" / "json" / "b.spec.json",
                   json.dumps({"type": "screen_spec", "transitions": []}))
            out = root / "out"
            written: list[Path] = []

            def fake_mermaid(spec_dir, output, title, screens_dir, layouts_dir=None, **kwargs):
                from jsonui_doc_cli.test_doc.mermaid.generator import DiagramResult
                written.append(Path(output))
                Path(output).write_text("<html></html>", encoding="utf-8")
                return DiagramResult(diagrams={"All": "diagram"}, combined="diagram")

            import jsonui_doc_cli.test_doc.generator as gen
            orig = gen.generate_mermaid_html
            gen.generate_mermaid_html = fake_mermaid
            try:
                with redirect_stdout(io.StringIO()):
                    generate_html_directory(root / "tests", out, title="Proj")
            finally:
                gen.generate_mermaid_html = orig

            rel = sorted(p.relative_to(out).as_posix() for p in written)
            self.assertEqual(rel, ["bar/diagram.html", "diagram.html"],
                             "each app must get its own diagram, not one shared page")


class TestUnitTestsBelongToTheirApp(unittest.TestCase):
    """Ruled 2026-09-09: an app's unit tests go under that app.

    The unit section was the ONLY one already carrying per-app subtitles, and
    that is exactly why it read as correct while sitting outside every app —
    it looked grouped. The pages were already written to ``<app>/unit/`` and
    every nav entry already carried its app in ``group``; the sidebar was the
    last reader still treating them as project-wide.
    """

    def test_unit_entries_land_in_the_app_their_group_names(self):
        model = build_app_model(
            apps_nav={"client": {}, "bar": {}},
            flow_files=[], screen_files=[],
            unit_files=[
                {"name": "AVM", "path": "client/unit/AVM.html", "group": "client"},
                {"name": "BVM", "path": "bar/unit/BVM.html", "group": "bar"},
            ],
            root_app="client",
        )
        self.assertEqual([u["name"] for u in model["client"]["unit"]], ["AVM"])
        self.assertEqual([u["name"] for u in model["bar"]["unit"]], ["BVM"])

    def test_an_app_holding_only_unit_tests_is_still_drawn(self):
        # `unit` must be in APP_SECTION_ORDER, or the "is this app empty?"
        # filter drops an app whose only content is unit pages.
        model = build_app_model(
            apps_nav={}, flow_files=[], screen_files=[],
            unit_files=[{"name": "U", "path": "solo/unit/U.html", "group": "solo"}],
            root_app=None,
        )
        self.assertEqual(list(model), ["solo"])

    def test_the_flat_units_section_is_gone_when_apps_are_drawn(self):
        html = "\n".join(generate_index_sidebar(
            title="Proj",
            flow_files=[], screen_files=[],
            apps_nav={"client": {}},
            root_app="client",
            unit_files=[{"name": "AVM", "path": "client/unit/AVM.html",
                         "group": "client"}],
        ))
        titles = _titles(html)
        flat = [x for k, x in titles if k == "title" and "Unit Tests" in x]
        self.assertEqual(flat, [], f"a flat Unit Tests copy survives: {flat}")
        self.assertIn(("subtitle", "\u25bc Unit Tests 1"), titles)

    def test_a_project_with_no_apps_keeps_the_flat_units_section(self):
        # Nothing to nest into: dropping it would lose the links entirely.
        html = "\n".join(generate_index_sidebar(
            title="Proj", flow_files=[], screen_files=[],
            unit_files=[{"name": "AVM", "path": "unit/AVM.html"}],
        ))
        self.assertTrue(
            any(k == "title" and "Unit Tests" in x for k, x in _titles(html)),
            "with no app to hold them the flat section must remain",
        )


class TestWritesOutsideOutputNameTheirOwner(unittest.TestCase):
    """Reported 2026-09-09: one lane's run rewrote ten files in another's tree.

    `generate html` regenerates per-spec html/md IN THE SOURCE TREE, for the
    root scope and for every ``--app``. The help says so and the end-of-run
    notice lists the directories. Neither is a message to the OWNER of those
    directories, and the owning lane found the change in ``git status`` with
    no way to tell which run produced it or which version of the tools wrote
    it — a version it had not accepted.

    ⚠️ The lane that reported it first read the help and confirmed the paths
    were named. The gap is not the warning's address; it is that a tracked
    path costs a review or a silently committed artifact, and an ignored one
    costs a regenerate. Only the notice can tell those apart.
    """

    def test_tracked_absent_and_unknown_are_three_different_answers(self):
        from jsonui_doc_cli.test_doc.generator import _git_tracked_file_count
        repo = Path(__file__).resolve().parents[2]
        self.assertGreater(_git_tracked_file_count(repo / "document_tools"), 0)
        # A directory outside any repository cannot be answered, and that is
        # NOT the same as "nothing there is tracked": folding them together
        # reports a clean result on every machine without git.
        with TemporaryDirectory() as tmp:
            self.assertEqual(_git_tracked_file_count(Path(tmp)), -1)

    def test_a_tracked_outside_write_is_called_out_by_owner_not_just_listed(self):
        import jsonui_doc_cli.test_doc.generator as gen
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            out.mkdir()
            elsewhere = Path(tmp) / "other-lane" / "docs"
            elsewhere.mkdir(parents=True)
            orig_written = set(gen._written_outside_output)
            orig_count = gen._git_tracked_file_count
            gen._written_outside_output.add(elsewhere)
            gen._git_tracked_file_count = lambda d: 10
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    gen._report_writes_outside_output(out)
            finally:
                gen._git_tracked_file_count = orig_count
                gen._written_outside_output.clear()
                gen._written_outside_output.update(orig_written)
            text = buf.getvalue()
            self.assertIn("GIT-TRACKED", text)
            self.assertIn("Tell the lane that owns them", text)
            self.assertIn(str(elsewhere), text)


if __name__ == "__main__":
    unittest.main()
