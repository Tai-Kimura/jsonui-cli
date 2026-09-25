import XCTest
@testable import ProbeApp

private let routes = [RouteSpec(op: "createOrder", method: "POST", pattern: "^/orders$", defaultScenario: "ok",
                                scenarios: ["ok": (200, "{}", "application/json")])]

/// Row 1 leaves a call behind (its view model posts 1 s after the act); row
/// 2's view model calls nothing, waits past that second, and reports — as a
/// generated row does — what it saw. Classes run in name order.
@MainActor private func rows(strongly: Bool, row1: String, row2: String, label: String) -> (() -> Void, () -> Void) {
  ({
    runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: LateVM()) }) { h, rec in
      rec.mark(); (h.vm as! LateVM).act(strongly: strongly); h.settle()
      reportOutlivedViewModels(row1)
    }
  }, {
    runBranchTest(routes: routes, overrides: [:], harnessFactory: { BaseBranchHarness(vm: LateVM()) }) { h, rec in
      rec.mark()
      RunLoop.main.run(until: Date().addingTimeInterval(1.3)); h.settle()
      print("PROBE \(label) row2=\(rec.countFor("createOrder"))")
      reportRetainedHarnesses(row2)
      reportOutlivedViewModels(row2)
    }
  })
}

nonisolated final class A_Strong: XCTestCase {
  @MainActor func test_1_row() { rows(strongly: true, row1: "strong row 1", row2: "strong row 2", label: "strong").0() }
  @MainActor func test_2_row() { rows(strongly: true, row1: "strong row 1", row2: "strong row 2", label: "strong").1() }
}

nonisolated final class B_Weak: XCTestCase {
  @MainActor func test_1_row() { rows(strongly: false, row1: "weak row 1", row2: "weak row 2", label: "weak").0() }
  @MainActor func test_2_row() { rows(strongly: false, row1: "weak row 1", row2: "weak row 2", label: "weak").1() }
}
