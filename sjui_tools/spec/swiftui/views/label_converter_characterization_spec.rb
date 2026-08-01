# frozen_string_literal: true

require 'swiftui/views/label_converter'

# Characterization of LabelConverter emit paths that label_converter_spec does
# not exercise: partialAttributes variants, font family/disabled color, line
# spacing derivations, truncation, and edgeInset padding forms.
RSpec.describe SjuiTools::SwiftUI::Views::LabelConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def convert(component)
    described_class.new(component, 0, nil, nil).convert
  end

  describe 'partialAttributes' do
    let(:code) do
      convert(
        'type' => 'Label', 'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => '@{pattern}', 'fontSize' => 20, 'fontWeight' => 'bold',
            'strikethrough' => true, 'background' => '#FF0000',
            'onClick' => '@{onTapLink}' },
          { 'range' => 'static_key', 'underline' => true }
        ]
      )
    end

    it 'binds a @{...} range as a data-driven textPattern' do
      expect(code).to include('textPattern: data.pattern,')
    end

    it 'localizes a snake_case range through StringManager' do
      expect(code).to include('textPattern: "static_key".localized(),')
    end

    it 'emits fontSize / fontWeight / strikethrough / backgroundColor / onClick' do
      expect(code).to include('fontSize: 20,')
      expect(code).to include('fontWeight: .bold,')
      expect(code).to include('strikethrough: true,')
      expect(code).to include('backgroundColor: SwiftJsonUIConfiguration.shared.getColor(for: "#FF0000") ?? Color.black,')
      expect(code).to include('onClick: { data.onTapLink?() }')
    end

    it 'emits underline in the second partial' do
      expect(code).to include('underline: true')
    end
  end

  describe 'fontFamily' do
    it 'binds @{...} to data' do
      expect(convert('type' => 'Label', 'text' => 't', 'fontFamily' => '@{familyProp}'))
        .to include('fontFamily: data.familyProp,')
    end

    it 'quotes a static family name' do
      expect(convert('type' => 'Label', 'text' => 't', 'fontFamily' => 'Menlo'))
        .to include('fontFamily: "Menlo",')
    end
  end

  describe 'disabledFontColor when enabled is false' do
    it 'uses the disabled color as the base font color' do
      code = convert('type' => 'Label', 'text' => 't', 'enabled' => false,
                     'disabledFontColor' => '#888888')
      expect(code).to include('fontColor: SwiftJsonUIConfiguration.shared.getColor(for: "#888888") ?? Color.black,')
    end
  end

  describe 'line spacing' do
    it 'derives lineSpacing from lineHeightMultiple and fontSize' do
      code = convert('type' => 'Label', 'text' => 't',
                     'lineHeightMultiple' => 1.5, 'fontSize' => 20)
      expect(code).to include('lineSpacing: 10.0,')
    end

    it 'passes lineSpacing through as a float' do
      expect(convert('type' => 'Label', 'text' => 't', 'lineSpacing' => 4))
        .to include('lineSpacing: 4.0,')
    end
  end

  describe 'truncation and scaling' do
    it 'maps Clip to .tail truncation (SwiftUI has no clip mode)' do
      expect(convert('type' => 'Label', 'text' => 't', 'lineBreakMode' => 'Clip'))
        .to include('.truncationMode(.tail)')
    end

    it 'applies a bare minimumScaleFactor' do
      expect(convert('type' => 'Label', 'text' => 't', 'minimumScaleFactor' => 0.5))
        .to include('.minimumScaleFactor(0.5)')
    end
  end

  describe 'edgeInset padding forms' do
    it 'maps a 1-element array to uniform padding' do
      expect(convert('type' => 'Label', 'text' => 't', 'edgeInset' => [8]))
        .to include('.padding(8)')
    end

    it 'maps a 2-element array to vertical/horizontal padding' do
      code = convert('type' => 'Label', 'text' => 't', 'edgeInset' => [4, 12])
      expect(code).to include('.padding(.vertical, 4)')
      expect(code).to include('.padding(.horizontal, 12)')
    end

    it 'maps a numeric value to uniform padding' do
      expect(convert('type' => 'Label', 'text' => 't', 'edgeInset' => 6))
        .to include('.padding(6)')
    end
  end
end
