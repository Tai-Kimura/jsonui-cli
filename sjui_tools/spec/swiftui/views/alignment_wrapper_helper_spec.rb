# frozen_string_literal: true

require 'swiftui/views/alignment_wrapper_helper'

RSpec.describe SjuiTools::SwiftUI::Views::AlignmentWrapperHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::AlignmentWrapperHelper

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
    end
  end

  describe '#wrap_child_for_alignment' do
    let(:helper) { helper_class.new }
    let(:child_lines) { ['Text("Hello")'] }

    context 'with no wrapper needed' do
      it 'adds child lines directly' do
        helper.wrap_child_for_alignment(child_lines, 'horizontal', false, nil)

        expect(helper.generated_code).to eq(['Text("Hello")'])
      end
    end

    context 'with horizontal orientation and wrapper needed' do
      it 'wraps in VStack with frame alignment' do
        helper.wrap_child_for_alignment(child_lines, 'horizontal', true, '.top')

        expect(helper.generated_code).to include('VStack {')
        expect(helper.generated_code).to include('Text("Hello")')
        expect(helper.generated_code.last).to include('.frame(maxHeight: .infinity, alignment: .top)')
      end
    end

    context 'with vertical orientation and wrapper needed' do
      it 'wraps in HStack with frame alignment' do
        helper.wrap_child_for_alignment(child_lines, 'vertical', true, '.leading')

        expect(helper.generated_code).to include('HStack {')
        expect(helper.generated_code).to include('Text("Hello")')
        expect(helper.generated_code.last).to include('.frame(maxWidth: .infinity, alignment: .leading)')
      end
    end

    context 'with empty lines in child' do
      it 'filters out empty lines' do
        lines_with_empty = ['Text("Hello")', '', '  ']
        helper.wrap_child_for_alignment(lines_with_empty, 'horizontal', true, '.center')

        expect(helper.generated_code).to include('Text("Hello")')
        expect(helper.generated_code).not_to include('')
      end
    end
  end

  describe '#remove_alignment_properties' do
    let(:helper) { helper_class.new }

    context 'with horizontal orientation' do
      it 'removes horizontal alignment properties' do
        child = {
          'type' => 'View',
          'alignLeft' => true,
          'alignRight' => true,
          'centerHorizontal' => true,
          'centerInParent' => true,
          'alignTop' => true
        }

        result = helper.remove_alignment_properties(child, 'horizontal', true)

        expect(result).not_to have_key('alignLeft')
        expect(result).not_to have_key('alignRight')
        expect(result).not_to have_key('centerHorizontal')
        expect(result).not_to have_key('centerInParent')
        expect(result).not_to have_key('alignTop')
      end

      it 'preserves vertical properties when not wrapping' do
        child = {
          'type' => 'View',
          'alignTop' => true,
          'alignBottom' => true
        }

        result = helper.remove_alignment_properties(child, 'horizontal', false)

        expect(result).to have_key('alignTop')
        expect(result).to have_key('alignBottom')
      end
    end

    context 'with vertical orientation' do
      it 'removes vertical alignment properties' do
        child = {
          'type' => 'View',
          'alignTop' => true,
          'alignBottom' => true,
          'centerVertical' => true,
          'centerInParent' => true,
          'alignLeft' => true
        }

        result = helper.remove_alignment_properties(child, 'vertical', true)

        expect(result).not_to have_key('alignTop')
        expect(result).not_to have_key('alignBottom')
        expect(result).not_to have_key('centerVertical')
        expect(result).not_to have_key('centerInParent')
        expect(result).not_to have_key('alignLeft')
      end

      it 'preserves horizontal properties when not wrapping' do
        child = {
          'type' => 'View',
          'alignLeft' => true,
          'alignRight' => true
        }

        result = helper.remove_alignment_properties(child, 'vertical', false)

        expect(result).to have_key('alignLeft')
        expect(result).to have_key('alignRight')
      end
    end
  end

  describe '#calculate_alignment_needs' do
    let(:helper) { helper_class.new }

    context 'with horizontal orientation' do
      it 'handles alignTop' do
        child = { 'alignTop' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.top')
      end

      it 'handles alignBottom' do
        child = { 'alignBottom' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.bottom')
      end

      it 'handles centerVertical' do
        child = { 'centerVertical' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.center')
      end

      it 'handles alignRight with spacer before' do
        child = { 'alignRight' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be false
      end

      it 'handles alignLeft with spacer after' do
        child = { 'alignLeft' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_spacer_before]).to be false
        expect(result[:needs_spacer_after]).to be true
      end

      it 'handles centerHorizontal with spacers on both sides' do
        child = { 'centerHorizontal' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be true
      end

      it 'handles centerInParent' do
        child = { 'centerInParent' => true }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.center')
        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be true
      end
    end

    context 'with vertical orientation' do
      it 'handles alignLeft' do
        child = { 'alignLeft' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.leading')
      end

      it 'handles alignRight' do
        child = { 'alignRight' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.trailing')
      end

      it 'handles centerHorizontal' do
        child = { 'centerHorizontal' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.center')
      end

      it 'handles alignBottom with spacer before' do
        child = { 'alignBottom' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be false
      end

      it 'handles alignTop with spacer after' do
        child = { 'alignTop' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_spacer_before]).to be false
        expect(result[:needs_spacer_after]).to be true
      end

      it 'handles centerVertical with spacers on both sides' do
        child = { 'centerVertical' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be true
      end

      it 'handles centerInParent' do
        child = { 'centerInParent' => true }
        result = helper.calculate_alignment_needs(child, 'vertical')

        expect(result[:needs_wrapper]).to be true
        expect(result[:wrapper_alignment]).to eq('.center')
        expect(result[:needs_spacer_before]).to be true
        expect(result[:needs_spacer_after]).to be true
      end
    end

    context 'with no alignment' do
      it 'returns all false' do
        child = { 'type' => 'View' }
        result = helper.calculate_alignment_needs(child, 'horizontal')

        expect(result[:needs_wrapper]).to be false
        expect(result[:wrapper_alignment]).to be_nil
        expect(result[:needs_spacer_before]).to be false
        expect(result[:needs_spacer_after]).to be false
      end
    end
  end
end
