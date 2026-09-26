# frozen_string_literal: true

require 'core/attribute_validator'

# The shared validator's two Collection sentences (shared/core, mirrored):
# - `items` is a binding only since 2026-09-26: the array form was declared
#   and drawn by no platform, codegen or Dynamic, and used by no face (all
#   116 face Collections bind it). A literal array is named for what it is.
# - `bind` on a Collection (a Table is one) is not its data source.
# Ticket collection-attributes-declared-but-not-drawn-on-some-paths.
RSpec.describe 'shared validator: Collection items and bind' do
  let(:validator) { SjuiTools::Core::AttributeValidator.new(:swiftui) }

  def said(extra, type: 'Collection')
    node = { 'type' => type, 'id' => 'list', 'width' => 100, 'height' => 100, 'cellIdProperty' => 'id' }.merge(extra)
    validator.validate(node).grep(/'items'|'bind'/)
  end

  it 'names a literal array: a binding is what every platform draws' do
    expect(said({ 'items' => %w[a b] })).to eq(
      ["[id=list] Attribute 'items' in 'Collection' takes a binding (\"@{…}\"), got a literal array: " \
       'no platform draws a literal here — bind it']
    )
  end

  it 'says nothing about a bound items (the control)' do
    expect(said({ 'items' => '@{rows}' })).to eq([])
  end

  it 'says bind is not the data source, on a Collection and on a Table' do
    %w[Collection Table].each do |type|
      expect(said({ 'items' => '@{rows}', 'bind' => '@{rows}' }, type: type)).to eq(
        ["[id=list] 'bind' is not a Collection's data source; use 'items' (e.g. \"items\": \"@{rows}\")"]
      ), type
    end
  end

  it 'says nothing about bind where it is the primary value (the control)' do
    node = { 'type' => 'Switch', 'id' => 'toggle', 'width' => 100, 'height' => 40, 'bind' => '@{isOn}' }
    expect(validator.validate(node).grep(/'bind'/)).to eq([])
  end
end

# setTargetAsDelegate / setTargetAsDataSource are UIKit's (SJUICollectionView
# reads them); the SwiftUI paths have no delegate or data source to set.
RSpec.describe 'shared validator: setTargetAsDelegate / setTargetAsDataSource are mode uikit' do
  %w[setTargetAsDelegate setTargetAsDataSource].each do |attr|
    it "#{attr}: valid in UIKit, an info (not an attribute of this mode) in SwiftUI" do
      node = { 'type' => 'Collection', 'id' => 'list', 'width' => 100, 'height' => 100, 'cellIdProperty' => 'id', attr => true }
      in_uikit = SjuiTools::Core::AttributeValidator.new(:uikit)
      expect(in_uikit.validate(node).grep(/#{attr}/)).to eq([])
      expect(in_uikit.instance_variable_get(:@infos).grep(/#{attr}/)).to eq([])

      in_swiftui = SjuiTools::Core::AttributeValidator.new(:swiftui)
      expect(in_swiftui.validate(node).grep(/#{attr}/)).to eq([])
      expect(in_swiftui.instance_variable_get(:@infos).grep(/#{attr}/)).to eq(
        ["[id=list] Attribute '#{attr}' in 'Collection' is for Uikit mode (current: Swiftui)"]
      )
    end
  end

  # Ruling 2026-09-26: a flow Collection wraps by content width, and no face
  # reads a column count there — its own or a section's. Named, so the
  # declaration does not read as drawn.
  describe 'columns on a flow Collection' do
    def flow_said(extra)
      node = { 'type' => 'Collection', 'id' => 'list', 'width' => 100, 'height' => 100, 'cellIdProperty' => 'id',
               'items' => '@{rows}' }.merge(extra)
      SjuiTools::Core::AttributeValidator.new(:swiftui).validate(node).grep(/columns/)
    end

    it "names the Collection's columns and each section's, on every spelling of flow" do
      %w[flow Flow leftAligned LeftAligned].each do |spelling|
        expect(flow_said({ 'layout' => spelling, 'columns' => 2,
                           'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell', 'columns' => 3 }] })).to eq(
          ['[id=list] columns has no effect on a flow Collection (it wraps by content width)',
           '[id=list] sections[1].columns has no effect on a flow Collection (it wraps by content width)']
        ), spelling
      end
      expect(flow_said({ 'orientation' => 'flow', 'columns' => 1 })).to eq(
        ['[id=list] columns has no effect on a flow Collection (it wraps by content width)']
      )
    end

    it 'says nothing where columns draws: a grid, a horizontal lane count, a flow turned horizontal (the controls)' do
      expect(flow_said({ 'columns' => 2, 'sections' => [{ 'cell' => 'ACell', 'columns' => 3 }] })).to eq([])
      expect(flow_said({ 'layout' => 'horizontal', 'columns' => 2 })).to eq([])
      expect(flow_said({ 'layout' => 'flow', 'horizontalScroll' => true, 'columns' => 2 })).to eq([])
      expect(flow_said({ 'layout' => 'flow', 'sections' => [{ 'cell' => 'ACell' }] })).to eq([])
    end
  end
end
