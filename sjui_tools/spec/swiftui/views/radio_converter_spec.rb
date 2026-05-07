# frozen_string_literal: true

require 'swiftui/views/radio_converter'

RSpec.describe SjuiTools::SwiftUI::Views::RadioConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with items (radio group)' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'myRadio',
          'items' => ['Option 1', 'Option 2', 'Option 3']
        }
      end

      it 'generates VStack with radio options' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('VStack(alignment: .leading')
        expect(code).to include('HStack')
      end

      it 'generates radio circle images' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image(systemName:')
        expect(code).to include('largecircle.fill.circle')
        expect(code).to include('circle')
      end

      it 'includes all items' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Option 1')
        expect(code).to include('Option 2')
        expect(code).to include('Option 3')
      end
    end

    context 'with items and text label' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'colorChoice',
          'text' => 'Choose a color',
          'items' => ['Red', 'Green', 'Blue']
        }
      end

      it 'includes text label' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Text("Choose a color")')
      end
    end

    context 'with selectedValue binding' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'radio1',
          'items' => ['A', 'B'],
          'selectedValue' => '@{selectedOption}'
        }
      end

      it 'uses binding for selection' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.selectedOption')
      end
    end

    context 'without items (single radio button)' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'singleRadio',
          'group' => 'myGroup',
          'text' => 'Single Option'
        }
      end

      it 'generates single radio button' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('HStack')
        expect(code).to include('Image(systemName:')
        expect(code).to include('Text("Single Option")')
      end

      it 'uses group for state variable' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedMygroup')
      end
    end

    context 'without items and with onClick' do
      let(:action_manager) { SjuiTools::SwiftUI::ActionManager.new }
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'radio1',
          'onClick' => 'onRadioSelected'
        }
      end

      it 'generates action with data call' do
        converter = described_class.new(component, 0, action_manager)
        code = converter.convert

        expect(code).to include('data.onRadioSelected?()')
      end
    end

    context 'without items and without action_manager' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'radio1',
          'onClick' => 'customAction'
        }
      end

      it 'generates data call' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.customAction?()')
      end
    end

    context 'with fontColor' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'coloredRadio',
          'text' => 'Colored Radio',
          'fontColor' => '#FF0000'
        }
      end

      it 'applies foreground color' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.foregroundColor(')
      end
    end

    context 'with enabled false' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'disabledRadio',
          'enabled' => false
        }
      end

      it 'applies disabled and opacity modifiers' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.disabled(true)')
        expect(code).to include('.opacity(0.6)')
      end
    end

    context 'with quotes in text' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'quoteRadio',
          'text' => 'Say "Hello"',
          'items' => ['Option "A"', 'Option "B"']
        }
      end

      it 'escapes quotes in text' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Say \\"Hello\\"')
        expect(code).to include('Option \\"A\\"')
        expect(code).to include('Option \\"B\\"')
      end
    end

    context 'with default group' do
      let(:component) do
        {
          'type' => 'Radio',
          'id' => 'noGroupRadio',
          'text' => 'Default Group'
        }
      end

      it 'uses defaultGroup for state variable' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedDefaultgroup')
      end
    end
  end
end
