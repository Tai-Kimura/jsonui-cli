# frozen_string_literal: true

require 'core/binding_validator'
require 'json'

# Consumes the shared canonical test vectors
# (shared/core/binding_vectors.json, renderer SSoT track 15) — every
# "kind": "validation" case must be reported by the sjui binding validator
# with the canonical rule id (binding_semantics.json validatorRules) present
# in the emitted message — as an error for expectError, as a warning (and not
# an error) for expectWarning.
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
      'invalid_array_in_params',
      # binding-mixed-text (warning), from jsonui-cli 1.9.6 — runtime
      # interpolation cases until then
      'text_flat_basic', 'text_multiple_bindings', 'text_adjacent_no_space',
      'text_repeated_binding', 'text_unresolved_mixed', 'text_default_in_mixed_text'
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
    rule = kase['expectError'] || kase['expectWarning']
    it "#{kase['id']} is reported with #{rule}" do
      validator = SjuiTools::Core::BindingValidator.new
      messages = validator.validate(build_layout(kase), 'vector.json')

      expect(messages.any? { |m| m.include?("[#{rule}]") }).to be(true),
        "expected a message containing '[#{rule}]', got: #{messages.inspect}"

      # The severity is binding_semantics.json validatorRules'.
      reported_as_error = validator.errors.any? { |m| m.include?("[#{rule}]") }
      expect(reported_as_error).to be(kase.key?('expectError')),
        "expected #{rule} as #{kase.key?('expectError') ? 'an ERROR' : 'a warning'}, got errors: #{validator.errors.inspect}"
    end
  end
end
