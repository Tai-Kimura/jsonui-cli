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

      it 'adds circular progressViewStyle and a scale that takes its own space' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.progressViewStyle(CircularProgressViewStyle())')
        # `.scaleEffect` alone scaled the drawing and kept the 20 layout of medium (frame-parity
        # Indicator/indicatorStyle__large, 2026-10-05).
        expect(code).to include('.scaledWithFootprint(1.5)')
        expect(code).not_to include('.scaleEffect(')
        expect(code).to include('// Requires SwiftJsonUI >= 10.29.6 (scaledWithFootprint)')
      end
    end

    context 'with style Large' do
      let(:component) do
        {
          'type' => 'Indicator',
          'style' => 'Large'
        }
      end

      # indicatorStyle declares large, in lowercase: 'Large' is declared in
      # no case — the normalizer leaves it as a style file's name — so it
      # draws the default size (1.9.0).
      it 'draws the default size for a spelling declared in no case' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.progressViewStyle(CircularProgressViewStyle())')
        expect(code).not_to include('.scaleEffect(')
        expect(code).not_to include('.scaledWithFootprint(')
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

    # hidesWhenStopped is UIActivityIndicatorView's own property, which
    # SJUIViewCreator sets. The codegen read it nowhere, so `false` — keep the
    # stopped indicator's space — behaved like the default.
    describe 'hidesWhenStopped' do
      it 'collapses a stopped indicator by default' do
        code = described_class.new({ 'type' => 'Indicator', 'animating' => false }).convert
        expect(code).to include('EmptyView()')
      end

      it 'keeps the space when false' do
        code = described_class.new(
          { 'type' => 'Indicator', 'animating' => false, 'hidesWhenStopped' => false }
        ).convert
        expect(code).to include('ProgressView()')
        expect(code).to include('.opacity(0)')
        expect(code).not_to include('EmptyView()')
      end

      it 'drives opacity from the binding when false' do
        code = described_class.new({
          'type' => 'Indicator', 'animating' => '@{isLoading}', 'hidesWhenStopped' => false
        }).convert
        expect(code).to include('.opacity(data.isLoading ? 1 : 0)')
        expect(code).not_to include('if data.isLoading {')
      end
    end
  end
end
