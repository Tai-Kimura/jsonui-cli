# frozen_string_literal: true

require 'xml/helpers/mappers/text_mapper'
require 'xml/helpers/resource_resolver'

RSpec.describe XmlGenerator::Mappers::TextMapper do
  let(:mapper) { described_class.new }

  describe '#initialize' do
    it 'creates mapper without arguments' do
      expect(mapper).to be_a(described_class)
    end

    it 'creates mapper with string resource manager' do
      mapper_with_manager = described_class.new(double('StringResourceManager'))
      expect(mapper_with_manager).to be_a(described_class)
    end
  end

  describe '#map_text_attributes' do
    context 'text attribute' do
      it 'maps text attribute' do
        result = mapper.map_text_attributes('text', 'Hello', 'TextView')
        expect(result[:namespace]).to eq('android')
        expect(result[:name]).to eq('text')
        expect(result[:value]).not_to be_nil
      end

      it 'preserves data binding' do
        result = mapper.map_text_attributes('text', '@{data.title}', 'TextView')
        expect(result[:value]).to eq('@{data.title}')
      end
    end

    context 'hint attribute' do
      it 'maps hint attribute' do
        result = mapper.map_text_attributes('hint', 'Enter text', 'EditText')
        expect(result[:namespace]).to eq('android')
        expect(result[:name]).to eq('hint')
      end

      it 'preserves hint data binding' do
        result = mapper.map_text_attributes('hint', '@{data.placeholder}', 'EditText')
        expect(result[:value]).to eq('@{data.placeholder}')
      end
    end

    context 'fontSize/textSize attribute' do
      it 'maps fontSize to textSize' do
        result = mapper.map_text_attributes('fontSize', 16, 'TextView')
        expect(result[:name]).to eq('textSize')
        expect(result[:value]).to eq('16sp')
      end

      it 'maps textSize' do
        result = mapper.map_text_attributes('textSize', 14, 'TextView')
        expect(result[:value]).to eq('14sp')
      end

      it 'handles string fontSize' do
        result = mapper.map_text_attributes('fontSize', '18', 'TextView')
        expect(result[:value]).to eq('18sp')
      end

      it 'passes through sp values' do
        result = mapper.map_text_attributes('fontSize', '20sp', 'TextView')
        expect(result[:value]).to eq('20sp')
      end
    end

    context 'fontColor/textColor attribute' do
      it 'maps fontColor to textColor' do
        result = mapper.map_text_attributes('fontColor', '#FF0000', 'TextView')
        expect(result[:name]).to eq('textColor')
      end

      it 'maps textColor' do
        result = mapper.map_text_attributes('textColor', '#00FF00', 'TextView')
        expect(result[:name]).to eq('textColor')
      end
    end

    context 'color attribute' do
      it 'maps color to textColor for text components' do
        result = mapper.map_text_attributes('color', '#FF0000', 'Label')
        expect(result[:name]).to eq('textColor')
      end

      it 'maps color to textColor for Button' do
        result = mapper.map_text_attributes('color', '#FF0000', 'Button')
        expect(result[:name]).to eq('textColor')
      end

      it 'maps color to tint for non-text components' do
        result = mapper.map_text_attributes('color', '#FF0000', 'ImageView')
        expect(result[:name]).to eq('tint')
      end
    end

    context 'font attribute' do
      it 'maps bold to textStyle' do
        result = mapper.map_text_attributes('font', 'bold', 'TextView')
        expect(result[:name]).to eq('textStyle')
        expect(result[:value]).to eq('bold')
      end

      it 'maps italic to textStyle' do
        result = mapper.map_text_attributes('font', 'italic', 'TextView')
        expect(result[:value]).to eq('italic')
      end

      it 'maps font file for Kjui views' do
        result = mapper.map_text_attributes('font', 'MyFont', 'Label')
        expect(result[:namespace]).to eq('app')
        expect(result[:name]).to eq('kjui_font_name')
        expect(result[:value]).to eq('MyFont.ttf')
      end

      it 'adds ttf extension if not present' do
        result = mapper.map_text_attributes('font', 'CustomFont', 'TextField')
        expect(result[:value]).to eq('CustomFont.ttf')
      end

      it 'preserves existing ttf extension' do
        result = mapper.map_text_attributes('font', 'MyFont.ttf', 'Label')
        expect(result[:value]).to eq('MyFont.ttf')
      end

      it 'preserves existing otf extension' do
        result = mapper.map_text_attributes('font', 'MyFont.otf', 'Label')
        expect(result[:value]).to eq('MyFont.otf')
      end

      it 'maps to fontFamily for non-Kjui views' do
        result = mapper.map_text_attributes('font', 'sans-serif', 'OtherView')
        expect(result[:name]).to eq('fontFamily')
      end
    end

    context 'fontFamily attribute' do
      it 'maps fontFamily for Kjui views' do
        result = mapper.map_text_attributes('fontFamily', 'Roboto', 'Label')
        expect(result[:namespace]).to eq('app')
        expect(result[:name]).to eq('kjui_font_name')
      end

      it 'maps fontFamily for non-Kjui views' do
        result = mapper.map_text_attributes('fontFamily', 'sans-serif', 'OtherView')
        expect(result[:namespace]).to eq('android')
        expect(result[:name]).to eq('fontFamily')
      end
    end

    context 'fontWeight attribute' do
      it 'maps bold' do
        result = mapper.map_text_attributes('fontWeight', 'bold', 'TextView')
        expect(result[:value]).to eq('bold')
      end

      it 'maps italic' do
        result = mapper.map_text_attributes('fontWeight', 'italic', 'TextView')
        expect(result[:value]).to eq('italic')
      end

      it 'maps bold_italic' do
        result = mapper.map_text_attributes('fontWeight', 'bold_italic', 'TextView')
        expect(result[:value]).to eq('bold|italic')
      end

      it 'maps normal' do
        result = mapper.map_text_attributes('fontWeight', 'normal', 'TextView')
        expect(result[:value]).to eq('normal')
      end

      it 'maps medium to bold' do
        result = mapper.map_text_attributes('fontWeight', 'medium', 'TextView')
        expect(result[:value]).to eq('bold')
      end

      it 'maps unknown to normal' do
        result = mapper.map_text_attributes('fontWeight', 'unknown', 'TextView')
        expect(result[:value]).to eq('normal')
      end
    end

    context 'textAlign/textAlignment attribute' do
      it 'maps left to textStart' do
        result = mapper.map_text_attributes('textAlign', 'left', 'TextView')
        expect(result[:value]).to eq('textStart')
      end

      it 'maps right to textEnd' do
        result = mapper.map_text_attributes('textAlign', 'right', 'TextView')
        expect(result[:value]).to eq('textEnd')
      end

      it 'maps center' do
        result = mapper.map_text_attributes('textAlign', 'center', 'TextView')
        expect(result[:value]).to eq('center')
      end

      it 'maps start to textStart' do
        result = mapper.map_text_attributes('textAlignment', 'start', 'TextView')
        expect(result[:value]).to eq('textStart')
      end

      it 'maps end to textEnd' do
        result = mapper.map_text_attributes('textAlignment', 'end', 'TextView')
        expect(result[:value]).to eq('textEnd')
      end
    end

    context 'maxLines attribute' do
      it 'maps maxLines' do
        result = mapper.map_text_attributes('maxLines', 2, 'TextView')
        expect(result[:name]).to eq('maxLines')
        expect(result[:value]).to eq('2')
      end
    end

    context 'ellipsize attribute' do
      it 'maps ellipsize' do
        result = mapper.map_text_attributes('ellipsize', 'end', 'TextView')
        expect(result[:name]).to eq('ellipsize')
        expect(result[:value]).to eq('end')
      end
    end

    context 'unknown attribute' do
      it 'returns nil for unknown attribute' do
        result = mapper.map_text_attributes('unknown', 'value', 'TextView')
        expect(result).to be_nil
      end
    end
  end
end
