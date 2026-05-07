# frozen_string_literal: true

require 'compose/generators/cell_generator'
require 'core/config_manager'
require 'fileutils'

RSpec.describe KjuiTools::Compose::Generators::CellGenerator do
  let(:temp_dir) { Dir.mktmpdir('cell_generator_test') }

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
      generator = described_class.new('TestCell')
      expect(generator).to be_a(described_class)
    end

    it 'accepts options' do
      generator = described_class.new('TestCell', root: true)
      expect(generator).to be_a(described_class)
    end
  end

  describe '#generate' do
    it 'creates JSON layout file' do
      generator = described_class.new('ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/product_cell.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'creates main view file' do
      generator = described_class.new('ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/product_cell/ProductCellView.kt')
      expect(File.exist?(view_path)).to be true
    end

    it 'creates generated view file' do
      generator = described_class.new('ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      generated_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/product_cell/ProductCellGeneratedView.kt')
      expect(File.exist?(generated_path)).to be true
    end

    it 'creates data file' do
      generator = described_class.new('ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      data_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/data/ProductCellData.kt')
      expect(File.exist?(data_path)).to be true
    end

    it 'creates viewmodel file' do
      generator = described_class.new('ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      viewmodel_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/viewmodels/ProductCellViewModel.kt')
      expect(File.exist?(viewmodel_path)).to be true
    end

    it 'handles subdirectory paths' do
      generator = described_class.new('products/ItemCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/products/item_cell.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'converts PascalCase subdirectory to snake_case for JSON path' do
      generator = described_class.new('MyProducts/ProductCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      # JSON uses snake_case path
      json_path = File.join(temp_dir, 'src/main/assets/Layouts/my_products/product_cell.json')
      expect(File.exist?(json_path)).to be true

      # View keeps original casing for package
      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/MyProducts/product_cell/ProductCellView.kt')
      expect(File.exist?(view_path)).to be true
    end

    it 'handles deeply nested paths with snake_case JSON directory' do
      generator = described_class.new('Home/Footer/ItemCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      # JSON uses snake_case nested path
      json_path = File.join(temp_dir, 'src/main/assets/Layouts/home/footer/item_cell.json')
      expect(File.exist?(json_path)).to be true

      # View uses original casing
      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/Home/Footer/item_cell/ItemCellView.kt')
      expect(File.exist?(view_path)).to be true
    end

    it 'converts PascalCase names to snake_case for files' do
      generator = described_class.new('MyAwesomeCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/my_awesome_cell.json')
      expect(File.exist?(json_path)).to be true
    end

    it 'does not overwrite existing JSON file' do
      json_path = File.join(temp_dir, 'src/main/assets/Layouts/existing_cell.json')
      FileUtils.mkdir_p(File.dirname(json_path))
      File.write(json_path, '{"type": "CustomCell"}')

      generator = described_class.new('ExistingCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      content = File.read(json_path)
      expect(content).to include('CustomCell')
    end
  end

  describe 'generated JSON content' do
    it 'includes View as root with horizontal orientation' do
      generator = described_class.new('TestCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/test_cell.json')
      content = JSON.parse(File.read(json_path))
      expect(content['type']).to eq('View')
      expect(content['orientation']).to eq('horizontal')
    end

    it 'includes child components' do
      generator = described_class.new('TestCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      json_path = File.join(temp_dir, 'src/main/assets/Layouts/test_cell.json')
      content = JSON.parse(File.read(json_path))
      expect(content).to have_key('child')
    end
  end

  describe 'generated Kotlin files' do
    it 'includes correct package in main view' do
      generator = described_class.new('TestCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      view_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/views/test_cell/TestCellView.kt')
      content = File.read(view_path)
      expect(content).to include('package com.example.app.views.test_cell')
    end

    it 'includes item parameter in cell data' do
      generator = described_class.new('TestCell')
      expect { generator.generate }.to output(/Generated Collection Cell/).to_stdout

      data_path = File.join(temp_dir, 'src/main/kotlin/com/example/app/data/TestCellData.kt')
      content = File.read(data_path)
      expect(content).to include('data class TestCellData')
    end
  end
end
