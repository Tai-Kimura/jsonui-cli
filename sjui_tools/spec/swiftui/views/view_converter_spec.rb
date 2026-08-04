# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::Views::ViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with empty View (no children)' do
      let(:component) do
        {
          'type' => 'View'
        }
      end

      it 'generates EmptyView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('EmptyView()')
      end
    end

    context 'with background and no children' do
      let(:component) do
        {
          'type' => 'View',
          'background' => '#F5F5F5'
        }
      end

      it 'generates Rectangle with fill' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Rectangle()')
        expect(code).to include('.fill(')
      end
    end

    context 'with cornerRadius' do
      let(:component) do
        {
          'type' => 'View',
          'cornerRadius' => 12
        }
      end

      it 'adds cornerRadius modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(12)')
      end
    end

    context 'with border' do
      let(:component) do
        {
          'type' => 'View',
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC'
        }
      end

      it 'adds overlay with stroke' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.overlay(')
        expect(code).to include('.stroke(')
      end
    end

    context 'with shadow' do
      let(:component) do
        {
          'type' => 'View',
          'shadow' => {
            'color' => '#000000',
            'radius' => 4,
            'offsetX' => 0,
            'offsetY' => 2
          }
        }
      end

      it 'adds shadow modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.shadow(')
      end
    end

    context 'with gradient' do
      let(:component) do
        {
          'type' => 'View',
          'gradient' => ['#FF0000', '#00FF00']
        }
      end

      it 'adds LinearGradient background' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('LinearGradient')
      end
    end

    context 'with horizontal gradient' do
      let(:component) do
        {
          'type' => 'View',
          'gradient' => ['#FF0000', '#00FF00'],
          'gradientDirection' => 'Horizontal'
        }
      end

      it 'adds LinearGradient with horizontal direction' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.leading')
        expect(code).to include('.trailing')
      end
    end

    context 'with onclick' do
      let(:component) do
        {
          'type' => 'View',
          'onClick' => 'handleTap'
        }
      end

      it 'adds onTapGesture' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onTapGesture')
        expect(code).to include('data.handleTap?()')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'View',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    context 'with alpha/opacity' do
      let(:component) do
        {
          'type' => 'View',
          'alpha' => 0.5
        }
      end

      it 'adds opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end

    context 'with clipToBounds' do
      let(:component) do
        {
          'type' => 'View',
          'clipToBounds' => true
        }
      end

      it 'adds clipped modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.clipped()')
      end
    end

    context 'with offset' do
      let(:component) do
        {
          'type' => 'View',
          'offsetX' => 10,
          'offsetY' => 20
        }
      end

      it 'adds offset modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.offset(x: 10, y: 20)')
      end
    end

    context 'with safeAreaInsetPositions array' do
      let(:component) do
        {
          'type' => 'View',
          'safeAreaInsetPositions' => ['top', 'bottom']
        }
      end

      # The attribute names the edges that RESERVE the safe area — the SSoT's
      # own wording, and what rjui, kjui and this library's UIKit runtime all
      # do. `.ignoresSafeArea` is the opposite modifier and is what the
      # SwiftUI codegen used to emit; these examples pinned the defect.
      it 'reserves the safe area on the named edges' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.safeAreaPadding([.top, .bottom])')
        expect(code).not_to include('.ignoresSafeArea')
      end
    end

    context 'with safeAreaInsetPositions all' do
      let(:component) do
        {
          'type' => 'View',
          'safeAreaInsetPositions' => 'all'
        }
      end

      it 'reserves the safe area on every edge' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.safeAreaPadding(.all)')
        expect(code).not_to include('.ignoresSafeArea')
      end
    end

    context 'with safeAreaInsetPositions on a SafeAreaView' do
      let(:component) do
        {
          'type' => 'SafeAreaView',
          'safeAreaInsetPositions' => ['top']
        }
      end

      # `apply_modifiers` already runs the safe-area step for every component,
      # and ViewConverter used to run it a SECOND time for SafeAreaView. Two
      # `.ignoresSafeArea` calls ignore an edge once; two `.safeAreaPadding`
      # calls inset twice.
      it 'reserves it once' do
        code = described_class.new(component).convert

        expect(code.scan('.safeAreaPadding').length).to eq(1)
      end
    end

    context 'with enabled false' do
      let(:component) do
        {
          'type' => 'View',
          'enabled' => false
        }
      end

      it 'adds disabled modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.disabled(true)')
      end
    end

    context 'with tag' do
      let(:component) do
        {
          'type' => 'View',
          'tag' => 1
        }
      end

      it 'adds tag modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.tag(1)')
      end
    end

    context 'with touchDisabledState' do
      let(:component) do
        {
          'type' => 'View',
          'touchDisabledState' => true
        }
      end

      it 'adds allowsHitTesting false' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.allowsHitTesting(false)')
      end
    end

    # Regression: sjui-weightedhstack-fixedsize-overflows-with-matchparent-height
    # A horizontal View with `height: matchParent` plus weighted children should
    # tell SwiftJsonUI's WeightedHStack to honor the parent's vertical
    # proposal — otherwise the inner `.fixedSize(vertical: true)` collapses
    # to the child's natural height (which is `.infinity` for Embeds with
    # `.frame(maxHeight: .infinity)`) and the stack overflows the pane.
    context 'with horizontal weighted children and height: matchParent' do
      let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
      let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
      let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }
      let(:component) do
        {
          'type' => 'View',
          'orientation' => 'horizontal',
          'width' => 'matchParent',
          'height' => 'matchParent',
          'child' => [
            { 'type' => 'View', 'width' => 375 },
            { 'type' => 'View', 'weight' => 1 }
          ]
        }
      end

      it 'emits WeightedHStack with hasMatchParentCrossAxis: true' do
        converter = described_class.new(component, 0, nil, converter_factory, view_registry, binding_registry)
        code = converter.convert
        expect(code).to include('WeightedHStack(')
        expect(code).to include('hasMatchParentCrossAxis: true')
      end

      # Regression: sjui-weightedhstack-hasmatchparentcrossaxis-arg-order
      # SwiftJsonUI's WeightedHStack init declares args as:
      #   alignment, spacing, children, hasMatchParentCrossAxis
      # Swift requires named args in declaration order. Emitting
      # `hasMatchParentCrossAxis` BEFORE `children` triggers
      # `Argument 'children' must precede argument 'hasMatchParentCrossAxis'`.
      it 'puts hasMatchParentCrossAxis after children (Swift arg-order rule)' do
        converter = described_class.new(component, 0, nil, converter_factory, view_registry, binding_registry)
        code = converter.convert
        # The opening line carries `children: [` but NOT
        # `hasMatchParentCrossAxis` — the flag goes on the closing line.
        opening = code.lines.find { |l| l.include?('WeightedHStack(') }
        expect(opening).not_to be_nil
        expect(opening).to include('children: [')
        expect(opening).not_to include('hasMatchParentCrossAxis')
        # The closing emits the flag AFTER the children array literal.
        expect(code).to include('], hasMatchParentCrossAxis: true)')
      end
    end

    context 'with horizontal weighted children but no height: matchParent' do
      let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
      let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
      let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }
      let(:component) do
        {
          'type' => 'View',
          'orientation' => 'horizontal',
          'width' => 'matchParent',
          'height' => 200,
          'child' => [
            { 'type' => 'View', 'width' => 100 },
            { 'type' => 'View', 'weight' => 1 }
          ]
        }
      end

      it 'omits hasMatchParentCrossAxis (default false)' do
        converter = described_class.new(component, 0, nil, converter_factory, view_registry, binding_registry)
        code = converter.convert
        expect(code).to include('WeightedHStack(')
        expect(code).not_to include('hasMatchParentCrossAxis')
      end
    end
  end

  describe 'gravity handling' do
    let(:converter) { described_class.new({ 'type' => 'View' }) }

    context '#extract_horizontal_from_gravity' do
      it 'extracts left from left|top' do
        expect(converter.extract_horizontal_from_gravity('left|top')).to eq('left')
      end

      it 'extracts right from right|bottom' do
        expect(converter.extract_horizontal_from_gravity('right|bottom')).to eq('right')
      end

      it 'extracts center from center' do
        expect(converter.extract_horizontal_from_gravity('center')).to eq('center')
      end

      it 'handles array format' do
        expect(converter.extract_horizontal_from_gravity(['left', 'top'])).to eq('left')
      end

      it 'returns left as default' do
        expect(converter.extract_horizontal_from_gravity(nil)).to eq('left')
      end

      it 'extracts center from centerHorizontal' do
        expect(converter.extract_horizontal_from_gravity('centerHorizontal')).to eq('center')
      end

      it 'extracts center from centerHorizontal|top' do
        expect(converter.extract_horizontal_from_gravity('centerHorizontal|top')).to eq('center')
      end

      it 'handles centerHorizontal in array format' do
        expect(converter.extract_horizontal_from_gravity(['centerHorizontal', 'top'])).to eq('center')
      end
    end

    context '#extract_vertical_from_gravity' do
      it 'extracts top from left|top' do
        expect(converter.extract_vertical_from_gravity('left|top')).to eq('top')
      end

      it 'extracts bottom from right|bottom' do
        expect(converter.extract_vertical_from_gravity('right|bottom')).to eq('bottom')
      end

      it 'handles array format' do
        expect(converter.extract_vertical_from_gravity(['left', 'bottom'])).to eq('bottom')
      end

      it 'returns top as default' do
        expect(converter.extract_vertical_from_gravity(nil)).to eq('top')
      end

      it 'extracts center from centerVertical' do
        expect(converter.extract_vertical_from_gravity('centerVertical')).to eq('center')
      end

      it 'extracts center from left|centerVertical' do
        expect(converter.extract_vertical_from_gravity('left|centerVertical')).to eq('center')
      end

      it 'handles centerVertical in array format' do
        expect(converter.extract_vertical_from_gravity(['left', 'centerVertical'])).to eq('center')
      end
    end
  end
end
