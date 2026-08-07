# frozen_string_literal: true

require 'swiftui/views/button_converter'

# Characterization of ButtonConverter emit paths that button_converter_spec
# does not exercise: partialAttributes, fontFamily binding, the legacy `font`
# weight spelling, and per-side padding assembly.
RSpec.describe SjuiTools::SwiftUI::Views::ButtonConverter do
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
        'type' => 'Button', 'text' => 'Tap',
        'partialAttributes' => [
          { 'range' => [0, 2], 'fontColor' => '#FF0000' },
          { 'range' => 'tap_here', 'underline' => true }
        ],
        'fontFamily' => '@{fam}'
      )
    end

    it 'emits a numeric range as a half-open Swift range' do
      expect(code).to include('range: 0..<2,')
      expect(code).to include('fontColor: SwiftJsonUIConfiguration.shared.getColor(for: "#FF0000") ?? Color.black')
    end

    it 'localizes a string range as a textPattern' do
      expect(code).to include('textPattern: "tap_here".localized(),')
      expect(code).to include('underline: true')
    end

    it 'binds fontFamily to data' do
      expect(code).to include('fontFamily: data.fam,')
    end

    # `None` is the lineStyle enum's spelling for "no line"; the read site
    # tested the face for truthiness, and an object is truthy.
    it 'draws no line for a partial whose lineStyle is None' do
      styled = convert(
        'type' => 'Button', 'text' => 'Tap',
        'partialAttributes' => [
          { 'range' => [0, 2], 'underline' => { 'lineStyle' => 'None' } }
        ]
      )

      expect(styled).to include('PartialAttribute(')
      expect(styled).not_to include('underline: true')
    end
  end

  describe 'legacy font attribute' do
    it 'passes font through as the fontWeight string' do
      expect(convert('type' => 'Button', 'text' => 'F', 'font' => 'bold'))
        .to include('fontWeight: "bold",')
    end
  end

  describe 'per-side padding attributes' do
    it 'assembles EdgeInsets from individual sides, defaulting the rest to 0' do
      code = convert('type' => 'Button', 'text' => 'PS',
                     'paddingTop' => 2, 'leftPadding' => 3)
      expect(code).to include('padding: EdgeInsets(top: 2, leading: 3, bottom: 0, trailing: 0),')
    end
  end
end
