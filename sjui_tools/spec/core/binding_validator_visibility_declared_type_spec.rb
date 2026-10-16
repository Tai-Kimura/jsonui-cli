# frozen_string_literal: true

require 'core/binding_validator'

# 'visibility' takes the String enum ("visible" / "gone" / "invisible"). A
# binding whose name starts is / has / can / should + capital is guessed to
# be Boolean — but only while the data section does not say: a declared
# class decides, as it does for colour bindings. The shared body
# (shared/core/binding_validator_core.rb) is mirrored byte-identical into
# each tool, so each tool pins the three cases.
RSpec.describe SjuiTools::Core::BindingValidator do
  def boolean_warnings(data)
    layout = { 'type' => 'View', 'data' => data, 'visibility' => '@{hasMoreVisibility}' }
    described_class.new.validate(layout).select { |w| w.include?('appears to be Boolean') }
  end

  it 'does not warn when the property is declared String, whatever its name' do
    expect(boolean_warnings([{ 'name' => 'hasMoreVisibility', 'class' => 'String' }])).to be_empty
  end

  it 'does not warn when the property is declared String?' do
    expect(boolean_warnings([{ 'name' => 'hasMoreVisibility', 'class' => 'String?' }])).to be_empty
  end

  it 'warns when the property is declared Bool' do
    expect(boolean_warnings([{ 'name' => 'hasMoreVisibility', 'class' => 'Bool' }]).size).to eq(1)
  end

  it 'warns when a property declared Boolean has a name the guess does not catch' do
    layout = { 'type' => 'View', 'data' => [{ 'name' => 'moreShown', 'class' => 'Boolean' }],
               'visibility' => '@{moreShown}' }
    expect(described_class.new.validate(layout).count { |w| w.include?('appears to be Boolean') }).to eq(1)
  end

  it 'falls back to the name guess when the property is not declared' do
    expect(boolean_warnings([{ 'name' => 'hasMoreVisibility' }]).size).to eq(1)
  end
end
