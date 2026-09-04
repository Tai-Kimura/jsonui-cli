# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# The cell address `{collectionId}_item_{index}` must be emitted from ONE
# place.
#
# It used to be emitted from sixteen, spread over nine shape methods
# (non-responsive, non-lazy horizontal / grid / flow, paging, flow layout,
# sections vertical, sections, legacy), each an identical line under an
# identical `if @component['id']` guard. A change to the cell address then
# had to be made sixteen times or be silently partial — which is the shape
# of defect the dynamic renderer already learned from: its own comment says
# the identifier was moved onto the one builder every cell path calls "so a
# tenth inherits it rather than having to remember, which is exactly how the
# static side lost two arms".
#
# This is a source gate, not a behaviour test, because that is where the
# hazard lives: the emitted Swift is identical whether there is one site or
# sixteen, so no generated-output assertion can see the difference. What it
# guards is the next change to this line.
RSpec.describe 'Collection cell identifier emit sites' do
  CONVERTER_SOURCE = File.expand_path(
    '../../../lib/swiftui/views/collection_converter.rb', __dir__
  )

  def emit_lines
    File.readlines(CONVERTER_SOURCE).each_with_index.select do |line, _i|
      line.include?('_item_') && line.include?('accessibilityIdentifier')
    end
  end

  it 'emits the cell address from exactly one place' do
    lines = emit_lines
    detail = lines.map { |line, i| "  #{i + 1}: #{line.strip}" }.join("\n")
    expect(lines.size).to eq(1), "expected 1 emit site, found #{lines.size}:\n#{detail}"
  end

  it 'emits it from the shared helper, not from a shape method' do
    source = File.read(CONVERTER_SOURCE)
    helper = source[/def apply_cell_item_identifier.*?\n        end/m]
    expect(helper).not_to be_nil, 'apply_cell_item_identifier is gone — did a shape method inline it again?'
    expect(helper).to include('accessibilityIdentifier')
    expect(helper).to include("_item_")
  end

  it 'keeps every cell path routed through that helper' do
    # Nine shape methods call it; the count is asserted as "more than one
    # caller" rather than a fixed number, because adding a Collection shape
    # is legitimate and adding a SEVENTEENTH inlined copy is not.
    callers = File.readlines(CONVERTER_SOURCE).count { |l| l.include?('apply_cell_item_identifier(') }
    # 16 call sites + 1 definition
    expect(callers).to be >= 2
    expect(callers).to eq(17)
  end

  it 'still emits the address for an id-bearing Collection' do
    # The gate above would also pass if the emit disappeared entirely.
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    code = SjuiTools::SwiftUI::Views::CollectionConverter.new(
      { 'type' => 'Collection', 'id' => 'target', 'items' => '@{items}',
        'columns' => 1, 'sections' => [{ 'cell' => 'FooCell' }] }, 0, nil, nil, []
    ).convert
    expect(code).to include('.accessibilityIdentifier("target_item_\\(cellIndex)")')
  ensure
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  it 'emits nothing for a Collection without an id' do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
    code = SjuiTools::SwiftUI::Views::CollectionConverter.new(
      { 'type' => 'Collection', 'items' => '@{items}',
        'columns' => 1, 'sections' => [{ 'cell' => 'FooCell' }] }, 0, nil, nil, []
    ).convert
    expect(code).not_to include('_item_')
  ensure
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end
end
