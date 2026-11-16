# frozen_string_literal: true

require 'json'
require 'open3'
require 'tmpdir'
require 'fileutils'
require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/react_generator'
require 'core/resources/color_manager'

# JsonUI's 8-digit hex is alpha-FIRST (#AARRGGBB): iOS (UIColor / Color(hex:)),
# Android (Color.parseColor) and the web's own theme.css (rgba) read it so, and
# every distribution lane writes it so in colors.json (#88000000, #CCFFFFFF).
# CSS reads an 8-digit hex alpha-LAST. Every other web path handed it to CSS as
# written: an arbitrary class, a style literal, a bound colour, a colors.json key
# resolved at run time — #80FF0000 (red at 50%) drew as a transparent
# (128, 255, 0) (measured in Chromium). Ticket 2026-11-07-eight-digit-hex-alpha-order.
RSpec.describe 'an eight-digit hex is alpha-first on the web' do
  HEX8 = '#80FF0000'          # red at 50%, alpha first
  CSS8 = '#FF000080'          # the same, as CSS reads it
  DEFS8 = JSON.parse(File.read(File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)))
  let(:generator) { RjuiTools::React::ReactGenerator.new({ 'use_tailwind' => true, 'typescript' => true }) }

  def emit(node)
    generator.send(:convert_component, { 'id' => 'p' }.merge(node), 2).to_s
  end

  it 'reorders an 8-digit hex and leaves every other colour as it was' do
    m = RjuiTools::React::TailwindMapper
    expect(m.css_hex(HEX8)).to eq(CSS8)
    expect(m.css_hex('#ff0000')).to eq('#ff0000')
    expect(m.css_hex('#F00')).to eq('#F00')
    expect(m.css_hex('rgba(1,2,3,0.5)')).to eq('rgba(1,2,3,0.5)')
    expect(m.css_hex('primary')).to eq('primary')
    expect(m.css_hex('@{c}')).to eq('@{c}')
    expect(m.css_hex(nil)).to be_nil
  end

  # Every colour the declaration has, on its component, written as an 8-digit
  # hex: what reaches the output is the CSS order, never the JsonUI one.
  COLOURISH = lambda do |name, d|
    d.is_a?(Hash) && (name =~ /(Color|color|background|Background|tint|Tint)$/ || d['description'].to_s =~ /\bcolou?r\b/i) &&
      Array(d['type']).flatten.map { |t| t.is_a?(Hash) ? t['type'] : t }.include?('string')
  end
  EXTRAS = { 'borderWidth' => 2, 'hint' => 'h', 'onClick' => '@{tap}', 'enabled' => '@{en}', 'items' => ['a'] }.freeze
  SWEEP = DEFS8.flat_map do |type, attrs|
    next [] unless attrs.is_a?(Hash) && !%w[_comment common].include?(type)

    attrs.select { |n, d| COLOURISH.call(n, d) }.map { |n, _| [type, n] }
  end + %w[View Label Button].product(DEFS8['common'].select { |n, d| COLOURISH.call(n, d) }.keys)

  it 'writes no colour in the JsonUI order, and the colours it draws in the CSS order' do
    drawn = 0
    raw = SWEEP.filter_map do |type, attr|
      node = EXTRAS.merge('type' => type, attr => HEX8)
      node['text'] = 'x' if %w[Label Button TextField TextView].include?(type)
      code = emit(node)
      drawn += 1 if code.include?(CSS8)
      "#{type}.#{attr}" if code.include?(HEX8.delete('#'))
    end
    expect(raw).to eq([])
    expect(drawn).to be >= 50   # 55 measured: the sweep reaches the paths, not a handful
  end

  it "folds a shadow's opacity into an 8-digit colour's own alpha" do
    expect(RjuiTools::React::TailwindMapper.shadow_color_with_alpha(HEX8, 0.5)).to eq('#FF000040')
    expect(emit({ 'type' => 'View', 'shadow' => { 'color' => HEX8, 'radius' => 3 } })).to include("[box-shadow:0px_0px_3px_#{CSS8}]")
  end

  describe 'the generated ColorManager' do
    let(:dir) { Dir.mktmpdir('cm8') }
    after { FileUtils.rm_rf(dir) }

    def generated(typescript)
      res = File.join(dir, 'Resources')
      FileUtils.mkdir_p(res)
      File.write(File.join(res, 'colors.json'), JSON.generate('light' => { 'veil' => HEX8, 'red' => '#FF0000' }))
      cfg = { 'generated_directory' => 'gen', 'typescript' => typescript }
      RjuiTools::Core::Resources::ColorManager.new(cfg, dir, res).send(:generate_color_manager)
      File.read(Dir.glob(File.join(dir, 'gen', "ColorManager.#{typescript ? 'ts' : 'js'}")).first)
    end

    it 'hands CSS the CSS order for a key, a hex and a lookup, and every other value as it was' do
      js = generated(false)
      node = ENV.fetch('NODE', 'node')
      skip 'node is not installed' unless system("#{node} --version", out: File::NULL, err: File::NULL)
      File.write(File.join(dir, 'cm.mjs'), js)
      File.write(File.join(dir, 't.mjs'), <<~JS)
        globalThis.window = { matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }) };
        const { ColorManager: m } = await import('./cm.mjs');
        console.log(JSON.stringify([m.resolveColor('veil'), m.resolveColor('#{HEX8}'), m.color('veil'), m.resolveColor('red'), m.resolveColor('rgba(1,2,3,0.5)'), m.resolveColor('crimson')]));
      JS
      out, status = Open3.capture2e(node, File.join(dir, 't.mjs'))
      expect(status).to be_success, out
      expect(JSON.parse(out.lines.last)).to eq([CSS8, CSS8, CSS8, '#FF0000', 'rgba(1,2,3,0.5)', 'crimson'])
    end

    it 'compiles as TypeScript', :typescript_compile do
      expect(generated(true)).to compile_as_typescript
    end
  end

  it 'writes what it draws so that it compiles', :typescript_compile do
    drawn = [{ 'type' => 'View', 'background' => HEX8 }, { 'type' => 'Label', 'text' => 'x', 'fontColor' => HEX8 },
             { 'type' => 'Switch', 'tintColor' => HEX8 }, { 'type' => 'Indicator', 'color' => HEX8 },
             { 'type' => 'Label', 'text' => 'x', 'textShadow' => { 'color' => HEX8, 'blur' => 2, 'offset' => [1, 1] } }]
            .each_with_index.map { |node, i| emit(node.merge('id' => "p#{i}")) }
    source = "const data = {} as { [key: string]: any };\nconst refs: any = {};\nexport const view = (\n  <div>\n#{drawn.join("\n")}\n  </div>\n);\n"
    expect(source.gsub(/ ref=\{\w+\}/, '').gsub(/ on\w+=\{[^}]*\}\}?/, ''))
      .to compile_as_typescript.with_ambient('declare namespace React { type CSSProperties = Record<string, unknown>; }; ' \
                                             'declare const ColorManager: { resolveColor(value: unknown): string | undefined };')
  end
end
