# frozen_string_literal: true

# A tap's receiver is the id box: inside the offset and the margins, the
# padding included (user ruling 2026-10-06), as Compose's clickable sits
# inside the margins. Until jsonui-cli 1.9.20 the bag wrote on_click …
# allows_hit_testing after :margin, so `.contentShape(Rectangle())` and the
# tap took the margin in, and a combined tap's id read it: a 56-high row with
# topMargin 24 read 80, a Label with onClick and topMargin 12 its 12 too
# (ticket sjui-a-combined-taps-id-box-takes-its-margin-in; SwiftJsonUI
# ConformanceHost AnchorTapProbe, rows g and h).
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

RSpec.describe 'a tap is inside the offset and the margins' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emitted(component)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(component, 0, 'View', 'vertical').convert.to_s
  end

  def lines(component)
    emitted(component).lines.map(&:strip)
  end

  def data_decls
    ['var onTap: (() -> Void)? = nil', 'var open: Bool? = nil']
  end

  # The library views the specimens draw, mirrored from SwiftJsonUI's
  # signatures (NetworkImage.swift, IconLabelView.swift,
  # AdvancedKeyboardAvoidingScrollView), as image_default_content_mode_spec
  # and scrollview_converter_spec stub them.
  def library_stubs
    <<~SWIFT
    struct NetworkImage: View {
        enum ContentMode { case fit, fill, center, stretch, top, bottom, left, right }
        init(url: String? = nil, placeholder: String? = nil, defaultImage: String? = nil,
             errorImage: String? = nil, loadingImage: String? = nil, contentMode: ContentMode = .fit,
             renderingMode: Image.TemplateRenderingMode? = nil, headers: [String: String] = [:]) {}
        var body: some View { Color.clear }
    }
    enum IconLabelView { enum IconPosition { case top, left, right, bottom } }
    struct IconLabelButton: View {
        init(text: String, iconOn: String? = nil, iconOff: String? = nil,
             iconPosition: IconLabelView.IconPosition = .left, iconSize: CGFloat? = nil,
             iconWidth: CGFloat? = nil, iconHeight: CGFloat? = nil, iconMargin: CGFloat = 5,
             fontSize: CGFloat = 16, fontColor: Color = .primary, selectedFontColor: Color = .accentColor,
             fontName: String? = nil, isSelected: Bool? = nil, action: (() -> Void)? = nil) {}
        var body: some View { Color.clear }
    }
    struct KeyboardAvoidanceConfiguration {
        var isEnabled: Bool
        var additionalPadding: CGFloat
        init(isEnabled: Bool = true, additionalPadding: CGFloat = 20) {
            self.isEnabled = isEnabled; self.additionalPadding = additionalPadding
        }
    }
    struct AdvancedKeyboardAvoidingScrollView<Content: View>: View {
        init(_ axes: Axis.Set = .vertical, showsIndicators: Bool = true,
             configuration: KeyboardAvoidanceConfiguration = .init(),
             keyboardDismissMode: String? = nil, @ViewBuilder content: () -> Content) {}
        var body: some View { EmptyView() }
    }
    SWIFT
  end

  def index_of(lines, pattern)
    lines.index { |l| l.match?(pattern) }
  end

  # The last: an IconLabel writes the handler into IconLabelButton's action
  # too, before the bag's tap.
  def last_index_of(lines, pattern)
    lines.rindex { |l| l.match?(pattern) }
  end

  margins = { 'topMargin' => 24, 'leftMargin' => 11, 'offsetX' => 5, 'padding' => 7 }.freeze

  {
    'a Label' => { 'type' => 'Label', 'text' => 'Tap' },
    'an Image' => { 'type' => 'Image', 'srcName' => 'star', 'width' => 24, 'height' => 24 },
    'a NetworkImage' => { 'type' => 'NetworkImage', 'src' => 'https://e/x.png', 'width' => 24, 'height' => 24 },
    'an IconLabel' => { 'type' => 'IconLabel', 'text' => 'I', 'iconOff' => 'star' },
    'an empty View' => { 'type' => 'View', 'width' => 60, 'height' => 40, 'background' => '#CCCCCC' },
    'a View of one Label (a combined tap)' => { 'type' => 'View', 'width' => 60, 'height' => 40,
                                               'child' => [{ 'type' => 'Label', 'text' => 'c' }] },
    'a row of an Image and a Label (a combined tap)' => {
      'type' => 'View', 'orientation' => 'horizontal', 'width' => 'matchParent', 'height' => 56,
      'child' => [{ 'type' => 'Image', 'srcName' => 'star', 'width' => 24, 'height' => 24 },
                  { 'type' => 'Label', 'text' => 'Sign in' }]
    },
    'a ScrollView' => { 'type' => 'ScrollView', 'width' => 60, 'height' => 40,
                        'child' => [{ 'type' => 'Label', 'text' => 's' }] }
  }.each do |name, node|
    it "taps #{name} inside its offset and its margins, outside its padding" do
      component = node.merge(margins).merge('id' => 'probe', 'onClick' => '@{onTap}')
      code = lines(component)
      # The handler's own line: what the tap runs, however it is attached.
      tap = last_index_of(code, /\Adata\.onTap\?\(\)/)
      shape = index_of(code, /\A\.contentShape\(Rectangle\(\)\)/)
      offset = index_of(code, /\A\.offset\(x: 5/)
      margin = index_of(code, /\A\.padding\(\.(top|leading), (24|11)\)/)
      expect([tap, shape, offset, margin]).to all(be_a(Integer)), code.join("\n")
      # An empty View draws its padding into its box, not as `.padding(7)`.
      padding = index_of(code, /\A\.padding\(7\)/)
      expect(padding).to be < shape if padding
      expect(shape).to be < tap
      expect(tap).to be < offset
      expect(offset).to be < margin
      expect(compilable_view(emitted(component), data: data_decls, stubs: library_stubs)).to compile_as_swift
    end
  end

  it 'keeps allowsHitTesting outside the tap and inside the margins' do
    component = { 'type' => 'Label', 'id' => 'probe', 'text' => 'Tap', 'onClick' => '@{onTap}',
                  'userInteractionEnabled' => '@{open}' }.merge(margins)
    code = lines(component)
    tap = index_of(code, /\Adata\.onTap\?\(\)/)
    hit = index_of(code, /\A\.allowsHitTesting/)
    margin = index_of(code, /\A\.padding\(\.(top|leading), (24|11)\)/)
    expect([tap, hit, margin]).to all(be_a(Integer)), code.join("\n")
    expect(tap).to be < hit
    expect(hit).to be < margin
    expect(compilable_view(emitted(component), data: data_decls, stubs: library_stubs)).to compile_as_swift
  end
end
