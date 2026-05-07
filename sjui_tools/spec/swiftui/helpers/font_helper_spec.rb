# frozen_string_literal: true

require 'swiftui/helpers/font_helper'

RSpec.describe SjuiTools::SwiftUI::Helpers::FontHelper do
  # Create a mock converter for testing
  let(:mock_converter) do
    Class.new do
      attr_reader :modifiers

      def initialize
        @modifiers = []
      end

      def add_modifier_line(modifier)
        @modifiers << modifier
      end
    end.new
  end

  describe '#font_weight_to_swiftui' do
    it 'maps every weight in the shared mapping to its swift literal' do
      expect(described_class.font_weight_to_swiftui('ultralight')).to eq('.ultraLight')
      expect(described_class.font_weight_to_swiftui('thin')).to eq('.thin')
      expect(described_class.font_weight_to_swiftui('light')).to eq('.light')
      expect(described_class.font_weight_to_swiftui('regular')).to eq('.regular')
      expect(described_class.font_weight_to_swiftui('medium')).to eq('.medium')
      expect(described_class.font_weight_to_swiftui('semibold')).to eq('.semibold')
      expect(described_class.font_weight_to_swiftui('bold')).to eq('.bold')
      expect(described_class.font_weight_to_swiftui('heavy')).to eq('.heavy')
      expect(described_class.font_weight_to_swiftui('black')).to eq('.black')
    end

    it 'accepts legacy aliases that are not in the shared mapping' do
      expect(described_class.font_weight_to_swiftui('normal')).to eq('.regular')
      expect(described_class.font_weight_to_swiftui('ultra-light')).to eq('.ultraLight')
      expect(described_class.font_weight_to_swiftui('semi-bold')).to eq('.semibold')
    end

    it 'is case insensitive' do
      expect(described_class.font_weight_to_swiftui('BOLD')).to eq('.bold')
      expect(described_class.font_weight_to_swiftui('Bold')).to eq('.bold')
    end

    it 'returns nil for nil input' do
      expect(described_class.font_weight_to_swiftui(nil)).to be_nil
    end

    it 'warns and falls back to .regular for an unknown weight' do
      expect {
        result = described_class.font_weight_to_swiftui('extra-extra-bold')
        expect(result).to eq('.regular')
      }.to output(/unknown font weight 'extra-extra-bold'/).to_stderr
    end
  end

  describe '#apply_font_modifiers' do
    let(:resolve_call) { /SwiftJsonUIConfiguration\.shared\.resolveFont\(FontSpec\(/ }

    context 'with no font attributes' do
      let(:component) { { 'text' => 'Hello' } }

      it 'emits no modifier' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to be_empty
      end
    end

    context 'with weight only (font keyword)' do
      let(:component) { { 'font' => 'bold' } }

      it 'emits a single resolveFont call with weight set and family/size nil' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers.size).to eq(1)
        expect(mock_converter.modifiers.first).to eq(
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: nil, weight: .bold, size: nil, italic: false)))'
        )
      end

      it 'never emits the legacy fontProvider?(...) pattern' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers.none? { |m| m.include?('fontProvider') }).to be true
      end
    end

    context 'with weight only (fontWeight attribute)' do
      let(:component) { { 'fontWeight' => 'semibold' } }

      it 'emits a resolveFont call with the resolved weight' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: nil, weight: .semibold, size: nil, italic: false)))'
        ])
      end
    end

    context 'with family only (fontFamily attribute)' do
      let(:component) { { 'fontFamily' => 'Noto Sans JP' } }

      it 'emits a resolveFont call with family literal and weight/size nil' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: "Noto Sans JP", weight: nil, size: nil, italic: false)))'
        ])
      end
    end

    context 'with family-shaped `font` attribute (non-weight string)' do
      let(:component) { { 'font' => 'Helvetica' } }

      it 'treats `font` as the family' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: "Helvetica", weight: nil, size: nil, italic: false)))'
        ])
      end
    end

    context 'with fontSize only' do
      let(:component) { { 'fontSize' => 18 } }

      it 'emits a resolveFont call with size set and family/weight nil' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: nil, weight: nil, size: CGFloat(18), italic: false)))'
        ])
      end
    end

    context 'with weight + family + size combined' do
      let(:component) do
        {
          'fontFamily' => 'Inter',
          'fontWeight' => 'bold',
          'fontSize' => 16
        }
      end

      it 'emits a single resolveFont call with all three populated' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: "Inter", weight: .bold, size: CGFloat(16), italic: false)))'
        ])
      end

      it 'does NOT emit a separate .fontWeight(...) modifier' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers.none? { |m| m.start_with?('.fontWeight(') }).to be true
      end
    end

    context 'with fontFamily + weight via `font` keyword' do
      let(:component) { { 'fontFamily' => 'Inter', 'font' => 'semibold', 'fontSize' => 14 } }

      it 'merges the keyword weight into the FontSpec' do
        described_class.apply_font_modifiers(component, mock_converter)
        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: "Inter", weight: .semibold, size: CGFloat(14), italic: false)))'
        ])
      end
    end

    context 'with an unknown weight string' do
      let(:component) { { 'fontWeight' => 'extra-extra-bold', 'fontSize' => 12 } }

      it 'warns and emits .regular as the weight' do
        expect {
          described_class.apply_font_modifiers(component, mock_converter)
        }.to output(/unknown font weight 'extra-extra-bold'/).to_stderr

        expect(mock_converter.modifiers).to eq([
          '.font(SwiftJsonUIConfiguration.shared.resolveFont(' \
            'FontSpec(family: nil, weight: .regular, size: CGFloat(12), italic: false)))'
        ])
      end
    end
  end

  describe '#build_font_spec_args' do
    it 'returns nils when no font attributes are present' do
      expect(described_class.build_font_spec_args({})).to eq([nil, nil, nil])
    end

    it 'extracts family from fontFamily preferentially over a non-weight `font`' do
      result = described_class.build_font_spec_args(
        'fontFamily' => 'Inter', 'font' => 'Helvetica'
      )
      expect(result[0]).to eq('Inter')
    end

    it 'derives weight from fontWeight preferentially over a weight-keyword `font`' do
      result = described_class.build_font_spec_args(
        'fontWeight' => 'bold', 'font' => 'semibold'
      )
      expect(result[1]).to eq('.bold')
    end
  end
end
