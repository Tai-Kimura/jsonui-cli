# frozen_string_literal: true

require 'swiftui/views/indicator_converter'

RSpec.describe SjuiTools::SwiftUI::Views::IndicatorConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic indicator' do
      let(:component) do
        {
          'type' => 'Indicator'
        }
      end

      it 'generates ProgressView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ProgressView()')
      end
    end

    context 'with style large' do
      let(:component) do
        {
          'type' => 'Indicator',
          'style' => 'large'
        }
      end

      it 'adds circular progressViewStyle and scale effect' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.progressViewStyle(CircularProgressViewStyle())')
        expect(code).to include('.scaleEffect(1.5)')
      end
    end

    context 'with style Large' do
      let(:component) do
        {
          'type' => 'Indicator',
          'style' => 'Large'
        }
      end

      it 'handles capitalized style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.progressViewStyle(CircularProgressViewStyle())')
        expect(code).to include('.scaleEffect(1.5)')
      end
    end

    context 'with style medium' do
      let(:component) do
        {
          'type' => 'Indicator',
          'style' => 'medium'
        }
      end

      it 'adds circular progressViewStyle without scale' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.progressViewStyle(CircularProgressViewStyle())')
        expect(code).not_to include('.scaleEffect')
      end
    end

    context 'with animating binding' do
      let(:component) do
        {
          'type' => 'Indicator',
          'animating' => '@{isLoading}'
        }
      end

      it 'wraps in if condition' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('if data.isLoading {')
        expect(code).to include('ProgressView()')
        expect(code).to include('}')
      end
    end

    context 'with animating false' do
      let(:component) do
        {
          'type' => 'Indicator',
          'animating' => false
        }
      end

      it 'generates EmptyView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('EmptyView()')
        expect(code).not_to include('ProgressView()')
      end
    end

    context 'with color' do
      let(:component) do
        {
          'type' => 'Indicator',
          'color' => '#007AFF'
        }
      end

      it 'adds tint modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.tint(')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'Indicator',
          'background' => '#F5F5F5',
          'cornerRadius' => 8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
        expect(code).to include('.cornerRadius(8)')
      end
    end
  end
end
