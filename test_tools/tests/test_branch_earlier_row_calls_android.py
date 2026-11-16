"""A call an earlier row's view model makes after its row ended, on Android —
the emitted runtime compiled whole and RUN against MockWebServer, two rows in
one process.

Measured before this (2026-09-26, the 1.8.121 runtime): a view model's
viewModelScope coroutine makes its call inside its own row (settle advances
the row's test dispatcher, delay included), so it never leaks. A real
thread, a timer or a Dispatchers.IO task outlives the row: sent to the URL
the harness factory was given, its call reached the row's closed server and
failed unseen inside the view model; sent to a process-wide base URL the
harness sets per row, it reached the NEXT row's server and counted there.

Now the ended row's server is kept through the next row: the late call is
answered 599 and named in the next row (earlier_row_call), and a row that
waited for that call by name says so in its red. The process-wide URL is
the limit, printed here: that call counts where it lands.

Pinned jars from a Gradle cache: in no CI job; run-suites.sh's Android leg
owns this file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests import _toolchain as tc

LATE_MS = 1000

_PROBE = '''package probe

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestDispatcher
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

class ProbeHarness(vm: Any, dispatcher: TestDispatcher) : BaseBranchHarness(vm, dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

/** A process-wide base URL, read per call (a harness sets it per row). */
object ApiConfig { @Volatile var baseUrl: String = "" }
/** An app-wide event other screens post; view models subscribe. */
object Bus { val listeners = java.util.concurrent.CopyOnWriteArrayList<() -> Unit>() }
val client = OkHttpClient()

class VM(private val builtWith: String, private val wiring: String) {
  private fun base() = if (wiring == "global") ApiConfig.baseUrl else builtWith
  fun post() {
    try {
      client.newCall(Request.Builder().url(base() + "orders")
        .post("{}".toRequestBody("application/json".toMediaType())).build()).execute().close()
    } catch (e: Exception) { println("LATE-FAILED " + e.javaClass.simpleName) }
  }
  fun act(kind: String) {
    when (kind) {
      "coroutine" -> CoroutineScope(Dispatchers.Main).launch { delay(LATE_MS); post() }   // viewModelScope's shape
      "thread" -> Thread { Thread.sleep(LATE_MS); post() }.apply { isDaemon = true }.start()
      "io" -> CoroutineScope(Dispatchers.IO).launch { delay(LATE_MS); post() }
      "subscription" -> Bus.listeners.add { post() }
    }
  }
}

fun main(args: Array<String>) {
  val kind = args[0]; val wiring = args[1]; val waits = args.getOrNull(2) == "waits"
  val routes = listOf(RouteSpec("createOrder", "POST", Regex("^/orders$"), "ok",
    mapOf("ok" to Triple(200, "{}", "application/json"))))
  val factory = { url: String, d: TestDispatcher -> ApiConfig.baseUrl = url; ProbeHarness(VM(url, wiring), d) }
  runBranchTest(routes, emptyMap(), factory) { h, rec ->
    rec.mark(); (h.vm as VM).act(kind); h.settle()
    println("ROW1 " + rec.countFor("createOrder"))
  }
  runBranchTest(routes, emptyMap(), factory) { h, rec ->
    rec.mark()
    if (kind == "subscription") Bus.listeners.forEach { it() }
    try {
      if (waits) settleUntilAnswered(h, rec, listOf("createOrder"))
      else { Thread.sleep(LATE_MS + 300L); h.settle() }
    } catch (e: AssertionError) { println("THROWN " + e.message) }
    println("ROW2 " + rec.countFor("createOrder"))
    reportEarlierRowCalls(BranchEndedRows.drain(), "row 2")
  }
  System.exit(0)
}
'''.replace("LATE_MS", f"{LATE_MS}L")


def _run(built, *args: str) -> tuple[dict, list[str]]:
    target_cp, out = built
    done = subprocess.run([str(tc.JAVA), "-cp", f"{out}:{target_cp}", "probe.ProbeKt", *args],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    got = dict(line.split(" ", 1) for line in done.stdout.strip().splitlines() if " " in line)
    said = [line for line in done.stderr.splitlines() if " earlier_row_call: " in line]
    return got, said


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return android.build(tmp_path_factory.mktemp("earlier-rows-android"), bt.KOTLIN_RUNTIME, _PROBE)


def test_a_viewmodelscope_coroutine_calls_inside_its_own_row(built):
    got, said = _run(built, "coroutine", "built-with")
    assert (got["ROW1"], got["ROW2"]) == ("1", "0") and said == [], (got, said)


@pytest.mark.parametrize("kind", ["thread", "io", "subscription"])
def test_a_call_to_the_ended_rows_server_is_named_not_lost(built, kind):
    """Before: a ConnectException inside the view model, nothing said."""
    got, said = _run(built, kind, "built-with")
    assert got["ROW2"] == "0" and "LATE-FAILED" not in got, got
    assert len(said) == 1 and said[0].startswith("jsonui-test branch test [row 2] earlier_row_call: 1 — POST /orders"), said


def test_a_row_waiting_for_the_call_names_the_one_its_ended_row_received(built):
    got, _ = _run(built, "thread", "built-with", "waits")
    assert got.get("THROWN", "").startswith("settle: the row expects createOrder, never called within EXPECT_MS"), got
    assert "not counted here, 1 call(s) an earlier row's view model made to its ended row's server: POST /orders" in got["THROWN"], got


def test_a_process_wide_base_url_sends_it_to_this_rows_server(built):
    """The limit, printed: which view model sent a request is not something
    the server can see, so a call sent to this row's URL counts here."""
    got, said = _run(built, "thread", "global")
    assert got["ROW2"] == "1" and said == [], (got, said)
