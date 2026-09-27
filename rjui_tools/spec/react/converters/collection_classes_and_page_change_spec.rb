# frozen_string_literal: true

require 'open3'
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
    # With the rows typed as the data model types them: an untyped `any` model
    # leaves the map's parameters implicitly `any` under --strict.
    expect(classes).to compile_as_typescript.with_ambient(typed_ambient(classes))
  end

  # The declarations tsc derives from the CollectionDataSource `rjui build`
  # writes (DataModelGenerator#generate_collection_data_source_typescript) —
  # the type a data model gives a Collection's items. With no tsc here the
  # example skips, as every tsc arm does (TypeScriptCompiler: recorded, never
  # a pass); it called tsc directly and failed with ENOENT.
  def collection_data_source_declarations
    skip "tsc: #{TypeScriptCompiler.unavailable_reason}" if TypeScriptCompiler.unavailable_reason
    require 'react/data_model_generator'
    source = RjuiTools::React::DataModelGenerator.allocate.send(:generate_collection_data_source_typescript)
    Dir.mktmpdir('rjui_cds') do |dir|
      File.write(File.join(dir, 'CollectionDataSource.ts'), source)
      out, status = Open3.capture2e(TypeScriptCompiler.tsc_path, '--declaration', '--emitDeclarationOnly', '--target', 'ES2020',
                                    '--outDir', dir, File.join(dir, 'CollectionDataSource.ts'))
      raise "tsc could not declare CollectionDataSource: #{out}" unless status.success?

      File.read(File.join(dir, 'CollectionDataSource.d.ts')).gsub('export declare ', 'export ')
    end
  end

  # ambient_for, with the screen's rows typed as the CollectionDataSource the
  # data model declares.
  def typed_ambient(tsx)
    ambient_for(tsx).sub(
      /declare module '@\/generated\/data\/ProbeData' \{[^\n]*\}/,
      "declare module '@/generated/data/CollectionDataSource' { #{collection_data_source_declarations} }\n" \
      "declare module '@/generated/data/ProbeData' { export type ProbeData = " \
      "{ rows?: import('@/generated/data/CollectionDataSource').CollectionDataSource }; " \
      'export const createProbeData: () => ProbeData; }'
    ).tap { |typed| raise 'ProbeData not typed' unless typed.include?('CollectionDataSource }') }
  end

  CLASS_LIST_ROUTES = {
    'list' => [{}, :every, true], 'grid' => [{ 'columns' => 2 }, :every, true],
    'lazy:none' => [{ 'lazy' => 'none' }, :every, true],
    'horizontal' => [{ 'layout' => 'horizontal' }, :first, false], 'flow' => [{ 'layout' => 'flow' }, :first, false],
    'paging' => [{ 'layout' => 'horizontal', 'paging' => true }, :first, false]
  }.freeze

  # The class-list shape draws from the data's sections, as sjui codegen does
  # (kjui codegen and both Dynamic renderers follow the same table): every
  # data section on the vertical routes, the first on horizontal, flow and
  # paging (a snap child per cell; paging drew nothing until jsonui-cli 1.9.0 —
  # 4f ruling 2026-09-26, round 6); the header and footer, with no data, on
  # the vertical routes only. The cells mapped `items` itself — `data.rows?.map` — which
  # a CollectionDataSource does not have (tsc TS2339, measured on 798f6e64,
  # 2026-09-26); the header and footer were drawn on every route. The file
  # type-checks with the rows typed as the data model types them.
  CLASS_LIST_ROUTES.each do |route, (extra, source, edges)|
    it "#{route}: cells from #{source == :every ? 'every data section' : source == :first ? 'the first data section' : 'nowhere'}, " \
       "#{edges ? 'header before and footer after' : 'no header or footer'}; the file type-checks with the rows typed" do
      tsx = generate([{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['RowCell'], 'headerClasses' => ['HeaderCell'],
                        'footerClasses' => ['footer_cell'], 'items' => '@{rows}' }.merge(extra)])
      cells = tsx.scan('<RowCell ').size
      case source
      when :every
        expect([cells, tsx.include?('(data.rows?.sections ?? []).map((section, sectionIndex)')]).to eq([1, true]), tsx
      when :first
        expect([cells, tsx.include?('(data.rows?.sections?.[0]?.cells?.data ?? []).map(')]).to eq([1, true]), tsx
      else
        expect(cells).to eq(0), tsx
      end
      expect(tsx).not_to include('data.rows?.map(')
      if edges
        expect(tsx.index('<HeaderCell />')).to be < tsx.index('<RowCell ')
        expect(tsx.index('<RowCell ')).to be < tsx.index('<FooterCell />')
      else
        expect(tsx).not_to include('<HeaderCell')
        expect(tsx).not_to include('<FooterCell')
      end
      expect(tsx).not_to match(/\.(header|footer) \|\|/)
      expect(tsx).to compile_as_typescript.with_ambient(typed_ambient(tsx))
    end
  end

  # Collection.items is a CollectionDataSource or an array (4f ruling,
  # 2026-09-26). A class-list Collection whose items property is DECLARED a
  # list (`Array`, `[T]`) is one section: every item with cellClasses[0], the
  # header before and the footer after, on every route — what this path wrote
  # before jsonui-cli 1.9.0, byte for byte (the element below is that emit,
  # measured on 798f6e64; a web face draws 56 Collections this way). An
  # undeclared items property is the canonical CollectionDataSource (above).
  {
    'Array' => ['any[]', 'vertical'],
    '[RowCellData]' => ['RowCellData[]', 'vertical'],
    'Array?' => ['any[] | undefined', 'horizontal']
  }.each do |declared, (ts_rows, layout)|
    it "items declared #{declared} (#{layout}): the list mapped as before, and the file type-checks with rows #{ts_rows}" do
      tsx = generate([{ 'data' => [{ 'name' => 'rows', 'class' => declared }] },
                      { 'type' => 'Collection', 'id' => 'list', 'layout' => layout, 'cellClasses' => ['row_cell'],
                        'headerClasses' => ['HeaderCell'], 'items' => '@{rows}' }])
      expect(tsx).to include(<<~JSX.chomp.gsub(/^/, '      '))
        <HeaderCell />
        {data.rows?.map((item: RowCellData, index: number) => (
          <RowCell key={index} id={`list_item_${index}`} data={item} />
        ))}
      JSX
      expect(tsx).not_to include('sections')
      typed = typed_ambient(tsx).sub(
        "{ rows?: import('@/generated/data/CollectionDataSource').CollectionDataSource }",
        "{ rows?: #{ts_rows} }"
      )
      expect(typed).to include("rows?: #{ts_rows} }")
      expect(tsx).to compile_as_typescript.with_ambient(typed)
    end
  end

  it 'reads the list shape from the declaration only: a CollectionDataSource or no declaration reads sections' do
    %w[CollectionDataSource CollectionDataSource?].each do |declared|
      tsx = generate([{ 'data' => [{ 'name' => 'rows', 'class' => declared }] },
                      { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}' }])
      expect(tsx).to include('(data.rows?.sections ?? []).map((section, sectionIndex)'), declared
    end
  end

  it 'writes no TypeScript into a JavaScript file (the map took `index: number`)' do
    js = Dir.mktmpdir('rjui_js') do |dir|
      Dir.chdir(dir) do
        %i[info debug warn].each { |m| allow(RjuiTools::Core::Logger).to receive(m) }
        config = RjuiTools::Core::ConfigManager.load_config.merge('typescript' => false)
        RjuiTools::React::ReactGenerator.new(config).generate(
          'Probe', { 'type' => 'View', 'id' => 'root', 'child' => [{ 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['RowCell'], 'items' => '@{rows}' }] }
        )
      end
    end
    expect(js).to include('(section.cells?.data ?? []).map((cellData, cellIndex) => (')
    expect(js).not_to match(/: number\b| as unknown as /)
  end

  # The pages are the first data section's cells (a snap child each; the
  # class-list pager drew none until jsonui-cli 1.9.0), so the model is typed
  # as the data model types it: the pages a CollectionDataSource, the
  # callback taking the page.
  it 'calls the page-change callback with the page, once per page, and the file type-checks' do
    expect(pager).to include("import { currentCollectionPage } from '@/generated/collectionScroll';")
    expect(pager).to include('data.onPageChange?.(page)').and include('el.dataset.jsonuiPage !== String(page)')
    expect(pager.scan('<PageCell ').size).to eq(1)
    typed = typed_ambient(pager).sub(
      "{ rows?: import('@/generated/data/CollectionDataSource').CollectionDataSource }",
      "{ pages?: import('@/generated/data/CollectionDataSource').CollectionDataSource; onPageChange?: (page: number) => void }"
    )
    expect(typed).to include('onPageChange?: (page: number) => void }')
    expect(pager).to compile_as_typescript.with_ambient(typed)
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
    # No items: no cell (4f ruling 2026-09-26, round 5); until jsonui-cli
    # 1.9.0 this drew `<RowCell />`, a cell with no data.
    expect(bound).not_to include('<RowCell')
  end
end
