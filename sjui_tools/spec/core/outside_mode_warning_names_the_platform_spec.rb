# frozen_string_literal: true

require 'core/attribute_validator'

# `add_outside_mode_warning` read the attribute's mode only, so one declared
# `warn_outside_mode` and limited by platform alone (no `mode`) was named
# "is  only" (ticket jui-build-mode-outside-infos-are-collected-and-never-
# printed). It names the platforms now; a mode-limited one keeps its words.
RSpec.describe 'sjui validator: the outside-mode warning names what limits the attribute' do
  def validator
    SjuiTools::Core::AttributeValidator.new(:swiftui)
  end

  it 'names the platforms of an attribute limited by platform alone' do
    v = validator
    v.definitions['View']['probeElsewhere'] = {
      'type' => 'string', 'platform' => %w[kotlin react], 'warn_outside_mode' => true,
      'description' => 'A probe declared for other platforms.'
    }
    warnings = v.validate({ 'type' => 'View', 'width' => 'matchParent', 'height' => 'wrapContent', 'probeElsewhere' => 'x' })
    expect(warnings).to eq(["[View] Attribute 'probeElsewhere' in 'View' is Kotlin/React only — A probe declared for other platforms."])
    expect(warnings.join).not_to include('is  only')
  end

  it 'keeps the words of a mode-limited one (touchDisabledState, UIKit)' do
    v = validator
    description = v.definitions['common']['touchDisabledState']['description']
    warnings = v.validate({ 'type' => 'View', 'width' => 'matchParent', 'height' => 'wrapContent', 'touchDisabledState' => 'onlyMe' })
    expect(warnings).to eq(["[View] Attribute 'touchDisabledState' in 'View' is UIKit only — #{description}"])
  end
end
