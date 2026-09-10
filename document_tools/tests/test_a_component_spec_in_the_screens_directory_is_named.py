"""Regression: two-holes-found-while-measuring-the-leaf-dirs (the library half).

A `*.component.json` filed under `<docs>/screens/json` reaches neither loop:
the screens loop globs `*.spec.json`, and the component loop reads
`<docs>/components/json` only. So the file produces no page, no link and no
line of output — and "wrote nothing" prints exactly like "there was nothing
to write", so the face cannot tell the two apart. One face was found holding
ten of them, with no `components/` directory at all.

Reported 2026-09-10 while measuring the leaf directories after v1.8.68.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc.generator import _pre_generate_spec_docs  # noqa: E402


def _spec(path: Path, screen_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "screen", "version": "1.0",
        "metadata": {"screen_id": screen_id, "title": screen_id, "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
    }), encoding="utf-8")


def _component(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "component", "version": "1.0",
        "metadata": {"component_id": name, "title": name, "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
    }), encoding="utf-8")


def test_a_component_spec_under_the_screens_json_directory_is_named(tmp_path, capsys):
    docs = tmp_path / "docs"
    _spec(docs / "screens" / "json" / "home.spec.json", "home")
    _component(docs / "screens" / "json" / "infopanel.component.json", "infopanel")
    _component(docs / "screens" / "json" / "badge.component.json", "badge")

    _pre_generate_spec_docs(docs)
    printed = capsys.readouterr().out

    assert "WARNING [doc]: 2 component spec(s) under" in printed
    assert "infopanel.component.json" in printed and "badge.component.json" in printed
    # The line has to say where they belong, or the reader cannot act on it.
    assert str(docs / "components" / "json") in printed
    # …and it must not claim to have deleted or moved anything.
    assert "Nothing is deleted by this warning" in printed

    # The premise this arm rests on: those two really did produce no page.
    # Without this the warning could be firing on files the run handled.
    assert not (docs / "screens" / "html" / "infopanel.html").exists()
    assert not (docs / "components" / "html" / "infopanel.html").exists()
    assert (docs / "screens" / "html" / "home.html").exists(), "the screen spec still generates"


def test_component_specs_in_their_own_directory_are_silent(tmp_path, capsys):
    """The control. Without it the warning could fire on every component spec
    anywhere, which would make the message noise rather than a finding."""
    docs = tmp_path / "docs"
    _spec(docs / "screens" / "json" / "home.spec.json", "home")
    _component(docs / "components" / "json" / "infopanel.component.json", "infopanel")

    _pre_generate_spec_docs(docs)
    printed = capsys.readouterr().out

    assert "component spec(s) under" not in printed
    # And the component DID produce its page — the run was not simply quiet.
    assert (docs / "components" / "html" / "infopanel.html").exists()


def test_the_screens_loop_still_ignores_the_misfiled_file(tmp_path, capsys):
    """The warning must not change what gets generated: it reports, it does
    not adopt the file. A `*.component.json` is not a screen spec."""
    docs = tmp_path / "docs"
    _component(docs / "screens" / "json" / "infopanel.component.json", "infopanel")
    _pre_generate_spec_docs(docs)
    capsys.readouterr()
    written = sorted(p.name for p in (docs / "screens" / "html").glob("*.html")) \
        if (docs / "screens" / "html").is_dir() else []
    assert written == [], "the misfiled component must not be adopted as a screen"
