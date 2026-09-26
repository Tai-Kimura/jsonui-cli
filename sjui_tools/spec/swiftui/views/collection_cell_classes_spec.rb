# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/views/color_helper'
require 'core/layout_validator'

# `cellClasses` with `items` and no `sections`.
#
# SSoT (`/Collection/cellClasses`): "Cell layouts this Collection may use.
# With `items` and no `sections`, a single cellClass renders every item;
# several cellClasses need `sections[].cell` to assign them."
#
# iOS was the only face that did not do that. Measured across the three
# emitters:
#
#   kjui  `<cellClass>View(data = itemData, …)`   — cellClasses IS the selector
#   rjui  `<CellView data={item} />`              — same, via generate_legacy_content
#   sjui  `Text("\(viewName): \(cellIndex)")`     — a TODO placeholder
#
# So the same layout rendered cells on Android and Web and debug text on iOS.
# The placeholder had a reason — `section.cells?.viewName` is a runtime string,
# so nothing can be instantiated from it at compile time — but that reason
# stops applying the moment a cellClass is declared, because then the view
# name IS known when the code is written.
#
# The several-cellClasses case is refused rather than guessed. All three faces
# implement "a single cellClass" by taking `.first`, so declaring several
# renders the first and drops the rest silently on every face; that check
# lives in JsonUIShared::LayoutValidator so the three faces cannot disagree.
RSpec.describe 'Collection cellClasses with items and no sections' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all)  { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  before do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
      'rows' => { 'name' => 'rows', 'class' => 'CollectionDataSource', 'defaultValue' => [] }
    }
  end

  after { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def emit(component)
    out = SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component).convert
    out.is_a?(Array) ? out.join("\n") : out.to_s
  end

  let(:base) do
    { 'type' => 'Collection', 'id' => 'target', 'columns' => 1, 'items' => '@{rows}' }
  end

  describe 'a single declared cellClass' do
    it 'renders every item with that cell view' do
      code = emit(base.merge('cellClasses' => ['ItemCollectionViewCell']))
      expect(code).to include('ItemView(data: cellData)')
    end

    it 'stops emitting the runtime-name placeholder' do
      code = emit(base.merge('cellClasses' => ['ItemCollectionViewCell']))
      expect(code).not_to include('TODO')
      expect(code).not_to include('\\(viewName)')
    end

    it 'carries the cell address, like every other cell path' do
      code = emit(base.merge('cellClasses' => ['ItemCollectionViewCell']))
      expect(code).to include('.accessibilityIdentifier("target_item_\\(cellIndex)")')
    end

    it 'drops the viewName binding it no longer reads' do
      # The guard used to bind `viewName` for the placeholder. Keeping it
      # would be an unused binding in the emitted Swift.
      code = emit(base.merge('cellClasses' => ['ItemCollectionViewCell']))
      expect(code).to include('if let cellsData = section.cells?.data {')
    end
  end

  describe 'no declared cellClass' do
    # ⚠️ `columns => 2`, not the `columns => 1` the examples above use. Only
    # the grid path reaches the runtime-name branch with no cellClass; the
    # single-column path answers "nothing renderable" earlier. Measured
    # across six Collection shapes (columns 1 / 2 / none, horizontal, flow,
    # grouped) — the grid is the only one, and a control written on the
    # wrong shape would have asserted nothing.
    it 'still cannot instantiate a runtime name' do
      # Control: the placeholder is correct HERE, and the change must not
      # remove it. Nothing declares which view to build.
      code = emit(base.merge('columns' => 2))
      expect(code).to include('\\(viewName)')
    end

    it 'renders the declared cell in that same grid path' do
      # The fix has to apply where the placeholder lives, not only where the
      # first examples looked.
      code = emit(base.merge('columns' => 2, 'cellClasses' => ['ItemCollectionViewCell']))
      expect(code).to include('ItemView(data: cellData)')
      expect(code).not_to include('\\(viewName)')
    end
  end

  describe 'several declared cellClasses' do
    def errors_for(component)
      JsonUIShared::LayoutValidator
        .validate_layout(component, source_path: 'x.json')
        .select { |w| w[:level] == :error }
    end

    it 'is refused by name, rather than rendering the first' do
      errs = errors_for(base.merge('cellClasses' => %w[AlphaCell BetaCell]))
      expect(errs.length).to eq(1)
      expect(errs.first[:message]).to include('2 cellClasses declared without sections')
      expect(errs.first[:message]).to include('sections[].cell')
    end

    it 'names the Collection' do
      errs = errors_for(base.merge('cellClasses' => %w[AlphaCell BetaCell]))
      expect(errs.first[:message]).to include('id=target')
    end

    it 'accepts several cellClasses WITH sections' do
      # Control: `sections[].cell` is exactly the way to assign them, so the
      # rule must not fire when the author has done that.
      component = base.merge('cellClasses' => %w[AlphaCell BetaCell],
                             'sections' => [{ 'cell' => 'AlphaCell' }])
      expect(errors_for(component)).to be_empty
    end

    it 'accepts a single cellClass' do
      # Control: the supported shape.
      expect(errors_for(base.merge('cellClasses' => ['AlphaCell']))).to be_empty
    end
  end

  # cellClasses and no `items` (4f ruling 2026-09-26, round 5): no cell is
  # drawn on every path (rjui drew one with no data until jsonui-cli 1.9.0),
  # and the shared validator names the shape — this face's mirror of it.
  # `sections` and no `items`: nothing to draw them from — no header, cell or
  # footer, on every route (4f ruling 2026-09-26, round 6; kjui and rjui draw
  # nothing either). Until jsonui-cli 1.9.0 the sectioned grid drew each
  # section's header and footer with no data around an empty grid.
  describe 'sections and no items' do
    SECTIONS_NO_ITEMS_ROUTES = {
      'list' => {}, 'grid' => { 'columns' => 2 }, 'lazy:none' => { 'lazy' => 'none' },
      'lazy:none grid' => { 'lazy' => 'none', 'columns' => 2 }, 'horizontal' => { 'layout' => 'horizontal' },
      'flow' => { 'layout' => 'flow' }, 'paging' => { 'layout' => 'horizontal', 'paging' => true }
    }.freeze

    SECTIONS_NO_ITEMS_ROUTES.each do |route, extra|
      it "#{route}: no header, cell or footer" do
        code = emit({ 'type' => 'Collection', 'id' => 'target',
                      'sections' => [{ 'cell' => 'RowCell', 'header' => 'HeadCell', 'footer' => 'FootCell' }] }.merge(extra))
        expect(code).not_to match(/\b(RowCell|HeadCell|FootCell)View\(/), code
      end
    end

    it 'control: with items, the grid draws the header, cells and footer' do
      code = emit({ 'type' => 'Collection', 'id' => 'target', 'columns' => 2, 'items' => '@{rows}',
                    'sections' => [{ 'cell' => 'RowCell', 'header' => 'HeadCell', 'footer' => 'FootCell' }] })
      expect(code).to include('HeadCellView(data: headerData)').and include('RowCellView(data: cellData)').and include('FootCellView(data: footerData)')
    end

    it 'the empty grid type-checks', :swift_compile do
      code = emit({ 'type' => 'Collection', 'id' => 'target', 'columns' => 2,
                    'sections' => [{ 'cell' => 'RowCell', 'header' => 'HeadCell', 'footer' => 'FootCell' }] })
      expect(compilable_view(code)).to compile_as_swift
    end
  end

  describe 'cellClasses and no items' do
    def no_items_warnings(component)
      JsonUIShared::LayoutValidator.validate_layout(component, source_path: 'x.json')
                                   .select { |w| w[:message].include?('items is not') }
    end

    it 'draws no cell' do
      code = emit({ 'type' => 'Collection', 'id' => 'target', 'columns' => 1, 'cellClasses' => ['ItemCollectionViewCell'] })
      expect(code).not_to include('ItemView(')
    end

    it 'the shared validator names it, as a warning' do
      found = no_items_warnings({ 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCollectionViewCell'] })
      expect(found.size).to eq(1)
      expect(found.first[:level]).to eq(:warning)
      expect(found.first[:message]).to include('Collection (id=target): cellClasses are declared but items is not, so no cell is drawn.')
    end

    it 'names nothing when items is bound, when the Collection declares sections, or without cellClasses' do
      expect(no_items_warnings(base.merge('cellClasses' => ['ItemCollectionViewCell']))).to be_empty
      expect(no_items_warnings({ 'type' => 'Collection', 'id' => 'target', 'cellClasses' => ['ItemCollectionViewCell'],
                                 'sections' => [{ 'cell' => 'ItemCollectionViewCell' }] })).to be_empty
      expect(no_items_warnings({ 'type' => 'Collection', 'id' => 'target' })).to be_empty
    end
  end

  describe 'the emitted Swift compiles', :swift_compile do
    it 'type-checks the single-cellClass cell loop' do
      code = emit(base.merge('cellClasses' => ['ItemCollectionViewCell']))
      body = code.lines.map { |l| "        #{l}" }.join

      expect(<<~SWIFT).to compile_as_swift
        struct CollectionDataSection {
            var cells: (viewName: String, data: [[String: Any]])?
        }
        struct CollectionDataSource {
            var sections: [CollectionDataSection] = []
        }
        struct ItemView: View {
            init(data: Any) {}
            var body: some View { Text("cell") }
        }
        struct TestData { var rows: CollectionDataSource? = nil }

        struct Host: View {
            let data = TestData()
            var body: some View {
        #{body}
            }
        }
      SWIFT
    end
  end
end
