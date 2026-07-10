# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/text_view_converter'

RSpec.describe RjuiTools::React::Converters::TextViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic text view' do
      it 'renders a textarea element' do
        converter = create_converter({
          'type' => 'TextView',
          'hint' => 'Enter description'
        })
        result = converter.convert
        expect(result).to include('<textarea')
        expect(result).to include('placeholder="Enter description"')
        expect(result).to include('</textarea>')
      end
    end

    context 'with placeholder alias' do
      it 'uses placeholder as hint' do
        converter = create_converter({
          'type' => 'TextView',
          'placeholder' => 'Type your message'
        })
        result = converter.convert
        expect(result).to include('placeholder="Type your message"')
      end
    end

    context 'with text binding' do
      it 'converts binding to controlled component (value + auto-generated onChange)' do
        converter = create_converter({
          'type' => 'TextView',
          'text' => '@{description}'
        })
        result = converter.convert
        expect(result).to include('value={data.description}')
        expect(result).to include('onChange={(e) => data.onDescriptionChange?.(e.target.value)}')
      end
    end

    context 'with static text' do
      it 'uses defaultValue for non-binding text' do
        converter = create_converter({
          'type' => 'TextView',
          'text' => 'Initial content'
        })
        result = converter.convert
        expect(result).to include('defaultValue="Initial content"')
      end
    end
  end

  describe '#build_class_name' do
    context 'with default styles' do
      it 'includes border and focus styles' do
        converter = create_converter({
          'type' => 'TextView'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('border')
        expect(classes).to include('focus:ring-2')
        expect(classes).to include('focus:ring-blue-500')
      end

      it 'includes resize-none by default' do
        converter = create_converter({
          'type' => 'TextView'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('resize-none')
      end

      it 'includes overflow-auto by default' do
        converter = create_converter({
          'type' => 'TextView'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-auto')
      end
    end

    context 'with resize enabled' do
      it 'does not include resize-none' do
        converter = create_converter({
          'type' => 'TextView',
          'resize' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('resize-none')
      end
    end

    context 'with flexible' do
      it 'adds resize-y class' do
        converter = create_converter({
          'type' => 'TextView',
          'flexible' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('resize-y')
      end
    end

    context 'with scrollEnabled false' do
      it 'does not include overflow-auto' do
        converter = create_converter({
          'type' => 'TextView',
          'scrollEnabled' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('overflow-auto')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with cornerRadius' do
      it 'adds borderRadius style' do
        converter = create_converter({
          'type' => 'TextView',
          'cornerRadius' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("borderRadius: '8px'")
      end
    end

    context 'with hintColor' do
      it 'adds placeholder color via Tailwind class' do
        converter = create_converter({
          'type' => 'TextView',
          'hintColor' => '#999999'
        })
        result = converter.send(:build_class_name)
        expect(result).to include('placeholder-#999999')
      end
    end

    context 'with hintAttributes' do
      it 'extracts fontColor from hintAttributes as Tailwind class' do
        converter = create_converter({
          'type' => 'TextView',
          'hintAttributes' => { 'fontColor' => '#888888' }
        })
        result = converter.send(:build_class_name)
        expect(result).to include('placeholder-#888888')
      end
    end

    context 'with containerInset' do
      it 'handles single value' do
        converter = create_converter({
          'type' => 'TextView',
          'containerInset' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '16px'")
      end

      it 'handles 2-element array' do
        converter = create_converter({
          'type' => 'TextView',
          'containerInset' => [10, 20]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px'")
      end

      it 'handles 4-element array' do
        converter = create_converter({
          'type' => 'TextView',
          'containerInset' => [10, 20, 30, 40]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end
    end

    context 'with minHeight and maxHeight' do
      it 'adds minHeight style' do
        converter = create_converter({
          'type' => 'TextView',
          'minHeight' => 100
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("minHeight: '100px'")
      end

      it 'adds maxHeight style' do
        converter = create_converter({
          'type' => 'TextView',
          'maxHeight' => 300
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("maxHeight: '300px'")
      end
    end

    context 'with border' do
      it 'adds border styles' do
        converter = create_converter({
          'type' => 'TextView',
          'borderWidth' => 2,
          'borderColor' => '#CCCCCC'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("borderWidth: '2px'")
        expect(result).to include("borderColor: '#CCCCCC'")
        expect(result).to include("borderStyle: 'solid'")
      end
    end
  end

  describe '#build_attributes' do
    context 'with rows/lines' do
      it 'adds rows attribute from lines' do
        converter = create_converter({
          'type' => 'TextView',
          'lines' => 5
        })
        result = converter.convert
        expect(result).to include('rows={5}')
      end

      it 'adds rows attribute from rows' do
        converter = create_converter({
          'type' => 'TextView',
          'rows' => 3
        })
        result = converter.convert
        expect(result).to include('rows={3}')
      end
    end

    context 'with maxLength' do
      it 'adds maxLength attribute' do
        converter = create_converter({
          'type' => 'TextView',
          'maxLength' => 500
        })
        result = converter.convert
        expect(result).to include('maxLength={500}')
      end
    end

    context 'with editable false' do
      it 'adds readOnly attribute' do
        converter = create_converter({
          'type' => 'TextView',
          'editable' => false
        })
        result = converter.convert
        expect(result).to include('readOnly')
      end
    end

    context 'with readOnly' do
      it 'adds readOnly attribute' do
        converter = create_converter({
          'type' => 'TextView',
          'readOnly' => true
        })
        result = converter.convert
        expect(result).to include('readOnly')
      end
    end

    context 'with autoFocus' do
      it 'adds autoFocus attribute' do
        converter = create_converter({
          'type' => 'TextView',
          'autoFocus' => true
        })
        result = converter.convert
        expect(result).to include('autoFocus')
      end
    end

    context 'with name' do
      it 'adds name attribute' do
        converter = create_converter({
          'type' => 'TextView',
          'name' => 'message_field'
        })
        result = converter.convert
        expect(result).to include('name="message_field"')
      end
    end
  end

  describe '#build_on_change' do
    it 'adds onChange handler' do
      converter = create_converter({
        'type' => 'TextView',
        'onTextChange' => 'handleTextChange'
      })
      result = converter.convert
      expect(result).to include('onChange={(e) => handleTextChange?.(e.target.value)}')
    end

    it 'handles binding expression in onChange' do
      converter = create_converter({
        'type' => 'TextView',
        'onTextChange' => '@{updateDescription}'
      })
      result = converter.convert
      expect(result).to include('onChange={(e) => data.updateDescription?.(e.target.value)}')
    end
  end

  describe '#build_disabled_attr' do
    it 'adds disabled when enabled is false' do
      converter = create_converter({
        'type' => 'TextView',
        'enabled' => false
      })
      result = converter.convert
      expect(result).to include(' disabled')
    end

    it 'adds disabled binding expression' do
      converter = create_converter({
        'type' => 'TextView',
        'enabled' => '@{canEdit}'
      })
      result = converter.convert
      expect(result).to include(%q(disabled={!data.canEdit}))
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'TextView',
        'testId' => 'description-input'
      })
      result = converter.convert
      expect(result).to include('data-testid="description-input"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'TextView',
        'tag' => 'comment-field'
      })
      result = converter.convert
      expect(result).to include('data-tag="comment-field"')
    end
  end
  # Focus-state binding — cross-platform parity with sjui/kjui data.<id>IsFocused.
  describe 'focus-state binding attrs' do
    it 'attaches ref + focus report-back handlers for an id-bearing textarea' do
      converter = described_class.new({ 'type' => 'TextView', 'id' => 'note_input' }, { 'use_tailwind' => true })
      result = converter.convert
      expect(result).to include('ref={noteInputRef}')
      expect(result).to include('onFocus={() => data.onNoteInputIsFocusedChange?.(true)}')
      expect(result).to include('onBlur={() => data.onNoteInputIsFocusedChange?.(false)}')
    end
  end
end

