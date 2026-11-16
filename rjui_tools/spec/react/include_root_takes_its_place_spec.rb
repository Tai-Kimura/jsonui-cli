# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/configuration_runtime'
require_relative '../../lib/cli/commands/build_command'
require 'react/react_generator'
require 'react/include_place'
require 'react/converters/converter_table'
require 'react/converters/include_converter'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'

# An included layout's root takes what the including container hands its
# children, as sjui and kjui (which expand the include before converting it)
# give it (ticket rjui-include-root-relative-placement-dropped). Measured on
# v2.5.22 in Chromium, a 20x20 root in a 100x100 frame, a direct child against
# the same JSON as an include's root:
#
#   overlay, alignLeft + alignBottom        (0,80)  vs (0,0)
#   overlay, centerInParent                 (40,40) vs (40,0)
#   overlay, alignBottom + margins 10       (10,70) vs (10,0)
#   stacked overlay (wrapContent), alignTop (0,0)   vs (0,45)
#   row, height matchParent                 w20     vs w90 (flex-1 grew it sideways)
#   row fillEqually, no width               w90     vs w0
#   column 100x100, a long label            h100    vs h120 (the wrapContent cap)
#   one child (flex-col wrapper), control   (80,80) vs (80,80)
#
# A constraint against a sibling across the include (alignTopOfView on the
# root) is ticket rjui-include-root-sibling-constraint-dropped, not this.
RSpec.describe 'an included layout root takes its place in the including layout' do
  Place = RjuiTools::React::IncludePlace

  def converters = RjuiTools::React::Converters::ConverterTable.table

  def box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20, 'background' => '#FF0000' }.merge(extra)
  end

  def filler(id) = box(id, 'width' => 10, 'height' => 10, 'background' => '#0000FF')

  describe 'the context keys' do
    # Everything a container writes into a child's json for the child to read
    # has to reach an include's root too — a key added to the converters and
    # not here is that key dropped at every include again.
    it 'are every key a converter adds to a child' do
      lib = File.expand_path('../../lib/react', __dir__)
      written = Dir[File.join(lib, '**/*.rb')].flat_map { |f| File.read(f).scan(/'(_[a-z_]+)' =>/).flatten }.uniq
      expect(written.sort).to eq(Place::CONTEXT_KEYS.sort)
    end
  end

  describe 'the root class' do
    it 'a plain class goes through the helper' do
      out = Place.apply(%(  <div id="a" className="w-[20px] mt-auto" />))
      expect(out).to eq(%(  <div id="a" className={jsonuiPlaceClass("w-[20px] mt-auto", jsonuiPlace)} />))
    end

    it 'a template literal keeps its run-time parts, braces and > inside them included' do
      jsx = "  {data.v !== \"gone\" && (\n  <span onClick={() => x > 1 && f({ a: `}` })} className={`w-fit mt-auto ${data.v === \"invisible\" ? \"invisible\" : \"\"}`}>x</span>\n  )}"
      out = Place.apply(jsx)
      expect(out).to include('className={jsonuiPlaceClass(`w-fit mt-auto ${data.v === "invisible" ? "invisible" : ""}`, jsonuiPlace)}')
      expect(Place.root_class_tokens(jsx)).to eq(%w[w-fit mt-auto])
    end

    it 'a root with no class gets one; a root that calls a partial hands the prop on; any other component is left' do
      expect(Place.apply('<div id="a" />')).to eq('<div className={jsonuiPlaceClass("", jsonuiPlace)} id="a" />')
      expect(Place.apply('<PM2 idPrefix={idPrefix} />', ['PM2'])).to eq('<PM2 jsonuiPlace={jsonuiPlace} idPrefix={idPrefix} />')
      expect(Place.apply('<Other />', ['PM2'])).to eq('<Other />')
    end

    it 'the prop value is the difference, nothing when there is none' do
      expect(Place.prop_value(%w[a b], %w[a b])).to be_nil
      expect(Place.prop_value(%w[flex-1 w-2], %w[w-2 self-stretch])).to eq('{{ add: "self-stretch", drop: "flex-1" }}')
    end
  end

  # Layouts on disk, as `jui build` hands them: _layouts_dir and _place_stems.
  def with_layouts(layouts)
    Dir.mktmpdir('rjui_include_place') do |dir|
      layouts.each { |stem, tree| File.write(File.join(dir, "#{stem}.json"), JSON.generate(tree)) }
      yield({ 'use_tailwind' => true, 'typescript' => true, '_layouts_dir' => dir,
              '_place_stems' => layouts.keys.select { |k| k.start_with?('p_') }, '_place_cache' => {} })
    end
  end

  def frame(id, children, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 100, 'height' => 100, 'child' => children }.merge(extra)
  end

  def container_jsx(node, config)
    converters.fetch(node['type']).new(node, config).convert_node(0)
  end

  describe 'an include call site' do
    it 'hands an overlay placement, and nothing where the container hands nothing' do
      with_layouts('p_a' => box('a', 'alignLeft' => true, 'alignBottom' => true)) do |config|
        overlay = container_jsx(frame('f', [{ 'include' => 'p_a' }, filler('x')]), config)
        expect(overlay).to include('<PA jsonuiPlace={{ add: "absolute bottom-0 left-0" }} />')
        single = container_jsx(frame('f', [{ 'include' => 'p_a' }]), config)
        expect(single).to include('<PA />')
      end
    end

    it 'swaps a column height for a row one' do
      with_layouts('p_e' => box('e', 'height' => 'matchParent')) do |config|
        row = container_jsx(frame('f', [{ 'include' => 'p_e' }, filler('x')], 'orientation' => 'horizontal'), config)
        expect(row).to include('<PE jsonuiPlace={{ add: "self-stretch", drop: "flex-1 min-w-0 min-h-0" }} />')
      end
    end

    it 'hands nothing to a layout that does not take the prop' do
      with_layouts('p_a' => box('a', 'alignBottom' => true)) do |config|
        out = container_jsx(frame('f', [{ 'include' => 'p_a' }, filler('x')]), config.merge('_place_stems' => []))
        expect(out).not_to include('jsonuiPlace')
      end
    end
  end

  describe 'the generated component' do
    def generate(name, stem, tree, config)
      RjuiTools::React::ReactGenerator.new(config).generate(name, tree, namespace_stem: stem)
    end

    it 'an included layout takes jsonuiPlace and puts its root class through the helper' do
      with_layouts('p_a' => box('a', 'alignBottom' => true)) do |config|
        out = generate('PA', 'p_a', box('a', 'alignBottom' => true), config)
        expect(out).to include("import { jsonuiPlaceClass } from '@/generated/includePlace';")
        expect(out).to include('jsonuiPlace?: { add?: string; drop?: string };')
        expect(out).to match(/export const PA = \(\{ data, id, jsonuiPlace \}: PAProps\)/)
        expect(out).to include('className={jsonuiPlaceClass("w-[20px] h-[20px] shrink-0 bg-[#FF0000] mt-auto", jsonuiPlace)}')
      end
    end

    it 'control: a layout nothing includes comes out without it' do
      with_layouts('p_a' => box('a')) do |config|
        out = generate('Screen', 'screen', frame('f', [box('a')]), config)
        expect(out).not_to include('jsonuiPlace')
      end
    end
  end

  describe 'the helper' do
    def helper_source(typescript: true)
      Dir.mktmpdir('rjui_include_place_helper') do |dir|
        instance = RjuiTools::CLI::Commands::BuildCommand.allocate
        instance.instance_variable_set(:@config, { 'typescript' => typescript,
                                                   'generated_directory' => File.join(dir, 'generated') })
        instance.send(:emit_include_place_helper)
        File.read(File.join(dir, 'generated', typescript ? 'includePlace.ts' : 'includePlace.js'))
      end
    end

    it 'type-checks under --strict' do
      expect(helper_source).to compile_as_typescript
    end

    it 'drops, keeps and adds' do
      out, err, st = Open3.capture3('node', '--input-type=module', '-e', <<~JS)
        #{ConfigurationRuntime.global_js}
        #{helper_source(typescript: false)}
        console.log(JSON.stringify([
          jsonuiPlaceClass('w-2  flex-1 min-w-0 mt-auto', { add: 'self-stretch', drop: 'flex-1 min-w-0' }),
          jsonuiPlaceClass('w-2 mt-auto', undefined),
          jsonuiPlaceClass('w-2', { add: 'absolute bottom-0' }),
        ]));
      JS
      expect(st.success?).to be(true), err
      expect(JSON.parse(out)).to eq(['w-2 mt-auto self-stretch', 'w-2 mt-auto', 'w-2 absolute bottom-0'])
    end
  end

  describe 'drawn in headless Chromium' do
    def support_dir = File.expand_path('../support', __dir__)
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # One frame per case: the subject as a direct child, and as the root of
    # an included layout. Each case's other children are the same in both.
    CASES = {
      'a' => [{}, { 'alignLeft' => true, 'alignBottom' => true }, [], [:fill]],
      'b' => [{}, { 'centerInParent' => true }, [], [:fill]],
      'i' => [{}, { 'alignLeft' => true, 'alignBottom' => true, 'leftMargin' => 10, 'bottomMargin' => 10 }, [], [:fill]],
      'k' => [{ 'width' => 'wrapContent' }, { 'alignTop' => true }, [:fill], []],
      'e' => [{ 'orientation' => 'horizontal' }, { 'height' => 'matchParent' }, [], [:fill]],
      'f' => [{ 'orientation' => 'horizontal', 'distribution' => 'fillEqually' }, { 'width' => nil }, [], [:fill]],
      'g' => [{ 'orientation' => 'vertical' }, :label, [], []],
      'j' => [{ 'orientation' => 'vertical' }, { 'alignBottom' => true, 'alignRight' => true }, [], []],
      'm' => [{}, { 'alignLeft' => true, 'alignBottom' => true }, [], [:fill], :nested]
    }.freeze

    def subject_node(id, attrs)
      return { 'type' => 'Label', 'id' => id, 'text' => 'w' * 40, 'background' => '#FF0000' } if attrs == :label

      node = box(id, attrs.compact)
      node.delete('width') if attrs.key?('width') && attrs['width'].nil?
      node
    end

    def build_page
      layouts = {}
      frames = []
      CASES.each do |key, (frame_attrs, attrs, before, after, nested)|
        %w[direct inc].each do |mode|
          sid = "s_#{key}_#{mode}"
          node = subject_node(sid, attrs)
          if mode == 'inc'
            if nested
              layouts["p_#{key}2"] = node
              layouts["p_#{key}"] = { 'include' => "p_#{key}2" }
            else
              layouts["p_#{key}"] = node
            end
            node = { 'include' => "p_#{key}" }
          end
          kids = before.map { filler("b_#{key}_#{mode}") } + [node] + after.map { filler("a_#{key}_#{mode}") }
          frames << frame("frame_#{key}_#{mode}", kids, frame_attrs)
        end
      end
      [layouts, frames]
    end

    def draw(config, layouts, frames)
      forward = config['_place_stems'].map { |s| Place.component_name(s) }
      components = layouts.map do |stem, tree|
        root = if tree['include']
                 RjuiTools::React::Converters::IncludeConverter.new(tree, config).convert_node(0)
               else
                 converters.fetch(tree['type']).new(tree, config).convert_node(0)
               end
        "const #{Place.component_name(stem)} = ({ jsonuiPlace }) => (#{Place.apply(root, forward)});"
      end
      elements = frames.map { |f| "h('div', { className: 'w-[120px] h-[120px]' }, #{container_jsx(f, config)})" }
      Dir.mktmpdir('rjui_include_place_draw') do |dir|
        File.write(File.join(dir, 'content.html'), (components + elements).join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          #{ConfigurationRuntime.global_js}
          const h = (tag, props, ...kids) => {
            if (typeof tag === 'function') return tag(props || {});
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v)) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.setAttribute(k, v);
            }
            for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          #{components.join("\n")}
          #{helper_js}
          const $s = new Proxy({}, { get: () => '' });
          for (const el of [#{elements.join(",\n")}]) document.body.append(el);
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle',
                                  '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body style="margin:0;display:flex;flex-wrap:wrap"><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const page = await browser.newPage({ viewport: { width: 1400, height: 800 } });
            page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
            await page.goto('file://#{File.join(dir, 'page.html')}');
            const out = await page.evaluate(() => {
              const r = {};
              for (const s of document.querySelectorAll('[id^="s_"]')) {
                const f = document.getElementById('frame_' + s.id.slice(2)).getBoundingClientRect();
                const b = s.getBoundingClientRect();
                r[s.id.slice(2)] = [b.left - f.left, b.top - f.top, b.width, b.height].map(Math.round);
              }
              return r;
            });
            console.log('AT' + JSON.stringify(out));
            await browser.close();
          })();
        JS
        log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: support_dir)
        raise "playwright: #{log}" unless st.success?

        JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
      end
    end

    def helper_js
      Dir.mktmpdir('rjui_include_place_helper') do |dir|
        instance = RjuiTools::CLI::Commands::BuildCommand.allocate
        instance.instance_variable_set(:@config, { 'typescript' => false, 'generated_directory' => dir })
        instance.send(:emit_include_place_helper)
        File.read(File.join(dir, 'includePlace.js')).gsub(/^export /, '')
      end
    end

    it 'draws the root where the same JSON draws as a direct child' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      layouts, frames = build_page
      with_layouts(layouts) do |config|
        got = draw(config, layouts, frames)
        CASES.each_key do |key|
          expect(got["#{key}_inc"]).to eq(got["#{key}_direct"]), "#{key}: #{got.inspect}"
        end
        # the measure itself: the direct children are where native draws them
        expect(got.values_at('a_direct', 'b_direct', 'e_direct', 'f_direct', 'g_direct'))
          .to eq([[0, 80, 20, 20], [40, 40, 20, 20], [0, 0, 20, 100], [0, 0, 90, 20], [0, 0, 100, 100]]), got.inspect

        # control: without the prop (v2.5.22) the include draws elsewhere
        bare = draw(config.merge('_place_stems' => []), layouts, frames)
        expect(%w[a b i k e f g].reject { |k| bare["#{k}_inc"] != bare["#{k}_direct"] }).to eq([]), bare.inspect
      end
    end
  end
end
