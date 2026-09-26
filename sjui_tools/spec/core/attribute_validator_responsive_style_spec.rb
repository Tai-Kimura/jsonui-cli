# frozen_string_literal: true

require 'core/attribute_validator'

# A `style` named inside a responsive override is applied by no path — sjui /
# kjui codegen, rjui and both Dynamic runtimes did not, jui's normalizer did
# (the hotloader drew what no build draws) — so every path names it in one
# sentence (4f's ruling, 1.9.0). The shared validator core, the same bytes in
# sjui, kjui and rjui.
RSpec.describe 'attribute validator: a style inside a responsive override' do
  let(:validator) { SjuiTools::Core::AttributeValidator.new(:swiftui) }
  let(:sentence) { "'style' inside a responsive override is not applied — put the attributes in the override" }

  def named(component)
    validator.validate(component).select { |m| m.include?("responsive override") }
  end

  it 'names it once, whatever class holds it' do
    node = { 'type' => 'View', 'id' => 'box', 'responsive' => { 'regular' => { 'style' => 'wide' }, 'landscape' => { 'style' => 'tall' } } }
    expect(named(node).size).to eq(1)
    expect(named(node).first).to include('id=box').and include(sentence)
  end

  it 'says nothing for an override of its own attributes, or a style on the node' do
    expect(named({ 'type' => 'View', 'responsive' => { 'regular' => { 'spacing' => 44 } } })).to be_empty
    expect(named({ 'type' => 'View', 'style' => 'wide', 'responsive' => { 'regular' => { 'spacing' => 44 } } })).to be_empty
    expect(named({ 'type' => 'View' })).to be_empty
  end
end
