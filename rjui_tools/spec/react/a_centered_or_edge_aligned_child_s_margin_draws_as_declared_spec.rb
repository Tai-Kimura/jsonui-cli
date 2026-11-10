# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A margin on the axis a child centers itself on, or on the side an edge
# alignment pushes from, draws as the declaration says (attribute_semantics
# margins.offsetModel: "an explicit center declaration disables that axis
# margin"; the margin still counts in a wrapContent parent's size — iOS, both
# modes). Until jsonui-cli 2.5.26 the margin's class stayed beside the
# centering and won (ticket relative-center-with-margin-diverges-from-
# declaration). Drawn in Chromium through the conformance web host, a 20x20
# child in a 100x100 frame, margin 10, the declaration 40:
#
#   one child (flex-col), centerHorizontal + leftMargin   x = 10   (the auto margins lost)
#   two children (absolute), centerHorizontal + leftMargin x = 50   (the translate and the margin)
#   stacked (grid), centerHorizontal + leftMargin          x = 10   (the self-alignment lost)
#   wrapContent parent, centerHorizontal + leftMargin      parent 30, x = 10 (the declaration: 5)
#   wrapContent parent, a bound centerHorizontal           parent 20, x = 0  (the margin dropped)
#   one child, alignRight + leftMargin                     x = 10 (the declaration: 80)
#   wrapContent parent, alignBottom + topMargin            parent 20 (the declaration: 30)
#
# 73 rows of 288 off in all (cen 51/168, mar 6/80, cwr 16/40) and 12 of 20
# bound and literal; 0 after.
RSpec.describe "a centered or edge-aligned child's margin draws as declared" do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20, 'background' => '#FF0000' }.merge(extra)
  end

  def frame(id, kids, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 100, 'height' => 100, 'background' => '#DDDDDD', 'child' => kids }.merge(extra)
  end

  def jsx(node, typescript: false)
    converters.fetch(node['type']).new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert_node(0)
  end

  def classes_of(out, id)
    out[/id="#{id}" className="([^"]*)"/, 1].to_s.split
  end

  def filler(id, extra = {}) = box(id, { 'width' => 6, 'height' => 6, 'background' => '#000000' }.merge(extra))

  describe 'what is emitted' do
    it 'a flow child centered on its cross axis: the half of the margins on each side and align-self' do
      c = classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true, 'leftMargin' => 10)])), 's')
      expect(c).to include('ml-[0.3125rem]', 'mr-[0.3125rem]', 'self-center')
      expect(c).not_to include('mx-auto', 'ml-[0.625rem]')
    end

    it 'a flow child centered on its main axis: the auto margins and no margin where the parent has a size, ' \
       'the half on each side where it wraps' do
      fixed = classes_of(jsx(frame('f', [box('s', 'centerVertical' => true, 'topMargin' => 10)])), 's')
      expect(fixed).to include('my-auto')
      expect(fixed.grep(/\Am[tb]-\[/)).to be_empty
      wraps = classes_of(jsx(frame('f', [box('s', 'centerVertical' => true, 'topMargin' => 10)],
                                   'width' => 'wrapContent', 'height' => 'wrapContent')), 's')
      expect(wraps).to include('mt-[0.3125rem]', 'mb-[0.3125rem]')
      expect(wraps).not_to include('my-auto')
    end

    it 'a stacked child: the half on each side, no auto margins; an absolute one: no margin on the axis' do
      stacked = classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true, 'leftMargin' => 10),
                                           filler('k', 'height' => 100)], 'height' => 'wrapContent')), 's')
      expect(stacked).to include('justify-self-center', 'ml-[0.3125rem]', 'mr-[0.3125rem]')
      expect(stacked).not_to include('mx-auto')
      absolute = classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true, 'leftMargin' => 10), filler('k')])), 's')
      expect(absolute).to include('left-1/2', '-translate-x-1/2')
      expect(absolute.grep(/\Am[lrx]-/)).to be_empty
    end

    it 'the other axis keeps its own margins, a `margins` array spread into the four' do
      c = classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true, 'margins' => [4, 10])])), 's')
      expect(c).to include('mt-[0.25rem]', 'mb-[0.25rem]', 'ml-[0.625rem]', 'mr-[0.625rem]', 'self-center')
    end

    it "an edge-aligned flow child: the auto margin where the parent has a size, the side's own margin where it wraps" do
      fixed = classes_of(jsx(frame('f', [box('s', 'alignRight' => true, 'leftMargin' => 10)])), 's')
      expect(fixed).to include('ms-auto')
      expect(fixed).not_to include('ml-[0.625rem]')
      wraps = classes_of(jsx(frame('f', [box('s', 'alignBottom' => true, 'topMargin' => 10)],
                                   'width' => 'wrapContent', 'height' => 'wrapContent')), 's')
      expect(wraps).to include('mt-[0.625rem]')
      expect(wraps).not_to include('mt-auto')
    end

    it 'a bound center under a wrapContent parent holds the half of the margins on each side while it is on' do
      out = jsx(frame('f', [box('s', 'centerHorizontal' => '@{c}', 'leftMargin' => 10)],
                      'width' => 'wrapContent', 'height' => 'wrapContent'))
      expect(out).to include("marginInline: data.c ? '0.3125rem' : undefined", "alignSelf: data.c ? 'center' : undefined")
      fixed = jsx(frame('f', [box('s', 'centerHorizontal' => '@{c}', 'leftMargin' => 10)]))
      expect(fixed).to include("marginInline: data.c ? 'auto' : undefined")
      expect(fixed).not_to include('alignSelf')
    end

    it 'control: a centered or aligned child with no margin on that axis comes out as it always did' do
      expect(classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true)])), 's')).to include('mx-auto')
      expect(classes_of(jsx(frame('f', [box('s', 'centerHorizontal' => true, 'topMargin' => 10)])), 's'))
        .to include('mx-auto', 'mt-[0.625rem]')
      expect(classes_of(jsx(frame('f', [box('s', 'alignRight' => true, 'rightMargin' => 10)])), 's'))
        .to include('ms-auto', 'mr-[0.625rem]')
    end

    it 'the bound emit compiles as TypeScript', :typescript_compile do
      elements = [jsx(frame('f', [box('s', 'centerHorizontal' => '@{c}', 'centerVertical' => '@{c}', 'leftMargin' => 10,
                                      'topMargin' => 10)], 'width' => 'wrapContent', 'height' => 'wrapContent'), typescript: true)]
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare const data: { c: boolean };
        declare namespace React { type CSSProperties = { [property: string]: string | number | undefined }; }
      TS
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # Each case: [the frame's own attributes, the subject's, the siblings after it, the declared [x, y, frame w, frame h]].
    def wrap = { 'width' => 'wrapContent', 'height' => 'wrapContent' }

    def cases = {
      'flow_cH_ml' => [{}, { 'centerHorizontal' => true, 'leftMargin' => 10 }, [], [40, 0, 100, 100]],
      'flow_cV_mt' => [{}, { 'centerVertical' => true, 'topMargin' => 10 }, [], [0, 40, 100, 100]],
      'flow_cIP_all' => [{}, { 'centerInParent' => true, 'margins' => [10] }, [], [40, 40, 100, 100]],
      'abs_cH_ml' => [{}, { 'centerHorizontal' => true, 'leftMargin' => 10 }, [{}], [40, 0, 100, 100]],
      'abs_cV_mb' => [{}, { 'centerVertical' => true, 'bottomMargin' => 10 }, [{}], [0, 40, 100, 100]],
      'grid_cH_mr' => [{ 'height' => 'wrapContent' }, { 'centerHorizontal' => true, 'rightMargin' => 10 },
                       [{ 'height' => 100 }], [40, 0, 100, 100]],
      'grid_cV_mt' => [{ 'height' => 'wrapContent' }, { 'centerVertical' => true, 'topMargin' => 10 },
                       [{ 'height' => 100 }], [0, 40, 100, 100]],
      'wrap_cH_ml' => [wrap, { 'centerHorizontal' => true, 'leftMargin' => 10 }, [], [5, 0, 30, 20]],
      'wrap_cV_tb' => [wrap, { 'centerVertical' => true, 'topMargin' => 10, 'bottomMargin' => 30 }, [], [0, 20, 20, 60]],
      'wrap2_cH_ml' => [wrap, { 'centerHorizontal' => true, 'leftMargin' => 10 }, [{}], [5, 0, 30, 20]],
      'bound_wrap_cH_ml' => [wrap, { 'centerHorizontal' => '@{on}', 'leftMargin' => 10 }, [], [5, 0, 30, 20]],
      'bound_off_wrap_cH_ml' => [wrap, { 'centerHorizontal' => '@{off}', 'leftMargin' => 10 }, [], [10, 0, 30, 20]],
      'bound_cH_ml' => [{}, { 'centerHorizontal' => '@{on}', 'leftMargin' => 10 }, [], [40, 0, 100, 100]],
      'edge_aR_ml' => [{}, { 'alignRight' => true, 'leftMargin' => 10 }, [], [80, 0, 100, 100]],
      'edge_wrap_aB_mt' => [wrap, { 'alignBottom' => true, 'topMargin' => 10 }, [], [0, 10, 20, 30]],
      # controls: no margin on the centered axis, a margin on the other one
      'ctl_cH' => [{}, { 'centerHorizontal' => true }, [], [40, 0, 100, 100]],
      'ctl_cH_mt' => [{}, { 'centerHorizontal' => true, 'topMargin' => 10 }, [], [40, 10, 100, 100]]
    }

    # {case => [x, y, frame w, frame h]}: the subject's offset in its frame, and the frame's size.
    def draw(elements, data)
      Dir.mktmpdir('rjui_center_margin') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v)) if (x != null) el.style[p] = x; }
              else if (k === 'id') el.setAttribute(k, v);
            }
            for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const data = #{data.to_json};
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.className = 'w-[120px] h-[120px]'; box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const page = await browser.newPage({ viewport: { width: 400, height: 800 } });
            page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
            await page.goto('file://#{File.join(dir, 'page.html')}');
            const out = await page.evaluate(() => {
              const r = {};
              for (const s of document.querySelectorAll('[id^="s_"]')) {
                const f = s.parentElement.getBoundingClientRect(), b = s.getBoundingClientRect();
                r[s.id.slice(2)] = [b.left - f.left, b.top - f.top, f.width, f.height].map(Math.round);
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

    it 'puts the child where the declaration does, in every way the parent centers or aligns it' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      elements = cases.map do |key, (frame_attrs, attrs, after, _)|
        kids = [box("s_#{key}", attrs)] + after.each_with_index.map { |extra, i| filler("k_#{key}_#{i}", extra) }
        jsx(frame("f_#{key}", kids, frame_attrs))
      end
      got = draw(elements, { on: true, off: false })
      want = cases.transform_values(&:last)
      expect(got).to eq(want), (want.keys.reject { |k| got[k] == want[k] }.map { |k| "#{k}: #{got[k]} (declared #{want[k]})" }.join("\n"))
    end
  end
end
