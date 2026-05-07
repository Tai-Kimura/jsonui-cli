# frozen_string_literal: true

require 'swiftui/action_manager'

RSpec.describe SjuiTools::SwiftUI::ActionManager do
  describe '#register_action' do
    it 'registers an action and returns handler name' do
      manager = described_class.new
      handler = manager.register_action('submitForm', 'button')

      expect(handler).to eq('submitForm')
      expect(manager.actions['submitForm']).not_to be_nil
    end

    it 'returns nil for nil action name' do
      manager = described_class.new
      expect(manager.register_action(nil)).to be_nil
    end

    it 'returns nil for empty action name' do
      manager = described_class.new
      expect(manager.register_action('')).to be_nil
    end

    it 'sanitizes action names with special characters' do
      manager = described_class.new
      handler = manager.register_action('on-click-action!', 'button')

      expect(handler).to eq('onclickaction')
    end

    it 'adds prefix if action starts with number' do
      manager = described_class.new
      handler = manager.register_action('123action', 'button')

      expect(handler).to eq('action123action')
    end

    it 'makes unique names for duplicate actions' do
      manager = described_class.new
      handler1 = manager.register_action('myAction', 'button')
      handler2 = manager.register_action('myAction', 'button')

      expect(handler1).to eq('myAction')
      expect(handler2).to eq('myAction1')
    end

    it 'stores component type' do
      manager = described_class.new
      manager.register_action('tapHandler', 'image')

      expect(manager.actions['tapHandler'][:component_type]).to eq('image')
    end
  end

  describe '#generate_action_handlers' do
    it 'returns empty array when no actions registered' do
      manager = described_class.new
      expect(manager.generate_action_handlers).to eq([])
    end

    it 'generates handler functions for registered actions' do
      manager = described_class.new
      manager.register_action('onSubmit', 'button')

      handlers = manager.generate_action_handlers

      expect(handlers.length).to eq(1)
      handler_text = handlers.first.join("\n")
      expect(handler_text).to include('func onSubmit()')
    end

    it 'includes action comments' do
      manager = described_class.new
      manager.register_action('handleClick', 'button')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('// Action: handleClick')
    end

    it 'generates button-specific comments' do
      manager = described_class.new
      manager.register_action('buttonTap', 'button')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('Navigate to another view')
    end

    it 'generates textfield-specific comments' do
      manager = described_class.new
      manager.register_action('onTextChange', 'textfield')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('Validate input')
    end

    it 'generates slider-specific comments' do
      manager = described_class.new
      manager.register_action('onSlide', 'slider')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('Update related UI elements')
    end

    it 'generates image-specific comments' do
      manager = described_class.new
      manager.register_action('onImageTap', 'image')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('Show fullscreen image')
    end

    it 'generates radio-specific comments' do
      manager = described_class.new
      manager.register_action('onRadioSelect', 'radio')

      handlers = manager.generate_action_handlers
      handler_text = handlers.first.join("\n")

      expect(handler_text).to include('Update selection state')
    end
  end

  describe '#actions' do
    it 'returns all registered actions' do
      manager = described_class.new
      manager.register_action('action1', 'button')
      manager.register_action('action2', 'image')

      expect(manager.actions.keys).to contain_exactly('action1', 'action2')
    end
  end
end
