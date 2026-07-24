# frozen_string_literal: true

require 'core/binding_validator'
require 'json'

# Consumes the shared canonical test vectors
# (shared/core/binding_vectors.json, renderer SSoT track 15) — every
# "kind": "validation" case must be rejected by the sjui binding validator
# with the canonical rule id (binding_semantics.json validatorRules) present
# in the emitted message.
RSpec.describe 'shared binding vectors — validation cases (sjui consumption)' do
  vectors_path = File.expand_path('../../../shared/core/binding_vectors.json', __dir__)
  vectors = JSON.parse(File.read(vectors_path))
  validation_cases = vectors['cases'].select { |c| c['kind'] == 'validation' }

  it 'exercises all validation vectors (none silently skipped)' do
    expect(validation_cases.map { |c| c['id'] }).to contain_exactly(
      'invalid_double_default',
      'invalid_twoway_dot_path',
      'invalid_twoway_bracket',
      'invalid_twoway_default',
      'invalid_twoway_negation',
      'invalid_negation_in_text',
      'invalid_negation_in_params',
      'invalid_default_in_params',
      'invalid_array_in_params'
    )
  end

  # Context mapping:
  #   text        => string attribute binding (Label.text; mixed or whole-value)
  #   twoWay      => two-way attribute (TextField.text, binding_direction: two-way)
  #   embedParams => Embed params leaf validation
  def build_layout(kase)
    case kase['context']
    when 'text'
      { 'type' => 'Label', 'id' => 'label', 'text' => kase['template'] || kase['expr'] }
    when 'twoWay'
      { 'type' => 'TextField', 'id' => 'field', 'text' => kase['expr'] }
    when 'embedParams'
      { 'type' => 'Embed', 'id' => 'embed', 'screen' => 'child_screen', 'params' => kase['params'] }
    else
      raise "unmapped vector context: #{kase['context']} (id=#{kase['id']})"
    end
  end

  validation_cases.each do |kase|
    it "#{kase['id']} is rejected with #{kase['expectError']}" do
      validator = SjuiTools::Core::BindingValidator.new
      messages = validator.validate(build_layout(kase), 'vector.json')

      expect(messages.any? { |m| m.include?(kase['expectError']) }).to be(true),
        "expected a message containing '#{kase['expectError']}', got: #{messages.inspect}"

      # All current validation vectors are error severity in
      # binding_semantics.json validatorRules
      expect(validator.errors.any? { |m| m.include?(kase['expectError']) }).to be(true),
        "expected an ERROR containing '#{kase['expectError']}', got errors: #{validator.errors.inspect}"
    end
  end
end
