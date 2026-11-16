# frozen_string_literal: true

require 'swiftui/data_model_updater'
require_relative '../support/emitted_swift'

# An empty container written as a string — `"{}"` or `"[]"`, the spelling a
# layout's defaultValue usually takes — is written by the DECLARED class's
# kind. It was written as its own characters: a `[String: Int]` given "{}"
# drew `{}` (a closure) and given "[]" drew `[]`; swiftc rejects both ("use
# [:] to get an empty dictionary literal"). jsonui-doc validate now reads
# `[K: V]` as a dictionary and lets "{}" through, so the generator has to
# write it (ticket 2026-10-30-jsonui-doc-initial-value-reads-swift-dictionary-as-array).
RSpec.describe 'data model: an empty container default takes the declared kind' do
  include EmittedSwift

  let(:updater) { SjuiTools::SwiftUI::DataModelUpdater.allocate }

  SJUI_EMPTY_CASES = [
    ['[String: Int]', '{}', '[:]'],
    ['[String: Int]', '[]', '[:]'],
    ['[String: Int]?', '{}', '[:]'],
    ['[String: [Int]]', '{}', '[:]'],
    ['[Int]', '[]', '[]'],
    ['[Int]', '{}', '[]'],
    ['[[String: Int]]', '[]', '[]']
  ].freeze

  it 'writes [:] for a dictionary and [] for an array, whichever was written' do
    SJUI_EMPTY_CASES.each do |klass, value, swift|
      expect(updater.send(:format_default_value, value, klass)).to eq(swift), "#{klass} #{value}"
    end
  end

  it 'leaves a declared value and the container names as they were' do
    expect(updater.send(:format_default_value, { 'a' => 1 }, '[String: Int]')).to eq('["a": 1]')
    # The call site hands the class as swift_data_type spells it: `Object` is
    # `[String: Any]`, which "{}" reached as `{}` too before.
    expect(updater.send(:format_default_value, '{}', updater.send(:swift_data_type, 'Object'))).to eq('[:]')
    expect(updater.send(:format_default_value, 'x', 'String')).to start_with('"x"')
  end

  it 'type-checks with swiftc' do
    lines = SJUI_EMPTY_CASES.each_with_index.map do |(klass, value, _), i|
      "var p#{i}: #{klass} = #{updater.send(:format_default_value, value, klass)}"
    end
    expect(compilable_data(lines.join("\n"))).to compile_as_swift
  end
end
