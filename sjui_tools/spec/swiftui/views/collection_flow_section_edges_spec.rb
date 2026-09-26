# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A flow section's declared header and footer (4f ruling 2026-09-26, round 7):
# rows of their own — the header above the section's wrap, the footer below —
# full width at the leading edge, siblings of the wrap in the section VStack
# (so spaced as the lines). On the lazy and the lazy:none flow alike. Until
# jsonui-cli 1.9.0 a flow drew the cells only. A section with no header or
# footer emits what it always did (the faces' six flows are byte-identical).
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  FLOW_EDGE_ROUTES = { 'lazy' => {}, 'lazy:none' => { 'lazy' => 'none' } }.freeze
  FLOW_EDGE_SECTIONS = [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'header' => 'GCell' }].freeze

  def convert(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'chips', 'layout' => 'flow', 'items' => '@{rows}',
                          'sections' => FLOW_EDGE_SECTIONS }.merge(extra)).convert.to_s
  end

  # Each section block's rows, in order: header / wrap / footer.
  def rows(code)
    blocks = code.split(/(?=if let dataSource = data\.rows, dataSource\.sections\.count > \d+ \{)/).drop(1)
    blocks.map do |body|
      [body[/sections\.count > (\d+)/, 1].to_i,
       body.scan(/(HCell|FCell|GCell)View\(data: \w+Data\)|FlowLayout\(/).map { |m| m.first || 'wrap' }]
    end
  end

  FLOW_EDGE_ROUTES.each do |route, extra|
    describe route do
      it 'each section: its header, its wrap, its footer; a header-only section its header' do
        code = convert(extra)
        expect(rows(code)).to eq([[0, %w[HCell wrap FCell]], [1, %w[GCell]]]), code
      end

      it 'the header and footer read the section\'s own data and fill the row, leading' do
        code = convert(extra)
        expect(code).to include("if let headerData = section.header?.data {\n")
        expect(code).to include("if let footerData = section.footer?.data {\n")
        expect(code.scan('.frame(maxWidth: .infinity, alignment: .leading)').size).to eq(3), code
      end

      it 'control: no header or footer declared, no row' do
        code = convert(extra.merge('sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }]))
        expect(code).not_to include('.header?')
        expect(code).not_to include('.footer?')
        expect(code).not_to include('maxWidth: .infinity')
      end
    end
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    it 'on both routes' do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView', 'BCellView', 'HCellView', 'FCellView', 'GCellView') +
              "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
              "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
              "  var body: some View { VStack { content() } } }\n"
      codes = FLOW_EDGE_ROUTES.values.map { |extra| convert(extra.merge('lineSpacing' => 4)) }
      expect(compilable_view("VStack {\n#{codes.join("\n")}\n}",
                             data: ['var rows: CollectionDataSource? = nil'], stubs: stubs)).to compile_as_swift
    end
  end
end
