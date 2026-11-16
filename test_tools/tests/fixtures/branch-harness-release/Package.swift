// swift-tools-version: 6.2
import PackageDescription

// A consumer-shaped probe: deployment 17 (so a pre-26 runtime takes the
// isolated-deinit back-deploy path), MainActor default isolation in both
// the app and the test target.
let package = Package(
  name: "RetainProbe",
  platforms: [.iOS(.v17)],
  products: [.library(name: "ProbeApp", targets: ["ProbeApp"])],
  targets: [
    .target(name: "ProbeApp", swiftSettings: [.defaultIsolation(MainActor.self)]),
    .testTarget(name: "ProbeTests", dependencies: ["ProbeApp"],
                swiftSettings: [.defaultIsolation(MainActor.self)]),
  ]
)
