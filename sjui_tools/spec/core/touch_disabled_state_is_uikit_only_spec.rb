# frozen_string_literal: true

require 'core/attribute_validator'

# touchDisabledState is UIKit's hit-test mode — SJUIView: none / onlyMe /
# viewsWithoutTouchEnabled / viewsWithoutInList (attribute_definitions.json
# common, mode uikit, warn_outside_mode). No other render path reads it, and
# SwiftUI read any value of it as "stop everything" until jsonui-cli 1.9.0:
# written for another mode, it is named, a WARNING, not the usual INFO.
RSpec.describe 'sjui validator: touchDisabledState is UIKit only' do
  validator = ->(mode) { mode ? SjuiTools::Core::AttributeValidator.new(mode) : SjuiTools::Core::AttributeValidator.new }

  it 'names it outside UIKit' do
    v = validator.call(:swiftui)
    warnings = v.validate({ 'type' => 'View', 'touchDisabledState' => 'onlyMe' })
    named = warnings.grep(/touchDisabledState/)
    expect(named.size).to eq(1), warnings.inspect
    expect(named.first).to include("is UIKit only — The hit-test mode of SJUIView (UIKit)")
    expect(named.first).to include('userInteractionEnabled: false')
  end

  it 'in UIKit it is the mode, and a value that names none is a warning of its own' do
    v = validator.call(:uikit)
    expect(v.validate({ 'type' => 'View', 'touchDisabledState' => 'onlyMe' }).grep(/touchDisabledState/)).to eq([])
    wrong = validator.call(:uikit).validate({ 'type' => 'View', 'touchDisabledState' => 'stop' }).grep(/touchDisabledState/)
    expect(wrong.size).to eq(1)
    expect(wrong.first).not_to include('UIKit only')
  end
end
