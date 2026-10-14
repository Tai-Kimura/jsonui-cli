"""conformance-mobile runs the iOS jobs as shards (.github/scripts/ios_shards.py):
each shard a slice of the fixture suite and a share of the probe classes, put
back together by ios-merge / ios-codegen-merge. The merge is the gate that
nothing was dropped or run twice, so its refusals are tested one by one —
each negative case below is a run that would otherwise read as complete.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "ios_shards.py"
WEIGHTS = REPO_ROOT / ".github" / "scripts" / "ios_shard_weights.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "conformance-mobile.yml"


def _load():
    spec = importlib.util.spec_from_file_location("ios_shards", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shards = _load()


def _uitests(directory: Path, classes: dict[str, list[str]]) -> Path:
    d = directory / "UITests"
    (d / "Vendor").mkdir(parents=True)
    # A driver source under Vendor/ is not a test class of the host.
    (d / "Vendor" / "Driver.swift").write_text("final class Helper: XCTestCase { func testNot() {} }\n")
    for cls, tests in classes.items():
        body = "\n".join(f"    func {t}() throws {{}}" for t in tests)
        (d / f"{cls}.swift").write_text(
            f"import XCTest\n// class Fake: XCTestCase in a comment is not a class\n"
            f"final class {cls}: XCTestCase {{\n{body}\n}}\n")
    return d


class Declared(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_classes_and_tests_skipping_vendor_and_comments(self):
        d = _uitests(self.dir, {"ConformanceUITests": ["testConformanceSuite"], "AProbeUITests": ["testA", "testB"]})
        self.assertEqual(shards.declared_tests(d),
                         {"AProbeUITests": ["testA", "testB"], "ConformanceUITests": ["testConformanceSuite"]})

    def test_refuses_a_file_with_two_test_classes(self):
        d = _uitests(self.dir, {"ConformanceUITests": ["testConformanceSuite"]})
        (d / "Two.swift").write_text("final class A: XCTestCase { func testA() {} }\n"
                                     "final class B: XCTestCase { func testB() {} }\n")
        with self.assertRaises(shards.Refused):
            shards.declared_tests(d)


class Plan(unittest.TestCase):
    def test_every_class_in_exactly_one_share_deterministically(self):
        classes = [f"P{i}" for i in range(23)]
        weights = {c: float(i * 7 % 13 + 1) for i, c in enumerate(classes)}
        for n in (1, 2, 3, 4):
            a = shards.plan(classes, weights, n)
            self.assertEqual(a, shards.plan(list(reversed(classes)), weights, n), "input order must not matter")
            flat = [c for share in a for c in share]
            self.assertEqual(sorted(flat), sorted(classes))
            loads = [sum(weights[c] for c in share) for share in a]
            # LPT: no share heavier than the lightest by more than the heaviest class.
            self.assertLessEqual(max(loads) - min(loads), max(weights.values()), (n, loads))

    def test_a_class_without_a_weight_still_lands_in_a_share(self):
        a = shards.plan(["Known", "New"], {"Known": 10.0}, 2)
        self.assertEqual(sorted(c for s in a for c in s), ["Known", "New"])

    def test_the_suite_is_in_every_shard_and_the_shares_cover_the_sources(self):
        with tempfile.TemporaryDirectory() as t:
            probes = {f"P{i}UITests": [f"test{i}"] for i in range(9)}
            d = _uitests(Path(t), {"ConformanceUITests": ["testConformanceSuite"], **probes})
            w = Path(t) / "w.json"
            w.write_text(json.dumps({"ios": {c: float(i + 1) for i, c in enumerate(probes)}}))
            got = [shards.shard_classes(d, w, "ios", 3, k) for k in (1, 2, 3)]
            self.assertTrue(all(g[0] == "ConformanceUITests" for g in got))
            self.assertEqual(sorted(c for g in got for c in g[1:]), sorted(probes))
            with self.assertRaises(shards.Refused):
                shards.shard_classes(d, w, "ios", 3, 4)
            # A mode the table does not weigh still gets a plan that covers
            # every class (the merge proves coverage; a table can only cost
            # balance), with a note on stderr.
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                no_weights = [shards.shard_classes(d, w, "ios-codegen", 3, k) for k in (1, 2, 3)]
            self.assertEqual(sorted(c for g in no_weights for c in g[1:]), sorted(probes))
            self.assertIn("no weights for ios-codegen", err.getvalue())

    def test_the_suite_slices_are_each_shares_starting_load(self):
        classes = [f"P{i}" for i in range(12)]
        weights = {c: float(10 + i) for i, c in enumerate(classes)}
        # A head start the probes can make up (they weigh 186 in all).
        start = [100.0, 0.0]
        seeded = shards.plan(classes, weights, 2, start)
        loads = [start[k] + sum(weights[c] for c in seeded[k]) for k in (0, 1)]
        self.assertLessEqual(abs(loads[0] - loads[1]), max(weights.values()), loads)
        plain = shards.plan(classes, weights, 2)
        plain_loads = [start[k] + sum(weights[c] for c in plain[k]) for k in (0, 1)]
        self.assertGreater(abs(plain_loads[0] - plain_loads[1]), abs(loads[0] - loads[1]),
                           "the seeded plan must balance what the unseeded one does not")

    def test_slices_for_another_shard_count_change_nothing(self):
        classes = [f"P{i}" for i in range(9)]
        weights = {c: float(i + 1) for i, c in enumerate(classes)}
        self.assertEqual(shards.plan(classes, weights, 3, [100.0, 0.0]), shards.plan(classes, weights, 3))

    def test_a_missing_or_broken_table_never_stops_the_plan(self):
        with tempfile.TemporaryDirectory() as t:
            probes = {f"P{i}UITests": [f"test{i}"] for i in range(7)}
            d = _uitests(Path(t), {"ConformanceUITests": ["testConformanceSuite"], **probes})
            tables = {
                "missing": None,
                "not json": "{ nope",
                "a list": "[1, 2]",
                "no mode": json.dumps({"ios-codegen": {}}),
                "bad weights": json.dumps({"ios": {"P0UITests": "heavy", "P1UITests": -3, "P2UITests": 5}}),
                "slices not numbers": json.dumps({"ios": {}, "suite_slices": {"ios": ["a", "b"]}}),
                "slices for 3": json.dumps({"ios": {}, "suite_slices": {"ios": [1, 2, 3]}}),
                "slices not a map": json.dumps({"ios": {}, "suite_slices": [1, 2]}),
            }
            for name, body in tables.items():
                w = Path(t) / f"{name}.json"
                if body is not None:
                    w.write_text(body)
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    got = [shards.shard_classes(d, w, "ios", 2, k) for k in (1, 2)]
                self.assertEqual(sorted(c for g in got for c in g[1:]), sorted(probes), name)
                self.assertTrue(all(g[0] == "ConformanceUITests" for g in got), name)
                self.assertIn("note:", err.getvalue(), f"{name}: the fallback says why")

    def test_the_committed_table_has_one_slice_per_shard_of_the_workflow(self):
        n = int(yaml.safe_load(WORKFLOW.read_text())["env"]["IOS_SHARDS"])
        table = json.loads(WEIGHTS.read_text())
        for mode in ("ios", "ios-codegen"):
            slices = table["suite_slices"][mode]
            self.assertEqual(len(slices), n, mode)
            self.assertTrue(all(isinstance(x, (int, float)) and x > 0 for x in slices), mode)
            weights, start, notes = shards.load_table(WEIGHTS, mode, n)
            self.assertEqual(notes, [], mode)
            self.assertEqual(start, [float(x) for x in slices])

    def test_the_committed_weights_plan_the_real_modes(self):
        table = json.loads(WEIGHTS.read_text())
        for mode in ("ios", "ios-codegen"):
            self.assertGreater(len(table[mode]), 40, mode)
            self.assertNotIn("ConformanceUITests", table[mode], "the suite is split by fixture, not weighted")


MANIFEST_IDS = ["a", "b", "c", "d", "e", "x"]  # x: runnable nowhere (a skip of its own)


class Merge(unittest.TestCase):
    """Two shards of a run: fixtures a,b in shard 1, c,d,e in shard 2, x skipped
    by both for its own reason; probes P1 in shard 1, P2 in shard 2."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.uitests = _uitests(self.dir, {"ConformanceUITests": ["testConformanceSuite"],
                                           "P1UITests": ["testOne"], "P2UITests": ["testTwo", "testThree"]})
        self.manifest = self.dir / "manifest.json"
        self.manifest.write_text(json.dumps({"fixtures": [{"id": i} for i in MANIFEST_IDS]}))
        self.executed = {1: ["a", "b"], 2: ["c", "d", "e"]}
        self.probes = {1: [("P1UITests", "testOne")], 2: [("P2UITests", "testTwo"), ("P2UITests", "testThree")]}

    def tearDown(self):
        self.tmp.cleanup()

    def _shard(self, k, *, record=True, executed=None, results=None, shots=None, tests=None, suite=1,
               mode="ios", count=2):
        rel, art = shards.LAYOUT[mode]
        d = self.dir / f"{mode}-shard-{k}"
        executed = self.executed[k] if executed is None else executed
        rows = []
        for fid in MANIFEST_IDS:
            if fid in executed:
                rows.append({"id": fid, "status": "pass", "detail": "", "screenshot": f"artifacts/ios/{fid}.png"})
            elif fid == "x":
                rows.append({"id": fid, "status": "skipped", "detail": "not applicable to ios", "screenshot": None})
            else:
                rows.append({"id": fid, "status": "skipped", "detail": shards.ELSEWHERE, "screenshot": None})
        if results is not None:
            rows = results(rows)
        data = {"platform": "ios", "manifestHash": "h", "runner": {"name": "xcuitest", "version": "ios-26.2"},
                "webMarkers": {"timedOut": 0, "webFixturesRunnable": k}, "results": rows}
        if record:
            data["shard"] = {"index": k, "count": count, "runnable": 5, "executed": executed}
        (d / Path(rel).parent).mkdir(parents=True)
        (d / rel).write_text(json.dumps(data))
        (d / art).mkdir(parents=True)
        for name in (shots if shots is not None else [f"{fid}.png" for fid in executed]):
            (d / art / name).write_bytes(b"png")
        lines = [f"Test Case '-[ConformanceHostUITests.ConformanceUITests testConformanceSuite]' passed (10.0 seconds)."] * suite
        for cls, test in (self.probes[k] if tests is None else tests):
            lines.append(f"Test Case '-[ConformanceHostUITests.{cls} {test}]' passed (2.5 seconds).")
        (d / "xctests.txt").write_text("\n".join(lines) + "\n")
        return d

    def _merge(self, dirs, mode="ios"):
        return shards.merge(mode, 2, self.uitests, self.manifest, dirs, self.dir / "out")

    def _refused(self, dirs, needle, mode="ios"):
        with self.assertRaises(shards.Refused) as cm:
            self._merge(dirs, mode)
        self.assertIn(needle, str(cm.exception))

    def test_two_shards_make_one_run(self):
        summary = self._merge([self._shard(1), self._shard(2)])
        self.assertEqual(summary["fixtures"], 6)
        self.assertEqual(summary["statuses"], {"pass": 5, "skipped": 1})
        self.assertEqual(summary["probe_tests"], 3)
        out = json.loads((self.dir / "out" / "results" / "ios.results.json").read_text())
        self.assertNotIn("shard", out)
        self.assertEqual([r["id"] for r in out["results"]], MANIFEST_IDS)
        self.assertNotIn(shards.ELSEWHERE, {r["detail"] for r in out["results"]})
        self.assertEqual(out["webMarkers"], {"timedOut": 0, "webFixturesRunnable": 3})
        self.assertEqual(sorted(p.name for p in (self.dir / "out" / "artifacts" / "ios").iterdir()),
                         ["a.png", "b.png", "c.png", "d.png", "e.png"])
        record = (self.dir / "out" / "xctests.txt").read_text().splitlines()
        self.assertEqual(sum("testConformanceSuite" in l for l in record), 1)
        self.assertIn("testConformanceSuite]' passed (20.000 seconds).", "\n".join(record))
        self.assertEqual(len(record), 4)

    def test_codegen_layout(self):
        summary = self._merge([self._shard(1, mode="ios-codegen"), self._shard(2, mode="ios-codegen")], mode="ios-codegen")
        self.assertEqual(summary["fixtures"], 6)
        self.assertTrue((self.dir / "out" / "codegen" / "ios.results.json").is_file())

    def test_refuses_a_results_file_without_the_shard_record(self):
        self._refused([self._shard(1, record=False), self._shard(2)], "ignores CONFORMANCE_SHARD")

    def test_refuses_a_missing_shard(self):
        self._refused([self._shard(1)], "shard(s) [2] of 2")

    def test_refuses_a_shard_of_another_count(self):
        self._refused([self._shard(1), self._shard(2, count=3)], "the run has 2")

    def test_refuses_a_fixture_run_in_two_shards(self):
        self.executed[2] = ["b", "c", "d", "e"]
        self._refused([self._shard(1), self._shard(2)], "b: run in shard 1 and shard 2")

    def test_refuses_a_fixture_run_in_no_shard(self):
        self.executed[2] = ["c", "d"]
        self._refused([self._shard(1), self._shard(2)], "ran 4 fixtures between them")

    def test_refuses_shards_that_disagree_on_a_skip(self):
        def other_reason(rows):
            return [dict(r, detail="mode uikit not hosted") if r["id"] == "x" else r for r in rows]
        self._refused([self._shard(1), self._shard(2, results=other_reason)], "x: no shard ran it")

    def test_refuses_a_screenshot_written_by_two_shards(self):
        self._refused([self._shard(1, shots=["a.png", "b.png", "c.png"]), self._shard(2)], "written by")

    def test_refuses_a_probe_test_in_no_shard(self):
        self._refused([self._shard(1), self._shard(2, tests=[("P2UITests", "testTwo")])],
                      "P2UITests.testThree: in no shard's record")

    def test_refuses_a_probe_test_in_two_shards(self):
        self._refused([self._shard(1, tests=[("P1UITests", "testOne"), ("P2UITests", "testTwo")]), self._shard(2)],
                      "P2UITests.testTwo: in")

    def test_refuses_a_test_the_sources_do_not_declare(self):
        self._refused([self._shard(1, tests=[("P1UITests", "testOne"), ("P9UITests", "testGhost")]), self._shard(2)],
                      "which the sources do not declare")

    def test_refuses_a_shard_whose_suite_did_not_run(self):
        self._refused([self._shard(1, suite=0), self._shard(2)], "testConformanceSuite 0 times")

    def test_meta_must_agree(self):
        a, b = self._shard(1), self._shard(2)
        (a / "meta.json").write_text(json.dumps({"library_sha": "tree:1", "toolchain": "x"}))
        (b / "meta.json").write_text(json.dumps({"library_sha": "tree:1", "toolchain": "x"}))
        self.assertEqual(shards.meta([a, b]), {"library_sha": "tree:1", "toolchain": "x"})
        (b / "meta.json").write_text(json.dumps({"library_sha": "tree:2", "toolchain": "x"}))
        with self.assertRaises(shards.Refused):
            shards.meta([a, b])
        self.assertEqual(shards.meta([self.dir / "nowhere"]), {})

    def test_the_command_line_exits_1_naming_the_problem(self):
        a = self._shard(1)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            # main() raises Refused; the __main__ guard turns it into exit 1.
            try:
                shards.main(["merge", "--mode", "ios", "--shards", "2", "--uitests", str(self.uitests),
                             "--manifest", str(self.manifest), "--out", str(self.dir / "o"), str(a)])
            except shards.Refused as e:
                print(e, file=err)
                raise SystemExit(1)
        self.assertIn("shard(s) [2] of 2", err.getvalue())


class Workflow(unittest.TestCase):
    """The workflow and the script agree on the shard count and the names."""

    @classmethod
    def setUpClass(cls):
        cls.wf = yaml.safe_load(WORKFLOW.read_text())
        cls.text = WORKFLOW.read_text()

    def test_each_matrix_lists_one_to_ios_shards(self):
        n = int(self.wf["env"]["IOS_SHARDS"])
        for job in ("ios", "ios-codegen"):
            self.assertEqual(self.wf["jobs"][job]["strategy"]["matrix"]["shard"], list(range(1, n + 1)), job)
            self.assertFalse(self.wf["jobs"][job]["strategy"]["fail-fast"], job)

    def test_shards_upload_under_names_the_report_does_not_read(self):
        for job in ("ios", "ios-codegen"):
            names = [s.get("with", {}).get("name", "") for s in self.wf["jobs"][job]["steps"]]
            self.assertIn(f"{job}-shard-${{{{ matrix.shard }}}}", names)
            self.assertFalse([n for n in names if n.startswith("results-") or n.startswith("xctests-")], job)
        # ios-shard-* must not also download the codegen shards.
        self.assertFalse("ios-codegen-shard-1".startswith("ios-shard-"))

    def test_the_merges_produce_what_the_report_reads(self):
        for job in ("ios", "ios-codegen"):
            merge = self.wf["jobs"][f"{job}-merge"]
            self.assertEqual(merge["needs"], job)
            self.assertIn("always()", merge["if"])
            names = [s.get("with", {}).get("name", "") for s in merge["steps"]]
            self.assertIn(f"results-{job}", names)
            self.assertIn(f"xctests-{job}", names)
            run = "\n".join(s.get("run", "") for s in merge["steps"])
            self.assertIn(f"--mode {job} --shards \"$IOS_SHARDS\"", run)
        report = self.wf["jobs"]["report"]
        self.assertIn("ios-merge", report["needs"])
        self.assertIn("ios-codegen-merge", report["needs"])
        self.assertNotIn("needs.ios.outputs", self.text, "the shards have no single outputs; ios-merge carries them")

    def test_the_probe_switch_check_reads_the_merged_record(self):
        for job in ("ios", "ios-codegen"):
            shard_runs = "\n".join(s.get("run", "") for s in self.wf["jobs"][job]["steps"])
            self.assertNotIn("ios_probe_gates.py check", shard_runs,
                             "a shard's own record lacks the other shards' probes")
            merge_runs = "\n".join(s.get("run", "") for s in self.wf["jobs"][f"{job}-merge"]["steps"])
            self.assertIn("ios_probe_gates.py check merged/xctests.txt", merge_runs)


if __name__ == "__main__":
    unittest.main()
