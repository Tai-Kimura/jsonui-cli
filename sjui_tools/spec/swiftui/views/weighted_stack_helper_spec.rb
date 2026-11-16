# frozen_string_literal: true

require 'swiftui/views/weighted_stack_helper'

RSpec.describe SjuiTools::SwiftUI::Views::WeightedStackHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::WeightedStackHelper

      attr_accessor :converter_factory, :view_registry, :action_manager, :indent_level, :state_variables
      attr_reader :generated_code

      def initialize
        @generated_code = []
        @state_variables = []
        @indent_level = 0
      end

      def add_line(line)
        @generated_code << line
      end

      def add_modifier_line(line)
        @generated_code << line
      end

      def indent
        @indent_level += 1
        yield
        @indent_level -= 1
      end
    end
  end

  describe '#get_child_weight' do
    let(:helper) { helper_class.new }

    context 'with weight property' do
      it 'returns the weight' do
        child = { 'weight' => 2 }
        expect(helper.send(:get_child_weight, child, 'horizontal')).to eq(2.0)
      end
    end

    context 'with widthWeight for horizontal' do
      it 'returns the widthWeight' do
        child = { 'widthWeight' => 1.5 }
        expect(helper.send(:get_child_weight, child, 'horizontal')).to eq(1.5)
      end
    end

    context 'with heightWeight for vertical' do
      it 'returns the heightWeight' do
        child = { 'heightWeight' => 3 }
        expect(helper.send(:get_child_weight, child, 'vertical')).to eq(3.0)
      end
    end

    context 'with no weight' do
      it 'returns 0' do
        child = { 'type' => 'View' }
        expect(helper.send(:get_child_weight, child, 'horizontal')).to eq(0)
      end
    end

    context 'with non-hash child' do
      it 'returns 0' do
        expect(helper.send(:get_child_weight, nil, 'horizontal')).to eq(0)
        expect(helper.send(:get_child_weight, 'string', 'vertical')).to eq(0)
      end
    end

    context 'with mismatched weight type' do
      it 'returns 0 for widthWeight in vertical' do
        child = { 'widthWeight' => 2 }
        expect(helper.send(:get_child_weight, child, 'vertical')).to eq(0)
      end

      it 'returns 0 for heightWeight in horizontal' do
        child = { 'heightWeight' => 2 }
        expect(helper.send(:get_child_weight, child, 'horizontal')).to eq(0)
      end
    end
  end

  describe '#generate_weighted_hstack' do
    let(:helper) { helper_class.new }
    let(:children) { [] }

    it 'generates GeometryReader with HStack' do
      helper.generate_weighted_hstack(children, '.center')

      expect(helper.generated_code).to include('GeometryReader { geometry in')
      expect(helper.generated_code).to include('HStack(alignment: .center, spacing: 0) {')
    end
  end

  describe '#generate_weighted_vstack' do
    let(:helper) { helper_class.new }
    let(:children) { [] }

    it 'generates GeometryReader with VStack' do
      helper.generate_weighted_vstack(children, '.leading')

      expect(helper.generated_code).to include('GeometryReader { geometry in')
      expect(helper.generated_code).to include('VStack(alignment: .leading, spacing: 0) {')
    end
  end
end
