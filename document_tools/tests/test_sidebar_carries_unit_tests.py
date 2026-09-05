"""Every sidebar carries Unit Tests, and every page reveals its own entry.

1.8.40 generated `<app>/unit/<Target>.html`, listed the group in the index
BODY, and counted `N Unit Targets` in the summary — but no sidebar linked to
any of it. A user opened the shared site, read the nav top to bottom, and
concluded the hand-written tests had never been generated. They had. A
missing nav entry and a missing feature look identical from the outside, and
no gate saw it: the generator succeeded, `--check` passed, nothing validated
the nav.

Ruled 2026-09-05: the section belongs in every sidebar. That REVERSES the
1.8.40 decision to keep `units` out of the shared `all_tests_nav` — which
was deliberate, to avoid putting a new section on pages that never had one.
The report is what settled it: pages that never had it were pages a reader
could not navigate from.

The populations here are derived, not listed. A seventh sidebar renderer, or
a fourth script bundle, joins these arms by existing.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from jsonui_doc_cli.test_doc.html import document, markdown, sidebar, styles

UNITS = [
    {"name": "ProfileViewModel", "path": "alpha/unit/ProfileViewModel.html", "group": "alpha"},
    {"name": "SettingsViewModel", "path": "alpha/unit/SettingsViewModel.html", "group": "alpha"},
]
NAV = {
    "flows": [{"name": "F", "path": "flows/f.html", "group": ""}],
    "screens": [{"name": "S", "path": "screens/s.html", "group": ""}],
    "units": UNITS,
}


def _sidebar_renderers():
    """Every `generate_*_sidebar` in the package, found by name."""
    found = {}
    for module in (sidebar, document, markdown):
        for name, fn in vars(module).items():
            if name.startswith("generate_") and name.endswith("_sidebar"):
                found[name] = fn
    return found


def _kwargs_for(fn, nav) -> dict:
    """Whatever this renderer declares it needs, from its own signature.

    Required arguments that carry no unit data (`cases`, `steps`,
    `checkpoints`) are filled with empty lists: they are not what these arms
    are about, and hardcoding a call per renderer would mean a new renderer
    is untested until someone remembers to add it.
    """
    kwargs = {}
    # The first parameter is the heading; it is spelled `title` in some
    # renderers and `name` in others, so it is skipped by POSITION.
    for index, (name, param) in enumerate(inspect.signature(fn).parameters.items()):
        if index == 0:
            continue
        if name == "all_tests_nav":
            kwargs[name] = nav
        elif name == "flow_files":
            kwargs[name] = nav.get("flows", [])
        elif name == "screen_files":
            kwargs[name] = nav.get("screens", [])
        elif name == "unit_files":
            kwargs[name] = nav.get("units")
        elif param.default is inspect.Parameter.empty:
            kwargs[name] = []
    return kwargs


def _render(fn, nav=None) -> str:
    return "\n".join(fn("Title", **_kwargs_for(fn, NAV if nav is None else nav)))


def test_the_population_is_the_six_renderers_we_think_it_is():
    # Not to freeze the number, but so that a renderer added without a Unit
    # Tests section fails HERE with its name rather than silently widening
    # the gap the ticket describes.
    assert set(_sidebar_renderers()) == {
        "generate_screen_sidebar",
        "generate_flow_sidebar",
        "generate_spec_sidebar",
        "generate_index_sidebar",
        "generate_document_sidebar",
        "generate_markdown_sidebar",
    }


@pytest.mark.parametrize("name", sorted(_sidebar_renderers()))
def test_every_sidebar_renders_the_unit_tests_section(name):
    html = _render(_sidebar_renderers()[name])
    assert "Unit Tests" in html, f"{name} has no Unit Tests section"
    for unit in UNITS:
        assert unit["path"] in html, f"{name} does not link {unit['path']}"


@pytest.mark.parametrize("name", sorted(_sidebar_renderers()))
def test_no_unit_section_when_nothing_declares_one(name):
    """(c) An app with no unitContracts gets no subgroup — and a project
    with none gets no section at all, matching the existing rule that a
    thing which did not run does not get an empty column."""
    html = _render(_sidebar_renderers()[name],
                   nav={"flows": NAV["flows"], "screens": NAV["screens"]})
    assert "Unit Tests" not in html


def test_only_apps_with_targets_get_a_subgroup():
    # Two apps declare contracts, a third does not appear in the data at
    # all — so it must not appear as an empty group.
    units = UNITS + [{"name": "T", "path": "beta/unit/T.html", "group": "beta"}]
    html = "\n".join(sidebar.generate_index_sidebar(
        "T", NAV["flows"], NAV["screens"], unit_files=units))
    assert "Alpha" in html and "Beta" in html
    assert "Gamma" not in html


def test_the_current_page_is_marked_so_the_reveal_has_something_to_find():
    html = "\n".join(sidebar.generate_screen_sidebar(
        "T", [], NAV, current_test_path="alpha/unit/SettingsViewModel.html"))
    assert "nav-link current" in html


# --- requirement 3: the reveal reaches every template -----------------

REVEAL_MARK = ".sidebar .nav-link.current"


def _script_bundles() -> dict[str, str]:
    """Every emitted script bundle that defines `toggleSection`.

    Derived from the source: a template that gives the sidebar collapsible
    groups and no reveal is exactly the spec-page defect this fixes, so the
    two facts are checked together rather than by a list of file names.
    """
    root = Path(styles.__file__).resolve().parents[3] / "jsonui_doc_cli"
    bundles = {}
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"function toggleSection", text):
            bundles[str(path.relative_to(root))] = text
    return bundles


def test_every_template_that_collapses_the_sidebar_also_reveals_the_current_entry():
    missing = []
    for rel, text in _script_bundles().items():
        # Either the reveal is written in the file, or the file composes it
        # from the one place it is defined.
        if REVEAL_MARK not in text and "_current_nav_reveal_lines" not in text \
           and "get_current_nav_reveal_script" not in text:
            missing.append(rel)
    assert not missing, f"collapsible sidebar with no reveal: {missing}"


def test_the_reveal_expands_collapsed_ancestors_before_scrolling():
    body = "\n".join(styles.get_current_nav_reveal_script())
    assert REVEAL_MARK in body
    # Expanding matters as much as scrolling: a unit page sits inside an app
    # subgroup that starts collapsed, so scrolling to a hidden element would
    # land on nothing.
    assert "classList.remove('collapsed')" in body
    assert "scrollIntoView" in body


def test_there_is_one_spelling_of_the_reveal():
    # It was already duplicated once in styles.py. Two copies that drift are
    # how one template keeps a behaviour another template quietly loses.
    assert "\n".join(styles.get_toggle_script()).count("scrollIntoView") == 1
    assert styles.get_current_nav_reveal_script()[1:-1] == styles._current_nav_reveal_lines()


def test_every_file_that_offers_flow_tests_also_offers_unit_tests():
    """The population is "emits a tests nav", not "is named generate_*_sidebar".

    The figma page builds its sidebar inline, so it is invisible to
    `_sidebar_renderers` above — and it shipped Flow Tests and Screen Tests
    with no Unit Tests on 12 pages until this arm was written. A file that
    offers two of the three and not the third is the ticket, repeated.
    """
    root = Path(styles.__file__).resolve().parents[3] / "jsonui_doc_cli"
    missing = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "'Flow Tests'" in text or '"Flow Tests"' in text:
            # The QUOTED label, so a prose mention in a comment cannot
            # satisfy this. The first version of this arm looked for the
            # bare words and passed on the comment sitting above the line
            # it was meant to be checking — green because of the
            # explanation for the code, not the code.
            if "'Unit Tests'" not in text and '"Unit Tests"' not in text:
                missing.append(str(path.relative_to(root)))
    assert not missing, f"offers Flow Tests but not Unit Tests: {missing}"
