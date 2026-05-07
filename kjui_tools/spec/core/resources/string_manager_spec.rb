# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Core::Resources::StringManager do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    }
  end
  let(:source_path) { temp_dir }
  let(:resources_dir) { File.join(temp_dir, 'src/main/assets/Layouts/Resources') }
  let(:manager) { described_class.new(config, source_path, resources_dir) }

  before do
    FileUtils.mkdir_p(resources_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets up strings file path' do
      expect(manager.instance_variable_get(:@strings_file)).to include('strings.json')
    end

    it 'initializes empty extracted strings' do
      expect(manager.instance_variable_get(:@extracted_strings)).to eq({})
    end
  end

  describe '#process_strings' do
    it 'returns early for empty files list' do
      expect(KjuiTools::Core::Logger).not_to receive(:info)
      manager.process_strings([], 0, 0)
    end

    it 'logs extraction info for non-empty files' do
      layouts_dir = File.join(temp_dir, 'src/main/assets/Layouts')
      FileUtils.mkdir_p(layouts_dir)
      json_file = File.join(layouts_dir, 'test.json')
      File.write(json_file, '{"type": "Text", "text": "Hello World"}')

      # Allow multiple info calls
      allow(KjuiTools::Core::Logger).to receive(:info)
      allow(KjuiTools::Core::Logger).to receive(:debug)
      expect(KjuiTools::Core::Logger).to receive(:info).with(/Extracting strings/).at_least(:once)
      manager.process_strings([json_file], 1, 0)
    end
  end

  describe 'private methods' do
    describe '#is_string_property?' do
      it 'returns true for text property' do
        expect(manager.send(:is_string_property?, 'text')).to be true
      end

      it 'returns true for hint property' do
        expect(manager.send(:is_string_property?, 'hint')).to be true
      end

      it 'returns true for placeholder property' do
        expect(manager.send(:is_string_property?, 'placeholder')).to be true
      end

      it 'returns true for label property' do
        expect(manager.send(:is_string_property?, 'label')).to be true
      end

      it 'returns true for prompt property' do
        expect(manager.send(:is_string_property?, 'prompt')).to be true
      end

      it 'returns false for non-string properties' do
        expect(manager.send(:is_string_property?, 'background')).to be false
        expect(manager.send(:is_string_property?, 'fontSize')).to be false
      end
    end

    describe '#should_extract_string?' do
      it 'returns false for data binding expressions' do
        expect(manager.send(:should_extract_string?, '@{userName}')).to be false
        expect(manager.send(:should_extract_string?, '${userName}')).to be false
      end

      it 'returns false for snake_case strings (already converted keys)' do
        expect(manager.send(:should_extract_string?, 'hello_world')).to be false
        expect(manager.send(:should_extract_string?, 'test_string_key')).to be false
      end

      it 'returns true for regular text strings' do
        expect(manager.send(:should_extract_string?, 'Hello World')).to be true
      end

      it 'returns false for very short strings without letters' do
        expect(manager.send(:should_extract_string?, '12')).to be false
      end

      it 'returns false for strings without letters' do
        expect(manager.send(:should_extract_string?, '12345')).to be false
      end
    end

    describe '#generate_string_key' do
      it 'converts text to snake_case' do
        expect(manager.send(:generate_string_key, 'Hello World')).to eq('hello_world')
      end

      it 'removes special characters' do
        expect(manager.send(:generate_string_key, 'Hello, World!')).to eq('hello_world')
      end

      it 'limits key length' do
        long_text = 'This is a very long string that should be truncated to thirty chars'
        result = manager.send(:generate_string_key, long_text)
        expect(result.length).to be <= 35  # 30 + some buffer for the actual implementation
      end

      it 'removes leading and trailing underscores' do
        expect(manager.send(:generate_string_key, '  Hello  ')).to eq('hello')
      end

      it 'collapses multiple underscores' do
        expect(manager.send(:generate_string_key, 'Hello   World')).to eq('hello_world')
      end
    end

    describe '#generate_file_prefix' do
      it 'removes .json extension' do
        expect(manager.send(:generate_file_prefix, 'test.json')).to eq('test')
      end

      it 'replaces slashes with underscores' do
        expect(manager.send(:generate_file_prefix, 'subdir/test.json')).to eq('subdir_test')
      end

      it 'handles multiple directories' do
        expect(manager.send(:generate_file_prefix, 'a/b/c/test.json')).to eq('a_b_c_test')
      end
    end

    describe '#snake_to_camel' do
      it 'converts snake_case to camelCase' do
        expect(manager.send(:snake_to_camel, 'hello_world')).to eq('helloWorld')
      end

      it 'handles single word' do
        expect(manager.send(:snake_to_camel, 'hello')).to eq('hello')
      end

      it 'handles multiple underscores' do
        expect(manager.send(:snake_to_camel, 'hello_big_world')).to eq('helloBigWorld')
      end
    end

    describe '#create_new_strings_xml' do
      it 'creates XML document with resources root' do
        doc = manager.send(:create_new_strings_xml)
        expect(doc.root.name).to eq('resources')
      end

      it 'includes XML declaration' do
        doc = manager.send(:create_new_strings_xml)
        expect(doc.xml_decl.version).to eq('1.0')
        expect(doc.xml_decl.encoding.downcase).to eq('utf-8')
      end
    end

    describe '#get_translated_value' do
      it 'returns default value' do
        result = manager.send(:get_translated_value, 'key', 'Hello', 'values')
        expect(result).to eq('Hello')
      end
    end
  end

  describe '#apply_to_strings_files' do
    it 'returns early when strings_data is empty' do
      manager.instance_variable_set(:@strings_data, {})
      expect(manager).not_to receive(:update_strings_xml)
      manager.apply_to_strings_files
    end

    it 'updates default strings.xml when no string_files configured' do
      manager.instance_variable_set(:@strings_data, { 'test' => { 'key' => 'value' } })
      expect(manager).to receive(:update_strings_xml).with('values')
      manager.apply_to_strings_files
    end
  end
end
