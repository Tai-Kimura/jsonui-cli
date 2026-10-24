"""A scenario's `headers` on Android — the emitted runtime compiled whole and RUN against MockWebServer (ticket
2026-10-24-jsonui-test-mock-scenario-cannot-set-response-headers).

The probe of test_branch_scenario_headers.py: a 429 with `Retry-After` and `X-Request-ID`, read off the response by
okhttp, a delayed one too. Its jars are in a Gradle cache and no CI image (tests/_android_runtime.py), so this file
is in no CI job; run-suites.sh's Android leg owns it.
"""
from __future__ import annotations

from tests import _android_runtime as android
from jsonui_test_cli import branch_tests as bt

_PROBE = '''package probe

import okhttp3.OkHttpClient
import okhttp3.Request
import kotlinx.coroutines.test.TestDispatcher

class ProbeHarness(val baseUrl: String, dispatcher: TestDispatcher) : BaseBranchHarness(Any(), dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun main() {
  val scen = mapOf("limited" to Triple(429, "{}", "application/json"))
  val routes = listOf(
    RouteSpec("a", "GET", Regex("^/a$"), "limited", scen,
              headers = mapOf("limited" to mapOf("Retry-After" to "30", "X-Request-ID" to "r-1"))),
    RouteSpec("b", "GET", Regex("^/b$"), "limited", scen, mapOf("limited" to 50L),
              headers = mapOf("limited" to mapOf("Retry-After" to "5"))))
  runBranchTest(routes, emptyMap<String, Any?>(), { url, d -> ProbeHarness(url, d) }) { h, _ ->
    val base = (h as ProbeHarness).baseUrl
    val client = OkHttpClient()
    for (name in listOf("a", "b")) {
      client.newCall(Request.Builder().url(base + name).build()).execute().use { r ->
        println(name.uppercase() + " " + r.code + " " + (r.header("Retry-After") ?: "-") + " " +
                (r.header("X-Request-ID") ?: "-") + " " + (r.header("Content-Type") ?: "-"))
      }
    }
    h.settle()
    client.dispatcher.executorService.shutdown()
  }
  System.exit(0)
}
'''


def test_android_runtime_puts_the_headers_on_the_response(tmp_path):
    got = android.run(android.build(tmp_path, bt.KOTLIN_RUNTIME, _PROBE))
    # a delayed delivery carries its headers too
    assert got == {"A": "429 30 r-1 application/json", "B": "429 5 - application/json"}, got
