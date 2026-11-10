"""conformance-mobile's `only`: a short run that draws the named fixtures for a baseline bake.

A fixture whose picture is new or changed made the full run red (no_baseline /
MOVED); its artifacts were baked and the whole run went again — two runs of an
hour and more. Dispatched with `only`, every face draws the named fixtures and
their controls and uploads them, the probes are off, and the report (the gate)
does not run (.github/scripts/conformance_only.py). Empty, the run is what it
always was.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "conformance-mobile.yml"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_the_schedule_raises_the_probes import EXPR, _eval, _on  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("conformance_only", ROOT / ".github" / "scripts" / "conformance_only.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


only = _load()

DRAWING = ("web", "ios", "ios-codegen", "android", "android-codegen")
MERGES = ("ios-merge", "ios-codegen-merge")
ONLY = ("workflow_dispatch", {"only": "common/a", "ios_probes": True, "image_probes": True, "android_probes": True})
FULL = ("workflow_dispatch", {"only": "", "ios_probes": True, "image_probes": True, "android_probes": True})


class Narrow(unittest.TestCase):
    MANIFEST = {"counts": {"fixtures": 4, "visual": 3}, "peerExpectedIdentical": [["common/a", "common/b"], ["common/b", "common/c"]],
                "fixtures": [{"id": "__control/View"}, {"id": "common/a", "control": "__control/View"},
                             {"id": "common/b", "control": "__control/View"}, {"id": "common/c", "control": None}]}

    def test_keeps_the_named_fixtures_and_their_controls_in_manifest_order(self):
        out = only.narrowed(self.MANIFEST, ["common/c", "common/a"])
        self.assertEqual([f["id"] for f in out["fixtures"]], ["__control/View", "common/a", "common/c"])
        self.assertEqual(out["counts"], {"fixtures": 3, "visual": 3})
        self.assertEqual(out["peerExpectedIdentical"], [])
        self.assertEqual(only.narrowed(self.MANIFEST, ["common/a", "common/b"])["peerExpectedIdentical"],
                         [["common/a", "common/b"]])

    def test_refuses_an_id_the_manifest_does_not_have(self):
        with self.assertRaises(only.Refused) as cm:
            only.narrowed(self.MANIFEST, ["common/a", "common/zz"])
        self.assertIn("common/zz", str(cm.exception))
        with self.assertRaises(only.Refused):
            only.parse_ids(" , ")
        self.assertEqual(only.parse_ids(" common/a ,common/b,"), ["common/a", "common/b"])

    def test_narrows_the_committed_manifest_in_place(self):
        manifest = json.loads((ROOT / "conformance" / "manifest.json").read_text(encoding="utf-8"))
        picked = [f for f in manifest["fixtures"] if f.get("control")][:2]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            kept = only.narrow(Path(d), ",".join(f["id"] for f in picked))
            want = {f["id"] for f in picked} | {f["control"] for f in picked}
            self.assertEqual(set(kept), want)
            self.assertEqual(json.loads((Path(d) / "manifest.json").read_text())["counts"]["fixtures"], len(want))


class TheWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.jobs = cls.wf["jobs"]

    def _cond(self, job):
        cond = self.jobs[job].get("if", "true")
        return EXPR.findall(cond)[0] if "${{" in cond else cond

    def test_the_input_is_declared_empty_by_default(self):
        spec = self.wf[True]["workflow_dispatch"]["inputs"]["only"] if True in self.wf else self.wf["on"]["workflow_dispatch"]["inputs"]["only"]
        self.assertEqual((spec["type"], spec["default"]), ("string", ""))

    def test_every_face_and_merge_narrows_right_after_its_checkout_and_only_when_named(self):
        for job in DRAWING + MERGES:
            steps = self.jobs[job]["steps"]
            self.assertEqual(steps[0].get("uses"), "actions/checkout@v4", job)
            narrow = steps[1]
            self.assertIn("conformance_only.py narrow conformance", narrow.get("run", ""), job)
            self.assertEqual(narrow["env"]["ONLY"], "${{ inputs.only }}", job)   # never interpolated into the script
            expr = EXPR.findall(narrow["if"])[0]
            self.assertTrue(_eval(expr, *ONLY), job)
            self.assertFalse(_eval(expr, *FULL), job)
            self.assertFalse(_eval(expr, "schedule", {}), job)

    def test_named_the_probes_are_off_and_the_gate_does_not_run(self):
        for where, text in self._strings(self.jobs):
            for expr in EXPR.findall(text):
                if any(f"inputs.{n}" in expr for n in ("ios_probes", "image_probes", "android_probes")):
                    self.assertFalse(_on(_eval(expr, *ONLY)), f"{where}: a probe raised under only — {expr.strip()}")
                    self.assertTrue(_on(_eval(expr, *FULL)), f"{where}: a full dispatch lost its probe")
        self.assertFalse(_eval(self._cond("report"), *ONLY))
        self.assertFalse(_eval(self._cond("android-library-tests"), *ONLY))
        for job in DRAWING + MERGES:
            self.assertTrue(_eval(self._cond(job), *ONLY), f"{job} does not run under only")
        self.assertTrue(_eval(self._cond("report"), *FULL))

    def test_named_the_ios_shards_run_the_suite_alone_and_the_merges_say_so(self):
        for job in ("ios", "ios-codegen"):
            suite = [s for s in self.jobs[job]["steps"] if "IOS_PROBES" in (s.get("env") or {})][0]
            self.assertEqual(suite["env"]["ONLY"], "${{ inputs.only }}")
            self.assertIn('if [ -n "$ONLY" ]; then\n  export CONFORMANCE_ONLY_TESTING="$(python3 .github/scripts/ios_shards.py suite)"',
                          suite["run"])
        for job in MERGES:
            merge = [s for s in self.jobs[job]["steps"] if "ios_shards.py merge" in s.get("run", "")][0]
            flag = re.search(r"\$\{\{(.*?)\}\}", merge["run"]).group(1)
            self.assertEqual(_eval(flag, *ONLY), "--fixtures-only", job)
            self.assertEqual(_eval(flag, *FULL), "", job)

    @staticmethod
    def _strings(node, where=()):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from TheWorkflow._strings(v, where + (str(k),))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from TheWorkflow._strings(v, where + (str(i),))
        elif isinstance(node, str):
            yield "/".join(where), node


if __name__ == "__main__":
    unittest.main()
