# frozen_string_literal: true

require 'core/attribute_validator'

# onPan on a TextField / TextView / Slider and onClick / onclick on a Web are
# written, build, and are never called: the component's own operation takes
# the gesture (measured 2026-10-03 on iOS codegen, iOS Dynamic, web and
# Android). Ruling 2026-10-03: not delivered — the SSoT declares them
# `notApplicableTo` on common, and the validator names them, in the same
# words on every face (the core is one file, mirrored). Tickets
# input-fields-never-call-onpan, rjui-slider-never-calls-onpan,
# web-component-onclick-is-never-delivered.
RSpec.describe 'rjui validator: an event declared not to reach a component is named' do
  def warnings_for(node)
    RjuiTools::Core::AttributeValidator.new.validate(node)
  end

  it 'names onPan on a TextField, its synonyms, a TextView and a Slider' do
    { 'TextField' => 'TextField', 'EditText' => 'TextField', 'Input' => 'TextField',
      'TextView' => 'TextView', 'Slider' => 'Slider' }.each do |type, section|
      found = warnings_for({ 'type' => type, 'onPan' => '@{h}' }).grep(/onPan/)
      expect(found.size).to eq(1), type
      expect(found.first).to include("'onPan' is not called on a #{section}: ")
    end
  end

  it 'names onClick and onclick on a Web' do
    expect(warnings_for({ 'type' => 'Web', 'onClick' => '@{h}' }).grep(/'onClick' is not called on a Web: the embedded page takes the taps/).size).to eq(1)
    expect(warnings_for({ 'type' => 'Web', 'onclick' => 'h' }).grep(/'onclick' is not called on a Web: /).size).to eq(1)
  end

  it 'control: onPan on a View and onClick on a Button say nothing' do
    expect(warnings_for({ 'type' => 'View', 'onPan' => '@{h}' }).grep(/onPan/)).to eq([])
    expect(warnings_for({ 'type' => 'Button', 'onClick' => '@{h}' }).grep(/onClick/)).to eq([])
  end
end
