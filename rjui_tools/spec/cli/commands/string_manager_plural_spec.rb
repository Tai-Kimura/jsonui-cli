# frozen_string_literal: true

require_relative '../../spec_helper'
require 'fileutils'
require 'tmpdir'
require 'open3'
require 'cli/commands/build_command'

RSpec.describe 'StringManager plural emit' do
  let(:instance) { RjuiTools::CLI::Commands::BuildCommand.allocate }
  let(:tmpdir) { Dir.mktmpdir }

  after { FileUtils.remove_entry(tmpdir) }

  def base_config(ts:)
    {
      'generated_directory' => File.join(tmpdir, 'generated'),
      'layouts_directory' => File.join(tmpdir, 'Layouts'),
      'strings_directory' => File.join(tmpdir, 'Strings'),
      'languages' => %w[en ja],
      'default_language' => 'en',
      'typescript' => ts
    }
  end

  def write_resources_strings(config, data)
    resources_dir = File.join(config['layouts_directory'], 'Resources')
    FileUtils.mkdir_p(resources_dir)
    File.write(File.join(resources_dir, 'strings.json'), JSON.pretty_generate(data))
  end

  def plural_strings
    {
      'home' => {
        'items_count' => {
          'en' => { 'plural' => { 'one' => '{count} item', 'other' => '{count} items' } },
          'ja' => { 'plural' => { 'other' => '{count}件' } }
        },
        'title' => { 'en' => 'Home', 'ja' => 'ホーム' }
      }
    }
  end

  def run_update(config)
    instance.instance_variable_set(:@config, config)
    instance.send(:update_string_manager)
  end

  describe 'byte stability without plurals' do
    it 'augment_with_plurals is a no-op for empty plural data' do
      strings_json = JSON.pretty_generate({ 'en' => { 'k' => 'v' } })
      [true, false].each do |is_ts|
        base = if is_ts
                 instance.send(:string_manager_typescript_content, strings_json, 'en', '// H', '// F')
               else
                 instance.send(:string_manager_javascript_content, strings_json, 'en', '// H', '// F')
               end
        augmented = instance.send(:augment_with_plurals, base,
                                  { 'en' => {}, 'ja' => {} }, 'en', is_ts: is_ts)
        expect(augmented).to eq(base)
      end
    end

    it 'generates a StringManager without any plural runtime for plural-free strings.json' do
      config = base_config(ts: true)
      write_resources_strings(config, { 'home' => { 'title' => 'Home' } })
      run_update(config)

      out = File.read(File.join(config['generated_directory'], 'StringManager.ts'))
      expect(out).not_to include('PLURAL_KEY_CANONICAL')
      expect(out).not_to include('plurals')
    end
  end

  describe 'plural runtime emission' do
    it 'emits plural tables, canonical map, guards and Intl.PluralRules resolution (TS)' do
      config = base_config(ts: true)
      write_resources_strings(config, plural_strings)
      run_update(config)

      out = File.read(File.join(config['generated_directory'], 'StringManager.ts'))
      expect(out).to include('type PluralsRoot = Record<string, Record<string, StringMap>>;')
      expect(out).to include('const plurals: PluralsRoot =')
      expect(out).to include('"home_items_count"')
      expect(out).to include('"homeItemsCount": "home_items_count"')
      expect(out).to include('plural(key: string, count: number): string {')
      expect(out).to include('getDefaultPlural(key: string, count: number): string {')
      expect(out).to include('new Intl.PluralRules(lang).select(count)')
      # Count-less access fails loudly: proxy guard + lookup guards
      expect(out).to include('Object.defineProperty(camelCaseMap, pluralKey')
      expect(out.scan('is a plural key - use StringManager.plural').length).to be >= 3
      # ja fallback tables are filled at generation time
      expect(out).to include('"ja"')
    end

    it 'emits the same runtime untyped for JS mode' do
      config = base_config(ts: false)
      write_resources_strings(config, plural_strings)
      run_update(config)

      out = File.read(File.join(config['generated_directory'], 'StringManager.js'))
      expect(out).to include('const plurals =')
      expect(out).not_to include('PluralsRoot')
      expect(out).to include('plural(key, count) {')
      expect(out).to include('_resolvePlural(lang, key, count) {')
    end

    it 'resolves CLDR categories for real when executed under node', if: system('which node > /dev/null 2>&1') do
      config = base_config(ts: false)
      write_resources_strings(config, plural_strings)
      run_update(config)

      out = File.read(File.join(config['generated_directory'], 'StringManager.js'))
      harness = out.sub("import { useSyncExternalStore } from 'react';",
                        'const useSyncExternalStore = () => ({});')
      harness += <<~JS

        const assert = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } };
        assert(StringManager.plural('home_items_count', 1) === '1 item', 'en one');
        assert(StringManager.plural('home_items_count', 2) === '2 items', 'en other');
        assert(StringManager.plural('homeItemsCount', 0) === '0 items', 'en count=0 selects other');
        StringManager.setLanguage('ja');
        assert(StringManager.plural('home_items_count', 1) === '1件', 'ja other for 1');
        let threw = false;
        try { StringManager.getString('home_items_count'); } catch (e) { threw = true; }
        assert(threw, 'getString throws for plural key');
        threw = false;
        try { const v = StringManager.currentLanguage.homeItemsCount; } catch (e) { threw = true; }
        assert(threw, 'proxy access throws for plural key');
        assert(StringManager.getString('home_title') === 'ホーム', 'plain keys unaffected');
        console.log('node plural OK');
      JS

      mjs_path = File.join(tmpdir, 'StringManagerHarness.mjs')
      File.write(mjs_path, harness)
      stdout, stderr, status = Open3.capture3('node', mjs_path)
      expect(status.success?).to be(true), "node failed: #{stdout}#{stderr}"
      expect(stdout).to include('node plural OK')
    end
  end

  describe 'validation' do
    it 'raises when a layout string attribute references a plural key' do
      config = base_config(ts: true)
      write_resources_strings(config, plural_strings)
      File.write(File.join(config['layouts_directory'], 'home.json'),
                 JSON.generate({ 'type' => 'Text', 'text' => 'home_items_count' }))

      expect { run_update(config) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'raises for a CLDR-invalid category (en zero)' do
      config = base_config(ts: true)
      write_resources_strings(config, { 'home' => { 'k' => {
        'en' => { 'plural' => { 'zero' => 'none', 'other' => '{count}' } }
      } } })

      expect { run_update(config) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end

    it 'rejects plural entries in legacy per-language files' do
      config = base_config(ts: true)
      FileUtils.mkdir_p(config['layouts_directory'])
      FileUtils.mkdir_p(config['strings_directory'])
      File.write(File.join(config['strings_directory'], 'en.json'),
                 JSON.generate({ 'k' => { 'plural' => { 'other' => '{count}' } } }))

      expect { run_update(config) }
        .to raise_error(JsonUIShared::PluralValidator::ValidationError)
    end
  end

  describe 'copy consistency' do
    it 'stays byte-identical to the canonical shared/core copy' do
      tool_copy = File.expand_path('../../../lib/core/plural_validator.rb', __dir__)
      shared_copy = File.expand_path('../../../../shared/core/plural_validator.rb', __dir__)
      skip 'shared/core copy not present in this layout' unless File.exist?(shared_copy)
      expect(File.read(tool_copy)).to eq(File.read(shared_copy))
    end
  end
end
