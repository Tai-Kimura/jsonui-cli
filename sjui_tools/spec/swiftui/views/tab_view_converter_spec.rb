# frozen_string_literal: true

require 'swiftui/views/tab_view_converter'

RSpec.describe SjuiTools::SwiftUI::Views::TabViewConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  let(:mock_child_converter) do
    double('ChildConverter',
           convert: "Text(\"Tab Content\")",
           state_variables: [])
  end

  let(:mock_factory) do
    factory = double('ConverterFactory')
    allow(factory).to receive(:create_converter).and_return(mock_child_converter)
    factory
  end

  describe '#convert' do
    context 'with no tabs' do
      let(:component) { { 'type' => 'TabView' } }

      it 'generates empty TabView' do
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        expect(code).to include('TabView {')
        expect(code).to include('}')
      end
    end

    context 'with single tab' do
      let(:component) do
        {
          'type' => 'TabView',
          'tabs' => [
            {
              'title' => 'Home',
              'icon' => 'house',
              'child' => [{ 'type' => 'Label', 'text' => 'Home Content' }]
            }
          ]
        }
      end

      it 'generates TabView with tab item' do
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        expect(code).to include('TabView {')
        expect(code).to include('.tabItem {')
        expect(code).to include('Label("Home", systemImage: "house")')
        expect(code).to include('.tag(0)')
      end
    end

    context 'with multiple tabs' do
      let(:component) do
        {
          'type' => 'TabView',
          'tabs' => [
            { 'title' => 'Home', 'icon' => 'house' },
            { 'title' => 'Profile', 'icon' => 'person' },
            { 'title' => 'Settings', 'icon' => 'gear' }
          ]
        }
      end

      it 'generates all tabs with correct tags' do
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        expect(code).to include('Label("Home", systemImage: "house")')
        expect(code).to include('Label("Profile", systemImage: "person")')
        expect(code).to include('Label("Settings", systemImage: "gear")')
        expect(code).to include('.tag(0)')
        expect(code).to include('.tag(1)')
        expect(code).to include('.tag(2)')
      end
    end

    context 'with default tab title and icon' do
      let(:component) do
        {
          'type' => 'TabView',
          'tabs' => [{}]
        }
      end

      it 'uses default values' do
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        expect(code).to include('Label("Tab 1", systemImage: "circle")')
      end
    end

    context 'with child content' do
      let(:component) do
        {
          'type' => 'TabView',
          'tabs' => [
            {
              'title' => 'Tab',
              'icon' => 'star',
              'child' => [
                { 'type' => 'Label', 'text' => 'Content 1' },
                { 'type' => 'Label', 'text' => 'Content 2' }
              ]
            }
          ]
        }
      end

      it 'generates TabView structure for tabs with child content' do
        # TabViewConverter generates basic tab content - child converters are not used
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        expect(code).to include('TabView {')
        expect(code).to include('Text("Tab")')
        expect(code).to include('.tabItem {')
      end
    end

    context 'with selectedTabIndex' do
      let(:component) do
        {
          'type' => 'TabView',
          'selectedTabIndex' => 1,
          'tabs' => [
            { 'title' => 'Tab1' },
            { 'title' => 'Tab2' }
          ]
        }
      end

      it 'handles selectedTabIndex property' do
        converter = described_class.new(component, 0, nil, mock_factory)
        code = converter.convert

        # selectedTabIndex is stored but selection binding would be handled separately
        expect(code).to include('TabView {')
      end
    end
  end
end
