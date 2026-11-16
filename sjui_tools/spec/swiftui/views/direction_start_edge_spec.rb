# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A reversed stack starts at the edge its direction starts from: a
# `bottomToTop` column at the bottom, a `rightToLeft` row at the right (user
# ruling 2026-10-05, attribute_semantics stackDirection). The reversed
# children were laid from the top / left (`alignment: .topLeading`, no
# leading spacer), so the first child hung from the top of the column
# (ticket sjui-a-reversed-stack-starts-at-the-top-not-at-its-start-edge).
# SwiftJsonUI's Dynamic face reads the same rule (DirectionStart).
RSpec.describe 'a reversed stack starts at its start edge' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  let(:kids) do
    [{ 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40 },
     { 'type' => 'View', 'id' => 'b', 'width' => 40, 'height' => 40 }]
  end

  def convert(extra)
    SjuiTools::SwiftUI::Views::ViewConverter.new(
      { 'type' => 'View', 'width' => 200, 'height' => 200, 'child' => kids }.merge(extra)
    ).convert
  end

  def leading_spacer?(code)
    code.lines.map(&:strip).each_cons(2).any? { |a, b| a.end_with?('{') && a.include?('Stack(') && b == 'Spacer(minLength: 0)' }
  end

  it 'starts a bottomToTop column at the bottom' do
    code = convert('orientation' => 'vertical', 'direction' => 'bottomToTop')
    expect(code).to include('alignment: .bottomLeading)')
    expect(leading_spacer?(code)).to be(true)
  end

  it 'starts a rightToLeft row at the right' do
    code = convert('orientation' => 'horizontal', 'direction' => 'rightToLeft')
    expect(code).to include('alignment: .topTrailing)')
    expect(leading_spacer?(code)).to be(true)
  end

  it 'lets a gravity on the main axis decide' do
    code = convert('orientation' => 'vertical', 'direction' => 'bottomToTop', 'gravity' => 'top')
    expect(code).to include('alignment: .topLeading)')
    expect(leading_spacer?(code)).to be(false)
  end

  it 'emits Swift a compiler reads' do
    codes = [convert('orientation' => 'vertical', 'direction' => 'bottomToTop'),
             convert('orientation' => 'horizontal', 'direction' => 'rightToLeft')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end

  it 'leaves a direction across the orientation alone' do
    code = convert('orientation' => 'horizontal', 'direction' => 'bottomToTop')
    expect(code).to include('alignment: .topLeading)')
    expect(leading_spacer?(code)).to be(false)
  end
end
