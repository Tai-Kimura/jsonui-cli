"""The site generator reads `component_spec_directory`, and says "no page"
only about pages the run did not write.

Reported 2026-09-11 from a downstream admin face that keeps its component
specs beside its screen specs and says so in `jui.config.json`
(`"component_spec_directory": "docs/screens/json"`). `doc_init_component`
wrote the file there; the site generator, with the directory spelled as a
literal in four places, warned that the file would "produce no page" — and
then wrote its page in the same run, because the site pass walks the docs
tree. A false warning and two spellings of one fact.

Now `_component_json_dir_for(docs_base)` is the one resolver (config, else
the tool's layout) for all four sites, the pre-generation warning says only
what that pass knows (it wrote no page), and the end of the run derives
"produced no page" from the pages written.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))
sys.path.insert(0, str(REPO / "jui_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _component(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pascal = "".join(part.capitalize() for part in name.split("_"))
    path.write_text(json.dumps({
        "type": "component_spec", "version": "1.0",
        "metadata": {"name": pascal, "displayName": pascal, "description": "d"},
        "structure": {"components": [{"type": "Label", "id": "t", "description": "d"}],
                      "layout": {"root": "View", "children": [{"id": "t"}]}},
    }), encoding="utf-8")


def _screen(path: Path, screen_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"name": screen_id, "displayName": screen_id, "description": "d",
                     "layoutFile": screen_id},
        "structure": {"components": [{"type": "Label", "id": "t", "description": "d"}],
                      "layout": {"root": "View", "children": [{"id": "t"}]}},
    }), encoding="utf-8")


def _pre(docs: Path) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        gen._pre_generate_spec_docs(docs)
    return buf.getvalue()


class TestOneResolver:
    def test_the_config_key_wins(self, tmp_path):
        (tmp_path / "jui.config.json").write_text(json.dumps(
            {"component_spec_directory": "docs/screens/json"}), encoding="utf-8")
        docs = tmp_path / "docs"
        docs.mkdir()
        assert gen._component_json_dir_for(docs).resolve() == (docs / "screens" / "json").resolve()

    def test_without_a_config_the_tools_layout_stands(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        assert gen._component_json_dir_for(docs) == docs / "components" / "json"

    def test_no_site_of_the_generator_spells_the_directory_itself(self):
        src = (REPO / "document_tools" / "jsonui_doc_cli" / "test_doc"
               / "generator.py").read_text(encoding="utf-8")
        body = src.split("def _component_json_dir_for", 1)[1]
        # The resolver's own fallback is the one remaining literal.
        assert body.count('"components" / "json"') == 1, (
            "a second spelling of the component spec directory is back")


class TestTheFaceThatKeepsComponentsBesideScreens:
    def test_a_configured_directory_is_not_misfiled_and_gets_its_page(self, tmp_path):
        (tmp_path / "jui.config.json").write_text(json.dumps(
            {"component_spec_directory": "docs/screens/json"}), encoding="utf-8")
        docs = tmp_path / "docs"
        _screen(docs / "screens" / "json" / "admin_dashboard.spec.json", "admin_dashboard")
        _component(docs / "screens" / "json" / "chart_bars.component.json", "chart_bars")
        out = _pre(docs)
        assert "component spec(s) under" not in out, out
        assert "produce no page" not in out and "produced no page" not in out
        # (a): the page sits beside the spec, like screens — where the
        # single-file `generate component` already wrote on that face.
        assert (docs / "screens" / "html" / "chart_bars.html").is_file(), out
        assert (docs / "screens" / "md" / "chart_bars.md").is_file(), out
        assert not (docs / "components").exists(), "the tool's default layout was created beside the configured one"
        assert not gen._component_specs_outside_dir

    def test_without_the_config_the_same_tree_is_named_and_the_pass_says_what_it_did(self, tmp_path):
        docs = tmp_path / "docs"
        _screen(docs / "screens" / "json" / "home.spec.json", "home")
        _component(docs / "screens" / "json" / "chart_bars.component.json", "chart_bars")
        out = _pre(docs)
        assert "WARNING [doc]: 1 component spec(s) under" in out
        assert "so it wrote no page for them" in out
        # The claim the ticket caught is no longer made at this point.
        assert "produce no page" not in out
        assert list(gen._component_specs_outside_dir) == [
            (docs / "screens" / "json" / "chart_bars.component.json").resolve()]


class TestTheDefaultLayoutStillWritesUnderComponents:
    def test_without_a_config_component_pages_go_to_components_html(self, tmp_path):
        docs = tmp_path / "docs"
        _component(docs / "components" / "json" / "badge.component.json", "badge")
        _pre(docs)
        assert (docs / "components" / "html" / "badge.html").is_file()


class TestTheRootIsNotPreGeneratedTwice:
    def test_an_app_naming_the_root_docs_dir_generates_each_page_once(self, tmp_path):
        """`--app x:<root docs>`: the root pass and the app pass read the same
        directory; the root pass now steps aside. One `Generated:` line per
        page, and the page count is unchanged (pages are a set either way)."""
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "s0.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios",
            "source": {"layout": "s0"},
            "metadata": {"name": "s0 test", "description": "d"},
            "cases": [{"name": "c", "description": "c",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        docs = tmp_path / "docs"
        _component(docs / "components" / "json" / "badge.component.json", "badge")
        _screen(docs / "screens" / "json" / "home.spec.json", "home")
        buf = io.StringIO()
        with redirect_stdout(buf):
            gen.generate_html_directory(
                tests, tmp_path / "out", "T",
                apps=[{"name": "root", "docs_path": str(docs)}],
                project_root=tmp_path)
        out = buf.getvalue()
        badge = [l for l in out.splitlines() if "Generated:" in l and "badge.html" in l]
        assert len(badge) == 1, "\n".join(badge) or out
        # The root pass's banner is absent (it stepped aside); the app pass
        # processed the component exactly once.
        assert out.count("Pre-generating specification documentation...") == 0, out
        assert out.count("OK: badge.component.json") == 1, out

    def test_the_reported_shape_no_app_components_beside_screens_one_generated_line(self, tmp_path):
        """The face's own repro: `cd admin && jsonui-doc generate html tests -o
        docs/html`, no --app, `component_spec_directory: docs/screens/json`,
        one component spec — `Generated: …/components/chart_bars.html` twice.
        The search dirs reached the file through the docs base and through
        screens/json (twice: once as the spec dir, once as the component dir)."""
        (tmp_path / "jui.config.json").write_text(json.dumps(
            {"component_spec_directory": "docs/screens/json"}), encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "s0.test.json").write_text(json.dumps({
            "type": "screen", "platform": "ios", "source": {"layout": "s0"},
            "metadata": {"name": "s0 test", "description": "d"},
            "cases": [{"name": "c", "description": "c",
                       "steps": [{"action": "tap", "id": "x"}]}],
        }), encoding="utf-8")
        docs = tmp_path / "docs"
        _screen(docs / "screens" / "json" / "admin_dashboard.spec.json", "admin_dashboard")
        _component(docs / "screens" / "json" / "chart_bars.component.json", "chart_bars")
        buf = io.StringIO()
        with redirect_stdout(buf):
            gen.generate_html_directory(tests, docs / "html", "T", project_root=tmp_path)
        out = buf.getvalue()
        lines = [l for l in out.splitlines() if "Generated:" in l and "chart_bars.html" in l]
        assert len(lines) == 1, "\n".join(lines) or out


class TestTheEndOfRunDerivesNoPageFromWhatWasWritten:
    def _outside(self, tmp_path) -> Path:
        f = (tmp_path / "docs" / "screens" / "json" / "chart_bars.component.json")
        f.parent.mkdir(parents=True)
        f.write_text("{}", encoding="utf-8")
        gen._component_specs_outside_dir[f.resolve()] = tmp_path / "docs" / "components" / "json"
        return f

    def _report(self) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            gen._report_component_specs_outside_dir()
        return buf.getvalue()

    def test_a_page_the_site_pass_wrote_turns_the_warning_into_a_note(self, tmp_path):
        self._outside(tmp_path)
        gen.note_page_generated(tmp_path / "out" / "admin" / "components" / "chart_bars.html")
        out = self._report()
        assert "produced no page" not in out, out
        assert "got a page from the site pass anyway" in out

    def test_no_page_anywhere_is_the_warning(self, tmp_path):
        self._outside(tmp_path)
        gen.note_page_generated(tmp_path / "out" / "screens" / "chart_bars.html")  # not a component page
        out = self._report()
        assert "WARNING [doc]: 1 component spec(s) outside the component spec directory produced no page this run" in out
        assert "component specs are read from" in out

    def test_nothing_outside_prints_nothing(self):
        assert self._report() == ""
