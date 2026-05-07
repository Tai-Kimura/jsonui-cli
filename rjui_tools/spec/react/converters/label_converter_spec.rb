# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/label_converter'

RSpec.describe RjuiTools::React::Converters::LabelConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic text' do
      it 'renders a span with text content' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Hello World'
        })
        result = converter.convert
        expect(result).to include('<span')
        expect(result).to include('Hello World')
        expect(result).to include('</span>')
      end
    end

    context 'with binding expression' do
      it 'converts binding to JSX expression with viewModel.data prefix' do
        converter = create_converter({
          'type' => 'Label',
          'text' => '@{userName}'
        })
        result = converter.convert
        expect(result).to include('{data.userName}')
      end
    end
  end

  describe '#build_class_name' do
    context 'with line clamp' do
      it 'adds truncate class for single line' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 1
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('truncate')
      end

      it 'adds line-clamp class for multiple lines' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 3
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('line-clamp-3')
      end

      it 'does not add line clamp for zero lines' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 0
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('truncate')
        expect(classes).not_to match(/line-clamp/)
      end
    end

    context 'with underline' do
      it 'adds underline class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Underlined text',
          'underline' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('underline')
      end
    end

    context 'with strikethrough' do
      it 'adds line-through class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Strikethrough text',
          'strikethrough' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('line-through')
      end
    end

    context 'with onClick' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Clickable',
          'onClick' => 'handleClick'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end

    context 'with linkable' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Visit https://example.com',
          'linkable' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with lineHeightMultiple' do
      it 'sets lineHeight style' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineHeightMultiple' => 1.5
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include('lineHeight: 1.5')
      end
    end

    context 'with lineSpacing' do
      it 'calculates lineHeight from lineSpacing and fontSize' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineSpacing' => 8,
          'fontSize' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        # lineHeight = (16 + 8) / 16 = 1.5
        expect(result).to include('lineHeight: 1.5')
      end

      it 'uses default fontSize of 16 when not specified' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineSpacing' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include('lineHeight: 1.5')
      end
    end

    context 'with edgeInset' do
      it 'handles single value' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => 10
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px'")
      end

      it 'handles 2-element array' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => [10, 20]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px'")
      end

      it 'handles 4-element array' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => [10, 20, 30, 40]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end

      it 'handles pipe-separated string' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => '10|20|30|40'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end
    end

    context 'with disabled state' do
      it 'sets color to disabledFontColor when enabled is false' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'enabled' => false,
          'disabledFontColor' => '#999999'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("color: '#999999'")
      end
    end

    context 'with lineBreakMode' do
      it 'handles Head truncation' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text that will be truncated',
          'lineBreakMode' => 'Head'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
        expect(result).to include("direction: 'rtl'")
        expect(result).to include("textAlign: 'left'")
        expect(result).to include("overflow: 'hidden'")
      end

      it 'handles Tail truncation' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Tail'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
        expect(result).to include("overflow: 'hidden'")
        expect(result).to include("whiteSpace: 'nowrap'")
      end

      it 'handles Middle truncation (falls back to ellipsis)' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Middle'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
      end

      it 'does not add whiteSpace nowrap when lines > 1' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Tail',
          'lines' => 2
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).not_to include("whiteSpace: 'nowrap'")
      end
    end

    context 'with autoShrink' do
      it 'uses CSS min() for font scaling' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'autoShrink' => true,
          'fontSize' => 20,
          'minimumScaleFactor' => 0.5
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("fontSize: 'min(20px, max(10px, 1vw))'")
      end

      it 'uses default minimumScaleFactor of 0.5' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'autoShrink' => true,
          'fontSize' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("fontSize: 'min(16px, max(8px, 1vw))'")
      end
    end
  end

  describe 'linkable text rendering' do
    it 'renders URLs as anchor tags' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Visit https://example.com today',
        'linkable' => true
      })
      result = converter.convert
      expect(result).to include('<a href="https://example.com"')
      expect(result).to include('target="_blank"')
      expect(result).to include('rel="noopener noreferrer"')
      expect(result).to include('data-linkable="true"')
    end

    it 'handles multiple URLs' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Check https://foo.com and https://bar.com',
        'linkable' => true
      })
      result = converter.convert
      expect(result).to include('href="https://foo.com"')
      expect(result).to include('href="https://bar.com"')
    end
  end

  describe 'partialAttributes rendering' do
    it 'renders styled spans for text ranges' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          {
            'range' => [0, 5],
            'fontColor' => '#FF0000',
            'fontWeight' => 'bold'
          }
        ]
      })
      result = converter.convert
      expect(result).to include("<span style={{ color: '#FF0000', fontWeight: 'bold' }}>Hello</span>")
      expect(result).to include(' World')
    end

    it 'handles multiple partial attributes' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Red Green Blue',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontColor' => '#FF0000' },
          { 'range' => [4, 9], 'fontColor' => '#00FF00' },
          { 'range' => [10, 14], 'fontColor' => '#0000FF' }
        ]
      })
      result = converter.convert
      expect(result).to include("color: '#FF0000'")
      expect(result).to include("color: '#00FF00'")
      expect(result).to include("color: '#0000FF'")
    end

    it 'applies underline to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'underline' => true }
        ]
      })
      result = converter.convert
      expect(result).to include('className="underline"')
    end

    it 'applies strikethrough to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'strikethrough' => true }
        ]
      })
      result = converter.convert
      expect(result).to include('className="line-through"')
    end

    it 'applies onclick to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Click Here for more',
        'partialAttributes' => [
          { 'range' => [0, 10], 'onclick' => 'handlePartialClick' }
        ]
      })
      result = converter.convert
      expect(result).to include('onClick={handlePartialClick}')
      expect(result).to include('cursor-pointer')
    end

    it 'applies fontSize to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Big Text',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontSize' => 24 }
        ]
      })
      result = converter.convert
      expect(result).to include("fontSize: '24px'")
    end

    it 'applies background to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Highlighted',
        'partialAttributes' => [
          { 'range' => [0, 11], 'background' => '#FFFF00' }
        ]
      })
      result = converter.convert
      expect(result).to include("backgroundColor: '#FFFF00'")
    end
  end

  describe '#escape_jsx_text' do
    it 'escapes curly braces in text' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test {value}'
      })
      # Access private method
      result = converter.send(:escape_jsx_text, 'Test {value}')
      expect(result).to eq('{`Test {value}`}')
    end

    it 'escapes angle brackets' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'a < b > c'
      })
      result = converter.send(:escape_jsx_text, 'a < b > c')
      expect(result).to eq('{`a < b > c`}')
    end

    it 'returns plain text when no special characters' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Plain text'
      })
      result = converter.send(:escape_jsx_text, 'Plain text')
      expect(result).to eq('Plain text')
    end

    it 'escapes template literal characters' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Value: ${name}'
      })
      result = converter.send(:escape_jsx_text, 'Value: ${name}')
      expect(result).to include('\\${')
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test',
        'testId' => 'label-test-id'
      })
      result = converter.convert
      expect(result).to include('data-testid="label-test-id"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test',
        'tag' => 'custom-tag'
      })
      result = converter.convert
      expect(result).to include('data-tag="custom-tag"')
    end
  end
end
