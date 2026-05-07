# frozen_string_literal: true

require 'swiftui/views/icon_label_converter'
require 'swiftui/action_manager'

RSpec.describe SjuiTools::SwiftUI::Views::IconLabelConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'without onclick' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Settings' } }

      it 'generates IconLabelView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('IconLabelView(')
        expect(code).to include('text: "Settings"')
      end
    end

    context 'with onClick' do
      let(:action_manager) { SjuiTools::SwiftUI::ActionManager.new }
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Click Me', 'onClick' => 'handleTap' } }

      it 'generates IconLabelButton' do
        converter = described_class.new(component, 0, action_manager)
        code = converter.convert

        expect(code).to include('IconLabelButton(')
        expect(code).to include('action: {')
        expect(code).to include('data.handleTap?()')
      end
    end

    context 'with onClick but no action_manager' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Click Me', 'onClick' => 'customAction' } }

      it 'generates action with data call' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('action: {')
        expect(code).to include('data.customAction?()')
      end
    end

    context 'with icons' do
      let(:component) do
        {
          'type' => 'IconLabel',
          'text' => 'Like',
          'icon_on' => 'heart_filled',
          'icon_off' => 'heart_empty'
        }
      end

      it 'includes icon parameters' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconOn: "heart_filled"')
        expect(code).to include('iconOff: "heart_empty"')
      end
    end

    context 'with icon positions' do
      it 'handles left position' do
        component = { 'type' => 'IconLabel', 'text' => 'Test', 'iconPosition' => 'left' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconPosition: .left')
      end

      it 'handles right position' do
        component = { 'type' => 'IconLabel', 'text' => 'Test', 'iconPosition' => 'right' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconPosition: .right')
      end

      it 'handles top position' do
        component = { 'type' => 'IconLabel', 'text' => 'Test', 'iconPosition' => 'top' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconPosition: .top')
      end

      it 'handles bottom position' do
        component = { 'type' => 'IconLabel', 'text' => 'Test', 'iconPosition' => 'bottom' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconPosition: .bottom')
      end

      it 'defaults to left' do
        component = { 'type' => 'IconLabel', 'text' => 'Test' }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconPosition: .left')
      end
    end

    context 'with iconSize' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'iconSize' => 24 } }

      it 'includes iconSize' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconSize: 24')
      end
    end

    context 'with iconMargin' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'iconMargin' => 8 } }

      it 'includes iconMargin' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('iconMargin: 8')
      end
    end

    context 'with fontSize' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'fontSize' => 16 } }

      it 'includes fontSize' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontSize: 16')
      end
    end

    context 'with fontColor' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'fontColor' => '#FF0000' } }

      it 'includes fontColor' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontColor:')
      end
    end

    context 'with selectedFontColor' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'selectedFontColor' => '#00FF00' } }

      it 'includes selectedFontColor' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedFontColor:')
      end
    end

    context 'with font name' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'font' => 'Helvetica' } }

      it 'includes fontName' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontName: "Helvetica"')
      end
    end

    context 'with bold font' do
      let(:component) { { 'type' => 'IconLabel', 'text' => 'Test', 'font' => 'bold' } }

      it 'does not include fontName for bold' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).not_to include('fontName:')
      end
    end
  end
end
