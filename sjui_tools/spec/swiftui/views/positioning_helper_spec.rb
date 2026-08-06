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

      # A positional `.zIndex(index)` replicated ZStack's own document-order
      # default and, worse, overrode the `.zIndex(±N)` indexAbove/indexBelow
      # emit inside the child's chain (ios parity run 4, common_indexAbove).
      it 'emits no positional zIndex stamp' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 0)

        expect(helper.generated_code.join).not_to include('.zIndex(')
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

    # Margins are declared ["number", "binding"], so "@{gap}" is a valid
    # value here — and subtracting it as a Ruby String raised
    # NoMethodError, i.e. a layout written exactly as the SSoT allows
    # crashed the generator. `.offset` takes an expression, so one is
    # emitted rather than the declaration being refused.
    context 'with a bound margin' do
      it 'emits the difference as a Swift expression instead of crashing' do
        helper = helper_class.new
        expect {
          helper.apply_zstack_positioning(
            { 'id' => 'child1', 'type' => 'View', 'leftMargin' => '@{gap}' }, 0
          )
        }.not_to raise_error

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: CGFloat(data.gap ?? 0), y: 0)')
      end

      it 'subtracts a bound edge from a numeric one' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'topMargin' => 20, 'bottomMargin' => '@{gap}' }, 0
        )

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: 0, y: 20 - CGFloat(data.gap ?? 0))')
      end

      it 'negates a lone bound margin on the far edge' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'rightMargin' => '@{gap}' }, 0
        )

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: -(CGFloat(data.gap ?? 0)), y: 0)')
      end

      # The same expression on both edges cancels — the pair is a pure
      # inset, and SpacingHelper emits it as padding.
      it 'cancels a symmetric bound margin to no offset' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'topMargin' => '@{gap}', 'bottomMargin' => '@{gap}' }, 0
        )

        expect(helper.generated_code.select { |c| c.include?('.offset') }).to be_empty
      end

      it 'still resets a centred axis' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'leftMargin' => '@{gap}', 'centerHorizontal' => true }, 0
        )

        expect(helper.generated_code.select { |c| c.include?('.offset') }).to be_empty
      end

      # An Optional cannot be subtracted, so the unwrap is what keeps the
      # generated Swift compiling; a property with a data-section
      # defaultValue is non-optional and needs none.
      it 'drops the unwrap for a non-optional property' do
        Thread.current[:sjui_data_definitions] = { 'gap' => { 'defaultValue' => 8 } }
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'leftMargin' => '@{gap}' }, 0
        )

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: CGFloat(data.gap), y: 0)')
      ensure
        Thread.current[:sjui_data_definitions] = nil
      end

      it 'unwraps with the inline default when the binding carries one' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'leftMargin' => '@{gap ?? 12}' }, 0
        )

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: CGFloat(data.gap ?? 12), y: 0)')
      end

      it 'reads a numeric string as a number, which also used to crash' do
        helper = helper_class.new
        helper.apply_zstack_positioning(
          { 'id' => 'child1', 'type' => 'View', 'leftMargin' => '10' }, 0
        )

        offset_code = helper.generated_code.find { |c| c.include?('.offset') }
        expect(offset_code).to eq('.offset(x: 10, y: 0)')
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

    context 'with a non-zero index' do
      let(:child) { { 'id' => 'child1', 'type' => 'View' } }

      it 'still emits no positional zIndex stamp' do
        helper = helper_class.new
        helper.apply_zstack_positioning(child, 5)

        expect(helper.generated_code.join).not_to include('.zIndex(')
      end
    end
  end
end
