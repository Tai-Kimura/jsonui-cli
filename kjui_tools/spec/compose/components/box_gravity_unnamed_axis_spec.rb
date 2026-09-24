# frozen_string_literal: true

require 'json'
require 'set'
require 'compose/components/container_component'

# kjui-box-gravity-unnamed-axis-centers-instead-of-start: a View with no
# orientation is a Compose `Box`, and its `gravity` becomes one
# `contentAlignment`. A single value names ONE axis; the axis it does not name
# takes the container default. Until 2026-09-24 kjui centred that axis instead —
# `top` gave TopCenter, `left` CenterStart — and an array with no vertical
# value centred vertically, while ios drew the same declaration at the
# leading/top corner.
#
# The expectations are derived from the SSoT, not copied from the converter:
# the values are `common.gravity`'s enum in attribute_definitions.json, and
# the defaults are `gravityDefaults.defaultGravity` in attribute_semantics.json.
# A converter that hardcodes a table cannot follow a change to either file,
# so a changed ruling turns this red instead of leaving the converter behind.
RSpec.describe KjuiTools::Compose::Components::ContainerComponent do
  shared_core = File.expand_path('../../../../shared/core', __dir__)
  definitions = JSON.parse(File.read(File.join(shared_core, 'attribute_definitions.json'), encoding: 'UTF-8'))
  semantics = JSON.parse(File.read(File.join(shared_core, 'attribute_semantics.json'), encoding: 'UTF-8'))

  enum = definitions.fetch('common').fetch('gravity').fetch('enum')
  default_vertical, default_horizontal = semantics.fetch('semantics').fetch('gravityDefaults')
                                                  .fetch('defaultGravity').split('|')

  axis_of = {
    'top' => [:v, 'Top'], 'bottom' => [:v, 'Bottom'], 'centerVertical' => [:v, 'Center'],
    'left' => [:h, 'Start'], 'right' => [:h, 'End'], 'centerHorizontal' => [:h, 'Center']
  }
  default_names = { 'top' => 'Top', 'bottom' => 'Bottom', 'start' => 'Start', 'end' => 'End' }

  expected = lambda do |values|
    v = default_names.fetch(default_vertical)
    h = default_names.fetch(default_horizontal)
    values.each do |value|
      if value == 'center'
        v = 'Center'
        h = 'Center'
      else
        axis, name = axis_of.fetch(value)
        axis == :v ? v = name : h = name
      end
    end
    v == 'Center' && h == 'Center' ? 'Alignment.Center' : "Alignment.#{v}#{h}"
  end

  def box(gravity)
    code = described_class.generate(
      { 'type' => 'View', 'gravity' => gravity,
        'child' => [{ 'type' => 'Label', 'text' => 'x' }] },
      0, Set.new
    )
    code = code[:code] if code.is_a?(Hash)
    code[/contentAlignment = (Alignment\.\w+)/, 1]
  end

  it 'reads the population and the defaults from the SSoT' do
    expect(enum).to match_array(axis_of.keys + ['center'])
    expect([default_vertical, default_horizontal]).to eq(%w[top start])
  end

  enum.each do |value|
    it "gives `#{value}` alone the SSoT's alignment" do
      expect(box(value)).to eq(expected.call([value]))
    end
  end

  %w[top bottom centerVertical].product(%w[left right centerHorizontal]).each do |pair|
    it "gives the array #{pair} the alignment of both named axes" do
      expect(box(pair)).to eq(expected.call(pair))
      expect(box(pair.join('|'))).to eq(expected.call(pair))
    end
  end

  %w[left right centerHorizontal].each do |horizontal|
    it "gives [#{horizontal}] (no vertical value) the default vertical axis" do
      expect(box([horizontal, horizontal])).to eq(expected.call([horizontal]))
    end
  end

  it 'emits no contentAlignment for a gravity that names neither axis' do
    expect(box('sideways')).to be_nil
  end

  it 'leaves a Column and a Row to their own defaults' do
    column = described_class.generate(
      { 'type' => 'View', 'orientation' => 'vertical', 'gravity' => 'top',
        'child' => [{ 'type' => 'Label', 'text' => 'x' }] }, 0, Set.new)
    column = column[:code] if column.is_a?(Hash)
    expect(column).to include('verticalArrangement = Arrangement.Top')
    expect(column).not_to include('horizontalAlignment')
  end
end
