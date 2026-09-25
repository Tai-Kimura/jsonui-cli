"""A scenario's `delayMs` on Android — the emitted runtime compiled whole and
RUN against MockWebServer.

The same probe as test_branch_scenario_delay.py (A, then B 50 ms later; the
order they land in; `settle` waits for the delayed one; a control with the
wait taken out; the budget failing by name), on the runtime compiled whole
by tests/_android_runtime.py — pinned jars from a Gradle cache, so this file
is in no CI job and run-suites.sh's Android leg owns it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android

DELAY_MS = 700


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
    return android.build(work, runtime, _PROBE % {"delay": DELAY_MS})


_run = android.run


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
