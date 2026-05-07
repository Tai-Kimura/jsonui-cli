# frozen_string_literal: true

require 'xml/xml_generator'
require 'fileutils'

RSpec.describe XmlGenerator::Generator do
  let(:temp_dir) { Dir.mktmpdir('xml_gen_test') }
  let(:config) do
    {
      'project_path' => temp_dir,
      'layouts_directory' => 'src/main/assets/Layouts',
      'package_name' => 'com.example.app'
    }
  end

  before do
    # Create layout directory
    layout_dir = File.join(temp_dir, 'src/main/assets/Layouts')
    FileUtils.mkdir_p(layout_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates a generator instance' do
      generator = described_class.new('test', config)
      expect(generator).to be_a(described_class)
    end

    it 'accepts options' do
      generator = described_class.new('test', config, { output_filename: 'custom.xml' })
      expect(generator).to be_a(described_class)
    end
  end

  describe 'private helper methods' do
    let(:generator) { described_class.new('test', config) }

    describe '#camelize' do
      it 'converts snake_case to PascalCase' do
        result = generator.send(:camelize, 'home_view')
        expect(result).to eq('HomeView')
      end

      it 'handles single word' do
        result = generator.send(:camelize, 'test')
        expect(result).to eq('Test')
      end
    end

    describe '#check_for_bindings' do
      it 'returns true when bindings present' do
        json_data = { 'text' => '@{title}' }
        result = generator.send(:check_for_bindings, json_data)
        expect(result).to be true
      end

      it 'returns false when no bindings' do
        json_data = { 'text' => 'Hello' }
        result = generator.send(:check_for_bindings, json_data)
        expect(result).to be false
      end
    end

    describe '#has_click_handlers?' do
      it 'returns true for onClick' do
        json_data = { 'onClick' => 'handleClick' }
        result = generator.send(:has_click_handlers?, json_data)
        expect(result).to be true
      end

      it 'returns true for onclick lowercase' do
        json_data = { 'onclick' => 'handleClick' }
        result = generator.send(:has_click_handlers?, json_data)
        expect(result).to be true
      end

      it 'returns false when no handlers' do
        json_data = { 'text' => 'Hello' }
        result = generator.send(:has_click_handlers?, json_data)
        expect(result).to be false
      end
    end

    describe '#has_data_definitions?' do
      it 'returns true when data key exists' do
        json_data = { 'data' => { 'name' => 'String' } }
        result = generator.send(:has_data_definitions?, json_data)
        expect(result).to be true
      end

      it 'returns true when child has data' do
        json_data = { 'child' => [{ 'data' => { 'name' => 'String' } }] }
        result = generator.send(:has_data_definitions?, json_data)
        expect(result).to be true
      end

      it 'returns false when no data' do
        json_data = { 'type' => 'Text' }
        result = generator.send(:has_data_definitions?, json_data)
        expect(result).to be false
      end
    end

    describe '#extract_binding_variables' do
      it 'extracts simple variable' do
        json_data = { 'text' => '@{title}' }
        result = generator.send(:extract_binding_variables, json_data)
        expect(result).to include('title')
      end

      it 'extracts nested variables' do
        json_data = {
          'type' => 'Box',
          'child' => [
            { 'text' => '@{name}' },
            { 'color' => '@{bgColor}' }
          ]
        }
        result = generator.send(:extract_binding_variables, json_data)
        expect(result).to include('name')
        expect(result).to include('bgColor')
      end
    end

    describe '#needs_tools_namespace?' do
      it 'returns true for title attribute' do
        json_data = { 'title' => 'Test Title' }
        result = generator.send(:needs_tools_namespace?, json_data)
        expect(result).to be true
      end

      it 'returns true for count attribute' do
        json_data = { 'count' => 5 }
        result = generator.send(:needs_tools_namespace?, json_data)
        expect(result).to be true
      end

      it 'returns false when no tools needed' do
        json_data = { 'text' => 'Hello' }
        result = generator.send(:needs_tools_namespace?, json_data)
        expect(result).to be false
      end
    end

    describe '#format_attributes' do
      it 'formats single attribute on one line' do
        xml = '<View android:id="@+id/test"/>'
        result = generator.send(:format_attributes, xml)
        expect(result).to include('android:id="@+id/test"')
      end

      it 'preserves XML declaration' do
        xml = '<?xml version="1.0"?>'
        result = generator.send(:format_attributes, xml)
        expect(result).to include('<?xml version="1.0"?>')
      end

      it 'preserves comments' do
        xml = '<!-- Comment -->'
        result = generator.send(:format_attributes, xml)
        expect(result).to include('<!-- Comment -->')
      end
    end
  end

  describe '#generate' do
    context 'with valid layout' do
      before do
        layout_file = File.join(temp_dir, 'src/main/assets/Layouts/test.json')
        File.write(layout_file, JSON.generate({
          'type' => 'View',
          'child' => [
            { 'type' => 'Text', 'text' => 'Hello' }
          ]
        }))

        # Create output directory
        FileUtils.mkdir_p(File.join(temp_dir, 'src/main/res/layout'))
      end

      it 'generates XML file' do
        generator = described_class.new('test', config)
        result = generator.generate
        expect(result).to be true
        expect(File.exist?(File.join(temp_dir, 'src/main/res/layout/test.xml'))).to be true
      end
    end

    context 'with missing layout' do
      it 'returns false' do
        generator = described_class.new('nonexistent', config)
        result = generator.generate
        expect(result).to be false
      end
    end
  end
end
