# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/views/collection_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A wrapContent container stops at its parent's size (SwiftJsonUI WrapCap,
# 10.29.6; user ruling 2026-10-05, attribute_semantics wrapContentCap). The
# emit puts `.wrapCap(width:height:)` on a container's wrapContent axes —
# after any fixedSize, as Dynamic applies it — and on no other node. A
# 168-high wrapContent box in a 100-high parent was 168 on iOS where Android
# stops it at 100 (ticket sjui-wrap-content-box-exceeds-a-sized-parent).
RSpec.describe 'the wrapContent cap in the emit' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  let(:kid) { { 'type' => 'View', 'id' => 'k', 'width' => 100, 'height' => 168 } }

  def convert(json)
    SjuiTools::SwiftUI::Views::ViewConverter.new(json).convert
  end

  it 'caps a container on its wrapContent axes' do
    code = convert('type' => 'View', 'orientation' => 'vertical', 'width' => 150, 'child' => [kid])
    expect(code).to include('.wrapCap(width: false, height: true)')
  end

  it 'caps both axes when neither is declared' do
    code = convert('type' => 'View', 'orientation' => 'vertical', 'child' => [kid])
    expect(code).to include('.wrapCap(width: true, height: true)')
  end

  it 'leaves a fixed-size container alone (ruling S)' do
    code = convert('type' => 'View', 'orientation' => 'vertical', 'width' => 150, 'height' => 168, 'child' => [kid])
    expect(code).not_to include('.wrapCap(')
  end

  it 'leaves a leaf alone' do
    code = convert('type' => 'View', 'width' => 150)
    expect(code).not_to include('.wrapCap(')
  end

  it 'leaves an axis a max or a weight sizes' do
    expect(convert('type' => 'View', 'width' => 150, 'maxHeight' => 300, 'child' => [kid])).not_to include('.wrapCap(')
    expect(convert('type' => 'View', 'width' => 150, 'weight' => 1, 'child' => [kid])).not_to include('.wrapCap(')
  end

  it 'emits Swift a compiler reads' do
    code = convert('type' => 'View', 'orientation' => 'vertical', 'width' => 150, 'child' => [kid])
    expect(compilable_view("VStack {\n#{code}\n}")).to compile_as_swift
  end
end
