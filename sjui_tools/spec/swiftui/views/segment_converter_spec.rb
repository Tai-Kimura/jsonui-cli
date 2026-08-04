# frozen_string_literal: true

require 'swiftui/views/segment_converter'

RSpec.describe SjuiTools::SwiftUI::Views::SegmentConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic segment' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => ['Tab 1', 'Tab 2', 'Tab 3']
        }
      end

      it 'generates Picker with segmented style' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Picker(')
        expect(code).to include('.pickerStyle(.segmented)')
      end

      it 'includes all items with tags' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("Tab 1").tag(0)')
        expect(code).to include('Text("Tab 2").tag(1)')
        expect(code).to include('Text("Tab 3").tag(2)')
      end
    end

    context 'with custom id' do
      let(:component) do
        {
          'type' => 'Segment',
          'id' => 'my_segment',
          'items' => ['A', 'B']
        }
      end

      it 'uses id in selection binding' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedMySegment')
      end
    end

    context 'with selectedIndex binding' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => ['Option 1', 'Option 2'],
          'selectedIndex' => '@{tabIndex}'
        }
      end

      it 'uses binding for selection' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('$data.tabIndex')
      end
    end

    context 'with selectedTabIndex binding' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => ['First', 'Second'],
          'selectedTabIndex' => '@{currentTab}'
        }
      end

      it 'uses binding for selection' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('$data.currentTab')
      end
    end

    context 'with empty items' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => []
        }
      end

      it 'generates empty picker' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Picker(')
        expect(code).to include('}')
      end
    end

    context 'with items containing quotes' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => ['Say "Hello"', 'Normal']
        }
      end

      it 'escapes quotes in items' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('\\"Hello\\"')
      end
    end

    context 'with common modifiers' do
      let(:component) do
        {
          'type' => 'Segment',
          'items' => ['A', 'B'],
          'cornerRadius' => 8
        }
      end

      it 'applies common modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end
  end

  describe 'event handler invocation' do
    before do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'generates onValueChange handler with onChange modifier' do
      component = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.selectedTab)')
      expect(code).to include('data.onTabChange?()')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Int) -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((String, Int) -> Void)?' }
      }

      component = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onTabChange?("tabSegment", newValue)')
    end

    it 'generates invoke() when handler type is () -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '(() -> Void)?' }
      }

      component = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('.onChange(of: data.selectedTab)')
      expect(code).to include('data.onTabChange?()')
      expect(code).not_to include('onTabChange?("tabSegment"')
    end

    it 'uses default segment id when no id specified' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((Event) -> Void)?' }
      }

      component = {
        'type' => 'Segment',
        'items' => ['A', 'B'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onTabChange?("segment", newValue)')
    end

    # SwiftUI's segmented Picker has no per-state colour modifier, so both the
    # UIKit runtime and the SwiftUI Dynamic runtime go through
    # UISegmentedControl.appearance(). The codegen read neither attribute.
    describe 'selected tint and unselected label' do
      it 'sets the selected segment tint' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'tintColor' => '#FF0000' }
        ).convert

        expect(code).to include('UISegmentedControl.appearance()')
        expect(code).to include('selectedSegmentTintColor')
      end

      it 'sets the unselected title colour' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'fontColor' => '#0000FF' }
        ).convert

        expect(code).to include('setTitleTextAttributes')
        expect(code).to include('for: .normal')
      end

      it 'applies in onAppear, since appearance() is process-wide' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'fontColor' => '#0000FF' }
        ).convert

        expect(code).to include('.onAppear {')
      end

      it 'emits nothing when neither is set' do
        code = described_class.new({ 'type' => 'Segment', 'items' => %w[One Two] }).convert

        expect(code).not_to include('UISegmentedControl.appearance()')
      end
    end

    # fontColor / selectedFontColor are the label colours; normalColor /
    # selectedColor are their declared aliases, resolved by the normalizer
    # before the converter sees the node (contract: semantics.segmentLabelColors).
    describe 'fontColor / selectedFontColor' do
      it 'sets the unselected title colour from fontColor' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'fontColor' => '#0000FF' }
        ).convert

        expect(code).to include('setTitleTextAttributes')
        expect(code).to include('for: .normal')
      end

      it 'sets the selected title colour from selectedFontColor' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'selectedFontColor' => '#00FF00' }
        ).convert

        expect(code).to include('for: .selected')
      end

      it 'gives the selected title fontColor when selectedFontColor is absent' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'fontColor' => '#0000FF' }
        ).convert

        expect(code).to include('for: .normal')
        expect(code).to include('for: .selected')
      end

      it 'reads canonical names only, leaving aliases to the normalizer' do
        code = described_class.new(
          { 'type' => 'Segment', 'items' => %w[One Two], 'normalColor' => '#123456' }
        ).convert

        expect(code).not_to include('123456')
      end
    end
  end
end
