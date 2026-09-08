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
    # 🚨 THE CODE, NOT THE PROSE. Reported 2026-09-09 by a support lane with the
    # mutation already fired:
    #
    #   linkify_text.tsx:100  className={`${className} whitespace-pre-line`}
    #                         -> whitespace-normal   (the comment on :95 left alone)
    #   result   9 examples, 0 failures — the behaviour was gone and the arm
    #            that pins it stayed green, because :95 says the word too
    #
    # ⚠️ SHIPPING TEMPLATES ARE A VESSEL FOR PROSE. `linkify_text.tsx` carries
    # 22 lines of comment, `network_image.tsx` 35. A `.tsx` under `templates/`
    # is source that gets shipped, so an arm reading it is reading the same
    # mixture of code and explanation that bit `jui_tools` twice this week —
    # a fourth subject after shipping source, generated output and data.
    #
    # ⚠️ Comment-only lines are dropped; a `//` inside a string literal is NOT
    # a comment, so the cut tracks quotes. Naive `split('//')` would shorten
    # `href="https://…"`, which this very template builds.
    def code_only(text)
      out = []
      text.each_line do |line|
        code = +''
        quote = nil
        chars = line.chars
        i = 0
        while i < chars.length
          ch = chars[i]
          if quote
            if ch == '\\' && i + 1 < chars.length
              code << ch << chars[i + 1]
              i += 2
              next
            end
            quote = nil if ch == quote
          elsif ["'", '"', '`'].include?(ch)
            quote = ch
          elsif ch == '/' && chars[i + 1] == '/'
            break
          end
          code << ch
          i += 1
        end
        out << code unless code.strip.empty?
      end
      out.join("\n")
    end

    let(:raw) do
      File.read(File.expand_path('../../lib/react/templates/linkify_text.tsx', __dir__))
    end

    # Block comments first, then line comments — a `/* … */` spanning lines
    # would otherwise survive the per-line cut.
    #
    # ⚠️ EXTRACTED SO IT CAN BE ARMED. Inlined in `let(:template)`, a mutation
    # that removed the block-comment pass stayed GREEN: this particular
    # template happens to use `//` only, so the line filter caught everything
    # and the `/* */` pass was dead code in this tree. Dead today, load-bearing
    # the day someone writes a block comment — and by then no arm would have
    # noticed it was gone.
    def strip_comments(text)
      code_only(text.gsub(%r{/\*.*?\*/}m, ''))
    end

    #: What the arms below read.
    let(:template) { strip_comments(raw) }

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

    describe 'the comment filter itself' do
      # ⚠️ Without these, every arm above passes over a filter that removed
      # nothing (or removed everything). The subject of this describe block is
      # the instrument, not the template.

      it 'drops a comment-only line' do
        expect(code_only("// whitespace-pre-line is nice\nconst a = 1\n"))
          .to eq("const a = 1\n")
      end

      it 'drops a trailing comment but keeps the code before it' do
        expect(code_only("const a = 1 // whitespace-pre-line\n"))
          .to eq('const a = 1 ')
      end

      it 'does NOT cut inside a string literal' do
        # 🚨 This template BUILDS `https://` URLs. A naive split on `//`
        # would shorten them — a fix that introduces the defect class it
        # repairs.
        line = %(const u = "https://example.com"\n)
        expect(code_only(line)).to eq(%(const u = "https://example.com"\n))
      end

      it 'does not cut inside a template literal either' do
        line = "const c = `${x} https://y`\n"
        expect(code_only(line)).to eq("const c = `${x} https://y`\n")
      end

      it 'removes block comments before the per-line cut' do
        expect(template).not_to include('preserves newlines carried by bound values')
      end

      it 'removes a MULTI-LINE block comment' do
        # 🚨 The arm this pass actually needs. `linkify_text.tsx` uses `//`
        # only, so removing the block-comment pass left every other arm green
        # — the pass was untested precisely because this template does not
        # exercise it. Synthetic input is the only way to reach it.
        src = "const a = 1\n/* whitespace-pre-line\n   still inside */\nconst b = 2\n"

        expect(strip_comments(src)).not_to include('whitespace-pre-line')
        expect(strip_comments(src)).to include('const a = 1')
        expect(strip_comments(src)).to include('const b = 2')
      end

      it 'the control: the line filter alone does NOT remove it' do
        # ⚠️ Proves the block pass is what removes it, not `code_only`.
        src = "const a = 1\n/* whitespace-pre-line\n   still inside */\nconst b = 2\n"

        expect(code_only(src)).to include('whitespace-pre-line')
      end

      it 'the control: the spelling IS still present in the raw file' do
        # ⚠️ Proves the arm above is not passing because the comment was never
        # there. The filter is what removes it, not the fixture.
        expect(raw).to include('preserves newlines carried by bound values')
      end
    end
  end
end
