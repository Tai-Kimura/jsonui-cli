# frozen_string_literal: true

# Container accessibility-identifier exposure (static SwiftUI codegen).
#
# Plain SwiftUI stacks are not accessibility elements: a bare
# .accessibilityIdentifier on a container never surfaces for the container
# itself and gets pushed down onto the nearest descendant element,
# clobbering that child's own identifier when the subtree holds a single
# element. Mirrors the SwiftJsonUI Dynamic-mode fix in
# DynamicModifierHelper.applyAccessibilityId:
#   - id-bearing containers become explicit accessibility containers
#     (.accessibilityElement(children: .contain)) so XCUITest can find them
#   - an invisible 0.5pt anchor overlay guarantees >= 2 accessibility
#     children so SwiftUI never merges nested single-child containers
#     (the merge drops the inner container's identifier)
#   - statically invisible components emit no identifier at all
require 'swiftui/converter_factory'
require 'swiftui/views/label_converter'
require 'swiftui/views/view_converter'

RSpec.describe 'container accessibilityIdentifier emission' do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  def convert(component)
    factory.create_converter(component).convert
  end

  describe 'id-bearing containers' do
    %w[View SafeAreaView Scroll ScrollView Blur BlurView GradientView].each do |type|
      it "emits an explicit accessibility container for #{type}" do
        code = convert({ 'type' => type, 'id' => 'root',
                         'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

        expect(code).to include('.accessibilityElement(children: .contain)')
        expect(code).to include('.accessibilityIdentifier("root")')
        # container element must be established before the identifier
        expect(code.index('.accessibilityElement(children: .contain)'))
          .to be < code.index('.accessibilityIdentifier("root")')
      end

      it "emits the invisible anchor overlay for #{type}" do
        code = convert({ 'type' => type, 'id' => 'root',
                         'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

        expect(code).to include('.overlay(alignment: .topLeading) {')
        expect(code).to include('Color.clear')
        expect(code).to include('.frame(width: 0.5, height: 0.5)')
        expect(code).to include('.accessibilityElement(children: .ignore)')
      end
    end

    it 'keeps a nested single-child container id queryable (anchor on both levels)' do
      code = convert({
                       'type' => 'View', 'id' => 'root',
                       'child' => [
                         { 'type' => 'View', 'id' => 'inner',
                           'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] }
                       ]
                     })

      expect(code).to include('.accessibilityIdentifier("root")')
      expect(code).to include('.accessibilityIdentifier("inner")')
      expect(code.scan('.accessibilityElement(children: .contain)').length).to eq(2)
      # one anchor overlay per identified container
      expect(code.scan('.overlay(alignment: .topLeading) {').length).to eq(2)
    end

    it 'emits no accessibility modifiers for a container without id' do
      code = convert({ 'type' => 'View',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).not_to include('.accessibilityIdentifier(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
      expect(code).not_to include('.overlay(alignment: .topLeading) {')
    end
  end

  describe 'non-container components' do
    it 'keeps the bare identifier for Label (real accessibility element)' do
      code = convert({ 'type' => 'Label', 'id' => 'title', 'text' => 'Hi' })

      expect(code).to include('.accessibilityIdentifier("title")')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
      expect(code).not_to include('.overlay(alignment: .topLeading) {')
    end
  end

  describe 'statically invisible components' do
    # Explicit accessibility containers ignore an ancestor
    # .accessibilityHidden(true), so an invisible container must not create
    # one; the library VisibilityWrapper collapses + hides the subtree.
    it 'emits no identifier for an invisible container' do
      code = convert({ 'type' => 'View', 'id' => 'ghost', 'visibility' => 'invisible',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).not_to include('.accessibilityIdentifier(')
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end

    it 'emits no identifier for an invisible non-container' do
      code = convert({ 'type' => 'Label', 'id' => 'ghost', 'visibility' => 'invisible',
                       'text' => 'Hi' })

      expect(code).not_to include('.accessibilityIdentifier(')
    end

    it 'still emits the identifier when visibility is a binding' do
      code = convert({ 'type' => 'View', 'id' => 'root',
                       'visibility' => '@{rootVisibility}',
                       'child' => [{ 'type' => 'Label', 'text' => 'Hi' }] })

      expect(code).to include('.accessibilityIdentifier("root")')
      expect(code).to include('.accessibilityElement(children: .contain)')
    end
  end
end
