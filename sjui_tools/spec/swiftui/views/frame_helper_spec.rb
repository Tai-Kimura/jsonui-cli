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
  end

  describe 'idealWidth / idealHeight' do
    it 'emits a separate .frame(idealWidth:) call' do
      helper = helper_class.new({ 'type' => 'View', 'idealWidth' => 120 })
      helper.apply_frame_constraints

      expect(helper.generated_code).to include('.frame(idealWidth: 120)')
    end

    it 'emits a separate .frame(idealHeight:) call' do
      helper = helper_class.new({ 'type' => 'View', 'idealHeight' => 80 })
      helper.apply_frame_constraints

      expect(helper.generated_code).to include('.frame(idealHeight: 80)')
    end

    it 'keeps them out of the min/max frame, matching the Dynamic runtime' do
      # DynamicModifierHelper applies each as its own `.frame()`; SwiftUI
      # composes nested frames, so merging them here would change semantics
      # AND collide with the auto-derived matchParent frame.
      helper = helper_class.new({
        'type' => 'View', 'idealWidth' => 120, 'minWidth' => 50
      })
      helper.apply_frame_constraints
      code = helper.generated_code

      expect(code).to include('.frame(idealWidth: 120)')
      expect(code.grep(/minWidth: 50/).first).not_to include('idealWidth')
    end

    it 'supports a binding' do
      helper = helper_class.new({ 'type' => 'View', 'idealHeight' => '@{rowHeight}' })
      helper.apply_frame_constraints

      expect(helper.generated_code.join("\n")).to include('idealHeight: data.rowHeight')
    end

    it 'emits nothing when absent' do
      helper = helper_class.new({ 'type' => 'View' })
      helper.apply_frame_constraints

      expect(helper.generated_code.join("\n")).not_to include('ideal')
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
