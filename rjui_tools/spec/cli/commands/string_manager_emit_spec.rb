# frozen_string_literal: true

require_relative '../../spec_helper'
require 'fileutils'
require 'tmpdir'
require 'cli/commands/build_command'
require 'cli/commands/init_command'

RSpec.describe 'StringManager emit' do
  describe RjuiTools::CLI::Commands::BuildCommand do
    let(:instance) { described_class.allocate }

    def content_for(is_ts:)
      strings_json = JSON.pretty_generate({ 'en' => { 'k' => 'v' } })
      if is_ts
        instance.send(:string_manager_typescript_content, strings_json, 'en', '// HEADER', '// FOOTER')
      else
        instance.send(:string_manager_javascript_content, strings_json, 'en', '// HEADER', '// FOOTER')
      end
    end

    it 'emits TS-typed members and StringsRoot type when typescript is true' do
      out = content_for(is_ts: true)
      expect(out).to include('type StringsRoot = Record<string, StringMap>;')
      expect(out).to include('private _currentLanguage: string;')
      expect(out).to include('setLanguage(lang: string): void')
      expect(out).to include('getString(key: string): string')
    end

    it 'emits plain JS class (no type annotations) when typescript is false' do
      out = content_for(is_ts: false)
      expect(out).not_to include('type StringsRoot')
      expect(out).not_to include('private _currentLanguage')
      expect(out).to include('class StringManagerClass {')
    end

    it 'wires useSyncExternalStore with a stable default-language server snapshot to avoid hydration mismatch' do
      [true, false].each do |is_ts|
        out = content_for(is_ts: is_ts)
        expect(out).to include('function getServerSnapshot')
        expect(out).to include("createCamelCaseProxy(strings['en'])")
        expect(out).to include('useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot)')
        expect(out).not_to include('useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getLanguageSnapshot)')
      end
    end

    it 'exposes getDefaultString(key) as an SSR-safe lookup for VM seed code' do
      [true, false].each do |is_ts|
        out = content_for(is_ts: is_ts)
        expect(out).to include('getDefaultString(key')
        expect(out).to include("const defaultLang = 'en';")
        expect(out).to include("this._cache[defaultLang] = createCamelCaseProxy(strings[defaultLang]);")
        expect(out).to include('return this._cache[defaultLang][key] || key;')
      end
    end

    # Regression: rjui-stringmanager-proxy-digit-underscore.
    # The TSX generator collapses `_` before BOTH letters and digits when
    # camelCasing (`trouble_1_symptom` → `Trouble1Symptom`). The proxy must
    # mirror that: `/_([a-z])/g` would only collapse `_<letter>` and leave
    # `_1` intact, so `$s.…Trouble1Symptom` lookups returned `undefined` and
    # rendered as empty `<span>`s. The fix widens the char class to
    # `[a-z0-9]`; `toUpperCase()` is a no-op on digits so the callback
    # works unchanged.
    it 'createCamelCaseProxy regex includes digits in the underscore-strip class' do
      [true, false].each do |is_ts|
        out = content_for(is_ts: is_ts)
        expect(out).to include('key.replace(/_([a-z0-9])/g')
        expect(out).not_to include('key.replace(/_([a-z])/g')
      end
    end
  end

  describe RjuiTools::CLI::Commands::InitCommand do
    let(:instance) { described_class.allocate }

    it 'emits TS-typed stub for typescript' do
      strings_json = JSON.pretty_generate({ 'en' => {} })
      out = instance.send(:string_manager_typescript_stub, strings_json, 'en', '// H', '// F')
      expect(out).to include('const strings: StringsRoot =')
      expect(out).to include('private _currentLanguage: string;')
    end

    it 'emits plain JS stub' do
      strings_json = JSON.pretty_generate({ 'en' => {} })
      out = instance.send(:string_manager_javascript_stub, strings_json, 'en', '// H', '// F')
      expect(out).to include('const strings = ')
      expect(out).not_to include(': StringsRoot')
    end

    it 'init stub also wires getServerSnapshot to default language' do
      strings_json = JSON.pretty_generate({ 'en' => {} })
      [
        instance.send(:string_manager_typescript_stub, strings_json, 'en', '// H', '// F'),
        instance.send(:string_manager_javascript_stub, strings_json, 'en', '// H', '// F'),
      ].each do |out|
        expect(out).to include('function getServerSnapshot')
        expect(out).to include('useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot)')
      end
    end

    it 'init stub exposes getDefaultString(key) for SSR-safe VM seed code' do
      strings_json = JSON.pretty_generate({ 'en' => {} })
      [
        instance.send(:string_manager_typescript_stub, strings_json, 'en', '// H', '// F'),
        instance.send(:string_manager_javascript_stub, strings_json, 'en', '// H', '// F'),
      ].each do |out|
        expect(out).to include('getDefaultString(key')
        expect(out).to include("const defaultLang = 'en';")
      end
    end

    # Regression: rjui-stringmanager-proxy-digit-underscore (init-time stub
    # must match build-time output — `jui init` lays down the same proxy
    # before any build runs, so the digit-underscore handling needs to be
    # present at scaffold time too).
    it 'init stub createCamelCaseProxy regex includes digits' do
      strings_json = JSON.pretty_generate({ 'en' => {} })
      [
        instance.send(:string_manager_typescript_stub, strings_json, 'en', '// H', '// F'),
        instance.send(:string_manager_javascript_stub, strings_json, 'en', '// H', '// F'),
      ].each do |out|
        expect(out).to include('key.replace(/_([a-z0-9])/g')
        expect(out).not_to include('key.replace(/_([a-z])/g')
      end
    end
  end

  describe RjuiTools::CLI::Commands::BuildCommand, 'update_string_manager file output' do
    let(:instance) { described_class.allocate }
    let(:tmpdir) { Dir.mktmpdir }

    after { FileUtils.remove_entry(tmpdir) }

    def run_with_config(ts:, seed: {})
      config = {
        'generated_directory' => File.join(tmpdir, 'generated'),
        'layouts_directory' => File.join(tmpdir, 'Layouts'),
        'strings_directory' => File.join(tmpdir, 'Strings'),
        'languages' => ['en'],
        'default_language' => 'en',
        'typescript' => ts
      }
      FileUtils.mkdir_p(config['strings_directory'])
      File.write(File.join(config['strings_directory'], 'en.json'), JSON.generate({ 'hello' => 'Hello' }))
      seed.each { |path, bytes| File.write(path, bytes) }
      instance.instance_variable_set(:@config, config)
      instance.send(:update_string_manager)
      config
    end

    it 'writes StringManager.ts when typescript is true' do
      config = run_with_config(ts: true)
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.ts'))).to be true
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.js'))).to be false
    end

    it 'writes StringManager.js when typescript is false' do
      config = run_with_config(ts: false)
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.js'))).to be true
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.ts'))).to be false
    end

    it 'cleans up the stale other-extension file when flipping modes' do
      config = run_with_config(ts: false)
      stale_ts = File.join(config['generated_directory'], 'StringManager.ts')
      FileUtils.mkdir_p(File.dirname(stale_ts))
      File.write(stale_ts, '// stale')
      # Re-run in TS mode
      run_with_config(ts: true)
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.ts'))).to be true
      expect(File.exist?(File.join(config['generated_directory'], 'StringManager.js'))).to be false
    end
  end
end
