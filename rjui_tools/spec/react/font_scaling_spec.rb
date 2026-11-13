# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'open3'
require 'tmpdir'
require_relative '../support/headless_chromium'
require_relative '../support/typescript_compiler'
require 'cli/commands/build_command'
require 'react/converters/label_converter'
require 'react/converters/segment_converter'

# fontScaling / maxFontScale on the web (ticket sjui-label-font-size-ignores-dynamic-type, ruling 2026-11-13):
# a component's text follows the browser's text size by its declaration, else by the app default
# (Configuration.Font.configureScaling). Not following: px. Following: rem. Capped: min(rem, N x max px).
#
# The sizes are drawn in headless Chromium by the lengths TailwindMapper.font_size_css writes, the browser's text
# size being the root font size (16px x the vector's scale), and compared with shared/core/font_scale_vectors.json's
# `drawn`. A page whose app sets nothing draws every undeclared size as N / 16 rem, uncapped — what every size was
# before 2.5.35 — at the standard size and at 200%.
RSpec.describe 'fontScaling / maxFontScale (rjui)' do
  TMF = RjuiTools::React::TailwindMapper
  # Methods, not constants: a top-level constant of the same name in another spec file is one constant
  # (spec_constants_are_scoped_spec).
  def font_vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/font_scale_vectors.json', __dir__)))
  def configuration_js = File.expand_path('../../lib/react/templates/js/Configuration.js', __dir__)

  # Each probe: [key, root px, css custom properties on the root, the element's font-size].
  def drawn_in_chromium(probes, script: '')
    HeadlessChromium.ensure!(self)
    Dir.mktmpdir('rjui_font_scaling') do |dir|
      File.write(File.join(dir, 'page.html'), <<~HTML)
        <html><body><script>
        #{script}
        const probes = #{JSON.generate(probes)};
        const out = {};
        for (const [key, root, vars, size] of probes) {
          const html = document.documentElement;
          html.removeAttribute('style');
          html.style.fontSize = root + 'px';
          for (const [k, v] of Object.entries(vars)) html.style.setProperty(k, v);
          const el = document.createElement('span');
          el.style.fontSize = size;
          el.textContent = 'x';
          document.body.append(el);
          out[key] = parseFloat(getComputedStyle(el).fontSize);
          el.remove();
        }
        document.body.textContent = 'AT' + JSON.stringify(out);
        </script></body></html>
      HTML
      dom, = Open3.capture2e(HeadlessChromium.path, *HeadlessChromium::FLAGS, '--dump-dom',
                             "file://#{File.join(dir, 'page.html')}")
      JSON.parse(dom[/AT(\{.*?\})\s*</m, 1] || raise("no result in:\n#{dom}"))
    end
  end

  def app_vars(app_default)
    app_default == false ? { TMF::FONT_UNIT_VAR => '1px' } : {}
  end

  it 'draws every shared vector at the size it names' do
    probes = font_vectors['drawn'].map do |c|
      css = TMF.font_size_css(c['size'], scaling: c.key?('declared') ? c['declared'] : nil, max: c['max'])
      [c['name'], 16 * c['scale'], app_vars(c['appDefault']), css]
    end
    drawn = drawn_in_chromium(probes)
    font_vectors['drawn'].each do |c|
      expect(drawn[c['name']]).to be_within(0.05).of(c['drawn']), "#{c['name']}: #{probes.assoc(c['name']).last}"
    end
  end

  it 'draws an undeclared size as before when the app sets nothing, at the standard size and at 200%' do
    sizes = [10, 12, 13, 14, 15, 16, 17, 20, 24, 28, 36]
    probes = sizes.product([16, 32]).flat_map do |n, root|
      [["new #{n}@#{root}", root, {}, TMF.font_size_css(n)], ["old #{n}@#{root}", root, {}, TMF.rem(n)]]
    end
    drawn = drawn_in_chromium(probes)
    sizes.product([16, 32]).each do |n, root|
      expect(drawn["new #{n}@#{root}"]).to eq(drawn["old #{n}@#{root}"]), "#{n} at #{root}px"
      expect(drawn["new #{n}@#{root}"]).to be_within(0.01).of(n * root / 16.0)
    end
  end

  # The app default is set through the generated Configuration, which writes the two custom properties.
  it 'follows the app default an app sets with Configuration.Font.configureScaling' do
    config = File.read(configuration_js).gsub(/^export /, '')
    probes = [['unset', 32, {}, TMF.font_size_css(15)]]
    drawn = drawn_in_chromium(probes, script: config)
    expect(drawn['unset']).to eq(30)

    drawn = drawn_in_chromium(
      [['off', 32, { TMF::FONT_UNIT_VAR => '1px' }, TMF.font_size_css(15)],
       ['capped', 48, { TMF::FONT_MAX_VAR => '1.5px' }, TMF.font_size_css(16)],
       ['declared wins over off', 32, { TMF::FONT_UNIT_VAR => '1px' }, TMF.font_size_css(15, scaling: true)]]
    )
    expect(drawn['off']).to eq(15)
    expect(drawn['capped']).to eq(24)
    expect(drawn['declared wins over off']).to eq(30)
  end

  it 'configureScaling writes the custom properties the sizes read' do
    config = File.read(configuration_js).gsub(/^export /, '')
    HeadlessChromium.ensure!(self)
    Dir.mktmpdir('rjui_font_configure') do |dir|
      File.write(File.join(dir, 'page.html'), <<~HTML)
        <html><body><script>
        #{config}
        const s = () => [document.documentElement.style.getPropertyValue('#{TMF::FONT_UNIT_VAR}'),
                         document.documentElement.style.getPropertyValue('#{TMF::FONT_MAX_VAR}')].join('|');
        const out = [];
        Configuration.Font.configureScaling({ scaling: false }); out.push(s());
        Configuration.Font.configureScaling({ scaling: true, maxScale: 1.5 }); out.push(s());
        Configuration.Font.configureScaling({ maxScale: undefined }); out.push(s());
        document.body.textContent = 'AT' + JSON.stringify(out);
        </script></body></html>
      HTML
      dom, = Open3.capture2e(HeadlessChromium.path, *HeadlessChromium::FLAGS, '--dump-dom',
                             "file://#{File.join(dir, 'page.html')}")
      expect(JSON.parse(dom[/AT(\[.*?\])\s*</m, 1])).to eq(['1px|', '0.0625rem|1.5px', '0.0625rem|'])
    end
  end

  describe 'what a component writes' do
    def label(extra)
      RjuiTools::React::Converters::LabelConverter.new(
        { 'type' => 'Label', 'id' => 'l', 'text' => 'a', 'fontSize' => 15 }.merge(extra), { 'use_tailwind' => true }
      ).convert
    end

    it 'writes px, rem or the capped length by its declaration, and the app default without one' do
      expect(label('fontScaling' => false)).to include('text-[length:15px]')
      expect(label('fontScaling' => true)).to include("text-[length:min(0.9375rem,calc(15*var(--jui-font-max,10000px)))]")
      expect(label('fontScaling' => true, 'maxFontScale' => 1.5)).to include('text-[length:min(0.9375rem,22.5px)]')
      expect(label({})).to include("text-[length:#{TMF.font_size_css(15)}]")
      expect(label('maxFontScale' => 2)).to include('text-[length:min(calc(15*var(--jui-font-unit,0.0625rem)),30px)]')
    end

    # No fontSize: the size the browser draws the text at (16) is the fontSize a declaration applies to; with no
    # declaration nothing is written and the text inherits, as before (ruling 2026-11-13).
    it 'treats a declared component with no fontSize as 16, and writes nothing for an undeclared one' do
      plain = RjuiTools::React::Converters::LabelConverter.new({ 'type' => 'Label', 'id' => 'l', 'text' => 'a' },
                                                              { 'use_tailwind' => true })
      expect(plain.convert).not_to include('font-size')
      expect(plain.convert).not_to match(/\btext-(base|\[length)/)
      declared = ->(extra) {
        RjuiTools::React::Converters::LabelConverter.new({ 'type' => 'Label', 'id' => 'l', 'text' => 'a' }.merge(extra),
                                                         { 'use_tailwind' => true }).convert
      }
      expect(declared.call('fontScaling' => false)).to include('text-base [font-size:16px]')
      expect(declared.call('maxFontScale' => 1.2)).to include('[font-size:min(calc(16*var(--jui-font-unit,0.0625rem)),19.2px)]')
      segment = RjuiTools::React::Converters::SegmentConverter.new(
        { 'type' => 'Segment', 'id' => 's', 'items' => %w[a b], 'fontScaling' => false }, { 'use_tailwind' => true }
      ).convert
      expect(segment).to include('text-sm [font-size:14px]')
    end

    it "gives partialAttributes' sizes their component's declaration" do
      out = label('fontScaling' => false, 'partialAttributes' => [{ 'range' => [0, 1], 'fontSize' => 24 }])
      expect(out).to include("fontSize: '24px'")
    end

    it 'type-checks what it writes' do
      ts = { 'use_tailwind' => true, 'typescript' => true }
      elements = [
        { 'fontScaling' => false }, { 'fontScaling' => true, 'maxFontScale' => 1.5 }, { 'maxFontScale' => 2 },
        { 'fontSize' => '@{size}', 'fontScaling' => false }, { 'fontSize' => '@{size}', 'maxFontScale' => 1.5 },
        { 'fontScaling' => false, 'partialAttributes' => [{ 'range' => [0, 1], 'fontSize' => 24 }] }
      ].map do |extra|
        RjuiTools::React::Converters::LabelConverter.new(
          { 'type' => 'Label', 'id' => 'l', 'text' => 'a', 'fontSize' => 15 }.merge(extra), ts
        ).convert
      end
      expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
        declare const data: { size?: number; [key: string]: any };
        declare const Configuration: any;
        declare const partialText: any;
      TS
    end

    it "draws a size class's fontSize by the component's declaration" do
      out = label('fontScaling' => false, 'responsive' => { 'regular' => { 'fontSize' => 20 } })
      expect(out).to include('lg:text-xl lg:[font-size:20px]')
    end
  end

  # autoShrink writes the size inline; it shrinks a fraction of the declared length, so a Label that does not
  # follow the browser's text size still does not when it fits (20px at a 32px root), and one that does, does.
  it 'autoShrink keeps the declaration' do
    HeadlessChromium.ensure!(self)
    Dir.mktmpdir('rjui_autoshrink_scaling') do |dir|
      command = RjuiTools::CLI::Commands::BuildCommand.allocate
      command.instance_variable_set(:@config, { 'generated_directory' => dir, 'typescript' => false })
      allow(RjuiTools::Core::Logger).to receive(:success)
      allow(RjuiTools::Core::Logger).to receive(:info)
      command.send(:emit_auto_shrink_helper)
      helper = File.read(File.join(dir, 'autoShrink.js')).gsub(/^export /, '')
      File.write(File.join(dir, 'page.html'), <<~HTML)
        <html><head><style>body{margin:0} div{white-space:nowrap;overflow:hidden;height:200px}</style></head><body><script>
        #{helper}
        document.documentElement.style.fontSize = '32px';
        const out = {};
        for (const [name, width, css] of [['fixed fits', 1000, '#{TMF.font_size_css(20, scaling: false)}'],
                                          ['follows fits', 1000, '#{TMF.font_size_css(20)}'],
                                          ['fixed shrinks', 60, '#{TMF.font_size_css(20, scaling: false)}']]) {
          const el = document.createElement('div');
          el.style.width = width + 'px';
          el.textContent = 'MMMMMMMM';
          document.body.append(el);
          applyAutoShrink(el, { fontSize: 20, fontCss: css, minimumScaleFactor: 0.25 });
          out[name] = parseFloat(getComputedStyle(el).fontSize);
          el.remove();
        }
        document.body.textContent = 'AT' + JSON.stringify(out);
        </script></body></html>
      HTML
      dom, = Open3.capture2e(HeadlessChromium.path, *HeadlessChromium::FLAGS, '--dump-dom',
                             "file://#{File.join(dir, 'page.html')}")
      sizes = JSON.parse(dom[/AT(\{.*?\})\s*</m, 1] || raise("no result in:\n#{dom}"))
      expect(sizes['fixed fits']).to eq(20)
      expect(sizes['follows fits']).to eq(40)
      expect(sizes['fixed shrinks']).to be_between(5, 20).exclusive
    end
  end
end
