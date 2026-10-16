# frozen_string_literal: true

require 'core/attribute_validator'

# onAppear / onDisappear are SwiftUI / Compose lifecycle callbacks
# (attribute_definitions.json common, mode [swiftui, compose],
# warn_outside_mode). Web and UIKit draw no call to the handler; until this
# was declared, the validator filed them as an INFO no tool prints, so a
# layout built with no word while the handler it declares was never called.
RSpec.describe 'rjui validator: onAppear / onDisappear are SwiftUI / Compose only' do
  it 'names each on web, a WARNING' do
    warnings = RjuiTools::Core::AttributeValidator.new(:react).validate(
      { 'type' => 'View', 'onAppear' => '@{onScreenAppear}', 'onDisappear' => 'onScreenGone' }
    )
    %w[onAppear onDisappear].each do |attr|
      named = warnings.grep(/'#{attr}'/)
      expect(named.size).to eq(1), warnings.inspect
      expect(named.first).to include("Attribute '#{attr}' in 'View' is SwiftUI/Compose only — Lifecycle callback")
    end
  end
end
