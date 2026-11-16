# frozen_string_literal: true

require 'json'
require_relative '../../lib/core/data_item_platform'
require_relative '../../lib/core/binding_validator'

# A layout data item's `platform` is read as `jui build` reads it
# (platform_resolver.py, restated in shared/core/platform_semantics.json):
# comma-separated tokens, without case, each naming a platform by any of
# its tokens; any other shape is no filter. Until jsonui-cli 1.9.0 sjui and
# kjui kept an item only for exactly 'swift' / 'kotlin', and rjui did not
# read the key at all. The validator and this tool's generators read it
# through the one reader, so they agree with each other as well.
RSpec.describe JsonUIShared::DataItemPlatform, '(rjui: a data item\'s platform)' do
  let(:canon) { File.expand_path('../../../shared/core/platform_semantics.json', __dir__) }

  it 'holds the token table of platform_semantics.json' do
    skip 'shared/core copy not present in this layout' unless File.exist?(canon)
    tokens = JSON.parse(File.read(canon))['nodeDirective']['stringForm']['tokens']
    expect(described_class::TOKENS.transform_values(&:sort)).to eq(tokens.transform_values(&:sort))
  end

  it 'keeps an item any token of this platform names, alone, among others (comma-separated), or in another case' do
    ["react", "web", "TypeScript", "javascript"].each do |token|
      expect(described_class.applies?({ 'platform' => token }, 'react')).to be(true), token
      expect(described_class.applies?({ 'platform' => "swift, #{token}" }, 'react')).to be(true), token
    end
  end

  it 'drops an item whose tokens name only other platforms' do
    expect(described_class.applies?({ 'platform' => 'swift' }, 'react')).to be(false)
    expect(described_class.applies?({ 'platform' => 'unknownToken' }, 'react')).to be(false)
  end

  it 'reads no filter in a shape that is not a string, or in an empty one' do
    [nil, '', ' , ', { 'ios' => { 'defaultValue' => 1 } }, ['swift']].each do |value|
      expect(described_class.applies?({ 'platform' => value }, 'react')).to be(true), value.inspect
    end
  end

  describe 'the binding validator' do
    subject(:validator) { RjuiTools::Core::BindingValidator.new }

    def layout(texts, data)
      { 'type' => 'View', 'id' => 'root', 'data' => data,
        'child' => texts.each_with_index.map { |text, i| { 'type' => 'Label', 'id' => "l#{i}", 'text' => text } } }
    end

    it 'takes an item another token of this platform names as this layout\'s data' do
      data = [{ 'name' => 'mine', 'class' => 'String', 'platform' => 'web' }]
      warnings = validator.validate(layout(['@{mine}'], data), 'a.json')
      expect(warnings.grep(/'mine'/)).to be_empty, warnings.join("\n")
    end

    it 'does not take an item of another platform: not "never used" here, and "not defined" if bound' do
      data = [{ 'name' => 'shown', 'class' => 'String' }, { 'name' => 'theirs', 'class' => 'String', 'platform' => 'swift' }]
      unbound = validator.validate(layout(['@{shown}'], data), 'a.json')
      expect(unbound.grep(/'theirs'/)).to be_empty, unbound.join("\n")
      bound = validator.validate(layout(['@{shown}', '@{theirs}'], data), 'a.json')
      expect(bound.grep(/Binding variable 'theirs'.*not defined/).size).to eq(1), bound.join("\n")
    end

    it 'names a platform shape nothing reads, and keeps the item' do
      data = [{ 'name' => 'listed', 'class' => 'String', 'platform' => ['swift'] }]
      warnings = validator.validate(layout(['@{listed}'], data), 'a.json')
      expect(warnings.grep(/data 'listed'.*platform/).size).to eq(1), warnings.join("\n")
      expect(warnings.grep(/Binding variable 'listed'/)).to be_empty, warnings.join("\n")
    end
  end

  # This tool's generators read it through the same reader: their arms are in
  # the generators' own specs (they load code that emits, and each such spec
  # is held to a compile arm or a listed reason).
end
