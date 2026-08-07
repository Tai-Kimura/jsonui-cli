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

    context 'with a strings.json key as hint (regression: rjui-textfield-hint-string-key-not-resolved)' do
      it 'resolves the key through StringManager like sjui does' do
        converter = create_converter({
          'type' => 'TextField',
          'hint' => 'staff_auth_6_digit_code'
        })
        allow(converter).to receive(:convert_string_key)
          .with('staff_auth_6_digit_code')
          .and_return('{StringManager.currentLanguage.staffAuth6DigitCode}')
        result = converter.convert
        expect(result).to include('placeholder={StringManager.currentLanguage.staffAuth6DigitCode}')
      end

      it 'leaves unregistered keys as plain literals' do
        converter = create_converter({
          'type' => 'TextField',
          'hint' => 'not_a_registered_key'
        })
        allow(converter).to receive(:convert_string_key).and_return(nil)
        result = converter.convert
        expect(result).to include('placeholder="not_a_registered_key"')
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
      # `placeholder-#999999` is not a Tailwind class. The conformance host
      # generates a `.placeholder-dark_red::placeholder` shim, so the
      # palette-named spelling rendered and hid this — the hex spelling every
      # consumer writes resolved to nothing.
      it 'adds placeholder color as an arbitrary Tailwind value' do
        converter = create_converter({
          'type' => 'TextField',
          'hintColor' => '#999999'
        })
        result = converter.send(:build_class_name)
        expect(result).to include('placeholder-[#999999]')
        expect(result).not_to include('placeholder-#999999')
      end

      it 'reads placeholderColor as the alias of hintColor' do
        converter = create_converter({
          'type' => 'TextField',
          'placeholderColor' => '#999999'
        })
        expect(converter.send(:build_class_name)).to include('placeholder-[#999999]')
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
  describe 'validation and keyboard traits' do
    # Both are declared `platform: react`, i.e. they exist FOR the web.
    it 'emits native pattern and required' do
      result = create_converter({
        'type' => 'TextField', 'pattern' => '[0-9]{3}', 'required' => true
      }).convert

      expect(result).to include('pattern="[0-9]{3}"')
      expect(result).to include(' required')
    end

    it 'escapes a quote in the pattern so the attribute cannot be broken out of' do
      result = create_converter({ 'type' => 'TextField', 'pattern' => 'a"b' }).convert
      expect(result).to include('pattern="a&quot;b"')
    end

    it 'maps the UIKit autocapitalization spellings to HTML values' do
      {
        'None' => 'off', 'Words' => 'words', 'Sentences' => 'sentences',
        'AllCharacters' => 'characters'
      }.each do |declared, expected|
        result = create_converter({
          'type' => 'TextField', 'autocapitalizationType' => declared
        }).convert
        expect(result).to include("autoCapitalize=\"#{expected}\"")
      end
    end

    it 'turns autocorrect and spellcheck off together' do
      result = create_converter({ 'type' => 'TextField', 'autocorrectionType' => 'No' }).convert
      expect(result).to include('autoCorrect="off"')
      expect(result).to include('spellCheck={false}')
    end

    it 'leaves the browser default alone for an unmapped value' do
      result = create_converter({ 'type' => 'TextField', 'autocorrectionType' => 'Default' }).convert
      expect(result).not_to include('autoCorrect')
    end
  end

  describe 'focus and submit handlers' do
    # React props replace rather than accumulate, so a second onFocus would
    # silently drop the id-derived focus-state binding.
    it 'merges a declared handler with the focus-state binding' do
      result = create_converter({
        'type' => 'TextField', 'id' => 'email_field', 'onFocus' => '@{didFocus}'
      }).convert

      expect(result.scan('onFocus=').length).to eq(1)
      expect(result).to include('data.onEmailFieldIsFocusedChange?.(true); data.didFocus?.();')
    end

    it 'fires both the web and the UIKit spelling, in declaration order' do
      result = create_converter({
        'type' => 'TextField', 'onFocus' => 'a', 'onBeginEditing' => 'b',
        'onBlur' => 'c', 'onEndEditing' => 'd'
      }).convert

      expect(result).to include('onFocus={() => { data.a?.(); data.b?.(); }}')
      expect(result).to include('onBlur={() => { data.c?.(); data.d?.(); }}')
    end

    it 'leaves the single-handler form as a bare expression' do
      result = create_converter({ 'type' => 'TextField', 'id' => 'email_field' }).convert
      expect(result).to include('onFocus={() => data.onEmailFieldIsFocusedChange?.(true)}')
    end

    # HTML onSubmit is a form event, not an input one.
    it 'binds onSubmit to the Enter key' do
      result = create_converter({ 'type' => 'TextField', 'onSubmit' => '@{submitForm}' }).convert
      expect(result).to include("onKeyDown={(e) => { if (e.key === 'Enter') { data.submitForm?.(); } }}")
    end

    it 'emits no handler when none is declared' do
      result = create_converter({ 'type' => 'TextField' }).convert
      expect(result).not_to include('onKeyDown')
      expect(result).not_to include('onFocus')
    end
  end
end

RSpec.describe RjuiTools::React::Converters::TextFieldConverter, 'nextFocus' do
  let(:config) { { 'use_tailwind' => true } }

  def field(extra)
    described_class.new({ 'class' => 'TextField', 'id' => 'email' }.merge(extra), config).convert(2)
  end

  # The target's ref is the one ReactGenerator already hoists for every editable
  # field with a literal id.
  it 'focuses the named field on Enter' do
    expect(field('nextFocus' => 'password_field'))
      .to include("onKeyDown={(e) => { if (e.key === 'Enter') { passwordFieldRef.current?.focus(); } }}")
  end

  # These are React props: a second onKeyDown replaces the first rather than
  # adding a listener, so both have to live in one handler.
  it 'runs the chain before the author handler, in one handler' do
    result = field('nextFocus' => 'password_field', 'onSubmit' => '@{submit}')
    expect(result.scan('onKeyDown=').length).to eq(1)
    expect(result).to include("{ passwordFieldRef.current?.focus(); data.submit?.(); }")
  end

  it 'still emits the author handler alone' do
    expect(field('onSubmit' => '@{submit}'))
      .to include("onKeyDown={(e) => { if (e.key === 'Enter') { data.submit?.(); } }}")
  end

  # A binding-form id has no ref to reach for.
  it 'skips a binding target and emits nothing when absent' do
    expect(field('nextFocus' => '@{nextId}')).not_to include('onKeyDown')
    expect(field({})).not_to include('onKeyDown')
  end
end

# Declared for TextField as well as TextView (SSoT), and only TextView read it.
# `::placeholder` is a pseudo-element, so the class variant is the only surface
# that reaches it — the same one TextViewConverter uses.
RSpec.describe RjuiTools::React::Converters::TextFieldConverter, 'hintLineHeightMultiple' do
  def field(extra)
    described_class.new({ 'class' => 'TextField', 'id' => 'email', 'hint' => 'Sample' }.merge(extra),
                        { 'use_tailwind' => true }).convert(2)
  end

  it 'carries the placeholder line height' do
    expect(field('hintLineHeightMultiple' => 3)).to include('placeholder:leading-[3]')
  end

  it 'emits nothing when it is not declared' do
    expect(field({})).not_to include('placeholder:leading')
  end
end
