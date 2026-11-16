# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A Collection's `insets` is read as `paddings` reads them (the SSoT's
# Collection.insets, jsonui-cli 1.9.0): 1, 2 or 4 values, an array or a string
# separated by `|`; one, every side; two, [vertical, horizontal]; four, [top,
# right, bottom, left] (right the end, left the start); any other value pads
# nothing. SwiftJsonUI Dynamic and both Compose paths read it so. Until
# jsonui-cli 1.9.0 sjui read four as [top, left, bottom, right] — `[0, 30, 0,
# 0]` put the cells 30pt in, where Dynamic put them at the start (measured on
# the ConformanceHost) — read a value it could not parse as 0, and on a
# horizontal row also set its leading / trailing spacers from [1] and [3], so
# the horizontal sides were applied twice (the first cell 60pt in).
#
# The drawn arm is InsetsOrderProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'width' => 300, 'height' => 80, 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)).convert.to_s
  end

  def insets_line(extra)
    emit(extra).lines.map(&:strip).grep(/EdgeInsets|insetLeading|insetTrailing/)
  end

  it 'four values are [top, right, bottom, left]' do
    expect(insets_line('insets' => [1, 2, 3, 4])).to eq(['contentInsets: EdgeInsets(top: 1, leading: 4, bottom: 3, trailing: 2)'])
    expect(insets_line('insets' => [0, 30, 0, 0])).to eq(['contentInsets: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 30)'])
  end

  it 'the string form, one value and two values' do
    expect(insets_line('insets' => '1|2|3|4')).to eq(['contentInsets: EdgeInsets(top: 1, leading: 4, bottom: 3, trailing: 2)'])
    expect(insets_line('insets' => [10])).to eq(['contentInsets: EdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10)'])
    expect(insets_line('insets' => '4|20')).to eq(['contentInsets: EdgeInsets(top: 4, leading: 20, bottom: 4, trailing: 20)'])
  end

  it 'any other value pads nothing' do
    [[1, 2, 3], 'a|b', '1|x|2|3', [], ''].each do |value|
      expect(insets_line('insets' => value)).to eq([]), value.inspect
    end
  end

  it 'a horizontal row: the insets are its content padding, once; insetHorizontal its spacers' do
    expect(insets_line('layout' => 'horizontal', 'insets' => [0, 0, 0, 30]))
      .to eq(['contentInsets: EdgeInsets(top: 0, leading: 30, bottom: 0, trailing: 0)'])
    expect(insets_line('layout' => 'horizontal', 'insets' => [0, 30, 0, 0], 'insetHorizontal' => 8))
      .to eq(['insetLeading: 8,', 'insetTrailing: 8,', 'contentInsets: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 30)'])
  end

  it 'type-checks the padding it emits', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView')
    codes = [emit('insets' => [1, 2, 3, 4]), emit('insets' => '4|20'), emit('layout' => 'horizontal', 'insets' => [0, 30, 0, 0], 'insetHorizontal' => 8)]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
