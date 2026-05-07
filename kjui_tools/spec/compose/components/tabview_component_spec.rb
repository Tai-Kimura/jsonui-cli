# frozen_string_literal: true

require 'compose/components/tabview_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::TabviewComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  describe '.generate' do
    it 'generates NavigationBar with tabs array' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house', 'view' => 'home' },
          { 'title' => 'Profile', 'icon' => 'person', 'view' => 'profile' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('NavigationBar(')
      expect(result).to include('NavigationBarItem(')
      expect(result).to include('HomeView()')
      expect(result).to include('ProfileView()')
      expect(required_imports).to include(:navigation_bar)
      expect(required_imports).to include(:scaffold)
    end

    it 'generates state variable for selected tab' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('var selectedTab by remember { mutableStateOf(0) }')
    end

    it 'handles selectedIndex binding' do
      json_data = {
        'type' => 'TabView',
        'selectedIndex' => '@{currentTab}',
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.currentTab')
      expect(result).to include('viewModel.updateData')
    end

    it 'generates tabs for each item in tabs array' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'First', 'icon' => 'house' },
          { 'title' => 'Second', 'icon' => 'person' },
          { 'title' => 'Third', 'icon' => 'gear' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('First')
      expect(result).to include('Second')
      expect(result).to include('Third')
    end

    it 'generates default title when not provided' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'icon' => 'circle' },
          { 'icon' => 'circle' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Tab 1')
      expect(result).to include('Tab 2')
    end

    it 'generates when expression for tab content' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house' },
          { 'title' => 'Settings', 'icon' => 'gear' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('when (selectedTab)')
      expect(result).to include('0 -> {')
      expect(result).to include('1 -> {')
    end

    it 'references view by name with PascalCase' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'My Tab', 'icon' => 'house', 'view' => 'home_screen' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('HomeScreenView()')
    end

    it 'generates default content when no view specified' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'My Tab', 'icon' => 'circle' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text("My Tab content")')
    end

    it 'wraps in Scaffold container' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Scaffold(')
      expect(result).to include('bottomBar = {')
    end

    it 'applies tabBarBackground color' do
      json_data = {
        'type' => 'TabView',
        'tabBarBackground' => 'primary',
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('containerColor =')
    end

    it 'applies tintColor to NavigationBarItem' do
      json_data = {
        'type' => 'TabView',
        'tintColor' => 'blue',
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('NavigationBarItemDefaults.colors(')
      expect(result).to include('selectedIconColor =')
    end

    it 'respects showLabels setting' do
      json_data = {
        'type' => 'TabView',
        'showLabels' => false,
        'tabs' => [{ 'title' => 'Tab', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('label = { Text("Tab") }')
    end

    it 'handles empty tabs array' do
      json_data = {
        'type' => 'TabView',
        'tabs' => []
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('NavigationBar(')
      expect(result).not_to include('NavigationBarItem(')
    end

    it 'adds click handler to each tab' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [{ 'title' => 'Tab 1', 'icon' => 'circle' }]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('onClick = { selectedTab = 0 }')
    end

    it 'maps SF Symbol icon names to Material Icons' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house' },
          { 'title' => 'Profile', 'icon' => 'person' },
          { 'title' => 'Settings', 'icon' => 'gearshape' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Icons.Filled.Home')
      expect(result).to include('Icons.Filled.Person')
      expect(result).to include('Icons.Filled.Settings')
    end

    it 'uses selectedIcon when provided' do
      json_data = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Heart', 'icon' => 'heart', 'selectedIcon' => 'heart.fill' }
        ]
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Icons.Filled.Favorite')
      expect(result).to include('Icons.Outlined.Favorite')
    end
  end

  describe '.to_icon_name' do
    it 'maps house to Home' do
      result = described_class.send(:to_icon_name, 'house')
      expect(result).to eq('Home')
    end

    it 'maps person to Person' do
      result = described_class.send(:to_icon_name, 'person')
      expect(result).to eq('Person')
    end

    it 'maps gearshape to Settings' do
      result = described_class.send(:to_icon_name, 'gearshape')
      expect(result).to eq('Settings')
    end

    it 'capitalizes unknown icon names' do
      result = described_class.send(:to_icon_name, 'custom')
      expect(result).to eq('Custom')
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

    it 'adds indentation for level 2' do
      result = described_class.send(:indent, 'text', 2)
      expect(result).to eq('        text')
    end
  end
end
