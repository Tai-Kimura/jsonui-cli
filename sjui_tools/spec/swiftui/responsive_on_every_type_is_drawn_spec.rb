# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'
require_relative '../support/emitted_swift'

# A node's `responsive` override is drawn whatever its type (ticket
# sjui-codegen-drops-a-leafs-responsive). Only a View / SafeAreaView with
# children, a Collection and an Embed drew it — their converters route it
# themselves — and an app's generated converter; on the other 21 declared
# types (a Label, an Image, a TextField, a Switch, a ScrollView, a View without
# children …) it was dropped, silently, while kjui, rjui and both Dynamic
# runtimes draw it. Those are drawn per size class now
# (Views::ResponsiveLeafConverter → ResponsiveHelper.generate_leaf_function),
# each branch's view-local state declared once.
RSpec.describe 'sjui: a responsive override is drawn on every type' do
  include EmittedSwift

  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('responsive_every_type') }

  before do
    JsonUI::StageFailures.clear!
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    FileUtils.rm_rf(dir)
  end

  def convert(child)
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate('type' => 'View', 'child' => [child]))
    converter.convert_json_to_view(path)
  end

  OVERRIDE = { 'responsive' => { 'regular' => { 'opacity' => 0.37 } } }.freeze

  TYPES = {
    'Label' => { 'text' => 'x' }, 'TextField' => { 'text' => 't' }, 'TextView' => { 'text' => 't' },
    'Image' => { 'srcName' => 'x', 'width' => 10, 'height' => 10 },
    'NetworkImage' => { 'url' => 'https://e/x.png', 'width' => 10, 'height' => 10 }, 'IconLabel' => { 'text' => 'i' },
    'Switch' => {}, 'CheckBox' => { 'label' => 'c' }, 'Radio' => { 'items' => %w[a] }, 'Segment' => { 'items' => %w[a b] },
    'SelectBox' => { 'items' => %w[a] }, 'Slider' => {}, 'Progress' => { 'progress' => 0.5 }, 'Indicator' => {},
    'View' => {}, 'ScrollView' => { 'child' => [{ 'type' => 'Label', 'text' => 'k' }] },
    'GradientView' => { 'items' => %w[#FFFFFF #000000], 'child' => [{ 'type' => 'Label', 'text' => 'k' }] },
    'Blur' => { 'child' => [{ 'type' => 'Label', 'text' => 'k' }] },
    'TabView' => { 'tabs' => [{ 'title' => 'a', 'view' => 'a_tab' }] }, 'Web' => { 'url' => 'https://e' }
  }.freeze

  TYPES.each do |type, attrs|
    it "#{type}: the regular override is drawn, in a function per size class" do
      _code, _actions, _decls, _root, functions = convert({ 'type' => type }.merge(attrs).merge(OVERRIDE))
      expect(functions.size).to eq(1)
      expect(functions.first).to include('horizontalSizeClass == .regular').and include('.opacity(0.37)')
    end
  end

  it 'a Button: drawn per size class too (its own override attribute, fontSize)' do
    _code, _actions, _decls, _root, functions = convert({ 'type' => 'Button', 'text' => 'b', 'responsive' => { 'regular' => { 'fontSize' => 34 } } })
    expect(functions.size).to eq(1)
    expect(functions.first).to include('horizontalSizeClass == .regular').and include('34')
  end

  it 'the containers that drew it still do, as they did' do
    _code, _actions, _decls, _root, functions = convert({ 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'k' }] }.merge(OVERRIDE))
    expect(functions.size).to eq(1)
    expect(functions.first).to include('content: () -> Content').or include('content()')
  end

  it 'a stateful node, and one holding stateful children, declares each state once' do
    _code, _actions, decls, = convert({ 'type' => 'ScrollView', 'child' => [{ 'type' => 'Switch' }, { 'type' => 'TextField', 'text' => 'a' }] }.merge(OVERRIDE))
    states = decls.grep(/@State|@FocusState/)
    expect(states).to eq(['@State private var toggle_0_0_0IsOn: Bool = false', '@State private var textField_0_0_1Text: String = "a"'])
    expect(JsonUI::StageFailures.entries).to be_empty
  end

  # The functions, the declarations and the body, type-checked together —
  # the kinds SwiftUI draws alone (a ScrollView draws the library's
  # AdvancedKeyboardAvoidingScrollView, not on this machine's search path).
  it 'compiles: a Switch, a Slider, a TextField and a View without children' do
    path = File.join(dir, 'kinds.json')
    File.write(path, JSON.generate('type' => 'View', 'child' => [
      { 'type' => 'Switch' }.merge(OVERRIDE), { 'type' => 'Slider' }.merge(OVERRIDE),
      { 'type' => 'TextField', 'text' => 'a' }.merge(OVERRIDE), { 'type' => 'View', 'height' => 4 }.merge(OVERRIDE)
    ]))
    code, _actions, decls, _root, functions = converter.convert_json_to_view(path)
    expect(functions.size).to eq(4)
    body = code.to_s.lines.map { |l| "        #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {}
      struct EmittedHost: View {
          @Binding var data: TestData
      #{decls.map { |d| "    #{d}" }.join("\n")}
          var body: some View {
      #{body}
          }
      #{functions.join("\n")}
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end

  # The parent draws two stages OUTSIDE the child's function, from the
  # child's own attributes: the VisibilityWrapper (every parent) and the
  # ZStack offset from the margins (a parent without orientation). An
  # override of either reached only the function and was dropped; both are
  # drawn at the call site now, over the same size-class condition.
  describe 'what the parent draws for the child, per size class' do
    def convert_under(parent, child)
      path = File.join(dir, 'parent.json')
      File.write(path, JSON.generate(parent.merge('child' => [child])))
      converter.convert_json_to_view(path)
    end

    it 'visibility: the wrapper takes the value per size class' do
      code, = convert_under({ 'type' => 'View', 'orientation' => 'vertical' },
                            { 'type' => 'Switch', 'responsive' => { 'regular' => { 'visibility' => 'invisible' } } })
      expect(code).to include('VisibilityWrapper((horizontalSizeClass == .regular ? ("invisible" as String?) : ("visible" as String?)))')
    end

    it 'a ZStack margin: the offset takes the value per size class' do
      code, = convert_under({ 'type' => 'View' },
                            { 'type' => 'Switch', 'topMargin' => 4, 'responsive' => { 'regular' => { 'topMargin' => 13 } } })
      expect(code).to include('.offset(x: 0, y: (horizontalSizeClass == .regular ? 13 : 4))')
    end

    it 'a child without such an override is drawn as before' do
      code, = convert_under({ 'type' => 'View' }, { 'type' => 'Switch', 'topMargin' => 4, 'visibility' => 'invisible' })
      expect(code).to include('VisibilityWrapper("invisible")').and include('.offset(x: 0, y: 4)')
      expect(code).not_to include('horizontalSizeClass == .regular ?')
    end

    it 'compiles: both, under a ZStack' do
      code, _actions, decls, _root, functions = convert_under(
        { 'type' => 'View' },
        { 'type' => 'Switch', 'responsive' => { 'regular' => { 'visibility' => 'gone', 'topMargin' => 13 } } }
      )
      body = code.to_s.lines.map { |l| "        #{l}" }.join
      swift = <<~SWIFT
        #{EmittedSwift::LIBRARY_STUBS}
        struct VisibilityWrapper<Content: View>: View {
            init(_ visibility: String?, @ViewBuilder content: () -> Content) {}
            var body: some View { EmptyView() }
        }
        struct TestData {}
        struct EmittedHost: View {
            @Binding var data: TestData
        #{decls.map { |d| "    #{d}" }.join("\n")}
            var body: some View {
        #{body}
            }
        #{functions.join("\n")}
        }
      SWIFT
      expect(swift).to compile_as_swift.with_imports('SwiftUI')
    end
  end
end
