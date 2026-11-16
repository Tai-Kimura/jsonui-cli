# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../../lib/cli/commands/build_command'
require 'react/react_generator'
require 'react/converters/include_converter'
require 'react/converters/label_converter'
require 'json'
require 'open3'
require 'tmpdir'

# Design U8: the ids inside an include that has an id carry the include's
# prefix on web as they do on iOS and Android (`hero` + `type_badge` ->
# `heroTypeBadge`). `jui build` decides whether (INCLUDE_ID_PREFIX_GATE_FROM)
# and hands the answer over in JSONUI_INCLUDE_ID_PREFIX; rjui reads no literal.
# Off — the default, and every build before the release — the output is the
# output it always was.
RSpec.describe 'include id prefix on web (U8)' do
  VECTORS = JSON.parse(File.read(File.expand_path('../../../shared/core/camel_case_vectors.json', __dir__)))

  def helper_source(typescript: true)
    Dir.mktmpdir('rjui_include_id') do |dir|
      instance = RjuiTools::CLI::Commands::BuildCommand.allocate
      instance.instance_variable_set(:@config, {
                                       'typescript' => typescript,
                                       'generated_directory' => File.join(dir, 'generated')
                                     })
      instance.send(:emit_include_id_helper)
      File.read(File.join(dir, 'generated', typescript ? 'includeId.ts' : 'includeId.js'))
    end
  end

  describe 'the helper' do
    it 'type-checks under --strict' do
      expect(helper_source).to compile_as_typescript
    end

    # The answers themselves, run: esbuild turns the emitted TypeScript into
    # JavaScript and node calls it with every row of the shared vectors — the
    # table sjui/kjui/Python are held to, so the four agree by construction.
    it 'answers every row of shared/core/camel_case_vectors.json as codegen does' do
      BundlerDefine.skip_unless_available!
      js = BundlerDefine.fold(helper_source, node_env: 'production')
      prefix = VECTORS['prefix']
      probe = <<~JS
        #{js.gsub(/^export /, '')}
        const cases = #{JSON.generate(VECTORS['cases'].map { |c| c['input'] })};
        console.log(JSON.stringify(cases.map((input) => ({
          input,
          camel: jsonuiCamel(input),
          combined: jsonuiIncludeId(#{JSON.generate(prefix)}, input),
          unprefixed: jsonuiIncludeId(undefined, input),
        }))));
      JS
      out, err, status = Open3.capture3('node', '-e', probe)
      expect(status.success?).to be(true), err
      expect(JSON.parse(out)).to eq(VECTORS['cases'].map { |c| c.slice('input', 'camel', 'combined', 'unprefixed') })
    end

    it 'composes a nested prefix the way the expanders do' do
      BundlerDefine.skip_unless_available!
      js = BundlerDefine.fold(helper_source, node_env: 'production')
      probe = "#{js.gsub(/^export /, '')}\nconsole.log(JSON.stringify([" \
              "jsonuiIncludePrefix(undefined, 'inner_box'), jsonuiIncludePrefix('hero', 'hero_card'), " \
              "jsonuiIncludeId(jsonuiIncludePrefix(undefined, 'inner_box'), 'deep_label')]))"
      out, err, status = Open3.capture3('node', '-e', probe)
      expect(status.success?).to be(true), err
      expect(JSON.parse(out)).to eq(%w[innerBox heroHeroCard innerBoxDeepLabel])
    end
  end

  let(:off) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:on) { off.merge('_include_id_prefix' => true) }

  describe 'an include site' do
    def convert(json, config)
      RjuiTools::React::Converters::IncludeConverter.new(json, config).convert
    end

    it 'hands its id down as the prefix — combined with the one above it' do
      expect(convert({ 'include' => 'part/hero', 'id' => 'hero' }, on))
        .to include('<Hero idPrefix={jsonuiIncludePrefix(idPrefix, "hero")} />')
    end

    it 'without an id, hands the prefix above it straight through' do
      expect(convert({ 'include' => 'part/hero' }, on)).to include('<Hero idPrefix={idPrefix} />')
    end

    it 'control: off, the include id overrides the partial root as it always did' do
      expect(convert({ 'include' => 'part/hero', 'id' => 'hero' }, off)).to include('<Hero id="hero" />')
      expect(convert({ 'include' => 'part/hero' }, off)).to include('<Hero />')
    end
  end

  describe 'an element id' do
    def convert(json, config)
      RjuiTools::React::Converters::LabelConverter.new(json, config).convert
    end

    it 'goes through the helper — as written on a screen, prefixed under an include' do
      expect(convert({ 'type' => 'Label', 'id' => 'type_badge', 'text' => 'x' }, on))
        .to include('id={jsonuiIncludeId(idPrefix, "type_badge")}')
    end

    it 'control: off, it is the literal it always was' do
      out = convert({ 'type' => 'Label', 'id' => 'type_badge', 'text' => 'x' }, off)
      expect(out).to include('id="type_badge"')
      expect(out).not_to include('jsonuiIncludeId')
    end
  end

  describe 'the component' do
    let(:partial) do
      { 'type' => 'View', 'id' => 'hero_root',
        'child' => [{ 'type' => 'Label', 'id' => 'type_badge', 'text' => 'x' },
                    { 'include' => 'part/inner', 'id' => 'inner_box' }] }
    end

    it 'takes idPrefix, imports what it calls, and prefixes its root too' do
      out = RjuiTools::React::ReactGenerator.new(on).generate('Hero', partial)
      expect(out).to include('idPrefix?: string;')
      expect(out).to match(/export const Hero = \(\{ data, id, idPrefix \}: HeroProps\)/)
      expect(out).to include("import { jsonuiIncludeId, jsonuiIncludePrefix } from '@/generated/includeId';")
      expect(out).to include('id={id ?? (jsonuiIncludeId(idPrefix, "hero_root"))}')
      expect(out).to include('<Inner idPrefix={jsonuiIncludePrefix(idPrefix, "inner_box")} />')
    end

    it 'the emitted component type-checks with the helper declared' do
      out = RjuiTools::React::ReactGenerator.new(on).generate('Hero', partial)
      body = out.lines.reject { |l| l.start_with?('import ') }.join
      expect(body).to compile_as_typescript.with_ambient(<<~TS)
        declare function jsonuiIncludeId(prefix: string | undefined, name: string): string;
        declare function jsonuiIncludePrefix(outer: string | undefined, includeId: string): string;
        declare const Inner: (props: { idPrefix?: string }) => JSX.Element;
        interface HeroData {}
        declare function useStringManager(): Record<string, string>;
      TS
    end

    it 'control: off, none of it — the bytes an unchanged build always emitted' do
      out = RjuiTools::React::ReactGenerator.new(off).generate('Hero', partial)
      %w[idPrefix jsonuiIncludeId jsonuiIncludePrefix includeId].each { |w| expect(out).not_to include(w) }
    end
  end

  describe "following jui's answer" do
    def decide(value)
      instance = RjuiTools::CLI::Commands::BuildCommand.allocate
      Dir.mktmpdir('rjui_decide') do |dir|
        instance.instance_variable_set(:@config, { 'typescript' => true,
                                                   'generated_directory' => File.join(dir, 'g') })
        old = ENV['JSONUI_INCLUDE_ID_PREFIX']
        value.nil? ? ENV.delete('JSONUI_INCLUDE_ID_PREFIX') : ENV['JSONUI_INCLUDE_ID_PREFIX'] = value
        begin
          out = capture_stdout { instance.send(:apply_include_id_prefix_decision) }
        ensure
          old.nil? ? ENV.delete('JSONUI_INCLUDE_ID_PREFIX') : ENV['JSONUI_INCLUDE_ID_PREFIX'] = old
        end
        [instance.instance_variable_get(:@config)['_include_id_prefix'], out,
         File.exist?(File.join(dir, 'g', 'includeId.ts'))]
      end
    end

    def capture_stdout
      old = $stdout
      $stdout = StringIO.new
      yield
      $stdout.string
    ensure
      $stdout = old
    end

    it 'on: prefixes, and emits the helper' do
      flag, out, helper = decide('on')
      expect([flag, helper]).to eq([true, true])
      expect(out).not_to include('NOTICE')
    end

    it 'announce: keeps the old spelling and names the release' do
      flag, out, helper = decide('announce:1.8.120')
      expect([flag, helper]).to eq([nil, false])
      expect(out).to include('NOTICE [include-ids]: from jsonui-cli 1.8.120, the ids inside an include')
    end

    it 'run on its own (no answer): keeps the old spelling and says jui decides' do
      flag, out, = decide(nil)
      expect(flag).to be_nil
      expect(out).to include('is decided by `jui build`; run on its own, this build keeps the unprefixed spelling')
    end

    it 'off (withdrawn / undeclared): keeps the old spelling, silently' do
      flag, out, helper = decide('off')
      expect([flag, out, helper]).to eq([nil, '', false])
    end

    it "no notice line matches the agents' warning count" do
      [decide('announce:1.8.120')[1], decide(nil)[1]].each do |out|
        expect(out).not_to match(/warning \[|warning:|\[warn|⚠/i)
      end
    end
  end
end
