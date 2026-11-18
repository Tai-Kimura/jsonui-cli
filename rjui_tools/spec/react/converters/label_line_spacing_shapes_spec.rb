# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/label_converter'

# lineSpacing on every Label shape. The plain text sits in a block whose
# negative block margins take back the half spacing above the first line and
# below the last (LabelConverter#line_spacing_wrap; user ruling B,
# 2026-10-05: between lines only). Through jsonui-cli 2.5.51 the
# partialAttributes shape and the linkable shape did not, and each was one
# spacing taller than the plain Label (184 -> 200 for five lines of 24 with a
# spacing of 16).
RSpec.describe 'Label lineSpacing on every shape' do
  def convert(node)
    RjuiTools::React::Converters::LabelConverter.new(node, { 'use_tailwind' => true }).convert
  end

  let(:block) { "<span style={{ display: 'block', marginBlock: '-8px' }}>" }
  let(:base) { { 'type' => 'Label', 'id' => 'target', 'text' => 'Sample text', 'lineSpacing' => 16 } }

  it 'takes the half spacing back on the plain shape (the reference)' do
    expect(convert(base)).to include("#{block}Sample text</span>")
  end

  it 'puts the partialAttributes runs in the same block' do
    jsx = convert(base.merge('partialAttributes' => [{ 'range' => [0, 3], 'fontColor' => '#FF0000' }]))
    expect(jsx).to match(/#{Regexp.escape(block)}\{partialText\(.*\)\}<\/span>/)
  end

  it 'puts the links in the same block, inside the Label span' do
    jsx = convert(base.merge('linkable' => true))
    expect(jsx).to match(/<span id="target"[^>]*>#{Regexp.escape(block)}<LinkifyText text=\{`Sample text`\} \/><\/span><\/span>/)
  end

  it 'leaves a linkable Label without lineSpacing as it was' do
    jsx = convert(base.reject { |k, _| k == 'lineSpacing' }.merge('linkable' => true))
    expect(jsx).to start_with('  <LinkifyText id="target"')
    expect(jsx).not_to include('marginBlock')
  end

  it 'writes TSX that compiles against LinkifyTextProps', :typescript_compile do
    elements = [
      convert(base.merge('linkable' => true)),
      convert(base.merge('linkable' => '@{isLinkable}', 'text' => '@{notesText}', 'lineSpacing' => '@{gap}'))
    ]
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      #{TypeScriptCompiler.template_declarations('linkify_text.tsx', 'LinkifyTextProps')}
      declare const LinkifyText: (props: LinkifyTextProps & { ref?: { current: HTMLSpanElement | null } }) => JSX.Element;
      declare const data: { notesText?: string; isLinkable?: boolean; gap?: number };
    TS
  end
end
