# frozen_string_literal: true

require 'core/attribute_validator'

# A partialAttributes range's `onclick` is the declared alias of its
# `onClick` (attribute_definitions.json, `items.properties.onClick.aliases`;
# 4f ruling, jsonui-cli 1.9.0). As for a node's own aliases: accepted on an L0
# layout, folded by the normalizer, so an L1 layout carries `onClick` only.
# onClick holds a binding or — the alias folded — a method name.
RSpec.describe 'a range\'s onclick, the alias of its onClick' do
  let(:validator) { SjuiTools::Core::AttributeValidator.new(:swiftui) }

  def warnings_for(range, normalized: false, type: 'Label')
    validator.normalized = normalized
    node = { 'type' => type, 'text' => 'Terms and more', 'partialAttributes' => [{ 'range' => 'Terms' }.merge(range)] }
    validator.validate(node, type).grep(/onclick|onClick/)
  end

  %w[Label Button].each do |type|
    it "#{type}: onclick is accepted on an L0 layout" do
      expect(warnings_for({ 'onclick' => 'onTerms' }, type: type)).to eq([])
    end

    it "#{type}: onClick holds a binding, or a method name" do
      expect(warnings_for({ 'onClick' => '@{onTerms}' }, type: type)).to eq([])
      expect(warnings_for({ 'onClick' => 'onTerms' }, type: type)).to eq([])
      expect(warnings_for({ 'onClick' => 'onTerms' }, normalized: true, type: type)).to eq([])
    end

    it "#{type}: onclick is not on an L1 layout (the normalizer folded it)" do
      expect(warnings_for({ 'onclick' => 'onTerms' }, normalized: true, type: type).join)
        .to include("Unknown property 'partialAttributes[0].onclick'")
    end
  end
end
