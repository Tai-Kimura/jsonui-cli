"""`settle` returns when the work the act started has landed — on Android, the
emitted runtime compiled whole and RUN against MockWebServer.

The same specimens as test_branch_settle_quiescence.py (a think chain of
20 ms x 50 links ending in an undeclared call; an expected op first sent at
EXPECT_MS / 5 and at 2 x EXPECT_MS), each with its control, on the runtime
compiled whole by tests/_android_runtime.py — pinned jars from a Gradle
cache, so this file is in no CI job and run-suites.sh's Android leg owns it.
Measured 2026-09-25 on 1.8.120's runtime (settle unchanged through 1.8.121's
rel, ee0bec5c) with the think chain below, the old fixed drain read 13/50
links and `unexpectedOps` [].
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests.test_branch_settle_quiescence import (
    CHAIN_GAP_MS, CHAIN_LINKS, FIRST_LATE_MS, FIRST_SOON_MS, _without_the_quiet,
)

# The view model's requests go through its own OkHttpClient, off the test
# dispatcher; its "thinking" is a sleep on its own thread.
_PROBE = '''package probe

import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import kotlinx.coroutines.test.TestDispatcher
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class ProbeHarness(val baseUrl: String, dispatcher: TestDispatcher) : BaseBranchHarness(Any(), dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun send(client: OkHttpClient, url: String, then: () -> Unit) {
  client.newCall(Request.Builder().url(url).build()).enqueue(object : Callback {
    override fun onFailure(call: Call, e: IOException) {}
    override fun onResponse(call: Call, response: Response) { response.close(); then() }
  })
}

fun main(args: Array<String>) {
  val ok = mapOf("ok" to Triple(200, "{}", "application/json"))
  val routes = listOf(
    RouteSpec("link", "GET", Regex("^/link$"), "ok", ok),
    RouteSpec("late", "GET", Regex("^/late$"), "ok", ok),
    RouteSpec("first", "GET", Regex("^/first$"), "ok", ok))
  runBranchTest(routes, emptyMap(), { url, d -> ProbeHarness(url, d) }) { h, rec ->
    rec.mark()
    val base = (h as ProbeHarness).baseUrl
    val client = OkHttpClient()
    val started = System.currentTimeMillis()
    if (args[0] == "chain") {
      // The view model: n links, each sent `gap` ms after the last response;
      // then a call no row declares.
      val n = args[1].toInt()
      val gap = args[2].toLong()
      val links = AtomicInteger(0)
      val done = AtomicBoolean(false)
      fun step(i: Int) {
        Thread {
          Thread.sleep(gap)
          send(client, base + (if (i < n) "link" else "late")) {
            if (i < n) { links.incrementAndGet(); step(i + 1) } else done.set(true)
          }
        }.apply { isDaemon = true }.start()
      }
      step(0)
      try { h.settle() } catch (e: AssertionError) { println("THROWN " + e.message) }
      println("LINKS " + links.get())
      println("DONE " + done.get())
      println("UNEXPECTED " + rec.unexpectedOps(setOf("link")))
    } else { // FIRST
      // The view model: one request, `after` ms after the act.
      val after = args[1].toLong()
      Thread { Thread.sleep(after); send(client, base + "first") {} }.apply { isDaemon = true }.start()
      try {
        if (args[2] == "expect") settleUntilAnswered(h, rec, listOf("first")) else h.settle()
      } catch (e: AssertionError) { println("THROWN " + e.message) }
      println("COUNT " + rec.countFor("first"))
    }
    println("WAITED " + (System.currentTimeMillis() - started))
    client.dispatcher.cancelAll()
    client.dispatcher.executorService.shutdown()
  }
  System.exit(0)
}
'''

_run = android.run


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return android.build(tmp_path_factory.mktemp("settle-android"), bt.KOTLIN_RUNTIME, _PROBE)


def test_android_settle_waits_out_a_chain_and_sees_the_late_call(built):
    got = _run(built, "chain", str(CHAIN_LINKS), str(CHAIN_GAP_MS))
    assert "THROWN" not in got, got
    assert (got["LINKS"], got["DONE"]) == (str(CHAIN_LINKS), "true"), got
    assert got["UNEXPECTED"] == "[late]", got


def test_android_control_without_the_quiet_the_chain_is_read_half_done(tmp_path):
    runtime = _without_the_quiet(bt.KOTLIN_RUNTIME, "  const val QUIET_MS = 400L\n",
                                 "  const val QUIET_MS = 0L\n")
    got = _run(android.build(tmp_path / "noquiet", runtime, _PROBE),
               "chain", str(CHAIN_LINKS), str(CHAIN_GAP_MS))
    assert int(got["LINKS"]) < CHAIN_LINKS and got["DONE"] == "false", got
    assert got["UNEXPECTED"] == "[]", got               # the vacuous green


def test_android_an_expected_op_sent_late_is_waited_for(built):
    got = _run(built, "first", str(FIRST_SOON_MS), "expect")
    assert "THROWN" not in got and got["COUNT"] == "1", got
    assert int(got["WAITED"]) >= FIRST_SOON_MS, got


def test_android_control_without_the_expectation_it_is_read_as_never_sent(built):
    got = _run(built, "first", str(FIRST_SOON_MS), "plain")
    assert "THROWN" not in got and got["COUNT"] == "0", got


def test_android_an_expected_op_never_sent_fails_by_name_at_expect_ms(built):
    got = _run(built, "first", str(FIRST_LATE_MS), "expect")
    assert got.get("THROWN", "").startswith(
        "settle: the row expects first, never called within EXPECT_MS (10000 ms) after the act, "
        "0 request(s) in flight (waited "), got
    assert got["COUNT"] == "0", got
    assert bt.EXPECT_MS <= int(got["WAITED"]) < FIRST_LATE_MS, got
