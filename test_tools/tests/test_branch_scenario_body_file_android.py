"""A `bodyFile`'s text on the generated Android runtime — compiled whole and RUN against MockWebServer (ticket
2026-10-25-jsonui-test-mock-bodyfile-is-never-read).

The probe of test_branch_scenario_body_file.py: the literal `_kt_str` writes for the file's text is served, and the
bytes okhttp receives must be the file's. Its jars are in a Gradle cache and no CI image (tests/_android_runtime.py),
so this file is in no CI job; run-suites.sh's Android leg owns it.
"""
from __future__ import annotations

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests.test_mock_scenario_body_file import CSV


_KT_PROBE = '''package probe

import okhttp3.OkHttpClient
import okhttp3.Request
import kotlinx.coroutines.test.TestDispatcher

class ProbeHarness(val baseUrl: String, dispatcher: TestDispatcher) : BaseBranchHarness(Any(), dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun main() {
  val routes = listOf(RouteSpec("a", "GET", Regex("^/a$"), "csv",
                                mapOf("csv" to Triple(200, %s, "text/csv"))))
  runBranchTest(routes, emptyMap<String, Any?>(), { url, d -> ProbeHarness(url, d) }) { h, _ ->
    val client = OkHttpClient()
    client.newCall(Request.Builder().url((h as ProbeHarness).baseUrl + "a").build()).execute().use { r ->
      println("BODY " + r.body!!.bytes().joinToString("") { "%%02x".format(it) })
    }
    h.settle()
    client.dispatcher.executorService.shutdown()
  }
  System.exit(0)
}
'''


def test_android_runtime_sends_the_files_bytes(tmp_path):
    got = android.run(android.build(tmp_path, bt.KOTLIN_RUNTIME, _KT_PROBE % bt._kt_str(CSV.decode("utf-8"))))
    assert got == {"BODY": CSV.hex()}, got
