# frozen_string_literal: true

require 'compose/generators/view_generator'
require 'core/config_manager'
require 'fileutils'

RSpec.describe KjuiTools::Compose::Generators::ViewGenerator do
  let(:temp_dir) { Dir.mktmpdir('view_generator_test') }

  let(:config) do
    {
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts',
      'view_directory' => 'kotlin/com/example/app/views',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'data_directory' => 'kotlin/com/example/app/data',
      'package_name' => 'com.example.app',
      'project_path' => temp_dir
    }
  end

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates instance with name' do
      generator = described_class.new('TestView')
      expect(generator).to be_a(described_class)
    end

    it 'accepts options' do
      generator = described_class.new('TestView', root: true)
      expect(generator).to be_a(described_class)
    end
  end

  describe '#generate' do
    it 'creates JSON layout file' do
      generator = described_class.new('HomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/home_view.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'creates main view file' do
      generator = described_class.new('HomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/home_view/HomeViewView.kt')
      expect(File.exist?(view_path)).to be true
    end

    it 'creates generated view file' do
      generator = described_class.new('HomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      generated_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/home_view/HomeViewGeneratedView.kt')
      expect(File.exist?(generated_path)).to be true
    end

    it 'creates data file' do
      generator = described_class.new('HomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      data_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/data/HomeViewData.kt')
      expect(File.exist?(data_path)).to be true
    end

    it 'creates viewmodel file' do
      generator = described_class.new('HomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      viewmodel_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/viewmodels/HomeViewViewModel.kt')
      expect(File.exist?(viewmodel_path)).to be true
    end

    it 'handles subdirectory paths' do
      generator = described_class.new('settings/ProfileView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/settings/profile_view.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'converts PascalCase names to snake_case' do
      generator = described_class.new('MyAwesomeView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/my_awesome_view.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'does not overwrite existing JSON file' do
      json_path = File.join(temp_dir, 'src/main/assets/Layouts/existing_view.json')
      FileUtils.mkdir_p(File.dirname(json_path))
      File.write(json_path, '{"type": "CustomContent"}')

      generator = described_class.new('ExistingView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      content = File.read(json_path)
      expect(content).to include('CustomContent')
    end
  end

  describe 'generated JSON content' do
    it 'includes SafeAreaView as root' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/test_view.json')
      content = JSON.parse(File.read(json_path))
      expect(content['type']).to eq('SafeAreaView')
    end

    it 'includes data definition' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/test_view.json')
      content = JSON.parse(File.read(json_path))
      expect(content['data']).to be_an(Array)
      expect(content['data'].first['name']).to eq('title')
    end

    it 'includes button component' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/test_view.json')
      content = JSON.parse(File.read(json_path))
      buttons = find_components_by_type(content, 'Button')
      expect(buttons).not_to be_empty
    end
  end

  describe 'generated Kotlin files' do
    it 'includes correct package in main view' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/test_view/TestViewView.kt')
      content = File.read(view_path)
      expect(content).to include('package com.example.app.views.test_view')
    end

    it 'includes ViewModel import' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/test_view/TestViewView.kt')
      content = File.read(view_path)
      expect(content).to include('import com.example.app.viewmodels.TestViewViewModel')
    end

    it 'includes data class in data file' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      data_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/data/TestViewData.kt')
      content = File.read(data_path)
      expect(content).to include('data class TestViewData')
    end

    it 'includes StateFlow in viewmodel' do
      generator = described_class.new('TestView')
      expect { generator.generate }.to output(/Generated Compose view/).to_stdout

      viewmodel_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/viewmodels/TestViewViewModel.kt')
      content = File.read(viewmodel_path)
      expect(content).to include('StateFlow')
      expect(content).to include('MutableStateFlow')
    end
  end

  private

  def find_components_by_type(json, type)
    results = []
    results << json if json['type'] == type

    children = json['child'] || json['children'] || []
    children = [children] unless children.is_a?(Array)
    children.each do |child|
      results.concat(find_components_by_type(child, type)) if child.is_a?(Hash)
    end

    results
  end
end
