# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# The non-lazy grid's headerClasses / footerClasses (a class-list Collection,
# `lazy: "none"`, more than one column): one VStack holds the header, the grid
# and the footer, and the Collection's own modifiers apply to it — as the
# single-column non-lazy route draws them and as SwiftJsonUI Dynamic does
# (91b932b). Until 1.8.121 (measured on aad4c8c4, 2026-09-26) the three were
# emitted as siblings, so the Collection was three views in its parent and
# its background, identifier and frame attached to the footer.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def convert(extra = {})
    described_class.new({
      'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'columns' => 2, 'lazy' => 'none',
      'cellClasses' => ['ACell'], 'headerClasses' => ['HeadCell'], 'footerClasses' => ['FootCell'],
      'background' => '#FF0000', 'lineSpacing' => 7
    }.merge(extra)).convert.to_s
  end

  # The views at the top of the emit (column 0, not a closing brace), and
  # where the Collection's modifiers begin.
  def top_level(code)
    lines = code.lines
    views = lines.each_index.select { |i| lines[i] =~ /\A[A-Za-z]/ }
    first_modifier = lines.index { |l| l.start_with?('    .background(') }
    [views.map { |i| lines[i][/\A\w+/] }, views, first_modifier, lines]
  end

  it 'is one view: a VStack holding header, grid and footer, with the Collection modifiers on it' do
    names, at, first_modifier, lines = top_level(convert)
    expect(names).to eq(['VStack']), lines.join
    expect(lines[first_modifier - 1]).to eq("}\n") # the VStack's own closing brace
    body = lines[at.first...first_modifier].join
    expect(body.index('HeadCellView()')).to be < body.index('LazyVGrid(')
    expect(body.index('LazyVGrid(')).to be < body.index('FootCellView()')
    expect(lines.first).to include('spacing: 7') # rows, header and footer spaced by lineSpacing
  end

  it 'the header alone and the footer alone are held the same way' do
    %w[headerClasses footerClasses].each do |dropped|
      names, = top_level(convert(dropped => nil))
      expect(names).to eq(['VStack']), dropped
    end
  end

  it 'without a header or footer the grid is the view, as before (the control)' do
    names, = top_level(convert('headerClasses' => nil, 'footerClasses' => nil))
    expect(names).to eq(['LazyVGrid'])
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    it 'with a header, a footer, both and neither' do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView') +
              %w[HeadCellView FootCellView].map { |n| "struct #{n}: View { var body: some View { Text(\"#{n}\") } }\n" }.join
      codes = [convert, convert('headerClasses' => nil), convert('footerClasses' => nil),
               convert('headerClasses' => nil, 'footerClasses' => nil)]
      expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
        .to compile_as_swift
    end
  end
end
