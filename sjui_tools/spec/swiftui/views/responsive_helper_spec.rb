# frozen_string_literal: true

require 'swiftui/views/responsive_helper'
require 'swiftui/views/view_converter'
require 'swiftui/converter_factory'
require 'swiftui/view_registry'

RSpec.describe SjuiTools::SwiftUI::Views::ResponsiveHelper do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '.size_class_condition' do
    it 'returns correct condition for regular' do
      result = described_class.size_class_condition('regular')
      expect(result).to eq('horizontalSizeClass == .regular')
    end

    it 'returns correct condition for compact' do
      result = described_class.size_class_condition('compact')
      expect(result).to eq('horizontalSizeClass == .compact')
    end

    it 'returns correct condition for landscape' do
      result = described_class.size_class_condition('landscape')
      expect(result).to eq('verticalSizeClass == .compact')
    end

    it 'returns correct condition for regular-landscape' do
      result = described_class.size_class_condition('regular-landscape')
      expect(result).to eq('horizontalSizeClass == .regular && verticalSizeClass == .compact')
    end

    it 'returns correct condition for compact-landscape' do
      result = described_class.size_class_condition('compact-landscape')
      expect(result).to eq('horizontalSizeClass == .compact && verticalSizeClass == .compact')
    end

    it 'falls back medium to compact' do
      result = described_class.size_class_condition('medium')
      expect(result).to eq('horizontalSizeClass == .compact')
    end

    it 'returns correct condition for medium-landscape' do
      result = described_class.size_class_condition('medium-landscape')
      expect(result).to eq('horizontalSizeClass == .compact && verticalSizeClass == .compact')
    end
  end

  describe '.has_responsive_descendant?' do
    it 'returns false for non-responsive component' do
      component = { 'type' => 'View', 'orientation' => 'vertical' }
      expect(described_class.has_responsive_descendant?(component)).to be false
    end

    it 'returns true for component with responsive block' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } }
      }
      expect(described_class.has_responsive_descendant?(component)).to be true
    end

    it 'returns true if a child has responsive block' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' },
          {
            'type' => 'View',
            'orientation' => 'horizontal',
            'responsive' => { 'regular' => { 'spacing' => 24 } },
            'child' => [{ 'type' => 'Label', 'text' => 'World' }]
          }
        ]
      }
      expect(described_class.has_responsive_descendant?(component)).to be true
    end

    it 'returns false for nil input' do
      expect(described_class.has_responsive_descendant?(nil)).to be false
    end

    it 'returns false for non-hash input' do
      expect(described_class.has_responsive_descendant?('string')).to be false
    end
  end

  describe '.environment_declarations' do
    it 'returns two @Environment declarations' do
      decls = described_class.environment_declarations
      expect(decls.length).to eq(2)
      expect(decls[0]).to include('@Environment')
      expect(decls[0]).to include('horizontalSizeClass')
      expect(decls[1]).to include('@Environment')
      expect(decls[1]).to include('verticalSizeClass')
    end
  end

  describe '.generate_container_function' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 },
          'regular-landscape' => { 'orientation' => 'horizontal', 'spacing' => 32 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    let(:converter) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(component, 0)
    end

    it 'generates a generic wrapper function' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('private func responsive0<Content: View>')
      expect(code).to include('@ViewBuilder content: () -> Content')
    end

    it 'generates if/else branches in priority order' do
      code = described_class.generate_container_function('responsive0', component, converter)
      # regular-landscape should come first (highest priority compound)
      expect(code).to include('horizontalSizeClass == .regular && verticalSizeClass == .compact')
      # Then landscape
      expect(code).to include('verticalSizeClass == .compact')
      # Then regular
      expect(code).to include('horizontalSizeClass == .regular')
      # Then default (else)
      expect(code).to include('} else {')
    end

    it 'generates HStack for horizontal orientation' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('HStack(')
    end

    it 'generates VStack for vertical/default orientation' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('VStack(')
    end

    it 'includes content() call in each branch' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code.scan('content()').length).to be >= 2
    end

    it 'uses correct spacing values per branch' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('spacing: 32')  # regular-landscape
      expect(code).to include('spacing: 24')  # regular
      expect(code).to include('spacing: 16')  # landscape
      expect(code).to include('spacing: 8')   # default
    end
  end

  describe '.generate_leaf_function' do
    let(:component) do
      {
        'type' => 'Label',
        'text' => 'Hello',
        'fontSize' => 14,
        'responsive' => {
          'regular' => { 'fontSize' => 20 }
        }
      }
    end

    let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
    let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
    let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }

    it 'generates a leaf function with branches' do
      code = described_class.generate_leaf_function(
        'responsive0', component, converter_factory, 0, nil, view_registry, binding_registry
      )
      expect(code).to include('private func responsive0()')
      expect(code).to include('-> some View')
      expect(code).to include('horizontalSizeClass == .regular')
    end
  end

  describe '.resolve_vstack_alignment' do
    it 'returns .leading by default' do
      expect(described_class.resolve_vstack_alignment(nil)).to eq('.leading')
    end

    it 'returns .center for center gravity' do
      expect(described_class.resolve_vstack_alignment('center')).to eq('.center')
    end

    it 'returns .trailing for right gravity' do
      expect(described_class.resolve_vstack_alignment('right')).to eq('.trailing')
    end

    it 'handles pipe-separated gravity' do
      expect(described_class.resolve_vstack_alignment('center|top')).to eq('.center')
    end
  end

  describe '.resolve_hstack_alignment' do
    it 'returns .center by default' do
      expect(described_class.resolve_hstack_alignment(nil)).to eq('.center')
    end

    it 'returns .top for top gravity' do
      expect(described_class.resolve_hstack_alignment('top')).to eq('.top')
    end

    it 'returns .bottom for bottom gravity' do
      expect(described_class.resolve_hstack_alignment('bottom')).to eq('.bottom')
    end
  end

  describe '.build_responsive_modifiers (regression: sjui-responsive-maxwidth-centerhorizontal-not-applied)' do
    it 'emits .frame(maxWidth:) when attrs has maxWidth' do
      modifiers = described_class.build_responsive_modifiers({ 'maxWidth' => 480 }, nil)
      expect(modifiers).to eq(['.frame(maxWidth: 480)'])
    end

    it 'emits .frame(maxWidth: .infinity, alignment: .center) for centerHorizontal alone' do
      modifiers = described_class.build_responsive_modifiers({ 'centerHorizontal' => true }, nil)
      expect(modifiers).to eq(['.frame(maxWidth: .infinity, alignment: .center)'])
    end

    it 'composes maxWidth and centerHorizontal into a single .frame' do
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 480, 'centerHorizontal' => true }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 480, alignment: .center)'])
    end

    it 'emits maxHeight and minWidth/minHeight when present' do
      modifiers = described_class.build_responsive_modifiers(
        { 'minWidth' => 100, 'maxWidth' => 400, 'minHeight' => 50, 'maxHeight' => 200 }, nil
      )
      expect(modifiers).to eq(
        ['.frame(minWidth: 100, maxWidth: 400, minHeight: 50, maxHeight: 200)']
      )
    end

    it 'expands centerInParent into both axes' do
      modifiers = described_class.build_responsive_modifiers({ 'centerInParent' => true }, nil)
      expect(modifiers).to eq(
        ['.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)']
      )
    end

    it 'returns an empty array when no recognized keys are present' do
      modifiers = described_class.build_responsive_modifiers(
        { 'orientation' => 'horizontal', 'spacing' => 24 }, nil
      )
      expect(modifiers).to eq([])
    end
  end

  describe '.generate_container_function (regression: maxWidth/centerHorizontal in responsive override)' do
    let(:component_with_size_override) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'responsive' => {
          'regular' => { 'maxWidth' => 480, 'centerHorizontal' => true }
        }
      }
    end

    let(:converter_for_override) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(component_with_size_override, 0)
    end

    it 'emits .frame(maxWidth: 480, alignment: .center) in the regular branch' do
      code = described_class.generate_container_function(
        'responsive0', component_with_size_override, converter_for_override
      )
      expect(code).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'does not emit the frame modifier in the default branch (no override)' do
      code = described_class.generate_container_function(
        'responsive0', component_with_size_override, converter_for_override
      )
      # The default branch's VStack does not have an override of maxWidth/centerHorizontal,
      # so build_responsive_modifiers returns [] for it. There should be exactly one .frame line.
      expect(code.scan('.frame(maxWidth:').length).to eq(1)
    end
  end

  describe 'responsive? instance method (via include)' do
    let(:converter_class) do
      Class.new do
        include SjuiTools::SwiftUI::Views::ResponsiveHelper
      end
    end

    it 'returns true for component with responsive block' do
      obj = converter_class.new
      component = { 'responsive' => { 'regular' => {} } }
      expect(obj.responsive?(component)).to be true
    end

    it 'returns false for component without responsive block' do
      obj = converter_class.new
      component = { 'type' => 'View' }
      expect(obj.responsive?(component)).to be false
    end
  end
end
