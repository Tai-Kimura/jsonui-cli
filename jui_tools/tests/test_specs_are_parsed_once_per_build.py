"""One `jui build` parses the specs once, so per-spec output appears once.

`cmd_build` had two consumers that each called `_load_all_specs`:
`_sync_viewmodel_protocols` and `_check_isolated_embed_constraints`. Every
per-spec line printed during extraction therefore appeared twice — including
the `@canonical` enum NOTE and the canonical-mark WARNINGs.

Only on some projects, though: the embed gate returns before it loads
anything when no layout declares `navigationMode: "isolated"`. Measured on a
temp project, one spec with one finding:

    isolated Embed absent,  1 platform    1 NOTE
    isolated Embed absent,  3 platforms   1 NOTE
    isolated Embed PRESENT, 1 platform    2 NOTE
    isolated Embed PRESENT, 3 platforms   2 NOTE

The platform count never moves it, which is what the report supposed.

Two things about how this was found, kept because they are easy to repeat.
The report was of a doubling seen on one project alongside a single count on
another, and both the offered explanation (per platform) and this mechanism
predicted a doubling — so reproducing a doubling did not confirm either one.
The report's number later turned out to be a measurement artefact and was
withdrawn; six projects were then counted and none doubles, because none of
them declares an isolated Embed. So this defect is real, reproduced above,
and had no exposure at all when it was fixed. Retracting the wrong
explanation would not have shown that, and neither would the right one.


The arms below pin the contract rather than the plumbing: given a spec list,
neither consumer reloads. A version that cached inside `_load_all_specs`
would pass them too, and should.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from jui_cli.commands import build_cmd  # noqa: E402


@pytest.fixture
def no_reload(monkeypatch):
    """Make `_load_all_specs` fail loudly if anything calls it."""
    calls = []

    def boom(config_mgr):
        calls.append(config_mgr)
        raise AssertionError("specs were loaded again")

    monkeypatch.setattr(build_cmd, "_load_all_specs", boom)
    return calls


class TestGivenTheSpecsNeitherConsumerReloadsThem:
    def test_the_embed_gate_uses_what_it_is_given(self, no_reload, tmp_path):
        # A layouts dir with no isolated Embed returns True before it would
        # have loaded anything, so this arm needs one present to be
        # meaningful — otherwise it passes against the old code as well.
        layouts = tmp_path / "layouts"
        layouts.mkdir()
        (layouts / "host.json").write_text(
            '{"type":"View","id":"h","child":[{"type":"Embed","id":"e",'
            '"screen":"my_page","navigationMode":"isolated"}]}',
            encoding="utf-8")

        class Cfg:
            layouts_directory = layouts

        assert build_cmd._check_isolated_embed_constraints(Cfg(), specs=[]) is True
        assert no_reload == []

    def test_the_gate_would_have_reloaded_without_the_argument(self, no_reload, tmp_path):
        # The control for the arm above: the same call WITHOUT `specs` does
        # reach `_load_all_specs`. Without this, an implementation that had
        # stopped loading entirely would look identical.
        layouts = tmp_path / "layouts"
        layouts.mkdir()
        (layouts / "host.json").write_text(
            '{"type":"View","id":"h","child":[{"type":"Embed","id":"e",'
            '"screen":"my_page","navigationMode":"isolated"}]}',
            encoding="utf-8")

        class Cfg:
            layouts_directory = layouts

        with pytest.raises(AssertionError, match="loaded again"):
            build_cmd._check_isolated_embed_constraints(Cfg())

    def test_protocol_sync_uses_what_it_is_given(self, no_reload):
        # An empty list is a legitimate answer meaning "no specs" — the
        # function returns early on it — so passing `[]` proves it never
        # asked for its own copy.
        assert build_cmd._sync_viewmodel_protocols(
            None, {}, {}, None, specs=[]) is True
        assert no_reload == []


class TestTheGateStillGates:
    """The de-duplication must not disarm the check it shares specs with.

    Written WITHOUT the `specs` argument on purpose: both of these return
    before any loading in either version, so they are true regression guards
    rather than arms that go red because a parameter is missing."""

    def test_no_isolated_embed_is_still_a_pass(self, tmp_path):
        layouts = tmp_path / "layouts"
        layouts.mkdir()
        (layouts / "plain.json").write_text(
            '{"type":"View","id":"v"}', encoding="utf-8")

        class Cfg:
            layouts_directory = layouts

        assert build_cmd._check_isolated_embed_constraints(Cfg()) is True

    def test_a_missing_layouts_dir_is_still_a_pass(self, tmp_path):
        class Cfg:
            layouts_directory = tmp_path / "nope"

        assert build_cmd._check_isolated_embed_constraints(Cfg()) is True
