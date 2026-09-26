# frozen_string_literal: true

require 'compose/components/collection_component'
require 'core/layout_validator'

# `cellClasses` with `items` and no `sections`, on the Android face.
#
# SSoT (`/Collection/cellClasses`): "Cell layouts this Collection may use.
# With `items` and no `sections`, a single cellClass renders every item;
# several cellClasses need `sections[].cell` to assign them."
#
# This file first pinned kjui's emit as the reference: `cell_classes.first`
# selects the composable and each item renders `<cellClass>View(data =
# itemData, …)` over `data.<items>?.get("<cellClass>")`. That emit compiled
# against neither CollectionDataSource (the type kjui gives the property)
# nor the cell scaffold, and only the lazy grid drew it (measured on
# 8e4ea3ea, 2026-09-26). The ruling since: kjui follows sjui codegen's route
# table for this shape — collection_class_list_shape_spec.rb places and
# compiles every route. What stays here is the selection and the shared
# validator rule, which is mirrored into this tool and must fire the same
# way.
RSpec.describe 'Collection cellClasses with items and no sections (Compose)' do
  let(:base) do
    { 'type' => 'Collection', 'id' => 'target', 'items' => '@{rows}' }
  end

  describe 'the emit' do
    it 'selects the composable from the single declared cellClass' do
      code = KjuiTools::Compose::Components::CollectionComponent.generate(
        base.merge('cellClasses' => ['ItemCell']), 0, nil, nil
      )
      expect(code).to include('ItemCellView(')
    end

    it 'draws no cell without items' do
      # The sibling shape, pinned so the two do not blur: with no data source
      # there is nothing to draw the cells from. This was an `items(0)` loop
      # around a cell that read an undeclared `item`.
      code = KjuiTools::Compose::Components::CollectionComponent.generate(
        { 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCell'] }, 0, nil, nil
      )
      expect(code).not_to include('ItemCellView(')
      expect(code).not_to include('items(')
    end
  end

  # cellClasses and no `items` (4f ruling 2026-09-26, round 5): no cell is
  # drawn on every path (rjui drew one with no data until jsonui-cli 1.9.0),
  # and the shared validator names the shape — this face's mirror of it.
  describe 'cellClasses and no items: the shared validator' do
    def no_items_warnings(component)
      JsonUIShared::LayoutValidator.validate_layout(component, source_path: 'x.json')
                                   .select { |w| w[:message].include?('items is not') }
    end

    it 'names it, as a warning' do
      found = no_items_warnings({ 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCell'] })
      expect(found.size).to eq(1)
      expect(found.first[:level]).to eq(:warning)
      expect(found.first[:message]).to include('Collection (id=target): cellClasses are declared but items is not, so no cell is drawn.')
    end

    it 'names nothing when items is bound, when the Collection declares sections, or without cellClasses' do
      expect(no_items_warnings(base.merge('cellClasses' => ['ItemCell']))).to be_empty
      expect(no_items_warnings({ 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCell'],
                                 'sections' => [{ 'cell' => 'ItemCell' }] })).to be_empty
      expect(no_items_warnings({ 'type' => 'Collection', 'id' => 'target' })).to be_empty
    end
  end

  describe 'several declared cellClasses' do
    def errors_for(component)
      JsonUIShared::LayoutValidator
        .validate_layout(component, source_path: 'x.json')
        .select { |w| w[:level] == :error }
    end

    it 'is refused by name, rather than rendering the first' do
      # kjui takes `.first` too, so several cellClasses lose all but one here
      # as well. The rule is mirrored into this tool from shared/core.
      errs = errors_for(base.merge('cellClasses' => %w[AlphaCell BetaCell]))
      expect(errs.length).to eq(1)
      expect(errs.first[:message]).to include('2 cellClasses declared without sections')
      expect(errs.first[:message]).to include('id=target')
    end

    it 'accepts several cellClasses WITH sections' do
      component = base.merge('cellClasses' => %w[AlphaCell BetaCell],
                             'sections' => [{ 'cell' => 'AlphaCell' }])
      expect(errors_for(component)).to be_empty
    end

    it 'accepts a single cellClass' do
      expect(errors_for(base.merge('cellClasses' => ['AlphaCell']))).to be_empty
    end
  end
end
