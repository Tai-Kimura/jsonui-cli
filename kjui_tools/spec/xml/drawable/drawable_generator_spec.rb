# frozen_string_literal: true

require 'xml/drawable/drawable_generator'
require 'xml/helpers/resource_resolver'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe DrawableGenerator::Generator do
  let(:temp_dir) { Dir.mktmpdir }
  let(:generator) { described_class.new(temp_dir) }

  before do
    # Create the src/main/res/drawable directory structure
    FileUtils.mkdir_p(File.join(temp_dir, 'src', 'main', 'res', 'drawable'))
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#generate_for_component' do
    it 'returns nil for nil input' do
      expect(generator.generate_for_component(nil, 'Button')).to be_nil
    end

    it 'returns ripple for Button even with empty hash' do
      result = generator.generate_for_component({}, 'Button')
      expect(result).to include('ripple')
    end

    it 'generates ripple drawable for Button' do
      result = generator.generate_for_component({ 'background' => '#FFFFFF' }, 'Button')
      expect(result).to include('ripple')
    end

    it 'generates ripple drawable for Card' do
      result = generator.generate_for_component({ 'background' => '#FFFFFF' }, 'Card')
      expect(result).to include('ripple')
    end

    it 'generates ripple drawable for components with click handlers' do
      result = generator.generate_for_component({ 'background' => '#FFFFFF', 'onclick' => 'handleClick' }, 'View')
      expect(result).to include('ripple')
    end

    it 'returns nil for View without click or special attributes' do
      expect(generator.generate_for_component({}, 'View')).to be_nil
    end
  end

  describe '#get_background_drawable' do
    it 'returns nil for nil input' do
      expect(generator.get_background_drawable(nil, 'Button')).to be_nil
    end

    it 'generates state_list for components with state backgrounds' do
      result = generator.get_background_drawable({ 'background' => '#FFFFFF', 'disabledBackground' => '#CCCCCC' }, 'Button')
      expect(result).to include('selector')
    end

    it 'generates ripple drawable for Button' do
      result = generator.get_background_drawable({ 'background' => '#FFFFFF' }, 'Button')
      expect(result).to include('ripple')
    end

    it 'generates shape drawable for View with cornerRadius' do
      result = generator.get_background_drawable({ 'background' => '#FFFFFF', 'cornerRadius' => 8 }, 'View')
      expect(result).to include('shape')
    end

    it 'returns nil for View without special attributes' do
      result = generator.get_background_drawable({ 'text' => 'Hello' }, 'View')
      expect(result).to be_nil
    end
  end

  describe 'private methods' do
    describe '#needs_ripple?' do
      it 'returns true for Button' do
        expect(generator.send(:needs_ripple?, { 'background' => '#FFF' }, 'Button')).to be true
      end

      it 'returns true for Card' do
        expect(generator.send(:needs_ripple?, { 'background' => '#FFF' }, 'Card')).to be true
      end

      it 'returns true for ImageButton' do
        expect(generator.send(:needs_ripple?, { 'background' => '#FFF' }, 'ImageButton')).to be true
      end

      it 'returns true for ListItem' do
        expect(generator.send(:needs_ripple?, { 'background' => '#FFF' }, 'ListItem')).to be true
      end

      it 'returns truthy when onClick present' do
        expect(generator.send(:needs_ripple?, { 'onClick' => 'handleClick' }, 'View')).to be_truthy
      end

      it 'returns truthy when onclick present' do
        expect(generator.send(:needs_ripple?, { 'onclick' => 'handleClick' }, 'View')).to be_truthy
      end

      it 'returns false for View without interactivity' do
        expect(generator.send(:needs_ripple?, {}, 'View')).to be false
      end

      it 'returns false for nil json_data' do
        expect(generator.send(:needs_ripple?, nil, 'Button')).to be false
      end
    end

    describe '#needs_shape?' do
      it 'returns true when cornerRadius is present' do
        expect(generator.send(:needs_shape?, { 'cornerRadius' => 8 })).to be_truthy
      end

      it 'returns true when borderWidth is present' do
        expect(generator.send(:needs_shape?, { 'borderWidth' => 2 })).to be_truthy
      end

      it 'returns true when borderColor is present' do
        expect(generator.send(:needs_shape?, { 'borderColor' => '#CCC' })).to be_truthy
      end

      it 'returns true when background is hex color' do
        expect(generator.send(:needs_shape?, { 'background' => '#FFFFFF' })).to be_truthy
      end

      it 'returns true when gradient is present' do
        expect(generator.send(:needs_shape?, { 'gradient' => {} })).to be_truthy
      end

      it 'returns false for nil json_data' do
        expect(generator.send(:needs_shape?, nil)).to be false
      end

      it 'returns false for empty hash' do
        expect(generator.send(:needs_shape?, {})).to be_falsy
      end
    end

    describe '#needs_state_list?' do
      it 'returns truthy for disabledBackground' do
        expect(generator.send(:needs_state_list?, { 'disabledBackground' => '#CCC' })).to be_truthy
      end

      it 'returns truthy for tapBackground' do
        expect(generator.send(:needs_state_list?, { 'tapBackground' => '#CCC' })).to be_truthy
      end

      it 'returns truthy for pressedBackground' do
        expect(generator.send(:needs_state_list?, { 'pressedBackground' => '#CCC' })).to be_truthy
      end

      it 'returns truthy for selectedBackground' do
        expect(generator.send(:needs_state_list?, { 'selectedBackground' => '#CCC' })).to be_truthy
      end

      it 'returns truthy for focusedBackground' do
        expect(generator.send(:needs_state_list?, { 'focusedBackground' => '#CCC' })).to be_truthy
      end

      it 'returns false for no state backgrounds' do
        expect(generator.send(:needs_state_list?, { 'background' => '#FFF' })).to be_falsy
      end

      it 'returns false for nil json_data' do
        expect(generator.send(:needs_state_list?, nil)).to be false
      end
    end
  end

  describe '#create_shape_drawable_for_state (via send for private method)' do
    it 'returns nil for nil state_data' do
      expect(generator.send(:create_shape_drawable_for_state, nil)).to be_nil
    end

    it 'creates shape drawable for state data' do
      result = generator.send(:create_shape_drawable_for_state, { 'background' => '#FF0000', 'cornerRadius' => 8 })
      expect(result).not_to be_nil
      expect(result).to include('shape')
    end
  end
end
