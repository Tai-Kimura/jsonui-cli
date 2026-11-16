# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/view_converter'

# A JSX element takes `style` once (ticket rjui-checkbox-without-label-emits-two-style-attributes). From 2.5.37 every
# element's style carries the app's font (P1: `...Configuration.Font.resolve(...)`), so build_style_attr writes a
# style on every element; a labelless CheckBox with an accent colour still wrote its own ` style={{ accentColor }}`
# beside it on the same <input>: TS17001 in the consumer's tsc and `next build`, and the later style dropped the
# accent. Measured over every component and every declared attribute (with and without text, bound and static, the
# structural shapes): this was the only element with two — the labelless CheckBox (and its synonym Check) with
# checkedColor, tintColor or onTintColor. The accent now joins the element's one style.
RSpec.describe 'rjui: an element is written with one style attribute' do
  OPTS = { 'use_tailwind' => true, 'typescript' => true }.freeze

  def emit(node)
    root = { 'type' => 'View', 'id' => 'root', 'child' => [{ 'id' => 'n' }.merge(node)] }
    RjuiTools::React::Converters::ViewConverter.new(root, OPTS).convert
  end

  # The opening tags that carry `style=` more than once (attributes read brace- and quote-aware).
  def tags_with_two_styles(jsx)
    found = []
    i = 0
    while (i = jsx.index(/<[A-Za-z]/, i))
      j = i + 1
      depth = 0
      quote = nil
      top = +''
      while j < jsx.size
        c = jsx[j]
        if quote then quote = nil if c == quote
        elsif depth.zero? && ['"', "'", '`'].include?(c) then quote = c
        elsif c == '{' then depth += 1
        elsif c == '}' then depth -= 1
        elsif c == '>' && depth.zero? then break
        end
        top << c if depth.zero? && quote.nil?
        j += 1
      end
      found << jsx[i..j] if top.scan(/\sstyle=/).size > 1
      i = j
    end
    found
  end

  # The family's shapes, and the two cells the reservation site's user face writes (PaymentOptionCell, StallCell).
  SHAPES = {
    'checkedColor' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'checkedColor' => '#FF0000' },
    'tintColor' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'tintColor' => '#FF0000' },
    'onTintColor' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'onTintColor' => '#FF0000' },
    'a colors.json name' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'checkedColor' => 'primary' },
    'a bound accent' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'checkedColor' => '@{accent}' },
    'with fontColor and background' => { 'type' => 'CheckBox', 'isOn' => '@{on}', 'checkedColor' => '#FF0000',
                                         'fontColor' => '#00FF00', 'background' => '#0000FF' },
    'the synonym Check' => { 'type' => 'Check', 'isOn' => '@{on}', 'tintColor' => '#FF0000' },
    'PaymentOptionCell' => { 'type' => 'CheckBox', 'width' => 'wrapContent', 'height' => 'wrapContent',
                             'isOn' => '@{isSelected}', 'checkedColor' => 'primary', 'iconSize' => 20,
                             'visibility' => '@{markVisibility}' },
    'StallCell' => { 'type' => 'CheckBox', 'width' => 'wrapContent', 'height' => 'wrapContent',
                     'isOn' => '@{isSelected}', 'checkedColor' => 'primary', 'iconSize' => 20,
                     'visibility' => '@{checkVisibility}' }
  }.freeze

  SHAPES.each do |name, node|
    it "a labelless CheckBox, #{name}: one style, holding the accent and the font" do
      jsx = emit(node)
      expect(tags_with_two_styles(jsx)).to eq([])
      input = jsx[/<input[^\n]*type="checkbox"[^\n]*/]
      expect(input).to include('accentColor:')
      expect(input).to include('...Configuration.Font.resolve(')
    end
  end

  it 'the labelled CheckBox keeps the accent on its <input> and its style on the <label>' do
    jsx = emit({ 'type' => 'CheckBox', 'isOn' => '@{on}', 'text' => 'Agree', 'checkedColor' => '#FF0000' })
    expect(tags_with_two_styles(jsx)).to eq([])
    expect(jsx[/<input[^\n]*/]).to include('accentColor:')
  end

  it 'the shapes compile as TypeScript (TS17001 on two style attributes)', :typescript_compile do
    elements = SHAPES.values.map { |node| emit(node) }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare const data: { [key: string]: any };
      declare const ColorManager: { cssColor(name: string): string; resolveColor(name: string): string | undefined };
      declare const VisibilityWrapper: any;
      // React types an <input>'s onChange event; the minimal ambient types no element (as converter_table_spec).
      declare namespace JSX { interface IntrinsicElements { input: { onChange?: (e: { target: { checked: boolean } }) => void; [attr: string]: unknown } } }
    TS
  end
end
