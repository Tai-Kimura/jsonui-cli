# frozen_string_literal: true

require 'swiftui/views/button_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ButtonConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic button' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Click Me',
          'onClick' => '@{handleClick}'
        }
      end

      it 'generates StateAwareButtonView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('StateAwareButtonView(')
        expect(code).to include('Click Me')
      end

      it 'includes action handler' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('action:')
        expect(code).to include('data.handleClick?()')
      end
    end

    context 'with background colors' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Styled',
          'background' => '#007AFF',
          'tapBackground' => '#0056B3',
          'disabledBackground' => '#CCCCCC'
        }
      end

      it 'includes backgroundColor parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('backgroundColor:')
      end

      it 'includes tapBackground parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('tapBackground:')
      end

      it 'includes disabledBackground parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('disabledBackground:')
      end
    end

    context 'with font styling' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Styled',
          'fontSize' => 18,
          'fontColor' => '#FFFFFF',
          'fontWeight' => 'bold'
        }
      end

      it 'includes fontSize parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontSize:')
      end

      it 'includes fontColor parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontColor:')
      end

      it 'includes fontWeight parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontWeight:')
      end
    end

    context 'with cornerRadius' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Styled',
          'cornerRadius' => 8
        }
      end

      it 'includes cornerRadius parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('cornerRadius: 8')
      end
    end

    context 'with disabled state' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Disabled',
          'enabled' => false,
          'disabledFontColor' => '#999999'
        }
      end

      it 'includes isEnabled parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('isEnabled:')
      end

      it 'includes disabledFontColor parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('disabledFontColor:')
      end
    end

    context 'with binding text' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Hello @{userName}'
        }
      end

      it 'interpolates binding expression' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.userName')
      end
    end

    context 'with paddings' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Padded',
          'paddings' => 16
        }
      end

      it 'includes padding parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('padding:')
        expect(code).to include('EdgeInsets')
      end
    end

    context 'with paddings array' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Padded',
          'paddings' => [10, 20]
        }
      end

      it 'includes padding with vertical/horizontal values' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('padding:')
        expect(code).to include('EdgeInsets')
      end
    end

    context 'with highlightColor' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Highlight',
          'highlightColor' => '#FF0000'
        }
      end

      it 'includes highlightColor parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('highlightColor:')
      end
    end

    context 'with highlightBackground' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Highlight BG',
          'highlightBackground' => '#FFFF00'
        }
      end

      it 'maps highlightBackground to the tapBackground parameter' do
        converter = described_class.new(component)
        code = converter.convert

        # StateAwareButtonView's pressed-state background parameter is
        # tapBackground; emitting the UIKit-era attribute name verbatim was
        # an "extra argument" compile error (codegen parity host, 2026-08-02).
        expect(code).to include('tapBackground:')
        expect(code).not_to include('highlightBackground:')
      end
    end

    context 'with both tapBackground and highlightBackground' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Both',
          'tapBackground' => '#00FF00',
          'highlightBackground' => '#FFFF00'
        }
      end

      it 'emits tapBackground once — the canonical spelling wins' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code.scan('tapBackground:').length).to eq(1)
      end
    end

    context 'with binding format onClick' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Action',
          'onClick' => '@{handleAction}'
        }
      end

      it 'generates action with handler invocation' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('data.handleAction?()')
      end
    end

    context 'with border' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Bordered',
          'borderWidth' => 1,
          'borderColor' => '#FF0000',
          'cornerRadius' => 8
        }
      end

      it 'includes border parameters' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('borderWidth: 1')
        expect(code).to include('borderColor:')
        expect(code).to include('cornerRadius: 8')
      end
    end

    context 'with border and no cornerRadius' do
      let(:component) do
        {
          'type' => 'Button',
          'text' => 'Bordered',
          'borderWidth' => 2,
          'borderColor' => 'primary_color'
        }
      end

      it 'includes border parameters without cornerRadius' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('borderWidth: 2')
        expect(code).to include('borderColor:')
        expect(code).not_to include('cornerRadius:')
      end
    end
  end

  describe 'event handler invocation' do
    before do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {}
    end

    it 'generates invoke() without arguments when handler type is () -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '(() -> Void)?' }
      }

      component = {
        'type' => 'Button',
        'id' => 'myButton',
        'text' => 'Click',
        'onClick' => '@{onClick}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onClick?()')
      expect(code).not_to include('onClick?("myButton"')
    end

    it 'generates invoke(viewId) when handler type is (Event) -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((Event) -> Void)?' }
      }

      component = {
        'type' => 'Button',
        'id' => 'myButton',
        'text' => 'Click',
        'onClick' => '@{onClick}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onClick?("myButton")')
    end

    it 'generates invoke(viewId) when handler type is (String) -> Void' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((String) -> Void)?' }
      }

      component = {
        'type' => 'Button',
        'id' => 'submitButton',
        'text' => 'Submit',
        'onClick' => '@{onClick}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onClick?("submitButton")')
    end

    it 'uses default button id when no id specified' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
        'onClick' => { 'name' => 'onClick', 'class' => '((Event) -> Void)?' }
      }

      component = {
        'type' => 'Button',
        'text' => 'Click',
        'onClick' => '@{onClick}'
      }

      converter = described_class.new(component)
      code = converter.convert

      expect(code).to include('data.onClick?("button")')
    end
  end
end
