# frozen_string_literal: true

require 'swiftui/views/gradient_view_converter'
require 'swiftui/converter_factory'

RSpec.describe SjuiTools::SwiftUI::Views::GradientViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

    context 'with no children' do
      let(:component) { { 'type' => 'GradientView', 'colors' => ['#FF0000', '#00FF00'] } }

      it 'generates Color.clear with gradient background' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('Color.clear')
        expect(code).to include('.background(LinearGradient')
      end
    end

    context 'with colors array' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#FF0000', '#00FF00', '#0000FF']
        }
      end

      it 'generates gradient with multiple colors' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('LinearGradient(colors:')
      end
    end

    context 'with vertical direction' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#000000', '#FFFFFF'],
          'gradientDirection' => 'Vertical'
        }
      end

      it 'uses top to bottom gradient' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('startPoint: .top')
        expect(code).to include('endPoint: .bottom')
      end
    end

    context 'with horizontal direction' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#000000', '#FFFFFF'],
          'gradientDirection' => 'Horizontal'
        }
      end

      it 'uses leading to trailing gradient' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('startPoint: .leading')
        expect(code).to include('endPoint: .trailing')
      end
    end

    context 'with oblique direction' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#000000', '#FFFFFF'],
          'gradientDirection' => 'Oblique'
        }
      end

      it 'uses diagonal gradient' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('startPoint: .topLeading')
        expect(code).to include('endPoint: .bottomTrailing')
      end
    end

    context 'with custom start and end points' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#000000', '#FFFFFF'],
          'startPoint' => { 'x' => 0, 'y' => 0 },
          'endPoint' => { 'x' => 1, 'y' => 1 }
        }
      end

      it 'uses custom unit points' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('.topLeading')
        expect(code).to include('.bottomTrailing')
      end
    end

    context 'with non-standard custom points' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#000000', '#FFFFFF'],
          'startPoint' => { 'x' => 0.25, 'y' => 0.25 },
          'endPoint' => { 'x' => 0.75, 'y' => 0.75 }
        }
      end

      it 'uses UnitPoint with custom values' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('UnitPoint(x: 0.25, y: 0.25)')
        expect(code).to include('UnitPoint(x: 0.75, y: 0.75)')
      end
    end

    context 'with single child' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#FF0000', '#0000FF'],
          'child' => [{ 'type' => 'Label', 'text' => 'Hello' }]
        }
      end

      it 'renders child with gradient background' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('"Hello"')
        expect(code).to include('LinearGradient')
      end
    end

    context 'with multiple children' do
      let(:component) do
        {
          'type' => 'GradientView',
          'colors' => ['#FF0000', '#0000FF'],
          'child' => [
            { 'type' => 'Label', 'text' => 'First' },
            { 'type' => 'Label', 'text' => 'Second' }
          ]
        }
      end

      it 'wraps children in VStack' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('VStack(spacing: 0)')
        expect(code).to include('"First"')
        expect(code).to include('"Second"')
      end
    end

    context 'with gradient property (alias for colors)' do
      let(:component) do
        {
          'type' => 'GradientView',
          'gradient' => ['#FF0000', '#00FF00']
        }
      end

      it 'uses gradient property' do
        converter = described_class.new(component, 0, nil, factory)
        code = converter.convert

        expect(code).to include('LinearGradient')
      end
    end
  end

  describe '#gradient_point (private)' do
    let(:component) { { 'type' => 'GradientView', 'colors' => ['#000', '#FFF'] } }
    let(:converter) { described_class.new(component) }

    it 'maps (0, 0) to .topLeading' do
      result = converter.send(:gradient_point, { 'x' => 0, 'y' => 0 })
      expect(result).to eq('.topLeading')
    end

    it 'maps (0.5, 0) to .top' do
      result = converter.send(:gradient_point, { 'x' => 0.5, 'y' => 0 })
      expect(result).to eq('.top')
    end

    it 'maps (1, 0) to .topTrailing' do
      result = converter.send(:gradient_point, { 'x' => 1, 'y' => 0 })
      expect(result).to eq('.topTrailing')
    end

    it 'maps (0, 0.5) to .leading' do
      result = converter.send(:gradient_point, { 'x' => 0, 'y' => 0.5 })
      expect(result).to eq('.leading')
    end

    it 'maps (0.5, 0.5) to .center' do
      result = converter.send(:gradient_point, { 'x' => 0.5, 'y' => 0.5 })
      expect(result).to eq('.center')
    end

    it 'maps (1, 0.5) to .trailing' do
      result = converter.send(:gradient_point, { 'x' => 1, 'y' => 0.5 })
      expect(result).to eq('.trailing')
    end

    it 'maps (0, 1) to .bottomLeading' do
      result = converter.send(:gradient_point, { 'x' => 0, 'y' => 1 })
      expect(result).to eq('.bottomLeading')
    end

    it 'maps (0.5, 1) to .bottom' do
      result = converter.send(:gradient_point, { 'x' => 0.5, 'y' => 1 })
      expect(result).to eq('.bottom')
    end

    it 'maps (1, 1) to .bottomTrailing' do
      result = converter.send(:gradient_point, { 'x' => 1, 'y' => 1 })
      expect(result).to eq('.bottomTrailing')
    end

    it 'returns UnitPoint for non-standard values' do
      result = converter.send(:gradient_point, { 'x' => 0.3, 'y' => 0.7 })
      expect(result).to eq('UnitPoint(x: 0.3, y: 0.7)')
    end
  end
end
