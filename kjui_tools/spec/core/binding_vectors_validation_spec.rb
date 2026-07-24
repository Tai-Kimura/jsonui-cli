# frozen_string_literal: true

require 'json'
require 'core/binding_validator'

# Shared-vector consumption (renderer SSoT 15, Phase 15-4).
#
# Loads shared/core/binding_vectors.json and drives every "kind":"validation"
# case through the kjui BindingValidator, asserting the canonical rule id
# (expectError, from shared/core/binding_semantics.json validatorRules)
# appears in the emitted message.
#
# Context mapping (vector context => kjui layout construct):
#   text        => a string attribute binding (Text.text)
#   twoWay      => a two-way attribute binding (TextField.text,
#                  binding_direction: "two-way" in attribute_definitions)
#   embedParams => an Embed 'params' leaf
RSpec.describe 'shared binding vectors — validation cases' do
  vectors_path = File.expand_path('../../../shared/core/binding_vectors.json', __dir__)

  vectors = JSON.parse(File.read(vectors_path))
  validation_cases = vectors['cases'].select { |c| c['kind'] == 'validation' }

  it 'finds the 9 validation vectors in the shared asset' do
    expect(validation_cases.size).to eq(9)
  end

  def build_layout_for(kase)
    case kase['context']
    when 'text'
      {
        'type' => 'View',
        'data' => [
          { 'name' => 'a', 'class' => 'String' },
          { 'name' => 'flag', 'class' => 'Boolean' }
        ],
        'child' => [
          { 'type' => 'Text', 'text' => kase.fetch('template') }
        ]
      }
    when 'twoWay'
      {
        'type' => 'View',
        'data' => [
          { 'name' => 'text', 'class' => 'String' },
          { 'name' => 'flag', 'class' => 'Boolean' },
          { 'name' => 'user', 'class' => 'User' },
          { 'name' => 'items', 'class' => 'List<String>' }
        ],
        'child' => [
          { 'type' => 'TextField', 'text' => kase.fetch('expr') }
        ]
      }
    when 'embedParams'
      {
        'type' => 'View',
        'data' => [
          { 'name' => 'name', 'class' => 'String' },
          { 'name' => 'flag', 'class' => 'Boolean' },
          { 'name' => 'list', 'class' => 'List<Int>' }
        ],
        'child' => [
          {
            'type' => 'Embed',
            'id' => 'pane',
            'screen' => 'foo',
            'params' => kase.fetch('params')
          }
        ]
      }
    else
      raise "unmapped vector context: #{kase['context']} (#{kase['id']})"
    end
  end

  validation_cases.each do |kase|
    it "#{kase['id']} => #{kase['expectError']}" do
      validator = KjuiTools::Core::BindingValidator.new
      warnings = validator.validate(build_layout_for(kase), 'vectors.json')
      expect(warnings).to include(a_string_including(kase.fetch('expectError'))),
                          "expected #{kase['expectError']} for #{kase['id']}, got: #{warnings.inspect}"
    end
  end
end
