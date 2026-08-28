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

    def test_branch_contracts_and_task_cancellation_come_from_sub_specs(self):
        result = self.merge({"branchContracts": {"onLoad": {"branches": []}},
                             "task_cancellation": {"onLoad": "cancel on leave"}})
        self.assertIn("onLoad", result.spec["branchContracts"])
        self.assertIn("onLoad", result.spec["task_cancellation"])

    def test_a_keyed_block_declared_twice_differently_conflicts(self):
        result = self.merge(
            {"branchContracts": {"onLoad": {"branches": ["a"]}}},
            {"branchContracts": {"onLoad": {"branches": ["b"]}}})
        self.assertTrue(result.has_conflicts)
        self.assertIn("branchContracts[onLoad]", result.conflicts[0].path)

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
