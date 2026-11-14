# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/collection_converter'
require_relative '../../support/typescript_compiler'

# A paging Collection's cellWidth / cellHeight: the cell's size wrapper sits in
# the middle of a page-wide snap child (the requester's ruling 2026-11-15,
# ticket collection-cellwidth-cellheight-unread-on-some-routes), as sjui's
# TabView page centres the cell's frame and kjui's HorizontalPager page its
# size box. Until then the wrapper was the snap child: a page was the cell's
# width and the pager snapped cell by cell. With no size declared the cell
# itself sits in the middle of the page-wide child (the orchestrator's ruling
# 2026-11-15, the same family): a cell narrower than the pager showed the
# next one beside it on the same page.
RSpec.describe RjuiTools::React::Converters::CollectionConverter, 'a pager\'s declared cell size' do
  PAGER_CELL_PAGE_OPEN = '<div key={cellIndex} className="w-full shrink-0 flex items-center justify-center">'
  PAGER_CELL_SIZE_OPEN = '<div className="shrink-0 overflow-hidden" style={{ width: \'150px\', height: \'40px\' }}>'

  def emit(extra, config = {})
    node = { 'type' => 'Collection', 'id' => 'pager', 'items' => '@{rows}', 'layout' => 'horizontal',
             'sections' => [{ 'cell' => 'ACell' }] }.merge(extra)
    described_class.new(node.compact, { 'use_tailwind' => true }.merge(config)).convert
  end

  it 'puts the size wrapper in the middle of a page-wide snap child, the cell its only child' do
    code = emit('paging' => true, 'cellWidth' => 150, 'cellHeight' => 40)
    expect(code).to match(/#{Regexp.escape(PAGER_CELL_PAGE_OPEN)}\n\s*#{Regexp.escape(PAGER_CELL_SIZE_OPEN)}\n\s*<ACell id=\{`pager_item_\$\{cellIndex\}`\} data=\{cellData\} \/>\n\s*<\/div>\n\s*<\/div>/)
    expect(code).to include('[&>*]:snap-start')
  end

  it 'does the same on the class-list shape and the plain array' do
    legacy = emit('paging' => true, 'cellWidth' => 150, 'sections' => nil, 'cellClasses' => ['ACell'])
    expect(legacy).to include('className="w-full shrink-0 flex items-center justify-center"')
    expect(legacy).to include("style={{ width: '150px' }}")
  end

  it 'with no declared size, puts the cell itself in the middle of the page-wide snap child' do
    code = emit('paging' => true)
    expect(code).to match(/#{Regexp.escape(PAGER_CELL_PAGE_OPEN)}\n\s*<ACell id=\{`pager_item_\$\{cellIndex\}`\} data=\{cellData\} \/>\n\s*<\/div>/)
    expect(code).not_to include('overflow-hidden')
    legacy = emit('paging' => true, 'sections' => nil, 'cellClasses' => ['ACell'])
    expect(legacy).to include('className="w-full shrink-0 flex items-center justify-center"')
  end

  it 'leaves a row that does not page as it was' do
    row = emit('cellWidth' => 150, 'cellHeight' => 40)
    expect(row).not_to include('w-full shrink-0 flex items-center justify-center')
    expect(row).to include("<div key={cellIndex} #{PAGER_CELL_SIZE_OPEN.delete_prefix('<div ')}")
  end

  it 'compiles as TypeScript, sized and not' do
    jsx = [{ 'paging' => true, 'cellWidth' => 150, 'cellHeight' => 40 }, { 'paging' => true }]
          .map { |extra| emit(extra, 'typescript' => true) }
    expect(TypeScriptCompiler.component(*jsx)).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace JSX { interface IntrinsicAttributes { key?: string | number } }
      declare const data: { rows?: { sections?: { cells?: { data: Record<string, unknown>[] } }[] } };
      type ACellData = Record<string, unknown>;
      declare const ACell: (props: { key?: string | number; id?: string; data: ACellData }) => JSX.Element;
    TS
  end
end
