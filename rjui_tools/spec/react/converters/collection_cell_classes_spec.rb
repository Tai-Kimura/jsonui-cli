# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/collection_converter'
require 'core/layout_validator'

# `cellClasses` with `items` and no `sections`.
#
# SSoT (`/Collection/cellClasses`): "Cell layouts this Collection may use.
# With `items` and no `sections`, a single cellClass renders every item;
# several cellClasses need `sections[].cell` to assign them."
#
# The web face already did the first half — `generate_legacy_content` takes
# `cell_classes.first` and maps it over the items binding, the same meaning
# kjui gives it. iOS was the outlier (it emitted a debug placeholder) and has
# been brought here rather than the reverse.
#
# What this file pins on the web side is that the behaviour is DECLARED, not
# incidental: the emit stays, and the several-cellClasses case is refused by
# the shared validator rather than silently rendering the first.
RSpec.describe 'Collection cellClasses with items and no sections' do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }

  def convert(json)
    RjuiTools::React::Converters::CollectionConverter.new(json, config).convert
  end

  let(:base) do
    { 'type' => 'Collection', 'id' => 'target', 'items' => '@{rows}' }
  end

  describe 'a single declared cellClass' do
    it 'renders every item with that cell view' do
      result = convert(base.merge('cellClasses' => ['ItemCard']))
      expect(result).to include('<ItemCard')
    end

    it 'maps it over the items binding' do
      result = convert(base.merge('cellClasses' => ['ItemCard']))
      expect(result).to match(/\?\.map\(\(item/)
    end
  end

  describe 'several declared cellClasses' do
    def errors_for(component)
      JsonUIShared::LayoutValidator
        .validate_layout(component, source_path: 'x.json')
        .select { |w| w[:level] == :error }
    end

    it 'is refused by name, rather than rendering the first' do
      # The emitter would take `.first` and drop the rest with no diagnostic,
      # exactly as the other two faces do — which is why the rule lives in
      # the shared validator and not in any one converter.
      errs = errors_for(base.merge('cellClasses' => %w[AlphaCard BetaCard]))
      expect(errs.length).to eq(1)
      expect(errs.first[:message]).to include('2 cellClasses declared without sections')
      expect(errs.first[:message]).to include('sections[].cell')
      expect(errs.first[:message]).to include('id=target')
    end

    it 'accepts several cellClasses WITH sections' do
      # Control: `sections[].cell` is the documented way to assign them.
      component = base.merge('cellClasses' => %w[AlphaCard BetaCard],
                             'sections' => [{ 'cell' => 'AlphaCard' }])
      expect(errors_for(component)).to be_empty
    end

    it 'accepts a single cellClass' do
      expect(errors_for(base.merge('cellClasses' => ['AlphaCard']))).to be_empty
    end
  end

  # ⚠️ Every example above asserts emitted TEXT, and until this arm existed
  # nothing in the rjui suite handed emitted TypeScript to a compiler at all.
  # `compile-emitted-kotlin.sh` said "`tsc --noEmit` ... run in the suite";
  # that was false for this face.
  #
  # Parsing would not be enough. Measured on the Swift side: `-parse` accepted
  # `data.collectionDataSource.getCellData(...)` — a property nothing declares
  # calling a method that exists nowhere — with zero errors. The rjui suite's
  # one existing check is a `@babel/parser` parse, which has the same blind
  # spot.
  describe 'the emitted TypeScript type-checks', :typescript_compile do
    it 'accepts the single-cellClass collection under --strict' do
      code = convert(base.merge('cellClasses' => ['ItemCard']))

      # The types the fragment names, declared by the spec that emits it —
      # not inferred, because a permissive stub accepts output a consumer's
      # strict build would reject.
      ambient = <<~TS
        interface ItemCardData { readonly title?: string }
        declare const ItemCard: (props: {
          key?: number; id?: string; data: ItemCardData
        }) => JSX.Element;
        declare const data: { rows?: ItemCardData[] };
      TS

      expect(<<~TSX).to compile_as_typescript.with_ambient(ambient)
        export const Emitted = (): JSX.Element => (
        #{code}
        );
      TSX
    end
  end
end
