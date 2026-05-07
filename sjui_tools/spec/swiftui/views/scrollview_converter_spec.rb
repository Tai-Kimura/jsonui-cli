# frozen_string_literal: true

require 'swiftui/views/scrollview_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ScrollViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with default vertical scroll' do
      let(:component) do
        {
          'type' => 'ScrollView'
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
      end

      it 'uses VStack for children' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('VStack')
      end
    end

    context 'with horizontal scroll' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'horizontalScroll' => true
        }
      end

      it 'generates horizontal scroll view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end

      it 'uses HStack for children' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('HStack')
      end
    end

    context 'with orientation horizontal' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'orientation' => 'horizontal'
        }
      end

      it 'generates horizontal scroll view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end
    end

    context 'with scroll indicators hidden' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'showsVerticalScrollIndicator' => false
        }
      end

      it 'hides scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with horizontal scroll indicator hidden' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'orientation' => 'horizontal',
          'showsHorizontalScrollIndicator' => false
        }
      end

      it 'hides horizontal scroll indicators' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('showsIndicators: false')
      end
    end

    context 'with scrollEnabled false' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'scrollEnabled' => false
        }
      end

      it 'emits scrollDisabled(true) without falling back to disabled(true)' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollDisabled(true)')
        expect(code).not_to include('.disabled(true)')
      end
    end

    context 'with scrollEnabled bound to data' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'scrollEnabled' => '@{canScroll}'
        }
      end

      it 'emits scrollDisabled with negated binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollDisabled(!data.canScroll)')
        expect(code).not_to include('.disabled(data.canScroll == false)')
      end
    end

    context 'with bounces false' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'bounces' => false
        }
      end

      it 'adds note about bounce behavior' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('bounce behavior')
      end
    end

    context 'with contentInsetAdjustmentBehavior' do
      context 'when never' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'never'
          }
        end

        it 'adds ignoresSafeArea modifier' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('.ignoresSafeArea()')
        end
      end

      context 'when scrollableAxes' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'scrollableAxes'
          }
        end

        it 'adds ignoresSafeArea with horizontal edges' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('.ignoresSafeArea(edges: .horizontal)')
        end
      end

      context 'when unknown value' do
        let(:component) do
          {
            'type' => 'ScrollView',
            'contentInsetAdjustmentBehavior' => 'custom'
          }
        end

        it 'adds comment with value' do
          converter = described_class.new(component)
          code = converter.convert

          expect(code).to include('// contentInsetAdjustmentBehavior: custom')
        end
      end
    end

    context 'with paging enabled' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'paging' => true
        }
      end

      it 'adds scrollTargetBehavior modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollTargetBehavior(.paging)')
      end

      it 'adds iOS 17 note' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iOS 17')
      end
    end

    context 'with paging as string' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'paging' => 'true'
        }
      end

      it 'adds scrollTargetBehavior modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.scrollTargetBehavior(.paging)')
      end
    end

    context 'with maxZoom' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'maxZoom' => 3.0
        }
      end

      it 'adds MagnificationGesture' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('MagnificationGesture()')
        expect(code).to include('maxZoom: 3.0')
      end
    end

    context 'with single View child' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'child' => {
            'type' => 'View',
            'orientation' => 'horizontal'
          }
        }
      end

      it 'inherits orientation from child' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.horizontal')
      end
    end

    context 'with keyboardAvoidance enabled (default)' do
      let(:component) do
        {
          'type' => 'ScrollView'
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView without configuration' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).not_to include('KeyboardAvoidanceConfiguration')
      end
    end

    context 'with keyboardAvoidance explicitly true' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'keyboardAvoidance' => true
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView without configuration' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).not_to include('KeyboardAvoidanceConfiguration')
      end
    end

    context 'with keyboardAvoidance disabled' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'keyboardAvoidance' => false
        }
      end

      it 'generates AdvancedKeyboardAvoidingScrollView with isEnabled false' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.vertical')
        expect(code).to include('KeyboardAvoidanceConfiguration(isEnabled: false)')
      end
    end

    context 'with keyboardAvoidance disabled and horizontal scroll' do
      let(:component) do
        {
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'keyboardAvoidance' => false
        }
      end

      it 'generates horizontal scroll with keyboard avoidance disabled' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('AdvancedKeyboardAvoidingScrollView(.horizontal')
        expect(code).to include('KeyboardAvoidanceConfiguration(isEnabled: false)')
      end
    end
  end

  describe '#extract_horizontal_from_gravity' do
    let(:converter) { described_class.new({ 'type' => 'ScrollView' }) }

    it 'extracts center from center gravity' do
      expect(converter.extract_horizontal_from_gravity('center')).to eq('center')
    end

    it 'extracts left from left|top' do
      expect(converter.extract_horizontal_from_gravity('left|top')).to eq('left')
    end

    it 'extracts right from right|bottom' do
      expect(converter.extract_horizontal_from_gravity('right|bottom')).to eq('right')
    end

    it 'handles array gravity format' do
      expect(converter.extract_horizontal_from_gravity(['right', 'top'])).to eq('right')
    end

    it 'returns left as default for nil' do
      expect(converter.extract_horizontal_from_gravity(nil)).to eq('left')
    end

    it 'returns left for invalid gravity' do
      expect(converter.extract_horizontal_from_gravity('invalid')).to eq('left')
    end
  end
end
