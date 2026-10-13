"""The judge of conformance-mobile's android-library-tests job.

.github/scripts/kjui_device_tests.py reads KotlinJsonUI's connected-test XML
and turns it into the job's verdict. The job itself needs an emulator, so only
a hosted runner can run it, but the judge is plain Python and is checked here
on every push.

The class-ownership arm is a defect caught while this was written. The first
rule gave each @Test to the last `class` declared before it. On
KotlinJsonUI's own tests it named `Reading` and `FixedWindowInfo`, two
private helpers nested in the test classes. The class COUNT still matched the
files (22 / 13), so a count check would have passed a gate that reports two
real classes as "not run" on every green run.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "kjui_device_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("kjui_device_tests", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


K = _load()

TEST_CLASS = """\
package com.example

class {name} {{
    private class Helper(val x: Int)

    @Test
    fun one() {{}}

    @Test
    fun two() {{}}
}}
"""


def _suite(cases: str) -> str:
    # The XML declaration must be the first byte, so no dedent over the
    # inserted case lines.
    return (
        "<?xml version='1.0' encoding='UTF-8' ?>\n"
        '<testsuite name="com.example" tests="0" failures="0" errors="0" skipped="0">\n'
        '  <properties><property name="device" value="Pixel_Tablet(AVD) - 14" /></properties>\n'
        f"{cases}\n"
        "</testsuite>\n"
    )


class _Tree:
    """A fake KotlinJsonUI checkout: sources and connected results per module."""

    def __init__(self, root: Path):
        self.root = root
        for module in K.MODULES:
            (root / module / "src" / "androidTest" / "kotlin").mkdir(parents=True)

    def source(self, module: str, name: str, text: str) -> None:
        (self.root / module / "src" / "androidTest" / "kotlin" / f"{name}.kt").write_text(text)

    def results(self, module: str, cases: str) -> None:
        out = (self.root / module / "build" / "outputs" / "androidTest-results"
               / "connected" / "debug" / "Pixel_Tablet(AVD) - 14")
        out.mkdir(parents=True, exist_ok=True)
        (out / "TEST-Pixel_Tablet(AVD) - 14-_library-.xml").write_text(_suite(cases))


def _case(cls: str, name: str, body: str = "") -> str:
    return f'  <testcase name="{name}" classname="com.example.{cls}" time="0.1">{body}</testcase>'


class KjuiDeviceTestsJudge(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = _Tree(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _judge(self) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = K.judge(self.tree.root)
        return rc, out.getvalue() + err.getvalue()

    def _green_tree(self):
        for module, cls in (("library", "ATest"), ("library-dynamic", "BTest"), ("conformance-host", "HProbeTest")):
            self.tree.source(module, cls, TEST_CLASS.format(name=cls))
            self.tree.results(module, "\n".join([_case(cls, "one"), _case(cls, "two")]))

    # -- ownership ----------------------------------------------------------

    def test_a_nested_helper_above_the_tests_does_not_take_them(self):
        self.tree.source("library", "ATest", TEST_CLASS.format(name="ATest"))
        self.assertEqual({"ATest"}, K.test_classes(self.tree.root, "library"))

    def test_an_abstract_base_is_not_expected_in_the_results(self):
        self.tree.source("library", "Base", textwrap.dedent("""\
            abstract class Base {
                @Test
                fun shared() {}
            }
            """))
        self.assertEqual(set(), K.test_classes(self.tree.root, "library"))

    # -- verdicts -----------------------------------------------------------

    def test_all_cases_passing_is_green(self):
        self._green_tree()
        rc, text = self._judge()
        self.assertEqual(0, rc, text)
        self.assertIn("== library: 2 case(s) from 1 result file(s) — 2 passed, 0 failed, 0 skipped", text)

    def test_a_class_with_tests_and_no_results_is_red(self):
        # Positive control for "did not run": Gradle can exit 0 over this.
        self._green_tree()
        self.tree.source("library", "CTest", TEST_CLASS.format(name="CTest"))
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("NOT RUN  CTest", text)

    def test_a_failure_is_red_and_named(self):
        self._green_tree()
        self.tree.results("library", "\n".join([
            _case("ATest", "one"),
            _case("ATest", "two", "<failure>java.lang.AssertionError: expected 1\n\tat x</failure>"),
        ]))
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("FAILED   ATest.two: java.lang.AssertionError: expected 1", text)

    def test_an_error_is_red(self):
        self._green_tree()
        self.tree.results("library", "\n".join([
            _case("ATest", "one", '<error message="Process crashed." />'),
            _case("ATest", "two"),
        ]))
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("FAILED   ATest.one: Process crashed.", text)

    def test_a_skip_is_printed_by_name_and_is_not_red(self):
        # An opt-in probe left off is a skip. It is green, and it is named, so a
        # reader sees what did not judge.
        self._green_tree()
        self.tree.results("library", "\n".join([
            _case("ATest", "one", '<skipped message="set -e fooProbe 1" />'),
            _case("ATest", "two"),
        ]))
        rc, text = self._judge()
        self.assertEqual(0, rc, text)
        self.assertIn("1 passed, 0 failed, 1 skipped", text)
        self.assertIn("skipped  ATest.one: set -e fooProbe 1", text)

    def test_a_module_without_results_is_red(self):
        self._green_tree()
        self.tree.source("library-dynamic", "BTest", TEST_CLASS.format(name="BTest"))
        results = self.tree.root / "library-dynamic" / "build"
        for path in sorted(results.rglob("*.xml")):
            path.unlink()
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("library-dynamic: no results", text)

    # -- reach: every module and class with device tests is run or named ----

    def test_a_module_with_device_tests_that_nothing_runs_is_red(self):
        # The ticket's shape: tests in a module no invocation reaches.
        self._green_tree()
        (self.tree.root / "orphan-app" / "src" / "androidTest").mkdir(parents=True)
        (self.tree.root / "orphan-app" / "src" / "androidTest" / "OTest.kt").write_text(TEST_CLASS.format(name="OTest"))
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("orphan-app: has @Test in src/androidTest and no CI invocation runs it", text)

    def test_a_named_unreached_module_is_green_and_says_why(self):
        self._green_tree()
        (self.tree.root / "sample-app" / "src" / "androidTest").mkdir(parents=True)
        (self.tree.root / "sample-app" / "src" / "androidTest" / "STest.kt").write_text(TEST_CLASS.format(name="STest"))
        rc, text = self._judge()
        self.assertEqual(0, rc, text)
        self.assertIn("== sample-app: not run by this job — ViewModelDrivenImeTest measures", text)

    def test_a_module_without_device_tests_is_not_counted(self):
        # Control: an androidTest dir with no @Test is not a module to reach.
        self._green_tree()
        (self.tree.root / "empty-app" / "src" / "androidTest").mkdir(parents=True)
        (self.tree.root / "empty-app" / "src" / "androidTest" / "Helper.kt").write_text("class Helper")
        self.assertNotIn("empty-app", K.modules_with_device_tests(self.tree.root))
        self.assertEqual(0, self._judge()[0])

    def test_the_suite_class_another_job_runs_is_not_expected_here(self):
        self._green_tree()
        self.tree.source("conformance-host", "ConformanceSuiteTest", TEST_CLASS.format(name="ConformanceSuiteTest"))
        self.assertNotIn("ConformanceSuiteTest", K.test_classes(self.tree.root, "conformance-host"))
        rc, text = self._judge()
        self.assertEqual(0, rc, text)
        self.assertIn("ConformanceSuiteTest left out here — the android and android-codegen jobs run it", text)

    def test_a_host_probe_that_did_not_run_is_red(self):
        # The probes are what this change reaches: one with no case is NOT RUN.
        self._green_tree()
        self.tree.source("conformance-host", "TapRoleProbeTest", TEST_CLASS.format(name="TapRoleProbeTest"))
        rc, text = self._judge()
        self.assertEqual(1, rc, text)
        self.assertIn("NOT RUN  TapRoleProbeTest", text)

    def test_not_class_names_what_another_job_runs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, K.main(["not-class", str(self.tree.root)]))
        self.assertEqual("com.kotlinjsonui.conformance.ConformanceSuiteTest", out.getvalue().strip())

    # -- switches -----------------------------------------------------------

    def test_a_switch_is_an_argument_compared_to_one(self):
        self.tree.source("library-dynamic", "Probe", textwrap.dedent("""\
            class Probe {
                @Test
                fun p() {
                    val on = InstrumentationRegistry.getArguments().getString("fooProbe") == "1"
                    val other = InstrumentationRegistry.getArguments().getString("mode") == "fast"
                }
            }
            """))
        self.assertEqual(["fooProbe"], K.flags(self.tree.root))



class RaisedProbes(unittest.TestCase):
    """On a run that raised every switch (--probes-raised, ANDROID_PROBES=true),
    a skipped case is a probe that did not run and is red, unless RAISED_SKIPS
    declares it (ticket conformance-mobile-android-raised-probe-skip-stays-green).
    A run with the switches down is judged as before."""

    SKIP = '<skipped />'

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = _Tree(Path(self._tmp.name))
        for module, cls in (("library", "ATest"), ("library-dynamic", "BProbeTest"), ("conformance-host", "HProbeTest")):
            self.tree.source(module, cls, TEST_CLASS.format(name=cls))
            self.tree.results(module, "\n".join([_case(cls, "one"), _case(cls, "two")]))
        self._declared = dict(K.RAISED_SKIPS)

    def tearDown(self):
        K.RAISED_SKIPS.clear()
        K.RAISED_SKIPS.update(self._declared)
        self._tmp.cleanup()

    def _judge(self, raised: bool) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = K.judge(self.tree.root, probes_raised=raised)
        return rc, out.getvalue() + err.getvalue()

    def _skip_one(self, module="library-dynamic", cls="BProbeTest", name="two"):
        self.tree.results(module, "\n".join([_case(cls, "one"), _case(cls, name, self.SKIP)]))

    def test_nothing_skipped_is_green_raised_or_not(self):
        self.assertEqual(0, self._judge(True)[0])
        self.assertEqual(0, self._judge(False)[0])

    def test_a_raised_probe_that_skipped_is_red_and_named(self):
        self._skip_one()
        rc, text = self._judge(True)
        self.assertEqual(1, rc, text)
        self.assertIn("RAISED BUT SKIPPED  BProbeTest.two", text)
        self.assertIn("library-dynamic: 1 case(s) skipped although the probes were raised", text)

    def test_with_the_switches_down_a_skip_is_judged_as_before(self):
        self._skip_one()
        rc, text = self._judge(False)
        self.assertEqual(0, rc, text)
        self.assertNotIn("RAISED BUT SKIPPED", text)

    def test_a_declared_skip_is_green(self):
        self._skip_one()
        K.RAISED_SKIPS[("library-dynamic", "BProbeTest.two")] = {"why": "the platform lacks X", "when": "API < 36"}
        rc, text = self._judge(True)
        self.assertEqual(0, rc, text)

    def test_a_new_skip_beside_a_declared_one_is_red(self):
        self._skip_one()
        self.tree.results("conformance-host", "\n".join([_case("HProbeTest", "one", self.SKIP), _case("HProbeTest", "two")]))
        K.RAISED_SKIPS[("library-dynamic", "BProbeTest.two")] = {"why": "the platform lacks X", "when": "API < 36"}
        rc, text = self._judge(True)
        self.assertEqual(1, rc, text)
        self.assertIn("RAISED BUT SKIPPED  HProbeTest.one", text)
        self.assertNotIn("RAISED BUT SKIPPED  BProbeTest.two", text)

    def test_a_declaration_is_keyed_by_its_module(self):
        self._skip_one()
        K.RAISED_SKIPS[("library", "BProbeTest.two")] = {"why": "x", "when": "y"}
        self.assertEqual(1, self._judge(True)[0])

    def test_a_declaration_without_why_or_when_is_red(self):
        K.RAISED_SKIPS[("library", "ATest.one")] = {"why": "flaky", "when": ""}
        rc, text = self._judge(False)
        self.assertEqual(1, rc, text)
        self.assertIn("declares no why or no when", text)

    def test_the_committed_declarations_each_say_why_and_when(self):
        for key, entry in self._declared.items():
            self.assertTrue(entry.get("why", "").strip() and entry.get("when", "").strip(), key)

    def test_the_command_line_takes_the_flag_and_nothing_else(self):
        (self.tree.root / "library").mkdir(exist_ok=True)
        self._skip_one()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, K.main(["judge", str(self.tree.root), "--probes-raised"]))
            self.assertEqual(0, K.main(["judge", str(self.tree.root)]))
            self.assertEqual(2, K.main(["judge", str(self.tree.root), "--probes-rised"]))

    def test_the_runner_passes_the_flag_only_when_it_raised_the_switches(self):
        import subprocess
        script = (REPO_ROOT / ".github" / "scripts" / "kjui_device_tests.sh").read_text()
        start = script.index("args=()\njudge_args=()")
        block = script[start:script.index("\nfi\n", start) + 4]
        self.assertIn("judge_args=(--probes-raised)", block)
        self.assertIn('judge "$kjui" ${judge_args[@]+"${judge_args[@]}"}', script)
        probe = ('here=/nonexistent; kjui=/nonexistent\n'
                 'python3() { :; }\n' + block +
                 'echo "n=${#judge_args[@]} ${judge_args[*]-}"\n')
        for value, expect in (("true", "n=1 --probes-raised"), ("false", "n=0"), ("", "n=0")):
            env = {"PATH": "/usr/bin:/bin", "ANDROID_PROBES": value}
            got = subprocess.run(["/bin/bash", "-euc", probe], env=env, capture_output=True, text=True)
            self.assertEqual(expect, got.stdout.strip().splitlines()[-1], (value, got.stdout, got.stderr))


if __name__ == "__main__":
    unittest.main()
