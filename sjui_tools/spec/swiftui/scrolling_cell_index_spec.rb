# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'tmpdir'
require 'swiftui/json_to_swiftui_converter'

# The project-wide half of the scrolling-ancestor mark.
#
# 912739e2 marks the descendants of a ScrollView in ONE tree, so a wrapping
# flow Collection under it lets the ancestor scroll. A cell layout is another
# file: its own tree shows no ScrollView, yet on the device it renders inside
# the host's Collection — the consumer shape ("flow chips in the cell of a
# vertical list") the in-tree mark could not reach. `sjui build` now indexes
# which layouts are cells / headers / footers of a VERTICALLY SCROLLING
# Collection across the layout tree and marks their root before conversion.
# Same rule as SwiftJsonUI's dynamic half (292106c): lazy in effect and not
# horizontal. A horizontal host's cells and a lazy:"none" host's cells are
# not under a vertical scroll and stay as they were; so does everything when
# no index was built (a spec, `sjui convert`).
RSpec.describe SjuiTools::SwiftUI::ScrollingCellIndex do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  before { allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data } }

  let(:layouts) { File.realpath(Dir.mktmpdir('scrolling_cell_index')) }
  after { FileUtils.rm_rf(layouts) }

  def write(rel, data)
    path = File.join(layouts, rel)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, JSON.generate(data))
    path
  end

  def host(cell, lazy: nil, layout: nil, extra: {})
    node = { 'type' => 'Collection', 'id' => 'list', 'sections' => [{ 'cell' => cell }], 'items' => '@{rows}' }
    node['lazy'] = lazy if lazy
    node['layout'] = layout if layout
    { 'type' => 'View', 'id' => 'root', 'child' => [node.merge(extra)] }
  end

  # The consumer shape: a cell whose root View holds a wrapContent flow.
  def flow_cell
    { 'type' => 'View', 'id' => 'cell_root', 'child' => [
      { 'type' => 'Collection', 'id' => 'chips', 'layout' => 'flow', 'width' => 'matchParent',
        'height' => 'wrapContent', 'sections' => [{ 'cell' => 'chip' }], 'items' => '@{chips}' }
    ] }
  end

  def scroll_views(code)
    code.to_s.scan('ScrollView(').size
  end

  describe '.build' do
    it 'names the cells, headers and footers of vertically scrolling Collections only' do
      write('vertical_host.json', host('vertical_row'))
      write('flow_host.json', host('flow_row', layout: 'flow'))
      write('eager_host.json', host('eager_row', lazy: 'eager'))
      write('horizontal_host.json', host('carousel_card', layout: 'horizontal'))
      write('orientation_host.json', host('strip_card', extra: { 'orientation' => 'horizontal' }))
      write('hscroll_host.json', host('banner_card', extra: { 'horizontalScroll' => true }))
      write('none_host.json', host('static_row', lazy: 'none'))
      write('sectioned_host.json', { 'type' => 'View', 'child' => [
        { 'type' => 'Collection', 'items' => '@{rows}',
          'sections' => [{ 'cell' => 'sub/nested_row', 'header' => 'group_header', 'footer' => 'group_footer' }] }
      ] })
      write('legacy_host.json', { 'type' => 'Collection', 'cellClasses' => ['legacy_card', { 'className' => 'ClassCell' }] })
      ids = described_class.build(layouts)
      expect(ids).to include('vertical_row', 'flow_row', 'eager_row',
                             'nested_row', 'group_header', 'group_footer',
                             'legacy_card', 'ClassCell')
      expect(ids).not_to include('carousel_card', 'strip_card', 'banner_card', 'static_row')
    end

    it 'is empty for a missing directory and for a tree with no scrolling Collection' do
      expect(described_class.build('/nonexistent/Layouts')).to be_empty
      write('plain.json', { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(described_class.build(layouts)).to be_empty
    end
  end

  describe 'through the converter, the way sjui build uses it' do
    let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }

    def convert(path)
      converter.convert_json_to_view(path).first.to_s
    end

    it 'a wrapContent flow in the cell of a vertical Collection lets the host scroll' do
      write('list.json', host('chips_row'))
      cell = write('chips_row.json', flow_cell)
      converter.scrolling_cell_ids = described_class.build(layouts)
      code = convert(cell)
      expect(scroll_views(code)).to eq(0)
      expect(code).to include('FlowLayout(')
      expect(code).to include('.accessibilityElement(children: .contain)')
      expect(code).to include('.accessibilityIdentifier("chips")')
    end

    it 'the cell of a horizontal Collection keeps its ScrollView' do
      write('carousel.json', host('carousel_card', layout: 'horizontal'))
      cell = write('carousel_card.json', flow_cell)
      converter.scrolling_cell_ids = described_class.build(layouts)
      expect(scroll_views(convert(cell))).to eq(1)
    end

    it 'the cell of a lazy:"none" Collection keeps its ScrollView' do
      write('static_list.json', host('static_row', lazy: 'none'))
      cell = write('static_row.json', flow_cell)
      converter.scrolling_cell_ids = described_class.build(layouts)
      expect(scroll_views(convert(cell))).to eq(1)
    end

    it 'with no index (a single-file conversion) nothing changes' do
      write('list.json', host('chips_row'))
      cell = write('chips_row.json', flow_cell)
      expect(converter.scrolling_cell_ids).to be_nil
      expect(scroll_views(convert(cell))).to eq(1)
    end

    it 'a cell layout in a subdirectory is matched by its basename, as the host references it' do
      write('list.json', host('cells/chips_row'))
      cell = write('cells/chips_row.json', flow_cell)
      converter.scrolling_cell_ids = described_class.build(layouts)
      expect(scroll_views(convert(cell))).to eq(0)
    end

    it 'the cell itself being the flow Collection (no wrapping View) is marked at the root' do
      write('list.json', host('chip_flow'))
      cell = write('chip_flow.json', flow_cell['child'].first)
      converter.scrolling_cell_ids = described_class.build(layouts)
      expect(scroll_views(convert(cell))).to eq(0)
    end
  end
end
