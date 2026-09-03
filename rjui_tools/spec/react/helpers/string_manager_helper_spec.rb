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

  # A bare key resolves ONLY in sections the layout owns; cross-section
  # reach is the fully-qualified '<section>_<key>' spelling. The old
  # "all other files as fallback" phase resolved a bare key through
  # whatever section happened to declare it (asymmetric-resolution
  # filing, 2026-08-11).
  describe 'bare keys and the own-section canon' do
    it 'does not resolve a bare key only foreign sections declare, and says so' do
      host = host_class.new(
        '_current_json_name' => 'settings',
        '_current_namespaces' => %w[settings]
      )
      allow(RjuiTools::Core::Logger).to receive(:warn)
      expect(host.convert_string_key('lang_toggle')).to be_nil
      expect(RjuiTools::Core::Logger).to have_received(:warn)
        .with(a_string_matching(
          /foreign strings\.json section\(s\) learn_hello_world, learn_installation/
        ))
    end

    it 'owns both the basename and the relative-path spelling' do
      host = host_class.new(
        '_current_json_name' => 'learn_installation',
        '_current_namespaces' => %w[installation learn_installation]
      )
      expect(host.convert_string_key('lang_toggle'))
        .to eq('{StringManager.currentLanguage.learnInstallationLangToggle}')
    end

    it 'reaches a foreign section through the fully-qualified spelling, silently' do
      host = host_class.new(
        '_current_json_name' => 'settings',
        '_current_namespaces' => %w[settings]
      )
      allow(RjuiTools::Core::Logger).to receive(:warn)
      expect(host.convert_string_key('learn_installation_lang_toggle'))
        .to eq('{StringManager.currentLanguage.learnInstallationLangToggle}')
      expect(RjuiTools::Core::Logger).not_to have_received(:warn)
    end
  end

  # The extractor truncates long ASCII text to 31 chars, which can leave a
  # trailing underscore ("dont_have_an_account_apply_for_"). Such a key is as
  # declared as any other; the old snake_case gate rejected the spelling, and
  # a legacy poison entry whose VALUE is the raw key hijacked the value
  # lookup on the sjui face (downstream login screen, 2026-08-09).
  describe 'declared trailing-underscore keys and key-over-value precedence' do
    before do
      strings_path = File.join('docs', 'screens', 'layouts', 'Resources', 'strings.json')
      extra = JSON.parse(File.read(strings_path))
      extra['login'] = {
        'dont_have_an_account_apply_for_' => "Don't have an account? Apply for Membership",
        # Legacy poison: a key whose value IS the other key's spelling.
        'dont_have_an_account_apply_for' => 'dont_have_an_account_apply_for_'
      }
      File.write(strings_path, JSON.generate(extra))
    end

    let(:host) { host_class.new('_current_json_name' => 'login') }

    it 'resolves a declared trailing-underscore key as the key itself' do
      # `…ApplyFor_`, with the underscore: that is the property the generated
      # proxy defines for this key (it upper-cases only after an underscore
      # and a trailing one has nothing to upper-case). This expectation used
      # to read `…ApplyFor`, the `capitalize`-per-segment spelling, which the
      # runtime does not expose — measured undefined under node, 2026-09-04.
      expect(host.get_text_with_string_manager('dont_have_an_account_apply_for_'))
        .to eq('{StringManager.currentLanguage.loginDontHaveAnAccountApplyFor_}')
    end

    it 'prefers key membership over a value reverse-lookup hit' do
      # Without key-first ordering the poison entry's value match wins.
      # Both resolutions camelize to the same accessor spelling here, so pin
      # the ORDER instead: value lookup must not even be consulted.
      expect(host).not_to receive(:lookup_string_manager_by_value)
      host.get_text_with_string_manager('dont_have_an_account_apply_for_')
    end

    it 'still falls back to value lookup for display text' do
      # Same accessor spelling as the key path above: the value lookup lands
      # on the same trailing-underscore key, so it emits the same property.
      expect(host.get_text_with_string_manager("Don't have an account? Apply for Membership"))
        .to eq('{StringManager.currentLanguage.loginDontHaveAnAccountApplyFor_}')
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

  # A key with a capital used to be invisible to this face: `convert_string_key`
  # asked `string_key?` (lowercase-only) BEFORE consulting strings.json, so a
  # declared key was never looked up and every caller fell back to the raw
  # identifier — which is how `section_collection_basic_bullet_scrollEnabled`
  # reached two published docsite pages as body text with `jui build` and
  # `lint-strings` both green. sjui calls its lookup unconditionally and kjui's
  # step 1 is `entries.key?`; this face was the only one gating on spelling.
  describe 'a key with a capital letter (membership decides, not spelling)' do
    before do
      strings_path = File.join('docs', 'screens', 'layouts', 'Resources', 'strings.json')
      extra = JSON.parse(File.read(strings_path))
      extra['learn_installation'] = extra['learn_installation'].merge(
        'bullet_scrollEnabled' => '• scrollEnabled — whether the collection scrolls'
      )
      extra['learn_hello_world'] = extra['learn_hello_world'].merge(
        'bullet_displayName' => '• displayName — the label shown to the reader'
      )
      File.write(strings_path, JSON.generate(extra))
    end

    let(:host) { host_class.new('_current_json_name' => 'learn_installation') }

    it 'resolves a bare key with a capital, like its all-lowercase sibling' do
      expect(host.convert_string_key('bullet_scrollEnabled'))
        .to eq('{StringManager.currentLanguage.learnInstallationBulletScrollEnabled}')
    end

    it 'resolves the fully-qualified spelling too' do
      # The ticket reported the bare form; the qualified form was equally
      # invisible, because the gate ran before either lookup phase.
      expect(host.convert_string_key('learn_installation_bullet_scrollEnabled'))
        .to eq('{StringManager.currentLanguage.learnInstallationBulletScrollEnabled}')
    end

    it 'still resolves all-lowercase keys' do
      expect(host.convert_string_key('lang_toggle'))
        .to eq('{StringManager.currentLanguage.learnInstallationLangToggle}')
    end

    it 'still returns nil for an identifier that is not declared' do
      # The membership gate is the whole safety story: `bash` / `yaml` /
      # `shell` are key-shaped and must stay literal.
      expect(host.convert_string_key('bash')).to be_nil
      expect(host.convert_string_key('scrollEnabled')).to be_nil
    end

    it 'still returns nil for a binding expression' do
      expect(host.convert_string_key('@{viewModel.title}')).to be_nil
    end

    it 'warns when a key with a capital is declared only in a foreign section' do
      # The one case where the raw identifier still reaches the screen was
      # also the one case nothing warned about: the warning guard carried the
      # same lowercase-only spelling as the gate.
      expect(RjuiTools::Core::Logger).to receive(:warn).with(/bullet_displayName/)
      expect(host.convert_string_key('bullet_displayName')).to be_nil
    end

    it 'rewrites a JSON value that is a key with a capital' do
      json = '{"label":"bullet_scrollEnabled"}'
      expect(host.rewrite_json_string_values(json))
        .to include('StringManager.currentLanguage.learnInstallationBulletScrollEnabled')
    end
  end

  # The emitted accessor has to be the property the GENERATED StringManager
  # exposes. `createCamelCaseProxy` (build_command.rb) upper-cases only the
  # character after an underscore; `capitalize` also lower-cases the rest of
  # the segment, so the two agree on an all-lowercase key and disagree the
  # moment a key carries a capital or a trailing underscore. Measured against
  # the generated proxy under node (2026-09-04): the `capitalize` spellings
  # below are `undefined` at runtime — a blank on the page, which is worse
  # than the identifier the ticket reported.
  describe '#string_manager_accessor matches the generated proxy' do
    let(:host) { host_class.new('_current_json_name' => 'learn_installation') }

    # key in strings.json => property createCamelCaseProxy defines
    {
      'guides_bullet_lazy' => 'guidesBulletLazy',
      'guides_bullet_scrollEnabled' => 'guidesBulletScrollEnabled',
      'login_dont_have_an_account_apply_for_' => 'loginDontHaveAnAccountApplyFor_',
      'a_b_1_c' => 'aB1C'
    }.each do |full_key, accessor|
      it "#{full_key} -> #{accessor}" do
        expect(host.send(:string_manager_accessor, full_key)).to eq(accessor)
      end
    end

    it 'is the JS transformation, not capitalize-per-segment' do
      # The distinguishing input: capitalize would answer "…Scrollenabled".
      expect(host.send(:string_manager_accessor, 'x_scrollEnabled')).to eq('xScrollEnabled')
      expect(host.send(:to_camel_case, 'x_scrollEnabled')).to eq('xScrollenabled')
    end
  end
end
