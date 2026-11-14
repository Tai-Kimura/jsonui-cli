# frozen_string_literal: true

require 'core/control_accessibility'
require 'core/attribute_validator'
require 'json'

# accessibilitySelected (shared/core/control_accessibility.rb `selected` / `selected_misplaced?`; this tool's copy is
# pinned to it by shared_core_mirror_spec): the vectors are the table the three codegens and the SwiftJsonUI /
# KotlinJsonUI Dynamic runtimes run, and the validator all three tools run says where it tells a screen reader
# nothing. The declaration is attribute_definitions.json's: the rule's SELECTED_TYPES are the sections that declare it.
RSpec.describe JsonUIShared::ControlAccessibility do
  shared_core = File.expand_path('../../../shared/core', __dir__)
  vectors_path = File.join(shared_core, 'control_accessibility_vectors.json')
  definitions_path = File.join(shared_core, 'attribute_definitions.json')

  if File.exist?(vectors_path)
    vectors = JSON.parse(File.read(vectors_path))

    vectors['cases'].each do |c|
      it "selected: #{c['name']}" do
        expect(described_class.selected(c['layout'])).to eq(c['selected'])
        expect(described_class.selected_misplaced?(c['layout'])).to eq(c['warns'])
      end

      it "the validator warns as the vector says: #{c['name']}" do
        warnings = Array(SjuiTools::Core::AttributeValidator.new(:swiftui).validate(c['layout']))
        said = warnings.any? { |w| w.include?('accessibilitySelected tells a screen reader nothing here') }
        expect(said).to eq(c['warns'])
      end
    end
  end

  if File.exist?(definitions_path)
    it 'holds exactly the sections attribute_definitions.json declares accessibilitySelected on' do
      definitions = JSON.parse(File.read(definitions_path))
      declared = definitions.select { |k, v| !k.start_with?('_') && v.is_a?(Hash) && v.key?('accessibilitySelected') }.keys
      expect(described_class::SELECTED_TYPES.sort).to eq(declared.sort)
    end
  end
end
