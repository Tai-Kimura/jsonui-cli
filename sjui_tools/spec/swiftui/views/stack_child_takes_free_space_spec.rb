# frozen_string_literal: true

require 'swiftui/views/view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# A stack child that takes the free space along the main axis with a Spacer of
# its own (alignRight / alignLeft / centerHorizontal in a row, alignBottom /
# alignTop / centerVertical in a column, centerInParent in either) has it all:
# the gravity's packing Spacer is not emitted, as flexbox's justify-content
# gives way to an auto margin on the web. Beside it the two split the free
# space — a matchParent row drew alignRight in the middle and centerHorizontal
# a third of the way along (measured on iPhone 17 / iOS 27.2; ticket
# sjui-hstack-alignright-centred-by-trailing-spacer). SwiftJsonUI's Dynamic face
# reads the same rule (DynamicComponentBuilder.takesMainAxisSpace).
RSpec.describe 'a stack child that takes the free space' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 40, 'height' => 40 }.merge(extra)
  end

  def convert(orientation, kids, extra = {})
    size = orientation == 'horizontal' ? { 'width' => 'matchParent', 'height' => 60 } : { 'width' => 'matchParent', 'height' => 'matchParent' }
    SjuiTools::SwiftUI::Views::ViewConverter.new(
      { 'type' => 'View', 'orientation' => orientation, 'child' => kids }.merge(size).merge(extra),
      0, nil, SjuiTools::SwiftUI::ConverterFactory.new, SjuiTools::SwiftUI::ViewRegistry.new
    ).convert
  end

  # The stack's direct lines: its own Spacers, the children's Spacers, and the
  # children (by their accessibility identifier).
  def outline(code)
    lines = code.lines.map(&:strip)
    lines.filter_map do |l|
      next l if l.start_with?('Spacer(') || l.start_with?('if ') && l.include?('Spacer(')
      next Regexp.last_match(1) if l =~ /\.accessibilityIdentifier\("(\w+)"\)/
    end
  end

  {
    'alignRight in a row' => ['horizontal', [['r', { 'alignRight' => true }]], {}, %w[Spacer() r]],
    'centerHorizontal in a row' => ['horizontal', [['r', { 'centerHorizontal' => true }]], {}, %w[Spacer() r Spacer()]],
    'centerInParent in a row' => ['horizontal', [['r', { 'centerInParent' => true }]], {}, %w[Spacer() r Spacer()]],
    'a box, then alignRight' => ['horizontal', [['b', {}], ['r', { 'alignRight' => true }]], {}, %w[b Spacer() r]],
    'alignLeft, then a box' => ['horizontal', [['r', { 'alignLeft' => true }], ['b', {}]], {}, %w[r Spacer() b]],
    'alignLeft in a row with gravity right' => ['horizontal', [['r', { 'alignLeft' => true }]], { 'gravity' => 'right' }, %w[r Spacer()]],
    'alignBottom in a column' => ['vertical', [['r', { 'alignBottom' => true }]], {}, %w[Spacer() r]],
    'centerVertical in a column' => ['vertical', [['r', { 'centerVertical' => true }]], {}, %w[Spacer() r Spacer()]],
    'alignTop in a column with gravity bottom' => ['vertical', [['r', { 'alignTop' => true }]], { 'gravity' => 'bottom' }, %w[r Spacer()]],
  }.each do |name, (orientation, kids, extra, want)|
    it "emits no gravity Spacer beside #{name}" do
      expect(outline(convert(orientation, kids.map { |id, a| box(id, a) }, extra))).to eq(want)
    end
  end

  # The controls: a child with no main-axis alignment, or one aligned across
  # the axis only, leaves the gravity's Spacer as it was.
  it 'keeps the gravity Spacer when no child takes the free space' do
    expect(outline(convert('horizontal', [box('r')]))).to eq(['r', 'Spacer(minLength: 0)'])
    expect(outline(convert('horizontal', [box('r')], 'gravity' => 'right'))).to eq(['Spacer(minLength: 0)', 'r'])
    expect(outline(convert('horizontal', [box('r', 'alignBottom' => true)]))).to eq(['r', 'Spacer(minLength: 0)'])
    expect(outline(convert('vertical', [box('r', 'alignRight' => true)]))).to eq(['r', 'Spacer(minLength: 0)'])
  end

  # A child in a VisibilityWrapper is drawn without its alignment Spacers, so
  # it takes no free space and the gravity's Spacer stays.
  it 'keeps the gravity Spacer beside a child with visibility' do
    expect(outline(convert('horizontal', [box('r', 'alignRight' => true, 'visibility' => '@{shown}')]))).to eq(['r', 'Spacer(minLength: 0)'])
  end

  # Under `responsive` the child's Spacer holds only in some size classes, and
  # the gravity's Spacer stands down under the same condition.
  it 'gives way under the size classes whose alignment takes the free space' do
    code = convert('horizontal', [box('r', 'responsive' => { 'regular' => { 'alignRight' => true } })])
    regular = '(horizontalSizeClass == .regular ? true : false)'
    expect(outline(code)).to eq(["if #{regular} { Spacer() }", 'r', "if !(#{regular}) { Spacer(minLength: 0) }"])
  end

  it 'emits Swift a compiler reads' do
    codes = [convert('horizontal', [box('r', 'alignRight' => true)]),
             convert('vertical', [box('r', 'alignBottom' => true)]),
             convert('horizontal', [box('r', 'responsive' => { 'regular' => { 'alignRight' => true } })])]
    # The view's size class and the responsive child's own function, as the
    # generated view declares them.
    stubs = "var horizontalSizeClass: UserInterfaceSizeClass? = .compact\nfunc responsive0() -> some View { Color.red.frame(width: 40, height: 40) }"
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", stubs: stubs)).to compile_as_swift
  end
end
