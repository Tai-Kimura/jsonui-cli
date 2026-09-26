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
        for module, cls in (("library", "ATest"), ("library-dynamic", "BTest")):
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


if __name__ == "__main__":
    unittest.main()
