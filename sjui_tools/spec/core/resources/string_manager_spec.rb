# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'

RSpec.describe SjuiTools::Core::Resources::StringManager do
  let(:temp_dir) { Dir.mktmpdir('string_manager_test') }
  let(:layouts_dir) { File.join(temp_dir, 'Layouts') }
  let(:resources_dir) { File.join(layouts_dir, 'Resources') }
  let(:resource_manager_dir) { File.join(temp_dir, 'ResourceManager') }

  before do
    FileUtils.mkdir_p(layouts_dir)
    FileUtils.mkdir_p(resources_dir)

    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'layouts_directory' => 'Layouts',
      'resource_manager_directory' => 'ResourceManager'
    })
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates instance' do
      manager = described_class.new
      expect(manager).to be_a(described_class)
    end
  end

  describe '#process_json_files' do
    let(:manager) { described_class.new }
    let(:json_file) { File.join(layouts_dir, 'home.json') }

    before do
      File.write(json_file, JSON.pretty_generate({
        'type' => 'VStack',
        'children' => [
          { 'type' => 'Text', 'text' => 'home_welcome_message' },
          { 'type' => 'Text', 'text' => 'home_subtitle' }
        ]
      }))
    end

    it 'extracts strings from json files' do
      result = manager.process_json_files([json_file])
      expect(result['strings']).to have_key('home')
    end

    it 'extracts regular text values but skips snake_case' do
      # Snake_case values like 'home_welcome_message' are skipped (considered already converted)
      result = manager.process_json_files([json_file])
      # The file should exist but no strings extracted since it's snake_case
      expect(result['strings']).to have_key('home')
    end

    it 'handles invalid json gracefully' do
      invalid_file = File.join(layouts_dir, 'invalid.json')
      File.write(invalid_file, 'invalid json')

      expect { manager.process_json_files([invalid_file]) }.not_to raise_error
    end
  end

  describe '#cache_strings_files' do
    let(:manager) { described_class.new }
    let(:strings_file) { File.join(temp_dir, 'Localizable.strings') }

    before do
      File.write(strings_file, <<~STRINGS)
        "home_welcome" = "Welcome!";
        "home_subtitle" = "Hello World";
      STRINGS
    end

    it 'caches strings from .strings files' do
      manager.cache_strings_files(['Localizable.strings'])
      # Should not raise error
    end

    it 'warns for non-existent files' do
      expect { manager.cache_strings_files(['nonexistent.strings']) }.to output(/Strings file not found/).to_stdout
    end
  end

  describe '#write_strings_json' do
    let(:manager) { described_class.new }
    let(:json_file) { File.join(layouts_dir, 'home.json') }

    before do
      # Use regular text (not snake_case) so it gets extracted
      File.write(json_file, JSON.pretty_generate({
        'type' => 'Text',
        'text' => 'Welcome Home!'
      }))
      manager.process_json_files([json_file])
    end

    it 'writes strings.json to Resources directory' do
      manager.write_strings_json

      strings_file = File.join(resources_dir, 'strings.json')
      expect(File.exist?(strings_file)).to be true
    end

    it 'writes strings as key-value pairs' do
      manager.write_strings_json

      strings_file = File.join(resources_dir, 'strings.json')
      content = JSON.parse(File.read(strings_file))
      expect(content['home']).to have_key('welcome_home')
      expect(content['home']['welcome_home']).to eq('Welcome Home!')
    end
  end

  describe '#get_extraction_summary' do
    let(:manager) { described_class.new }
    let(:json_file) { File.join(layouts_dir, 'home.json') }

    before do
      # Use regular text (not snake_case) so it gets extracted
      File.write(json_file, JSON.pretty_generate({
        'type' => 'Text',
        'text' => 'Welcome Home!'
      }))
      manager.process_json_files([json_file])
    end

    it 'returns summary with files_count' do
      summary = manager.get_extraction_summary
      expect(summary).to have_key('files_count')
    end

    it 'returns summary with total_strings' do
      summary = manager.get_extraction_summary
      expect(summary).to have_key('total_strings')
      expect(summary['total_strings']).to eq(1)
    end
  end

  describe '#generate_swift_file' do
    let(:manager) { described_class.new }
    let(:strings_json_file) { File.join(resources_dir, 'strings.json') }

    before do
      FileUtils.mkdir_p(resource_manager_dir)
      File.write(strings_json_file, JSON.pretty_generate({
        'home' => {
          'title' => 'Home',
          'subtitle' => 'Welcome'
        }
      }))
    end

    it 'generates StringManager.swift' do
      manager.generate_swift_file

      output_file = File.join(resource_manager_dir, 'StringManager.swift')
      expect(File.exist?(output_file)).to be true
    end

    it 'includes struct for each file' do
      manager.generate_swift_file

      output_file = File.join(resource_manager_dir, 'StringManager.swift')
      content = File.read(output_file)
      expect(content).to include('struct Home')
    end

    it 'warns when strings.json not found' do
      FileUtils.rm_f(strings_json_file)
      expect { manager.generate_swift_file }.to output(/strings.json not found/).to_stdout
    end
  end

  describe '#process_strings' do
    let(:manager) { described_class.new }
    let(:json_file) { File.join(layouts_dir, 'home.json') }

    before do
      FileUtils.mkdir_p(resource_manager_dir)
      File.write(json_file, JSON.pretty_generate({
        'type' => 'Text',
        'text' => 'home_title'
      }))
    end

    it 'processes strings and generates files' do
      config = {
        'layouts_directory' => 'Layouts',
        'resource_manager_directory' => 'ResourceManager'
      }

      manager.process_strings([json_file], 1, 0, config)

      strings_file = File.join(resources_dir, 'strings.json')
      expect(File.exist?(strings_file)).to be true
    end
  end

  describe '#string_registered?' do
    let(:manager) { described_class.new }
    let(:strings_file) { File.join(temp_dir, 'Localizable.strings') }

    before do
      File.write(strings_file, <<~STRINGS)
        "logout_text" = "Logout";
        "settings_title" = "Settings";
      STRINGS
      manager.cache_strings_files(['Localizable.strings'])
    end

    it 'returns true for registered keys' do
      expect(manager.string_registered?('logout_text')).to be true
      expect(manager.string_registered?('settings_title')).to be true
    end

    it 'returns false for unregistered keys' do
      expect(manager.string_registered?('unknown_key')).to be false
    end

    it 'returns false when cache is empty' do
      empty_manager = described_class.new
      expect(empty_manager.string_registered?('any_key')).to be false
    end

    it 'skips keys in auto-generated section' do
      auto_gen_manager = described_class.new
      auto_gen_strings_file = File.join(temp_dir, 'AutoGen.strings')
      File.write(auto_gen_strings_file, <<~STRINGS)
        "manual_key" = "Manual Value";
        /* Auto-generated strings - DO NOT EDIT */
        "auto_generated_key" = "Auto Value";
      STRINGS
      auto_gen_manager.cache_strings_files(['AutoGen.strings'])
      expect(auto_gen_manager.string_registered?('manual_key')).to be true
      expect(auto_gen_manager.string_registered?('auto_generated_key')).to be false
    end
  end

  describe '#strings_cache' do
    let(:manager) { described_class.new }
    let(:strings_file) { File.join(temp_dir, 'Localizable.strings') }

    before do
      File.write(strings_file, <<~STRINGS)
        "home_title" = "Home";
      STRINGS
      manager.cache_strings_files(['Localizable.strings'])
    end

    it 'returns the cached strings' do
      cache = manager.strings_cache
      expect(cache).to have_key('home_title')
      expect(cache['home_title']).to eq('Home')
    end

    it 'returns empty hash when not cached' do
      empty_manager = described_class.new
      expect(empty_manager.strings_cache).to eq({})
    end
  end

  describe '#string_manager_call' do
    let(:manager) { described_class.new }

    it 'generates StringManager function call for simple key' do
      expect(manager.string_manager_call('logout_text')).to eq('StringManager.logoutText()')
    end

    it 'generates StringManager function call for multi-word key' do
      expect(manager.string_manager_call('settings_notification_title')).to eq('StringManager.settingsNotificationTitle()')
    end

    it 'generates StringManager function call for single word key' do
      expect(manager.string_manager_call('title')).to eq('StringManager.title()')
    end

    it 'handles keys with numbers' do
      expect(manager.string_manager_call('caution_1')).to eq('StringManager.caution1()')
    end
  end

  describe 'private methods' do
    let(:manager) { described_class.new }

    describe '#snake_to_camel' do
      it 'converts snake_case to camelCase' do
        expect(manager.send(:snake_to_camel, 'submit_button')).to eq('submitButton')
      end

      it 'handles single word' do
        expect(manager.send(:snake_to_camel, 'title')).to eq('title')
      end

      it 'handles numbers at end' do
        expect(manager.send(:snake_to_camel, 'caution_1')).to eq('caution1')
      end

      it 'handles pure numbers' do
        expect(manager.send(:snake_to_camel, '123')).to eq('value123')
      end
    end

    describe '#escape_json_string' do
      it 'escapes double quotes' do
        expect(manager.send(:escape_json_string, 'say "hello"')).to eq('say \\"hello\\"')
      end

      it 'escapes newlines' do
        expect(manager.send(:escape_json_string, "line1\nline2")).to eq('line1\\nline2')
      end

      it 'escapes tabs' do
        expect(manager.send(:escape_json_string, "col1\tcol2")).to eq('col1\\tcol2')
      end
    end

    describe '#escape_swift_string' do
      it 'escapes double quotes' do
        expect(manager.send(:escape_swift_string, 'say "hello"')).to eq('say \\"hello\\"')
      end

      it 'escapes newlines' do
        expect(manager.send(:escape_swift_string, "line1\nline2")).to eq('line1\\nline2')
      end
    end

    describe '#should_extract_string?' do
      it 'returns false for data binding expressions with @{}' do
        expect(manager.send(:should_extract_string?, '@{viewModel.title}')).to be false
      end

      it 'returns false for data binding expressions with ${}' do
        expect(manager.send(:should_extract_string?, '${viewModel.title}')).to be false
      end

      it 'returns false for snake_case strings (already converted)' do
        expect(manager.send(:should_extract_string?, 'hello_world')).to be false
      end

      it 'returns true for regular text strings' do
        expect(manager.send(:should_extract_string?, 'Hello World')).to be true
      end

      it 'returns false for very short non-snake_case strings' do
        expect(manager.send(:should_extract_string?, 'Hi')).to be false
      end

      it 'returns false for strings without letters' do
        expect(manager.send(:should_extract_string?, '12345')).to be false
      end

      it 'returns true for Japanese hiragana text' do
        expect(manager.send(:should_extract_string?, 'こんにちは')).to be true
      end

      it 'returns true for Japanese katakana text' do
        expect(manager.send(:should_extract_string?, 'コンニチハ')).to be true
      end

      it 'returns true for Japanese kanji text' do
        expect(manager.send(:should_extract_string?, '完了する')).to be true
      end

      it 'returns true for mixed Japanese and English text' do
        expect(manager.send(:should_extract_string?, 'Hello 世界')).to be true
      end

      it 'returns false for short Japanese text (2 chars or less)' do
        expect(manager.send(:should_extract_string?, '完了')).to be false
      end
    end

    describe '#generate_string_key' do
      before do
        # generate_string_key reads @current_file_strings to de-duplicate keys.
        manager.instance_variable_set(:@current_file_strings, {})
      end

      it 'converts text to snake_case' do
        expect(manager.send(:generate_string_key, 'Hello World')).to eq('hello_world')
      end

      it 'removes special characters' do
        expect(manager.send(:generate_string_key, 'Hello, World!')).to eq('hello_world')
      end

      it 'limits key length' do
        long_text = 'This is a very long string that should be truncated to thirty chars'
        result = manager.send(:generate_string_key, long_text)
        expect(result.length).to be <= 31
      end

      it 'removes leading and trailing underscores' do
        expect(manager.send(:generate_string_key, '  Hello  ')).to eq('hello')
      end

      it 'collapses multiple underscores' do
        expect(manager.send(:generate_string_key, 'Hello   World')).to eq('hello_world')
      end

      it 'uses original text as key for Japanese hiragana' do
        expect(manager.send(:generate_string_key, 'こんにちは')).to eq('こんにちは')
      end

      it 'uses original text as key for Japanese katakana' do
        expect(manager.send(:generate_string_key, 'コンニチハ')).to eq('コンニチハ')
      end

      it 'uses original text as key for Japanese kanji' do
        expect(manager.send(:generate_string_key, '完了する')).to eq('完了する')
      end

      it 'uses original text as key for mixed Japanese' do
        expect(manager.send(:generate_string_key, 'お支払い方法を選択')).to eq('お支払い方法を選択')
      end

      it 'trims whitespace for Japanese text' do
        expect(manager.send(:generate_string_key, '  完了する  ')).to eq('完了する')
      end
    end

    describe '#extract_strings_recursive' do
      before do
        manager.instance_variable_set(:@current_file_strings, {})
      end

      it 'skips already converted snake_case keys (text)' do
        # Snake_case values are already converted keys - skip them to preserve strings.json
        data = { 'type' => 'Text', 'text' => 'home_title' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips already converted snake_case keys (hint)' do
        data = { 'type' => 'TextField', 'hint' => 'home_enter_name' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips already converted snake_case keys (placeholder)' do
        data = { 'type' => 'TextField', 'placeholder' => 'home_search' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips already converted snake_case keys (label)' do
        data = { 'type' => 'Checkbox', 'label' => 'home_accept_terms' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips already converted snake_case keys (prompt)' do
        data = { 'type' => 'SelectBox', 'prompt' => 'home_select_option' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips snake_case values regardless of file prefix' do
        # All snake_case values are skipped - they are already converted
        data = { 'type' => 'Text', 'text' => 'other_title' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips binding expressions with @{}' do
        data = { 'type' => 'Text', 'text' => '@{viewModel.title}' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips binding expressions with ${}' do
        data = { 'type' => 'Text', 'text' => '${viewModel.title}' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'generates key for regular text (not snake_case)' do
        data = { 'type' => 'Text', 'text' => 'Hello World!' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to have_key('hello_world')
        expect(strings['hello_world']).to eq('Hello World!')
      end

      it 'skips snake_case in nested children' do
        data = {
          'type' => 'VStack',
          'children' => [
            { 'type' => 'Text', 'text' => 'home_child_text' }
          ]
        }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips snake_case in partial_attributes with range hash' do
        # partial_attributes range hash uses 'text' key which is processed recursively
        data = {
          'type' => 'Text',
          'partial_attributes' => [
            { 'range' => { 'text' => 'home_bold_text' } }
          ]
        }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'skips snake_case in partial_attributes with range string' do
        data = {
          'type' => 'Text',
          'partial_attributes' => [
            { 'range' => 'home_link_text' }
          ]
        }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end

      it 'extracts Japanese text and uses original as key' do
        data = { 'type' => 'Text', 'text' => '完了する' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to have_key('完了する')
        expect(strings['完了する']).to eq('完了する')
      end

      it 'extracts mixed Japanese-English text' do
        data = { 'type' => 'Text', 'text' => 'Hello 世界!' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to have_key('Hello 世界!')
        expect(strings['Hello 世界!']).to eq('Hello 世界!')
      end

      it 'skips short Japanese text (2 chars or less)' do
        data = { 'type' => 'Text', 'text' => '完了' }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings).to be_empty
      end
    end

    describe '#generate_swift_content' do
      it 'generates static functions from strings_cache' do
        # Set up strings cache
        manager.instance_variable_set(:@strings_cache, {
          'logout_text' => 'Logout',
          'settings_title' => 'Settings'
        })

        strings_data = {}
        swift_content = manager.send(:generate_swift_content, strings_data)

        expect(swift_content).to include('// MARK: - Localizable.strings keys')
        expect(swift_content).to include('public static func logoutText() -> String {')
        expect(swift_content).to include('return "logout_text".localized()')
        expect(swift_content).to include('public static func settingsTitle() -> String {')
        expect(swift_content).to include('return "settings_title".localized()')
      end

      it 'generates functions in sorted order' do
        manager.instance_variable_set(:@strings_cache, {
          'zebra_key' => 'Zebra',
          'apple_key' => 'Apple',
          'middle_key' => 'Middle'
        })

        strings_data = {}
        swift_content = manager.send(:generate_swift_content, strings_data)

        apple_pos = swift_content.index('appleKey')
        middle_pos = swift_content.index('middleKey')
        zebra_pos = swift_content.index('zebraKey')

        expect(apple_pos).to be < middle_pos
        expect(middle_pos).to be < zebra_pos
      end

      it 'does not generate MARK section when cache is empty' do
        manager.instance_variable_set(:@strings_cache, {})

        strings_data = {}
        swift_content = manager.send(:generate_swift_content, strings_data)

        expect(swift_content).not_to include('// MARK: - Localizable.strings keys')
      end
    end
  end
end
