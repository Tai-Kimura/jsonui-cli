# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/view_converter'
require 'json'
require 'stringio'

# `testId` (attribute_definitions.json common, platform react) is the
# element's `data-testid` on every type. Measured at 2.3.20 through the
# ConverterTable: 24 of 28 emitted it; View / SafeAreaView (ViewConverter)
# and Embed dropped it without a word, and Include has no element of its own
# (it renders the partial's component). View and Embed now carry it — Embed on
# EmbedContainer's container div, through its `data-testid` prop — and an
# Include with a testId is named at build (ticket rjui-view-testid-not-emitted).
RSpec.describe 'rjui testId on every type' do
  let(:config) { { 'use_tailwind' => true } }

  defs_path = File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)
  defs = JSON.parse(File.read(defs_path))
  types = (defs.keys - %w[common]).select { |k| defs[k].is_a?(Hash) && !k.start_with?('_', '$') }.sort

  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }, 'Embed' => { 'screen' => 'S' },
    'TextField' => { 'text' => '@{t}' }, 'EditText' => { 'text' => '@{t}' }, 'Input' => { 'text' => '@{t}' },
    'TextView' => { 'text' => '@{t}' }, 'TabView' => { 'tabs' => [{ 'title' => 'a' }] }
  }

  def convert(type, more)
    probe = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config)
    klass = probe.send(:get_converter_class, type)
    klass.new({ 'type' => type, 'id' => 'n', 'testId' => 'tid' }.merge(more), config).convert_node(1)
  end

  def capture_stdout
    old = $stdout
    $stdout = StringIO.new
    yield
    $stdout.string
  ensure
    $stdout = old
  end

  it 'reads every type the declaration knows' do
    expect(types).to include('View', 'SafeAreaView', 'Embed')
    expect(types.size).to be >= 29
  end

  # The family, in one arm: every declared type, with and without children.
  it 'every type writes its testId as data-testid, once' do
    missing = []
    types.each do |type|
      [{}, { 'child' => [{ 'type' => 'Label', 'text' => 'c' }] }].each do |children|
        out = convert(type, (extra[type] || {}).merge(children))
        n = out.scan('data-testid="tid"').size
        missing << "#{type}#{children.empty? ? '' : ' +child'}: #{n}" unless n == 1
      end
    end
    expect(missing).to be_empty, missing.join("\n")
  end

  it 'an Include with a testId is named, in English and Japanese, with where to write it' do
    out = nil
    said = capture_stdout { out = convert('Include', 'include' => 'parts/row') }
    expect(out).not_to include('data-testid')
    expect(said).to include("Include 'parts/row' has testId 'tid'", "partial's root view")
    expect(said).to include("Include 'parts/row' の testId 'tid'", 'partial の root の view に書いてください')
    expect(capture_stdout { convert('Include', 'include' => 'parts/row', 'testId' => nil) }).to eq('')
  end

  # EmbedContainer (lib/react/templates, written by `rjui init`) takes the
  # testId as its `data-testid` prop and puts it on the container div, beside
  # data-embed-id.
  it "EmbedContainer's container div carries its data-testid prop" do
    source = File.read(File.join(TypeScriptCompiler::TEMPLATES_DIR, 'EmbedContainer.tsx'))
    props = TypeScriptCompiler.template_declarations('EmbedContainer.tsx', 'EmbedContainerProps')
    expect(props).to include("'data-testid'?: string;")
    expect(source).to match(/^  'data-testid': (\w+),$/)
    name = source[/^  'data-testid': (\w+),$/, 1]
    container = source[/<div\n\s+data-embed-id=\{embedId\}.*?>/m]
    expect(container).to include("data-testid={#{name}}")
  end

  it 'View, SafeAreaView and Embed with a testId compile against EmbedContainerProps', :typescript_compile do
    elements = [
      convert('View', {}), convert('View', 'child' => [{ 'type' => 'Label', 'text' => 'c' }]),
      convert('SafeAreaView', 'child' => [{ 'type' => 'Label', 'text' => 'c' }]),
      convert('Embed', 'screen' => 'S')
    ]
    ambient = TypeScriptCompiler::AMBIENT + TypeScriptCompiler.template_declarations(
      'EmbedContainer.tsx', 'EmbedNavigationMode', 'EmbeddedEvent', 'EmbedStackEntry', 'EmbedScreenResolver',
      'EmbedContainerProps'
    ) + <<~TS
      declare const EmbedContainer: (props: EmbedContainerProps) => JSX.Element;
      declare const S: () => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
