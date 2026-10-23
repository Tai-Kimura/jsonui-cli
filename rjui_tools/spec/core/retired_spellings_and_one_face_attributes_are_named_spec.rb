# frozen_string_literal: true

require 'core/attribute_validator'

# 2.3.22 (ticket rjui-textfield-autofocus-read-but-not-defined): the
# converters stopped reading the fallback spellings they used to read beside a
# declared attribute, and declared what one or two faces draw for those faces
# only. A layout that writes a retired spelling is told the declared one
# (retired_attribute_spellings.json), not "Unknown attribute" alone; one that
# writes a face's own attribute elsewhere is told which face it is for.
RSpec.describe "rjui validator: retired spellings and one face's attributes are named" do
  def warnings_for(node)
    RjuiTools::Core::AttributeValidator.new(:react).validate({ 'width' => 'matchParent', 'height' => 'wrapContent' }.merge(node))
  end

  it 'names the declared attribute for a retired spelling' do
    expect(warnings_for('type' => 'Slider', 'min' => 0))
      .to eq(["[Slider] Unknown attribute 'min' for component type 'Slider' — no such name; use 'minimum'"])
    expect(warnings_for('type' => 'TextField', 'becomeFirstResponder' => true))
      .to eq(["[TextField] Unknown attribute 'becomeFirstResponder' for component type 'TextField' — no such name; use 'autoFocus'"])
  end

  it 'reads the table per component (CircleView.color is retired, Indicator.color is declared)' do
    expect(warnings_for('type' => 'CircleView', 'color' => '#FF0000').join).to include("use 'background'")
    expect(warnings_for('type' => 'Indicator', 'color' => '#FF0000').join).not_to include('Unknown attribute')
  end

  it 'keeps the plain sentence for a name the table does not hold' do
    expect(warnings_for('type' => 'Slider', 'noSuchName' => 1))
      .to eq(["[Slider] Unknown attribute 'noSuchName' for component type 'Slider'"])
  end

  it 'accepts autoFocus on TextField and TextView' do
    expect(warnings_for('type' => 'TextField', 'autoFocus' => true)).to be_empty
    expect(warnings_for('type' => 'TextView', 'autoFocus' => true)).to be_empty
  end

  it 'names the face an attribute is for when it is written on another' do
    expect(warnings_for('type' => 'Web', 'url' => 'https://example.com', 'allowZoom' => true).join)
      .to include("Attribute 'allowZoom' in 'Web' is Kotlin only")
  end
end
