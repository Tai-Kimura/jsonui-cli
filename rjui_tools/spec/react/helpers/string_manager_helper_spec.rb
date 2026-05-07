# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require_relative '../../spec_helper'
require 'core/config_manager'
require 'react/helpers/string_manager_helper'

RSpec.describe RjuiTools::React::Helpers::StringManagerHelper do
  # Minimal host class that includes the helper so we can exercise the lookup
  # methods directly without the full ReactGenerator wiring.
  let(:host_class) do
    Class.new do
      include RjuiTools::React::Helpers::StringManagerHelper

      attr_accessor :config

      def initialize(config)
        @config = config
      end
    end
  end

  # The helper loads strings.json via Core::ConfigManager.load_config, so we
  # stage a minimal repo layout inside a tmpdir and Dir.chdir into it.
  around do |example|
    Dir.mktmpdir do |dir|
      layouts_dir = File.join(dir, 'docs', 'screens', 'layouts')
      resources_dir = File.join(layouts_dir, 'Resources')
      FileUtils.mkdir_p(resources_dir)

      File.write(
        File.join(dir, 'rjui.config.json'),
        JSON.generate('layouts_directory' => layouts_dir)
      )

      # Two namespaces sharing a key name. `learn_hello_world` is written
      # first, so a linear scan (Phase 3) will pick it up before
      # `learn_installation`.
      File.write(
        File.join(resources_dir, 'strings.json'),
        JSON.generate(
          'learn_hello_world' => { 'lang_toggle' => 'Language: Hello' },
          'learn_installation' => { 'lang_toggle' => 'Language: Install' }
        )
      )

      Dir.chdir(dir) { example.run }
    end
  end

  describe '#convert_string_key with directory-qualified namespace' do
    it 'resolves a bare key to the screen that owns it when subdir is on _current_json_name' do
      host = host_class.new('_current_json_name' => 'learn_installation')
      expect(host.convert_string_key('lang_toggle'))
        .to eq('{StringManager.currentLanguage.learnInstallationLangToggle}')
    end

    it 'does NOT silently resolve to the sibling namespace when the screen is installation' do
      host = host_class.new('_current_json_name' => 'learn_installation')
      expect(host.convert_string_key('lang_toggle'))
        .not_to include('learnHelloWorld')
    end

    it 'still resolves root-level layouts (no subdir) when the namespace matches the basename' do
      # Extend strings.json with a root-level namespace so we can cover the
      # no-subdir path too.
      extra = JSON.parse(
        File.read(File.join('docs', 'screens', 'layouts', 'Resources', 'strings.json'))
      )
      extra['home'] = { 'welcome' => 'Hello' }
      File.write(
        File.join('docs', 'screens', 'layouts', 'Resources', 'strings.json'),
        JSON.generate(extra)
      )

      host = host_class.new('_current_json_name' => 'home')
      expect(host.convert_string_key('welcome'))
        .to eq('{StringManager.currentLanguage.homeWelcome}')
    end

    it 'returns nil for snake_case identifiers that do not resolve in strings.json' do
      # `bash` / `yaml` / `shell` look like snake_case keys but are not
      # translations — they are Shiki language ids, file extensions, etc.
      # The old fallback emitted `{StringManager.currentLanguage.bash}`
      # which is undefined at runtime. Returning nil lets callers fall
      # back to a literal.
      host = host_class.new('_current_json_name' => 'learn_installation')
      expect(host.convert_string_key('bash')).to be_nil
      expect(host.convert_string_key('yaml_config')).to be_nil
    end

    it 'returns nil for non-snake_case values (was already nil-ish, now explicit)' do
      host = host_class.new('_current_json_name' => 'learn_installation')
      expect(host.convert_string_key('On this page')).to be_nil
      expect(host.convert_string_key('@{binding}')).to be_nil
    end
  end

  describe '#rewrite_json_string_values' do
    let(:host) { host_class.new('_current_json_name' => 'learn_installation') }

    it 'rewrites resolvable object values to bare StringManager expressions' do
      json = '{"id":"a","label":"lang_toggle"}'
      # `lang_toggle` resolves (both namespaces have it); `a` does not.
      result = host.rewrite_json_string_values(json)
      expect(result).to include('"id":"a"')
      expect(result).to include('"label": StringManager.currentLanguage.learnInstallationLangToggle')
      expect(result).not_to include('"lang_toggle"')
    end

    it 'leaves values that do not resolve to any strings.json namespace alone' do
      # `section_contract` matches the snake_case pattern but is not in
      # strings.json — this is the safety gate for identifier fields.
      json = '{"anchor":"section_contract","label":"lang_toggle"}'
      result = host.rewrite_json_string_values(json)
      expect(result).to include('"anchor":"section_contract"')
      expect(result).to include('StringManager.currentLanguage.learnInstallationLangToggle')
    end

    it 'leaves JSON object keys untouched' do
      # `label` itself is a strings.json namespace candidate (snake_case) but
      # appears as a KEY here, not a VALUE — must not be substituted.
      json = '{"label":"lang_toggle"}'
      result = host.rewrite_json_string_values(json)
      expect(result).to include('"label":')  # key preserved verbatim
    end

    it 'preserves strings that contain spaces (regular text)' do
      json = '{"label":"On this page"}'
      result = host.rewrite_json_string_values(json)
      expect(result).to eq('{"label":"On this page"}')
    end

    it 'handles arrays of objects' do
      json = '[{"id":"x","label":"lang_toggle"},{"id":"y","label":"lang_toggle"}]'
      result = host.rewrite_json_string_values(json)
      expect(result.scan(/StringManager\.currentLanguage\.learnInstallationLangToggle/).size).to eq(2)
      expect(result).to include('"id":"x"')
      expect(result).to include('"id":"y"')
    end
  end
end
