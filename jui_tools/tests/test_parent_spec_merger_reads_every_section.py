"""A sub-spec can supply every section the parent is forbidden from declaring.

v1.7.3 made a parent declaring `dataFlow.repositories` an error, on the ground
that the merger builds that section from the sub-specs and anything written in
the parent is discarded. The message said to move the declaration into a
sub-spec.

For four of the six sections it fires on that was not possible: the merger did
not read `error_handling`, `task_cancellation`, `structure.rootComponents` or
`branchContracts` from sub-specs either. The instruction had no destination.

`dataFlow.viewModel` was the mirror image — read from the parent, dropped from
the sub-specs — and the two together left `branchContracts` with no legal home
at all: it must sit with the viewModel methods it names, the viewModel only
worked in the parent, and the parent may not declare branchContracts.

Reported by the lane that took the v1.7.3 message at its word and found the
content vanished. Their measurement also corrected mine: I had told every lane
that deleting the flagged sections left the merged output byte-identical, so
the change was free. The bytes matched, but not for the reason I gave — not
because the sub-specs already carried the content, but because the parent's
copy was being discarded before it could matter. Deleting it removes the
content, and eleven root components and six error-handling entries existed
nowhere else.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "jui_tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "jui_tools"))

from jui_cli.core.parent_spec_merger import (  # noqa: E402
    ParentSpecDeclarationError, ParentSpecMerger,
)


class SubSpecsSupplyEverythingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.parent_path = self.root / "p.spec.json"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def merge(self, *subs):
        files = []
        for i, sub in enumerate(subs):
            body = {"type": "screen_spec",
                    "metadata": {"name": f"S{i}", "description": "s"}}
            body.update(sub)
            self.write(f"p/{i}.spec.json", body)
            files.append({"file": f"p/{i}.spec.json", "name": f"S{i}"})
        self.write("p.spec.json", {
            "type": "screen_parent_spec", "version": "1.0",
            "metadata": {"name": "P", "displayName": "P", "description": "P."},
            "subSpecs": files})
        return ParentSpecMerger().merge_from_file(self.parent_path)

    def test_a_sub_spec_supplies_the_view_model(self):
        result = self.merge({"dataFlow": {"viewModel": {
            "methods": [{"name": "onLoad"}],
            "vars": [{"name": "loading", "type": "Bool"}],
            "description": "the screen's contract"}}})
        vm = result.spec["dataFlow"]["viewModel"]
        self.assertEqual([m["name"] for m in vm["methods"]], ["onLoad"])
        self.assertEqual([v["name"] for v in vm["vars"]], ["loading"])
        self.assertEqual(vm["description"], "the screen's contract")

    def test_view_models_from_several_sub_specs_are_merged(self):
        result = self.merge(
            {"dataFlow": {"viewModel": {"methods": [{"name": "onLoad"}]}}},
            {"dataFlow": {"viewModel": {"methods": [{"name": "onRefresh"}]}}})
        self.assertEqual(
            [m["name"] for m in result.spec["dataFlow"]["viewModel"]["methods"]],
            ["onLoad", "onRefresh"])

    def test_two_sub_specs_declaring_one_method_differently_conflict(self):
        result = self.merge(
            {"dataFlow": {"viewModel": {"methods": [
                {"name": "onLoad", "returnType": "Void"}]}}},
            {"dataFlow": {"viewModel": {"methods": [
                {"name": "onLoad", "returnType": "String"}]}}})
        self.assertTrue(result.has_conflicts)
        self.assertIn("viewModel.methods[name=onLoad]",
                      result.conflicts[0].path)

    def test_identical_declarations_do_not_conflict(self):
        """Two sub-specs describing the same shared method is normal."""
        m = {"dataFlow": {"viewModel": {"methods": [{"name": "onLoad"}]}}}
        result = self.merge(m, json.loads(json.dumps(m)))
        self.assertFalse(result.has_conflicts)
        self.assertEqual(
            len(result.spec["dataFlow"]["viewModel"]["methods"]), 1)

    def test_unit_contracts_come_from_sub_specs(self):
        """The same defect, found again in a section added after this file.

        Reported 2026-09-04: `unitContracts` was default-denied in the parent
        (the message promising, from a template, that the merger builds it
        from the sub-specs) while no arm here built it. A split screen had no
        legal home for the block — parent a hard error, sub-spec read by
        nobody — which is precisely what the docstring above says was fixed
        for the other six sections.
        """
        result = self.merge(
            {"unitContracts": {"target": "Handler",
                               "cases": [{"name": "a"}, {"name": "b"}]}})
        self.assertEqual(
            [c["name"] for c in result.spec["unitContracts"][0]["cases"]],
            ["a", "b"])

    def test_two_sub_specs_naming_one_target_keep_both_case_sets(self):
        """Keyed at (target, case), not at target.

        Several sub-specs contributing cases for one handler is the normal
        shape for a split screen — it is why the block belongs in the
        sub-specs at all. Keying on `target` would call the second block
        "Defined differently" and drop its cases wholesale, which is the
        2/2/2/6 defect `branchContracts` had one level too shallow.
        """
        result = self.merge(
            {"unitContracts": {"target": "H", "cases": [{"name": "a"}]}},
            {"unitContracts": {"target": "H", "cases": [{"name": "b"}]}})
        self.assertFalse(result.has_conflicts, result.conflicts)
        blocks = result.spec["unitContracts"]
        self.assertEqual(len(blocks), 1, blocks)
        self.assertEqual([c["name"] for c in blocks[0]["cases"]], ["a", "b"])

    def test_one_case_defined_differently_in_two_sub_specs_conflicts(self):
        """Named at the case, so the message says which one to look at."""
        result = self.merge(
            {"unitContracts": {"target": "H",
                               "cases": [{"name": "a", "platforms": ["ios"]}]}},
            {"unitContracts": {"target": "H",
                               "cases": [{"name": "a", "platforms": ["android"]}]}})
        self.assertTrue(result.has_conflicts)
        self.assertIn("unitContracts[target=H].cases[name=a]",
                      result.conflicts[0].path)

    def test_an_identical_case_in_two_sub_specs_does_not_conflict(self):
        """Control for the arm above: same shape, same value, no complaint.

        Without it, "it conflicts" could mean the merger conflicts on every
        second block rather than on disagreement — which is the exact defect
        the granularity test guards, seen from the other side.
        """
        case = {"unitContracts": {"target": "H",
                                  "cases": [{"name": "a", "platforms": ["ios"]}]}}
        result = self.merge(case, json.loads(json.dumps(case)))
        self.assertFalse(result.has_conflicts, result.conflicts)
        self.assertEqual(len(result.spec["unitContracts"][0]["cases"]), 1)

    def test_a_block_the_merger_cannot_key_is_carried_not_dropped(self):
        """A misspelled `cases` must still reach the readers.

        `unitContracts` exists to stop a declaration going missing quietly,
        so the merger silently discarding a malformed block would reproduce
        the very defect one layer down — and `validate spec` / `unit-stubs`
        are the two that name the bad key, so they have to receive it.
        """
        result = self.merge({"unitContracts": {"target": "H", "caes": []}})
        self.assertEqual(result.spec["unitContracts"],
                         [{"target": "H", "caes": []}])

    def test_branch_contracts_and_task_cancellation_come_from_sub_specs(self):
        result = self.merge(
            {"branchContracts": {"methods": {"onLoad": {"branches": []}}},
             "task_cancellation": {"onLoad": "cancel on leave"}})
        self.assertIn("onLoad", result.spec["branchContracts"]["methods"])
        self.assertIn("onLoad", result.spec["task_cancellation"])

    def test_each_tabs_contracts_coexist_in_the_merge(self):
        """The reported defect. `conditions` and `methods` are FIXED
        sub-sections; the entries under them are the keyed individuals. The
        shallow merge read 'the second sub-spec also has conditions' as a
        conflict and dropped that tab's contracts wholesale — a four-tab
        parent whose tabs declared 2/2/2/6 conditions kept only the first
        tab's 2. These earlier fixtures put a method name directly under
        branchContracts, a shape the schema never allowed, so the tests
        pinned the shallow key on a spec that cannot occur."""
        result = self.merge(
            {"branchContracts": {
                "conditions": {"canEditA": {"witness": "a"}},
                "methods": {"onLoadA": {"branches": []}}}},
            {"branchContracts": {
                "conditions": {"canEditB": {"witness": "b"}},
                "methods": {"onLoadB": {"branches": []}}}})
        self.assertFalse(result.has_conflicts)
        merged = result.spec["branchContracts"]
        self.assertEqual(sorted(merged["conditions"]), ["canEditA", "canEditB"])
        self.assertEqual(sorted(merged["methods"]), ["onLoadA", "onLoadB"])

    def test_one_condition_declared_twice_differently_conflicts(self):
        """The consumer declared its acceptance for this fix in advance: its
        real corpus holds exactly one same-name condition whose wording
        differs between two tabs, and the fixed merge must surface THAT — a
        merge that comes back conflict-free is one that did not descend."""
        result = self.merge(
            {"branchContracts": {"conditions": {
                "manageAllowed": {"witness": "w", "meaning": "tab A"}}}},
            {"branchContracts": {"conditions": {
                "manageAllowed": {"witness": "w", "meaning": "tab B"}}}})
        self.assertTrue(result.has_conflicts)
        self.assertEqual(len(result.conflicts), 1)
        self.assertIn("branchContracts.conditions[name=manageAllowed]",
                      result.conflicts[0].path)

    def test_identical_contract_entries_do_not_conflict(self):
        m = {"branchContracts": {"conditions": {
            "canEdit": {"witness": "w", "meaning": "same"}}}}
        result = self.merge(m, json.loads(json.dumps(m)))
        self.assertFalse(result.has_conflicts)
        self.assertEqual(list(result.spec["branchContracts"]["conditions"]),
                         ["canEdit"])

    def test_error_handling_and_root_components_concatenate(self):
        result = self.merge(
            {"error_handling": [{"case": "offline"}],
             "structure": {"rootComponents": [{"id": "a"}]}},
            {"error_handling": [{"case": "timeout"}],
             "structure": {"rootComponents": [{"id": "b"}]}})
        self.assertEqual([e["case"] for e in result.spec["error_handling"]],
                         ["offline", "timeout"])
        self.assertEqual(
            [c["id"] for c in result.spec["structure"]["rootComponents"]],
            ["a", "b"])

    def test_a_parent_declaring_the_view_model_is_refused(self):
        """It is no longer read from the parent, so leaving it accepted would
        make it vanish silently — the failure this release removes, mirrored."""
        self.write("p/0.spec.json", {"type": "screen_spec",
                                     "metadata": {"name": "S", "description": "s"}})
        self.write("p.spec.json", {
            "type": "screen_parent_spec", "version": "1.0",
            "metadata": {"name": "P", "displayName": "P", "description": "P."},
            "subSpecs": [{"file": "p/0.spec.json", "name": "S"}],
            "dataFlow": {"viewModel": {"methods": [{"name": "onLoad"}]}}})
        with self.assertRaises(ParentSpecDeclarationError) as caught:
            ParentSpecMerger().merge_from_file(self.parent_path)
        self.assertIn("dataFlow.viewModel", str(caught.exception))

    def test_every_section_the_parent_is_refused_has_a_destination(self):
        """The property that was missing. Whatever the rule forbids in the
        parent, a sub-spec must be able to supply — otherwise the error tells
        the reader to do something impossible."""
        from jui_cli.core import shared_core
        rules = shared_core.load("parent_spec_rules")
        forbidden = {
            "branchContracts": {"branchContracts": {"k": {"branches": []}}},
            "task_cancellation": {"task_cancellation": {"k": "v"}},
            "error_handling": {"error_handling": [{"case": "c"}]},
            "structure.rootComponents": {"structure": {"rootComponents": [{"id": "a"}]}},
            "dataFlow.viewModel": {"dataFlow": {"viewModel": {"methods": [{"name": "m"}]}}},
            "dataFlow.repositories": {"dataFlow": {"repositories": [
                {"name": "R", "methods": [{"name": "m"}]}]}},
            "stateManagement.uiVariables": {"stateManagement": {
                "uiVariables": [{"name": "v", "type": "String"}]}},
        }
        for path, body in forbidden.items():
            parent = {"type": "screen_parent_spec", "version": "1.0",
                      "metadata": {"name": "P", "displayName": "P",
                                   "description": "P."},
                      "subSpecs": []}
            parent.update(json.loads(json.dumps(body)))
            self.assertIn(
                path, [p for p, _m in rules.dropped_parent_declarations(parent)],
                f"{path} is not actually refused — fixture is stale")

            merged = self.merge(body).spec
            section, _, key = path.partition(".")
            got = merged.get(section)
            if key:
                got = (got or {}).get(key)
            self.assertTrue(
                got,
                f"{path} is refused in the parent but no sub-spec can supply "
                f"it — the error message has no destination")


if __name__ == "__main__":
    unittest.main()


class TheRefusalsPromiseIsKept(unittest.TestCase):
    """Every section the refusal sends to a sub-spec must actually be built.

    The refusal is DEFAULT-DENY — any top-level key outside
    `PARENT_READS_TOP_LEVEL` — while construction is hand-written, one arm at
    a time. So adding a section switches the refusal on for free and leaves
    the promise unbacked, and the author is left with no legal home: the
    parent errors, the sub-spec is read by nobody.

    That has happened twice (`branchContracts` before v1.7.3, `unitContracts`
    before 1.8.28). This walks the declared vocabulary through a real merge so
    a third one has to fail here first.

    Proposed by the triage lane on the day the second occurrence shipped:
    "if the wording and the implementation can be tied together by one test,
    a pattern that has appeared twice does not appear a third time."
    """

    SAMPLES = {
        "structure": {"components": [{"id": "c1"}], "layout": {}},
        "stateManagement": {"uiVariables": [{"name": "v", "type": "Bool"}],
                            "eventHandlers": []},
        "dataFlow": {"viewModel": {"methods": [{"name": "m"}], "vars": []}},
        "branchContracts": {"methods": {"onLoad": {"branches": []}}},
        "unitContracts": {"target": "T", "cases": [{"name": "a"}]},
        "task_cancellation": {"onLoad": "cancel"},
        "error_handling": [{"case": "network"}],
        "userActions": [{"name": "tap"}],
        "transitions": [{"to": "next"}],
        "relatedFiles": ["a.swift"],
        "notes": "hello",
    }

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _merged_with(self, sections):
        sub = {"type": "screen_spec", "metadata": {"name": "S0", "description": "s"}}
        sub.update(sections)
        (self.root / "p").mkdir(exist_ok=True)
        (self.root / "p" / "0.spec.json").write_text(json.dumps(sub), encoding="utf-8")
        (self.root / "p.spec.json").write_text(json.dumps({
            "type": "screen_parent_spec", "version": "1.0",
            "metadata": {"name": "P", "displayName": "P", "description": "P."},
            "subSpecs": [{"file": "p/0.spec.json", "name": "S0"}]}), encoding="utf-8")
        return ParentSpecMerger().merge_from_file(self.root / "p.spec.json").spec

    def test_the_vocabulary_is_covered_by_a_sample(self):
        """Guards the arm below: an uncovered name would pass by not being run.

        Without this, adding a section to the vocabulary and forgetting the
        sample makes the suite greener rather than redder — the failure mode
        this whole class exists to stop, one level up.
        """
        rules = _rules()
        self.assertEqual(set(rules.MERGER_BUILDS_FROM_SUB_SPECS) - set(self.SAMPLES),
                         set(), "vocabulary entries with no sample to merge")

    def test_every_promised_section_survives_a_sub_spec(self):
        merged = self._merged_with(self.SAMPLES)
        missing = [k for k in _rules().MERGER_BUILDS_FROM_SUB_SPECS
                   if not merged.get(k)]
        self.assertEqual(missing, [], f"promised but not built: {missing}")

    def test_every_section_the_merger_builds_is_in_the_vocabulary(self):
        """The converse, and the arm the first draft was missing.

        Membership only ever gated the WORDING, so deleting a name left every
        other arm green while authors of that section started being told it is
        "NOT built from the sub-specs" — a false statement pointing them at
        the removal of a declaration that works. Set containment has two
        directions and one of them was unguarded.
        """
        merged = self._merged_with(self.SAMPLES)
        built = {k for k in self.SAMPLES if merged.get(k)}
        stray = sorted(built - set(_rules().MERGER_BUILDS_FROM_SUB_SPECS))
        self.assertEqual(stray, [], f"built but the message disowns them: {stray}")

    def test_a_section_outside_the_vocabulary_is_not_sent_to_a_sub_spec(self):
        """The message must not name a destination that drops the value.

        "Move it into a sub-spec" for something nobody builds is worse than
        the error it replaces: the author complies, the declaration vanishes
        quietly, and silence reads as acceptance.
        """
        rules = _rules()
        dropped = dict(rules.dropped_parent_declarations({
            "type": "screen_parent_spec", "somethingNobodyBuilds": [{"a": 1}]}))
        message = dropped["somethingNobodyBuilds"]
        self.assertIn("NOT built from", message)
        self.assertNotIn("Move the declaration into the sub-spec", message)

    def test_a_section_inside_the_vocabulary_still_names_the_sub_spec(self):
        """Positive control. Without it the arm above passes if the promise
        is never made at all, which would be a different defect wearing the
        same green."""
        rules = _rules()
        dropped = dict(rules.dropped_parent_declarations({
            "type": "screen_parent_spec",
            "branchContracts": {"methods": {"onLoad": {"branches": []}}}}))
        self.assertIn("Move the declaration into the sub-spec",
                      dropped["branchContracts"])


def _rules():
    from jui_cli.core import shared_core
    rules = shared_core.load("parent_spec_rules")
    assert rules is not None, "shared/core/parent_spec_rules.py did not load"
    return rules
