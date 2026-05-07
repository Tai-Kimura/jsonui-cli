# frozen_string_literal: true

require 'swiftui/views/include_converter'

RSpec.describe SjuiTools::SwiftUI::Views::IncludeConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'without include property' do
      let(:component) { { 'type' => 'Include' } }

      it 'raises error' do
        converter = described_class.new(component)
        expect { converter.convert }.to raise_error(/must have 'include' property/)
      end
    end

    context 'with simple include' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'header_section'
        }
      end

      it 'generates view with correct name' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('HeaderSectionView()')
      end
    end

    context 'with nested path include' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'components/footer_section'
        }
      end

      it 'uses last path component for view name' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('FooterSectionView()')
      end
    end

    context 'with static data' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'item_card',
          'data' => {
            'title' => 'Test Title',
            'count' => 5
          }
        }
      end

      it 'generates view with data dictionary' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ItemCardView(data:')
        expect(code).to include('"title": "Test Title"')
        expect(code).to include('"count": 5')
      end
    end

    context 'with reactive data' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'user_profile',
          'data' => {
            'name' => '@{userName}'
          }
        }
      end

      it 'generates reactive view with id' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('UserProfileView(data:')
        expect(code).to include('data.userName')
        expect(code).to include('.id(')
      end
    end

    context 'with shared_data' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'shared_view',
          'shared_data' => {
            'theme' => 'dark'
          }
        }
      end

      it 'includes shared_data in output' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('"theme": "dark"')
      end
    end

    context 'with shared_data and data merge' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'merge_test',
          'shared_data' => {
            'base' => 'shared_value',
            'override' => 'shared_override'
          },
          'data' => {
            'override' => 'data_value',
            'extra' => 'data_extra'
          }
        }
      end

      it 'merges data over shared_data' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('"base": "shared_value"')
        expect(code).to include('"override": "data_value"')
        expect(code).to include('"extra": "data_extra"')
      end
    end

    context 'with boolean value' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'bool_test',
          'data' => {
            'enabled' => true,
            'disabled' => false
          }
        }
      end

      it 'formats boolean values' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('"enabled": true')
        expect(code).to include('"disabled": false')
      end
    end

    context 'with nil value' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'nil_test',
          'data' => {
            'optional' => nil
          }
        }
      end

      it 'formats nil as nil' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('"optional": nil')
      end
    end

    context 'with array value' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'array_test',
          'data' => {
            'items' => ['a', 'b', 'c']
          }
        }
      end

      it 'formats array values' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('"items":')
        expect(code).to include('"a"')
        expect(code).to include('"b"')
      end
    end

    context 'with this. prefix in reactive data' do
      let(:component) do
        {
          'type' => 'Include',
          'include' => 'this_test',
          'data' => {
            'value' => '@{this.someValue}'
          }
        }
      end

      it 'converts this. to data.' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.someValue')
      end
    end
  end
end
