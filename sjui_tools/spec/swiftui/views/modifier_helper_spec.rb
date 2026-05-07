# frozen_string_literal: true

require 'swiftui/views/modifier_helper'
require 'swiftui/views/modifier_bag'

RSpec.describe SjuiTools::SwiftUI::Views::ModifierHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::ModifierHelper

      attr_accessor :component

      def initialize
        @generated_lines = []
        @modifier_bag = SjuiTools::SwiftUI::Views::ModifierBag.new
      end

      def generated_code
        lines = @generated_lines.dup
        emitter = Class.new do
          def initialize(lines)
            @lines = lines
          end

          def add_modifier_line(line)
            @lines << line
          end

          def add_line(line)
            @lines << line
          end
        end.new(lines)
        @modifier_bag.emit_all(emitter)
        lines
      end

      def add_modifier_line(line)
        @generated_lines << line
      end

      def add_line(line)
        @generated_lines << line
      end

      # Simulate the apply_safe_area_insets_to_bag from base_view_converter
      def apply_safe_area_insets_to_bag
        positions = @component['safeAreaInsetPositions']
        return unless positions

        if positions.is_a?(Array)
          edges = []
          edges << '.top' if positions.include?('top')
          edges << '.bottom' if positions.include?('bottom')
          edges << '.leading' if positions.include?('leading') || positions.include?('left')
          edges << '.trailing' if positions.include?('trailing') || positions.include?('right')

          if edges.any?
            @modifier_bag.append(:safe_area_insets, ".ignoresSafeArea(.all, edges: [#{edges.join(', ')}])")
          end
        elsif positions == 'all'
          @modifier_bag.append(:safe_area_insets, ".ignoresSafeArea()")
        elsif positions == 'none'
          # default safe area respected
        else
          add_line "// safeAreaInsetPositions: #{positions}"
        end
      end
    end
  end

  describe '#apply_gradient' do
    let(:helper) { helper_class.new }

    context 'with vertical gradient' do
      it 'applies linear gradient with top to bottom' do
        helper.component = {
          'gradient' => ['#FF0000', '#0000FF'],
          'gradientDirection' => 'Vertical'
        }
        helper.send(:apply_gradient)

        expect(helper.generated_code.first).to include('.background(LinearGradient')
        expect(helper.generated_code.first).to include('startPoint: .top')
        expect(helper.generated_code.first).to include('endPoint: .bottom')
      end
    end

    context 'with horizontal gradient' do
      it 'applies linear gradient with leading to trailing' do
        helper.component = {
          'gradient' => ['#FF0000', '#00FF00'],
          'gradientDirection' => 'Horizontal'
        }
        helper.send(:apply_gradient)

        expect(helper.generated_code.first).to include('startPoint: .leading')
        expect(helper.generated_code.first).to include('endPoint: .trailing')
      end
    end

    context 'with oblique gradient' do
      it 'applies linear gradient diagonally' do
        helper.component = {
          'gradient' => ['#FF0000', '#00FF00'],
          'gradientDirection' => 'Oblique'
        }
        helper.send(:apply_gradient)

        expect(helper.generated_code.first).to include('startPoint: .topLeading')
        expect(helper.generated_code.first).to include('endPoint: .bottomTrailing')
      end
    end

    context 'without direction' do
      it 'defaults to vertical' do
        helper.component = { 'gradient' => ['#FF0000', '#00FF00'] }
        helper.send(:apply_gradient)

        expect(helper.generated_code.first).to include('startPoint: .top')
        expect(helper.generated_code.first).to include('endPoint: .bottom')
      end
    end
  end

  describe '#apply_safe_area_insets' do
    let(:helper) { helper_class.new }

    context 'with array of edges' do
      it 'ignores top and bottom' do
        helper.component = { 'safeAreaInsetPositions' => ['top', 'bottom'] }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to include('.ignoresSafeArea(.all, edges:')
        expect(helper.generated_code.first).to include('.top')
        expect(helper.generated_code.first).to include('.bottom')
      end

      it 'handles left as leading' do
        helper.component = { 'safeAreaInsetPositions' => ['left'] }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to include('.leading')
      end

      it 'handles right as trailing' do
        helper.component = { 'safeAreaInsetPositions' => ['right'] }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to include('.trailing')
      end

      it 'handles leading and trailing directly' do
        helper.component = { 'safeAreaInsetPositions' => ['leading', 'trailing'] }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to include('.leading')
        expect(helper.generated_code.first).to include('.trailing')
      end
    end

    context 'with all edges' do
      it 'ignores all safe area' do
        helper.component = { 'safeAreaInsetPositions' => 'all' }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to eq('.ignoresSafeArea()')
      end
    end

    context 'with none' do
      it 'does not add modifier' do
        helper.component = { 'safeAreaInsetPositions' => 'none' }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code).to be_empty
      end
    end

    context 'without safeAreaInsetPositions' do
      it 'does not add modifier' do
        helper.component = {}
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code).to be_empty
      end
    end

    context 'with unknown value' do
      it 'adds comment' do
        helper.component = { 'safeAreaInsetPositions' => 'unknown' }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code.first).to include('// safeAreaInsetPositions: unknown')
      end
    end

    context 'with empty array' do
      it 'does not add modifier' do
        helper.component = { 'safeAreaInsetPositions' => [] }
        helper.send(:apply_safe_area_insets)

        expect(helper.generated_code).to be_empty
      end
    end
  end
end
