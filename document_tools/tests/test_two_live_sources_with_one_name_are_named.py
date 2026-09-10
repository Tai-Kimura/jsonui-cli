"""Regression: doc-stale-names-old-pages-but-nothing-names-an-old-source.

v1.8.68 gave the run an instrument for a page nothing wrote this time. It
cannot see a rename done in ONE slot directory and not the other: both
sources are alive, so the run writes BOTH pages every time and the site
carries two spellings of one screen — on the face that reported it the two
had drifted as far as their titles.

🚨 That face's first remedy was to delete the generated PAGES. The next run
wrote them again, because the sources are alive. So the deletion looked like
a fix at the moment it was made and came back somewhere the person who made
it was not looking — the failure did not report itself. Until an instrument
names the SOURCE, a face has no better move available, which is why the
absence of this check is the defect and not the face's reaction to it.

⚠️ Direction: those two pages came back because their sources were alive.
A deletion aimed at a page whose source is already gone does NOT come back,
and nothing then measures whether it was the right page. The mechanism is
not safe; this instance landed on the harmless side of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "document_tools"))

from jsonui_doc_cli.test_doc import generator as gen  # noqa: E402


def _spec(path: Path, screen_id: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "screen_spec", "version": "1.0",
        "metadata": {"screen_id": screen_id, "title": title, "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
    }), encoding="utf-8")


def test_a_rename_done_in_one_slot_and_not_the_other_is_named(tmp_path, capsys):
    docs = tmp_path / "docs"
    _spec(docs / "requirements" / "json" / "forgotpassword.spec.json",
          "forgotpassword", "Password reset request")
    _spec(docs / "screens" / "json" / "forgot_password.spec.json",
          "forgot_password", "Password reset")
    _spec(docs / "screens" / "json" / "home.spec.json", "home", "Home")

    found = gen._report_colliding_spec_sources(docs)
    printed = capsys.readouterr().out

    assert [k for k, _ in found] == ["forgotpassword"]
    assert "WARNING [doc-source]: 1 name(s) are held by more than one LIVE spec source" in printed
    # Both sides named, with the path that tells them apart.
    assert "requirements/json/forgotpassword.spec.json" in printed
    assert "screens/json/forgot_password.spec.json" in printed
    # The titles, because that is how far this pair had drifted on the face
    # that reported it — the same screen under two names saying two things.
    assert "Password reset request" in printed and "Password reset" in printed
    # …and the line that stops the remedy that does not work.
    assert "Deleting the generated pages does not fix this" in printed


def test_names_that_do_not_normalise_alike_are_silent(tmp_path, capsys):
    """The control. Two slot directories holding DIFFERENT screens is the
    normal case; without this the warning could fire on every face that uses
    `requirements/` at all, which would make it noise instead of a finding."""
    docs = tmp_path / "docs"
    _spec(docs / "requirements" / "json" / "billing.spec.json", "billing", "Billing")
    _spec(docs / "screens" / "json" / "home.spec.json", "home", "Home")

    assert gen._report_colliding_spec_sources(docs) == []
    assert "doc-source" not in capsys.readouterr().out


def test_the_same_name_inside_one_directory_is_named_too(tmp_path, capsys):
    """The rename need not cross slots — `old_name` and `oldname` side by
    side in `screens/json` is the same defect and the same remedy."""
    docs = tmp_path / "docs"
    _spec(docs / "screens" / "json" / "item_detail.spec.json", "item_detail", "Detail")
    _spec(docs / "screens" / "json" / "itemdetail.spec.json", "itemdetail", "Detail (old)")

    found = gen._report_colliding_spec_sources(docs)
    assert [k for k, _ in found] == ["itemdetail"]
    assert "item_detail.spec.json" in capsys.readouterr().out


def test_the_key_ignores_separators_and_case_only(tmp_path):
    """The predicate, stated where it is used. A rename changes separators
    and case; it does not turn one word into another."""
    assert gen._source_key(Path("forgot_password.spec.json")) == "forgotpassword"
    assert gen._source_key(Path("forgotpassword.spec.json")) == "forgotpassword"
    assert gen._source_key(Path("Forgot-Password.spec.json")) == "forgotpassword"
    assert gen._source_key(Path("infopanel.component.json")) == "infopanel"
    # …and does NOT collapse two different screens.
    assert gen._source_key(Path("reset_password.spec.json")) != \
        gen._source_key(Path("forgot_password.spec.json"))


def test_a_component_and_a_screen_sharing_a_name_are_named(tmp_path, capsys):
    """A component spec and a screen spec under one name is the same
    ambiguity: two live sources, one key, two pages."""
    docs = tmp_path / "docs"
    _spec(docs / "screens" / "json" / "side_panel.spec.json", "side_panel", "Side panel")
    (docs / "components" / "json").mkdir(parents=True)
    (docs / "components" / "json" / "sidepanel.component.json").write_text(json.dumps({
        "type": "component_spec", "version": "1.0",
        "metadata": {"component_id": "sidepanel", "title": "Side panel (component)", "description": "d"},
        "structure": {"root": {"type": "View", "children": []}},
    }), encoding="utf-8")
    found = gen._report_colliding_spec_sources(docs)
    assert [k for k, _ in found] == ["sidepanel"]
    assert "components/json/sidepanel.component.json" in capsys.readouterr().out


def test_the_same_file_name_in_two_slots_is_silent(tmp_path, capsys):
    """The control this check needed and did not have, 2026-09-10.

    The first cut asked only whether the names normalise alike, so it named
    every face that keeps a `requirements/` spec and a `screens/` spec for
    one screen under the SAME file name — a deliberate arrangement, measured
    on one face as fourteen pairs, every one with the same title. The defect
    reported is a rename done in one slot and not the other: the spellings
    DIFFER and normalise alike.

    ⚠️ The control that shipped with the first cut — two slots holding two
    DIFFERENT screens — does not test this. Those names do not normalise
    alike either, so they never reach the predicate. A control has to be
    chosen from inside the window it is checking.
    """
    docs = tmp_path / "docs"
    _spec(docs / "requirements" / "json" / "login.spec.json", "login", "Login")
    _spec(docs / "screens" / "json" / "login.spec.json", "login", "Login")
    _spec(docs / "requirements" / "json" / "splash.spec.json", "splash", "Splash")
    _spec(docs / "screens" / "json" / "splash.spec.json", "splash", "Splash")

    assert gen._report_colliding_spec_sources(docs) == []
    assert "doc-source" not in capsys.readouterr().out


def test_one_differing_spelling_among_same_named_pairs_is_still_named(tmp_path, capsys):
    """…and narrowing must not swallow the real one. The same tree as the
    control, plus one screen renamed under only one slot."""
    docs = tmp_path / "docs"
    _spec(docs / "requirements" / "json" / "login.spec.json", "login", "Login")
    _spec(docs / "screens" / "json" / "login.spec.json", "login", "Login")
    _spec(docs / "requirements" / "json" / "twofaverification.spec.json",
          "twofaverification", "Two-factor")
    _spec(docs / "screens" / "json" / "two_fa_verification.spec.json",
          "two_fa_verification", "Two-factor (renamed)")

    found = gen._report_colliding_spec_sources(docs)
    printed = capsys.readouterr().out
    assert [k for k, _ in found] == ["twofaverification"], "the deliberate pair must not be named"
    assert "1 name(s) are held by more than one LIVE spec source" in printed
    assert "login" not in printed


def test_the_count_reaches_the_manifest_because_the_warning_tally_cannot_carry_it(tmp_path, monkeypatch):
    r"""triage, 2026-09-10: `warnings N` in the closing line counts LINES.

    This check reports N names in ONE line, so fourteen findings and one
    finding produce the same tally — and narrowing the predicate from 14 to
    0 moves that number by one. Someone comparing closing lines cannot see
    the change at all. triage read a 14 as a 1 exactly this way while
    measuring it, with `grep -oE 'WARNING \[doc-[a-z-]*\]' | uniq -c`.

    ⚠️ Direction: the misreading says "the detector did not fire", which is
    shaped like a bug report about the implementation — so it sends the
    reader to the wrong code and never to their own instrument.

    So the number goes where the run's numbers live, explicit zero included.
    """
    docs = tmp_path / "docs"
    _spec(docs / "requirements" / "json" / "twofaverification.spec.json", "a", "T")
    _spec(docs / "screens" / "json" / "two_fa_verification.spec.json", "b", "T")
    _spec(docs / "requirements" / "json" / "storeinfo.spec.json", "c", "S")
    _spec(docs / "screens" / "json" / "store_info.spec.json", "d", "S")

    out = tmp_path / "out"; out.mkdir()
    monkeypatch.setattr(gen, "get_written_pages", lambda: set())
    assert len(gen._report_colliding_spec_sources(docs)) == 2
    gen._record_generation_manifest(out, tmp_path, [], {})
    run = json.loads((tmp_path / ".jsonui-cli" / "generation-manifest.json")
                     .read_text(encoding="utf-8"))["summary"]["run"]
    assert run["collidingSourceNames"] == 2

    # …and the explicit zero, so a reader can tell "none" from "older record".
    gen._colliding_sources = 0
    assert gen._report_colliding_spec_sources(tmp_path / "empty") == []
    gen._record_generation_manifest(out, tmp_path, [], {})
    run2 = json.loads((tmp_path / ".jsonui-cli" / "generation-manifest.json")
                      .read_text(encoding="utf-8"))["summary"]["run"]
    assert run2["collidingSourceNames"] == 0
