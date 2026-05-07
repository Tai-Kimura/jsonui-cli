# frozen_string_literal: true

require 'swiftui/views/visibility_helper'

RSpec.describe SjuiTools::SwiftUI::Views::VisibilityHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::VisibilityHelper

      attr_accessor :converter_factory, :action_manager, :view_registry, :indent_level
      attr_reader :generated_code

      def initialize
        @generated_code = []
        @indent_level = 0
      end

      def add_line(line)
        @generated_code << line
      end

      def indent
        @indent_level += 1
        yield
        @indent_level -= 1
      end

      def to_camel_case(str)
        str.gsub(/_([a-z])/) { Regexp.last_match(1).upcase }
      end
    end
  end

  let(:mock_converter) do
    double('Converter',
           convert: "Text(\"Hello\")",
           state_variables: [])
  end

  let(:mock_factory) do
    double('ConverterFactory',
           create_converter: mock_converter)
  end

  describe '#apply_visibility_wrapper' do
    let(:helper) do
      h = helper_class.new
      h.converter_factory = mock_factory
      h.action_manager = nil
      h.view_registry = nil
      h
    end

    context 'with no visibility' do
      it 'returns nil' do
        child = { 'type' => 'View' }
        result = helper.apply_visibility_wrapper(child)

        expect(result).to be_nil
        expect(helper.generated_code).to be_empty
      end
    end

    context 'with binding visibility' do
      it 'wraps with VisibilityWrapper using binding variable' do
        child = { 'type' => 'Label', 'visibility' => '@{is_visible}' }
        helper.apply_visibility_wrapper(child)

        expect(helper.generated_code).to include('VisibilityWrapper(data.isVisible) {')
        expect(helper.generated_code).to include('}')
      end
    end

    context 'with string visibility' do
      it 'wraps with VisibilityWrapper using quoted string' do
        child = { 'type' => 'Label', 'visibility' => 'visible' }
        helper.apply_visibility_wrapper(child)

        expect(helper.generated_code).to include('VisibilityWrapper("visible") {')
      end
    end

    context 'returns converter for state propagation' do
      it 'returns the child converter' do
        child = { 'type' => 'Label', 'visibility' => '@{show}' }
        result = helper.apply_visibility_wrapper(child)

        expect(result).to eq(mock_converter)
      end
    end
  end
end
