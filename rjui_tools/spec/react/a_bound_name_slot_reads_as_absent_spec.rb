# frozen_string_literal: true

require 'json'
require 'stringio'
require 'react/react_generator'
require_relative '../support/typescript_compiler'

# An attribute that names something the generator has to know has no value yet
# when it is a binding. The web answered three ways: `import @{v} from` for an
# Embed (a SyntaxError in the generated file, while the converter had warned and
# drawn nothing), `name="@{v}"` for a Radio (the characters were the group), and
# nothing at all for nextFocus. Every face now reads it as absent and says so once
# (LayoutValidator.drop_name_slot_bindings!), before anything reads the tree.
RSpec.describe 'a bound name slot on the web build path' do
  def size
    { 'width' => 'matchParent', 'height' => 40 }
  end

  def built(*nodes)
    json = { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
             'child' => [{ 'data' => [{ 'name' => 'v', 'class' => 'String', 'defaultValue' => '' }] }, *nodes] }
    err = StringIO.new
    orig = $stderr
    $stderr = err
    begin
      jsx = RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }).generate('Probe', json).to_s
    ensure
      $stderr = orig
    end
    yield jsx, err.string
  end

  it 'Embed.screen: the file imports nothing named after the binding' do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => '@{v}' }.merge(size)) do |jsx, err|
      expect(jsx).not_to include('import @{')
      expect(jsx).not_to include('@{v}')
      expect(err.scan("'screen' names a screen").size).to eq(1)
    end
  end

  # @ts-nocheck leaves the syntax errors, which is what `import @{v} from` was:
  # the generated file did not parse, whatever the names in it resolve to.
  it 'the generated file parses', :typescript_compile do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => '@{v}' }.merge(size)) do |jsx, _|
      expect("// @ts-nocheck\n#{jsx}").to compile_as_typescript
    end
  end

  it 'a written screen is still imported' do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => 'other_screen' }.merge(size)) do |jsx, err|
      expect(jsx).to include("import OtherScreen from '@/generated/components/OtherScreen';")
      expect(err).not_to include('does not take')
    end
  end

  it 'Embed.navigationMode: no attribute carrying the characters' do
    built({ 'type' => 'Embed', 'id' => 'e', 'screen' => 'other_screen', 'navigationMode' => '@{v}' }.merge(size)) do |jsx, err|
      expect(jsx).not_to include('@{v}')
      expect(err).to include("'navigationMode' names a mode")
    end
  end

  it 'Radio.group: the characters are not the group, and a warning says so' do
    built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => '@{v}' }.merge(size)) do |jsx, err|
      expect(jsx).not_to include('name="@{v}"')
      expect(err).to include("'group' names a radio group and does not take a binding (@{v}); ignored.")
    end
  end

  it 'a written group is untouched' do
    built({ 'type' => 'Radio', 'id' => 'r', 'text' => 'x', 'group' => 'written' }.merge(size)) do |jsx, err|
      expect(jsx).to include('name="written"')
      expect(err).not_to include('does not take')
    end
  end

  it 'TextField.nextFocus: the warning it did not have' do
    built({ 'type' => 'TextField', 'id' => 't', 'text' => '@{v}', 'nextFocus' => '@{v}' }.merge(size)) do |jsx, err|
      expect(jsx).not_to include('onKeyDown')
      expect(err).to include("'nextFocus' names a field and does not take a binding (@{v}); ignored.")
    end
  end

  it 'ScrollView.defaultScrollAnchor is the same rule, reported on the web too' do
    built({ 'type' => 'ScrollView', 'id' => 's', 'defaultScrollAnchor' => '@{v}', 'child' => [] }.merge(size)) do |jsx, err|
      expect(jsx).not_to include('@{v}')
      expect(err).to include("'defaultScrollAnchor' names an anchor")
    end
  end

  it 'an override in `responsive` is taken off too' do
    node = { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'responsive' => { 'compact' => { 'alignTopOfView' => '@{v}' } } }.merge(size)
    built(node) do |jsx, err|
      expect(jsx).not_to include('@{v}')
      expect(err).to include("'alignTopOfView' names a view")
    end
  end

  it 'an alignment against a binding is read as no alignment' do
    built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'alignTopOfView' => '@{v}' }.merge(size)) do |bound, err|
      expect(err).to include("'alignTopOfView' names a view")
      built({ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }.merge(size)) { |absent, _| expect(bound).to eq(absent) }
    end
  end
end
