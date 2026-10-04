# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'compose/compose_builder'

# A sibling aligned to an anchor reaches the box the anchor DRAWS, not its
# margin-inclusive ref box (ticket
# kjui-relative-align-view-measures-the-anchor-with-its-margin). An anchor
# with no positioning constraint draws its margins as padding around its
# declared size, so its createRef() box starts at 0 and the drawn box at the
# margin. Until jsonui-cli 1.9.15 the linkTo()s pointed at the ref box: with
# the conformance fixture's anchor (topMargin / leftMargin 120), a target
# aligned to its top, left or centre landed at 0 / 85 on Android (codegen and
# Dynamic alike) while iOS and web placed it at 120 / 145; its far edges were
# right by accident, the margin sitting on the near side.
RSpec.describe 'kjui codegen: relative alignment to a margined anchor' do
  let(:temp_dir) { Dir.mktmpdir('kjui_align_anchor') }

  before do
    config = { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
               'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app',
               'project_path' => temp_dir }
    FileUtils.mkdir_p(File.join(temp_dir, 'src/main/assets/Layouts'))
    FileUtils.mkdir_p(File.join(temp_dir, 'src/main/kotlin/com/example/app/views'))
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(Dir).to receive(:pwd).and_return(temp_dir)
  end

  after { FileUtils.rm_rf(temp_dir) }

  ANCHOR = { 'type' => 'View', 'id' => 'anchor', 'width' => 50, 'height' => 50, 'topMargin' => 120, 'leftMargin' => 120 }.freeze

  def emitted(attr, root: 'View', anchor: ANCHOR, target_extra: {})
    json = { 'type' => root, 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
             'child' => [anchor, { 'type' => 'View', 'id' => 'target', 'width' => 200, 'height' => 200,
                                   attr => 'anchor' }.merge(target_extra)] }
    # The generator writes into the nodes it walks: hand it a deep copy.
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, JSON.parse(JSON.generate(json)), 1, nil, is_root: true)
  end

  # The constrainAs block of `target`.
  def links(code)
    block = code[/constrainAs\(target\) \{(.*?)\n\s*\}/m, 1] or raise "no constrainAs(target) in:\n#{code}"
    block.lines.map(&:strip).reject(&:empty?)
  end

  EXPECTED = {
    'alignTopView' => ['top.linkTo(anchor.top, margin = 120.dp)'],
    'alignBottomView' => ['bottom.linkTo(anchor.bottom)'],
    'alignLeftView' => ['start.linkTo(anchor.start, margin = 120.dp)'],
    'alignRightView' => ['end.linkTo(anchor.end)'],
    'alignCenterVerticalView' => ['top.linkTo(anchor.top, margin = 120.dp)', 'bottom.linkTo(anchor.bottom)'],
    'alignCenterHorizontalView' => ['start.linkTo(anchor.start, margin = 120.dp)', 'end.linkTo(anchor.end)'],
    # `bottom.linkTo(a.top, m)` is a.top - m: the drawn top is a.top + 120.
    'alignTopOfView' => ['bottom.linkTo(anchor.top, margin = (-120.dp))'],
    'alignBottomOfView' => ['top.linkTo(anchor.bottom)'],
    'alignLeftOfView' => ['end.linkTo(anchor.start, margin = (-120.dp))'],
    'alignRightOfView' => ['start.linkTo(anchor.end)']
  }.freeze

  it "links each alignment to the anchor's drawn box (the conformance fixture's anchor)" do
    EXPECTED.each { |attr, lines| expect(links(emitted(attr))).to eq(lines), attr }
  end

  it 'reads every margin spelling the anchor draws — a margins array per edge' do
    anchor = ANCHOR.reject { |k, _| k.end_with?('Margin') }.merge('margins' => [10, 20, 30, 40])
    expect(links(emitted('alignTopView', anchor: anchor))).to eq(['top.linkTo(anchor.top, margin = 10.dp)'])
    expect(links(emitted('alignBottomView', anchor: anchor))).to eq(['bottom.linkTo(anchor.bottom, margin = 30.dp)'])
    expect(links(emitted('alignLeftView', anchor: anchor))).to eq(['start.linkTo(anchor.start, margin = 40.dp)'])
    expect(links(emitted('alignRightView', anchor: anchor))).to eq(['end.linkTo(anchor.end, margin = 20.dp)'])
    expect(links(emitted('alignRightOfView', anchor: anchor))).to eq(['start.linkTo(anchor.end, margin = (-20.dp))'])
    expect(links(emitted('alignBottomOfView', anchor: anchor))).to eq(['top.linkTo(anchor.bottom, margin = (-30.dp))'])
  end

  it "adds the target's own margin to the anchor's, as before" do
    expect(links(emitted('alignTopView', target_extra: { 'topMargin' => 10 })))
      .to eq(['top.linkTo(anchor.top, margin = (120.dp + (-10.dp)))'])
    expect(links(emitted('alignTopOfView', target_extra: { 'bottomMargin' => 8 })))
      .to eq(['bottom.linkTo(anchor.top, margin = (8.dp + (-120.dp)))'])
  end

  it 'an anchor positioned by its own constraints keeps its margins in linkTo, so nothing is added (control)' do
    positioned = ANCHOR.merge('alignTop' => true, 'alignLeft' => true)
    expect(links(emitted('alignTopView', anchor: positioned))).to eq(['top.linkTo(anchor.top)'])
  end

  it 'the SafeAreaView constraint path does the same' do
    expect(links(emitted('alignTopView', root: 'SafeAreaView'))).to eq(['top.linkTo(anchor.top, margin = 120.dp)'])
    expect(links(emitted('alignTopOfView', root: 'SafeAreaView'))).to eq(['bottom.linkTo(anchor.top, margin = (-120.dp))'])
  end

  it 'the emitted links compile against the anchor and Dp shapes ConstraintLayout declares' do
    lines = EXPECTED.keys.flat_map { |attr| links(emitted(attr)) } +
            links(emitted('alignTopView', target_extra: { 'topMargin' => 10 }))
    expect(<<~KT).to compile_as_kotlin
      data class Dp(val value: Float) {
          operator fun plus(other: Dp) = Dp(value + other.value)
          operator fun unaryMinus() = Dp(-value)
      }
      val Int.dp: Dp get() = Dp(toFloat())
      class HorizontalAnchor
      class VerticalAnchor
      class HorizontalAnchorable { fun linkTo(anchor: HorizontalAnchor, margin: Dp = 0.dp) {} }
      class VerticalAnchorable { fun linkTo(anchor: VerticalAnchor, margin: Dp = 0.dp) {} }
      class Ref { val top = HorizontalAnchor(); val bottom = HorizontalAnchor(); val start = VerticalAnchor(); val end = VerticalAnchor() }
      class Scope { val top = HorizontalAnchorable(); val bottom = HorizontalAnchorable(); val start = VerticalAnchorable(); val end = VerticalAnchorable() }
      fun constrain(block: Scope.() -> Unit) {}
      fun host(anchor: Ref) = constrain {
      #{lines.map { |l| "    #{l}" }.join("\n")}
      }
    KT
  end
end
