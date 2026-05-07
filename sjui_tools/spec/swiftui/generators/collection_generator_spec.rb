# frozen_string_literal: true

require 'swiftui/generators/collection_generator'
require 'fileutils'
require 'tmpdir'

RSpec.describe SjuiTools::SwiftUI::Generators::CollectionGenerator do
  let(:temp_dir) { Dir.mktmpdir('collection_generator_test') }

  before do
    # Mock ProjectFinder to use temp directory
    allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(temp_dir)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'converts name to snake_case and PascalCase' do
      generator = described_class.new('my_item')
      expect(generator.instance_variable_get(:@snake_name)).to eq('my_item')
      expect(generator.instance_variable_get(:@pascal_name)).to eq('MyItem')
    end

    it 'handles already PascalCase names' do
      generator = described_class.new('TestCell')
      expect(generator.instance_variable_get(:@snake_name)).to eq('test_cell')
      expect(generator.instance_variable_get(:@pascal_name)).to eq('TestCell')
    end
  end

  describe '#generate' do
    let(:generator) { described_class.new('test_cell') }

    before do
      # Suppress puts output
      allow(generator).to receive(:puts)
    end

    it 'creates directories' do
      generator.generate

      expect(Dir.exist?(File.join(temp_dir, 'View', 'TestCell'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'Layouts'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'Data'))).to be true
      expect(Dir.exist?(File.join(temp_dir, 'ViewModel'))).to be true
    end

    it 'generates JSON layout file' do
      generator.generate

      json_path = File.join(temp_dir, 'Layouts', 'test_cell.json')
      expect(File.exist?(json_path)).to be true

      content = JSON.parse(File.read(json_path))
      expect(content['type']).to eq('View')
      expect(content['width']).to eq('matchParent')
    end

    it 'generates view file' do
      generator.generate

      view_path = File.join(temp_dir, 'View', 'TestCell', 'TestCellView.swift')
      expect(File.exist?(view_path)).to be true

      content = File.read(view_path)
      expect(content).to include('struct TestCellView: View')
      expect(content).to include('TestCellViewModel')
      expect(content).to include('TestCellGeneratedView')
    end

    it 'generates generated view file' do
      generator.generate

      path = File.join(temp_dir, 'View', 'TestCell', 'TestCellGeneratedView.swift')
      expect(File.exist?(path)).to be true

      content = File.read(path)
      expect(content).to include('struct TestCellGeneratedView: View')
      expect(content).to include('GENERATED_CODE_START')
      expect(content).to include('GENERATED_CODE_END')
    end

    it 'generates data file' do
      generator.generate

      path = File.join(temp_dir, 'Data', 'TestCellData.swift')
      expect(File.exist?(path)).to be true

      content = File.read(path)
      expect(content).to include('struct TestCellData')
      expect(content).to include('var title: String')
      expect(content).to include('var subtitle: String')
    end

    it 'generates view model file' do
      generator.generate

      path = File.join(temp_dir, 'ViewModel', 'TestCellViewModel.swift')
      expect(File.exist?(path)).to be true

      content = File.read(path)
      expect(content).to include('class TestCellViewModel: ObservableObject')
      expect(content).to include('func setData(_ itemData: Any)')
      expect(content).to include('jsonFileName = "test_cell"')
    end
  end

  describe 'name conversion helpers' do
    let(:generator) { described_class.new('Test') }

    describe '#to_snake_case' do
      it 'converts PascalCase to snake_case' do
        expect(generator.send(:to_snake_case, 'MyItemCell')).to eq('my_item_cell')
      end

      it 'handles consecutive capitals' do
        expect(generator.send(:to_snake_case, 'XMLParser')).to eq('xml_parser')
      end

      it 'handles dashes' do
        expect(generator.send(:to_snake_case, 'my-item')).to eq('my_item')
      end
    end

    describe '#to_pascal_case' do
      it 'converts snake_case to PascalCase' do
        expect(generator.send(:to_pascal_case, 'my_item_cell')).to eq('MyItemCell')
      end

      it 'handles dashes' do
        expect(generator.send(:to_pascal_case, 'my-item')).to eq('MyItem')
      end

      it 'handles slashes' do
        expect(generator.send(:to_pascal_case, 'my/item')).to eq('MyItem')
      end
    end
  end

  describe 'path helpers' do
    let(:generator) { described_class.new('my_cell') }

    it 'returns correct view directory' do
      expect(generator.send(:view_dir)).to eq(File.join(temp_dir, 'View', 'MyCell'))
    end

    it 'returns correct layouts directory' do
      expect(generator.send(:layouts_dir)).to eq(File.join(temp_dir, 'Layouts'))
    end

    it 'returns correct data directory' do
      expect(generator.send(:data_dir)).to eq(File.join(temp_dir, 'Data'))
    end

    it 'returns correct view model directory' do
      expect(generator.send(:view_model_dir)).to eq(File.join(temp_dir, 'ViewModel'))
    end

    it 'returns correct json path' do
      expect(generator.send(:json_path)).to eq(File.join(temp_dir, 'Layouts', 'my_cell.json'))
    end

    it 'returns correct view path' do
      expect(generator.send(:view_path)).to eq(File.join(temp_dir, 'View', 'MyCell', 'MyCellView.swift'))
    end

    it 'returns correct generated view path' do
      expect(generator.send(:generated_view_path)).to eq(File.join(temp_dir, 'View', 'MyCell', 'MyCellGeneratedView.swift'))
    end

    it 'returns correct data path' do
      expect(generator.send(:data_path)).to eq(File.join(temp_dir, 'Data', 'MyCellData.swift'))
    end

    it 'returns correct view model path' do
      expect(generator.send(:view_model_path)).to eq(File.join(temp_dir, 'ViewModel', 'MyCellViewModel.swift'))
    end
  end

  describe 'nested path support' do
    describe '#initialize with nested path' do
      it 'parses folder/cell format correctly' do
        generator = described_class.new('home/item_cell')
        expect(generator.instance_variable_get(:@view_folder_parts)).to eq(['Home'])
        expect(generator.instance_variable_get(:@cell_name)).to eq('item_cell')
        expect(generator.instance_variable_get(:@snake_name)).to eq('item_cell')
        expect(generator.instance_variable_get(:@pascal_name)).to eq('ItemCell')
      end

      it 'handles snake_case folder name' do
        generator = described_class.new('my_folder/my_cell')
        expect(generator.instance_variable_get(:@view_folder_parts)).to eq(['MyFolder'])
        expect(generator.instance_variable_get(:@cell_name)).to eq('my_cell')
      end

      it 'sets empty folder parts for non-nested path' do
        generator = described_class.new('simple_cell')
        expect(generator.instance_variable_get(:@view_folder_parts)).to eq([])
        expect(generator.instance_variable_get(:@cell_name)).to eq('simple_cell')
      end

      it 'handles deeply nested paths' do
        generator = described_class.new('home/footer/item_cell')
        expect(generator.instance_variable_get(:@view_folder_parts)).to eq(['Home', 'Footer'])
        expect(generator.instance_variable_get(:@cell_name)).to eq('item_cell')
        expect(generator.instance_variable_get(:@pascal_name)).to eq('ItemCell')
      end
    end

    describe 'path helpers with nested path' do
      let(:generator) { described_class.new('home/item_cell') }

      it 'returns nested view directory' do
        expect(generator.send(:view_dir)).to eq(File.join(temp_dir, 'View', 'Home', 'ItemCell'))
      end

      it 'returns correct json path in nested directory (snake_case)' do
        expect(generator.send(:json_path)).to eq(File.join(temp_dir, 'Layouts', 'home', 'item_cell.json'))
      end

      it 'returns correct view path in nested directory' do
        expect(generator.send(:view_path)).to eq(File.join(temp_dir, 'View', 'Home', 'ItemCell', 'ItemCellView.swift'))
      end

      it 'returns correct generated view path in nested directory' do
        expect(generator.send(:generated_view_path)).to eq(File.join(temp_dir, 'View', 'Home', 'ItemCell', 'ItemCellGeneratedView.swift'))
      end
    end

    describe '#generate with nested path' do
      let(:generator) { described_class.new('home/item_cell') }

      before do
        allow(generator).to receive(:puts)
      end

      it 'creates nested view directory structure' do
        generator.generate

        expect(Dir.exist?(File.join(temp_dir, 'View', 'Home', 'ItemCell'))).to be true
      end

      it 'generates files in nested directory' do
        generator.generate

        expect(File.exist?(File.join(temp_dir, 'View', 'Home', 'ItemCell', 'ItemCellView.swift'))).to be true
        expect(File.exist?(File.join(temp_dir, 'View', 'Home', 'ItemCell', 'ItemCellGeneratedView.swift'))).to be true
      end

      it 'generates JSON in nested layouts directory (snake_case)' do
        generator.generate

        expect(File.exist?(File.join(temp_dir, 'Layouts', 'home', 'item_cell.json'))).to be true
      end

      it 'generates view file with correct class names' do
        generator.generate

        view_path = File.join(temp_dir, 'View', 'Home', 'ItemCell', 'ItemCellView.swift')
        content = File.read(view_path)
        expect(content).to include('struct ItemCellView: View')
        expect(content).to include('ItemCellViewModel')
        expect(content).to include('ItemCellGeneratedView')
      end

      it 'generates view model with correct json reference' do
        generator.generate

        vm_path = File.join(temp_dir, 'ViewModel', 'ItemCellViewModel.swift')
        content = File.read(vm_path)
        expect(content).to include('jsonFileName = "item_cell"')
      end
    end

    describe '#generate with deeply nested path' do
      let(:generator) { described_class.new('home/footer/item_cell') }

      before do
        allow(generator).to receive(:puts)
      end

      it 'creates deeply nested view directory structure' do
        generator.generate

        expect(Dir.exist?(File.join(temp_dir, 'View', 'Home', 'Footer', 'ItemCell'))).to be true
      end

      it 'generates files in deeply nested directory' do
        generator.generate

        expect(File.exist?(File.join(temp_dir, 'View', 'Home', 'Footer', 'ItemCell', 'ItemCellView.swift'))).to be true
        expect(File.exist?(File.join(temp_dir, 'View', 'Home', 'Footer', 'ItemCell', 'ItemCellGeneratedView.swift'))).to be true
      end

      it 'generates JSON in deeply nested layouts directory (snake_case)' do
        generator.generate

        expect(File.exist?(File.join(temp_dir, 'Layouts', 'home', 'footer', 'item_cell.json'))).to be true
      end

      it 'returns correct view_dir path' do
        expect(generator.send(:view_dir)).to eq(File.join(temp_dir, 'View', 'Home', 'Footer', 'ItemCell'))
      end
    end
  end
end
