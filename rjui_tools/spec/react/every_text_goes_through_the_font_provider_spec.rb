# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'open3'
require 'tmpdir'
Dir[File.expand_path('../../lib/react/converters/*_converter.rb', __dir__)].sort.each { |f| require f }

# P1 (ruling 2026-11-13): every text is the app's font. A text component
# with no fontFamily went to the browser's inherited font and never reached
# Configuration.Font.fontProvider: only `fontFamily` (and a bound `font`)
# routed through Configuration.Font.resolve (ticket
# jui-font-provider-not-reached-without-font-attributes-android-web). iOS
# draws such a text with sjuiFont(FontSpec(family: nil, ...)) and
# KotlinJsonUI with Configuration.Font.resolve; the web now calls resolve too,
# with what the text wrote and no family. The classes stay beside the spread:
# with no provider and no Configuration.Font.family, the spread writes only
# the lengths the classes write.
RSpec.describe 'Every text goes through the font provider' do
  let(:config) { { 'use_tailwind' => true } }

  text_converters = {
    'Label' => ['LabelConverter', { 'text' => 'Hi' }],
    'Button' => ['ButtonConverter', { 'text' => 'Go', 'onClick' => '@{go}' }],
    'TextField' => ['TextFieldConverter', { 'text' => '@{t}', 'hint' => 'h' }],
    'TextView' => ['TextViewConverter', { 'text' => '@{t}' }],
    'SelectBox' => ['SelectBoxConverter', { 'items' => %w[a b] }],
    'Switch' => ['SwitchConverter', { 'label' => 'S' }],
    'CheckBox' => ['ToggleConverter', { 'label' => 'C' }],
    'Radio' => ['RadioConverter', { 'items' => %w[a b] }],
    'IconLabel' => ['IconLabelConverter', { 'text' => 'I' }],
    'Segment' => ['SegmentConverter', { 'items' => %w[a b] }]
  }.freeze
  let(:converters) { text_converters }

  def emit(type, attrs)
    klass_name, base = converters.fetch(type) { [type == 'View' ? 'ViewConverter' : 'ImageConverter', {}] }
    klass = RjuiTools::React::Converters.const_get(klass_name)
    klass.new(base.merge(attrs).merge('type' => type, 'id' => 'x'), config).convert
  end

  def spreads(code)
    code.scan(/\.\.\.Configuration\.Font\.resolve\(\{[^}]*\}\)/)
  end

  text_converters.each_key do |type|
    it "a #{type} with no font attribute calls resolve once, with no family" do
      found = spreads(emit(type, {}))
      # A Segment draws its segments medium (`font-medium`): its spec says so.
      want = type == 'Segment' ? "{ weight: 'medium', italic: false }" : '{ italic: false }'
      expect(found).to eq(["...Configuration.Font.resolve(#{want})"])
    end
  end

  # A provider that maps a weight to a face (client / bar return Regular for
  # a spec with none) must get the weight a part draws, or a medium text is
  # drawn in the regular face (KotlinJsonUI passes it the same way).
  it "a Radio's title, drawn medium, calls resolve with medium on its own" do
    found = spreads(emit('Radio', { 'text' => 'Title' }))
    expect(found).to eq(['...Configuration.Font.resolve({ italic: false })', "...Configuration.Font.resolve({ weight: 'medium', italic: false })"])
  end

  it "a Segment's written weight wins over the one it draws" do
    expect(spreads(emit('Segment', { 'font' => 'bold' }))).to eq(["...Configuration.Font.resolve({ weight: 'bold', italic: false })"])
  end

  it 'a component that draws no text does not call resolve' do
    expect(spreads(emit('View', {}))).to be_empty
  end

  it 'passes a written weight name and a written size, and keeps the classes' do
    code = emit('Label', { 'font' => 'semibold', 'fontSize' => 14 })
    expect(spreads(code)).to eq(["...Configuration.Font.resolve({ weight: 'semibold', size: 14, italic: false })"])
    expect(code).to include('font-semibold')
  end

  it 'fontWeight wins over font, as in the fontFamily branch' do
    code = emit('Label', { 'font' => 'bold', 'fontWeight' => 'light' })
    expect(spreads(code)).to eq(["...Configuration.Font.resolve({ weight: 'light', italic: false })"])
  end

  it 'a family alias or a custom name in `font` is not a weight' do
    expect(spreads(emit('Label', { 'font' => 'monospace' }))).to eq(['...Configuration.Font.resolve({ italic: false })'])
    expect(spreads(emit('Label', { 'font' => 'CustomFace' }))).to eq(['...Configuration.Font.resolve({ italic: false })'])
  end

  it 'a declared fontScaling with no fontSize passes 16, the size the browser draws' do
    code = emit('Label', { 'fontScaling' => false })
    expect(spreads(code)).to eq(['...Configuration.Font.resolve({ size: 16, italic: false, scaling: false })'])
  end

  it 'a fontFamily keeps its own single spread' do
    code = emit('Label', { 'fontFamily' => 'Helvetica', 'font' => 'bold' })
    expect(spreads(code)).to eq(["...Configuration.Font.resolve({ family: 'Helvetica', weight: 'bold', italic: false })"])
  end

  it 'a bound font keeps its own single spread' do
    code = emit('Label', { 'font' => '@{w}' })
    expect(spreads(code).size).to eq(1)
    expect(spreads(code).first).to include('weight: data.w')
  end

  # The spreads themselves, as one component's styles: each emitted
  # `Configuration.Font.resolve({...})` type-checks against the template's
  # FontSpec (a field the spec does not declare, or a wrong type, is red).
  # The ten components' whole emit needs their screens' refs and seeds; the
  # spread is what this change writes.
  it 'every emitted spread compiles against the template FontSpec', :typescript_compile do
    ts = config.merge('typescript' => true)
    found = text_converters.flat_map do |type, (klass_name, base)|
      spreads(RjuiTools::React::Converters.const_get(klass_name).new(base.merge('type' => type, 'id' => "x_#{type}"), ts).convert)
    end
    found += spreads(RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'id' => 'w', 'text' => 'a', 'font' => 'semibold', 'fontSize' => 14, 'fontScaling' => false, 'maxFontScale' => 2 }, ts
    ).convert)
    expect(found.size).to eq(11)
    elements = found.map { |spread| "    <span style={{ #{spread} }} />" }
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(<<~TS)
      #{TypeScriptCompiler.template_declarations('Configuration.ts', 'FontSpec')}
      declare const Configuration: { Font: { resolve(spec: FontSpec): { [property: string]: string | number | undefined } } };
    TS
  end

  describe 'Configuration.Font.family (the template)', :node do
    let(:template) { File.expand_path('../../lib/react/templates/js/Configuration.js', __dir__) }

    def run_node(body)
      skip('node is not installed') unless system('command -v node >/dev/null 2>&1')
      Dir.mktmpdir do |dir|
        FileUtils.cp(template, File.join(dir, 'Configuration.mjs'))
        File.write(File.join(dir, 'probe.mjs'), "import { Configuration } from './Configuration.mjs';\n#{body}\n")
        out, err, status = Open3.capture3('node', File.join(dir, 'probe.mjs'))
        raise "node failed: #{err}" unless status.success?
        JSON.parse(out)
      end
    end

    it 'draws a text with no family in the default family, and a written family in its own' do
      got = run_node(<<~JS)
        Configuration.Font.family = 'BeVietnamPro';
        const none = Configuration.Font.resolve({ italic: false });
        const own = Configuration.Font.resolve({ family: 'Serif', italic: false });
        Configuration.Font.family = undefined;
        const unset = Configuration.Font.resolve({ italic: false });
        console.log(JSON.stringify({ none, own, unset }));
      JS
      expect(got['none']).to eq('fontFamily' => 'BeVietnamPro')
      expect(got['own']).to eq('fontFamily' => 'Serif')
      expect(got['unset']).to eq({})
    end

    it "writes a weight name as its CSS weight, by shared/core/font_weight_mapping.json" do
      mapping = JSON.parse(File.read(File.expand_path('../../../shared/core/font_weight_mapping.json', __dir__)))['weights']
      names = mapping.keys
      got = run_node(<<~JS)
        const names = #{names.to_json};
        const out = {};
        for (const n of names) out[n] = Configuration.Font.resolve({ weight: n, italic: false }).fontWeight;
        out['600'] = Configuration.Font.resolve({ weight: '600', italic: false }).fontWeight;
        console.log(JSON.stringify(out));
      JS
      expect(got.reject { |k, _| k == '600' }).to eq(mapping.transform_values { |v| v['css'] })
      expect(got['600']).to eq('600')
    end

    it 'hands the spec to a provider as written (no family filled in), as iOS and Android do' do
      got = run_node(<<~JS)
        Configuration.Font.family = 'BeVietnamPro';
        Configuration.Font.fontProvider = (spec) => ({ seen: spec.family ?? null });
        console.log(JSON.stringify(Configuration.Font.resolve({ italic: false })));
      JS
      expect(got).to eq('seen' => nil)
    end
  end
end
