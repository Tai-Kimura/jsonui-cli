# frozen_string_literal: true

require 'swiftui/views/child_rendering_helper'
require 'swiftui/converter_factory'
require 'swiftui/action_manager'

RSpec.describe SjuiTools::SwiftUI::Views::ChildRenderingHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::ChildRenderingHelper

      attr_accessor :component, :indent_level, :action_manager, :converter_factory, :view_registry
      attr_reader :generated_code, :state_variables

      def initialize
        @generated_code = []
        @state_variables = []
        @indent_level = 0
      end

      def add_line(line)
        @generated_code << line
      end

      def apply_visibility_wrapper(child)
        nil  # Default: no visibility wrapper
      end

      def apply_zstack_positioning(child, index)
        # Default positioning logic
      end

      def calculate_alignment_needs(child, orientation)
        {
          needs_wrapper: false,
          wrapper_alignment: nil,
          needs_spacer_before: false,
          needs_spacer_after: false
        }
      end

      def remove_alignment_properties(child, orientation, needs_wrapper)
        child.dup
      end

      def wrap_child_for_alignment(child_lines, orientation, needs_wrapper, wrapper_alignment)
        child_lines.each { |line| add_line line }
      end
    end
  end

  let(:helper) { helper_class.new }
  let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
  let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
  let(:action_manager) { SjuiTools::SwiftUI::ActionManager.new }

  before do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    helper.converter_factory = converter_factory
    helper.action_manager = action_manager
    helper.view_registry = nil
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#render_child_element' do
    context 'with ZStack orientation (nil)' do
      it 'wraps child in Group' do
        child = { 'type' => 'Label', 'text' => 'Test' }

        helper.render_child_element(child, nil, 0)

        expect(helper.generated_code.first).to eq('Group {')
        expect(helper.generated_code.last).to eq('}')
      end

      it 'applies zstack positioning' do
        child = { 'type' => 'Label', 'text' => 'Test' }

        # Override apply_zstack_positioning to track calls
        positioning_called = false
        helper.define_singleton_method(:apply_zstack_positioning) do |c, i|
          positioning_called = true
        end

        helper.render_child_element(child, nil, 1)

        expect(positioning_called).to be true
      end
    end

    context 'with HStack orientation' do
      it 'renders child without Group wrapper' do
        child = { 'type' => 'Label', 'text' => 'Horizontal' }

        helper.render_child_element(child, :horizontal, 0)

        expect(helper.generated_code).not_to include('Group {')
      end
    end

    context 'with VStack orientation' do
      it 'renders child without Group wrapper' do
        child = { 'type' => 'Label', 'text' => 'Vertical' }

        helper.render_child_element(child, :vertical, 0)

        expect(helper.generated_code).not_to include('Group {')
      end
    end

    context 'with visibility wrapper' do
      it 'propagates state variables from visibility wrapper' do
        child = { 'type' => 'Label', 'text' => 'Test', 'visibility' => '${isVisible}' }

        # Create a mock converter with state variables
        mock_converter = double('converter')
        allow(mock_converter).to receive(:respond_to?).with(:state_variables).and_return(true)
        allow(mock_converter).to receive(:state_variables).and_return(['@State private var isVisible = false'])

        helper.define_singleton_method(:apply_visibility_wrapper) do |c|
          mock_converter
        end

        helper.render_child_element(child, :horizontal, 0)

        expect(helper.state_variables).to include('@State private var isVisible = false')
      end
    end
  end

  describe '#render_child_with_alignment' do
    context 'with spacer before' do
      it 'adds Spacer before child' do
        child = { 'type' => 'Label', 'text' => 'After Spacer' }

        helper.define_singleton_method(:calculate_alignment_needs) do |c, o|
          {
            needs_wrapper: false,
            wrapper_alignment: nil,
            needs_spacer_before: true,
            needs_spacer_after: false
          }
        end

        helper.send(:render_child_with_alignment, child, :horizontal)

        expect(helper.generated_code.first).to eq('Spacer()')
      end
    end

    context 'with spacer after' do
      it 'adds Spacer after child' do
        child = { 'type' => 'Label', 'text' => 'Before Spacer' }

        helper.define_singleton_method(:calculate_alignment_needs) do |c, o|
          {
            needs_wrapper: false,
            wrapper_alignment: nil,
            needs_spacer_before: false,
            needs_spacer_after: true
          }
        end

        helper.send(:render_child_with_alignment, child, :horizontal)

        expect(helper.generated_code.last).to eq('Spacer()')
      end
    end

    context 'with spacers on both sides' do
      it 'adds Spacers before and after' do
        child = { 'type' => 'Label', 'text' => 'Centered' }

        helper.define_singleton_method(:calculate_alignment_needs) do |c, o|
          {
            needs_wrapper: false,
            wrapper_alignment: nil,
            needs_spacer_before: true,
            needs_spacer_after: true
          }
        end

        helper.send(:render_child_with_alignment, child, :horizontal)

        spacer_indices = helper.generated_code.each_index.select { |i| helper.generated_code[i] == 'Spacer()' }
        expect(spacer_indices.size).to eq(2)
        expect(spacer_indices.first).to eq(0)
        expect(spacer_indices.last).to eq(helper.generated_code.size - 1)
      end
    end

    it 'propagates state variables from child converter' do
      child = { 'type' => 'Toggle', 'text' => 'Enable', 'binding' => 'isEnabled' }

      helper.send(:render_child_with_alignment, child, :vertical)

      # The converter may generate state variables
      # We just verify that the method completes without error
      expect(helper.generated_code).not_to be_empty
    end
  end
end
