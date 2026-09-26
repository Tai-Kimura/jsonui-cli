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
# The web face takes `cell_classes.first` for every item. It mapped it over
# `items` as an array until jsonui-cli 1.9.0; the items are a
# CollectionDataSource, and the cells now come from its sections, as on sjui
# and kjui (collection_classes_and_page_change_spec.rb has the route table).
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

    it "maps it over the items' data sections" do
      result = convert(base.merge('cellClasses' => ['ItemCard']))
      expect(result).to include('(data.rows?.sections ?? []).map((section, sectionIndex) =>')
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

  # cellClasses and no `items` (4f ruling 2026-09-26, round 5): no cell is
  # drawn — the class-list cells come from `items` on every path, and sjui,
  # kjui and both Dynamic renderers draw none. Until jsonui-cli 1.9.0 this
  # path drew one cell with no data (`<ItemCard />`) on every route, paging
  # included. The header and footer stay where the vertical routes draw
  # them. The shared validator names the shape.
  describe 'cellClasses and no items' do
    CELL_CLASSES_NO_ITEMS_ROUTES = {
      'list' => [{}, true], 'grid' => [{ 'columns' => 2 }, true], 'lazy:none' => [{ 'lazy' => 'none' }, true],
      'horizontal' => [{ 'layout' => 'horizontal' }, false], 'flow' => [{ 'layout' => 'flow' }, false],
      'paging' => [{ 'layout' => 'horizontal', 'paging' => true }, false]
    }.freeze

    let(:bare) do
      { 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCard'],
        'headerClasses' => ['HeadCard'], 'footerClasses' => ['FootCard'] }
    end

    CELL_CLASSES_NO_ITEMS_ROUTES.each do |route, (extra, edges)|
      it "#{route}: no cell#{edges ? '; the header and footer' : ', no header or footer'}" do
        code = convert(bare.merge(extra))
        expect(code).not_to match(/<ItemCard\b/)
        expect(code).not_to include('Add items prop')
        expect(code.scan(/<HeadCard \/>/).size).to eq(edges ? 1 : 0), code
        expect(code.scan(/<FootCard \/>/).size).to eq(edges ? 1 : 0), code
      end
    end

    def no_items_warnings(component)
      JsonUIShared::LayoutValidator.validate_layout(component, source_path: 'x.json')
                                   .select { |w| w[:message].include?('items is not') }
    end

    it 'the shared validator names it, as a warning' do
      found = no_items_warnings(bare)
      expect(found.size).to eq(1)
      expect(found.first[:level]).to eq(:warning)
      expect(found.first[:message]).to include('Collection (id=target): cellClasses are declared but items is not, so no cell is drawn.')
      expect(JsonUIShared::LayoutValidator.blocking?(found)).to be(false)
    end

    it 'names nothing when items is bound, when the Collection declares sections, or without cellClasses' do
      expect(no_items_warnings(bare.merge('items' => '@{rows}'))).to be_empty
      expect(no_items_warnings(bare.merge('sections' => [{ 'cell' => 'ItemCard' }]))).to be_empty
      expect(no_items_warnings({ 'type' => 'Collection', 'id' => 'target' })).to be_empty
    end

    it 'names it in a nested Collection too (the layout walk)' do
      layout = { 'type' => 'View', 'child' => [bare] }
      expect(no_items_warnings(layout).size).to eq(1)
    end

    describe 'the emit type-checks', :typescript_compile do
      it 'on a vertical route: the header and footer, no cell' do
        code = convert(bare)
        ambient = <<~TS
          declare const HeadCard: () => JSX.Element;
          declare const FootCard: () => JSX.Element;
        TS
        expect(<<~TSX).to compile_as_typescript.with_ambient(ambient)
          export const Emitted = (): JSX.Element => (
          #{code}
          );
        TSX
      end
    end
  end

  # `sections` and no `items`: nothing to draw them from — no header, cell or
  # footer, as sjui and kjui codegen draw. Until jsonui-cli 1.9.0 each
  # section's header and footer read `?.sections` off nothing — `data={?.
  # sections?.[0]?.header || {}}`, which does not parse — around one cell with
  # no data, on every route.
  describe 'sections and no items' do
    let(:sectioned) do
      { 'type' => 'Collection', 'id' => 'target',
        'sections' => [{ 'cell' => 'ItemCard', 'header' => 'HeadCard', 'footer' => 'FootCard' }] }
    end

    CELL_CLASSES_NO_ITEMS_ROUTES.each do |route, (extra, _edges)|
      it "#{route}: no header, cell or footer" do
        code = convert(sectioned.merge(extra))
        expect(code).not_to match(/<(ItemCard|HeadCard|FootCard)\b/)
        expect(code).not_to include('{?.')
      end
    end

    it 'control: with items, the section draws' do
      code = convert(sectioned.merge('items' => '@{rows}'))
      expect(code).to include('{data.rows?.sections?.[0]?.header && <HeadCard data={data.rows?.sections?.[0]?.header} />}')
      expect(code).to match(/<ItemCard key=/)
    end

    describe 'the emit type-checks', :typescript_compile do
      it 'on the list route' do
        expect(<<~TSX).to compile_as_typescript.with_ambient('')
          export const Emitted = (): JSX.Element => (
          #{convert(sectioned)}
          );
        TSX
      end
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
          key?: string | number; id?: string; data: ItemCardData
        }) => JSX.Element;
        declare const data: { rows?: { sections: { cells?: { data: unknown[] } }[] } };
      TS

      expect(<<~TSX).to compile_as_typescript.with_ambient(ambient)
        export const Emitted = (): JSX.Element => (
        #{code}
        );
      TSX
    end
  end
end
