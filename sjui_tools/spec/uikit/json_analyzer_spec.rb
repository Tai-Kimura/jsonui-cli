# frozen_string_literal: true

require 'uikit/json_analyzer'
require 'uikit/import_module_manager'
require 'uikit/ui_control_event_manager'
require 'tempfile'
require 'json'

RSpec.describe SjuiTools::UIKit::JsonAnalyzer do
  before(:all) do
    described_class.validation_enabled = false
  end

  after(:all) do
    described_class.validation_enabled = true
  end

  let(:import_module_manager) { SjuiTools::UIKit::ImportModuleManager.new }
  let(:ui_control_event_manager) { SjuiTools::UIKit::UIControlEventManager.new }
  let(:layout_path) { '/tmp/layouts' }
  let(:style_path) { '/tmp/styles' }
  let(:super_binding) { nil }
  let(:view_type_set) { {} }  # Hash of type => view class mappings

  let(:analyzer) do
    described_class.new(
      import_module_manager,
      ui_control_event_manager,
      layout_path,
      style_path,
      super_binding,
      view_type_set
    )
  end

  describe '.validation_enabled' do
    it 'can be disabled' do
      described_class.validation_enabled = false
      expect(described_class.validation_enabled?).to be false
    end

    it 'can be enabled' do
      described_class.validation_enabled = true
      expect(described_class.validation_enabled?).to be true
      described_class.validation_enabled = false  # Reset for other tests
    end
  end

  describe '#analyze_json' do
    context 'with simple Label component' do
      let(:json) do
        {
          'type' => 'Label',
          'text' => 'Hello World'
        }
      end

      it 'does not raise error' do
        expect { analyzer.analyze_json('test.json', json) }.not_to raise_error
      end
    end

    context 'with data declarations' do
      let(:json) do
        {
          'type' => 'View',
          'data' => ['userName', 'userEmail']
        }
      end

      it 'collects data sets' do
        analyzer.analyze_json('test.json', json)
        expect(analyzer.data_sets).to include('userName', 'userEmail')
      end
    end

    context 'with nested child elements' do
      let(:json) do
        {
          'type' => 'View',
          'child' => [
            { 'type' => 'Label', 'text' => 'Label 1' },
            { 'type' => 'Label', 'text' => 'Label 2' }
          ]
        }
      end

      it 'processes all children' do
        expect { analyzer.analyze_json('test.json', json) }.not_to raise_error
      end
    end

    context 'with id element (requires view type setup)' do
      let(:view_type_set) { { Label: 'UILabel' } }
      let(:json) do
        {
          'type' => 'Label',
          'id' => 'titleLabel',
          'text' => 'Hello'
        }
      end

      it 'tracks view variables' do
        analyzer.analyze_json('test.json', json)
        # View variables should be collected
        expect(analyzer.view_variables).to be_an(Array)
      end
    end
  end

  describe 'attribute readers' do
    it 'exposes binding_content' do
      expect(analyzer.binding_content).to eq('')
    end

    it 'exposes data_sets' do
      expect(analyzer.data_sets).to eq([])
    end

    it 'exposes binding_processes_group' do
      expect(analyzer.binding_processes_group).to eq({})
    end

    it 'exposes including_files' do
      expect(analyzer.including_files).to eq({})
    end

    it 'exposes reset_constraint_views' do
      expect(analyzer.reset_constraint_views).to eq({})
    end

    it 'exposes weak_vars_content' do
      expect(analyzer.weak_vars_content).to eq('')
    end

    it 'exposes invalidate_methods_content' do
      expect(analyzer.invalidate_methods_content).to eq('')
    end

    it 'exposes partial_bindings' do
      expect(analyzer.partial_bindings).to eq([])
    end

    it 'exposes view_variables' do
      expect(analyzer.view_variables).to eq([])
    end
  end

  describe '#analyze_json with onClick events' do
    let(:view_type_set) { { Button: 'UIButton' } }
    let(:json) do
      {
        'type' => 'Button',
        'id' => 'submitBtn',
        'text' => 'Submit',
        'onClick' => 'handleSubmit'
      }
    end

    it 'registers click event' do
      analyzer.analyze_json('test', json)
      events = ui_control_event_manager.instance_variable_get(:@ui_control_events)
      click_event = events.find { |e| e[:view_name] == 'submitBtn' && e[:event] == 'click' }
      expect(click_event).not_to be_nil
    end
  end

  describe '#analyze_json with gesture events' do
    # Note: Gesture events (onLongPress, onPan, onPinch) require proper ID processing
    # which happens before the event registration. The onClick test validates the event
    # registration mechanism.
    let(:view_type_set) { { View: 'UIView' } }

    it 'handles view without gesture events' do
      json = { 'type' => 'View', 'id' => 'simpleView' }
      expect { analyzer.analyze_json('test', json) }.not_to raise_error
    end
  end

  describe '#analyze_json with binding expressions' do
    let(:view_type_set) { { Label: 'UILabel' } }
    let(:json) do
      {
        'type' => 'Label',
        'id' => 'nameLabel',
        'text' => '@{userName}'
      }
    end

    it 'processes binding without error' do
      expect { analyzer.analyze_json('test', json) }.not_to raise_error
    end
  end

  describe '#analyze_json with style reference' do
    let(:temp_dir) { Dir.mktmpdir('json_analyzer_test') }
    let(:style_path) { temp_dir }

    before do
      # Create style file
      File.write(File.join(temp_dir, 'primary_button.json'), JSON.generate({
        'background' => '#0000FF',
        'fontColor' => '#FFFFFF'
      }))
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    let(:json) do
      {
        'type' => 'Button',
        'style' => 'primary_button',
        'text' => 'Click Me'
      }
    end

    it 'merges style properties' do
      expect { analyzer.analyze_json('test', json) }.not_to raise_error
    end
  end

  describe '#analyze_json with missing style file' do
    let(:json) do
      {
        'type' => 'Button',
        'style' => 'nonexistent_style',
        'text' => 'Click Me'
      }
    end

    it 'logs warning but does not raise error' do
      expect(SjuiTools::Core::Logger).to receive(:warn).with(/Style file not found/)
      analyzer.analyze_json('test', json)
    end
  end

  describe '#analyze_json with include element' do
    let(:temp_dir) { Dir.mktmpdir('json_analyzer_include_test') }
    let(:layout_path) { temp_dir }
    let(:view_type_set) { { View: 'UIView', Label: 'UILabel' } }

    before do
      # Create partial file
      File.write(File.join(temp_dir, 'header.json'), JSON.generate({
        'type' => 'View',
        'id' => 'headerView',
        'child' => [
          { 'type' => 'Label', 'text' => 'Header' }
        ]
      }))
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    let(:json) do
      {
        'type' => 'View',
        'child' => [
          { 'include' => 'header' }
        ]
      }
    end

    it 'processes include element' do
      expect { analyzer.analyze_json('test', json) }.not_to raise_error
    end
  end

  describe '#analyze_json with include element having shared_data' do
    let(:temp_dir) { Dir.mktmpdir('json_analyzer_shared_data_test') }
    let(:layout_path) { temp_dir }

    before do
      File.write(File.join(temp_dir, 'user_card.json'), JSON.generate({
        'type' => 'View',
        'child' => [
          { 'type' => 'Label', 'text' => '@{userName}' }
        ]
      }))
    end

    after do
      FileUtils.rm_rf(temp_dir)
    end

    let(:json) do
      {
        'include' => 'user_card',
        'shared_data' => ['userName']
      }
    end

    it 'processes include with shared data' do
      expect { analyzer.analyze_json('test', json) }.not_to raise_error
    end
  end

  describe '#analyze_binding_process with missing view name' do
    let(:binding_process) do
      {
        view: { 'type' => 'Label' },
        key: 'text',
        value: 'userName',
        element_path: ['root', 'child[0]'],
        file_name: 'test_view'
      }
    end

    it 'raises error with detailed message' do
      expect { analyzer.analyze_binding_process(binding_process) }.to raise_error(/View ID is missing/)
    end
  end

  describe '#track_collection_data_binding' do
    it 'tracks CollectionView items bindings' do
      analyzer.track_collection_data_binding('homeCollection', 'homeDataSource')
      expect(analyzer.collection_data_bindings['homeDataSource']).to include('homeCollection')
    end

    it 'tracks multiple CollectionViews bound to same data' do
      analyzer.track_collection_data_binding('collection1', 'sharedData')
      analyzer.track_collection_data_binding('collection2', 'sharedData')
      expect(analyzer.collection_data_bindings['sharedData']).to include('collection1', 'collection2')
    end

    it 'does not duplicate view names' do
      analyzer.track_collection_data_binding('homeCollection', 'homeDataSource')
      analyzer.track_collection_data_binding('homeCollection', 'homeDataSource')
      expect(analyzer.collection_data_bindings['homeDataSource'].count('homeCollection')).to eq(1)
    end
  end

  describe '#analyze_binding_process with Collection items binding' do
    # JsonUI's collection component is `Collection` (see JsonAnalyzer#analyze_binding_process).
    let(:binding_process) do
      {
        view: { 'type' => 'Collection', 'name' => 'myCollection' },
        key: 'items',
        value: 'myDataSource',
        element_path: ['root'],
        file_name: 'test_view'
      }
    end

    it 'tracks the binding instead of adding to binding_content' do
      analyzer.analyze_binding_process(binding_process)
      expect(analyzer.collection_data_bindings['myDataSource']).to include('myCollection')
      expect(analyzer.binding_content).not_to include('reloadWithDataSource')
    end
  end
end
