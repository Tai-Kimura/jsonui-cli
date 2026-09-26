# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/view_converter'
require 'react/converters/embed_converter'
require 'json'
require 'stringio'

# `userInteractionEnabled` (attribute_definitions.json common, boolean |
# binding) stops the element and what is in it — `pointer-events: none` — on
# every type. Only View built the bound form into its className
# (build_responsive_class_attr); every other converter builds its own
# className and dropped `@{…}`, and TabView dropped `false` too (measured:
# 26 of the 27 declared types that convert). BaseConverter#apply_interaction_class
# puts it on the first element of every converter's subtree, through
# convert_node (past a JsonUISeeded state holder, which takes no className).
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
      it 'with no flag, its first element stops nothing' do
        expect(element_tag(convert(type, extra[type] || {}))).not_to include('pointer-events-none')
      end

      it 'userInteractionEnabled: false stops its first element' do
        expect(element_tag(convert(type, (extra[type] || {}).merge('userInteractionEnabled' => false))))
          .to include('pointer-events-none')
      end

      it 'a bound userInteractionEnabled stops its first element while it is false, once' do
        tag = element_tag(convert(type, (extra[type] || {}).merge('userInteractionEnabled' => '@{u}')))
        expect(tag.scan(bound).size).to eq(1), tag
      end
    end
  end

  # `enabled` bound: the tap does not happen while it is false, as for a
  # literal `false`, on every type — the same means `false` uses there. A
  # type `false` stops with the classes `opacity-50 pointer-events-none` gets
  # them behind the binding; a control `false` disables gets `disabled={!…}`
  # on the same element (and no classes on top). Before: only View (classes)
  # and the controls (disabled) — Label, Image, NetworkImage, IconLabel, Blur,
  # CircleView and GradientView kept their tap, and a Segment switched tabs.
  describe 'a bound enabled, against false' do
    bound_classes = "${!data.on ? 'opacity-50 pointer-events-none' : ''}"

    types.each do |type|
      it "#{type}: stopped as false stops it" do
        more = (extra[type] || {}).merge('onClick' => '@{onTap}')
        off = convert(type, more.merge('enabled' => false))
        on_bound = convert(type, more.merge('enabled' => '@{on}'))
        off_tag = element_tag(off)
        off_classes = off_tag.include?('opacity-50') && off_tag.include?('pointer-events-none')
        off_disabled = off.match?(/(?<![-\w])disabled(?=[\s>\/])/)
        bound_classes_here = element_tag(on_bound).include?(bound_classes)
        bound_disabled = on_bound.match?(/(?<![-\w])disabled=\{!data\.on\}/)
        expect(bound_disabled).to eq(off_disabled), "disabled: false #{off_disabled}, bound #{bound_disabled}\n#{on_bound}"
        expect(bound_classes_here).to eq(off_classes && !off_disabled), "classes: false #{off_classes}, bound #{bound_classes_here}\n#{on_bound}"
      end
    end

    it 'the tappable types that dropped it now carry it' do
      %w[Label Image NetworkImage IconLabel Blur CircleView GradientView].each do |type|
        on_bound = convert(type, (extra[type] || {}).merge('onClick' => '@{onTap}', 'enabled' => '@{on}'))
        expect(element_tag(on_bound)).to include(bound_classes), type
      end
    end
  end

  # `hidden` / `visibility` bound, and userInteractionEnabled, land on the
  # first element of the page — past the state holder a static-seeded control
  # is wrapped in (JsonUISeeded, which declares no className: a className on it
  # does not compile) — whatever form its className has, or none. Before: a
  # bound `hidden` on a Segment, a TabView or an Embed was passed over without
  # a word (measured), and userInteractionEnabled on a Segment or a TabView
  # put a className on JsonUISeeded.
  describe 'hidden, visibility and the flag on every type' do
    types.each do |type|
      it "#{type}: a bound hidden and a bound visibility land on its first element" do
        hidden = convert(type, (extra[type] || {}).merge('hidden' => '@{h}'))
        expect(element_tag(hidden)).to include('${data.h ? "invisible" : ""}'), hidden
        visible = convert(type, (extra[type] || {}).merge('visibility' => '@{vis}'))
        expect(element_tag(visible)).to include('=== "invisible" ? "invisible" : ""'), visible
      end
    end

    it 'nothing goes on the state holder' do
      %w[Segment TabView].each do |type|
        code = convert(type, (extra[type] || { 'tabs' => [{ 'title' => 'a' }] }).merge(
          'hidden' => '@{h}', 'userInteractionEnabled' => '@{u}', 'enabled' => '@{on}'
        ))
        holder = root_tag(code)
        expect(holder).to start_with('<JsonUISeeded') if code.include?('<JsonUISeeded')
        expect(holder).not_to include('className') if holder.start_with?('<JsonUISeeded')
      end
    end

    it 'a markup with no element to carry it is named' do
      probe = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View', 'id' => 'x', 'hidden' => '@{h}' }, config)
      # a markup that is only an expression: no element to put a class on
      out = capture_stdout { probe.send(:inject_class_expression, '{flag}', 'invisible') }
      expect(out).to include("View 'x': hidden / visibility is not applied")
    end
  end

  # The first element of the page — past the `display: contents` box a
  # stopped component is wrapped in for its inert (apply_interaction_inert),
  # to the component that carries the class.
  def element_tag(jsx)
    probe = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config)
    range = probe.send(:element_root_range, jsx)
    return '' unless range

    return element_tag(jsx[(range.last + 1)..]) if jsx[range].start_with?('<div className="contents" {...jsonuiInert(')

    jsx[range]
  end

  def capture_stdout
    old = $stdout
    $stdout = StringIO.new
    yield
    $stdout.string
  ensure
    $stdout = old
  end

  it 'a Segment and a TabView with the flag, hidden and enabled bound compile against JsonUISeeded', :typescript_compile do
    elements = [
      convert('Segment', 'items' => %w[a b], 'hidden' => '@{h}', 'userInteractionEnabled' => '@{u}', 'enabled' => '@{on}'),
      convert('TabView', 'tabs' => [{ 'title' => 'a' }], 'hidden' => '@{h}', 'userInteractionEnabled' => '@{u}')
    ]
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: { u?: boolean; h?: boolean; on?: boolean; selectedTabIndex?: number; setSelectedTabIndex?: (i: number) => void };
      declare const Circle: (props: { className?: string }) => JSX.Element;
      declare function jsonuiInert(stop: boolean): Record<string, unknown>;
      declare const JsonUISeeded: <T,>({ seed, children }: { seed: T; children: (value: T, set: (value: T) => void) => React.ReactNode }) => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
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
    elements.each { |e| expect(element_tag(e).scan(bound).size).to eq(1), e }
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: { u?: boolean; h?: boolean; hi?: boolean };
      declare const EmbedContainer: (props: any) => JSX.Element;
      declare function jsonuiInert(stop: boolean): Record<string, unknown>;
      declare const S: any;
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end
end
