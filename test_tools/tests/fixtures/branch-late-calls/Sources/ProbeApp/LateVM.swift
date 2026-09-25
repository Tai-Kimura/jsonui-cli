import Foundation

/// A view model whose call comes 1 s after its act, from a Task that holds
/// it strongly (the app's view model leaks past its screen) or weakly (the
/// usual `[weak self]`).
public final class LateVM {
  let session = URLSession(configuration: .default)
  public init() {}
  func post() {
    var request = URLRequest(url: URL(string: "https://api.test/orders")!)
    request.httpMethod = "POST"
    session.dataTask(with: request).resume()
  }
  public func act(strongly: Bool) {
    if strongly {
      Task { try? await Task.sleep(for: .seconds(1)); self.post() }
    } else {
      Task { [weak self] in try? await Task.sleep(for: .seconds(1)); self?.post() }
    }
  }
}
