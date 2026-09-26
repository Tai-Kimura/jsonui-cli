# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require_relative '../../support/bundler_define'
require_relative '../../../lib/cli/commands/build_command'
require 'react/react_generator'
require 'react/converters/view_converter'
require 'react/converters/embed_converter'
require 'json'
require 'open3'
require 'tmpdir'

# The rule: what `userInteractionEnabled` stops starts from no pointer, no
# screen reader and no keyboard, and nothing drawn changes (jsonui-cli 1.9.0).
# `pointer-events: none` stopped the pointer alone — measured in Chromium, a
# stopped button, checkbox, text field and link were reached by Tab, operated
# by Enter / Space / typing and pressed from the accessibility tree. What the
# flag stops is inert now (BaseConverter#apply_interaction_inert).
#
# And a tap the rule makes a button — a Label or a View with onClick, the
# rule's `button` / `combine` shape — was reached by neither Tab nor a screen
# reader's buttons (measured); it is a button on web as on iOS and Android
# (BaseConverter#keyboard_tap_attrs).
RSpec.describe 'rjui: a stop is inert, and a tap is a button to the keyboard' do
  let(:config) { { 'use_tailwind' => true } }

  defs = JSON.parse(File.read(File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__)))
  types = (defs.keys - %w[common]).select { |k| defs[k].is_a?(Hash) && !k.start_with?('_', '$') }.sort
  extra = {
    'Image' => { 'srcName' => 'x' }, 'CircleImage' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'Label' => { 'text' => 't' },
    'Text' => { 'text' => 't' }, 'IconLabel' => { 'text' => 't' }, 'Button' => { 'text' => 't' },
    'SelectBox' => { 'items' => ['a'] }, 'Segment' => { 'items' => ['a'] }, 'Embed' => { 'screen' => 'S' },
    'TextField' => { 'text' => '@{t}' }, 'EditText' => { 'text' => '@{t}' }, 'Input' => { 'text' => '@{t}' },
    'TextView' => { 'text' => '@{t}' }, 'TabView' => { 'tabs' => [{ 'title' => 'a' }] }
  }

  def probe
    RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config)
  end

  def convert(node)
    probe.send(:get_converter_class, node['type']).new({ 'id' => 'n' }.merge(node), config).convert_node(1)
  end

  # The opening tag of the first element of the page (past a state holder).
  def element_tag(jsx)
    range = probe.send(:element_root_range, jsx)
    range ? jsx[range] : ''
  end

  describe 'userInteractionEnabled: what it stops is inert' do
    static = '{...jsonuiInert(true)}'
    bound = '{...jsonuiInert(!(data.u))}'

    types.each do |type|
      it "#{type}: false and a binding make the first element inert, or a contents box around a component; no flag, nothing" do
        node = { 'type' => type }.merge(extra[type] || {})
        off = convert(node.merge('userInteractionEnabled' => false))
        on_bound = convert(node.merge('userInteractionEnabled' => '@{u}'))
        tag = element_tag(off)
        if tag.match?(/\A<[a-z]/)
          expect(tag).to include(static), off
          expect(element_tag(on_bound)).to include(bound), on_bound
        else
          expect(off.lstrip).to start_with(%(<div className="contents" #{static}>)), off
          expect(on_bound.lstrip).to start_with(%(<div className="contents" #{bound}>)), on_bound
        end
        expect(off.scan('jsonuiInert(').size).to eq(1), off
        expect(convert(node)).not_to include('jsonuiInert'), 'no flag'
        expect(convert(node.merge('userInteractionEnabled' => true))).not_to include('jsonuiInert'), 'true'
      end
    end

    it 'a component root — an Embed, a NetworkImage, a linkable Label — is wrapped, the class kept on it' do
      [{ 'type' => 'Embed', 'screen' => 'S' }, { 'type' => 'NetworkImage', 'url' => 'https://e/x.png' },
       { 'type' => 'Label', 'text' => 'see https://e.com', 'linkable' => true }].each do |node|
        jsx = convert(node.merge('userInteractionEnabled' => false))
        expect(jsx.lstrip).to start_with(%(<div className="contents" #{static}>)), jsx
        expect(jsx).to match(/<(EmbedContainer|NetworkImage|LinkifyText)\b[^>]*pointer-events-none/m), jsx
      end
    end

    it 'the state holder is passed: the inert goes on the element inside JsonUISeeded' do
      %w[Segment TabView].each do |type|
        jsx = convert({ 'type' => type, 'userInteractionEnabled' => false }.merge(extra[type]))
        next unless jsx.include?('<JsonUISeeded')

        expect(jsx[/<JsonUISeeded[^>]*>/]).not_to include('jsonuiInert'), jsx
        expect(element_tag(jsx)).to include(static), jsx
      end
    end

    it 'the stopped elements and the wrapped component compile against JSX with the helper declared', :typescript_compile do
      elements = [
        convert({ 'type' => 'View', 'userInteractionEnabled' => '@{u}', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] }),
        convert({ 'type' => 'TextField', 'text' => '@{t}', 'userInteractionEnabled' => false }),
        convert({ 'type' => 'NetworkImage', 'url' => 'https://e/x.png', 'userInteractionEnabled' => '@{u}' })
      ]
      # The text field's own props (its ref, its change handlers) are not
      # what this arm checks: they are declared loosely; the spread and the
      # wrapper are what must compile.
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare namespace JSX {
          interface IntrinsicElements { input: { onChange?: (e: { target: HTMLInputElement }) => void; [attr: string]: any } }
        }
        declare const data: { u?: boolean } & Record<string, any>;
        declare const nRef: any;
        declare const NetworkImage: (props: Record<string, unknown>) => JSX.Element;
        declare function jsonuiInert(stop: boolean): Record<string, unknown>;
      TS
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
    end
  end

  describe 'the generated interactionStop helper' do
    def emit(typescript:)
      Dir.mktmpdir('rjui_stop') do |dir|
        instance = RjuiTools::CLI::Commands::BuildCommand.allocate
        instance.instance_variable_set(:@config, { 'typescript' => typescript, 'generated_directory' => File.join(dir, 'g') })
        instance.send(:emit_interaction_stop_helper)
        return File.read(File.join(dir, 'g', typescript ? 'interactionStop.ts' : 'interactionStop.js'))
      end
    end

    # The helper run under a React of each version: esbuild strips the types
    # to CommonJS, and `react` resolves to a stub that has only `version`.
    def run_under(version, source)
      BundlerDefine.skip_unless_available!
      Dir.mktmpdir('rjui_stop_run') do |dir|
        js, err, st = Open3.capture3(BundlerDefine.esbuild_path, '--loader=ts', '--format=cjs', stdin_data: source)
        raise err unless st.success?

        File.write(File.join(dir, 'helper.js'), js)
        FileUtils.mkdir_p(File.join(dir, 'node_modules', 'react'))
        File.write(File.join(dir, 'node_modules', 'react', 'index.js'), "module.exports = { version: '#{version}' };\n")
        out, err, st = Open3.capture3('node', '-e',
                                      "const { jsonuiInert } = require('./helper.js'); " \
                                      'console.log(JSON.stringify([jsonuiInert(true), jsonuiInert(false)]))', chdir: dir)
        raise err unless st.success?

        return JSON.parse(out)
      end
    end

    it 'gives React 19 a boolean and React 18 a string, and nothing when not stopped' do
      ts = emit(typescript: true)
      expect(run_under('19.2.7', ts)).to eq([{ 'inert' => true }, {}])
      expect(run_under('18.3.1', ts)).to eq([{ 'inert' => '' }, {}])
      expect(run_under('20.0.0', ts)).to eq([{ 'inert' => true }, {}])
    end

    it 'is the same function in JavaScript' do
      js = emit(typescript: false)
      expect(js).not_to match(/: boolean|: Record/)
      expect(run_under('18.3.1', js)).to eq([{ 'inert' => '' }, {}])
    end
  end

  describe 'a tap the rule makes a button: role, tab stop and keys' do
    press = "onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}"
    keyboard = %(role="button" tabIndex={0} #{press})

    # Through the generator, as `rjui build` converts a layout: annotate! gives
    # each tap its shape, and the converters read it.
    def generate(layout)
      generator = RjuiTools::React::ReactGenerator.new(config)
      generator.send(:convert_component, JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(layout))))
    end

    # The line that opens the element with this id (an attribute can hold
    # `=>`, so a `[^>]*` tag scan stops short).
    def tag_of(jsx, id)
      jsx.lines.find { |l| l.match?(/<[A-Za-z][\w.]*\b[^\n]*\bid="#{id}"/) } or raise "no element #{id} in\n#{jsx}"
    end

    # The generator's own entry, as `rjui build` calls it: it annotates the
    # tree (the arms around this one annotate for themselves), and imports
    # the inert helper where a stop is.
    it 'the build entry annotates the layout, and imports the helper where a stop is' do
      out = RjuiTools::React::ReactGenerator.new(config.merge('typescript' => true)).generate('Probe', {
        'type' => 'View', 'child' => [
          { 'type' => 'Label', 'id' => 'tap', 'text' => 'x', 'onClick' => '@{onTap}' },
          { 'type' => 'View', 'id' => 'stop', 'userInteractionEnabled' => false, 'child' => [{ 'type' => 'Label', 'text' => 'y' }] }
        ]
      })
      expect(tag_of(out, 'tap')).to include(keyboard)
      expect(out).to include("import { jsonuiInert } from '@/generated/interactionStop';")
      expect(RjuiTools::React::ReactGenerator.new(config.merge('typescript' => true)).generate('Plain', { 'type' => 'View' }))
        .not_to include('interactionStop')
    end

    it 'a Label, an Image, an IconLabel, a Blur, a CircleView and a GradientView with onClick (`button`)' do
      %w[Label Image IconLabel Blur CircleView GradientView].each do |type|
        jsx = generate({ 'type' => 'View', 'child' => [{ 'type' => type, 'id' => 'tap', 'onClick' => '@{onTap}' }.merge(extra[type] || {})] })
        expect(tag_of(jsx, 'tap')).to include(keyboard), "#{type}\n#{jsx}"
      end
    end

    it 'a View with onClick holding text (`combine`)' do
      jsx = generate({ 'type' => 'View', 'id' => 'tap', 'onClick' => '@{onTap}', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(tag_of(jsx, 'tap')).to include(keyboard)
    end

    it 'a NetworkImage and a linkable Label take it through their props' do
      jsx = generate({ 'type' => 'View', 'child' => [
        { 'type' => 'NetworkImage', 'id' => 'img', 'url' => 'https://e/x.png', 'onClick' => '@{onTap}' },
        { 'type' => 'Label', 'id' => 'lnk', 'text' => 'see https://e.com', 'linkable' => true, 'onClick' => '@{onTap}' }
      ] })
      expect(tag_of(jsx, 'img')).to include(keyboard)
      expect(tag_of(jsx, 'lnk')).to include(keyboard)
    end

    it 'not on `none` — a control, an app component, a tap holding a control — nor without a tap' do
      jsx = generate({ 'type' => 'View', 'child' => [
        { 'type' => 'Button', 'id' => 'btn', 'text' => 't', 'onClick' => '@{onTap}' },
        { 'type' => 'AppCard', 'id' => 'app', 'onClick' => '@{onTap}' },
        { 'type' => 'View', 'id' => 'holder', 'onClick' => '@{onTap}', 'child' => [{ 'type' => 'Switch', 'isOn' => '@{on}' }] },
        { 'type' => 'Label', 'id' => 'plain', 'text' => 'x' }
      ] })
      expect(jsx).not_to include('role="button"'), jsx
      expect(jsx).not_to include('tabIndex'), jsx
    end

    it 'not on a tap a stop holds (no shape: inert takes it away), nor under canTap / enabled false' do
      jsx = generate({ 'type' => 'View', 'child' => [
        { 'type' => 'View', 'userInteractionEnabled' => false, 'child' => [{ 'type' => 'Label', 'id' => 'in', 'text' => 'x', 'onClick' => '@{onTap}' }] },
        { 'type' => 'Label', 'id' => 'own', 'text' => 'x', 'onClick' => '@{onTap}', 'userInteractionEnabled' => false },
        { 'type' => 'Label', 'id' => 'cantap', 'text' => 'x', 'onClick' => '@{onTap}', 'canTap' => false },
        { 'type' => 'Label', 'id' => 'disabled', 'text' => 'x', 'onClick' => '@{onTap}', 'enabled' => false }
      ] })
      expect(jsx).not_to include('role='), jsx
    end

    it 'inside a bound stop it is a button while open (inert takes it while closed)' do
      jsx = generate({ 'type' => 'View', 'userInteractionEnabled' => '@{u}', 'child' => [{ 'type' => 'Label', 'id' => 'in', 'text' => 'x', 'onClick' => '@{onTap}' }] })
      expect(tag_of(jsx, 'in')).to include(keyboard)
    end

    it 'a bound canTap and a bound enabled gate the role, the tab stop and the keys' do
      jsx = generate({ 'type' => 'View', 'child' => [
        { 'type' => 'Label', 'id' => 'ct', 'text' => 'x', 'onClick' => '@{onTap}', 'canTap' => '@{c}' },
        { 'type' => 'Label', 'id' => 'both', 'text' => 'x', 'onClick' => '@{onTap}', 'canTap' => '@{c}', 'enabled' => '@{on}' }
      ] })
      ct = tag_of(jsx, 'ct')
      expect(ct).to include("role={(data.c) ? 'button' : undefined} tabIndex={(data.c) ? 0 : undefined}")
      expect(ct).to include("if ((data.c) && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.currentTarget.click(); }")
      expect(tag_of(jsx, 'both')).to include("role={(data.c) && (data.on) ? 'button' : undefined}")
    end

    it 'the keys compile on a span, a div, an img and the two components', :typescript_compile do
      jsx = generate({ 'type' => 'View', 'id' => 'tap', 'onClick' => '@{onTap}', 'child' => [
        { 'type' => 'Label', 'text' => 'x' }
      ] })
      more = generate({ 'type' => 'View', 'child' => [
        { 'type' => 'Label', 'id' => 'l', 'text' => 'x', 'onClick' => '@{onTap}', 'canTap' => '@{c}' },
        { 'type' => 'Image', 'id' => 'i', 'srcName' => 'x', 'onClick' => '@{onTap}' },
        { 'type' => 'NetworkImage', 'id' => 'n', 'url' => 'https://e/x.png', 'onClick' => '@{onTap}' },
        { 'type' => 'Label', 'id' => 'k', 'text' => 'see https://e.com', 'linkable' => true, 'onClick' => '@{onTap}' }
      ] })
      # The keys' handler is typed where React types it — onKeyDown on the
      # element — so `e.currentTarget.click()` is checked against the DOM.
      # `onTap` takes the event: a bound canTap's onClick passes it
      # (can_tap_gated_click), which a `() => void` handler refuses — not this
      # arm's question.
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare namespace React {
          type CSSProperties = { [property: string]: string | number | undefined };
          interface KeyboardEvent<T> { key: string; preventDefault(): void; currentTarget: T }
        }
        declare namespace JSX {
          interface IntrinsicElements {
            span: { onKeyDown?: (e: React.KeyboardEvent<HTMLSpanElement>) => void; onClick?: (e: unknown) => void; [attr: string]: any };
            div: { onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void; onClick?: (e: unknown) => void; [attr: string]: any };
            img: { onKeyDown?: (e: React.KeyboardEvent<HTMLImageElement>) => void; onClick?: (e: unknown) => void; [attr: string]: any };
          }
        }
        declare const data: { onTap?: (e?: unknown) => void; c?: boolean };
        #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
        #{TypeScriptCompiler.template_declarations('linkify_text.tsx', 'LinkifyTextProps')}
        declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
        declare const LinkifyText: (props: LinkifyTextProps) => JSX.Element;
      TS
      expect(TypeScriptCompiler.component(jsx, more)).to compile_as_typescript.with_ambient(ambient)
    end
  end
end
