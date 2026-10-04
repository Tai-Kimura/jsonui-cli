"""The iOS tap-miss reproduction's two halves (.github/scripts/tap_repro.py).

`make` appends alternating, uniquely named copies of the two fixtures to a
manifest; `judge` counts and classifies the misses from a results file. The
workflow (ios-tap-repro.yml) needs a macOS runner; these halves are plain
Python and are checked here.
"""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "tap_repro.py"


def _load():
    spec = importlib.util.spec_from_file_location("tap_repro", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


T = _load()


class TapReproTest(unittest.TestCase):
    def test_make_alternates_unique_copies_on_the_real_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "conformance"
            src = REPO_ROOT / "conformance"
            (root / "fixtures").mkdir(parents=True)
            manifest = json.loads((src / "manifest.json").read_text())
            (root / "manifest.json").write_text(json.dumps(manifest))
            for fid, _ in T.SOURCES:
                f = next(x for x in manifest["fixtures"] if x["id"] == fid)
                for k in ("layout", "test"):
                    (root / f[k]).parent.mkdir(parents=True, exist_ok=True)
                    (root / f[k]).write_text((src / f[k]).read_text())
            self.assertEqual(T.make(root, 3), 0)
            ids = [f["id"] for f in json.loads((root / "manifest.json").read_text())["fixtures"]
                   if f["id"].startswith("Loop/")]
            self.assertEqual(ids, ["Loop/sw_001", "Loop/clip_001", "Loop/sw_002", "Loop/clip_002",
                                   "Loop/sw_003", "Loop/clip_003"])
            test = json.loads((root / "fixtures/Loop/clip_002.test.json").read_text())
            self.assertEqual(test["source"]["layout"], "fixtures/Loop/clip_002.layout.json")
            self.assertTrue((root / "fixtures/Loop/clip_002.layout.json").is_file())

    def judge_on(self, results, expected):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.json"
            p.write_text(json.dumps({"results": results}))
            out = io.StringIO()
            return T.judge(p, expected, out=out), out.getvalue()

    def test_judge_counts_and_classifies_each_miss(self):
        results = [
            {"id": "Loop/sw_001", "status": "pass", "detail": ""},
            {"id": "Loop/clip_001", "status": "error",
             "detail": "assert text(mirror): ... — [post-tap] ...; a second tap made it pass (touch not delivered)"},
            {"id": "Loop/sw_002", "status": "error",
             "detail": "assert text(mirror): ... — [post-tap] ...; a second tap did not either: ..."},
            {"id": "Loop/clip_002", "status": "error", "detail": "fixture marker did not appear within 15s"},
            {"id": "Label/text__static", "status": "error", "detail": "not a loop fixture"},
        ]
        rc, out = self.judge_on(results, 4)
        self.assertEqual(rc, 0)
        self.assertIn("[tap repro] 3 miss(es) in 4 loop fixture(s) (expected 4)", out)
        self.assertIn("'touch not delivered': 1", out)
        self.assertIn("'no handler answered': 1", out)
        self.assertIn("'no post-tap line': 1", out)
        self.assertEqual(out.count("::warning title=tap miss::"), 3)

    def test_a_short_run_is_not_no_miss(self):
        rc, out = self.judge_on([{"id": "Loop/sw_001", "status": "pass", "detail": ""}], 300)
        self.assertEqual(rc, 1)
        self.assertIn("0 miss(es) in 1 loop fixture(s) (expected 300)", out)


if __name__ == "__main__":
    unittest.main()
