# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'

RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter, 'responsive support' do
  let(:converter) { described_class.new }
  let(:temp_dir) { File.realpath(Dir.mktmpdir('converter_responsive_test')) }

  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(temp_dir)
  end

  describe '#convert_json_to_view with responsive' do
    let(:json_file) { File.join(temp_dir, 'responsive_test.json') }

    it 'returns responsive_functions as 5th element' do
      json_content = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      result = converter.convert_json_to_view(json_file)
      expect(result.length).to eq(5)

      code, _actions, state_vars, _root_children, responsive_funcs = result
      expect(responsive_funcs).to be_an(Array)
      expect(responsive_funcs.length).to eq(1)
      expect(responsive_funcs.first).to include('responsive0')
    end

    it 'adds @Environment variables to state_variables' do
      json_content = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal' }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Test' }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      _code, _actions, state_vars, _root_children, _responsive_funcs = converter.convert_json_to_view(json_file)

      expect(state_vars).to include(a_string_matching(/horizontalSizeClass/))
      expect(state_vars).to include(a_string_matching(/verticalSizeClass/))
    end

    it 'does not add @Environment variables when no responsive' do
      json_content = {
        'type' => 'View',
        'orientation' => 'vertical',
        'child' => [
          { 'type' => 'Label', 'text' => 'Test' }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      _code, _actions, state_vars, _root_children, responsive_funcs = converter.convert_json_to_view(json_file)

      expect(state_vars).not_to include(a_string_matching(/horizontalSizeClass/))
      expect(responsive_funcs).to be_empty
    end

    it 'generates correct body code with responsive function call' do
      json_content = {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      code, _actions, _state_vars, _root_children, _responsive_funcs = converter.convert_json_to_view(json_file)

      expect(code).to include('responsive0 {')
    end

    it 'handles nested responsive components with unique names' do
      json_content = {
        'type' => 'View',
        'orientation' => 'vertical',
        'child' => [
          {
            'type' => 'View',
            'orientation' => 'horizontal',
            'responsive' => { 'regular' => { 'spacing' => 24 } },
            'child' => [{ 'type' => 'Label', 'text' => 'A' }]
          },
          {
            'type' => 'View',
            'orientation' => 'vertical',
            'responsive' => { 'landscape' => { 'spacing' => 16 } },
            'child' => [{ 'type' => 'Label', 'text' => 'B' }]
          }
        ]
      }
      File.write(json_file, JSON.generate(json_content))

      _code, _actions, _state_vars, _root_children, responsive_funcs = converter.convert_json_to_view(json_file)

      expect(responsive_funcs.length).to eq(2)
      expect(responsive_funcs[0]).to include('responsive0')
      expect(responsive_funcs[1]).to include('responsive1')
    end
  end
end
