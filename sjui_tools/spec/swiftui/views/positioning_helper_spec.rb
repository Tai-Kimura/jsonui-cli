# frozen_string_literal: true

require 'swiftui/views/positioning_helper'

RSpec.describe SjuiTools::SwiftUI::Views::PositioningHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::PositioningHelper

      attr_accessor :view_registry
      attr_reader :generated_code

      def initialize
        @generated_code = []
        @view_registry = nil
      end

      def add_modifier_line(line)
        @generated_code << line
      end
    end
  end

  describe '#apply_zstack_positioning' do
    context 'with no margins' do
      let(:child) { { 'id' => 'child1', 'type' => 'View' } }

      it 'adds zIndex' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        expect(helper.generated_code.last).to include('.zIndex(0)')
      end
    end

    context 'with margins' do
      let(:child) do
        {
          'id' => 'child1',
          'type' => 'View',
          'leftMargin' => 10,
          'topMargin' => 20
        }
      end

      it 'applies offset' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 1)

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to include('x: 10')
        expect(offset_code).to include('y: 20')
      end
    end

    context 'with centerInParent' do
      let(:child) do
        {
          'id' => 'child1',
          'type' => 'View',
          'centerInParent' => true,
          'leftMargin' => 5
        }
      end

      # semantics.margins: a centred axis has its margin disabled, and this
      # centres both. Emitting the margin as an offset moved the child back
      # off the centre the ZStack alignment had just placed it on.
      it 'resets both offsets' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        offset_codes = helper.generated_code.select { |c| c.include?('.offset') }
        expect(offset_codes).to be_empty
      end
    end

    context 'with centerVertical' do
      let(:child) do
        {
          'id' => 'child1',
          'type' => 'View',
          'centerVertical' => true,
          'topMargin' => 10,
          'leftMargin' => 5
        }
      end

      it 'resets y offset' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to include('x: 5')
        expect(offset_code).to include('y: 0')
      end
    end

    context 'with centerHorizontal' do
      let(:child) do
        {
          'id' => 'child1',
          'type' => 'View',
          'centerHorizontal' => true,
          'leftMargin' => 10,
          'topMargin' => 5
        }
      end

      it 'resets x offset' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to include('x: 0')
        expect(offset_code).to include('y: 5')
      end
    end

    context 'with relative positioning' do
      let(:child) do
        {
          'id' => 'child1',
          'type' => 'View',
          'alignTopOfView' => 'target'
        }
      end

      it 'skips normal offset calculation' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        # Should not have offset modifier (only zIndex)
        offset_codes = helper.generated_code.select { |c| c.include?('.offset') }
        expect(offset_codes).to be_empty
      end
    end

    context 'with different zIndex values' do
      let(:child) { { 'id' => 'child1', 'type' => 'View' } }

      it 'uses provided index' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 5)

        expect(helper.generated_code.last).to include('.zIndex(5)')
      end
    end
  end
end
