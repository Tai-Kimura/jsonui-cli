# frozen_string_literal: true

require 'core/layout_validator'

# A reorderable Collection needs an identity that moves with its rows (ticket
# jui-collection-drag-to-reorder, ruling B 2026-11-13). The rule lives in
# shared/core/layout_validator.rb (check_collection), mirrored into each tool;
# this file pins it on this tool's copy.
RSpec.describe 'a reorderable Collection without cellIdProperty' do
  def warnings(node)
    JsonUIShared::LayoutValidator.check_collection(node, source_path: 'screen.json')
      .select { |w| w[:message].include?('reorderable') }
  end

  let(:base) { { 'type' => 'Collection', 'id' => 'rows', 'items' => '@{rows}', 'cellClasses' => ['RowCell'] } }

  it 'is warned when reorderable is true' do
    found = warnings(base.merge('reorderable' => true))
    expect(found.size).to eq(1)
    expect(found.first[:level]).to eq(:warning)
    expect(found.first[:message]).to include('(id=rows)', 'cellIdProperty')
  end

  it 'is warned when reorderable is a binding (it may turn on)' do
    expect(warnings(base.merge('reorderable' => '@{editing}')).size).to eq(1)
  end

  it 'is not warned with cellIdProperty' do
    expect(warnings(base.merge('reorderable' => true, 'cellIdProperty' => 'cellId'))).to be_empty
  end

  it 'is not warned when not reorderable' do
    expect(warnings(base)).to be_empty
    expect(warnings(base.merge('reorderable' => false))).to be_empty
  end
end
