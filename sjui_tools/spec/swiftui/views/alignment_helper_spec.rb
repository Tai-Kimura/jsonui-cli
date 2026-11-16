# frozen_string_literal: true

require 'swiftui/views/alignment_helper'

RSpec.describe SjuiTools::SwiftUI::Views::AlignmentHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::AlignmentHelper

      attr_accessor :component
      attr_reader :needs_center_both, :needs_center_horizontal, :needs_center_vertical
      attr_reader :align_top, :align_bottom, :align_left, :align_right
      attr_reader :generated_code

      def initialize(component)
        @component = component
        @generated_code = []
      end

      def add_modifier_line(line)
        @generated_code << line
      end
    end
  end

  describe '#apply_center_alignment' do
    context 'with centerInParent' do
      let(:component) { { 'centerInParent' => true } }

      it 'sets needs_center_both' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        expect(helper.needs_center_both).to be true
      end
    end

    context 'with centerHorizontal' do
      let(:component) { { 'centerHorizontal' => true } }

      it 'sets needs_center_horizontal' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        expect(helper.needs_center_horizontal).to be true
      end
    end

    context 'with centerVertical' do
      let(:component) { { 'centerVertical' => true } }

      it 'sets needs_center_vertical' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        expect(helper.needs_center_vertical).to be true
      end
    end
  end

  describe '#apply_edge_alignment' do
    context 'with edge alignments' do
      let(:component) do
        {
          'alignTop' => true,
          'alignBottom' => false,
          'alignLeft' => true,
          'alignRight' => false
        }
      end

      it 'sets alignment flags' do
        helper = helper_class.new(component)
        helper.apply_edge_alignment
        expect(helper.align_top).to be true
        expect(helper.align_bottom).to be false
        expect(helper.align_left).to be true
        expect(helper.align_right).to be false
      end
    end
  end

  describe '#apply_alignment_modifiers' do
    context 'with centerInParent' do
      let(:component) { { 'centerInParent' => true } }

      it 'adds frame with maxWidth and maxHeight infinity' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        helper.apply_alignment_modifiers
        expect(helper.generated_code.first).to include('maxWidth: .infinity')
        expect(helper.generated_code.first).to include('maxHeight: .infinity')
      end
    end

    context 'with centerHorizontal only' do
      let(:component) { { 'centerHorizontal' => true } }

      it 'adds frame with maxWidth infinity' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        helper.apply_alignment_modifiers
        expect(helper.generated_code.first).to include('maxWidth: .infinity')
        expect(helper.generated_code.first).not_to include('maxHeight')
      end
    end

    context 'with centerVertical only' do
      let(:component) { { 'centerVertical' => true } }

      it 'adds frame with maxHeight infinity' do
        helper = helper_class.new(component)
        helper.apply_center_alignment
        helper.apply_alignment_modifiers
        expect(helper.generated_code.first).to include('maxHeight: .infinity')
        expect(helper.generated_code.first).not_to include('maxWidth')
      end
    end
  end

  describe '#get_parent_alignment' do
    context 'with centerInParent' do
      let(:component) { { 'centerInParent' => true } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.center')
      end
    end

    context 'with default alignment' do
      let(:component) { {} }

      it 'returns .topLeading' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.topLeading')
      end
    end

    context 'with alignRight' do
      let(:component) { { 'alignRight' => true } }

      it 'returns .topTrailing' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.topTrailing')
      end
    end

    context 'with alignBottom' do
      let(:component) { { 'alignBottom' => true } }

      it 'returns .bottomLeading' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.bottomLeading')
      end
    end

    context 'with alignBottom and alignRight' do
      let(:component) { { 'alignBottom' => true, 'alignRight' => true } }

      it 'returns .bottomTrailing' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.bottomTrailing')
      end
    end

    context 'with centerHorizontal' do
      let(:component) { { 'centerHorizontal' => true } }

      it 'returns .top' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.top')
      end
    end

    context 'with centerVertical' do
      let(:component) { { 'centerVertical' => true } }

      it 'returns .leading' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.leading')
      end
    end

    context 'with centerHorizontal and alignBottom' do
      let(:component) { { 'centerHorizontal' => true, 'alignBottom' => true } }

      it 'returns .bottom' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.bottom')
      end
    end

    context 'with centerVertical and alignRight' do
      let(:component) { { 'centerVertical' => true, 'alignRight' => true } }

      it 'returns .trailing' do
        helper = helper_class.new(component)
        expect(helper.get_parent_alignment).to eq('.trailing')
      end
    end
  end
end
