# frozen_string_literal: true

require 'core/attribute_types'
require 'swiftui/generators/swift_component_generator'
require 'swiftui/generators/adapter_generator'
require 'swiftui/generators/converter_generator'

# Every attribute type `sjui g converter` understands: the Swift component it
# scaffolds and the Dynamic adapter that reads the prop — a plain prop and a
# binding one (`@b`) — typechecked together with swiftc. The list is DERIVED
# from the shared vocabulary (lib/core/attribute_types.rb), plus `T?`, `[T]`,
# callbacks, and types outside it that the app declares (AppRow, Date).
#
# Until 1.8.121 the component and the adapter kept separate lists and did not
# agree: Float was Double in one and Float in the other, Color? was passed for
# a Color, `Integer` / `Boolean` became type names, and a binding attribute
# read a variable declared nowhere. Measured against the SwiftJsonUI module
# (iOS simulator, 2026-09-26). Ticket kjui-sjui-converter-attr-types-do-not-compile.
#
# The SwiftJsonUI API the adapter calls is stubbed with the library's own
# signatures (DynamicBindingHelper.resolveValue, DynamicHelpers.getColor(_:data:),
# DynamicEventHelper.extractPropertyName(from:), …); the module itself is not
# on this machine's test path.
RSpec.describe 'sjui g converter and every attribute type' do
  before do
    %i[info debug warn success error].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
  end

  def types
    vocab = JsonUIShared::AttributeTypes::VOCABULARY.keys.reject { |k| k.include?('_') } +
            JsonUIShared::AttributeTypes::ALIASES.keys
    vocab + ['String?', 'Int?', 'Long?', 'Bool?', 'Color?', 'CGFloat?', '[String]', '[Int]?', 'Array(Double)', 'Array', 'Object?',
             '(() -> Void)?', '((String) -> Void)?', 'Callback'] +
      # outside the vocabulary: model types the app declares, and one as a list
      %w[Date AppRow AppRow!! [AppRow] Array(AppSection)]
  end

  LIBRARY = <<~SWIFT
    struct DynamicComponent {
        var rawData: [String: Any] = [:]
        var childComponents: [DynamicComponent]? = nil
    }
    protocol CustomComponentAdapter {
        var componentType: String { get }
        func buildView(component: DynamicComponent, data: [String: Any], viewId: String?, parentOrientation: String?) -> AnyView
        var acceptsChildren: Bool { get }
    }
    extension CustomComponentAdapter { var acceptsChildren: Bool { true } }
    enum DynamicBindingHelper { static func resolveValue<T>(_ expression: Any?, data: [String: Any]) -> T? { nil } }
    enum DynamicHelpers { static func getColor(_ identifier: String?, data: [String: Any]) -> Color? { nil } }
    enum DynamicEventHelper { static func extractPropertyName(from value: String?) -> String? { nil } }
    enum DynamicModifierHelper {
        static func applyStandardModifiers(_ view: AnyView, component: DynamicComponent, data: [String: Any]) -> AnyView { view }
    }
    struct DynamicComponentBuilder: View {
        init(component: DynamicComponent, data: [String: Any], viewId: String?, isWeightedChild: Bool, parentOrientation: String?) {}
        var body: some View { EmptyView() }
    }
    final class CollectionDataSource {}
    // The app's own model types.
    struct AppRow { static var mock: AppRow { AppRow() } }
    struct AppSection {}
  SWIFT

  # The files as written, minus their imports and the DEBUG fence (so the
  # adapter and the preview are typechecked too).
  def plain(swift)
    swift.lines.reject { |l| l =~ /\A\s*(import |#if DEBUG|#endif)/ || l =~ %r{\A//} }.join
  end

  def sources
    types.each_with_index.map do |type, i|
      attributes = { 'v' => type }
      attributes['@b'] = type unless JsonUIShared::AttributeTypes.parse(type).kind == :callback
      options = { is_container: nil, attributes: attributes, command: 'spec' }
      plain(SjuiTools::SwiftUI::Generators::SwiftComponentGenerator.new("T#{i}", options).send(:swift_template)) +
        plain(SjuiTools::SwiftUI::Generators::AdapterGenerator.new("T#{i}", options).send(:adapter_template))
    end.join("\n")
  end

  it 'derives its list from the shared vocabulary' do
    expect(types).to include('long', 'cgfloat', 'integer', 'boolean', 'number', 'collectiondatasource')
  end

  it 'typechecks the component and its adapter for every type, plain and bound, and for the types outside the vocabulary' do
    expect(LIBRARY + sources).to compile_as_swift
  end

  # `String?` used to become `String??`. Asked of the component's property
  # declarations (`let v: …` alone on a line); an adapter's `??` is
  # nil-coalescing.
  it 'declares no double optional' do
    types.each do |type|
      swift = SjuiTools::SwiftUI::Generators::SwiftComponentGenerator
              .new('T', is_container: nil, attributes: { 'v' => type }, command: 'spec').send(:swift_template)
      expect(swift[/^\s*let v: (.*)$/, 1]).not_to end_with('??'), type
    end
  end

  # A type outside the vocabulary: `g converter` names it, in the one sentence
  # the three tools share (JsonUIShared::AttributeTypes.outside_warning — the
  # file is byte-identical in each tool, shared_core_mirror_spec), and says
  # nothing of the others. Not a refusal: faces declare their own model types,
  # and refusing stopped `jui g converter --all` on three of them (measured
  # 2026-09-26). The file writers are stubbed; nothing here is written.
  def warnings_for(attributes)
    said = []
    allow(SjuiTools::Core::Logger).to receive(:warn) { |m| said << m }
    %i[info debug success error].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
    generator = SjuiTools::SwiftUI::Generators::ConverterGenerator.new('Probe', attributes: attributes)
    %i[create_converter_file update_mappings_file generate_attribute_definition_file
       update_membership_exceptions_if_needed].each { |m| allow(generator).to receive(m) }
    allow_any_instance_of(SjuiTools::SwiftUI::Generators::SwiftComponentGenerator).to receive(:generate)
    allow_any_instance_of(SjuiTools::SwiftUI::Generators::AdapterGenerator).to receive(:generate)
    generator.generate
    said
  end

  it 'names the type once, in the shared sentence' do
    said = warnings_for('rows' => '[AppRow]', 'when' => 'Date', 'title' => 'String', 'count' => 'Long')
    expect(said).to eq([
      JsonUIShared::AttributeTypes.outside_warning('rows', '[AppRow]'),
      JsonUIShared::AttributeTypes.outside_warning('when', 'Date')
    ])
    expect(said.first).to include("'[AppRow]'").and include('List<Any?> in Kotlin')
  end

  it 'says nothing when every type is in the vocabulary' do
    expect(warnings_for('title' => 'String', 'tap' => '(() -> Void)?', 'rows' => '[Int]?')).to be_empty
  end
end
