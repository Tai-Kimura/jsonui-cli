# frozen_string_literal: true

require 'swiftui/views/button_converter'

# Regression: rjui-button-image-attribute-dropped (iOS half).
#
# `image` was declared for Button in attribute_definitions.json, so the
# unknown-attribute validation passed it, but no SwiftUI converter read it —
# an icon-only button generated a StateAwareButtonView with an empty label.
# UIKit had read `image` all along, so the two iOS modes disagreed.
RSpec.describe SjuiTools::SwiftUI::Views::ButtonConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def convert(component)
    described_class.new({ 'type' => 'Button' }.merge(component)).convert
  end

  describe 'Button#image' do
    it 'passes the asset name to the button view' do
      expect(convert('image' => 'menu')).to include('image: "menu"')
    end

    it 'drops the "Button" placeholder for an icon-only button' do
      # The placeholder is for a button with nothing in it; an icon-only
      # button would otherwise render the word "Button" beside its icon.
      code = convert('image' => 'menu')
      expect(code).to include('text: ""')
      expect(code).not_to include('text: "Button"')
    end

    it 'keeps the placeholder when there is neither text nor icon' do
      expect(convert({})).to include('text: "Button"')
    end

    it 'keeps an explicit label alongside the icon' do
      code = convert('image' => 'menu', 'text' => 'Menu')
      expect(code).to include('image: "menu"')
      expect(code).to include('text: "Menu"')
    end

    it 'tints the icon with fontColor' do
      # Without a tint the icon renders as authored; with one it becomes a
      # template so a currentColor-style asset follows the label colour.
      code = convert('image' => 'menu', 'fontColor' => '#FFFFFF')
      expect(code).to match(/imageTint: .+#FFFFFF/)
    end

    it 'prefers tintColor over fontColor for the icon' do
      code = convert('image' => 'menu', 'fontColor' => '#FFFFFF', 'tintColor' => '#FF0000')
      expect(code).to match(/imageTint: .+#FF0000/)
      expect(code).to match(/fontColor: .+#FFFFFF/)
    end

    it 'passes no tint when the layout asked for none' do
      # Icon() / .renderingMode(.template) would flatten a multi-colour asset.
      expect(convert('image' => 'menu')).not_to include('imageTint:')
    end

    it 'resolves a bound name through data' do
      expect(convert('image' => '@{iconName}')).to include('image: data.iconName')
    end

    it 'leaves a text-only button exactly as before' do
      code = convert('text' => 'Save')
      expect(code).not_to include('image:')
      expect(code).not_to include('imageTint:')
      expect(code).not_to include('Requires SwiftJsonUI')
    end

    it 'records the library version the emitted call needs' do
      # image:/imageTint: are new parameters — icon output does not compile
      # against an older SwiftJsonUI.
      expect(convert('image' => 'menu')).to include('// Requires SwiftJsonUI >= 10.9.0 (Button image)')
    end
  end
end
