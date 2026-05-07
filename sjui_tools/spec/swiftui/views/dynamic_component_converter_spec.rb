# frozen_string_literal: true

require 'swiftui/views/dynamic_component_converter'

RSpec.describe SjuiTools::SwiftUI::Views::DynamicComponentConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'without jsonFile' do
      let(:component) { { 'type' => 'DynamicComponent' } }

      it 'generates error Text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("DynamicComponent requires jsonFile")')
        expect(code).to include('.foregroundColor(.red)')
      end
    end

    context 'with jsonFile' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'jsonFile' => 'child_layout'
        }
      end

      it 'generates DynamicView with jsonName' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('DynamicView(jsonName: "child_layout")')
      end
    end

    context 'with json_file (snake_case)' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'json_file' => 'snake_case_layout'
        }
      end

      it 'generates DynamicView with jsonName' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('DynamicView(jsonName: "snake_case_layout")')
      end
    end

    context 'with viewId' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'jsonFile' => 'my_layout',
          'viewId' => 'unique_view'
        }
      end

      it 'generates DynamicView with viewId' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('DynamicView(jsonName: "my_layout", viewId: "unique_view")')
      end
    end

    context 'with id (as viewId)' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'jsonFile' => 'layout',
          'id' => 'component_id'
        }
      end

      it 'uses id as viewId' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('viewId: "component_id"')
      end
    end

    context 'with common modifiers' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'jsonFile' => 'my_layout',
          'cornerRadius' => 8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end

    context 'with empty jsonFile' do
      let(:component) do
        {
          'type' => 'DynamicComponent',
          'jsonFile' => ''
        }
      end

      it 'generates error Text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("DynamicComponent requires jsonFile")')
      end
    end
  end
end
