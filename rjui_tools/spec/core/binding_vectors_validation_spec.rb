# frozen_string_literal: true

require 'json'
require_relative '../../lib/core/binding_validator'

# Consumes the shared canonical binding vectors
# (shared/core/binding_vectors.json, renderer SSoT track 15).
#
# The "kind": "validation" cases are authoring-time rejections: the rjui
# validator must flag each one with the canonical rule id declared in
# shared/core/binding_semantics.json validatorRules. Context mapping:
#   text / value -> attribute binding validation (Label.text)
#   twoWay       -> a two-way attribute (TextField.text)
#   embedParams  -> Embed params validation
RSpec.describe 'shared binding vectors — validation cases (rjui)' do
  vectors_path = File.expand_path('../../../shared/core/binding_vectors.json', __dir__)
  vectors = JSON.parse(File.read(vectors_path))
  validation_cases = vectors['cases'].select { |c| c['kind'] == 'validation' }

  # 9 errors, and from jsonui-cli 1.9.6 the six binding-mixed-text warnings
  # (runtime interpolation cases until then).
  it 'exercises all validation vectors (15 expected)' do
    expect(validation_cases.length).to eq(15)
  end

  validation_cases.each do |c|
    rule = c['expectError'] || c['expectWarning']
    it "#{c['id']} is reported with #{rule}" do
      component =
        case c['context']
        when 'text', 'value'
          { 'type' => 'Label', 'text' => c['template'] || c['expr'] }
        when 'twoWay'
          { 'type' => 'TextField', 'text' => c['expr'] }
        when 'embedParams'
          { 'type' => 'Embed', 'screen' => 'child_screen', 'params' => c['params'] }
        else
          raise "unmapped vector context: #{c['context']}"
        end

      validator = RjuiTools::Core::BindingValidator.new
      messages = validator.validate(component, "#{c['id']}.json")

      expect(messages.any? { |m| m.include?("[#{rule}]") }).to(
        be(true),
        "expected rule id #{rule} for vector #{c['id']}, got: #{messages.inspect}"
      )
      # The severity is binding_semantics.json validatorRules'.
      reported_as_error = validator.errors.any? { |m| m.include?("[#{rule}]") }
      expect(reported_as_error).to be(c.key?('expectError')),
                                   "expected #{c['id']} as #{c.key?('expectError') ? 'a hard error' : 'a warning'}"
    end
  end
end
