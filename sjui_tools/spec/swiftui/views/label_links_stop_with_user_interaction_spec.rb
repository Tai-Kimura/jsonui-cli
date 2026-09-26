# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# A Label's links — a partialAttributes range with an onClick, and a link
# `linkable` detects — stop with `userInteractionEnabled`: `false` on the
# Label or on a view around it stops them, a binding gates them (the tap rule,
# shared/core/tap_accessibility.rb; 4f ruling, jsonui-cli 1.9.0). sjui passes
# that to PartialAttributedText as `linksEnabled` (SwiftJsonUI sets no `.link`
# while it is false): `.allowsHitTesting` stops a touch, and a link is also an
# accessibility element of its own. canTap and enabled are the Label's own tap
# and state; the arms pin that they are not read for its links.
RSpec.describe 'sjui: a Label\'s links stop with userInteractionEnabled' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  convert = lambda do |comp|
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end

  linkable = ->(more = {}) { { 'type' => 'Label', 'id' => 'l', 'text' => 'See https://example.com', 'linkable' => true }.merge(more) }
  ranged = lambda do |more = {}|
    { 'type' => 'Label', 'id' => 'l', 'text' => 'Terms and Privacy',
      'partialAttributes' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }] }.merge(more)
  end
  inside = ->(flag, child) { { 'type' => 'View', 'id' => 'p', 'userInteractionEnabled' => flag, 'child' => [child] } }
  links = ->(code) { code[/linksEnabled: (.+?),?$/, 1] }

  { 'linkable' => linkable, 'partialAttributes' => ranged }.each do |shape, label|
    describe "a #{shape} Label" do
      it 'passes no linksEnabled with no flag (the control: the links operate)' do
        expect(links.call(convert.call(label.call))).to be_nil
      end

      it 'stops its links under its own false, and under a View\'s false' do
        expect(links.call(convert.call(label.call('userInteractionEnabled' => false)))).to eq('false')
        expect(links.call(convert.call(inside.call(false, label.call)))).to eq('false')
      end

      it 'gates its links on its own binding, on a View\'s, and on both, outermost first' do
        expect(links.call(convert.call(label.call('userInteractionEnabled' => '@{u}')))).to eq('(data.u ?? false)')
        expect(links.call(convert.call(inside.call('@{a}', label.call)))).to eq('(data.a ?? false)')
        expect(links.call(convert.call(inside.call('@{a}', label.call('userInteractionEnabled' => '@{u}')))))
          .to eq('(data.a ?? false) && (data.u ?? false)')
      end

      it 'reads neither canTap nor enabled for its links' do
        %w[canTap enabled].each do |key|
          expect(links.call(convert.call(label.call(key => false)))).to be_nil, key
          expect(links.call(convert.call(label.call(key => '@{x}')))).to be_nil, key
        end
      end
    end
  end

  it 'passes nothing for a Label with no links, under its own stop or a View\'s' do
    plain = { 'type' => 'Label', 'id' => 'l', 'text' => 'plain' }
    expect(convert.call(plain.merge('userInteractionEnabled' => false))).not_to include('linksEnabled')
    expect(convert.call(plain.merge('userInteractionEnabled' => '@{u}'))).not_to include('linksEnabled')
    expect(convert.call(inside.call(false, plain))).not_to include('linksEnabled')
  end

  # PartialAttributedText as spec/support/swift_compiler.rb mocks it, with
  # SwiftJsonUI's parameter order (linkable, then linksEnabled), so the
  # argument in a place the library does not take it does not type-check.
  it 'emits Swift that compiles' do
    trees = [
      linkable.call('userInteractionEnabled' => false), linkable.call('userInteractionEnabled' => '@{u}'),
      ranged.call('userInteractionEnabled' => false), inside.call('@{a}', ranged.call('userInteractionEnabled' => '@{u}'))
    ]
    trees.each do |tree|
      code = convert.call(tree)
      expect(code).to include('linksEnabled: ')
      data = ['var onTerms: (() -> Void)? = nil', 'var u: Bool? = nil', 'var a: Bool? = nil']
      expect(compilable_view(code, data: data)).to compile_as_swift
    end
  end
end
