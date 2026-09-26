# frozen_string_literal: true

require 'swiftui/views/collection_converter'

# A flow Collection's three gaps (attribute_semantics.json -> collectionSpacing,
# 4f ruling 2026-09-26): between the cells of a line columnSpacing, else
# itemSpacing; between lines lineSpacing, else itemSpacing; between the
# section blocks as between lines (sectionSpacing is lineSpacing's alias).
# Undeclared, each is 0 — flow included, on every route and path. Until
# jsonui-cli 1.9.0 this path drew 8 for each undeclared gap (the only path that
# did; Android and web drew 0), and the section blocks did not fall back to
# itemSpacing.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  FLOW_SPACING_ROUTES = { 'lazy' => {}, 'lazy:none' => { 'lazy' => 'none' } }.freeze

  def convert(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'chips', 'layout' => 'flow', 'items' => '@{rows}',
                          'sections' => [{ 'cell' => 'ACell' }, { 'cell' => 'BCell' }] }.merge(extra)).convert.to_s
  end

  # [cells, lines, section blocks] as emitted: every FlowLayout's two
  # arguments (one per section, all equal) and the VStack around the blocks.
  def gaps(code)
    flows = code.scan(/FlowLayout\(alignment: \.\w+, horizontalSpacing: (\S+?), verticalSpacing: (\S+?)\) \{/).uniq
    expect(flows.size).to eq(1), code
    stacks = code.scan(/^\s*VStack\(spacing: (\S+?)\) \{/).flatten
    expect(stacks.size).to eq(1), code
    [flows[0][0], flows[0][1], stacks[0]]
  end

  FLOW_SPACING_ROUTES.each do |route, extra|
    describe route do
      it 'nothing declared: 0 between cells, lines and section blocks' do
        expect(gaps(convert(extra))).to eq(%w[0 0 0])
      end

      it 'itemSpacing alone spaces all three' do
        expect(gaps(convert(extra.merge('itemSpacing' => 5)))).to eq(%w[5 5 5])
      end

      it 'columnSpacing spaces only the cells of a line; the lines and blocks fall back to itemSpacing' do
        expect(gaps(convert(extra.merge('columnSpacing' => 10)))).to eq(%w[10 0 0])
        expect(gaps(convert(extra.merge('columnSpacing' => 10, 'itemSpacing' => 5)))).to eq(%w[10 5 5])
      end

      it 'lineSpacing spaces the lines and the blocks; the cells fall back to itemSpacing' do
        expect(gaps(convert(extra.merge('lineSpacing' => 4)))).to eq(%w[0 4 4])
        expect(gaps(convert(extra.merge('lineSpacing' => 4, 'itemSpacing' => 5)))).to eq(%w[5 4 4])
      end

      it 'a declared 0 is drawn as 0, not as the fallback' do
        expect(gaps(convert(extra.merge('lineSpacing' => 0, 'columnSpacing' => 0, 'itemSpacing' => 5)))).to eq(%w[0 0 0])
      end

      it 'sectionSpacing (lineSpacing\'s alias, as an unnormalised layout spells it) spaces the blocks' do
        expect(gaps(convert(extra.merge('sectionSpacing' => 12, 'lineSpacing' => 4)))).to eq(%w[0 4 12])
      end
    end
  end

  describe 'the emitted Swift type-checks', :swift_compile do
    it 'on both routes, undeclared and declared' do
      stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + cell_view_stub('ACellView', 'BCellView') +
              "struct FlowLayout<Content: View>: View { let content: () -> Content\n" \
              "  init(alignment: HorizontalAlignment, horizontalSpacing: CGFloat, verticalSpacing: CGFloat, @ViewBuilder content: @escaping () -> Content) { self.content = content }\n" \
              "  var body: some View { VStack { content() } } }\n"
      codes = FLOW_SPACING_ROUTES.values.flat_map do |extra|
        [convert(extra), convert(extra.merge('lineSpacing' => 4.5, 'columnSpacing' => 10, 'sectionSpacing' => 12))]
      end
      expect(compilable_view("VStack {\n#{codes.join("\n")}\n}",
                             data: ['var rows: CollectionDataSource? = nil'], stubs: stubs)).to compile_as_swift
    end
  end
end
