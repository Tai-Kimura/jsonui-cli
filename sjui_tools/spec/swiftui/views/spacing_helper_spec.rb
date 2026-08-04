# frozen_string_literal: true

require 'swiftui/views/spacing_helper'
require 'swiftui/views/modifier_bag'

RSpec.describe SjuiTools::SwiftUI::Views::SpacingHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::SpacingHelper

      attr_accessor :component

      def initialize
        @modifier_bag = SjuiTools::SwiftUI::Views::ModifierBag.new
      end

      def generated_code
        lines = []
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
    end
  end

  describe '#apply_padding' do
    let(:helper) { helper_class.new }

    context 'with single padding value' do
      it 'applies single padding' do
        helper.component = { 'paddings' => 10 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(10)')
      end
    end

    context 'with array padding [1 value]' do
      it 'applies uniform padding' do
        helper.component = { 'paddings' => [8] }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(8)')
      end
    end

    context 'with array padding [2 values]' do
      it 'applies vertical and horizontal padding' do
        helper.component = { 'paddings' => [10, 20] }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.horizontal, 20)')
        expect(helper.generated_code).to include('.padding(.vertical, 10)')
      end
    end

    context 'with array padding [4 values]' do
      # JsonUI paddings format is [top, left, bottom, right]
      it 'applies all four paddings' do
        helper.component = { 'paddings' => [5, 10, 15, 20] }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.top, 5)')
        expect(helper.generated_code).to include('.padding(.leading, 10)')
        expect(helper.generated_code).to include('.padding(.bottom, 15)')
        expect(helper.generated_code).to include('.padding(.trailing, 20)')
      end
    end

    context 'with individual padding properties' do
      it 'applies paddingLeft' do
        helper.component = { 'paddingLeft' => 12 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.leading, 12)')
      end

      it 'applies paddingRight' do
        helper.component = { 'paddingRight' => 8 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.trailing, 8)')
      end

      it 'applies paddingTop' do
        helper.component = { 'paddingTop' => 16 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.top, 16)')
      end

      it 'applies paddingBottom' do
        helper.component = { 'paddingBottom' => 24 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.bottom, 24)')
      end
    end

    # RTL-aware padding tests
    context 'with RTL-aware padding properties' do
      it 'applies paddingStart to leading' do
        helper.component = { 'paddingStart' => 20 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.leading, 20)')
      end

      it 'applies paddingEnd to trailing' do
        helper.component = { 'paddingEnd' => 30 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.trailing, 30)')
      end

      it 'prioritizes paddingStart over paddingLeft' do
        helper.component = { 'paddingLeft' => 10, 'paddingStart' => 20 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.leading, 20)')
        expect(helper.generated_code).not_to include('.padding(.leading, 10)')
      end

      it 'prioritizes paddingEnd over paddingRight' do
        helper.component = { 'paddingRight' => 15, 'paddingEnd' => 25 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.trailing, 25)')
        expect(helper.generated_code).not_to include('.padding(.trailing, 15)')
      end

      it 'applies all RTL-aware paddings' do
        helper.component = {
          'paddingStart' => 12,
          'paddingEnd' => 16,
          'paddingTop' => 8,
          'paddingBottom' => 8
        }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.leading, 12)')
        expect(helper.generated_code).to include('.padding(.trailing, 16)')
        expect(helper.generated_code).to include('.padding(.top, 8)')
        expect(helper.generated_code).to include('.padding(.bottom, 8)')
      end

      it 'falls back to paddingLeft when paddingStart is not present' do
        helper.component = { 'paddingLeft' => 10 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.leading, 10)')
      end

      it 'falls back to paddingRight when paddingEnd is not present' do
        helper.component = { 'paddingRight' => 10 }
        helper.apply_padding

        expect(helper.generated_code).to include('.padding(.trailing, 10)')
      end
    end

    context 'with no padding' do
      it 'adds no modifiers' do
        helper.component = {}
        helper.apply_padding

        expect(helper.generated_code).to be_empty
      end
    end
  end

  describe '#apply_margins' do
    let(:helper) { helper_class.new }

    context 'with single margins value' do
      it 'applies all margins' do
        helper.component = { 'margins' => 10 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.all, 10)')
      end
    end

    context 'with array margins [1 value]' do
      it 'applies uniform margin' do
        helper.component = { 'margins' => [8] }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.all, 8)')
      end
    end

    context 'with array margins [2 values]' do
      it 'applies vertical and horizontal margins' do
        helper.component = { 'margins' => [10, 20] }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.vertical, 10)')
        expect(helper.generated_code).to include('.padding(.horizontal, 20)')
      end
    end

    context 'with array margins [4 values]' do
      it 'applies all four margins' do
        helper.component = { 'margins' => [5, 10, 15, 20] }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.top, 5)')
        expect(helper.generated_code).to include('.padding(.trailing, 10)')
        expect(helper.generated_code).to include('.padding(.bottom, 15)')
        expect(helper.generated_code).to include('.padding(.leading, 20)')
      end
    end

    context 'in a ZStack, where the parent offset owns the margin difference' do
      it 'keeps the shared part of a symmetric vertical margin as padding' do
        helper.component = { 'topMargin' => 10, 'bottomMargin' => 10, '_zstack_margin_offset' => true }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.top, 10)')
        expect(helper.generated_code).to include('.padding(.bottom, 10)')
      end

      it 'keeps the shared part of a symmetric horizontal margin as padding' do
        helper.component = { 'leftMargin' => 24, 'rightMargin' => 24, '_zstack_margin_offset' => true }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 24)')
        expect(helper.generated_code).to include('.padding(.trailing, 24)')
      end

      it 'pads by the smaller margin and leaves the difference to the offset' do
        helper.component = { 'topMargin' => 12, 'bottomMargin' => 4, '_zstack_margin_offset' => true }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.top, 4)')
        expect(helper.generated_code).to include('.padding(.bottom, 4)')
      end

      it 'emits no padding when only one edge is declared' do
        helper.component = { 'topMargin' => 8, 'leftMargin' => 8, '_zstack_margin_offset' => true }
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end

      it 'leaves a bound margin to the offset' do
        helper.component = { 'topMargin' => '@{gap}', 'bottomMargin' => '@{gap}', '_zstack_margin_offset' => true }
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end

      it 'lifts nothing on an axis the child centres' do
        helper.component = {
          'leftMargin' => 24, 'rightMargin' => 24, 'centerHorizontal' => true,
          '_zstack_margin_offset' => true
        }
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end

      it 'lifts nothing on either axis under centerInParent' do
        helper.component = {
          'topMargin' => 10, 'bottomMargin' => 10, 'leftMargin' => 24, 'rightMargin' => 24,
          'centerInParent' => true, '_zstack_margin_offset' => true
        }
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end

      it 'still lifts the axis the child does not centre' do
        helper.component = {
          'topMargin' => 10, 'bottomMargin' => 10, 'leftMargin' => 24, 'rightMargin' => 24,
          'centerVertical' => true, '_zstack_margin_offset' => true
        }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 24)')
        expect(helper.generated_code).to include('.padding(.trailing, 24)')
        expect(helper.generated_code).not_to include('.padding(.top, 10)')
      end

      it 'keeps start/endMargin padding, which the offset never owned' do
        helper.component = {
          'startMargin' => 12, 'endMargin' => 6, 'leftMargin' => 24, 'rightMargin' => 24,
          '_zstack_margin_offset' => true
        }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 12)')
        expect(helper.generated_code).to include('.padding(.trailing, 6)')
      end
    end

    context 'with individual margin properties' do
      it 'applies topMargin' do
        helper.component = { 'topMargin' => 16 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.top, 16)')
      end

      it 'applies bottomMargin' do
        helper.component = { 'bottomMargin' => 24 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.bottom, 24)')
      end

      it 'applies leftMargin' do
        helper.component = { 'leftMargin' => 12 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 12)')
      end

      it 'applies rightMargin' do
        helper.component = { 'rightMargin' => 8 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.trailing, 8)')
      end
    end

    # RTL-aware margin tests
    context 'with RTL-aware margin properties' do
      it 'applies startMargin to leading' do
        helper.component = { 'startMargin' => 20 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 20)')
      end

      it 'applies endMargin to trailing' do
        helper.component = { 'endMargin' => 30 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.trailing, 30)')
      end

      it 'prioritizes startMargin over leftMargin' do
        helper.component = { 'leftMargin' => 10, 'startMargin' => 20 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 20)')
        expect(helper.generated_code).not_to include('.padding(.leading, 10)')
      end

      it 'prioritizes endMargin over rightMargin' do
        helper.component = { 'rightMargin' => 15, 'endMargin' => 25 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.trailing, 25)')
        expect(helper.generated_code).not_to include('.padding(.trailing, 15)')
      end

      it 'applies all RTL-aware margins' do
        helper.component = {
          'startMargin' => 12,
          'endMargin' => 16,
          'topMargin' => 8,
          'bottomMargin' => 8
        }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 12)')
        expect(helper.generated_code).to include('.padding(.trailing, 16)')
        expect(helper.generated_code).to include('.padding(.top, 8)')
        expect(helper.generated_code).to include('.padding(.bottom, 8)')
      end

      it 'falls back to leftMargin when startMargin is not present' do
        helper.component = { 'leftMargin' => 10 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 10)')
      end

      it 'falls back to rightMargin when endMargin is not present' do
        helper.component = { 'rightMargin' => 10 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.trailing, 10)')
      end
    end

    context 'with no margins' do
      it 'adds no modifiers' do
        helper.component = {}
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end
    end

    # min/max{Start,End}Margin — a margin declared as a range. The library turns
    # the bounds into a capped Spacer; the converter only decides whether they
    # apply.
    context 'with bounded margins' do
      it 'emits both bounds for one side' do
        helper.component = { 'minStartMargin' => 8, 'maxStartMargin' => 40 }
        helper.apply_margins

        expect(helper.generated_code).to include('.flexibleHorizontalMargin(minStart: 8, maxStart: 40)')
      end

      it 'emits a lone lower bound' do
        helper.component = { 'minEndMargin' => 12 }
        helper.apply_margins

        expect(helper.generated_code).to include('.flexibleHorizontalMargin(minEnd: 12)')
      end

      it 'emits a lone upper bound' do
        helper.component = { 'maxStartMargin' => 24 }
        helper.apply_margins

        expect(helper.generated_code).to include('.flexibleHorizontalMargin(maxStart: 24)')
      end

      # Argument order has to match the library signature's declaration order.
      it 'emits all four bounds in signature order' do
        helper.component = {
          'minStartMargin' => 8, 'maxStartMargin' => 40,
          'minEndMargin' => 2, 'maxEndMargin' => 9
        }
        helper.apply_margins

        expect(helper.generated_code)
          .to include('.flexibleHorizontalMargin(minStart: 8, maxStart: 40, minEnd: 2, maxEnd: 9)')
      end

      it 'keeps a fractional bound intact' do
        helper.component = { 'minStartMargin' => 8.5, 'maxStartMargin' => 40 }
        helper.apply_margins

        expect(helper.generated_code).to include('.flexibleHorizontalMargin(minStart: 8.5, maxStart: 40)')
      end

      # UIKit gives the `equal` constraint to the fixed margin and never
      # consults the pair (UIViewDisposure.applyLeftPaddingConstraint).
      it 'yields the leading side to startMargin' do
        helper.component = { 'startMargin' => 4, 'minStartMargin' => 8, 'maxStartMargin' => 40 }
        helper.apply_margins

        expect(helper.generated_code).to include('.padding(.leading, 4)')
        expect(helper.generated_code.join).not_to include('flexibleHorizontalMargin')
      end

      it 'yields the leading side to leftMargin' do
        helper.component = { 'leftMargin' => 4, 'maxStartMargin' => 40 }
        helper.apply_margins

        expect(helper.generated_code.join).not_to include('flexibleHorizontalMargin')
      end

      it 'yields the trailing side to endMargin while keeping the leading pair' do
        helper.component = { 'endMargin' => 4, 'maxEndMargin' => 40, 'maxStartMargin' => 30 }
        helper.apply_margins

        expect(helper.generated_code).to include('.flexibleHorizontalMargin(maxStart: 30)')
      end

      # `margins` sets every side, so there is no side left to bound.
      it 'yields to the margins array' do
        helper.component = { 'margins' => [1, 2, 3, 4], 'minStartMargin' => 8, 'maxStartMargin' => 40 }
        helper.apply_margins

        expect(helper.generated_code.join).not_to include('flexibleHorizontalMargin')
      end

      # Declared `type: number`: a binding would be dropped by the library's
      # CGFloat signature, so it must not be emitted as a bare identifier.
      it 'ignores a non-numeric bound' do
        helper.component = { 'minStartMargin' => '@{someMargin}' }
        helper.apply_margins

        expect(helper.generated_code).to be_empty
      end
    end
  end

  describe '#apply_insets (private)' do
    let(:helper) { helper_class.new }

    context 'with single insets value' do
      it 'applies uniform insets' do
        helper.component = { 'insets' => 10 }
        helper.send(:apply_insets)

        expect(helper.generated_code).to include('.padding(10)')
      end
    end

    context 'with array insets [1 value]' do
      it 'applies uniform inset' do
        helper.component = { 'insets' => [8] }
        helper.send(:apply_insets)

        expect(helper.generated_code).to include('.padding(8)')
      end
    end

    context 'with array insets [2 values]' do
      it 'applies vertical and horizontal insets' do
        helper.component = { 'insets' => [10, 20] }
        helper.send(:apply_insets)

        expect(helper.generated_code).to include('.padding(.vertical, 10)')
        expect(helper.generated_code).to include('.padding(.horizontal, 20)')
      end
    end

    context 'with array insets [4 values]' do
      it 'applies all four insets' do
        helper.component = { 'insets' => [5, 10, 15, 20] }
        helper.send(:apply_insets)

        expect(helper.generated_code).to include('.padding(.top, 5)')
        expect(helper.generated_code).to include('.padding(.trailing, 10)')
        expect(helper.generated_code).to include('.padding(.bottom, 15)')
        expect(helper.generated_code).to include('.padding(.leading, 20)')
      end
    end

    context 'with insetHorizontal' do
      it 'applies horizontal inset' do
        helper.component = { 'insetHorizontal' => 16 }
        helper.send(:apply_insets)

        expect(helper.generated_code).to include('.padding(.horizontal, 16)')
      end
    end

    context 'with no insets' do
      it 'adds no modifiers' do
        helper.component = {}
        helper.send(:apply_insets)

        expect(helper.generated_code).to be_empty
      end
    end
  end
end
