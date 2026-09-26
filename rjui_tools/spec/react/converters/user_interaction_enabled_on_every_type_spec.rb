# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/embed_converter'
require 'json'

# `userInteractionEnabled` (attribute_definitions.json common, boolean |
# binding) stops the element and what is in it — `pointer-events: none` — on
# every type. Only View built the bound form into its className
# (build_responsive_class_attr); every other converter builds its own
# className and dropped `@{…}`, and TabView dropped `false` too (measured:
# 26 of the 27 declared types that convert). BaseConverter#apply_interaction_class
# puts it on the root tag of every converter's subtree, through convert_node.
RSpec.describe 'rjui userInteractionEnabled on every type' do
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
    'TextView' => { 'text' => '@{t}' }
  }
  bound = "${!data.u ? 'pointer-events-none' : ''}"

  def root_tag(jsx)
    probe = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config)
    range = probe.send(:root_open_tag_range, jsx)
    range ? jsx[range] : ''
  end

  def convert(type, more)
    probe = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config)
    klass = probe.send(:get_converter_class, type)
    klass.new({ 'type' => type, 'id' => 'n' }.merge(more), config).convert_node(1)
  end

  it 'reads every type the declaration knows' do
    expect(types.size).to be >= 29
  end

  types.each do |type|
    describe type do
      it 'with no flag, the root tag stops nothing' do
        expect(root_tag(convert(type, extra[type] || {}))).not_to include('pointer-events-none')
      end

      it 'userInteractionEnabled: false stops the root tag' do
        expect(root_tag(convert(type, (extra[type] || {}).merge('userInteractionEnabled' => false))))
          .to include('pointer-events-none')
      end

      it 'a bound userInteractionEnabled stops the root tag while it is false, once' do
        tag = root_tag(convert(type, (extra[type] || {}).merge('userInteractionEnabled' => '@{u}')))
        expect(tag.scan(bound).size).to eq(1), tag
      end
    end
  end

  # The forms a root className takes: a static string, a template literal, a
  # Label's highlight ternary (`className={cond ? "a" : "b"}`), and none.
  it 'appends to each form of className, and the TSX compiles', :typescript_compile do
    elements = [
      convert('Label', 'text' => 't', 'userInteractionEnabled' => '@{u}'),
      convert('Image', 'srcName' => 'x', 'userInteractionEnabled' => '@{u}', 'hidden' => '@{h}'),
      convert('Label', 'text' => 't', 'highlighted' => '@{hi}', 'highlightColor' => '#FF0000',
                       'userInteractionEnabled' => '@{u}'),
      convert('Embed', 'screen' => 'S', 'userInteractionEnabled' => '@{u}')
    ]
    elements.each { |e| expect(root_tag(e).scan(bound).size).to eq(1), e }
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: { u?: boolean; h?: boolean; hi?: boolean };
      declare const EmbedContainer: (props: any) => JSX.Element;
      declare const S: any;
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
