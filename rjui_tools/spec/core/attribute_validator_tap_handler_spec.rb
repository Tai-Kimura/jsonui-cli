# frozen_string_literal: true

require_relative '../../lib/core/attribute_validator'

# An empty or blank tap handler names no method (shared/core/
# tap_accessibility.rb `handler?`): no codegen emits a tap for it, so the
# validator says so — once, naming the attribute and the view, instead of
# "expects binding, got string" (which only `"onClick": ""` got, and `onclick`
# nothing). A blank element of an `onclick` array is named by index; it is
# not called. Ticket kjui-empty-onclick-emits-invalid-kotlin.
RSpec.describe 'attribute validator: empty and blank tap handlers' do
  let(:validator) { RjuiTools::Core::AttributeValidator.new(:all) }

  def tap_warnings(component, key)
    validator.validate(component).select { |m| m.include?("'#{key}'") || m.include?(".#{key}'") }
  end

  [['onClick', ''], ['onClick', '   '], ['onClick', '@{}'], ['onClick', '@{ }'],
   ['onclick', ''], ['onclick', '   '], ['onclick', []], ['onclick', ['', ' ']]].each do |key, value|
    it "warns once that #{key}: #{value.inspect} names no handler" do
      warnings = tap_warnings({ 'type' => 'Label', 'id' => 'title', 'text' => 'x', key => value }, key)
      expect(warnings.size).to eq(1), warnings.inspect
      expect(warnings.first).to include('id=title').and include("'#{key}'").and include('names no handler')
    end
  end

  it 'names the blank elements of an onclick array by index' do
    warnings = tap_warnings({ 'type' => 'Label', 'id' => 'title', 'text' => 'x', 'onclick' => ['', 'onOpen', ' '] }, 'onclick')
    expect(warnings.size).to eq(1), warnings.inspect
    expect(warnings.first).to include('id=title').and include('[0], [2]').and include('not called')
  end

  it 'names a blank range handler by its path' do
    component = { 'type' => 'Label', 'id' => 'terms', 'text' => 'Open terms',
                  'partialAttributes' => [{ 'range' => [0, 4], 'onclick' => '  ' }] }
    warnings = tap_warnings(component, 'onclick')
    expect(warnings.size).to eq(1), warnings.inspect
    expect(warnings.first).to include('id=terms').and include('partialAttributes[0].onclick').and include('names no handler')
  end

  # The control: a handler that names a method is not a tap warning.
  it 'says nothing of a real handler' do
    [['onClick', '@{onOpen}'], ['onclick', 'onOpen'], ['onclick', %w[onOpen onClose]]].each do |key, value|
      expect(tap_warnings({ 'type' => 'Label', 'id' => 'title', 'text' => 'x', key => value }, key)).to eq([]), key
    end
  end
end
