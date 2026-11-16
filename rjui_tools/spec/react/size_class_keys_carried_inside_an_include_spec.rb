# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'stringio'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A size class's keys are carried for a node whose id is an include's
# prefixed expression too. `jui build` has rjui prefix the ids inside an include
# (JSONUI_INCLUDE_ID_PREFIX=on -> `id={jsonuiIncludeId(idPrefix, "list")}`),
# and BaseConverter#drawn_classes found the element with the id only when it
# was written `id="list"`. A padded Collection then compared its padding box
# with the merged node's, read the scroll box as other markup, and refused its
# columns — measured on a consumer's 2.3.32 tree through `jui build`: two of
# three such Collections said "not drawn on web" where `rjui build` alone, with
# the plain ids, carried them.
RSpec.describe 'a size class key is carried inside an include' do
  def converters = RjuiTools::React::Converters::ConverterTable.table

  def emit(node, config = {})
    old = $stdout
    $stdout = StringIO.new
    jsx = converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true }.merge(config)).convert_node(0)
    [jsx, $stdout.string]
  ensure
    $stdout = old
  end

  def padded_list
    { 'type' => 'Collection', 'id' => 'candidates_list', 'width' => 'matchParent', 'paddings' => [16, 16, 16, 16],
      'sections' => [{ 'cell' => 'RowCell' }], 'cellClasses' => ['RowCell'], 'items' => '@{candidates}', 'lineSpacing' => 12,
      'responsive' => { 'minWidth:840' => { 'columns' => 2, 'columnSpacing' => 12 } } }
  end

  it 'a padded Collection under the include prefix carries its columns onto the scroll box' do
    jsx, said = emit(padded_list, '_include_id_prefix' => true)
    expect(said).not_to include('not drawn on web')
    scroll_box = jsx[/<div id=\{jsonuiIncludeId\(idPrefix, "candidates_list"\)\} className="([^"]*)"/, 1].to_s.split
    expect(scroll_box).to include('min-[840px]:grid', 'min-[840px]:grid-cols-2', 'min-[840px]:gap-x-[0.75rem]')
  end

  it 'control: the same node with the plain id carries the same classes' do
    plain, = emit(padded_list)
    prefixed, = emit(padded_list, '_include_id_prefix' => true)
    classes = ->(jsx) { jsx[/<div id=(?:"candidates_list"|\{[^}]*"candidates_list"\)\}) className="([^"]*)"/, 1].to_s.split }
    expect(classes.(prefixed)).to eq(classes.(plain))
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    jsx, = emit(padded_list, '_include_id_prefix' => true, 'typescript' => true)
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const idPrefix: string;
      declare function jsonuiIncludeId(prefix: string, id: string): string;
      declare const data: { candidates?: { sections?: { cells?: { data?: unknown[] } }[] } };
      interface RowCellData {}
      declare const RowCell: (props: { id: string; data: RowCellData }) => JSX.Element;
      declare namespace JSX { interface IntrinsicAttributes { key?: unknown } }
    TS
    expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(ambient)
  end
end
