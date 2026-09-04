# frozen_string_literal: true

require_relative '../../lib/core/string_manager_core'

# The layout string-attribute vocabulary must exist ONCE. plural_validator.rb
# used to carry its own STRING_PROPS with the same five names, so extending
# extraction updated string_manager_core and left the validator behind — the
# duplication was invisible because both copies happened to agree.
#
# The behavioural assertion is the one that matters: a text match would pass
# against a second literal that merely spelled the reference correctly.
RSpec.describe 'layout string vocabulary' do
  it 'is defined in exactly one place' do
    expect(defined?(JsonUIShared::StringManagerCore::STRING_PROPERTIES)).to eq('constant')
    expect(defined?(JsonUIShared::PluralValidator::STRING_PROPS)).to be_nil
  end

  it 'is the vocabulary the plural validator actually walks' do
    require_relative '../../lib/core/plural_validator'
    vocabulary = JsonUIShared::StringManagerCore::STRING_PROPERTIES
    expect(vocabulary).not_to be_empty

    node = vocabulary.each_with_object({}) { |prop, acc| acc[prop] = "#{prop}_key" }
    yielded = []
    JsonUIShared::PluralValidator.send(:scan_layout_node, node) { |k, v| yielded << [k, v] }

    expect(yielded).to match_array(vocabulary.map { |prop| [prop, "#{prop}_key"] })
  end

  it 'reads the constant rather than repeating its contents' do
    source = File.read(File.expand_path('../../lib/core/plural_validator.rb', __dir__))
    expect(source).to include('StringManagerCore::STRING_PROPERTIES')
    # A re-introduced literal would be a %w[...] holding the same names.
    expect(source).not_to match(/STRING_PROPS\s*=\s*%w\[/)
  end
end
