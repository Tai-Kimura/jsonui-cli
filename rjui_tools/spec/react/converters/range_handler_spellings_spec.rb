# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/label_converter'
require 'react/converters/button_converter'

# A partialAttributes range's handler in both declared spellings: `onClick`
# (a binding) is canonical, `onclick` (a selector) its alias. Every path reads
# both, the canonical one first (TapAccessibility.range_handler; 4f ruling,
# jsonui-cli 1.9.0). The normalizer folds `onclick` into `onClick` (its declared
# alias), so onClick may hold a method name as well as a binding. rjui read `onclick` only, so a range written the
# canonical way had no handler on web (measured in two apps' generated TSX:
# 8 such ranges, each emitted with no onClick).
RSpec.describe 'rjui: a range\'s handler in either spelling' do
  emit = lambda do |type, ranges|
    klass = RjuiTools::React::Converters.const_get("#{type}Converter")
    klass.new({ 'type' => type, 'id' => 'l', 'text' => 'Terms and more', 'partialAttributes' => ranges }, { 'use_tailwind' => true }).convert
  end
  call = ->(code) { code[/onClick: ([^,}\]]+(?:\(\) => \{[^}]*\})?)/, 1]&.strip }

  cases = {
    'onClick (canonical)' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }, 'data.onTerms'],
    'onclick (alias)' => [{ 'range' => 'Terms', 'onclick' => 'onTerms' }, 'data.onTerms'],
    'both: the canonical one' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}', 'onclick' => 'onOther' }, 'data.onTerms'],
    'onClick holding a name (the alias folded)' => [{ 'range' => 'Terms', 'onClick' => 'onTerms', 'onclick' => 'onOther' }, 'data.onTerms'],
    'onclick holding a binding' => [{ 'range' => 'Terms', 'onclick' => '@{onTerms}' }, 'data.onTerms'],
    'none' => [{ 'range' => 'Terms' }, nil]
  }
  %w[Label Button].each do |type|
    cases.each do |name, (range, want)|
      it("#{type}: #{name}") { expect(call.call(emit.call(type, [range]))).to eq(want) }
    end
    it("#{type}: a handler in either spelling makes the range a pointer") do
      expect(emit.call(type, [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }])).to include("className: 'cursor-pointer'")
    end
  end

  it 'compiles, the canonical spelling on a Label and a Button', :typescript_compile do
    jsx = %w[Label Button].map { |t| emit.call(t, [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }]) }
    expect(TypeScriptCompiler.component(*jsx)).to compile_as_typescript.with_ambient(<<~TS)
      type PartialSpec = { range: [number, number] | string; style?: Record<string, string | number>; className?: string; onClick?: () => void };
      declare function partialText(text: string, partials: PartialSpec[]): JSX.Element;
      declare const data: { onTerms?: () => void };
    TS
  end
end
