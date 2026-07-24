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

  it 'exercises all validation vectors (9 expected)' do
    expect(validation_cases.length).to eq(9)
  end

  validation_cases.each do |c|
    it "#{c['id']} is rejected with #{c['expectError']}" do
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

      expect(messages.any? { |m| m.include?("[#{c['expectError']}]") }).to(
        be(true),
        "expected rule id #{c['expectError']} for vector #{c['id']}, got: #{messages.inspect}"
      )
      expect(validator.has_errors?).to be(true), "expected #{c['id']} to be a hard error"
    end
  end
end
