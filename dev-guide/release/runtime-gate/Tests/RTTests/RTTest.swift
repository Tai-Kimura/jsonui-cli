import XCTest

@MainActor final class FakeVM {
  func fetch() {
    let sem = DispatchSemaphore(value: 0)
    let session = URLSession(configuration: .ephemeral)
    session.dataTask(with: URL(string: "https://example.test/api/ping")!) { _,_,_ in sem.signal() }.resume()
    _ = sem.wait(timeout: .now() + 5)
  }
}
final class FakeHarness: BaseBranchHarness {
  override func invoke(_ name: String, args: [Any]) { (vm as! FakeVM).fetch() }
}
func createFakeHarness() -> BranchHarness { FakeHarness(vm: FakeVM()) }

nonisolated final class RTBranchesTest: XCTestCase {
  private let routes: [RouteSpec] = [
    RouteSpec(op: "ping", method: "GET", pattern: "^/api/ping$", defaultScenario: "default",
              scenarios: ["default": (200, "{\"ok\": true}", "application/json")])
  ]

  @MainActor func test_branch_1() {
    runBranchTest(routes: routes, overrides: [:], harnessFactory: createFakeHarness) { h, rec in
      h.invoke("ping", args: [])
      XCTAssertGreaterThan(rec.countFor("ping"), 0)

      // 🔑 消費側の crash が示す経路：他社 SDK が **背景スレッド**で session を作る。
      // swizzle 済みの @objc getter が背景から呼ばれる。
      let sem = DispatchSemaphore(value: 0)
      DispatchQueue.global(qos: .utility).async {
        let cfg = URLSessionConfiguration.ephemeral   // ← swizzle 済み
        _ = URLSession(configuration: cfg)
        sem.signal()
      }
      XCTAssertEqual(sem.wait(timeout: .now() + 5), .success, "background session creation hung")
    }
  }
}
