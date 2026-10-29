# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A declared alignment can be two classes on web, and the second one is what
# moves the content (ticket rjui-label-bound-textalign-has-no-justify-on-web).
# The family, measured on v2.3.26 over every bindable attribute (272 pairs:
# none / declared / `@{v}`), then drawn in headless Chromium:
#
#   Label textAlign, bound          text-* + justify-*  ->  style textAlign only:
#                                   a bound right / center stayed at the start
#                                   (0 px left, 188 px right in a 240 wide label),
#                                   a bound left beside gravity right went right
#   Label textAlign, a size class   lg:text-* only, no lg:justify-*: the text
#                                   stayed where the base put it
#   NetworkImage contentMode, bound object-none + object-top -> the fit prop only:
#                                   top / bottom / left / right drew in the middle
#
# A single-run Label is a flex row, so text-align does not move its text;
# justify-* does. A Label that is not a flex row (lines, linkable) needs none.
RSpec.describe 'a bound or size-class alignment draws like a declared one' do
  def converters = RjuiTools::React::Converters::ConverterTable.table
  def support_dir = File.expand_path('../support', __dir__)

  def jsx(node, typescript: false)
    converters.fetch(node['type']).new(node, { 'use_tailwind' => true, 'typescript' => typescript }).convert_node(0).strip
  end

  def label(id, extra)
    { 'type' => 'Label', 'id' => id, 'text' => 'Go', 'width' => 240, 'height' => 32 }.merge(extra)
  end

  def image(id, mode)
    { 'type' => 'NetworkImage', 'id' => id, 'url' => '@{src}', 'width' => 80, 'height' => 80, 'contentMode' => mode }
  end

  describe 'what is emitted' do
    it 'a bound textAlign on a single-run label also sets justifyContent, by the declared spellings' do
      out = jsx(label('l', 'textAlign' => '@{align}'))
      expect(out).to include("justifyContent: (({ 'Left': 'flex-start', 'Center': 'center', 'Right': 'flex-end', " \
                             "'left': 'flex-start', 'center': 'center', 'right': 'flex-end' })[String(data.align)])")
    end

    it 'a label that is not a flex row gets no justifyContent' do
      expect(jsx(label('l', 'textAlign' => '@{align}', 'lines' => 2))).not_to include('justifyContent')
      expect(jsx(label('l', 'textAlign' => '@{align}', 'linkable' => true))).not_to include('justifyContent')
    end

    it "a size class's textAlign brings its justify-* (and no reset of the lines beside its own text-*)" do
      cls = jsx(label('l', 'textAlign' => 'Left', 'responsive' => { 'regular' => { 'textAlign' => 'Right' } }))[/className="([^"]*)"/, 1].split
      expect(cls.select { |c| c.start_with?('lg:') }).to contain_exactly('lg:text-right', 'lg:justify-end')
      cls = jsx(label('l', 'gravity' => 'right', 'responsive' => { 'regular' => { 'textAlign' => 'Center' } }))[/className="([^"]*)"/, 1].split
      expect(cls.select { |c| c.start_with?('lg:') }).to contain_exactly('lg:text-center', 'lg:justify-center')
    end

    it "a bound NetworkImage contentMode puts the position in the class, its names written whole" do
      out = jsx(image('i', '@{mode}'))
      expect(out).to include("'top': 'object-top'", "'bottom': 'object-bottom'", "'left': 'object-left'", "'right': 'object-right'")
      expect(out).to match(/className=\{`[^`]*\$\{\(\{[^}]*\}\)\[String\(data\.mode\)\] \?\? ''\}`\}/)
    end

    it 'control: the declared forms are as they were' do
      expect(jsx(label('l', 'textAlign' => 'Right'))).to include('text-right', 'justify-end')
      expect(jsx(label('l', 'textAlign' => 'Right'))).not_to include('style=')
      expect(jsx(image('i', 'top'))).to include('className="w-[80px] h-[80px] shrink-0 object-none object-top"')
    end

    it 'the emit compiles as TypeScript', :typescript_compile do
      elements = [label('a', 'textAlign' => '@{align}'), label('b', 'textAlign' => '@{align}', 'gravity' => 'right'),
                  image('c', '@{mode}')].map { |n| jsx(n, typescript: true) }
      ambient = TypeScriptCompiler::AMBIENT + <<~TS
        declare const data: { align: string; mode: string; src: string };
        declare namespace React {
          type CSSProperties = { [property: string]: string | number | undefined };
          type ComponentProps<T> = T extends (props: infer P) => unknown ? P : never;
        }
        #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
        declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
      TS
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
    end
  end

  describe 'drawn in headless Chromium' do
    def node_modules = File.join(support_dir, 'node_modules')

    def tools_ready?
      %w[.bin/esbuild .bin/tailwindcss playwright].all? { |p| File.exist?(File.join(node_modules, p)) }
    end

    # {id => reading} at each width: a label's text as [left gap, right gap]
    # in px, an image's object-position.
    def draw(elements, data, widths)
      Dir.mktmpdir('rjui_bound_align') do |dir|
        File.write(File.join(dir, 'content.html'), elements.join("\n"))
        File.write(File.join(dir, 'in.css'), %(@import "#{node_modules}/tailwindcss/index.css" source(none);\n@source "./content.html";\n))
        log, st = Open3.capture2e(File.join(node_modules, '.bin/tailwindcss'), '-i', File.join(dir, 'in.css'), '-o', File.join(dir, 'out.css'))
        raise "tailwindcss: #{log}" unless st.success?

        File.write(File.join(dir, 'app.jsx'), <<~JSX)
          const h = (tag, props, ...kids) => {
            if (typeof tag === 'function') return tag(props || {});
            const el = document.createElement(tag);
            for (const [k, v] of Object.entries(props || {})) {
              if (k === 'className') el.className = v;
              else if (k === 'style') { for (const [p, x] of Object.entries(v)) if (x != null) el.style[p] = x; }
              else if (k === 'id' || k === 'src') el.setAttribute(k, v);
            }
            for (const c of kids.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
            return el;
          };
          const React = { Fragment: 'div' };
          // lib/react/templates/network_image.tsx's own render: the class it is given, then its fit class.
          const NetworkImage = ({ id, src, className = '', contentMode = 'contain' }) => {
            const objectFitMap = { cover: 'object-cover', contain: 'object-contain', fill: 'object-fill', none: 'object-none', scaleDown: 'object-scale-down', fit: 'object-contain' };
            return h('img', { id, src, className: `${className} ${objectFitMap[contentMode] || 'object-contain'}` });
          };
          const data = #{data.to_json};
          for (const el of [#{elements.join(",\n")}]) { const box = document.createElement('div'); box.append(el); document.body.append(box); }
        JSX
        log, st = Open3.capture2e(File.join(node_modules, '.bin/esbuild'), File.join(dir, 'app.jsx'), '--bundle', '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
        raise "esbuild: #{log}" unless st.success?

        File.write(File.join(dir, 'page.html'), %(<html><head><link rel="stylesheet" href="out.css"></head><body><script src="app.js"></script></body></html>))
        File.write(File.join(dir, 'read.js'), <<~JS)
          const { chromium } = require('playwright');
          (async () => {
            const browser = await chromium.launch({ executablePath: #{HeadlessChromium.path.to_json} });
            const out = {};
            for (const width of #{widths.to_json}) {
              const page = await browser.newPage({ viewport: { width, height: 800 } });
              page.on('pageerror', (e) => { console.log('PAGEERROR ' + e.message); process.exit(3); });
              await page.goto('file://#{File.join(dir, 'page.html')}');
              out[width] = await page.evaluate(() => {
                const r = {};
                for (const el of document.querySelectorAll('[id]')) {
                  if (el.tagName === 'IMG') { r[el.id] = getComputedStyle(el).objectPosition; continue; }
                  const range = document.createRange(); range.selectNodeContents(el);
                  const t = range.getBoundingClientRect(), b = el.getBoundingClientRect();
                  r[el.id] = [Math.round(t.left - b.left), Math.round(b.right - t.right)];
                }
                return r;
              });
              await page.close();
            }
            console.log('AT' + JSON.stringify(out));
            await browser.close();
          })();
        JS
        log, st = Open3.capture2e({ 'NODE_PATH' => node_modules }, 'node', File.join(dir, 'read.js'), chdir: support_dir)
        raise "playwright: #{log}" unless st.success?

        JSON.parse(log[/AT(\{.*\})/, 1] || raise("no result in:\n#{log}"))
      end
    end

    it 'puts the text and the image where the declared value does, at a compact and a regular width' do
      HeadlessChromium.ensure!(self)
      unless tools_ready?
        reason = 'esbuild / tailwindcss / playwright are not installed under spec/support'
        raise "#{reason} — #{HeadlessChromium::REQUIRE_ENV}=1 says this run installed them" if HeadlessChromium.required?

        skip reason
      end

      red = "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16'%3E%3Crect width='16' height='16' fill='red'/%3E%3C/svg%3E"
      nodes = [
        label('declRight', 'textAlign' => 'Right'), label('declCenter', 'textAlign' => 'Center'),
        label('right', 'textAlign' => '@{right}'), label('center', 'textAlign' => '@{center}'),
        label('left', 'textAlign' => '@{left}'), label('capRight', 'textAlign' => '@{capRight}'),
        label('leftOverGravity', 'textAlign' => '@{left}', 'gravity' => 'right'),
        label('unknown', 'textAlign' => '@{unknown}', 'gravity' => 'right'),
        label('sized', 'textAlign' => 'Left', 'responsive' => { 'regular' => { 'textAlign' => 'Right' } }),
        label('sizedOverGravity', 'gravity' => 'right', 'responsive' => { 'regular' => { 'textAlign' => 'Center' } }),
        image('declTop', 'top'), image('top', '@{top}'), image('bottom', '@{bottom}'), image('imgLeft', '@{left}')
      ]
      data = { right: 'right', center: 'center', left: 'left', capRight: 'Right', unknown: 'justify',
               top: 'top', bottom: 'bottom', src: red }
      got = draw(nodes.map { |n| jsx(n) }, data, [400, 1200])
      compact, regular = got['400'], got['1200']

      # the declared labels are the measure: the text at the end, in the middle
      end_, mid = compact['declRight'], compact['declCenter']
      start = end_.reverse
      expect(end_.first).to be > 40, got.inspect
      expect(mid.first - mid.last).to be_between(-1, 1), got.inspect
      expect(compact.slice('right', 'center', 'left', 'capRight')).to eq(
        'right' => end_, 'center' => mid, 'left' => start, 'capRight' => end_
      ), got.inspect
      # textAlign wins over gravity across, as the declared one does; a value
      # it does not know leaves gravity's place, as a declared one would.
      expect(compact.slice('leftOverGravity', 'unknown')).to eq('leftOverGravity' => start, 'unknown' => end_), got.inspect
      # a size class: the base below lg, its own textAlign at regular
      expect(compact.slice('sized', 'sizedOverGravity')).to eq('sized' => start, 'sizedOverGravity' => end_), got.inspect
      expect(regular.slice('sized', 'sizedOverGravity')).to eq('sized' => end_, 'sizedOverGravity' => mid), got.inspect
      expect(compact.slice('declTop', 'top', 'bottom', 'imgLeft')).to eq(
        'declTop' => '50% 0%', 'top' => '50% 0%', 'bottom' => '50% 100%', 'imgLeft' => '0% 50%'
      ), got.inspect
    end
  end
end
