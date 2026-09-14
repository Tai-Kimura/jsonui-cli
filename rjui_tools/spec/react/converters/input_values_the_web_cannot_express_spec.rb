# frozen_string_literal: true

# `input` gained four values in 1.8.8x -- signedDecimal, date, time,
# datetime -- and web can express none of them the way the keyboard-shaped
# name suggests. The landing places are DECLARED in the SSoT's own
# `description`, so the contract is written down before any of the three
# faces implemented it; this file pins that web does what the declaration
# says, in both directions.
#
# The population is the SSoT's `enum`, not a list retyped here: a
# fourteenth value added upstream fails `the enum is the population`
# rather than silently landing on `text` with nobody looking.
#
# 🔻 TWO OF THESE ARMS EXIST TO STOP A "BETTER" IMPLEMENTATION.
# `signedDecimal` must be INDISTINGUISHABLE from `decimal` on web -- HTML
# has no signed-decimal input, `number` already takes a leading minus, and
# `inputmode` has no signed token. An implementation that invents a
# difference (a pattern attribute, a `step`, a custom data-*) would look
# like an improvement and would put the two values into a state the
# platform cannot round-trip. Same for the textarea: it has no `type`
# attribute at all, so date/time/datetime CANNOT degrade to anything but
# a plain textarea, and an implementation that reaches for a wrapper or a
# hidden input to fake it is out of contract.
#
# ⚠️ THE SPELLING IS `inputMode`, NOT `inputmode`. The first measurement
# written for this change grepped the HTML spelling, found zero across all
# thirteen values, and read as "the mapping is never called" -- one step
# from deleting a working path. The emitter writes the JSX attribute. The
# positive control below fails loudly if that ever stops being true, so
# the same misreading cannot come back as a silently empty table.

require_relative '../../spec_helper'
require 'json'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'

RSpec.describe 'input values web cannot express natively' do
  SSOT_PATH = File.expand_path(
    '../../../../shared/core/attribute_definitions.json', __dir__
  )

  # value => [<input type>, <input inputMode>, <textarea inputMode>]
  # A textarea's `type` column is absent from this table on purpose: there
  # is no such attribute, and `the textarea never grows a type` asserts it
  # for every value at once.
  LANDING = {
    'default'       => ['text',           nil,       nil],
    'alphabet'      => ['text',           'text',    'text'],
    'allphabet'     => ['text',           'text',    'text'],
    'email'         => ['email',          'email',   'email'],
    'number'        => ['number',         'numeric', 'numeric'],
    'phone'         => ['tel',            'tel',     'tel'],
    'url'           => ['url',            'url',     'url'],
    'password'      => ['password',       nil,       nil],
    'decimal'       => ['number',         'decimal', 'decimal'],
    'signedDecimal' => ['number',         'decimal', 'decimal'],
    'date'          => ['date',           nil,       nil],
    'time'          => ['time',           nil,       nil],
    'datetime'      => ['datetime-local', nil,       nil]
  }.freeze

  let(:config) { { 'use_tailwind' => true } }

  def field(value)
    RjuiTools::React::Converters::TextFieldConverter
      .new({ 'type' => 'TextField', 'input' => value }, config).convert
  end

  def area(value)
    RjuiTools::React::Converters::TextViewConverter
      .new({ 'type' => 'TextView', 'input' => value }, config).convert
  end

  def attr_of(html, name)
    html[/\b#{name}="([^"]*)"/, 1]
  end

  describe 'the instrument itself' do
    it 'reads the attribute the emitter actually writes' do
      # Positive control. `inputmode` (lowercase) matches nothing here; if
      # this arm ever goes red, every nil in LANDING became unfalsifiable.
      html = field('number')
      expect(attr_of(html, 'inputMode')).to eq('numeric')
      expect(html).to include('inputMode=')
      expect(html).not_to include('inputmode=')
    end

    it 'can tell a present attribute from an absent one' do
      expect(attr_of(field('number'), 'inputMode')).not_to be_nil
      expect(attr_of(field('date'), 'inputMode')).to be_nil
    end
  end

  describe 'the enum is the population' do
    it 'every declared value has a decided landing place' do
      ssot = JSON.parse(File.read(SSOT_PATH))
      declared = ssot['TextField']['input']['enum']
      expect(declared.sort).to eq(LANDING.keys.sort),
                               "undecided: #{(declared - LANDING.keys).inspect}; " \
                               "stale: #{(LANDING.keys - declared).inspect}"
    end

    it 'TextView declares the same vocabulary, so one table serves both' do
      ssot = JSON.parse(File.read(SSOT_PATH))
      expect(ssot['TextView']['input']['enum'])
        .to eq(ssot['TextField']['input']['enum'])
    end
  end

  describe 'TextField' do
    LANDING.each do |value, (type, mode, _)|
      it "maps #{value} to type=#{type.inspect} inputMode=#{mode.inspect}" do
        html = field(value)
        expect(attr_of(html, 'type')).to eq(type)
        expect(attr_of(html, 'inputMode')).to eq(mode)
      end
    end

    it 'reaches the element type for the three date-like values' do
      # They are not `inputmode` tokens -- that vocabulary has nothing
      # date-shaped in it -- so the only place they can land is the element
      # type, which is the path SelectBox's datepicker already takes.
      %w[date time datetime].each do |value|
        expect(attr_of(field(value), 'inputMode')).to be_nil
        expect(attr_of(field(value), 'type')).not_to eq('text')
      end
    end
  end

  describe 'TextView renders a textarea' do
    it 'never grows a type attribute, whatever the input value is' do
      LANDING.each_key do |value|
        html = area(value)
        expect(html).to include('<textarea')
        expect(attr_of(html, 'type')).to be_nil, "#{value} put a type on a textarea"
      end
    end

    LANDING.each do |value, (_, _, mode)|
      it "maps #{value} to inputMode=#{mode.inspect}" do
        expect(attr_of(area(value), 'inputMode')).to eq(mode)
      end
    end

    it 'degrades the three date-like values to a plain textarea' do
      # Nothing left to carry them: no type attribute, and no inputmode
      # token. This is the declared degradation, so an implementation that
      # fakes it with a wrapper or a hidden input is out of contract.
      %w[date time datetime].each do |value|
        html = area(value)
        expect(attr_of(html, 'inputMode')).to be_nil
        expect(attr_of(html, 'type')).to be_nil
      end
    end
  end

  describe 'signedDecimal is indistinguishable from decimal on web' do
    it 'lands identically in both layers' do
      expect(LANDING['signedDecimal']).to eq(LANDING['decimal'])
    end

    it 'produces byte-identical markup in an input' do
      expect(field('signedDecimal')).to eq(field('decimal'))
    end

    it 'produces byte-identical markup in a textarea' do
      expect(area('signedDecimal')).to eq(area('decimal'))
    end

    it 'is a declared degradation, not an omission' do
      # If the SSoT stops saying so, this collapse becomes an unexplained
      # behaviour and the arms above turn into its only justification.
      ssot = JSON.parse(File.read(SSOT_PATH))
      description = ssot['TextField']['input']['description']
      expect(description).to include('signedDecimal').or include('degradation')
    end
  end
end
