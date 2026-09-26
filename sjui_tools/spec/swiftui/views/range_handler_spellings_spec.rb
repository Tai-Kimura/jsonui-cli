# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'json'

# A partialAttributes range's handler in both declared spellings: `onClick`
# (a binding) is canonical, `onclick` (a selector) its alias. Every path reads
# both, the canonical one first (TapAccessibility.range_handler; 4f ruling,
# jsonui-cli 1.9.0). The normalizer folds `onclick` into `onClick` (its declared
# alias), so onClick may hold a method name as well as a binding. sjui read `onClick` only, on the Label and the Button.
RSpec.describe 'sjui: a range\'s handler in either spelling' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  emit = lambda do |type, ranges|
    node = { 'type' => type, 'id' => 'l', 'text' => 'Terms and more', 'partialAttributes' => ranges }
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(node).convert.to_s
  end
  call = ->(code) { code[/onClick: (\{[^}]*\})/, 1] }

  cases = {
    'onClick (canonical)' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}' }, '{ data.onTerms?() }'],
    'onclick (alias)' => [{ 'range' => 'Terms', 'onclick' => 'onTerms' }, '{ data.onTerms?() }'],
    'both: the canonical one' => [{ 'range' => 'Terms', 'onClick' => '@{onTerms}', 'onclick' => 'onOther' }, '{ data.onTerms?() }'],
    'onClick holding a name (the alias folded)' => [{ 'range' => 'Terms', 'onClick' => 'onTerms', 'onclick' => 'onOther' }, '{ data.onTerms?() }'],
    'onclick holding a binding' => [{ 'range' => 'Terms', 'onclick' => '@{onTerms}' }, '{ data.onTerms?() }'],
    'onclick array' => [{ 'range' => 'Terms', 'onclick' => %w[onA onB] }, '{ data.onA?(); data.onB?() }'],
    'none' => [{ 'range' => 'Terms' }, nil]
  }
  %w[Label Button].each do |type|
    cases.each do |name, (range, want)|
      it("#{type}: #{name}") { expect(call.call(emit.call(type, [range]))).to eq(want) }
    end
  end

  it 'compiles, the alias on a Label' do
    code = emit.call('Label', [{ 'range' => 'Terms', 'onclick' => %w[onA onB] }])
    expect(compilable_view(code, data: ['var onA: (() -> Void)? = nil', 'var onB: (() -> Void)? = nil'])).to compile_as_swift
  end
end
