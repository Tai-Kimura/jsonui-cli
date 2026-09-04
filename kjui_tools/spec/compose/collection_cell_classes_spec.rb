# frozen_string_literal: true

require 'compose/components/collection_component'
require 'core/layout_validator'

# `cellClasses` with `items` and no `sections`, on the Android face.
#
# SSoT (`/Collection/cellClasses`): "Cell layouts this Collection may use.
# With `items` and no `sections`, a single cellClass renders every item;
# several cellClasses need `sections[].cell` to assign them."
#
# ⚠️ Nothing about kjui's emit changed. This face is where the meaning came
# FROM: `cell_classes.first` selects the composable and each item renders
# `<cellClass>View(data = itemData, …)`. rjui already agreed; iOS was the
# outlier, emitting `Text("\(viewName): \(cellIndex)")`, and was brought here.
#
# So this file exists to pin the reference behaviour while the other face
# moves toward it — a face that is being copied needs a test, or "the three
# agree" degrades into "the two that have tests agree". The shared validator
# rule is asserted here too, because it is mirrored into this tool and must
# fire the same way.
RSpec.describe 'Collection cellClasses with items and no sections (Compose)' do
  let(:base) do
    { 'type' => 'Collection', 'id' => 'target', 'items' => '@{rows}' }
  end

  describe 'the reference emit (unchanged)' do
    it 'selects the composable from the single declared cellClass' do
      code = KjuiTools::Compose::Components::CollectionComponent.generate(
        base.merge('cellClasses' => ['ItemCell']), 0, nil, nil
      )
      expect(code).to include('ItemCellView(')
    end

    it 'has no data source without items, and says so' do
      # The sibling shape, pinned so the two do not blur: with no data source
      # kjui emits an explicit empty loop rather than a broken reference.
      code = KjuiTools::Compose::Components::CollectionComponent.generate(
        { 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCell'] }, 0, nil, nil
      )
      expect(code).to include('items(0)')
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
