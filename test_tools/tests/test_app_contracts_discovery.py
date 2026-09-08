"""An app-level declaration site, seen from the gate rather than the validator.

`discover_unit_contracts` filed every case under the basename of the file it
was read from, so a target owned by no single screen had to be declared in an
unrelated screen's spec and then reported as that screen's. The app contracts
spec removes the need for that lie; these arms are about the counts, because
the counts are what a reader believes.

The dangerous direction is an app spec that reads as a SCREEN. `scanned` is
the denominator of "N screens carrying a block", so one extra member makes
every ratio built on it describe a project with one more screen than exists,
and nothing in the output looks wrong.
"""

import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonui_test_cli import unit_contracts as uc
from jsonui_test_cli.branch_tests import APP_CONTRACTS_SPEC_TYPE

REPO_ROOT = Path(__file__).resolve().parents[2]


def _project(tmp_path, *, screens=None, app=None, unreadable=False,
             data_flow=None):
    specs = tmp_path / "docs" / "screens"
    specs.mkdir(parents=True)
    for name, block in (screens or {}).items():
        spec = {"type": "screen"}
        if block is not None:
            spec["unitContracts"] = block
        if (data_flow or {}).get(name):
            spec["dataFlow"] = data_flow[name]
        (specs / f"{name}.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if app is not None:
        (specs / "storefront.spec.json").write_text(
            json.dumps({"type": APP_CONTRACTS_SPEC_TYPE, "version": "1.0",
                        "metadata": {"name": "storefront", "description": "d"},
                        "unitContracts": app}),
            encoding="utf-8")
    if unreadable:
        (specs / "broken.spec.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "jui.config.json").write_text(
        json.dumps({"spec_directory": "docs/screens", "platforms": {}}),
        encoding="utf-8")
    return tmp_path


APP_BLOCK = {"target": "SharedHttpClient", "cases": [{"name": "retries_once"}]}
SCREEN_BLOCK = {"target": "ChatViewModel", "cases": [{"name": "sends"}]}


class TestTheDenominatorCountsScreensOnly:
    def test_an_app_spec_is_absent_from_scanned(self, tmp_path):
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        _c, scanned, _d, _p, _f, _u, _a = uc.discover_unit_contracts(root)
        assert scanned == ["chat"], scanned

    def test_an_app_spec_is_absent_from_declaring(self, tmp_path):
        """`declaring` names SCREENS carrying a block. An app spec carrying
        one is not a screen carrying one."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        _c, _s, declaring, _p, _f, _u, _a = uc.discover_unit_contracts(root)
        assert declaring == ["chat"], declaring

    def test_the_control_a_screen_spec_is_still_counted(self, tmp_path):
        """Without this, an implementation that dropped EVERY spec from
        `scanned` would satisfy both arms above."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK})
        _c, scanned, declaring, _p, _f, _u, apps = uc.discover_unit_contracts(root)
        assert scanned == ["chat"]
        assert declaring == ["chat"]
        assert apps == []

    def test_an_unreadable_spec_stays_in_the_denominator(self, tmp_path):
        """The type check is what removes a file from `scanned`, and an
        unreadable file has no readable type. It must not leave the
        denominator on the strength of a type nobody could see."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, unreadable=True)
        _c, scanned, _d, problems, _f, unread, _a = uc.discover_unit_contracts(root)
        assert sorted(scanned) == ["broken", "chat"], scanned
        assert unread == ["broken.spec.json"]
        assert any("could not be read" in p for p in problems)


class TestTheCasesStillArrive:
    def test_an_app_spec_contributes_its_cases(self, tmp_path):
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        cases, _s, _d, problems, _f, _u, apps = uc.discover_unit_contracts(root)
        assert sorted(c.name for c in cases) == ["retries_once", "sends"]
        assert apps == ["storefront.spec.json"]
        assert problems == []

    def test_an_app_case_names_its_app_and_no_screen(self, tmp_path):
        """A case has an `app` or a `screen`, never both. Filing an app-level
        case under a screen is the false ownership this spec type exists to
        remove, and it would come back silently as a plausible screen name."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        cases, *_ = uc.discover_unit_contracts(root)
        by_name = {c.name: c for c in cases}
        assert by_name["retries_once"].app == "storefront"
        assert by_name["retries_once"].screen == ""
        # The control: a screen case is unchanged by any of this.
        assert by_name["sends"].screen == "chat"
        assert by_name["sends"].app == ""

    def test_the_app_spec_is_counted_among_declaring_files(self, tmp_path):
        """`declaring_files` is the file-level count `grep -l` reproduces, so
        an app spec carrying a block belongs in it even though it is not a
        screen. The two counts answer different questions."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        _c, _s, _d, _p, files, _u, _a = uc.discover_unit_contracts(root)
        assert sorted(files) == ["chat.spec.json", "storefront.spec.json"]


class TestTheTwoPackagesSpellTheTypeAlike:
    """`jsonui-doc` validates the type and `jsonui-test` discovers it. They
    are separate packages with separate suites, so a rename in one leaves the
    other green while an app spec silently validates as a document the gate
    never reads. Compared against the validator's SOURCE rather than by
    importing it: the two tools ship separately and a test that needs both on
    `sys.path` would be skipped in exactly the tree where they diverge.
    """

    VALIDATOR = (REPO_ROOT / "document_tools" / "jsonui_doc_cli" / "spec_doc"
                 / "validator.py")

    def _validator_constant(self, name):
        tree = ast.parse(self.VALIDATOR.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        return ast.literal_eval(node.value)
        raise AssertionError(f"{name} is not assigned in {self.VALIDATOR}")

    def test_the_validator_spells_it_the_same_way(self):
        assert self._validator_constant("APP_CONTRACTS_SPEC") == APP_CONTRACTS_SPEC_TYPE

    def test_the_literal_is_what_it_reads(self):
        """Every other arm compares the two constants against EACH OTHER, so
        none of them can see both moving together. A rename that changed the
        string in both packages would keep them all green and silently orphan
        every app spec already written. This one reads the literal."""
        assert APP_CONTRACTS_SPEC_TYPE == "app_contracts_spec"


class TestTheDeclarationSiteIsJudged:
    """The production caller for `shared/core/unit_target_ownership`.

    Ownership and declaration site used to be the same thing, so "this is
    declared in the wrong place" had no meaning: the place WAS the
    definition. The rule derives ownership from the specs instead, which is
    what makes the question answerable at all.

    Only ONE direction is reported here -- an app-level declaration that a
    single screen owns. The mirror defect belongs to the check that owns
    screen-level sites; reporting both from here would hand a consumer the
    same pair twice with two different remedies.
    """

    OWNED = {"chat": {"repositories": [{"name": "ChatRepository",
                                        "methods": []}]}}

    def test_an_app_declaration_a_single_screen_owns_is_reported(self, tmp_path):
        root = _project(
            tmp_path, screens={"chat": SCREEN_BLOCK}, data_flow=self.OWNED,
            app={"target": "ChatRepository", "cases": [{"name": "loads"}]})
        _c, _s, _d, problems, _f, _u, _a = uc.discover_unit_contracts(root)
        assert len(problems) == 1, problems
        assert "ChatRepository" in problems[0]
        assert "chat" in problems[0]

    def test_the_control_an_app_owned_target_is_not_reported(self, tmp_path):
        """`SharedHttpClient` is named by no screen. Without this arm an
        implementation that reported EVERY app declaration would pass the
        arm above."""
        root = _project(
            tmp_path, screens={"chat": SCREEN_BLOCK}, data_flow=self.OWNED,
            app=APP_BLOCK)
        _c, _s, _d, problems, _f, _u, _a = uc.discover_unit_contracts(root)
        assert problems == [], problems

    def test_a_screen_declaring_its_own_target_is_not_reported(self, tmp_path):
        """The second control: the rule must not fire on screen-level sites,
        which are the overwhelming majority and would turn every project
        red."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        data_flow=self.OWNED)
        _c, _s, _d, problems, _f, _u, _a = uc.discover_unit_contracts(root)
        assert problems == []

    def test_the_rule_was_actually_loaded(self, tmp_path):
        """The positive control for the loader itself.

        Every arm above passes if `_ownership_rule()` silently returns None
        and the check never runs -- except that it would report
        OWNERSHIP_UNAVAILABLE. This asserts the rule is REACHABLE, so a tree
        where `shared/core` cannot be found fails here rather than going
        quietly green on the arms that expect no problems."""
        assert uc._ownership_rule() is not None
        rule = uc._ownership_rule()
        assert rule.SCREEN_OWNED == "screen_owned"

    def test_an_unloadable_rule_says_so_instead_of_passing(self, tmp_path):
        """The negative control, and the one that matters at distribution
        time: `shared/core/unit_target_ownership.py` is NOT in the installed
        tree until a release carries it there. The check must announce that
        it did not run -- silence would read as a clean declaration site."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        data_flow=self.OWNED,
                        app={"target": "ChatRepository",
                             "cases": [{"name": "loads"}]})
        real = uc._ownership_rule
        uc._ownership_rule = lambda: None
        try:
            _c, _s, _d, problems, _f, _u, _a = uc.discover_unit_contracts(root)
        finally:
            uc._ownership_rule = real
        assert problems == [uc.OWNERSHIP_UNAVAILABLE]
        assert "NOT checked" in problems[0]


class TestTheBlindSpotIsPrintedNotCounted:
    def test_a_run_that_read_an_app_spec_names_its_blind_spot(self, tmp_path):
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_PARTIAL in report.notes
        assert any("NOTE" in line and "Components a screen DECLARES" in line
                   for line in uc.format_report(report))

    def test_the_blind_spot_does_not_fail_the_gate(self, tmp_path):
        """A check that truthfully names its own limit must not go red for
        it -- a limit nobody can ship past gets deleted rather than fixed."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert report.notes
        assert report.ok, uc.format_report(report)

    def test_a_run_with_no_app_spec_still_says_it(self, tmp_path):
        """INVERTED 2026-09-08, when the screen-level direction landed.

        This asserted the opposite -- that a project with no app spec carries
        no note -- and the reasoning behind it still holds in general: a note
        printed unconditionally is noise, and noise is how a real one stops
        being read. It stopped applying because the limit stopped being about
        app specs. The component source is unresolved for BOTH directions, and
        the screen-level one runs on every project, so a project without an
        app spec is now judged with lower-bound owner counts too -- and it is
        precisely the project least likely to expect that.

        Kept and inverted rather than deleted: with the arm gone, restoring
        the `if app_specs` gate would be silent, and the note would go missing
        for every project that has not adopted the spec type yet."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK})
        assert uc.check_unit_contracts(root).notes == [uc.OWNERSHIP_PARTIAL]
