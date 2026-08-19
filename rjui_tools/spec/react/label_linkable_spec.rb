# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/converters/label_converter'

# Label `linkable` canon (rjui-label-linkable-binding-renders-raw):
# both text shapes — literal and bound — render through the LinkifyText
# built-in, whose runtime detection is what makes the declared URL/phone
# auto-linking work for bound values at all. The converter's job is only to
# hand the text over correctly; detection, tel: sanitization and newline
# preservation are pinned on the template below.
RSpec.describe 'Label linkable' do
  def convert(node, config = { 'use_tailwind' => true })
    RjuiTools::React::Converters::LabelConverter.new(node, config).convert
  end

  describe 'bound text' do
    let(:jsx) { convert({ 'type' => 'Label', 'linkable' => true, 'text' => '@{notesText}' }) }

    it 'hands the resolved binding to LinkifyText — never the raw @{...} literal' do
      expect(jsx).to include('<LinkifyText')
      expect(jsx).to include('text={data.notesText}')
      expect(jsx).not_to include('@{')
    end
  end

  describe 'interpolated bound text' do
    it 'hands over a template literal with the binding resolved' do
      jsx = convert({ 'type' => 'Label', 'linkable' => true, 'text' => 'お問い合わせ: @{contactPhone}' })
      expect(jsx).to include('text={`お問い合わせ: ${data.contactPhone}`}')
      expect(jsx).not_to include('@{')
    end
  end

  describe 'literal text' do
    it 'hands the escaped literal to the same runtime (one implementation, both shapes)' do
      jsx = convert({ 'type' => 'Label', 'linkable' => true,
                      'text' => 'See https://example.com or call 03-1234-5678' })
      expect(jsx).to include('<LinkifyText')
      expect(jsx).to include('text={`See https://example.com or call 03-1234-5678`}')
      # Build-time <a> emission is gone — detection is the template's job.
      expect(jsx).not_to include('<a href')
    end
  end

  describe 'bound linkable flag' do
    it 'keeps the runtime ternary, with the ON arm on LinkifyText' do
      jsx = convert({ 'type' => 'Label', 'linkable' => '@{isLinkable}', 'text' => '@{notesText}' })
      expect(jsx).to include('data.isLinkable')
      expect(jsx).to include('<LinkifyText')
      expect(jsx).not_to include('@{')
    end
  end

  describe 'LinkifyText template (runtime canon pins)' do
    let(:template) do
      File.read(File.expand_path('../../lib/react/templates/linkify_text.tsx', __dir__))
    end

    it 'detects phone numbers with digit-count bounds (declared URL/phone semantics)' do
      expect(template).to include('PHONE_PATTERN')
      expect(template).to include('MIN_PHONE_DIGITS = 8')
      expect(template).to include('MAX_PHONE_DIGITS = 15')
    end

    it 'builds tel: from digits and leading + only — no scheme injection surface' do
      expect(template).to match(/tel:.*\$\{plus\}\$\{candidate\.replace\(\/\\D\/g, ''\)\}/)
    end

    it 'opens URLs with the noopener/noreferrer contract' do
      expect(template).to include('rel="noopener noreferrer"')
    end

    it 'preserves newlines in bound values (whitespace-pre-line on the root)' do
      expect(template).to include('whitespace-pre-line')
    end

    it 'keeps the data-linkable marker for test hooks' do
      expect(template).to include('data-linkable="true"')
    end
  end
end
