# frozen_string_literal: true

# What each declared `input` value becomes on iOS, checked against the
# SSoT's own promise and against the UIKit enum.
#
# The declaration (attribute_definitions, TextField/input and TextView/input)
# writes the iOS degradation down:
#
#   "iOS: UIKeyboardType has no member for the date family, so they fall
#    back to .default, and signedDecimal to .numbersAndPunctuation"
#
# Only half of that was true. `date` / `time` / `datetime` do reach
# `.default` — `input_to_keyboard_type` is `KEYBOARD_TYPES[...] || '.default'`,
# so the fallback is real AND it emits the modifier explicitly rather than
# dropping it. `signedDecimal` fell through the same way, landing on a plain
# `.default`: not `.numbersAndPunctuation` as promised, and not even
# `decimal`'s `.decimalPad`.
#
# 🔻 TWO LAYERS, AND ONLY ONE OF THEM IS WHAT THE DECLARATION MEANS.
# `keyboard_type_to_swiftui` (textview_converter) reads the `keyboardType`
# ATTRIBUTE, has no `else`, and returns nil for anything unlisted. Reading
# that one and concluding "iOS emits nothing for the date family" is wrong
# about `input`, which is the attribute the sentence above is about. The
# same shape cost this train two other misreadings today, so the arms below
# name the function they exercise.
#
# ⚠️ SPELLING COMES FROM THE SDK, NOT FROM THE PLAN OR THE DECLARATION.
# The Android lane shipped against `KeyboardType.SignedDecimal`, which does
# not exist (the real member is `DecimalSigned`); their compiler caught it.
# Ruby has no compiler here, so `UI_KEYBOARD_TYPES` below is transcribed
# from UITextInputTraits.h and every emitted value is checked for membership
# — an expectation that merely repeats the implementation's string passes
# whatever the implementation says.

require 'json'
require 'swiftui/views/text_style_helper'

RSpec.describe 'input values on iOS' do
  SSOT = File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)

  # UIKeyboardType's members, from
  #   $(xcrun --sdk iphoneos --show-sdk-path)/System/Library/Frameworks/
  #   UIKit.framework/Headers/UITextInputTraits.h
  # lower-camel-cased the way Swift imports them.
  UI_KEYBOARD_TYPES = %w[
    .default .asciiCapable .numbersAndPunctuation .URL .numberPad .phonePad
    .namePhonePad .emailAddress .decimalPad .twitter .webSearch
    .asciiCapableNumberPad .alphabet
  ].freeze

  LANDING = {
    'default' => '.default',
    'alphabet' => '.asciiCapable',
    'allphabet' => '.asciiCapable',
    'email' => '.emailAddress',
    'number' => '.numberPad',
    'phone' => '.phonePad',
    'url' => '.URL',
    'password' => '.default',
    'decimal' => '.decimalPad',
    'signedDecimal' => '.numbersAndPunctuation',
    'date' => '.default',
    'time' => '.default',
    'datetime' => '.default'
  }.freeze

  # The helper is a module of instance methods; this is the smallest thing
  # that can call the one function under test.
  let(:helper) do
    Class.new { include SjuiTools::SwiftUI::Views::TextStyleHelper }.new
  end

  describe 'the enum is the population' do
    it 'every declared value has a decided landing place' do
      declared = JSON.parse(File.read(SSOT))['TextField']['input']['enum']
      expect(declared.sort).to eq(LANDING.keys.sort),
                               "undecided: #{(declared - LANDING.keys).inspect}; " \
                               "stale: #{(LANDING.keys - declared).inspect}"
    end

    it 'TextView declares the same vocabulary' do
      d = JSON.parse(File.read(SSOT))
      expect(d['TextView']['input']['enum']).to eq(d['TextField']['input']['enum'])
    end
  end

  describe 'input_to_keyboard_type (the `input` attribute path)' do
    LANDING.each do |value, keyboard|
      it "maps #{value} to #{keyboard}" do
        expect(helper.input_to_keyboard_type(value)).to eq(keyboard)
      end
    end

    it 'emits the fallback rather than dropping the modifier' do
      # `|| '.default'` — an unlisted value still produces a keyboardType.
      # This is what makes the declaration's "fall back to .default" true,
      # and it is a different behaviour from the `keyboardType` attribute
      # path, which returns nil and emits nothing.
      expect(helper.input_to_keyboard_type('no-such-input-value')).to eq('.default')
    end
  end

  describe 'the emitted value is a keyboard UIKit has' do
    LANDING.each_value do |keyboard|
      it "#{keyboard} is a real UIKeyboardType member" do
        expect(UI_KEYBOARD_TYPES).to include(keyboard)
      end
    end

    it 'every row of the shipped table is a real member, not just the declared ones' do
      table = SjuiTools::SwiftUI::Views::TextStyleHelper::KEYBOARD_TYPES
      bad = table.reject { |_, v| UI_KEYBOARD_TYPES.include?(v) }
      expect(bad).to be_empty, "not UIKeyboardType members: #{bad.inspect}"
    end

    it 'the member list is not an echo of what we emit' do
      emitted = LANDING.values.uniq
      expect((UI_KEYBOARD_TYPES - emitted).size).to be >= 3
      expect(UI_KEYBOARD_TYPES).to include('.asciiCapableNumberPad')
    end

    it 'plausible near-misses are absent, which is what makes it a check' do
      # `.signedDecimal` is the spelling the plan would suggest by analogy
      # with the Android member name. UIKit has no such thing.
      ['.signedDecimal', '.decimalSigned', '.numbersAndPunctuations',
       '.dateTime', '.date'].each do |wrong|
        expect(UI_KEYBOARD_TYPES).not_to include(wrong)
      end
    end
  end

  # 🔻 THE NEXT TWO ARMS ARE A PAIR; NEITHER IS REDUNDANT.
  # triage's mutation run (8 mutations, all red) measured which arm catches
  # what: deleting the `signeddecimal` row leaves "gets a keyboard that can
  # type a sign" GREEN, because signedDecimal falls to `.default` while
  # decimal keeps `.decimalPad` -- still different, just both wrong. The one
  # that catches deletion is "is not left on the bare fallback". Conversely a
  # row that collapsed onto `.decimalPad` is caught by the first and not the
  # second. Pruning either as a duplicate reopens one of the two holes.
  describe 'signedDecimal is not decimal on iOS' do
    it 'gets a keyboard that can type a sign' do
      # The whole point of the value. `.decimalPad` has no minus key, so
      # collapsing the two here would lose the only thing that distinguishes
      # them — unlike web, where the collapse is forced by the platform.
      expect(helper.input_to_keyboard_type('signedDecimal'))
        .not_to eq(helper.input_to_keyboard_type('decimal'))
    end

    it 'is not left on the bare fallback' do
      expect(helper.input_to_keyboard_type('signedDecimal')).not_to eq('.default')
    end
  end

  describe 'what these arms do not claim' do
    it 'input_to_keyboard_type returns the same keyboard for the date family, password and default' do
      # NOT a defect to fix by inventing a table row: UIKit has no date
      # keyboard. Recorded so a later reader does not "fix" it.
      #
      # ⚠️ THE SCOPE IS IN THE NAME OF THIS ARM ON PURPOSE. An earlier
      # version was called "...indistinguishable from password here", where
      # `here` meant this one function. That sentence is TRUE of the keyboard
      # argument and FALSE of the rendered view, and `here` is exactly the
      # word that falls off when a sentence is quoted into a declaration or a
      # release note. Same shape as the 1.8.78 dev-guide, where a limit put
      # in a subordinate clause shipped as an unqualified claim.
      #
      # What is actually true, measured on this tree:
      #   TextField  password -> `is_secure_field?` (text_field_binding_handler:50,
      #              one caller, textfield_converter:74) -> emits SecureField.
      #              A different VIEW, so password and date are distinguishable
      #              even though this function collapses them.
      #   TextView   no secure path at all (zero mentions), and `secure` is
      #              declared on TextField only -- so there the collapse is
      #              the whole rendering.
      # The value that collapses with the date family on BOTH components and
      # at every layer is `default`. Name that one when writing prose.
      %w[date time datetime password default].each do |v|
        expect(helper.input_to_keyboard_type(v)).to eq('.default')
      end
    end

    it 'the collapse is this function only -- TextField still picks a different view' do
      # The control for the arm above: if password stopped selecting
      # SecureField, the sentence "on TextField it is distinguishable" would
      # go quiet with nothing failing.
      handler_src = File.read(File.expand_path(
        '../../../lib/swiftui/binding/handlers/text_field_binding_handler.rb', __dir__
      ))
      expect(handler_src).to include('def is_secure_field?')
      expect(handler_src).to include("component['input'] == 'password'")

      # ...and that the TextField converter is what calls it. The rule only
      # holds because this one caller exists; TextView has none.
      field_src = File.read(File.expand_path(
        '../../../lib/swiftui/views/textfield_converter.rb', __dir__
      ))
      expect(field_src).to include('is_secure_field?')
      expect(field_src).to include('SecureField')

      view_src = File.read(File.expand_path(
        '../../../lib/swiftui/views/textview_converter.rb', __dir__
      ))
      expect(view_src).not_to include('SecureField'),
                              'TextView grew a secure path; the asymmetry this arm ' \
                              'records is gone and the prose above is now wrong'
    end
  end
end
