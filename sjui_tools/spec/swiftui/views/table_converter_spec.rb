# frozen_string_literal: true

require 'swiftui/views/table_converter'

RSpec.describe SjuiTools::SwiftUI::Views::TableConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic table' do
      let(:component) { { 'type' => 'Table' } }

      it 'generates List with ForEach' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('List {')
        expect(code).to include('ForEach')
      end
    end

    context 'with cell layout' do
      let(:component) do
        {
          'type' => 'Table',
          'cell_layout' => 'layouts/item_cell'
        }
      end

      it 'adds comment for cell layout' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('// Cell layout: layouts/item_cell')
      end
    end

    context 'with binding data' do
      let(:component) do
        {
          'type' => 'Table',
          'cell_layout' => 'item_row',
          'binding' => {
            'data' => '@{users}'
          }
        }
      end

      it 'generates ForEach with data binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ForEach(users)')
        expect(code).to include('ItemRowView(item: item)')
      end
    end

    context 'with hideSeparator' do
      let(:component) do
        {
          'type' => 'Table',
          'hideSeparator' => true
        }
      end

      it 'adds list style and row separator hidden' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.listStyle(.plain)')
        expect(code).to include('.listRowSeparator(.hidden)')
      end
    end

    context 'with grouped list style' do
      let(:component) do
        {
          'type' => 'Table',
          'listStyle' => 'grouped'
        }
      end

      it 'applies grouped style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.listStyle(.grouped)')
      end
    end

    context 'with insetGrouped list style' do
      let(:component) do
        {
          'type' => 'Table',
          'listStyle' => 'insetGrouped'
        }
      end

      it 'applies insetGrouped style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.listStyle(.insetGrouped)')
      end
    end

    context 'with sidebar list style' do
      let(:component) do
        {
          'type' => 'Table',
          'listStyle' => 'sidebar'
        }
      end

      it 'applies sidebar style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.listStyle(.sidebar)')
      end
    end

    context 'with unknown list style' do
      let(:component) do
        {
          'type' => 'Table',
          'listStyle' => 'unknown'
        }
      end

      it 'falls back to plain style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.listStyle(.plain)')
      end
    end

    context 'with custom id' do
      let(:component) do
        {
          'type' => 'Table',
          'id' => 'userTable'
        }
      end

      it 'generates valid code' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('List {')
      end
    end
  end
end
