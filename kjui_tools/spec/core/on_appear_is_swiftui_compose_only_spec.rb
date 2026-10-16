# frozen_string_literal: true

require 'core/attribute_validator'

# onAppear / onDisappear are SwiftUI / Compose lifecycle callbacks
# (attribute_definitions.json common, mode [swiftui, compose],
# warn_outside_mode). Web and UIKit draw no call to the handler; until this
# was declared, the validator filed them as an INFO no tool prints, so a
# layout built with no word while the handler it declares was never called.
RSpec.describe 'kjui validator: onAppear / onDisappear are SwiftUI / Compose only' do
  it 'is the mode in Compose: no word' do
    layout = { 'type' => 'View', 'onAppear' => '@{onScreenAppear}', 'onDisappear' => 'onScreenGone' }
    expect(KjuiTools::Core::AttributeValidator.new(:compose).validate(layout).grep(/onAppear|onDisappear/)).to eq([])
  end
end
