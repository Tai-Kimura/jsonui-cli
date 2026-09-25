import XCTest
@testable import ProbeApp

private let routes = [RouteSpec(op: "ping", method: "GET", pattern: "^/ping$", defaultScenario: "ok",
                                scenarios: ["ok": (200, "{}", "application/json")])]

/// Two tests build a harness, the third posts the notification in its own
/// window and reports what its recorder saw. Classes run in name order.
nonisolated final class A_IsolatedDeinit: XCTestCase {
  @MainActor func test_1_build() { runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: IsolatedDeinitVM(tag: "iso-1")) }) { h, _ in h.settle() } }
  @MainActor func test_2_build() { runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: IsolatedDeinitVM(tag: "iso-2")) }) { h, _ in h.settle() } }
  @MainActor func test_3_post() {
    runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: IsolatedDeinitVM(tag: "iso-3")) }) { h, rec in
      h.settle()
      rec.mark()
      NotificationCenter.default.post(name: .probePing, object: nil)
      h.settle()
      print("PROBE iso ping=\(rec.countFor("ping")) unexpected=\(rec.unexpectedOps([])) alive=\(LiveVMs.alive.filter { $0.hasPrefix("iso") }) note=[\(branchRetainedHarnessesNote())]")
      reportRetainedHarnesses("probe A test_3")
    }
  }
}

nonisolated final class B_PlainDeinit: XCTestCase {
  @MainActor func test_1_build() { runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: PlainDeinitVM(tag: "plain-1")) }) { h, _ in h.settle() } }
  @MainActor func test_2_build() { runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: PlainDeinitVM(tag: "plain-2")) }) { h, _ in h.settle() } }
  @MainActor func test_3_post() {
    runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: PlainDeinitVM(tag: "plain-3")) }) { h, rec in
      h.settle()
      rec.mark()
      NotificationCenter.default.post(name: .probePing, object: nil)
      h.settle()
      print("PROBE plain ping=\(rec.countFor("ping")) unexpected=\(rec.unexpectedOps([])) alive=\(LiveVMs.alive.filter { $0.hasPrefix("plain") }) note=[\(branchRetainedHarnessesNote())]")
      reportRetainedHarnesses("probe B test_3")
    }
  }
}

/// The silent-green direction: this test's view model never calls /ping, the
/// row expects it (then api.ping: "called"), and an earlier test's view
/// model answers the notification inside this window.
nonisolated final class C_SilentGreen: XCTestCase {
  @MainActor func test_1_build() { runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: PlainDeinitVM(tag: "green-1")) }) { h, _ in h.settle() } }
  @MainActor func test_2_expects_ping() {
    runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: SilentVM(tag: "green-2")) }) { h, rec in
      h.settle()
      rec.mark()
      NotificationCenter.default.post(name: .probePing, object: nil)
      settleUntilAnswered(h, rec, ["ping"])
      print("PROBE silent own=0 ping=\(rec.countFor("ping")) calledRowHolds=\(rec.countFor("ping") > 0) alive=\(LiveVMs.alive.filter { $0.hasPrefix("green") })")
    }
  }
}
