# frozen_string_literal: true

# Wrap emitted Swift in enough context for a compiler to read it.
#
# WHY THIS EXISTS
#
# 56 spec files assert emitted Swift. Three of them also hand it to a
# compiler. The other 53 assert the TEXT — `expect(code).to include('...')` —
# and a compiler has never read a line of it.
#
# That is not laziness, and a generic "also parse it" helper does not fix it.
# Measured: `-parse` accepts
#
#     data.collectionDataSource.getCellData(for: "ItemCell")
#
# with zero errors, because it is syntactically perfect Swift. Only
# `-typecheck` rejects it — and type-checking needs TYPES, which a fragment
# does not carry. Converter output is a View expression referencing
# `data.<prop>` and cell views that exist only in the consumer's project.
# That is why `compile_as_swift` sits in 3 files and not 56: the barrier is
# the stub universe, not the matcher.
#
# So this file makes the stub universe cheap to declare rather than pretending
# it is unnecessary. The spec says what its fragment needs; nothing is
# inferred, because guessing a type is how a compile arm goes green against a
# shape the real code never has.
#
# The defect this was written after: three specs pinned
# `data.collectionDataSource.getCellData(...)` for years. Nothing declares
# `collectionDataSource`, and `getCellData` has no implementation anywhere in
# SwiftJsonUI. Uncompilable Swift, behind three passing examples.
module EmittedSwift
  # A `CollectionDataSource` shaped like the library's, for fragments that
  # iterate one. Mirrors the real public surface
  # (SwiftJsonUI/Classes/SwiftUI/CollectionDataSource.swift): `sections`,
  # and per section an optional `cells` tuple of viewName + rows.
  COLLECTION_DATA_SOURCE_STUB = <<~SWIFT
    struct CollectionDataSection {
        var header: (viewName: String, data: [String: Any])?
        var cells: (viewName: String, data: [[String: Any]])?
        var footer: (viewName: String, data: [String: Any])?
    }
    struct CollectionDataSource {
        var sections: [CollectionDataSection] = []
    }
  SWIFT

  # `CollectionStackView`, the container the emitted collection code wraps
  # itself in. Mirrored from the real declaration
  # (SwiftJsonUI/Classes/SwiftUI/CollectionStackView.swift:60) INCLUDING the
  # defaulted parameters, because a stub that accepts more than the library
  # does lets a wrong argument list pass here and fail in a consumer build.
  COLLECTION_STACK_VIEW_STUB = <<~SWIFT
    enum CollectionStackMode { case lazy, eager, none }
    enum CollectionStackAxis { case vertical, horizontal }
    struct CollectionStackView<Content: View>: View {
        let content: () -> Content
        init(
            mode: CollectionStackMode,
            axis: CollectionStackAxis = .vertical,
            horizontalAlignment: HorizontalAlignment = .leading,
            verticalAlignment: VerticalAlignment = .center,
            spacing: CGFloat = 0,
            showsIndicators: Bool = true,
            scrollDisabled: Bool = false,
            defaultScrollAnchor: UnitPoint? = nil,
            insetLeading: CGFloat = 0,
            insetTrailing: CGFloat = 0,
            contentInsets: EdgeInsets? = nil,
            @ViewBuilder content: @escaping () -> Content
        ) { self.content = content }
        var body: some View { content() }
    }
  SWIFT

  # A generated cell view: `init(data: Any)` is the wrapper contract the
  # collection call sites use, and Equatable is required where they chain
  # `.equatable()`.
  def cell_view_stub(*names)
    names.map do |name|
      <<~SWIFT
        struct #{name}: View, Equatable {
            init(data: Any) {}
            static func == (lhs: Self, rhs: Self) -> Bool { true }
            var body: some View { Text("cell") }
        }
      SWIFT
    end.join("\n")
  end

  # Library surface that almost all emitted view code touches, so it is
  # included by default rather than repeated per spec. `.localized()` alone
  # appears 596 times in the generated corpus.
  #
  # Mirrored from the real declarations — `localized` is a METHOD with
  # defaulted parameters (Classes/Extensions/StringExtension.swift:12), not a
  # computed property. A stub that made it a property would accept
  # `"x".localized` and reject the `"x".localized()` the emitter actually
  # writes, which is a stub disagreeing with the library in the direction
  # that matters.
  #
  # `SwiftJsonUIConfiguration` is NOT here: swift_compiler.rb's own
  # `mock_types` already declares it, and a second declaration is a
  # redeclaration error rather than a harmless duplicate.
  LIBRARY_STUBS = <<~SWIFT
    extension String {
        func localized(tableName: String? = nil, bundle: Bundle? = nil,
                       value: String? = nil, comment: String = "") -> String { self }
    }
  SWIFT

  # Emitted Swift that belongs in a `var body: some View`.
  #
  # `data` is a list of Swift property DECLARATIONS, verbatim — not names and
  # not inferred types. A fragment reading `data.rows` needs the spec to say
  # what `rows` is, and saying it wrong is how the arm passes against a type
  # the generator never produces.
  def compilable_view(fragment, data: [], stubs: '')
    properties = Array(data).map { |d| "    #{d}" }.join("\n")
    indented = fragment.to_s.lines.map { |l| "        #{l}" }.join
    <<~SWIFT
      #{LIBRARY_STUBS}
      #{stubs}
      struct TestData {
      #{properties}
      }

      struct EmittedHost: View {
          let data = TestData()
          var body: some View {
      #{indented}
          }
      }
    SWIFT
  end

  # Emitted Swift that belongs inside a data model declaration.
  def compilable_data(fragment, stubs: '')
    <<~SWIFT
      #{LIBRARY_STUBS}
      #{stubs}
      struct TestData {
      #{fragment.to_s.lines.map { |l| "    #{l}" }.join}
      }
    SWIFT
  end
end

RSpec.configure { |config| config.include EmittedSwift }
