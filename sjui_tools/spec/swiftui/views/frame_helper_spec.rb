# frozen_string_literal: true

require 'swiftui/views/frame_helper'
require 'swiftui/views/template_helper'
require 'swiftui/views/modifier_bag'

RSpec.describe SjuiTools::SwiftUI::Views::FrameHelper do
  let(:helper_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::FrameHelper
      include SjuiTools::SwiftUI::Views::TemplateHelper

      attr_accessor :component

      def initialize(component)
        @component = component
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

      def size_to_swiftui(size)
        case size
        when 'matchParent' then '.infinity'
        when 'wrapContent' then nil
        when Integer, Float then size
        else size
        end
      end
    end
  end

  describe '#apply_frame_constraints' do
    context 'with minWidth' do
      let(:component) { { 'type' => 'View', 'minWidth' => 100 } }

      it 'adds frame with minWidth' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code.first).to include('minWidth: 100')
      end
    end

    context 'with maxWidth matchParent' do
      let(:component) { { 'type' => 'View', 'maxWidth' => 'matchParent' } }

      it 'converts maxWidth to .infinity' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code.first).to include('maxWidth: .infinity')
      end
    end

    context 'with multiple constraints' do
      let(:component) do
        {
          'type' => 'View',
          'minWidth' => 50,
          'maxWidth' => 200,
          'minHeight' => 30,
          'maxHeight' => 100
        }
      end

      it 'includes all constraints' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        code = helper.generated_code.first
        expect(code).to include('minWidth: 50')
        expect(code).to include('maxWidth: 200')
        expect(code).to include('minHeight: 30')
        expect(code).to include('maxHeight: 100')
      end
    end

    context 'with Label type' do
      let(:component) { { 'type' => 'Label', 'maxWidth' => 'matchParent' } }

      it 'adds topLeading alignment for Label' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code.first).to include('alignment: .topLeading')
      end
    end

    # Regression: sjui-wrap-content-without-max-skips-fixed-size-emit.
    # Before the fix, `apply_frame_constraints` was gated behind "has any
    # min/maxWidth/Height set"; for nodes declaring only `width: wrapContent`
    # (no min/max) the entire method early-returned and `.fixedSize` was
    # never emitted, so custom components that internally use
    # `.frame(maxWidth: .infinity)` (e.g. MarkdownText) expanded to parent
    # fill on iPhone. Android emitted `Modifier.wrapContentWidth()`
    # correctly, so the same JSON produced visually-different layouts
    # per platform. Now `.fixedSize` lifts out of the gate for explicit
    # wrapContent, mirroring Android's semantics.
    context 'with width: wrapContent only (no min/max constraints)' do
      let(:component) { { 'type' => 'MarkdownText', 'width' => 'wrapContent' } }

      it 'emits .fixedSize(horizontal: true, vertical: false)' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code).to include(
          '.fixedSize(horizontal: true, vertical: false)'
        )
      end
    end

    context 'with height: wrapContent only (no min/max constraints)' do
      let(:component) { { 'type' => 'View', 'height' => 'wrapContent' } }

      it 'emits .fixedSize(horizontal: false, vertical: true)' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code).to include(
          '.fixedSize(horizontal: false, vertical: true)'
        )
      end
    end

    context 'with both width and height: wrapContent (no min/max)' do
      let(:component) do
        { 'type' => 'MarkdownText', 'width' => 'wrapContent', 'height' => 'wrapContent' }
      end

      it 'emits .fixedSize(horizontal: true, vertical: true)' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code).to include(
          '.fixedSize(horizontal: true, vertical: true)'
        )
      end
    end

    context 'with width: wrapContent + maxWidth (gate-path, no horizontal fixedSize)' do
      let(:component) do
        { 'type' => 'MarkdownText', 'width' => 'wrapContent', 'maxWidth' => 600 }
      end

      it 'does NOT emit horizontal .fixedSize (maxWidth caps it)' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        # maxWidth alone does not gate-trip vertical fixedSize either —
        # height is implicit (nil) so v_fixed is true. The point is no
        # `horizontal: true` slips in when maxWidth bounds the width.
        fixed_size_line = helper.generated_code.find { |l| l.include?('.fixedSize') }
        expect(fixed_size_line).not_to include('horizontal: true')
      end
    end

    context 'with no size attributes at all' do
      let(:component) { { 'type' => 'View' } }

      it 'emits nothing (does NOT auto-fixedSize for unconfigured nodes)' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code).to be_empty
      end
    end

    context 'with fixed numeric width only (no wrapContent)' do
      let(:component) { { 'type' => 'View', 'width' => 100 } }

      it 'emits nothing from apply_frame_constraints' do
        helper = helper_class.new(component)
        helper.apply_frame_constraints

        expect(helper.generated_code).to be_empty
      end
    end
  end

  describe '#apply_frame_size' do
    context 'with fixed width and height' do
      let(:component) { { 'type' => 'View', 'width' => 100, 'height' => 50 } }

      it 'adds frame with width and height' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('width: 100')
        expect(helper.generated_code.first).to include('height: 50')
      end
    end

    context 'with matchParent width' do
      let(:component) { { 'type' => 'View', 'width' => 'matchParent' } }

      it 'adds maxWidth .infinity' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('maxWidth: .infinity')
      end
    end

    context 'with Label and textAlign center' do
      let(:component) { { 'type' => 'Label', 'width' => 'matchParent', 'textAlign' => 'center' } }

      it 'adds center alignment' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('alignment: .center')
      end
    end

    context 'with Label and textAlign right' do
      let(:component) { { 'type' => 'Label', 'width' => 'matchParent', 'textAlign' => 'right' } }

      it 'adds trailing alignment' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('alignment: .trailing')
      end
    end

    context 'with width 0 and weight' do
      let(:component) { { 'type' => 'View', 'width' => 0, 'weight' => 1 } }

      it 'ignores width 0 when weight is present' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code).to be_empty
      end
    end

    context 'with only height' do
      let(:component) { { 'type' => 'View', 'height' => 80 } }

      it 'adds frame with only height' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('idealHeight: 80')
        expect(helper.generated_code.first).to include('maxHeight: 80')
        expect(helper.generated_code.first).not_to include('width:')
      end
    end

    context 'with matchParent height' do
      let(:component) { { 'type' => 'View', 'height' => 'matchParent' } }

      it 'adds maxHeight .infinity' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('maxHeight: .infinity')
      end
    end

    context 'with both matchParent' do
      let(:component) { { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent' } }

      it 'adds both maxWidth and maxHeight' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('maxWidth: .infinity')
        expect(helper.generated_code.first).to include('maxHeight: .infinity')
      end
    end

    context 'with infinity width and fixed height' do
      let(:component) { { 'type' => 'View', 'width' => 'matchParent', 'height' => 100 } }

      it 'splits into two frame calls' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.length).to eq(2)
        expect(helper.generated_code[0]).to include('maxWidth:')
        expect(helper.generated_code[1]).to include('maxHeight: 100')
      end
    end

    context 'with binding width' do
      let(:component) { { 'type' => 'View', 'width' => '@{dynamicWidth}' } }

      # Frame values are read-only so binding references use `data.` (not `$data.`)
      it 'uses binding value for width' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('data.dynamicWidth')
      end
    end

    context 'with binding height' do
      let(:component) { { 'type' => 'View', 'height' => '@{dynamicHeight}' } }

      it 'uses binding value for height' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        expect(helper.generated_code.first).to include('data.dynamicHeight')
      end
    end

    context 'with binding width and height' do
      let(:component) { { 'type' => 'View', 'width' => '@{w}', 'height' => '@{h}' } }

      it 'uses binding values for both' do
        helper = helper_class.new(component)
        helper.apply_frame_size

        code = helper.generated_code.first
        expect(code).to include('data.w')
        expect(code).to include('data.h')
      end
    end
  end
end
