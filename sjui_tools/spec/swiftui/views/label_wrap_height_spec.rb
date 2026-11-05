# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require_relative '../../support/emitted_swift'

# A Label of height wrapContent inside a vertical ScrollView keeps all its
# lines: a stack divides a finite height among its children, and a child whose
# text needs more than its share shrank with room left on the screen (ticket
# sjui-label-matchparent-wrapcontent-truncates-in-scroll). Outside a ScrollView
# the text would push what is below it off a screen that does not scroll, so it
# stays as it was, as it does under a node that bounds the height, and `lines`
# limits it as before. The Dynamic half is LabelHeightFit.swift;
# ConformanceHost's LabelHeightProbeUITests reads the frames on both.
RSpec.describe 'a wrapContent Label in a ScrollView keeps its lines' do
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

  def scroll(*children, **extra)
    { 'type' => 'ScrollView', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical', 'child' => children }
      .merge(extra.transform_keys(&:to_s))
  end

  def emit(tree)
    SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_component(tree, 0).to_s
  end

  context 'inside a vertical ScrollView' do
    it 'in a wrapContent stack, as the reported screen has it' do
      expect(emit(scroll(view({ 'height' => 'wrapContent' }, label)))).to include(fixed)
    end

    it 'as the ScrollView\'s own child' do
      expect(emit(scroll(label))).to include(fixed)
    end

    it 'with the height undeclared, or wrap_content' do
      expect(emit(scroll(view({}, label('height' => nil))))).to include(fixed)
      expect(emit(scroll(view({}, label('height' => 'wrap_content'))))).to include(fixed)
    end

    it 'under matchParent: inside a ScrollView that is the content\'s height' do
      expect(emit(scroll(view({ 'height' => 'matchParent' }, label)))).to include(fixed)
    end

    it 'with a weight across the row: the weight gives the width' do
      row = { 'type' => 'View', 'orientation' => 'horizontal', 'width' => 'matchParent', 'height' => 'wrapContent',
              'child' => [label('width' => 0, 'weight' => 1), label('width' => 0, 'weight' => 1)] }
      expect(emit(scroll(row))).to include(fixed)
    end

    it 'keeps `lines`: the limit is still in the emit, the height is the limit\'s' do
      code = emit(scroll(view({}, label('lines' => 2))))
      expect(code).to include('lineLimit: 2,')
      expect(code).to include(fixed)
    end

    it 'whatever bounds the ScrollView: its content has no height to run out of' do
      expect(emit(view({ 'height' => 200 }, scroll(label)))).to include(fixed)
      expect(emit(scroll(view({ 'height' => 200 }, scroll(label))))).to include(fixed)
    end

    it 'what it emits type-checks', :swift_compile do
      stub = <<~SWIFT
        struct AdvancedKeyboardAvoidingScrollView<Content: View>: View {
            init(_ axes: Axis.Set, showsIndicators: Bool = true, @ViewBuilder content: () -> Content) { self.content = content() }
            let content: Content
            var body: some View { ScrollView { content } }
        }
      SWIFT
      expect(compilable_view(emit(scroll(view({ 'height' => 'wrapContent' }, label))), stubs: stub)).to compile_as_swift
    end

    it 'one fixedSize where a min or max already gave one' do
      code = emit(scroll(view({}, label('width' => 'wrapContent', 'minHeight' => 40))))
      expect(code.scan('.fixedSize(').length).to eq(1)
    end
  end

  context 'outside a ScrollView, where the text would push the rest off the screen' do
    it 'in a wrapContent stack' do
      expect(emit(view({ 'height' => 'wrapContent' }, label))).not_to include(fixed)
    end

    it 'under matchParent, the root of a screen that does not scroll' do
      expect(emit(view({ 'height' => 'matchParent' }, label))).not_to include(fixed)
    end

    it 'in a horizontal ScrollView: it is not the height that scrolls' do
      tree = { 'type' => 'ScrollView', 'width' => 'matchParent', 'height' => 100, 'orientation' => 'horizontal', 'child' => [label('width' => 'wrapContent')] }
      expect(emit(tree)).not_to include(fixed)
    end

    it 'after a ScrollView, as its sibling' do
      tree = view({ 'height' => 'matchParent' }, scroll(label('text' => 'in')), label('text' => 'after'))
      code = emit(tree)
      expect(code.scan(fixed).length).to eq(1)
    end
  end

  context 'inside a ScrollView, where it stays as it was' do
    it 'a declared height' do
      expect(emit(scroll(view({}, label('height' => 40))))).not_to include(fixed)
    end

    it 'a bound height' do
      expect(emit(scroll(view({}, label('height' => '@{h}'))))).not_to include(fixed)
    end

    it 'matchParent' do
      expect(emit(scroll(view({}, label('height' => 'matchParent'))))).not_to include(fixed)
    end

    it 'a vertical weight: the stack gives the height' do
      expect(emit(scroll(view({ 'height' => 'matchParent' }, label('height' => 0, 'weight' => 1), label('height' => 0, 'weight' => 1))))).not_to include(fixed)
    end

    it 'a maxHeight: the max bounds the text' do
      expect(emit(scroll(view({}, label('maxHeight' => 50))))).not_to include(fixed)
    end

    it 'under a declared height, however deep' do
      expect(emit(scroll(view({ 'height' => 56 }, label)))).not_to include(fixed)
      expect(emit(scroll(view({ 'height' => 56 }, view({ 'height' => 'wrapContent' }, label))))).not_to include(fixed)
    end

    it 'under a maxHeight, a bound height, and a height only a responsive branch declares' do
      expect(emit(scroll(view({ 'maxHeight' => 56 }, label)))).not_to include(fixed)
      expect(emit(scroll(view({ 'height' => '@{h}' }, label)))).not_to include(fixed)
      expect(emit(scroll(view({ 'height' => 'wrapContent', 'responsive' => { 'minWidth:840' => { 'height' => 56 } } }, label)))).not_to include(fixed)
    end

    it 'under a vertical weight' do
      expect(emit(scroll(view({ 'height' => 'matchParent' }, view({ 'height' => 0, 'weight' => 1 }, label), view({ 'height' => 0, 'weight' => 2 }, label))))).not_to include(fixed)
    end

    it 'in a horizontal ScrollView under a declared height' do
      tree = scroll(view({ 'height' => 200 }, { 'type' => 'ScrollView', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'horizontal', 'child' => [label('width' => 'wrapContent')] }))
      expect(emit(tree)).not_to include(fixed)
    end
  end
end
