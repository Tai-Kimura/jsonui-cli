# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/views/base_view_converter'
require 'swiftui/collection_cell_index'

# A Collection wraps every cell with
# `.accessibilityIdentifier("{collectionId}_item_{index}")`. A plain SwiftUI
# container is not an accessibility element, so that identifier is pushed
# down onto the cell root's direct children, which then answer to
# `{id}_item_{N}` instead of the identifiers they declared — invisible to
# XCUITest, while the generated Swift still shows the right modifier.
#
# The discriminator is not depth. It is whether the CELL ROOT declares an
# `id`: with one, the id-bearing path already made the root an explicit
# container and the wrapper's identifier landed on the wrapper. Measured
# across 8 cells of one consumer, 8/8 explained by that (2026-09-05), and a
# positive control confirmed it — adding an id to the root of the failing
# cell turned its 3 UI tests green.
RSpec.describe 'Collection cell root accessibility container' do
  CELL_ROOT_KEY = SjuiTools::SwiftUI::Views::BaseViewConverter::COLLECTION_CELL_ROOT_KEY

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  def convert(component)
    factory.create_converter(component).convert
  end

  def cell_root(extra = {})
    { 'type' => 'View', CELL_ROOT_KEY => true,
      'child' => [{ 'type' => 'Label', 'id' => 'holiday_date_label', 'text' => 'x' }] }.merge(extra)
  end

  describe 'a cell root with no id of its own' do
    it 'becomes an explicit accessibility container' do
      expect(convert(cell_root)).to include('.accessibilityElement(children: .contain)')
    end

    it 'gets no identifier of its own — the wrapper carries the address' do
      code = convert(cell_root)
      # The child's identifier is in this output and must stay, so the claim
      # is about the ROOT: exactly one identifier is emitted, the child's,
      # and nothing follows the root's container modifier.
      ids = code.scan(/\.accessibilityIdentifier\("([^"]*)"\)/).flatten
      expect(ids).to eq(['holiday_date_label'])
      expect(code.strip).to end_with('.accessibilityElement(children: .contain)')
    end

    it 'leaves the child identifier where the author put it' do
      expect(convert(cell_root)).to include('.accessibilityIdentifier("holiday_date_label")')
    end
  end

  describe 'what must not change' do
    it 'a cell root WITH an id keeps the id-bearing shape' do
      code = convert(cell_root('id' => 'holiday_row_root'))
      expect(code).to include('.accessibilityElement(children: .contain)')
      expect(code).to include('.accessibilityIdentifier("holiday_row_root")')
    end

    it 'an ordinary id-less container that is NOT a cell root stays bare' do
      # The scope control. Emitting this for every id-less container is what
      # exhausted a device main-thread stack once (DEPTH BUDGET), so the mark
      # is what gates it, not the absence of an id.
      code = convert({ 'type' => 'View',
                       'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end

    it 'a statically invisible cell root does not become an element' do
      # Same suppression the id path applies: an explicit container ignores
      # an ancestor's .accessibilityHidden(true).
      expect(convert(cell_root('visibility' => 'invisible')))
        .not_to include('.accessibilityElement(children: .contain)')
      expect(convert(cell_root('hidden' => true)))
        .not_to include('.accessibilityElement(children: .contain)')
    end

    it 'a non-container cell root is left alone' do
      # Only types whose emitted shape is a plain layout container qualify;
      # a Label root is already an accessibility element.
      code = convert({ 'type' => 'Label', 'text' => 'x', CELL_ROOT_KEY => true })
      expect(code).not_to include('.accessibilityElement(children: .contain)')
    end
  end

  describe 'the index that sets the mark' do
    require 'tmpdir'
    require 'json'

    def index_for(layout)
      Dir.mktmpdir('cell_index') do |dir|
        File.write(File.join(dir, 'host.json'), JSON.generate(layout))
        SjuiTools::SwiftUI::CollectionCellIndex.build(dir).to_a.sort
      end
    end

    it 'names the cells of a vertically scrolling Collection' do
      expect(index_for({ 'type' => 'Collection', 'id' => 'c',
                         'sections' => [{ 'cell' => 'holiday_row' }] })).to eq(['holiday_row'])
    end

    it 'names the cells of a HORIZONTAL Collection too' do
      # ScrollingCellIndex excludes these on purpose — it answers a scrolling
      # question. The wrapper identifier does not care about direction, so
      # this index must not inherit that exclusion.
      expect(index_for({ 'type' => 'Collection', 'id' => 'c', 'orientation' => 'horizontal',
                         'sections' => [{ 'cell' => 'chip_cell' }] })).to eq(['chip_cell'])
    end

    it 'names the cells of a non-lazy Collection too' do
      expect(index_for({ 'type' => 'Collection', 'id' => 'c', 'lazy' => 'none',
                         'sections' => [{ 'cell' => 'static_cell' }] })).to eq(['static_cell'])
    end

    it 'names legacy cellClasses, headers and footers' do
      expect(index_for({ 'type' => 'Collection', 'id' => 'c',
                         'cellClasses' => ['legacy_cell'],
                         'sections' => [{ 'cell' => 'a', 'header' => 'h', 'footer' => 'f' }] }))
        .to eq(%w[a f h legacy_cell])
    end

    it 'names nothing when there is no Collection' do
      expect(index_for({ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })).to eq([])
    end
  end
end
