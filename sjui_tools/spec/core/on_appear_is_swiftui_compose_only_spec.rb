# frozen_string_literal: true

require 'core/attribute_validator'

# onAppear / onDisappear are SwiftUI / Compose lifecycle callbacks
# (attribute_definitions.json common, mode [swiftui, compose],
# warn_outside_mode). Web and UIKit draw no call to the handler; until this
# was declared, the validator filed them as an INFO no tool prints, so a
# layout built with no word while the handler it declares was never called.
RSpec.describe 'sjui validator: onAppear / onDisappear are SwiftUI / Compose only' do
  layout = { 'type' => 'View', 'onAppear' => '@{onScreenAppear}', 'onDisappear' => 'onScreenGone' }

  it 'is the mode in SwiftUI: no word' do
    expect(SjuiTools::Core::AttributeValidator.new(:swiftui).validate(layout).grep(/onAppear|onDisappear/)).to eq([])
  end

  it 'names each in UIKit, a WARNING' do
    warnings = SjuiTools::Core::AttributeValidator.new(:uikit).validate(layout)
    %w[onAppear onDisappear].each do |attr|
      expect(warnings.grep(/Attribute '#{attr}' in 'View' is SwiftUI\/Compose only/).size).to eq(1), warnings.inspect
    end
  end
end
