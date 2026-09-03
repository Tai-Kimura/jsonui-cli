"""A spec page under an app opens that app's list, not somebody else's.

`generate_spec_sidebar` renders the top-level `specs` list and the per-app
lists as siblings, and it used to expand the top-level one on every spec
page. A reader arrives from the index having chosen an app, clicks a
screen, and lands on a page whose open list is a different set of screens —
the one choice they made is gone on the first click. Reported by a user
with two screenshots: the index offered client 100 / bar 78 / liquor 75 /
admin 18, and `admin/specs/admin_app_settings.html` opened a list of 55
that is none of them (the top-level `specs/`, which belongs to no app).

Two things about that report were not quite right, and both are pinned
below so the tests do not encode them:

* The current page WAS marked `current` — inside the app's own section, one
  level down and collapsed. The highlight existed and could not be seen.
* On a project with no top-level `specs/` at all the symptom reads
  differently: nothing is expanded, because the section that used to be
  expanded is not rendered. Same defect, different face.

What this does NOT change: other apps' links stay in the sidebar HTML,
collapsed, exactly as before. Counting `<a href>` in the file will still
find them. That is a question about what the sidebar should carry, not
about which list it opens.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonui_doc_cli.test_doc.html.sidebar import generate_spec_sidebar  # noqa: E402

SECTION = re.compile(
    r"<div class='sidebar-(?:title|subtitle)([^']*)'[^>]*>.*?</span> ([^<]+)<span class='count'>(\d+)"
)


def expanded_sections(html: str) -> list[tuple[str, str]]:
    """(label, count) for every section NOT carrying `collapsed`, in order."""
    return [
        (m.group(2).strip(), m.group(3))
        for m in SECTION.finditer(html)
        if "collapsed" not in m.group(1)
    ]


def sidebar(nav: dict, current: str | None) -> str:
    return "\n".join(generate_spec_sidebar("T", nav, current))


def _specs(prefix: str, n: int) -> list[dict]:
    return [{"name": f"{prefix}{i}", "path": f"{prefix}/specs/s{i}.html"} for i in range(n)]


# The reported shape: a top-level list belonging to no app, plus apps.
REPORTED = {
    "specs": [{"name": "Top A", "path": "specs/a.html"},
              {"name": "Top B", "path": "specs/b.html"}],
    "components": [{"name": "Top C", "path": "components/c.html"}],
    "apps": {"client": _specs("client", 3), "admin": _specs("admin", 2)},
}
REPORTED = {**REPORTED, "apps": {k: {"specs": v} for k, v in REPORTED["apps"].items()}}

# The second face: two apps and no top-level specs at all.
NO_TOP_LEVEL = {"apps": {"admin": {"specs": _specs("admin", 19)},
                         "user": {"specs": _specs("user", 10)}}}


class TestThePageOpensItsOwnApp:
    def test_an_app_page_opens_that_app_first(self):
        first = expanded_sections(sidebar(REPORTED, "admin/specs/s1.html"))[0]
        assert first == ("admin", "2")

    def test_the_top_level_list_no_longer_opens_over_it(self):
        labels = [s[0] for s in expanded_sections(sidebar(REPORTED, "admin/specs/s1.html"))]
        assert "Screen Specs" not in labels[:1]

    def test_the_current_page_is_marked_inside_a_list_that_is_open(self):
        # The marker was never missing — the old sidebar set `current` on
        # the app entry too. It was one level down inside a collapsed
        # section, so the reader could not see it. Asserting only that
        # `current` appears in the list therefore passes against the defect;
        # the arm has to say the list is not collapsed.
        html = sidebar(REPORTED, "admin/specs/s1.html")
        opening = html.split("id='app-admin-specs-list'")[0].rsplit("<div class=", 1)[1]
        assert "collapsed" not in opening
        body = html.split("id='app-admin-specs-list'")[1].split("</div>")[0]
        assert "nav-link current" in body


class TestTheFaceWithNoTopLevelSpecs:
    """Same defect, and the one where the old behaviour opened nothing."""

    def test_something_is_open_at_all(self):
        assert expanded_sections(sidebar(NO_TOP_LEVEL, "admin/specs/s3.html"))

    def test_each_app_opens_its_own(self):
        assert expanded_sections(sidebar(NO_TOP_LEVEL, "admin/specs/s3.html"))[0] == ("admin", "19")
        assert expanded_sections(sidebar(NO_TOP_LEVEL, "user/specs/s2.html"))[0] == ("user", "10")


class TestWrongFixesThisWouldCatch:
    """Green in BOTH versions by construction — these do not witness the
    defect, they fence off repairs that would look right on the reported
    page. Filed apart so the red-check count is not read as evidence."""

    def test_it_is_not_enough_to_open_the_first_app(self):
        # The user read the symptom as "the first app's list opens". It was
        # actually the top-level list, which belongs to no app — but a fix
        # written to that reading would pass every arm above, since the
        # reported page happens to be in the first app of its own nav. This
        # one uses a page in the SECOND app, where the two rules differ.
        assert list(REPORTED["apps"]) == ["client", "admin"]
        labels = [s[0] for s in expanded_sections(sidebar(REPORTED, "admin/specs/s1.html"))]
        assert "client" not in labels


class TestPagesThatWereAlreadyRight:
    """Regression guards. These must hold in BOTH versions — they are here
    to catch a fix that changed more than the page it was aimed at."""

    def test_a_top_level_spec_page_is_untouched(self):
        assert expanded_sections(sidebar(REPORTED, "specs/a.html"))[0] == ("Screen Specs", "2")

    def test_a_page_belonging_to_no_app_is_untouched(self):
        assert expanded_sections(sidebar(REPORTED, "somewhere/else.html"))[0] == ("Screen Specs", "2")

    def test_no_current_path_is_untouched(self):
        assert expanded_sections(sidebar(REPORTED, None))[0] == ("Screen Specs", "2")

    def test_a_project_with_no_apps_is_untouched(self):
        nav = {k: v for k, v in REPORTED.items() if k != "apps"}
        assert expanded_sections(sidebar(nav, "specs/a.html"))[0] == ("Screen Specs", "2")

    def test_the_links_themselves_did_not_move(self):
        # Which lists open is the whole change; what they point at is not.
        html = sidebar(REPORTED, "admin/specs/s1.html")
        assert "href='../../admin/specs/s1.html'" in html
        assert "href='../../specs/a.html'" in html

    def test_no_link_is_removed_from_a_multi_app_page(self):
        # Collapsing is not deleting. A repair that dropped the other apps'
        # sections would satisfy every arm about which list opens, and the
        # sidebar would quietly stop being able to reach them.
        #
        # Counted with `href='([^']+)'` rather than a pattern anchored on
        # `/specs/` — the app pages' hrefs start `../../`, so a pattern
        # beginning at `/specs/` matches none of them and reports zero.
        for current in ("admin/specs/s1.html", "user/specs/s2.html"):
            after = len(re.findall(r"href='([^']+)'", sidebar(NO_TOP_LEVEL, current)))
            assert after == 30  # 29 specs + the Back to Index link


class TestTheAppIsFoundByContainmentNotByName:
    """The app name and the path prefix agree only because generator.py
    passes `path_prefix=app_name`. That is how the paths happen to be made,
    not something declared, so the lookup asks the data instead."""

    def test_an_app_whose_name_is_not_its_directory_still_resolves(self):
        nav = {"specs": [{"name": "T", "path": "specs/a.html"}],
               "apps": {"Admin Console": {"specs": [{"name": "S", "path": "admin/specs/s.html"}]}}}
        assert expanded_sections(sidebar(nav, "admin/specs/s.html"))[0] == ("Admin Console", "1")

    def test_a_page_under_a_directory_no_app_claims_is_not_adopted(self):
        nav = {"specs": [{"name": "T", "path": "specs/a.html"}],
               "apps": {"admin": {"specs": [{"name": "S", "path": "admin/specs/s.html"}]}}}
        labels = [s[0] for s in expanded_sections(sidebar(nav, "admin/specs/UNLISTED.html"))]
        assert labels[0] == "Screen Specs"


class TestComponentPages:
    def test_a_component_page_opens_its_app_s_components(self):
        nav = {"specs": [{"name": "T", "path": "specs/a.html"}],
               "apps": {"admin": {"specs": [{"name": "S", "path": "admin/specs/s.html"}],
                                  "components": [{"name": "C", "path": "admin/components/c.html"}]}}}
        labels = [s[0] for s in expanded_sections(sidebar(nav, "admin/components/c.html"))]
        assert labels[0] == "admin"
        assert "Components" in labels
        assert "Screen Specs" not in labels
