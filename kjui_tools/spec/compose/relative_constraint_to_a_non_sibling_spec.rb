# frozen_string_literal: true

require 'tmpdir'
require 'json'
require 'compose/compose_builder'

# A relative constraint whose target is not a sibling links to nothing
# (ticket jui-relative-constraint-target-not-a-sibling). The ConstraintLayout
# declares one createRef() per child; a target that is not one of them — the
# parent, a sibling's child, another container's element, an id nothing
# carries — was emitted as `bottom.linkTo(a.top)` all the same, and Gradle
# stopped on `Unresolved reference 'a'` (measured on jsonui-cli 2.5.25 with
# seven such shapes in a sample-app copy). `jui build` names each as an ERROR
# ([relative-constraints]); the link is left out so the project compiles, as
# iOS and the web drop the constraint. A sibling, and the element itself
# (declared, so it compiles; `jui build` names it), are linked as before.
RSpec.describe 'kjui codegen: a relative constraint to something that is not a sibling' do
  let(:temp_dir) { Dir.mktmpdir('kjui_non_sibling') }

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

  def box(id, extra = {})
    { 'type' => 'View', 'id' => id, 'width' => 20, 'height' => 20 }.merge(extra)
  end

  def emitted(children, root: 'View')
    json = { 'type' => root, 'id' => 'frame', 'width' => 100, 'height' => 100, 'child' => children }
    KjuiTools::Compose::ComposeBuilder.new.send(:generate_component, JSON.parse(JSON.generate(json)), 1, nil, is_root: true)
  end

  def links(code, ref = 's')
    block = code[/constrainAs\(#{ref}\) \{(.*?)\n\s*\}/m, 1] or raise "no constrainAs(#{ref}) in:\n#{code}"
    block.lines.map(&:strip).reject(&:empty?)
  end

  KEYS = %w[alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView alignTopView alignBottomView
            alignLeftView alignRightView alignCenterVerticalView alignCenterHorizontalView].freeze

  it 'links to a sibling, by every key, as before' do
    KEYS.each do |key|
      expect(links(emitted([box('s', key => 'a'), box('a')])).join).to include('a.'), key
    end
  end

  it 'leaves out every key whose target is not declared here' do
    KEYS.each do |key|
      code = emitted([box('s', key => 'nowhere'), box('a')])
      expect(code).not_to include('nowhere'), key
    end
  end

  it "leaves out a sibling's child, keeps the one that is a sibling" do
    code = emitted([box('s', 'alignTopOfView' => 'inner', 'alignLeftView' => 'a'),
                    { 'type' => 'View', 'id' => 'a', 'width' => 60, 'height' => 60, 'child' => [box('inner'), box('other')] }])
    expect(code).not_to include('inner.')
    expect(links(code)).to include('start.linkTo(a.start)')
  end

  it 'leaves out the parent, under a SafeAreaView root too' do
    expect(emitted([box('s', 'alignTopOfView' => 'frame'), box('a')])).not_to include('linkTo(frame.')
    expect(emitted([box('s', 'alignTopOfView' => 'frame'), box('a')], root: 'SafeAreaView')).not_to include('linkTo(frame.')
  end

  # What Gradle stopped on: the emitted links, against only the refs the
  # ConstraintLayout declares (s and a here) — a link to anything else is an
  # unresolved reference, as it was in the sample-app.
  it 'the emitted links compile against the refs the ConstraintLayout declares' do
    lines = KEYS.flat_map { |key| links(emitted([box('s', key => 'nowhere', 'alignLeftView' => 'a'), box('a')])) } +
            links(emitted([box('s', 'alignTopOfView' => 'frame'), box('a')])) +
            links(emitted([box('s', 'alignTopOfView' => 's'), box('a')]))
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
      fun host(s: Ref, a: Ref) = constrain {
      #{lines.map { |l| "    #{l}" }.join("\n")}
      }
    KT
  end

  it 'still links the element to itself (it compiles; jui build names it)' do
    expect(links(emitted([box('s', 'alignTopOfView' => 's'), box('a')]))).to eq(['bottom.linkTo(s.top)'])
  end
end
