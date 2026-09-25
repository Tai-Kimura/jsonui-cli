# frozen_string_literal: true

require 'core/attribute_types'
require 'swiftui/generators/converter_generator'

# `sjui g converter` names each attribute whose type is outside the shared
# vocabulary, in the one sentence the three tools share
# (JsonUIShared::AttributeTypes.outside_warning — the file is byte-identical
# in each tool, shared_core_mirror_spec), and says nothing of the others.
# Not a refusal: faces declare their own model types, and refusing stopped
# `jui g converter --all` on three of them (measured 2026-09-26). Ticket
# kjui-sjui-converter-attr-types-do-not-compile.
RSpec.describe 'sjui g converter and a type outside the vocabulary' do
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
