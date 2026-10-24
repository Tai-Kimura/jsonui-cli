"""A `bodyFile`'s text on the generated iOS and Android runtimes — RUN, not read (ticket
2026-10-25-jsonui-test-mock-bodyfile-is-never-read).

The generator embeds the file's text as the literal `_swift_str` / `_kt_str` writes; each probe serves that literal
and prints the bytes the app's client receives, which must be the file's bytes — a BOM, CRLFs and non-ASCII kept.
Needs swiftc and the Android jars: run with the compilers (run-suites.sh), as the header probes are.
"""
from __future__ import annotations

import subprocess

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests import _toolchain as tc
from tests.test_mock_scenario_body_file import CSV

_SWIFT_MAIN = """import Foundation
let routes = [
  RouteSpec(op: "a", method: "GET", pattern: "^/a$", defaultScenario: "csv",
            scenarios: ["csv": (200, %s, "text/csv")]),
]
let dummy = NSObject()
runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: dummy) }) { h, _ in
  let session = URLSession(configuration: .default)
  let done = DispatchSemaphore(value: 0)
  session.dataTask(with: URL(string: "https://example.test/a")!) { data, _, _ in
    print("BODY " + (data ?? Data()).map { String(format: "%%02x", $0) }.joined())
    done.signal()
  }.resume()
  while done.wait(timeout: .now()) == .timedOut { RunLoop.current.run(until: Date().addingTimeInterval(0.01)) }
  h.settle()
  session.invalidateAndCancel()
}
"""


def test_ios_runtime_sends_the_files_bytes(tmp_path):
    from tests.test_branch_scenario_delay import _SWIFT_SHIM
    tc.tool("swiftc")
    runtime = bt.SWIFT_RUNTIME
    assert runtime.count("\nimport XCTest\n") == 1
    (tmp_path / "shim.swift").write_text(_SWIFT_SHIM, encoding="utf-8")
    (tmp_path / "runtime.swift").write_text(runtime.replace("\nimport XCTest\n", "\n", 1), encoding="utf-8")
    (tmp_path / "main.swift").write_text(_SWIFT_MAIN % bt._swift_str(CSV.decode("utf-8")), encoding="utf-8")
    build = subprocess.run(["swiftc", "-Onone", "-o", str(tmp_path / "prog"), str(tmp_path / "shim.swift"),
                            str(tmp_path / "runtime.swift"), str(tmp_path / "main.swift")],
                           capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stderr[:4000]
    run = subprocess.run([str(tmp_path / "prog")], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[:3000]
    body = [line[5:] for line in run.stdout.splitlines() if line.startswith("BODY ")]
    assert body == [CSV.hex()], run.stdout


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
