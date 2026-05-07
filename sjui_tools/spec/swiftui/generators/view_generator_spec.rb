# frozen_string_literal: true

require 'swiftui/generators/view_generator'
require 'json'
require 'fileutils'

RSpec.describe SjuiTools::SwiftUI::Generators::ViewGenerator do
  let(:temp_dir) { File.realpath(Dir.mktmpdir('view_generator_test')) }

  before do
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(SjuiTools::Core::Logger).to receive(:info)
    allow(SjuiTools::Core::Logger).to receive(:debug)
    allow(SjuiTools::Core::Logger).to receive(:warn)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'stores name and options' do
      generator = described_class.new('test_view', root: true)
      expect(generator.instance_variable_get(:@name)).to eq('test_view')
      expect(generator.instance_variable_get(:@options)).to eq({ root: true })
    end
  end

  describe '#build_command_string' do
    it 'builds basic command' do
      generator = described_class.new('my_view')
      result = generator.build_command_string('my_view', {})
      expect(result).to eq('sjui g view my_view')
    end

    it 'adds --root flag when specified' do
      generator = described_class.new('my_view', root: true)
      result = generator.build_command_string('my_view', { root: true })
      expect(result).to eq('sjui g view my_view --root')
    end
  end

  describe '#generate' do
    it 'creates directories' do
      generator = described_class.new('test')
      generator.generate

      expect(Dir.exist?(File.join(temp_dir, 'Layouts'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'View', 'Test'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'ViewModel'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'Data'))).to be true
    end

    it 'creates JSON file' do
      generator = described_class.new('sample')
      generator.generate

      json_file = File.join(temp_dir, 'Layouts', 'sample.json')
      expect(File.exist?(json_file)).to be true

      content = JSON.parse(File.read(json_file))
      expect(content['type']).to eq('View')
    end

    it 'creates main view file' do
      generator = described_class.new('sample')
      generator.generate

      main_view_file = File.join(temp_dir, 'View', 'Sample', 'SampleView.swift')
      expect(File.exist?(main_view_file)).to be true

      content = File.read(main_view_file)
      expect(content).to include('struct SampleView: View')
      expect(content).to include('@StateObject private var viewModel: SampleViewModel')
    end

    it 'creates generated view file' do
      generator = described_class.new('sample')
      generator.generate

      generated_file = File.join(temp_dir, 'View', 'Sample', 'SampleGeneratedView.swift')
      expect(File.exist?(generated_file)).to be true

      content = File.read(generated_file)
      expect(content).to include('struct SampleGeneratedView: View')
      expect(content).to include('@SwiftUI.Binding var data: SampleData')
    end

    it 'creates data file' do
      generator = described_class.new('sample')
      generator.generate

      data_file = File.join(temp_dir, 'Data', 'SampleData.swift')
      expect(File.exist?(data_file)).to be true

      content = File.read(data_file)
      expect(content).to include('struct SampleData')
      expect(content).to include('var title: String')
    end

    it 'creates viewmodel file' do
      generator = described_class.new('sample')
      generator.generate

      viewmodel_file = File.join(temp_dir, 'ViewModel', 'SampleViewModel.swift')
      expect(File.exist?(viewmodel_file)).to be true

      content = File.read(viewmodel_file)
      expect(content).to include('class SampleViewModel: ObservableObject')
      expect(content).to include('@Published var data = SampleData()')
    end

    context 'with subdirectory' do
      it 'creates files in subdirectory' do
        generator = described_class.new('settings/profile')
        generator.generate

        json_file = File.join(temp_dir, 'Layouts', 'settings', 'profile.json')
        expect(File.exist?(json_file)).to be true

        view_file = File.join(temp_dir, 'View', 'settings', 'Profile', 'ProfileView.swift')
        expect(File.exist?(view_file)).to be true
      end
    end

    context 'when file already exists' do
      before do
        FileUtils.mkdir_p(File.join(temp_dir, 'Layouts'))
        File.write(File.join(temp_dir, 'Layouts', 'existing.json'), '{}')
      end

      it 'does not overwrite existing files' do
        generator = described_class.new('existing')
        generator.generate

        content = File.read(File.join(temp_dir, 'Layouts', 'existing.json'))
        expect(content).to eq('{}')
      end
    end
  end

  describe '#to_pascal_case (private)' do
    let(:generator) { described_class.new('test') }

    it 'converts snake_case to PascalCase' do
      result = generator.send(:to_pascal_case, 'my_view')
      expect(result).to eq('MyView')
    end

    it 'converts camelCase to PascalCase' do
      result = generator.send(:to_pascal_case, 'myView')
      expect(result).to eq('MyView')
    end

    it 'handles already PascalCase' do
      result = generator.send(:to_pascal_case, 'MyView')
      expect(result).to eq('MyView')
    end

    it 'handles kebab-case' do
      result = generator.send(:to_pascal_case, 'my-view')
      expect(result).to eq('MyView')
    end
  end

  describe '#to_snake_case (private)' do
    let(:generator) { described_class.new('test') }

    it 'converts PascalCase to snake_case' do
      result = generator.send(:to_snake_case, 'MyView')
      expect(result).to eq('my_view')
    end

    it 'converts camelCase to snake_case' do
      result = generator.send(:to_snake_case, 'myView')
      expect(result).to eq('my_view')
    end

    it 'handles consecutive capitals' do
      result = generator.send(:to_snake_case, 'MyAPIView')
      expect(result).to eq('my_api_view')
    end
  end
end
