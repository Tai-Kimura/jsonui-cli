# frozen_string_literal: true

require 'core/attribute_validator'

# An array whose items declare a vocabulary (safeAreaInsetPositions: top /
# bottom / leading / trailing / vertical / all) names an item declared in no
# case, as a top-level enum names a value (1.9.0; 4f's ruling on
# safeAreaInsetPositions: an undeclared word reserves nothing and is named).
# The validator checked the items' type only, so `left` and `Top` passed.
RSpec.describe 'attribute validator: an array item outside its declared vocabulary' do
  def warnings(value, type = 'View')
    Array(SjuiTools::Core::AttributeValidator.new.validate({ 'type' => type, 'safeAreaInsetPositions' => value }))
      .grep(/safeAreaInsetPositions/)
  end

  it 'names an item declared nowhere, and one declared in no case' do
    expect(warnings(%w[top left])).to eq(["[View] Attribute 'safeAreaInsetPositions[1]' in 'View' has invalid value 'left'. " \
                                          'Valid values: top, bottom, leading, trailing, vertical, all'])
    expect(warnings(%w[Top vertical], 'SafeAreaView')).to eq(["[SafeAreaView] Attribute 'safeAreaInsetPositions[0]' in 'SafeAreaView' has invalid value 'Top'. " \
                                                              "Valid values: top, bottom, leading, trailing, vertical, all — did you mean 'top'?"])
  end

  # A near miss in case is named with the declared spelling, as every enum's
  # is (the sentence the generated parsers use); a different word is not.
  it 'names the declared spelling of a near miss in case, for a single value and a list' do
    validate = ->(component) { Array(SjuiTools::Core::AttributeValidator.new.validate(component)) }
    expect(validate.('type' => 'View', 'orientation' => 'Horizontal').grep(/orientation/).first).to end_with("— did you mean 'horizontal'?")
    expect(validate.('type' => 'View', 'gravity' => %w[top Left]).grep(/gravity/).first).to end_with("— did you mean 'left'?")
    expect(validate.('type' => 'Label', 'textAlign' => 'centre').grep(/textAlign/).first).not_to include('did you mean')
  end

  it 'passes the declared items' do
    expect(warnings(%w[top bottom leading trailing])).to be_empty
    expect(warnings(%w[vertical])).to be_empty
    expect(warnings(%w[all])).to be_empty
  end
end
