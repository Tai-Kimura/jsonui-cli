# frozen_string_literal: true

require 'compose/components/segment_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SegmentComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates Segment component' do
      json_data = {
        'type' => 'Segment',
        'items' => ['Tab 1', 'Tab 2']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Segment(')
      expect(required_imports).to include(:segment)
    end

    it 'generates Segment with static items' do
      json_data = {
        'type' => 'Segment',
        'items' => ['First', 'Second', 'Third']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Tab(')
      expect(result).to include('First')
      expect(result).to include('Second')
      expect(result).to include('Third')
    end

    it 'uses segments attribute as alias' do
      json_data = {
        'type' => 'Segment',
        'segments' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Tab(')
      expect(result).to include('"A"')
      expect(result).to include('"B"')
    end

    it 'handles dynamic segments binding' do
      json_data = {
        'type' => 'Segment',
        'items' => '@{segmentOptions}'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.segmentOptions.forEachIndexed')
    end

    it 'generates Segment with static selectedIndex' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => 1,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = 1')
    end

    it 'generates Segment with dynamic selectedIndex binding' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{currentTab}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = data.currentTab')
    end

    it 'generates Segment with bind attribute' do
      json_data = {
        'type' => 'Segment',
        'bind' => '@{tabIndex}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = data.tabIndex')
    end

    it 'defaults selectedIndex to 0' do
      json_data = {
        'type' => 'Segment',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = 0')
    end

    it 'generates Segment with enabled attribute' do
      json_data = {
        'type' => 'Segment',
        'enabled' => false,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = false')
    end

    it 'generates Segment with enabled binding' do
      json_data = {
        'type' => 'Segment',
        'enabled' => '@{isEnabled}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = data.isEnabled')
    end

    it 'generates Segment with backgroundColor' do
      json_data = {
        'type' => 'Segment',
        'backgroundColor' => '#EEEEEE',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('containerColor')
    end

    it 'generates Segment with normalColor' do
      json_data = {
        'type' => 'Segment',
        'normalColor' => '#666666',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentColor')
    end

    it 'generates Segment with selectedColor' do
      json_data = {
        'type' => 'Segment',
        'selectedColor' => '#007AFF',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedContentColor')
    end

    it 'generates Segment with tintColor' do
      json_data = {
        'type' => 'Segment',
        'tintColor' => '#FF0000',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedContentColor')
    end

    it 'generates Segment with indicatorColor' do
      json_data = {
        'type' => 'Segment',
        'indicatorColor' => '#0000FF',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('indicatorColor')
    end

    it 'generates Segment with onValueChange handler' do
      json_data = {
        'type' => 'Segment',
        'onValueChange' => '@{handleTabChange}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.handleTabChange?.invoke()')
    end

    it 'generates update when binding is set' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{tab}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('viewModel.updateData(mapOf("tab" to')
    end

    it 'applies size modifiers' do
      json_data = {
        'type' => 'Segment',
        'width' => 'matchParent',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.fillMaxWidth()')
    end

    it 'applies padding modifiers' do
      json_data = {
        'type' => 'Segment',
        'padding' => 16,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(16.dp)')
    end

    it 'handles conditional text color for static index' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => 0,
        'selectedColor' => '#FF0000',
        'normalColor' => '#999999',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text(')
      expect(result).to include('color =')
    end

    it 'handles conditional text color for dynamic index' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{tab}',
        'selectedColor' => '#FF0000',
        'normalColor' => '#999999',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('if (data.tab')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke()')
      expect(result).not_to include('invoke("tabSegment"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("tabSegment", 0)')
      expect(result).to include('data.onTabChange?.invoke("tabSegment", 1)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Int) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((String, Int) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'categorySegment',
        'items' => ['All', 'Active', 'Completed'],
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("categorySegment", 0)')
      expect(result).to include('data.onTabChange?.invoke("categorySegment", 1)')
      expect(result).to include('data.onTabChange?.invoke("categorySegment", 2)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((String, Int) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onTabChange?.invoke("tabSegment", 0)')
    end

    it 'uses default segment id when no id specified' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'items' => ['A', 'B'],
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("segment", 0)')
    end
  end
end
