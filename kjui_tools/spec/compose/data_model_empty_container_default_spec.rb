# frozen_string_literal: true

require_relative '../../lib/compose/data_model_updater'
require_relative '../support/kotlin_compiler'

# An empty container written as a string — `"{}"` or `"[]"` — is written by
# the DECLARED class's kind. It was written by its own characters: a
# `Map<String, Int>` given "[]" drew `emptyList()`, which kotlinc rejects
# (ticket 2026-10-30-jsonui-doc-initial-value-reads-swift-dictionary-as-array).
RSpec.describe 'data model: an empty container default takes the declared kind' do
  let(:updater) { KjuiTools::Compose::DataModelUpdater.allocate }

  KJUI_EMPTY_CASES = [
    ['Map<String, Int>', '{}', 'emptyMap()'],
    ['Map<String, Int>', '[]', 'emptyMap()'],
    ['Map<String, Int>?', '[]', 'emptyMap()'],
    ['[String: Int]', '[]', 'emptyMap()'],
    ['List<Int>', '{}', 'emptyList()'],
    ['List<Int>', '[]', 'emptyList()'],
    ['List<Map<String, Int>>', '[]', 'emptyList()']
  ].freeze

  it 'writes emptyMap() for a map and emptyList() for a list, whichever was written' do
    KJUI_EMPTY_CASES.each do |klass, value, kotlin|
      expect(updater.send(:format_default_value, value, klass)).to eq(kotlin), "#{klass} #{value}"
    end
  end

  it 'leaves the container names and other classes as they were' do
    expect(updater.send(:format_default_value, '{}', 'Object')).to eq('emptyMap()')
    expect(updater.send(:format_default_value, '[]', 'Array')).to eq('emptyList()')
    expect(updater.send(:format_default_value, '3', 'Int')).to eq('3')
  end

  it 'type-checks with kotlinc' do
    props = KJUI_EMPTY_CASES.each_with_index.map do |(klass, value, _), i|
      kotlin_class = klass == '[String: Int]' ? 'Map<String, Int>' : klass
      "    var p#{i}: #{kotlin_class} = #{updater.send(:format_default_value, value, klass)}"
    end
    expect("class Holder {\n#{props.join("\n")}\n}\n").to compile_as_kotlin
  end
end
