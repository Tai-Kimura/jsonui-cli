# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/converter_factory'
require 'swiftui/view_registry'

RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter, 'responsive integration' do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
  let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
  let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }

  describe '#convert with responsive container' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' },
          { 'type' => 'Label', 'text' => 'World' }
        ]
      }
    end

    it 'generates a function call instead of inline stack' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      # Should reference the responsive function, not generate HStack/VStack inline
      expect(code).to include('responsive0 {')
      expect(code).not_to include('VStack(alignment:')
      expect(code).not_to include('HStack(alignment:')
    end

    it 'still renders children inline' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      # Children should still appear in the generated code
      expect(code).to include('PartialAttributedText(')
    end

    it 'registers a responsive function in the converter_factory' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert

      expect(converter_factory.responsive_functions.length).to eq(1)
      func_code = converter_factory.responsive_functions.first
      expect(func_code).to include('private func responsive0<Content: View>')
      expect(func_code).to include('content()')
    end

    it 'increments the responsive counter' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert

      expect(converter_factory.responsive_counter).to eq(1)
    end
  end

  describe '#convert without responsive' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    it 'generates normal VStack code (no responsive function)' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      code = converter.convert

      expect(code).to include('VStack(alignment:')
      expect(code).not_to include('responsive0')
      expect(converter_factory.responsive_functions).to be_empty
    end
  end

  describe '#convert responsive with background on parent' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'background' => '#FFFFFF',
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    it 'applies background inside the wrapper function (per branch)' do
      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert

      # Background lives on the parent View, so each branch inside the
      # wrapper function emits `.background(...)`. It is NOT emitted at the
      # call site any more — that was the old behavior pre-fix.
      func_code = converter_factory.responsive_functions.first
      expect(func_code).to include('.background(')
      # Both branches should have it, since branch attrs include base.
      expect(func_code.scan('.background(').length).to be >= 2
    end
  end

  # Regression: sjui-kjui-responsive-non-frame-attrs-dropped
  # The OLD apply_non_responsive_modifiers path stripped overridden keys
  # from @component before re-running apply_modifiers; combined with
  # ResponsiveHelper.build_responsive_modifiers covering only frame /
  # center keys, that meant padding/margin/background/cornerRadius/etc.
  # overrides silently disappeared from BOTH branches.
  describe '#convert responsive with non-frame override (regression: non-frame attrs dropped)' do
    it 'emits .padding(.top, 80) inside the regular branch only when overridden' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'responsive' => {
          'regular' => { 'maxWidth' => 480, 'centerHorizontal' => true, 'topMargin' => 80 }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hello' }]
      }

      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert
      func_code = converter_factory.responsive_functions.first

      # Regular branch: combined frame + branch-level padding.
      expect(func_code).to include('.frame(maxWidth: 480, alignment: .center)')
      expect(func_code).to include('.padding(.top, 80)')
      # Default branch must NOT have either, since base has neither.
      expect(func_code.scan('.padding(.top, 80)').length).to eq(1)
      expect(func_code.scan('.frame(maxWidth: 480').length).to eq(1)
    end

    it 'emits per-branch padding/margin/background/cornerRadius/border/alpha from base merge' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'leftPadding' => 16,
        'cornerRadius' => 12,
        'background' => '#FFFFFF',
        'borderWidth' => 1,
        'borderColor' => '#CCCCCC',
        'alpha' => 0.9,
        'responsive' => {
          'regular' => { 'leftPadding' => 32, 'cornerRadius' => 0, 'alpha' => 1.0 }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hello' }]
      }

      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      converter.convert
      func_code = converter_factory.responsive_functions.first

      # Regular branch (override): 32 leftPadding, 0 cornerRadius, alpha 1.0
      expect(func_code).to include('.padding(.leading, 32)')
      expect(func_code).to include('.cornerRadius(0)')
      expect(func_code).to include('.opacity(1.0)')

      # Default branch (base): 16 leftPadding, 12 cornerRadius, alpha 0.9
      expect(func_code).to include('.padding(.leading, 16)')
      expect(func_code).to include('.cornerRadius(12)')
      expect(func_code).to include('.opacity(0.9)')

      # Non-overridden base attrs (background, border) appear in BOTH branches
      expect(func_code.scan('.background(').length).to be >= 2
      expect(func_code.scan('.overlay(').length).to be >= 2
    end

    it 'does not emit container modifiers at the call site any more' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'topMargin' => 12,
        'background' => '#FFFFFF',
        'responsive' => {
          'regular' => { 'maxWidth' => 480 }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hello' }]
      }

      converter = described_class.new(
        component, 0, nil, converter_factory, view_registry, binding_registry
      )
      call_site = converter.convert

      # Container-level modifiers now live INSIDE the wrapper function.
      # The call site is just `responsive0 { children }`.
      expect(call_site).to include('responsive0 {')
      expect(call_site).not_to include('.padding(.top, 12)')
      expect(call_site).not_to include('.background(')
      expect(call_site).not_to include('.frame(maxWidth: 480)')
    end
  end

  describe 'multiple responsive components' do
    it 'assigns unique function names' do
      component1 = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } },
        'child' => [{ 'type' => 'Label', 'text' => 'A' }]
      }
      component2 = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } },
        'child' => [{ 'type' => 'Label', 'text' => 'B' }]
      }

      c1 = described_class.new(component1, 0, nil, converter_factory, view_registry, binding_registry)
      c1.convert

      c2 = described_class.new(component2, 0, nil, converter_factory, view_registry, binding_registry)
      c2.convert

      expect(converter_factory.responsive_functions.length).to eq(2)
      expect(converter_factory.responsive_functions[0]).to include('responsive0')
      expect(converter_factory.responsive_functions[1]).to include('responsive1')
    end
  end
end
