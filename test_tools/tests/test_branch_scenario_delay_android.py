"""A scenario's `delayMs` on Android — the emitted runtime compiled whole and
RUN against MockWebServer.

The same probe as test_branch_scenario_delay.py (A, then B 50 ms later; the
order they land in; `settle` waits for the delayed one; a control with the
wait taken out; the budget failing by name). The runtime needs the okhttp,
mockwebserver, coroutines-test and serialization jars, which only a Gradle
cache has and CI does not, so this file is in no CI job: run-suites.sh's
leg runs it with JSONUI_REQUIRE_ANDROID_JARS set, and there a missing jar
FAILS rather than skips. The versions are pinned and printed — not the
newest found — so a run says what it compiled against.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _toolchain as tc

DELAY_MS = 700
CACHE = Path.home() / ".gradle/caches/modules-2/files-2.1"
#: (group/artifact, version) the runtime is compiled and run against.
PINNED = [
    ("com.squareup.okhttp3/okhttp", "4.12.0"),
    ("com.squareup.okhttp3/mockwebserver", "4.12.0"),
    ("com.squareup.okio/okio-jvm", "3.6.0"),
    ("org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm", "1.10.2"),
    ("org.jetbrains.kotlinx/kotlinx-coroutines-test-jvm", "1.10.2"),
    ("org.jetbrains.kotlinx/kotlinx-serialization-core-jvm", "1.9.0"),
    ("org.jetbrains.kotlinx/kotlinx-serialization-json-jvm", "1.9.0"),
    ("junit/junit", "4.13.2"),
    ("org.hamcrest/hamcrest-core", "1.3"),
]


def _missing(why: str) -> None:
    if os.environ.get("CI") or os.environ.get("JSONUI_REQUIRE_ANDROID_JARS"):
        pytest.fail(why)
    pytest.skip(why)


def _classpath() -> tuple[str, str]:
    """(compiler classpath, target classpath) — the compiler and its stdlib
    from _toolchain, the rest pinned above."""
    jars = tc.kotlin_jars()
    if jars is None:
        _missing("no Kotlin compiler in the Gradle cache (kotlin-compiler-embeddable)")
    compiler_cp, target_cp = jars
    extra = []
    for artifact, version in PINNED:
        found = sorted(p for p in (CACHE / artifact / version).glob("*/*.jar")
                       if not p.name.endswith("-sources.jar"))
        if not found:
            _missing(f"{artifact}:{version} is not in the Gradle cache")
        extra.append(str(found[0]))
    return compiler_cp, ":".join([target_cp, *extra])


_PROBE = '''package probe

import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import kotlinx.coroutines.test.TestDispatcher
import java.io.IOException
import java.util.Collections

class ProbeHarness(val baseUrl: String, dispatcher: TestDispatcher) : BaseBranchHarness(Any(), dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun main(args: Array<String>) {
  val scen = mapOf("ok" to Triple(200, "{}", "application/json"),
                   "slow" to Triple(200, "{}", "application/json"))
  val routes = listOf(
    RouteSpec("a", "GET", Regex("^/a$"), "ok", scen, mapOf("slow" to %(delay)dL)),
    RouteSpec("b", "GET", Regex("^/b$"), "ok", scen, mapOf("slow" to %(delay)dL)))
  val chain = args.contains("chain")
  val overrides: Map<String, Any?> = args.filter { it != "chain" }.associateWith { "slow" }
  runBranchTest(routes, if (chain) mapOf("a" to "slow") else overrides,
                { url, d -> ProbeHarness(url, d) }) { h, _ ->
    val base = (h as ProbeHarness).baseUrl
    val landed = Collections.synchronizedList(mutableListOf<String>())
    val client = OkHttpClient()
    fun send(name: String, again: Boolean) {
      client.newCall(Request.Builder().url(base + name).build()).enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) { landed.add("!" + name) }
        override fun onResponse(call: Call, response: Response) {
          response.close(); landed.add(name)
          if (again) send(name, true)       // each arrival sends the next: a chain
        }
      })
    }
    val started = System.currentTimeMillis()
    if (chain) send("a", true) else for (name in listOf("a", "b")) { send(name, false); Thread.sleep(50) }
    try {
      h.settle()
      println("ORDER " + landed.toList().joinToString(","))
    } catch (e: AssertionError) {
      println("THROWN " + e.message)
    }
    println("WAITED " + (System.currentTimeMillis() - started))
    client.dispatcher.cancelAll()
    client.dispatcher.executorService.shutdown()
  }
  System.exit(0)
}
'''


def _build(work: Path, runtime: str) -> tuple[str, Path]:
    compiler_cp, target_cp = _classpath()
    work.mkdir(parents=True, exist_ok=True)
    # Rendered as the generator renders it (branch_tests: `KOTLIN_RUNTIME % {"package": …}`).
    (work / "Runtime.kt").write_text(runtime % {"package": "probe"}, encoding="utf-8")
    (work / "Probe.kt").write_text(_PROBE % {"delay": DELAY_MS}, encoding="utf-8")
    out = work / "out"
    build = subprocess.run(
        [str(tc.JAVA), "-cp", compiler_cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
         "-no-stdlib", "-cp", target_cp, "-d", str(out), str(work / "Runtime.kt"), str(work / "Probe.kt")],
        capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, f"emitted runtime did not compile:\n{(build.stdout + build.stderr)[-4000:]}"
    return target_cp, out


def _run(built: tuple[str, Path], *args: str) -> dict:
    target_cp, out = built
    run = subprocess.run([str(tc.JAVA), "-cp", f"{out}:{target_cp}", "probe.ProbeKt", *args],
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, (run.stdout + run.stderr)[-3000:]
    return dict(line.split(" ", 1) for line in run.stdout.strip().splitlines() if " " in line)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("delay-android"), bt.KOTLIN_RUNTIME)


@pytest.mark.parametrize("slow, order, waits", [
    ((), "a,b", False),
    (("a",), "b,a", True),
    (("b",), "a,b", True),
])
def test_android_the_delay_decides_the_order_and_settle_waits(built, slow, order, waits):
    got = _run(built, *slow)
    assert got.get("ORDER") == order, got
    assert (int(got["WAITED"]) >= DELAY_MS) is waits, got


def test_android_control_a_settle_that_does_not_wait_reads_before_the_arrival(tmp_path):
    runtime = bt.KOTLIN_RUNTIME
    wait = "      while (BranchDeliveries.pending(System.currentTimeMillis()) > 0) {\n"
    assert runtime.count(wait) == 1
    got = _run(_build(tmp_path / "nowait", runtime.replace(wait, "      return\n" + wait)), "a")
    assert got.get("ORDER") == "b", got


def test_android_past_the_budget_settle_fails_by_name(tmp_path):
    """A chain of delays longer than the budget, in a runtime whose cap is
    shortened to 100 ms (budget 1100 ms) so the arm takes a second."""
    runtime = bt.KOTLIN_RUNTIME
    cap = "  const val CAP_MS = 30000L\n"
    assert runtime.count(cap) == 1
    got = _run(_build(tmp_path / "chain", runtime.replace(cap, "  const val CAP_MS = 100L\n")), "chain")
    thrown = got.get("THROWN", "")
    assert thrown.startswith("settle: ") and "delayed response(s) still pending after waiting" in thrown, got
    waited = int(re.search(r"after waiting (\d+) ms", thrown).group(1))
    assert waited >= 1100 and "budget 1100 ms" in thrown, got
