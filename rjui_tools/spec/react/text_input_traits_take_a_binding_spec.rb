# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'

# TextField and TextView keyboard and length attributes take a binding
# (attribute_definitions, 2.5.61). Before, every one of them was dropped
# when bound: the literal mappers match no `@{...}`, so the element carried
# no inputMode, no enterKeyHint, no maxLength, no readOnly. A bound enum now
# carries the literal path's own table, keyed by the declared spellings.
RSpec.describe 'rjui: TextField / TextView keyboard and length attributes take a binding' do
  def emit(node, typescript: false)
    klass = node['type'] == 'TextView' ? RjuiTools::React::Converters::TextViewConverter : RjuiTools::React::Converters::TextFieldConverter
    klass.new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert
  end

  let(:field) do
    { 'type' => 'TextField', 'id' => 'f', 'text' => '@{text}', 'input' => '@{keyboard}', 'returnKeyType' => '@{submit}',
      'autocapitalizationType' => '@{caps}', 'autocorrectionType' => '@{fix}', 'maxLength' => '@{limit}', 'editable' => '@{on}' }
  end

  it 'reads each bound value at run time' do
    out = emit(field)
    expect(out).to include("type={(({ 'default': 'text',", "'number': 'number',", "})[String(data.keyboard)] ?? 'text')}")
    expect(out).to include("inputMode={({", "'number': 'numeric'", "})[String(data.keyboard)]}")
    expect(out).to include("enterKeyHint={({ 'Done': 'done',", "})[String(data.submit)]}")
    expect(out).to include("autoCapitalize={({ 'none': 'off',", "})[String(data.caps)]}")
    expect(out).to include("autoCorrect={({ 'yes': 'on',", 'spellCheck={((c) => (c === undefined ? undefined : c === \'on\'))(')
    expect(out).to include('maxLength={((limit) => (limit > 0 ? limit : undefined))(Number(data.limit))}')
    expect(out).to include('readOnly={!(data.on)}')
    expect(out).not_to include('@{')
  end

  it 'keeps a bound secure over a bound input' do
    out = emit({ 'type' => 'TextField', 'text' => '@{text}', 'secure' => '@{hide}', 'input' => '@{keyboard}' })
    expect(out).to match(/type=\{\(data\.hide\) \? 'password' : \(\(\{ 'default': 'text'.*\}\)\[String\(data\.keyboard\)\] \?\? 'text'\)\}/)
  end

  it 'leaves the literal forms as they were, and a written maxLength of 0 is no limit' do
    out = emit({ 'type' => 'TextField', 'text' => '@{text}', 'input' => 'number', 'returnKeyType' => 'Next',
                 'autocapitalizationType' => 'words', 'autocorrectionType' => 'no', 'maxLength' => 8, 'editable' => false })
    expect(out).to include('type="number"', 'inputMode="numeric"', 'enterKeyHint="next"', 'autoCapitalize="words"',
                           'autoCorrect="off" spellCheck={false}', 'maxLength={8}', ' readOnly')
    expect(emit({ 'type' => 'TextField', 'text' => '@{text}', 'maxLength' => 0 })).not_to include('maxLength')
  end

  it 'reads a bound TextView input, keyboardType, returnKeyType, maxLength and editable, with one inputMode' do
    out = emit({ 'type' => 'TextView', 'text' => '@{text}', 'input' => '@{keyboard}', 'keyboardType' => '@{other}',
                 'returnKeyType' => '@{submit}', 'maxLength' => '@{limit}', 'editable' => '@{on}' })
    expect(out.scan('inputMode=').size).to eq(1)
    # keyboardType wins over input, as on Compose and in SwiftJsonUI.
    expect(out).to include('})[String(data.other)]}', '})[String(data.submit)]}', 'readOnly={!(data.on)}',
                           'maxLength={((limit) => (limit > 0 ? limit : undefined))(Number(data.limit))}')
    expect(emit({ 'type' => 'TextView', 'text' => '@{text}', 'input' => '@{keyboard}' }))
      .to include("inputMode={({ 'alphabet': 'text',", '})[String(data.keyboard)]}')
  end

  # inputMode and enterKeyHint are unions of string literals in React's DOM
  # types; an untyped table indexes to `string`, which a strict consumer
  # rejects (measured with @types/react 18.3 and tsc --strict: 7 errors
  # without the cast, 0 with it).
  it 'names the values a TypeScript lookup can yield' do
    out = emit(field, typescript: true)
    expect(out).to include("as Record<string, 'done' | 'go' | 'next' | 'enter' | 'search' | 'send'>)[String(data.submit)]")
    expect(emit(field)).not_to include('as Record')
  end

  it 'compiles', :typescript_compile do
    drawn = [emit(field, typescript: true),
             emit({ 'type' => 'TextView', 'id' => 'v', 'text' => '@{text}', 'input' => '@{keyboard}', 'returnKeyType' => '@{submit}',
                    'maxLength' => '@{limit}', 'editable' => '@{on}' }, typescript: true)]
    source = "const data = {} as { [key: string]: any };\nconst fRef: any = null;\nconst vRef: any = null;\n" \
             "export const view = (\n  <div>\n#{drawn.join("\n")}\n  </div>\n);\n"
    # The event handlers are typed by React's own JSX, which this ambient
    # does not carry (`(e) =>` reads as an implicit any); they are not
    # what changed here.
    expect(source.gsub(/ on\w+=\{[^}]*\}\}?/, '')).to compile_as_typescript
  end
end
