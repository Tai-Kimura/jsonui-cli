# frozen_string_literal: true

require 'json'
require 'stringio'
require 'tmpdir'
require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'core/config_manager'
require 'react/react_generator'

# One table from a component type to its converter, for a layout's root and
# for every child (converters/converter_table.rb). Until jsonui-cli 1.9.0 the
# root dispatch (ReactGenerator::CONVERTERS) and the child dispatch
# (BaseConverter#get_converter_class) each kept a table, and they differed in
# two types: a root NetworkImage was a plain <img> (ImageConverter — no
# defaultImage, no errorImage, contentMode a class only), a nested one a
# <NetworkImage> (NetworkImageConverter); a root Toggle a switch
# (SwitchConverter), a nested one a checkbox (ToggleConverter). Faces
# measured: 0 of 248 layouts have a NetworkImage or a Toggle at the root (50
# nested NetworkImage, 0 Toggle), so no face emit moves.
RSpec.describe 'rjui: one converter table, root and child' do
  let(:config) { RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => true) }
  let(:table) { RjuiTools::React::Converters::ConverterTable.table }

  def child_class(type)
    RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config.dup).send(:get_converter_class, type)
  end

  it 'the root dispatch and the child dispatch read the same table' do
    expect(RjuiTools::React::ReactGenerator::CONVERTERS).to equal(table)
    table.each { |type, klass| expect(child_class(type)).to eq(klass), type }
  end

  # Each alias the SSoT declares (`_alias_of`) converts as the type it is an
  # alias of — derived from the declaration, not restated here.
  it "every declared alias converts as the type it is an alias of (Toggle is Switch's)" do
    definitions = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
    aliases = definitions.select { |_, v| v.is_a?(Hash) && v['_alias_of'] }.transform_values { |v| v['_alias_of'] }
    expect(aliases).to include('Toggle' => 'Switch')
    aliases.each do |alias_name, canonical|
      next unless table.key?(alias_name)

      expect(table[alias_name]).to eq(table.fetch(canonical)), "#{alias_name} (_alias_of #{canonical})"
    end
  end

  def element(json, name)
    $stderr = StringIO.new
    out = Dir.mktmpdir do |dir|
      Dir.chdir(dir) { RjuiTools::React::ReactGenerator.new(config.dup).generate(name, json) }
    end
    out.lines.find { |l| l =~ /<(NetworkImage|img|label)\b/ }.to_s.strip.sub(/id=\{id \?\? "(\w+)"\}/, 'id="\1"')
  ensure
    $stderr = STDERR
  end

  PROBES = {
    'NetworkImage' => [{ 'type' => 'NetworkImage', 'id' => 'photo', 'width' => 140, 'height' => 80, 'url' => '@{photoUrl}',
                         'defaultImage' => 'placeholder', 'errorImage' => 'broken', 'contentMode' => 'fill' },
                       { 'name' => 'photoUrl', 'class' => 'String' }, '<NetworkImage '],
    'Toggle' => [{ 'type' => 'Toggle', 'id' => 'sw', 'isOn' => '@{on}' }, { 'name' => 'on', 'class' => 'Bool' }, 'w-[51px] h-[31px]']
  }.freeze

  PROBES.each do |type, (node, datum, drawn)|
    it "a #{type} at the root is drawn as the same node nested" do
      root = element(node.merge('data' => [datum]), 'RootProbe')
      nested = element({ 'type' => 'View', 'id' => 'root', 'data' => [datum], 'child' => [node] }, 'NestedProbe')
      expect(root).to eq(nested)
      expect(root).to include(drawn)
    end
  end

  # What the table's converters now draw at the root type-checks — the
  # NetworkImage against the built-in's own props (lib/react/templates).
  it 'the root NetworkImage and Toggle type-check' do
    # Drawn as both callers draw a node: its type canonicalized first (Toggle
    # is Switch), then the table.
    jsx = PROBES.map do |_, (node, _, _)|
      drawn = JsonUIShared::ComponentAliases.resolve(JsonUIShared::TypeSynonyms.canonicalize(node))
      table.fetch(drawn['type']).new(drawn, config.dup).convert
    end
    expect(TypeScriptCompiler.component(*jsx)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
      declare const data: { photoUrl?: string; on: boolean; onOnChange?: (value: boolean) => void };
      // React types an <input>'s onChange event; the minimal ambient types no
      // element, so this one is declared (the part the switch reads).
      declare namespace JSX { interface IntrinsicElements { input: { onChange?: (e: { target: { checked: boolean } }) => void; [attr: string]: unknown } } }
      #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
      declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
    TS
  end
end
