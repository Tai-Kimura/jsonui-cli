# frozen_string_literal: true

require 'swiftui/views/progress_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ProgressConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic progress' do
      let(:component) do
        {
          'type' => 'Progress',
          'progress' => 0.5
        }
      end

      it 'generates ProgressView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ProgressView(')
        expect(code).to include('value:')
      end
    end

    context 'with binding progress' do
      let(:component) do
        {
          'type' => 'Progress',
          'progress' => '@{downloadProgress}'
        }
      end

      it 'uses viewModel.data binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.downloadProgress')
      end
    end

    context 'with progressTintColor' do
      let(:component) do
        {
          'type' => 'Progress',
          'progress' => 0.7,
          'progressTintColor' => '#007AFF'
        }
      end

      it 'adds tint modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.tint(')
      end
    end

    context 'with trackTintColor' do
      let(:component) do
        {
          'type' => 'Progress',
          'progress' => 0.3,
          'trackTintColor' => '#E0E0E0'
        }
      end

      it 'adds background modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
      end
    end

    context 'with id' do
      let(:component) do
        {
          'type' => 'Progress',
          'id' => 'uploadProgress',
          'progress' => 0.0
        }
      end

      it 'creates state variable with id' do
        converter = described_class.new(component)
        converter.convert

        expect(converter.state_variables).not_to be_empty
        expect(converter.state_variables.first).to include('uploadProgressValue')
      end
    end

    context 'with default progress value' do
      let(:component) do
        {
          'type' => 'Progress'
        }
      end

      it 'uses default 0.5 progress' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('ProgressView(')
      end
    end
  end
end
