# frozen_string_literal: true

require_relative '../spec_helper'
require 'bigdecimal'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'cli/commands/build_command'
require 'react/converters/label_converter'
require 'react/converters/text_field_converter'
require 'react/converters/text_view_converter'
require 'react/responsive_helper'

# The text's own lengths follow the browser's font size, as spacing does
# from 1.9.15 (ticket rjui-spacing-px-does-not-follow-the-browser-font-size).
# A size on Tailwind's scale (14 -> text-sm) was already rem; a size off it
# (15) wrote text-[15px] and stayed put when the reader raised the browser's
# font size while every text-sm beside it grew. The same held for lineHeight,
# underline's lineOffset, partialAttributes' fontSize, the placeholder's
# size, a bound fontSize, the Configuration font fallback and the autoShrink
# helper. Each now writes N / 16 rem: the same pixels at the default 16px
# root.
RSpec.describe 'rjui text lengths follow the root font size' do
  TM2 = RjuiTools::React::TailwindMapper
  RC = RjuiTools::React::Converters

  def convert(converter, json)
    converter.new({ 'id' => 'x' }.merge(json), { 'use_tailwind' => true }).convert
  end

  it 'a fontSize off the scale is its rem value; one on the scale keeps its class' do
    expect(TM2.map_font_size(15)).to eq('text-[0.9375rem]')
    expect(TM2.map_font_size(13)).to eq('text-[0.8125rem]')
    expect(TM2.map_font_size(14)).to eq('text-sm')
  end

  it 'is exact for every size off the scale: rem x 16 == the declared px' do
    ((1..200).to_a + (1..200).map { |n| n + 0.5 }).reject { |v| TM2::FONT_SIZE_MAP.key?(v) }.each do |v|
      written = TM2.map_font_size(v)[/\Atext-\[([\d.]+)rem\]\z/, 1]
      expect(written).not_to be_nil, v.inspect
      expect(BigDecimal(written) * 16).to eq(BigDecimal(v.to_s)), "#{v} -> #{written}"
    end
  end

  it 'the responsive override spells it the same way' do
    expect(RjuiTools::React::ResponsiveHelper::ATTRIBUTE_MAPPERS['fontSize'].call(15, 'md:')).to eq('md:text-[0.9375rem]')
  end

  it "a Label's lineHeight and underline lineOffset are rem" do
    expect(convert(RC::LabelConverter, 'type' => 'Label', 'text' => 'a', 'lineHeight' => 28)).to include("lineHeight: '1.75rem'")
    expect(convert(RC::LabelConverter, 'type' => 'Label', 'text' => 'a', 'underline' => { 'lineOffset' => 3 }))
      .to include('underline-offset-[0.1875rem]')
  end

  it "partialAttributes' fontSize is rem" do
    out = convert(RC::LabelConverter, 'type' => 'Label', 'text' => 'Big Text',
                                      'partialAttributes' => [{ 'range' => [0, 3], 'fontSize' => 24 }])
    expect(out).to include("fontSize: '1.5rem'")
  end

  it "the placeholder's size is rem on TextField and TextView" do
    expect(convert(RC::TextFieldConverter, 'type' => 'TextField', 'hint' => 'h', 'hintFontSize' => 13))
      .to include('placeholder:[font-size:0.8125rem]')
    expect(convert(RC::TextViewConverter, 'type' => 'TextView', 'hint' => 'h', 'hintFontSize' => 13))
      .to include('placeholder:text-[0.8125rem]')
  end

  it 'a bound fontSize is rem, with or without a font family' do
    expect(convert(RC::LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}'))
      .to include('fontSize: `${Number(data.size) / 16}rem`')
    expect(convert(RC::LabelConverter, 'type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}', 'fontFamily' => 'Helvetica'))
      .to include('fontSize: `${Number(data.size) / 16}rem`')
  end

  it 'the Configuration font fallback writes rem in both languages' do
    %w[Configuration.ts js/Configuration.js].each do |name|
      text = File.read(File.expand_path("../../lib/react/templates/#{name}", __dir__))
      expect(text).to include('css.fontSize = `${spec.size / 16}rem`;'), name
      expect(text).not_to include('${spec.size}px'), name
    end
  end

  it 'the emitted Labels and fields type-check' do
    ts = { 'use_tailwind' => true, 'typescript' => true }
    elements = [
      { 'type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}' },
      { 'type' => 'Label', 'text' => 'a', 'fontSize' => '@{size}', 'fontFamily' => 'Helvetica' },
      { 'type' => 'Label', 'text' => 'a', 'fontSize' => 15, 'lineHeight' => 28, 'underline' => { 'lineOffset' => 3 } },
      { 'type' => 'Label', 'text' => 'Big Text', 'partialAttributes' => [{ 'range' => [0, 3], 'fontSize' => 24 }] }
    ].map { |e| RC::LabelConverter.new({ 'id' => 'l' }.merge(e), ts).convert } +
               [RC::TextFieldConverter.new({ 'type' => 'TextField', 'id' => 'f', 'hint' => 'h', 'hintFontSize' => 13 }, ts).convert,
                RC::TextViewConverter.new({ 'type' => 'TextView', 'id' => 't', 'hint' => 'h', 'hintFontSize' => 13 }, ts).convert]
    # A bound size may be undefined: `${data.size / 16}` does not compile
    # under --strict, so the emit divides Number(...).
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      declare const data: { size?: number; [key: string]: any };
      declare const Configuration: any;
      declare const partialText: any;
      declare const fRef: any;
      declare const tRef: any;
    TS
  end

  # Nothing that writes a text length writes px. The census reads the code,
  # so a new emitter that spells one in px is caught the day it is written.
  it 'no emitter writes a text length in px' do
    lib = File.expand_path('../../lib', __dir__)
    shapes = [/text-\[#\{[^}]*\}px\]/, /font-size:#\{[^}]*\}px/, /fontSize[^\n]*\}px/, /fontSize = [^\n]*'px'/,
              /lineHeight[^\n]*\}px/, /underline-offset-\[#\{[^}]*\}px\]/]
    hits = Dir.glob(File.join(lib, '**/*.{rb,ts,js,tsx,jsx}')).flat_map do |file|
      File.readlines(file).each_with_index.filter_map do |line, i|
        next if line.lstrip.start_with?('#', '//', '*')

        "#{file.delete_prefix("#{lib}/")}:#{i + 1}: #{line.strip}" if shapes.any? { |s| s.match?(line) }
      end
    end
    expect(hits).to eq([])
    # The control: each shape sees the spelling it is there to catch.
    expect(['"text-[#{size}px]"', 'placeholder:[font-size:#{v}px]', "fontSize: '\#{v}px'",
            "el.style.fontSize = lo + 'px';", "lineHeight = \"'\#{v}px'\"", 'underline-offset-[#{o}px]']
             .map { |l| shapes.count { |s| s.match?(l) } }).to all(be >= 1)
  end

  describe 'the autoShrink helper' do
    def helper(typescript: false)
      Dir.mktmpdir('rjui_autoshrink') do |dir|
        command = RjuiTools::CLI::Commands::BuildCommand.allocate
        command.instance_variable_set(:@config, { 'generated_directory' => dir, 'typescript' => typescript })
        allow(RjuiTools::Core::Logger).to receive(:success)
        allow(RjuiTools::Core::Logger).to receive(:info)
        command.send(:emit_auto_shrink_helper)
        File.read(File.join(dir, "autoShrink.#{typescript ? 'ts' : 'js'}"))
      end
    end

    it 'type-checks' do
      # Skips where the spec toolchain is not installed, by the same reason the
      # compile_as_typescript matcher uses (TypeScriptCompiler.unavailable_reason).
      # It used to fail there instead: a worktree without
      # rjui_tools/spec/support/node_modules showed it as the one red example
      # among 281 pending ones. The CI job installs the toolchain, so it runs there.
      if (reason = TypeScriptCompiler.unavailable_reason)
        skip reason
      end
      Dir.mktmpdir('rjui_autoshrink_tsc') do |dir|
        File.write(File.join(dir, 'autoShrink.ts'), helper(typescript: true))
        out, status = Open3.capture2e(TypeScriptCompiler.tsc_path, '--strict', '--noEmit', '--lib', 'es2020,dom',
                                      File.join(dir, 'autoShrink.ts'))
        expect(status).to be_success, out
      end
    end

    # Drawn in Chromium at a 16px and a 20px root: a text that fits is the
    # declared size in rem (20 -> 20px, then 25px), and one that overflows
    # shrinks to a size between the floor and the declared size at that root.
    # A text with no declared size keeps its computed size at either root.
    # The 1.9.14 helper wrote px and drew 20px at both.
    it 'sizes against the root: the declared size at 16px, scaled at 20px' do
      HeadlessChromium.ensure!(self)
      Dir.mktmpdir('rjui_autoshrink_page') do |dir|
        File.write(File.join(dir, 'page.html'), <<~HTML)
          <html><head><style>body{margin:0} div{white-space:nowrap;overflow:hidden;height:200px}</style></head><body><script>
          #{helper.gsub(/^export /, '')}
          const out = {};
          for (const root of [16, 20]) {
            document.documentElement.style.fontSize = root + 'px';
            for (const [name, width, declared] of [['fits', 1000, 20], ['shrinks', 60, 20], ['computed', 1000, undefined]]) {
              const el = document.createElement('div');
              el.style.width = width + 'px';
              if (declared === undefined) el.style.fontSize = '1.25rem';
              el.textContent = 'MMMMMMMM';
              document.body.append(el);
              applyAutoShrink(el, { fontSize: declared, minimumScaleFactor: 0.25 });
              out[root + name] = parseFloat(getComputedStyle(el).fontSize);
              el.remove();
            }
          }
          document.body.textContent = 'AT' + JSON.stringify(out);
          </script></body></html>
        HTML
        dom, = Open3.capture2e(HeadlessChromium.path, *HeadlessChromium::FLAGS, '--dump-dom', "file://#{File.join(dir, 'page.html')}")
        sizes = JSON.parse(dom[/AT(\{.*?\})\s*</m, 1] || raise("no result in:\n#{dom}"))
        expect(sizes['16fits']).to eq(20)
        expect(sizes['20fits']).to eq(25)
        # No declared size: the helper reads the computed one (real px) and
        # writes it back unchanged — 1.25rem stays 20px / 25px.
        expect(sizes['16computed']).to eq(20)
        expect(sizes['20computed']).to eq(25)
        expect(sizes['16shrinks']).to be_between(5, 20).exclusive
        expect(sizes['20shrinks']).to be_between(6.25, 25).exclusive
      end
    end
  end
end
