"""The harness's `tearDown` on Android: the emitted Kotlin runtime compiled
whole and RUN on the JVM. The web and iOS faces, and why the member exists:
test_branch_harness_teardown.py.

Pinned jars from a Gradle cache: in no CI job; run-suites.sh's Android leg
owns this file.
"""
from __future__ import annotations

import subprocess

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests import _toolchain as tc


# ---------------------------------------------------------------- android --

_KT_PROBE = '''package probe

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.TestDispatcher

val log = mutableListOf<String>()

/** Overrides tearDown; throws from it when asked. */
class CleaningHarness(vm: Any, dispatcher: TestDispatcher, private val throwIt: Boolean) :
    BaseBranchHarness(vm, dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
  override fun tearDown() {
    log.add("tearDown")
    if (throwIt) throw IllegalStateException("from tearDown")
  }
}

/** A harness written before tearDown: it neither overrides nor declares it. */
class OlderHarness(vm: Any, dispatcher: TestDispatcher) : BaseBranchHarness(vm, dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

/** Implements the interface itself, without BaseBranchHarness and without tearDown. */
class OwnHarness(override val vm: Any) : BranchHarness {
  override fun readField(name: String): Any? = null
  override fun setState(state: Map<String, Any?>) {}
  override fun invoke(name: String, vararg args: Any?) {}
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
  override fun settle() {}
}

/** Main is set by runBranchTest and reset after it: on a plain JVM there is
 * no Main dispatcher, so touching it then throws. */
fun mainIsReset(): Boolean = try {
  Dispatchers.Main.isDispatchNeeded(kotlin.coroutines.EmptyCoroutineContext); false
} catch (e: IllegalStateException) { true }

fun main(args: Array<String>) {
  val case = args[0]
  val blockFails = case.contains("block-fails")
  val tearDownThrows = case.contains("teardown-throws")
  val factory: (String, TestDispatcher) -> BranchHarness = { _, d ->
    when {
      case.startsWith("factory-fails") -> { log.add("factory"); throw IllegalArgumentException("from the factory") }
      case.startsWith("older") -> OlderHarness(Any(), d)
      case.startsWith("own") -> OwnHarness(Any())
      else -> CleaningHarness(Any(), d, tearDownThrows)
    }
  }
  try {
    runBranchTest(emptyList(), emptyMap(), factory) { _, _ ->
      log.add("block")
      if (blockFails) throw AssertionError("from the block")
    }
    println("THROWN none")
  } catch (t: Throwable) {
    println("THROWN " + t.javaClass.simpleName + ": " + t.message)
    println("SUPPRESSED " + t.suppressed.joinToString(",") { it.javaClass.simpleName + ": " + it.message })
  }
  println("LOG " + log.joinToString(","))
  println("MAIN-RESET " + mainIsReset())
  System.exit(0)
}
'''


@pytest.fixture(scope="module")
def kt_built(tmp_path_factory):
    return android.build(tmp_path_factory.mktemp("teardown-android"), bt.KOTLIN_RUNTIME, _KT_PROBE)


def _kt_run(built, case: str) -> dict:
    target_cp, out = built
    done = subprocess.run([str(tc.JAVA), "-cp", f"{out}:{target_cp}", "probe.ProbeKt", case],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    return dict(line.split(" ", 1) for line in done.stdout.strip().splitlines() if " " in line)


def test_android_teardown_runs_after_a_block_that_passed(kt_built):
    got = _kt_run(kt_built, "passes")
    assert got["LOG"] == "block,tearDown" and got["THROWN"] == "none", got
    assert got["MAIN-RESET"] == "true", got


def test_android_teardown_runs_after_a_block_that_failed(kt_built):
    got = _kt_run(kt_built, "block-fails")
    assert got["LOG"] == "block,tearDown", got
    assert got["THROWN"] == "AssertionError: from the block" and got["SUPPRESSED"] == "", got


def test_android_a_failed_factory_gets_no_teardown_and_the_runtime_still_cleans_up(kt_built):
    got = _kt_run(kt_built, "factory-fails")
    assert got["LOG"] == "factory", got                       # no block, no tearDown
    assert got["THROWN"] == "IllegalArgumentException: from the factory", got
    assert got["MAIN-RESET"] == "true", got                   # resetMain ran


def test_android_a_failing_teardown_never_hides_the_blocks_failure(kt_built):
    """The block's failure is the one thrown; tearDown's is attached to it."""
    got = _kt_run(kt_built, "block-fails+teardown-throws")
    assert got["THROWN"] == "AssertionError: from the block", got
    assert got["SUPPRESSED"] == "IllegalStateException: from tearDown", got
    assert got["MAIN-RESET"] == "true", got


def test_android_a_failing_teardown_fails_a_block_that_passed(kt_built):
    got = _kt_run(kt_built, "passes+teardown-throws")
    assert got["THROWN"] == "IllegalStateException: from tearDown", got
    assert got["MAIN-RESET"] == "true", got                   # resetMain ran past it


@pytest.mark.parametrize("case", ["older", "own"])
def test_android_a_harness_without_teardown_compiles_and_runs(kt_built, case):
    got = _kt_run(kt_built, case)
    assert got["LOG"] == "block" and got["THROWN"] == "none", got


def test_android_control_a_plain_finally_lets_teardown_hide_the_block(tmp_path):
    """The control: the shape this replaced — tearDown called straight in
    the finally — throws tearDown's failure over the block's."""
    runtime = bt.KOTLIN_RUNTIME
    guarded = ("      try {\n        harness?.tearDown()\n      } catch (t: Throwable) {\n"
               "        val primary = failure\n        if (primary == null) throw t\n"
               "        primary.addSuppressed(t)\n      }\n")
    assert runtime.count(guarded) == 1
    built = android.build(tmp_path, runtime.replace(guarded, "      harness?.tearDown()\n"), _KT_PROBE)
    got = _kt_run(built, "block-fails+teardown-throws")
    assert got["THROWN"] == "IllegalStateException: from tearDown", got
