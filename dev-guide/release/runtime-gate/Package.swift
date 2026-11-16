// swift-tools-version: 6.2
import PackageDescription

let package = Package(
  name: "RT",
  platforms: [.macOS(.v14)],
  targets: [
    .target(name: "Dummy"),
    .testTarget(
      name: "RTTests",
      dependencies: ["Dummy"],
      swiftSettings: [
        .swiftLanguageMode(.v6),
        .defaultIsolation(MainActor.self),
      ]
    ),
  ]
)
