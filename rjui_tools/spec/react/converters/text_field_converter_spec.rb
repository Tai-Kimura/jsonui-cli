# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/text_field_converter'

RSpec.describe RjuiTools::React::Converters::TextFieldConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic text field' do
      it 'renders an input element' do
        converter = create_converter({
          'type' => 'TextField',
          'hint' => 'Enter text'
        })
        result = converter.convert
        expect(result).to include('<input')
        expect(result).to include('placeholder="Enter text"')
        expect(result).to include('/>')
      end
    end

    context 'with placeholder alias' do
      it 'uses placeholder as hint' do
        converter = create_converter({
          'type' => 'TextField',
          'placeholder' => 'Type here'
        })
        result = converter.convert
        expect(result).to include('placeholder="Type here"')
      end
    end

    context 'with text binding' do
      it 'converts binding to controlled component (value + onChange)' do
        converter = create_converter({
          'type' => 'TextField',
          'text' => '@{username}'
        })
        result = converter.convert
        expect(result).to include('value={data.username}')
        expect(result).to include('onChange={(e) => data.onUsernameChange?.(e.target.value)}')
      end
    end

    context 'with static text' do
      it 'uses defaultValue for non-binding text' do
        converter = create_converter({
          'type' => 'TextField',
          'text' => 'Initial value'
        })
        result = converter.convert
        expect(result).to include('defaultValue="Initial value"')
      end
    end
  end

  describe '#determine_input_type' do
    context 'with email input' do
      it 'sets type to email' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'email'
        })
        result = converter.convert
        expect(result).to include('type="email"')
      end
    end

    context 'with password input' do
      it 'sets type to password' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'password'
        })
        result = converter.convert
        expect(result).to include('type="password"')
      end
    end

    context 'with secure attribute' do
      it 'sets type to password' do
        converter = create_converter({
          'type' => 'TextField',
          'secure' => true
        })
        result = converter.convert
        expect(result).to include('type="password"')
      end
    end

    context 'with number input' do
      it 'sets type to number' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'number'
        })
        result = converter.convert
        expect(result).to include('type="number"')
      end
    end

    context 'with tel input' do
      it 'sets type to tel' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'tel'
        })
        result = converter.convert
        expect(result).to include('type="tel"')
      end
    end

    context 'with url input' do
      it 'sets type to url' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'URL'
        })
        result = converter.convert
        expect(result).to include('type="url"')
      end
    end

    context 'with search input' do
      it 'sets type to search' do
        converter = create_converter({
          'type' => 'TextField',
          'input' => 'webSearch'
        })
        result = converter.convert
        expect(result).to include('type="search"')
      end
    end
  end

  describe '#build_class_name' do
    context 'with borderStyle roundedRect' do
      it 'adds rounded-md class' do
        converter = create_converter({
          'type' => 'TextField',
          'borderStyle' => 'roundedRect'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('rounded-md')
      end
    end

    context 'with borderStyle line' do
      it 'adds bottom border only classes' do
        converter = create_converter({
          'type' => 'TextField',
          'borderStyle' => 'line'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('border-b')
        expect(classes).to include('border-t-0')
      end
    end

    context 'with borderStyle none' do
      it 'adds border-0 class' do
        converter = create_converter({
          'type' => 'TextField',
          'borderStyle' => 'none'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('border-0')
      end
    end

    context 'with default styles' do
      it 'includes focus ring styles' do
        converter = create_converter({
          'type' => 'TextField'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('focus:ring-2')
        expect(classes).to include('focus:ring-blue-500')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with cornerRadius' do
      it 'adds borderRadius style' do
        converter = create_converter({
          'type' => 'TextField',
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
          'type' => 'TextField',
          'hintColor' => '#999999'
        })
        result = converter.send(:build_class_name)
        expect(result).to include('placeholder-#999999')
      end
    end

    context 'with caretAttributes' do
      it 'adds caretColor style' do
        converter = create_converter({
          'type' => 'TextField',
          'caretAttributes' => { 'fontColor' => '#FF0000' }
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("caretColor: '#FF0000'")
      end
    end

    context 'with textPaddingLeft' do
      it 'adds paddingLeft style' do
        converter = create_converter({
          'type' => 'TextField',
          'textPaddingLeft' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("paddingLeft: '16px'")
      end
    end

    context 'with shadow object' do
      it 'adds boxShadow style' do
        converter = create_converter({
          'type' => 'TextField',
          'shadow' => {
            'radius' => 4,
            'offsetX' => 0,
            'offsetY' => 2,
            'color' => 'rgba(0,0,0,0.1)'
          }
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("boxShadow: '0px 2px 4px rgba(0,0,0,0.1)'")
      end
    end

    context 'with shadow boolean' do
      it 'adds default boxShadow' do
        converter = create_converter({
          'type' => 'TextField',
          'shadow' => true
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("boxShadow:")
      end
    end
  end

  describe '#map_content_type' do
    it 'maps username to username' do
      converter = create_converter({ 'type' => 'TextField', 'contentType' => 'username' })
      result = converter.convert
      expect(result).to include('autoComplete="username"')
    end

    it 'maps password to current-password' do
      converter = create_converter({ 'type' => 'TextField', 'contentType' => 'password' })
      result = converter.convert
      expect(result).to include('autoComplete="current-password"')
    end

    it 'maps email to email' do
      converter = create_converter({ 'type' => 'TextField', 'contentType' => 'email' })
      result = converter.convert
      expect(result).to include('autoComplete="email"')
    end

    it 'maps tel to tel' do
      converter = create_converter({ 'type' => 'TextField', 'contentType' => 'tel' })
      result = converter.convert
      expect(result).to include('autoComplete="tel"')
    end
  end

  describe '#map_input_mode' do
    it 'maps number to numeric inputMode' do
      converter = create_converter({ 'type' => 'TextField', 'input' => 'number' })
      result = converter.convert
      expect(result).to include('inputMode="numeric"')
    end

    it 'maps decimal to decimal inputMode' do
      converter = create_converter({ 'type' => 'TextField', 'input' => 'decimal' })
      result = converter.convert
      expect(result).to include('inputMode="decimal"')
    end

    it 'maps email to email inputMode' do
      converter = create_converter({ 'type' => 'TextField', 'input' => 'email' })
      result = converter.convert
      expect(result).to include('inputMode="email"')
    end
  end

  describe '#map_return_key' do
    it 'maps Done to done enterKeyHint' do
      converter = create_converter({ 'type' => 'TextField', 'returnKeyType' => 'Done' })
      result = converter.convert
      expect(result).to include('enterKeyHint="done"')
    end

    it 'maps Search to search enterKeyHint' do
      converter = create_converter({ 'type' => 'TextField', 'returnKeyType' => 'Search' })
      result = converter.convert
      expect(result).to include('enterKeyHint="search"')
    end

    it 'maps Next to next enterKeyHint' do
      converter = create_converter({ 'type' => 'TextField', 'returnKeyType' => 'Next' })
      result = converter.convert
      expect(result).to include('enterKeyHint="next"')
    end
  end

  describe '#build_on_change' do
    it 'adds onChange handler' do
      converter = create_converter({
        'type' => 'TextField',
        'onTextChange' => 'handleChange'
      })
      result = converter.convert
      expect(result).to include('onChange={(e) => handleChange?.(e.target.value)}')
    end

    it 'handles binding expression in onChange' do
      converter = create_converter({
        'type' => 'TextField',
        'onTextChange' => '@{handleTextChange}'
      })
      result = converter.convert
      expect(result).to include('onChange={(e) => data.handleTextChange?.(e.target.value)}')
    end
  end

  describe '#build_disabled_attr' do
    it 'adds disabled when enabled is false' do
      converter = create_converter({
        'type' => 'TextField',
        'enabled' => false
      })
      result = converter.convert
      expect(result).to include(' disabled')
    end

    it 'adds disabled binding expression' do
      converter = create_converter({
        'type' => 'TextField',
        'enabled' => '@{isEditable}'
      })
      result = converter.convert
      expect(result).to include(%q(disabled={!data.isEditable}))
    end
  end

  describe 'other attributes' do
    it 'adds maxLength attribute' do
      converter = create_converter({
        'type' => 'TextField',
        'maxLength' => 100
      })
      result = converter.convert
      expect(result).to include('maxLength={100}')
    end

    it 'adds autoFocus attribute' do
      converter = create_converter({
        'type' => 'TextField',
        'autoFocus' => true
      })
      result = converter.convert
      expect(result).to include('autoFocus')
    end

    it 'adds readOnly when editable is false' do
      converter = create_converter({
        'type' => 'TextField',
        'editable' => false
      })
      result = converter.convert
      expect(result).to include('readOnly')
    end

    it 'adds name attribute' do
      converter = create_converter({
        'type' => 'TextField',
        'name' => 'email_field'
      })
      result = converter.convert
      expect(result).to include('name="email_field"')
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'TextField',
        'testId' => 'email-input'
      })
      result = converter.convert
      expect(result).to include('data-testid="email-input"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'TextField',
        'tag' => 'login-field'
      })
      result = converter.convert
      expect(result).to include('data-tag="login-field"')
    end
  end
  # Focus-state binding — cross-platform parity with sjui/kjui data.<id>IsFocused.
  describe 'focus-state binding attrs' do
    it 'attaches ref + focus report-back handlers for an id-bearing field' do
      converter = create_converter({ 'type' => 'TextField', 'id' => 'email_field' })
      result = converter.convert
      expect(result).to include('ref={emailFieldRef}')
      expect(result).to include('onFocus={() => data.onEmailFieldIsFocusedChange?.(true)}')
      expect(result).to include('onBlur={() => data.onEmailFieldIsFocusedChange?.(false)}')
    end

    it 'emits no focus attrs for an id-less field' do
      converter = create_converter({ 'type' => 'TextField' })
      result = converter.convert
      expect(result).not_to include('ref={')
      expect(result).not_to include('IsFocusedChange')
    end
  end
end

