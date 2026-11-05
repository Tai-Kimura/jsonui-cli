# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require_relative '../../support/emitted_swift'

# A Label of height wrapContent keeps all its lines: a stack divides a finite
# height among its children, and a child whose text needs more than its share
# shrank with room left on the screen (ticket
# sjui-label-matchparent-wrapcontent-truncates-in-scroll). Under a node that
# bounds the height the text stays inside it, and `lines` limits it, as before.
# The Dynamic half is LabelHeightFit.swift; ConformanceHost's
# LabelHeightProbeUITests reads the frames on both.
RSpec.describe 'a wrapContent Label keeps its lines' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  include EmittedSwift

  let(:fixed) { '.fixedSize(horizontal: false, vertical: true)' }

  def label(extra = {})
    { 'type' => 'Label', 'text' => 'text', 'width' => 'matchParent', 'height' => 'wrapContent' }.merge(extra)
  end

  def view(extra = {}, *children)
    { 'type' => 'View', 'width' => 'matchParent', 'orientation' => 'vertical', 'child' => children }.merge(extra)
  end

  def emit(tree)
    SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_component(tree, 0).to_s
  end

  it 'in a wrapContent stack, as the reported screen has it' do
    expect(emit(view({ 'height' => 'wrapContent' }, label))).to include(fixed)
  end

  it 'with the height undeclared, or wrap_content' do
    expect(emit(view({}, label('height' => nil)))).to include(fixed)
    expect(emit(view({}, label('height' => 'wrap_content')))).to include(fixed)
  end

  it 'under matchParent: the screen is not a bound' do
    expect(emit(view({ 'height' => 'matchParent' }, label))).to include(fixed)
  end

  it 'with a weight across the row: the weight gives the width' do
    tree = { 'type' => 'View', 'orientation' => 'horizontal', 'width' => 'matchParent', 'height' => 'wrapContent',
             'child' => [label('width' => 0, 'weight' => 1), label('width' => 0, 'weight' => 1)] }
    expect(emit(tree)).to include(fixed)
  end

  it 'keeps `lines`: the limit is still in the emit, the height is the limit\'s' do
    code = emit(view({}, label('lines' => 2)))
    expect(code).to include('lineLimit: 2,')
    expect(code).to include(fixed)
  end

  context 'where it stays as it was' do
    it 'a declared height' do
      expect(emit(view({}, label('height' => 40)))).not_to include(fixed)
    end

    it 'a bound height' do
      expect(emit(view({}, label('height' => '@{h}')))).not_to include(fixed)
    end

    it 'matchParent' do
      expect(emit(view({}, label('height' => 'matchParent')))).not_to include(fixed)
    end

    it 'a vertical weight: the stack gives the height' do
      expect(emit(view({ 'height' => 'matchParent' }, label('height' => 0, 'weight' => 1), label('height' => 0, 'weight' => 1)))).not_to include(fixed)
    end

    it 'a maxHeight: the max bounds the text' do
      expect(emit(view({}, label('maxHeight' => 50)))).not_to include(fixed)
    end

    it 'under a declared height, however deep' do
      expect(emit(view({ 'height' => 56 }, label))).not_to include(fixed)
      expect(emit(view({ 'height' => 56 }, view({ 'height' => 'wrapContent' }, label)))).not_to include(fixed)
    end

    it 'under a maxHeight, a bound height, and a height only a responsive branch declares' do
      expect(emit(view({ 'maxHeight' => 56 }, label))).not_to include(fixed)
      expect(emit(view({ 'height' => '@{h}' }, label))).not_to include(fixed)
      expect(emit(view({ 'height' => 'wrapContent', 'responsive' => { 'minWidth:840' => { 'height' => 56 } } }, label))).not_to include(fixed)
    end

    it 'under a vertical weight' do
      tree = view({ 'height' => 'matchParent' }, view({ 'height' => 0, 'weight' => 1 }, label), view({ 'height' => 0, 'weight' => 2 }, label))
      expect(emit(tree)).not_to include(fixed)
    end
  end

  it 'what it emits type-checks', :swift_compile do
    expect(compilable_view(emit(view({ 'height' => 'wrapContent' }, label)))).to compile_as_swift
  end

  it 'one fixedSize where a min or max already gave one' do
    code = emit(view({}, label('width' => 'wrapContent', 'minHeight' => 40)))
    expect(code.scan('.fixedSize(').length).to eq(1)
  end

  it 'a vertical ScrollView ends a bound: its content has no height to run out of' do
    tree = view({ 'height' => 200 }, { 'type' => 'ScrollView', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => [label] })
    expect(emit(tree)).to include(fixed)
  end

  it 'a horizontal ScrollView does not: its height is the bound\'s' do
    tree = view({ 'height' => 200 }, { 'type' => 'ScrollView', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'horizontal', 'child' => [label('width' => 'wrapContent')] })
    expect(emit(tree)).not_to include(fixed)
  end
end
