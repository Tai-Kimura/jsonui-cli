# frozen_string_literal: true

require 'core/attribute_validator'

# The generated iOS code crops an AspectFill image to its frame (ticket
# sjui-aspectfill-image-is-not-cropped-to-its-frame), except for a contentMode
# bound to a value that is AspectFill at run time on a frame that is not two
# numbers — a known gap. The SSoT declares it on Image / NetworkImage
# contentMode (`bindingInfo`, platform swift) and the validator names a bound
# contentMode once as INFO on that face only. 0 bound image contentModes on
# the three iOS consumers (2026-10-03).
RSpec.describe 'rjui validator: a bound contentMode with a declared limitation' do
  def infos_for(node)
    v = RjuiTools::Core::AttributeValidator.new
    v.validate(node)
    v.infos.grep(/contentMode' on/)
  end

  it 'names a bound Image / NetworkImage contentMode nowhere on this face' do
    %w[Image NetworkImage].each do |type|
      expect(infos_for({ 'type' => type, 'contentMode' => '@{mode}' }).size).to eq(0), type
    end
  end

  it 'control: a literal contentMode says nothing' do
    expect(infos_for({ 'type' => 'Image', 'contentMode' => 'AspectFill' })).to eq([])
  end
end
