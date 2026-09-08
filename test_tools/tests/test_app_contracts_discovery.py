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
             data_flow=None, components=None, declares=None):
    """A face on disk.

    `components` maps a `*.component.json` file name to the `metadata.name`
    it declares -- or to None, for a component spec that declares no identity.
    `declares` maps a screen to the `customComponents[]` entries it carries.

    ⚠️ The component directory is written as a SIBLING of the screen
    directory, not the same one. Both shapes exist on real faces, and a
    specimen that puts them together cannot tell a resolver that uses the
    configured directory from one that uses the screen's own -- the defect
    reported by the face where the two differ.
    """
    specs = tmp_path / "docs" / "screens"
    specs.mkdir(parents=True)
    for name, block in (screens or {}).items():
        spec = {"type": "screen"}
        if block is not None:
            spec["unitContracts"] = block
        if (data_flow or {}).get(name):
            spec["dataFlow"] = data_flow[name]
        if (declares or {}).get(name):
            spec["structure"] = {"customComponents": declares[name]}
        (specs / f"{name}.spec.json").write_text(json.dumps(spec), encoding="utf-8")
    if components is not None:
        comp_dir = tmp_path / "docs" / "components"
        comp_dir.mkdir(parents=True, exist_ok=True)
        for file_name, identity in components.items():
            body = {"type": "component_spec", "metadata": {}}
            if identity is not None:
                body["metadata"]["name"] = identity
            (comp_dir / file_name).write_text(json.dumps(body), encoding="utf-8")
    if app is not None:
        (specs / "storefront.spec.json").write_text(
            json.dumps({"type": APP_CONTRACTS_SPEC_TYPE, "version": "1.0",
                        "metadata": {"name": "storefront", "description": "d"},
                        "unitContracts": app}),
            encoding="utf-8")
    if unreadable:
        (specs / "broken.spec.json").write_text("{ not json", encoding="utf-8")
    config = {"spec_directory": "docs/screens", "platforms": {}}
    if components is not None:
        config["component_spec_directory"] = "docs/components"
    (tmp_path / "jui.config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


APP_BLOCK = {"target": "SharedHttpClient", "cases": [{"name": "retries_once"}]}
SCREEN_BLOCK = {"target": "ChatViewModel", "cases": [{"name": "sends"}]}


class TestTheDenominatorCountsScreensOnly:
    def test_an_app_spec_is_absent_from_scanned(self, tmp_path):
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        _c, scanned, _d, _p, _f, _u, _a, _n = uc.discover_unit_contracts(root)
        assert scanned == ["chat"], scanned

    def test_an_app_spec_is_absent_from_declaring(self, tmp_path):
        """`declaring` names SCREENS carrying a block. An app spec carrying
        one is not a screen carrying one."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        _c, _s, declaring, _p, _f, _u, _a, _n = uc.discover_unit_contracts(root)
        assert declaring == ["chat"], declaring

    def test_the_control_a_screen_spec_is_still_counted(self, tmp_path):
        """Without this, an implementation that dropped EVERY spec from
        `scanned` would satisfy both arms above."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK})
        _c, scanned, declaring, _p, _f, _u, apps, _n = uc.discover_unit_contracts(root)
        assert scanned == ["chat"]
        assert declaring == ["chat"]
        assert apps == []

    def test_an_unreadable_spec_stays_in_the_denominator(self, tmp_path):
        """The type check is what removes a file from `scanned`, and an
        unreadable file has no readable type. It must not leave the
        denominator on the strength of a type nobody could see."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, unreadable=True)
        _c, scanned, _d, problems, _f, unread, _a, _n = uc.discover_unit_contracts(root)
        assert sorted(scanned) == ["broken", "chat"], scanned
        assert unread == ["broken.spec.json"]
        assert any("could not be read" in p for p in problems)


class TestTheCasesStillArrive:
    def test_an_app_spec_contributes_its_cases(self, tmp_path):
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        cases, _s, _d, problems, _f, _u, apps, _n = uc.discover_unit_contracts(root)
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
        _c, _s, _d, _p, files, _u, _a, _n = uc.discover_unit_contracts(root)
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

    def test_an_app_declaration_a_single_screen_owns_is_hinted(self, tmp_path):
        """A HINT, not a problem, and the distinction is the whole point:
        see `TestAMissingSourceCanInventASingleOwner` below."""
        root = _project(
            tmp_path, screens={"chat": SCREEN_BLOCK}, data_flow=self.OWNED,
            app={"target": "ChatRepository", "cases": [{"name": "loads"}]})
        _c, _s, _d, problems, _f, _u, _a, notes = uc.discover_unit_contracts(root)
        assert problems == []
        hit = [n for n in notes if "ChatRepository" in n]
        assert len(hit) == 1, notes
        assert "chat" in hit[0]
        assert "UNVERIFIED" in hit[0]

    def test_the_control_an_app_owned_target_is_not_reported(self, tmp_path):
        """`SharedHttpClient` is named by no screen. Without this arm an
        implementation that reported EVERY app declaration would pass the
        arm above."""
        root = _project(
            tmp_path, screens={"chat": SCREEN_BLOCK}, data_flow=self.OWNED,
            app=APP_BLOCK)
        _c, _s, _d, problems, _f, _u, _a, notes = uc.discover_unit_contracts(root)
        assert problems == [], problems
        # ⚠️ Narrowed 2026-09-08. This asserted that NO note mentions the
        # target, which stopped being the right claim when a separate channel
        # started counting targets no source owns — `SharedHttpClient` is one,
        # and that line naming it is correct. What this arm owns is that the
        # app-level DIRECTION stays silent, so it names that direction's
        # wording instead of the whole note list.
        assert not [n for n in notes
                    if "SharedHttpClient" in n and "may belong in" in n], notes

    def test_a_screen_declaring_its_own_target_is_not_reported(self, tmp_path):
        """The second control: the rule must not fire on screen-level sites,
        which are the overwhelming majority and would turn every project
        red."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        data_flow=self.OWNED)
        _c, _s, _d, problems, _f, _u, _a, _n = uc.discover_unit_contracts(root)
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
            _c, _s, _d, problems, _f, _u, _a, _n = uc.discover_unit_contracts(root)
        finally:
            uc._ownership_rule = real
        assert problems == [uc.OWNERSHIP_UNAVAILABLE]
        assert "NOT checked" in problems[0]
        # A problem, not a hint: this one says the check did not run, which
        # is the opposite claim from a clean result.
        assert report_notes_exclude(_n, uc.OWNERSHIP_UNAVAILABLE)


def report_notes_exclude(notes, text):
    return text not in (notes or [])


class TestAMissingSourceCanInventASingleOwner:
    """The specimen for the reason every finding above is a hint.

    `owner_screens` is a UNION over four sources, so leaving one out lowers
    owner counts. The first draft of this caller argued that lowering could
    never manufacture the single owner it reports. It can: 2 -> 1 is a
    decrease, and 1 is the reported count.

    This is not hypothetical and not a corpus question -- it is a property of
    the union, pinned here so that wiring the component source later cannot
    quietly reintroduce the argument.
    """

    SCREENS = {
        "Dashboard": {"dataFlow": {}},
        "Listing": {"dataFlow": {"repositories": [
            {"name": "CalendarWidget", "methods": []}]}},
    }
    DECLARED = {"Dashboard": {"CalendarWidget"}}

    def test_the_same_target_classifies_two_ways(self):
        """The promotion gate. PROMOTED 2026-09-08 -- read the note below.

        This arm used to end with

            assert with_source != without, \
                "if these ever agree, the hint above can be promoted"

        and it was the thing that told a later reader the promotion was
        allowed, so that the permission did not live in anyone's memory. The
        component source is now resolved by production
        (`_declared_component_identities`), the user ruled that a component's
        identity is its spec's required `metadata.name`, and the app-level
        channel emits findings.

        ⚠️ The two answers still differ, and that is not leftover -- it is the
        whole reason the promotion is sound. `None` means the source was not
        consulted and the count is a LOWER BOUND; supplying it can only RAISE
        the count. So the disagreement below is the measurement that says a
        reported `1` was never trustworthy without the source, and is now.
        Deleting this arm would leave nothing asserting that the two inputs
        are distinguishable at all -- and a resolver that silently returned
        `None` forever would then be invisible.
        """
        rule = uc._ownership_rule()
        assert rule is not None
        with_source, _ = rule.classify(
            "CalendarWidget", self.SCREENS, self.DECLARED, {"CalendarWidget"})
        without, _ = rule.classify(
            "CalendarWidget", self.SCREENS, None, {"CalendarWidget"})
        assert with_source == rule.APP_OWNED
        assert without == rule.SCREEN_OWNED
        assert with_source != without, (
            "supplying the component source must still change the answer; if "
            "these ever agree, the resolver has stopped contributing and the "
            "findings below are being made on a lower bound again")

    def test_adding_the_source_can_only_raise_an_owner_count(self):
        """Condition 3, at the level where the direction is a property.

        The promotion rests entirely on this: a source that could LOWER a
        count would turn a true 2 into a reported 1, which is exactly how a
        correct app-level declaration gets reported as belonging to a screen.
        Asserted over every subset rather than on one specimen, because one
        specimen agreeing is what a monotone rule and a lucky rule both do.
        """
        rule = uc._ownership_rule()
        assert rule is not None
        for target in ("CalendarWidget", "Missing", "ListingViewModel"):
            without = rule.owner_screens(target, self.SCREENS, None)
            with_source = rule.owner_screens(target, self.SCREENS, self.DECLARED)
            assert set(without) <= set(with_source), (
                f"{target}: the component source removed an owner "
                f"({without} -> {with_source}); every claim that survives "
                f"adding owners would become unsound")

    def test_so_the_check_never_fails_on_a_site_judgment(self, tmp_path):
        """The consequence, asserted where a consumer would feel it: the
        specimen's shape must not turn a correct app declaration red."""
        root = _project(
            tmp_path, screens={"chat": SCREEN_BLOCK},
            data_flow={"chat": {"repositories": [
                {"name": "CalendarWidget", "methods": []}]}},
            app={"target": "CalendarWidget", "cases": [{"name": "renders"}]})
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)


class TestTheBlindSpotIsPrintedNotCounted:
    def test_a_run_that_read_an_app_spec_names_its_blind_spot(self, tmp_path):
        """⚠️ The pinned phrase moved on 2026-09-08 and that is the point.

        It used to pin "Components a screen DECLARES", from a sentence that
        said the source was not consulted YET -- true of every run back then.
        Now the source usually IS consulted, and this specimen configures no
        `component_spec_directory`, so the note has to say the source could
        not be RESOLVED here. Pinning the old phrase would have kept passing
        while the note said something else, because both sentences mention
        components.
        """
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_PARTIAL in report.notes
        assert any("NOTE" in line and "could NOT be resolved" in line
                   for line in uc.format_report(report))

    def test_the_complete_wording_is_printed_too_not_only_stored(self, tmp_path):
        """The twin. `OWNERSHIP_COMPLETE in report.notes` says it was
        COLLECTED; only reading the rendered lines says it reaches a human.
        The defect this pairs with shipped in v1.8.53: a field was collected
        and never printed, and every arm was green.
        """
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        components={}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert any("NOTE" in line and "component ownership were" not in line
                   and "metadata.name" in line
                   for line in uc.format_report(report)), \
            uc.format_report(report)

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
        notes = uc.check_unit_contracts(root).notes
        # Equality was the right assertion while this was the only note. A
        # second channel now counts targets no source owns, and this fixture
        # has one (`ChatViewModel` on a screen named `chat` resolves to
        # `chatViewModel`), so the list is checked for membership and the
        # extra line is identified rather than tolerated silently.
        assert uc.OWNERSHIP_PARTIAL in notes, notes
        assert all(n == uc.OWNERSHIP_PARTIAL or "resolve to NO owner" in n
                   for n in notes), notes


class TestTheComponentSourceIsResolvedByProduction:
    """The wiring ruled on 2026-09-08: a component's identity is its spec's
    `metadata.name`, required, and production resolves it.

    ⚠️ These arms drive `check_unit_contracts` on a project ON DISK rather
    than calling the pure rule. The pure rule has been able to accept
    `components_declared_by_screen` since it was written -- what was missing
    for months was a production caller passing it, and a unit test of the rule
    is green either way. The thing under test here is the WIRE.
    """

    #: Two screens, and the only thing that makes `Picker` app-owned is that
    #: Dashboard DECLARES it as a component while Listing owns it via
    #: dataFlow. Drop the component source and the count falls 2 -> 1.
    SCREENS = {"Dashboard": None, "Listing": None}
    DECLARES = {"Dashboard": [
        {"name": "Picker", "specFile": "picker.component.json"}]}
    DATA_FLOW = {"Listing": {"repositories": [{"name": "Picker", "methods": []}]}}

    def test_a_component_owned_target_stays_app_owned(self, tmp_path):
        """Condition 3, end to end: the specimen the ticket named.

        Dashboard owns `Picker` through a component, Listing through
        dataFlow. That is two owners, so an app-level declaration is CORRECT
        and must not be reported. Before the wiring the component owner was
        invisible, the count was 1, and this specimen produced
        "may belong in Listing's spec" -- telling a consumer to move a
        declaration that was already in the only right place.
        """
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"},
            declares=self.DECLARES,
            app={"target": "Picker", "cases": [{"name": "renders"}]})
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)
        assert not any("may belong in" in p or "belongs in" in p
                       for p in report.problems), report.problems

    def test_the_control_without_the_component_the_same_specimen_is_reported(
            self, tmp_path):
        """The arm above passes trivially if nothing is ever reported.

        Same specimen, minus only the component declaration. Now Listing is
        genuinely the only owner, so the app-level site IS wrong and the
        finding must fire. This is what proves the first arm measured the
        component source rather than a check that never speaks.
        """
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"},
            declares={},
            app={"target": "Picker", "cases": [{"name": "renders"}]})
        report = uc.check_unit_contracts(root)
        assert any("belongs in Listing's spec" in p for p in report.problems), \
            uc.format_report(report)

    def test_it_is_a_finding_now_not_a_hint(self, tmp_path):
        """Condition 5, the half that fails the run.

        The app-level channel used to append to `hints`, which never touch
        `ok`. Promoted in the same commit as the wording; an arm on the text
        alone would pass while the gate stayed green.
        """
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"}, declares={},
            app={"target": "Picker", "cases": [{"name": "renders"}]})
        report = uc.check_unit_contracts(root)
        assert not report.ok, "an app-level site with one real owner must fail"

    def test_the_wording_moves_with_the_behaviour(self, tmp_path):
        """Condition 5, the other half.

        A message that still calls the count a lower bound while a finding
        fires on it tells the reader the tool does not trust its own result.
        """
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"},
            declares=self.DECLARES, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_COMPLETE in report.notes, report.notes
        assert uc.OWNERSHIP_PARTIAL not in report.notes

    def test_an_unresolvable_source_says_so_and_stays_a_hint(self, tmp_path):
        """⚠️ The two states must not share a sentence.

        No `component_spec_directory` in the config -- so the source could not
        be consulted at all. That is NOT the same as a face whose screens
        declare no components, and a single string for both is how a
        distribution missing `shared/` reads as a clean project.
        """
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_PARTIAL in report.notes, report.notes
        assert uc.OWNERSHIP_COMPLETE not in report.notes

    def test_the_control_a_face_with_no_components_is_not_the_same_state(
            self, tmp_path):
        """The other half of the pair above: consulted, and found nothing.

        Same EMPTY map as a face with no components declared -- and this is
        the arm that fails if a later edit folds `None` into `{}`.
        """
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        components={}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_COMPLETE in report.notes, report.notes
        assert uc.OWNERSHIP_PARTIAL not in report.notes


class TestTheIdentityIsRequiredAndNeverSubstituted:
    def test_a_component_with_no_name_is_reported(self, tmp_path):
        """The ruling, where a writer feels it.

        No default is substituted -- not the file stem, not "Component". A
        substitute would merge every unnamed component onto one target, and
        the merge would be invisible because a wrong owner set still
        classifies.
        """
        root = _project(
            tmp_path, screens={"Dashboard": None},
            components={"picker.component.json": None},
            declares={"Dashboard": [
                {"name": "Picker", "specFile": "picker.component.json"}]},
            app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert any("declares no metadata.name" in p for p in report.problems), \
            uc.format_report(report)

    def test_the_stem_is_not_used_as_a_fallback(self):
        """The inversion of the arm above, at the rule.

        If a later edit adds `or path.stem`, the arm above still passes -- the
        component would resolve, just to the wrong identity. This one names
        the substitute directly.
        """
        identity = uc._identity_rule()
        assert identity is not None
        assert identity.identity_of({"metadata": {}}) is None
        assert identity.identity_of({"metadata": {"name": "   "}}) is None
        assert identity.identity_of({"metadata": {"name": "Picker"}}) == "Picker"

    def test_a_screen_that_names_it_differently_is_reported(self, tmp_path):
        """Two spellings of one fact.

        The screen's `customComponents[]` entry carries its own `name`. The
        component spec is the identity; when they disagree, ownership would be
        computed from whichever the resolver happened to read.
        """
        root = _project(
            tmp_path, screens={"Dashboard": None},
            components={"picker.component.json": "Picker"},
            declares={"Dashboard": [
                {"name": "Chooser", "specFile": "picker.component.json"}]},
            app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert any("names itself 'Picker'" in p for p in report.problems), \
            uc.format_report(report)

    def test_ownership_does_not_aggregate_across_apps(self):
        """Condition 4.

        The rule is scoped to the screens it is GIVEN. Two apps that happen to
        use the same target must not merge into one owner set -- which would
        turn a screen-owned target in each app into an app-owned target in
        both, and silence a real finding on each side.
        """
        rule = uc._ownership_rule()
        identity = uc._identity_rule()
        assert rule is not None and identity is not None
        app_a = {"Dashboard": {"structure": {"customComponents": [
            {"name": "Picker", "specFile": "picker.component.json"}]}}}
        app_b = {"Console": {"structure": {"customComponents": [
            {"name": "Picker", "specFile": "picker.component.json"}]}}}
        read = lambda _f: {"metadata": {"name": "Picker"}}
        decl_a, _ = identity.resolve_declared_identities(app_a, read)
        decl_b, _ = identity.resolve_declared_identities(app_b, read)
        assert rule.owner_screens("Picker", app_a, decl_a) == ["Dashboard"]
        assert rule.owner_screens("Picker", app_b, decl_b) == ["Console"]
        # And the control: given BOTH, it is two owners. So the separation
        # above is the caller's scope, not the rule failing to see them.
        both = dict(app_a, **app_b)
        decl_both, _ = identity.resolve_declared_identities(both, read)
        assert rule.owner_screens("Picker", both, decl_both) == \
            ["Console", "Dashboard"]

    def test_the_three_controls_a_viewmodel_a_component_and_a_utility(self):
        """Condition 2: known VM = 1, known component = 1, shared utility = 0.

        One table so the three cannot drift apart, and so a resolver that
        returned every screen for everything would fail on the utility.
        """
        rule = uc._ownership_rule()
        identity = uc._identity_rule()
        assert rule is not None and identity is not None
        screens = {"Dashboard": {"structure": {"customComponents": [
            {"name": "Picker", "specFile": "picker.component.json"}]}}}
        declared, problems = identity.resolve_declared_identities(
            screens, lambda _f: {"metadata": {"name": "Picker"}})
        assert problems == []
        assert rule.owner_screens("DashboardViewModel", screens, declared) == \
            ["Dashboard"]
        assert rule.owner_screens("Picker", screens, declared) == ["Dashboard"]
        assert rule.owner_screens("SharedHttpClient", screens, declared) == []


class TestTheScreenLevelDirectionIsWiredToo:
    """⚠️ Written because a mutation proved it was NOT measured.

    Both production call sites were given `components` in the same commit, and
    unwiring the app-level one reddened two arms while unwiring the
    screen-level one changed NOTHING. A wire nothing measures is
    indistinguishable from a wire that was never added -- and this direction
    is the one that runs on EVERY project, app spec or not.

    The reason no existing specimen covered it: this direction only speaks for
    `APP_OWNED with >= 2 owners`, and reaching two owners through a component
    is exactly the shape the source was missing.
    """

    #: `Picker` is declared in Dashboard's own spec, but Listing owns it
    #: through dataFlow and Dashboard owns it through a COMPONENT. Two owners,
    #: so no single screen's spec records the truth -- and without the
    #: component source it is one owner and the check stays silent.
    SCREENS = {"Dashboard": {"target": "Picker", "cases": [{"name": "renders"}]},
               "Listing": None}
    DATA_FLOW = {"Listing": {"repositories": [{"name": "Picker", "methods": []}]}}
    DECLARES = {"Dashboard": [
        {"name": "Picker", "specFile": "picker.component.json"}]}

    def test_a_component_owned_target_declared_on_a_screen_is_reported(
            self, tmp_path):
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"},
            declares=self.DECLARES)
        report = uc.check_unit_contracts(root)
        assert any("2 screens own it" in p and "'Picker'" in p
                   for p in report.problems), uc.format_report(report)

    def test_the_control_without_the_component_it_stays_silent(self, tmp_path):
        """The same specimen minus the component declaration.

        Now Listing is the only owner besides the declaring screen's own
        ViewModel, the count is 1, and this direction correctly says nothing.
        Without this arm the one above would pass for an implementation that
        reported every declared target.
        """
        root = _project(
            tmp_path, screens=self.SCREENS, data_flow=self.DATA_FLOW,
            components={"picker.component.json": "Picker"}, declares={})
        report = uc.check_unit_contracts(root)
        assert not any("screens own it" in p for p in report.problems), \
            uc.format_report(report)


class TestWhatNeitherDirectionReports:
    """Reported 2026-09-08 by a face that read its own specs by hand.

    ⚠️ The face did that because the note said owner counts were "complete".
    It meant every SOURCE was consulted; it was read as every TARGET being
    covered. 14 of that face's 26 declared targets resolved to ZERO owners,
    and neither direction says anything about zero — one speaks for
    exactly-one, the other for two-or-more.

    Both halves moved in one commit: the wording no longer claims coverage,
    and the count is printed instead of being left for someone to compute by
    hand or never.
    """

    SCREENS = {"Dashboard": None}
    #: `SharedHttpClient` is owned by nothing: not a ViewModel name, not in
    #: dataFlow, not a component. Exactly the shape the face measured.
    APP = {"target": "SharedHttpClient", "cases": [{"name": "retries_once"}]}

    def test_a_target_no_source_owns_is_counted(self, tmp_path):
        root = _project(tmp_path, screens=self.SCREENS, components={},
                        app=self.APP)
        report = uc.check_unit_contracts(root)
        assert any("resolve to NO owner" in n and "SharedHttpClient" in n
                   for n in report.notes), report.notes

    def test_it_is_a_count_not_a_finding(self, tmp_path):
        """A shared utility that legitimately belongs nowhere and a misspelled
        target both land here, and this rule cannot tell them apart without
        `known_targets` — which no caller supplies. Printing a number is
        honest; failing the run would be inventing a verdict."""
        root = _project(tmp_path, screens=self.SCREENS, components={},
                        app=self.APP)
        report = uc.check_unit_contracts(root)
        assert report.ok, uc.format_report(report)

    def test_the_control_an_owned_target_is_not_counted(self, tmp_path):
        """Without this, a rule that counted every target would pass above.

        ⚠️ The screen is `Chat`, not `chat`. The shared `SCREEN_BLOCK` fixture
        declares `ChatViewModel` on a screen named `chat`, and the generator
        names that screen's ViewModel `chatViewModel` — so the shared fixture's
        target is genuinely unowned, and using it here would have made this
        control assert the opposite of what it means. The first cut did
        exactly that and failed, which is the fixture being wrong rather than
        the rule.
        """
        root = _project(
            tmp_path, components={},
            screens={"Chat": {"target": "ChatViewModel",
                              "cases": [{"name": "sends"}]}})
        report = uc.check_unit_contracts(root)
        assert not any("resolve to NO owner" in n for n in report.notes), \
            report.notes

    def test_the_marker_is_emitted_not_just_named(self):
        """⚠️ Reported independently by two faces: the constant NAMES
        (`OWNERSHIP_COMPLETE`/`_PARTIAL`) live only in this module, so a
        consumer grepping for them gets 0 hits and reads that as the check not
        existing — one face wrote exactly that before catching it. Matching the
        prose instead ties every consumer gate to wording that moves between
        releases. So the discriminator has to be IN the output."""
        assert uc.OWNERSHIP_MARKER_COMPLETE in uc.OWNERSHIP_COMPLETE
        assert uc.OWNERSHIP_MARKER_PARTIAL in uc.OWNERSHIP_PARTIAL
        assert uc.OWNERSHIP_MARKER_COMPLETE not in uc.OWNERSHIP_PARTIAL
        assert uc.OWNERSHIP_MARKER_PARTIAL not in uc.OWNERSHIP_COMPLETE

    def test_the_marker_reaches_the_rendered_lines(self, tmp_path):
        """The pair to the arm above: being in the constant says it was
        WRITTEN; only reading the rendered output says it reaches a consumer's
        grep. That gap shipped in v1.8.53 — a field collected and never
        printed, with every arm green."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK},
                        components={}, app=APP_BLOCK)
        lines = uc.format_report(uc.check_unit_contracts(root))
        assert any(uc.OWNERSHIP_MARKER_COMPLETE in line for line in lines), lines

    def test_the_complete_wording_no_longer_claims_coverage(self):
        """The exact misreading, pinned. `complete` next to `owner counts` is
        what the face read as coverage."""
        assert "SOURCES complete is not TARGETS covered" in uc.OWNERSHIP_COMPLETE
        assert "owner counts below are complete" not in uc.OWNERSHIP_COMPLETE


class TestTheDefaultIsNotOneReaderShortOfThree:
    """Reported 2026-09-08 by a face whose directory layout was correct all
    along — only the config KEY was absent.

    `jui` has applied a default for `component_spec_directory` since before
    this check existed (`config_manager`), and `init_cmd` writes it into new
    configs. This module used a bare `.get()` with no default, so a project
    created before `init_cmd` started writing the key had `jui` working from
    the default while THIS check alone went to `OWNERSHIP_PARTIAL` — with no
    problem line, so nothing said why.

    📌 The same fact was a literal in three places and absent from a fourth
    reader. Four implementations of one default; the one that degraded quietly
    is the one nobody noticed for a day.
    """

    DECL = {"Dashboard": [
        {"name": "Picker", "specFile": "picker.component.json"}]}

    def test_a_config_without_the_key_still_resolves_the_source(self, tmp_path):
        """The defect. `components=None` on `_project` writes NO
        `component_spec_directory` into the config, and the default directory
        is created by hand at the layout `jui` would have assumed."""
        root = _project(tmp_path, screens={"Dashboard": None},
                        declares=self.DECL, app=APP_BLOCK)
        comp = root / "docs" / "components" / "json"
        comp.mkdir(parents=True)
        (comp / "picker.component.json").write_text(
            json.dumps({"type": "component_spec",
                        "metadata": {"name": "Picker"}}), encoding="utf-8")
        report = uc.check_unit_contracts(root)
        assert uc.OWNERSHIP_COMPLETE in report.notes, report.notes
        assert uc.OWNERSHIP_PARTIAL not in report.notes

    def test_a_project_with_no_components_is_not_scolded(self, tmp_path):
        """⚠️ The noise the default could have introduced.

        A project that never wrote the key and has no components must not be
        told every run that its configuration is broken — the problem line is
        for an EXPLICIT directory that is missing, which is a real config
        error. Without this arm the fix above would trade a silent gap for a
        permanent false alarm on every face that has no components.
        """
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        report = uc.check_unit_contracts(root)
        assert not any("configured but not a directory" in p
                       for p in report.problems), report.problems

    def test_an_explicit_but_missing_directory_is_still_reported(self, tmp_path):
        """The control for the arm above: a config error must stay loud."""
        root = _project(tmp_path, screens={"chat": SCREEN_BLOCK}, app=APP_BLOCK)
        cfg = root / "jui.config.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data["component_spec_directory"] = "docs/nowhere"
        cfg.write_text(json.dumps(data), encoding="utf-8")
        report = uc.check_unit_contracts(root)
        assert any("configured but not a directory" in p
                   for p in report.problems), report.problems

    def test_the_default_is_named_once(self):
        """The SSoT itself. If a reader re-introduces its own literal, this
        stays green — so the arm below counts the literals instead."""
        keys = uc._config_keys()
        assert keys is not None
        assert keys.default_for("component_spec_directory") == "docs/components/json"
        assert keys.default_for("a_key_with_no_default") is None
