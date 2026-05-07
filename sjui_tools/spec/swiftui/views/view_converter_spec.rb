# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'

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

        expect(code).to include('.hidden()')
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

      it 'adds ignoresSafeArea modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.ignoresSafeArea(')
      end
    end

    context 'with safeAreaInsetPositions all' do
      let(:component) do
        {
          'type' => 'View',
          'safeAreaInsetPositions' => 'all'
        }
      end

      it 'adds ignoresSafeArea modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.ignoresSafeArea()')
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
