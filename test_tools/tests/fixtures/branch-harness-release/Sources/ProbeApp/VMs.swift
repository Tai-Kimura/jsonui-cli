import Foundation

public extension Notification.Name {
  static let probePing = Notification.Name("probePing")
}

/// Every VM built, weakly: which ones are still alive.
public enum LiveVMs {
  nonisolated(unsafe) private static var all: [(String, WeakBox)] = []
  public static func add(_ tag: String, _ vm: AnyObject) { all.append((tag, WeakBox(vm))) }
  public static var alive: [String] { all.filter { $0.1.object != nil }.map { $0.0 } }
}
public final class WeakBox { public weak var object: AnyObject?; init(_ o: AnyObject) { object = o } }

/// A view model that answers a notification with a request — the shape of
/// an app-wide notification a screen observes.
public final class IsolatedDeinitVM {
  let session = URLSession(configuration: .default)
  var token: NSObjectProtocol?
  public init(tag: String) {
    LiveVMs.add(tag, self)
    token = NotificationCenter.default.addObserver(forName: .probePing, object: nil, queue: .main) { [weak self] _ in
      MainActor.assumeIsolated { self?.fetch() }
    }
  }
  func fetch() { session.dataTask(with: URL(string: "https://api.test/ping")!).resume() }
  isolated deinit {
    if let token { NotificationCenter.default.removeObserver(token) }
  }
}

/// The same, with a plain (nonisolated) deinit.
public final class PlainDeinitVM {
  let session = URLSession(configuration: .default)
  var token: NSObjectProtocol?
  public init(tag: String) {
    LiveVMs.add(tag, self)
    token = NotificationCenter.default.addObserver(forName: .probePing, object: nil, queue: .main) { [weak self] _ in
      MainActor.assumeIsolated { self?.fetch() }
    }
  }
  func fetch() { session.dataTask(with: URL(string: "https://api.test/ping")!).resume() }
}

/// A view model that never calls /ping: the later test's own screen.
public final class SilentVM {
  public init(tag: String) { LiveVMs.add(tag, self) }
}
