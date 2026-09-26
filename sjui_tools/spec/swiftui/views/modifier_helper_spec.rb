# frozen_string_literal: true

require 'swiftui/views/modifier_helper'
require 'swiftui/views/modifier_bag'
require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'

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

  # `apply_safe_area_insets` delegates to BaseViewConverter's
  # apply_safe_area_insets_to_bag. These examples used to run a copy of an
  # older implementation written into this spec's host (`.ignoresSafeArea`,
  # `left` read as leading) — the defect base_view_converter.rb describes —
  # so they stayed green whatever the method did. They run the real one.
  describe '#apply_safe_area_insets' do
    def lines_for(component)
      converter = SjuiTools::SwiftUI::Views::ViewConverter.new({ 'type' => 'View' }.merge(component))
      converter.send(:apply_safe_area_insets)
      converter.instance_variable_get(:@modifier_bag).to_lines
    end

    it 'reserves the safe area on the named edges' do
      expect(lines_for('safeAreaInsetPositions' => %w[top bottom])).to eq(['.safeAreaPadding([.top, .bottom])'])
      expect(lines_for('safeAreaInsetPositions' => %w[leading trailing])).to eq(['.safeAreaPadding([.leading, .trailing])'])
    end

    it 'reserves every edge for all' do
      expect(lines_for('safeAreaInsetPositions' => 'all')).to eq(['.safeAreaPadding(.all)'])
    end

    # The items are declared top / bottom / leading / trailing / vertical /
    # all, as written (1.9.0).
    it 'selects no edge for a spelling declared nowhere' do
      expect(lines_for('safeAreaInsetPositions' => %w[left])).to eq([])
      expect(lines_for('safeAreaInsetPositions' => %w[right horizontal])).to eq([])
    end

    it 'adds nothing for none, an empty list, an unknown value or no declaration' do
      [{ 'safeAreaInsetPositions' => 'none' }, { 'safeAreaInsetPositions' => [] },
       { 'safeAreaInsetPositions' => 'unknown' }, {}].each do |component|
        expect(lines_for(component)).to eq([]), component.inspect
      end
    end
  end
end
