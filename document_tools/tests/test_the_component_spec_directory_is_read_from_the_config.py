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
    path.write_text(json.dumps({
        "type": "component", "version": "1.0",
        "metadata": {"component_id": name, "title": name, "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
    }), encoding="utf-8")


def _screen(path: Path, screen_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "screen", "version": "1.0",
        "metadata": {"screen_id": screen_id, "title": screen_id, "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
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
        assert (docs / "components" / "html" / "chart_bars.html").is_file(), out
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
