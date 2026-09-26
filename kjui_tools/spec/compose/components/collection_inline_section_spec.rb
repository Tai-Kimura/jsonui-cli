# frozen_string_literal: true

require_relative '../../../lib/compose/components/collection_component'

# A section's header / cell / footer names its layout (attribute_definitions
# Collection.sections: strings). A node written inline there is declared
# nowhere and drawn by no path (4f's ruling, 1.9.0); the shared validator
# names it (inline_layout?). kjui's build raised on it — the Hash reached
# `.split` — and stopped; the section entry is set aside now, and a cell
# named by its layout is drawn as before.
RSpec.describe 'kjui codegen: a node written inline in a section' do
  let(:node) do
    { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'cellIdProperty' => 'id',
      'sections' => [{ 'cell' => { 'type' => 'Label', 'text' => 'INLINE_CELL_MARK' } }, { 'cell' => 'row_cell', 'header' => { 'type' => 'View' } }] }
  end

  it 'does not stop the build, and draws the named cell only' do
    code = nil
    expect { code = KjuiTools::Compose::Components::CollectionComponent.generate(node, 0, Set.new) }.not_to raise_error
    expect(code).not_to include('INLINE_CELL_MARK')
    expect(code).to include('RowCell')
  end
end
