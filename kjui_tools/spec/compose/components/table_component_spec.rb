# frozen_string_literal: true

require 'compose/components/table_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::TableComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates LazyColumn for table' do
      json_data = { 'type' => 'Table' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('LazyColumn(')
      expect(required_imports).to include(:lazy_column)
    end

    it 'handles bind attribute for items' do
      json_data = { 'type' => 'Table', 'bind' => '@{items}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('items(data.items)')
    end

    it 'handles items attribute' do
      json_data = { 'type' => 'Table', 'items' => '@{tableItems}' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('items(data.tableItems)')
    end

    it 'defaults to emptyList when no binding' do
      json_data = { 'type' => 'Table' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('items(emptyList())')
    end

    it 'applies content padding as array' do
      json_data = { 'type' => 'Table', 'contentPadding' => [16, 8, 16, 8] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues')
    end

    it 'applies content padding as number' do
      json_data = { 'type' => 'Table', 'contentPadding' => 16 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentPadding = PaddingValues(16.dp)')
    end

    it 'applies row spacing' do
      json_data = { 'type' => 'Table', 'rowSpacing' => 8 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Arrangement.spacedBy(8.dp)')
      expect(required_imports).to include(:arrangement)
    end

    it 'applies spacing attribute' do
      json_data = { 'type' => 'Table', 'spacing' => 12 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Arrangement.spacedBy(12.dp)')
    end

    it 'generates header row' do
      json_data = { 'type' => 'Table', 'header' => ['Name', 'Age', 'City'] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('item {')
      expect(result).to include('Row(')
      expect(result).to include('FontWeight.Bold')
      expect(result).to include('Name')
      expect(result).to include('Age')
      expect(result).to include('City')
    end

    it 'generates header with divider by default' do
      json_data = { 'type' => 'Table', 'header' => ['Column1'] }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Divider(')
    end

    it 'skips header divider when separatorStyle is none' do
      json_data = { 'type' => 'Table', 'header' => ['Column1'], 'separatorStyle' => 'none' }
      result = described_class.generate(json_data, 0, required_imports)
      # Should not have divider after header
      header_section = result.split('items(').first
      expect(header_section.scan('Divider(').count).to eq(0)
    end

    it 'generates custom cell' do
      json_data = { 'type' => 'Table', 'cell' => { 'type' => 'Text' } }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Custom cell rendering')
    end

    it 'generates default row' do
      json_data = { 'type' => 'Table' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Row(')
      expect(result).to include('clickable')
      expect(result).to include('item.toString()')
    end

    it 'applies custom row height' do
      json_data = { 'type' => 'Table', 'rowHeight' => 80 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.height(80.dp)')
    end

    it 'uses default row height when not specified' do
      json_data = { 'type' => 'Table' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.height(60.dp)')
    end

    it 'generates row separator' do
      json_data = { 'type' => 'Table' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Divider(')
      expect(result).to include('Color.LightGray')
    end

    it 'skips row separator when separatorStyle is none' do
      json_data = { 'type' => 'Table', 'separatorStyle' => 'none' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('Divider(')
    end

    it 'applies separator inset with hash' do
      json_data = { 'type' => 'Table', 'separatorInset' => { 'left' => 16 } }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier.padding(start = 16.dp)')
    end

    it 'applies separator inset with start' do
      json_data = { 'type' => 'Table', 'separatorInset' => { 'start' => 20 } }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Modifier.padding(start = 20.dp)')
    end

    it 'handles non-array header' do
      json_data = { 'type' => 'Table', 'header' => 'Single Header' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text(text = "Header"')
    end
  end

  describe 'private methods' do
    describe '.indent' do
      it 'returns text unchanged for level 0' do
        result = described_class.send(:indent, 'text', 0)
        expect(result).to eq('text')
      end

      it 'adds indentation for level 1' do
        result = described_class.send(:indent, 'text', 1)
        expect(result).to eq('    text')
      end

      it 'preserves empty lines' do
        result = described_class.send(:indent, "line1\n\nline2", 1)
        expect(result).to eq("    line1\n\n    line2")
      end
    end
  end
end
