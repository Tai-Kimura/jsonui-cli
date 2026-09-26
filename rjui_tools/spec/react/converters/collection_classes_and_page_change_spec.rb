# frozen_string_literal: true

require 'tmpdir'
require_relative '../../spec_helper'
require 'react/react_generator'
require_relative '../../support/typescript_compiler'

# Two Collection rows of the audit, through the whole generated component and
# tsc --strict (every module the file imports declared from its own import
# lines, so what is checked is that the file's own names agree):
#
# - `headerClasses` / `cellClasses` / `footerClasses`: the JSX named
#   `<HeaderCellView/>` under `import HeaderCell …` — the converter ran its
#   own UIKit-migration heuristics while the import and the cell Data type
#   used the plain PascalCase name. tsc: TS2304 "Cannot find name".
# - `onValueChange` (alias `onPageChanged`) on a paging Collection: read
#   nowhere, so the page-change callback never fired on web; sjui and kjui
#   call it with the page index.
#
# Measured on b53f59da (2026-09-26). Ticket
# collection-attributes-declared-but-not-drawn-on-some-paths.
RSpec.describe 'rjui Collection: class-list names and the page-change callback' do
  def generate(children)
    Dir.mktmpdir('rjui_coll') do |dir|
      Dir.chdir(dir) do
        %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
        config = RjuiTools::Core::ConfigManager.load_config.merge('typescript' => true)
        RjuiTools::React::ReactGenerator.new(config)
                                        .generate('Probe', { 'type' => 'View', 'id' => 'root', 'child' => children })
      end
    end
  end

  # Every module the file imports, declared loosely: the check is the file's
  # own names, not the shapes of modules this spec does not have.
  def ambient_for(tsx)
    decls = tsx.scan(/^import (.+?) from '([^']+)';$/).map do |what, from|
      type_only = what.start_with?('type ')
      named = what.sub(/\Atype /, '')
      body = if named.start_with?('{')
               named.delete('{}').split(',').map(&:strip).map do |n|
                 type_only || n.start_with?('type ') ? "export type #{n.sub('type ', '')} = any;" : "export const #{n}: any;"
               end.join(' ')
             elsif what.start_with?('React')
               'const React: any; export default React; export function useRef<T>(v: T): { current: T }; ' \
                 'export const useEffect: any; export const useState: any; export const useMemo: any; export const useCallback: any;'
             else
               'const C: (props: any) => any; export default C;'
             end
      "declare module '#{from}' { #{body} }"
    end
    "#{TypeScriptCompiler::AMBIENT.sub('declare const React: any;', '')}\n#{decls.join("\n")}"
  end

  let(:classes) do
    generate([{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['RowCell'], 'headerClasses' => ['HeaderCell'],
                'footerClasses' => ['footer_cell'], 'items' => '@{rows}' }])
  end

  let(:pager) do
    generate([{ 'type' => 'Collection', 'id' => 'pager', 'paging' => true, 'layout' => 'horizontal',
                'cellClasses' => ['page_cell'], 'items' => '@{pages}', 'onPageChanged' => '@{onPageChange}' }])
  end

  it 'names each class-list view as its import names it, and the file type-checks' do
    expect(classes).to include("import HeaderCell from '@/generated/components/HeaderCell';")
      .and include('<HeaderCell ').and include('<RowCell ').and include('<FooterCell ')
    expect(classes).not_to include('CellView')
    expect(classes).to compile_as_typescript.with_ambient(ambient_for(classes))
  end

  # The header and footer views take no data, as sjui and kjui draw them:
  # they were handed `data.rows?.header` / `?.footer`, fields no item source
  # has — the items here are the cells' array (tsc: TS2339 once the data model
  # says so; measured on 46a54fc3, 2026-09-26).
  it 'draws the header and footer views without data, around the cells, and type-checks with the rows typed' do
    header = classes.index('<HeaderCell />')
    cells = classes.index('<RowCell ')
    footer = classes.index('<FooterCell />')
    expect([header, cells, footer]).to all(be_a(Integer)), classes
    expect(header).to be < cells
    expect(cells).to be < footer
    expect(classes).not_to match(/\.(header|footer) \|\|/)
    typed = ambient_for(classes).sub(
      /declare module '@\/generated\/data\/ProbeData' \{[^\n]*\}/,
      "declare module '@/generated/data/ProbeData' { export type ProbeData = { rows?: Record<string, unknown>[] }; " \
      'export const createProbeData: () => ProbeData; }'
    )
    expect(typed).to include('rows?: Record<string, unknown>[]')
    expect(classes).to compile_as_typescript.with_ambient(typed)
  end

  it 'calls the page-change callback with the page, once per page, and the file type-checks' do
    expect(pager).to include("import { currentCollectionPage } from '@/generated/collectionScroll';")
    expect(pager).to include('data.onPageChange?.(page)').and include('el.dataset.jsonuiPage !== String(page)')
    expect(pager).to compile_as_typescript.with_ambient(ambient_for(pager))
  end

  it "declares the callback in the screen's Data model, taking the page index (the alias spelling too)" do
    require 'react/data_model_generator'
    generator = RjuiTools::React::DataModelGenerator.allocate
    %w[onValueChange onPageChanged].each do |key|
      node = { 'type' => 'View', 'child' => [{ 'type' => 'Collection', 'id' => 'pager', 'paging' => true, key => '@{onPageChange}' }] }
      expect(generator.send(:extract_event_handler_bindings, node)).to eq('onPageChange' => { type: 'number' }), key
    end
  end

  it 'does not call it for a Collection that does not page (as sjui and kjui do not)' do
    list = generate([{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['page_cell'], 'items' => '@{pages}',
                       'onValueChange' => '@{onPageChange}' }])
    expect(list).not_to include('onPageChange')
  end

  it 'draws a Collection from `items` only: `bind` is not its data source' do
    bound = generate([{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'bind' => '@{rows}' }])
    expect(bound).not_to include('data.rows')
    expect(bound).to include('<RowCell />') # the cell, with no data source to map
  end
end
