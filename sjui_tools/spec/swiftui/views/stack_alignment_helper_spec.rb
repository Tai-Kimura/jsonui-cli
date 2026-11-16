# frozen_string_literal: true

require 'swiftui/views/stack_alignment_helper'
require 'swiftui/views/frame_helper'

RSpec.describe SjuiTools::SwiftUI::Views::StackAlignmentHelper do
  let(:helper_class) do
    Class.new do
      # FrameHelper rides along as it does in every real converter:
      # zstack_default_alignment reads the declared gravity through
      # FrameHelper#gravity_to_frame_alignment.
      include SjuiTools::SwiftUI::Views::FrameHelper
      include SjuiTools::SwiftUI::Views::StackAlignmentHelper

      attr_accessor :component

      def initialize(component)
        @component = component
      end
    end
  end

  describe '#get_hstack_alignment' do
    # 子要素のalignmentは個別の子要素の配置に影響するが、HStack自体のalignmentには影響しない
    # HStackのalignmentはgravityで決まる
    context 'with centerVertical child (does not affect HStack alignment)' do
      let(:component) { { 'child' => [{ 'centerVertical' => true }] } }

      it 'returns default .top (child alignment does not affect HStack)' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.top')
      end
    end

    context 'with alignBottom child (does not affect HStack alignment)' do
      let(:component) { { 'child' => [{ 'alignBottom' => true }] } }

      it 'returns default .top (child alignment does not affect HStack)' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.top')
      end
    end

    context 'with gravity array' do
      let(:component) { { 'gravity' => ['center', 'left'] } }

      it 'extracts vertical alignment from array' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.center')
      end
    end

    context 'with gravity string containing pipe' do
      let(:component) { { 'gravity' => 'left|bottom' } }

      it 'extracts vertical alignment' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.bottom')
      end
    end

    context 'with single gravity value' do
      let(:component) { { 'gravity' => 'center' } }

      it 'uses the value if vertical' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.center')
      end
    end

    context 'with no gravity' do
      let(:component) { {} }

      it 'defaults to .top' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.top')
      end
    end

    context 'with gravity centerVertical string' do
      let(:component) { { 'gravity' => 'centerVertical' } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.center')
      end
    end

    context 'with gravity centerVertical in pipe format' do
      let(:component) { { 'gravity' => 'left|centerVertical' } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.center')
      end
    end

    context 'with gravity centerVertical in array format' do
      let(:component) { { 'gravity' => ['centerVertical', 'left'] } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_hstack_alignment).to eq('.center')
      end
    end
  end

  describe '#get_vstack_alignment' do
    # 子要素のalignmentは個別の子要素の配置に影響するが、VStack自体のalignmentには影響しない
    # VStackのalignmentはgravityで決まる
    context 'with centerHorizontal child (does not affect VStack alignment)' do
      let(:component) { { 'child' => [{ 'centerHorizontal' => true }] } }

      it 'returns default .leading (child alignment does not affect VStack)' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.leading')
      end
    end

    context 'with alignRight child (does not affect VStack alignment)' do
      let(:component) { { 'child' => [{ 'alignRight' => true }] } }

      it 'returns default .leading (child alignment does not affect VStack)' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.leading')
      end
    end

    context 'with gravity array' do
      let(:component) { { 'gravity' => ['top', 'right'] } }

      it 'extracts horizontal alignment from array' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.trailing')
      end
    end

    context 'with gravity string containing pipe' do
      let(:component) { { 'gravity' => 'center|top' } }

      it 'extracts horizontal alignment' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.center')
      end
    end

    context 'with single gravity value' do
      let(:component) { { 'gravity' => 'right' } }

      it 'uses the value if horizontal' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.trailing')
      end
    end

    context 'with no gravity' do
      let(:component) { {} }

      it 'defaults to .leading' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.leading')
      end
    end

    context 'with gravity centerHorizontal string' do
      let(:component) { { 'gravity' => 'centerHorizontal' } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.center')
      end
    end

    context 'with gravity centerHorizontal in pipe format' do
      let(:component) { { 'gravity' => 'centerHorizontal|top' } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.center')
      end
    end

    context 'with gravity centerHorizontal in array format' do
      let(:component) { { 'gravity' => ['centerHorizontal', 'top'] } }

      it 'returns .center' do
        helper = helper_class.new(component)
        expect(helper.get_vstack_alignment).to eq('.center')
      end
    end
  end

  describe '#get_zstack_alignment_for_child' do
    let(:helper) { helper_class.new({}) }

    it 'returns .topLeading for alignTop and alignLeft' do
      child = { 'alignTop' => true, 'alignLeft' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.topLeading')
    end

    it 'returns .top for alignTop and centerHorizontal' do
      child = { 'alignTop' => true, 'centerHorizontal' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.top')
    end

    it 'returns .topTrailing for alignTop and alignRight' do
      child = { 'alignTop' => true, 'alignRight' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.topTrailing')
    end

    it 'returns .center for centerInParent' do
      child = { 'centerInParent' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.center')
    end

    it 'returns .bottomTrailing for alignBottom and alignRight' do
      child = { 'alignBottom' => true, 'alignRight' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.bottomTrailing')
    end

    it 'returns .leading for alignLeft only' do
      child = { 'alignLeft' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.topLeading')
    end

    it 'returns .bottom for alignBottom and centerHorizontal' do
      child = { 'alignBottom' => true, 'centerHorizontal' => true }
      expect(helper.get_zstack_alignment_for_child(child)).to eq('.bottom')
    end

    it 'returns nil for no alignment' do
      child = {}
      expect(helper.get_zstack_alignment_for_child(child)).to be_nil
    end
  end

  describe '#get_zstack_alignment' do
    context 'with explicit alignment attribute' do
      it 'returns .center for center' do
        helper = helper_class.new({ 'alignment' => 'center' })
        expect(helper.get_zstack_alignment).to eq('.center')
      end

      it 'returns .topTrailing for topTrailing' do
        helper = helper_class.new({ 'alignment' => 'topTrailing' })
        expect(helper.get_zstack_alignment).to eq('.topTrailing')
      end

      it 'returns .leading for left' do
        helper = helper_class.new({ 'alignment' => 'left' })
        expect(helper.get_zstack_alignment).to eq('.leading')
      end

      it 'returns .trailing for right' do
        helper = helper_class.new({ 'alignment' => 'right' })
        expect(helper.get_zstack_alignment).to eq('.trailing')
      end

      it 'returns .bottomLeading for bottomLeading' do
        helper = helper_class.new({ 'alignment' => 'bottomLeading' })
        expect(helper.get_zstack_alignment).to eq('.bottomLeading')
      end
    end

    context 'with child alignment' do
      let(:component) do
        {
          'child' => [
            { 'centerInParent' => true }
          ]
        }
      end

      it 'derives alignment from child' do
        helper = helper_class.new(component)
        expect(helper.get_zstack_alignment).to eq('.center')
      end
    end

    context 'with no alignment' do
      let(:component) { {} }

      it 'defaults to .topLeading' do
        helper = helper_class.new(component)
        expect(helper.get_zstack_alignment).to eq('.topLeading')
      end
    end

    context 'with declared gravity' do
      # The ZStack is the container: its alignment IS the declared content
      # gravity, the same declaration kjui feeds Box(contentAlignment:). The
      # old literal .topLeading gave `gravity: "center"` no rendering at all
      # on ios (downstream hero_section field report).
      let(:component) do
        {
          'gravity' => 'center',
          'child' => [{ 'type' => 'NetworkImage', 'width' => 'matchParent', 'height' => 'matchParent' }]
        }
      end

      it 'reflects the declaration' do
        helper = helper_class.new(component)
        expect(helper.get_zstack_alignment).to eq('.center')
      end
    end
  end
end
