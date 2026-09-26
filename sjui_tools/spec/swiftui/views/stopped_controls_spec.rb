# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/json_to_swiftui_converter'
require_relative '../../support/emitted_swift'
require_relative '../../support/swift_compiler'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# A control a stop holds (the tap rule's `control?`, which annotate! marks):
# `.allowsHitTesting` kept a touch out and nothing else — VoiceOver's
# activation called the control's default action through it (measured,
# SwiftJsonUI ConformanceHost -a11yActivationProbe: a Switch inside
# `userInteractionEnabled: false` switched, codegen and Dynamic; jsonui-cli
# 1.9.0). SwiftJsonUI's `.jsonuiStoppedControl(stopped)` replaces that action
# by nothing and reads the control as nothing to operate while it is stopped,
# and draws it as it is (measured against the control drawn without it;
# `.disabled(true)` dims it). The emit gives it the stop the build can see.
RSpec.describe 'sjui a control a stop holds' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = false
  end

  convert = lambda do |comp, reads: false|
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = reads
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  ensure
    SjuiTools::SwiftUI::Views::BaseViewConverter.reads_interaction_environment = false
  end

  # Every control type, with what it needs to convert.
  controls = {
    'Button' => { 'text' => 't', 'onClick' => '@{onTap}' }, 'Switch' => { 'isOn' => '@{on}' },
    'Toggle' => { 'isOn' => '@{on}' }, 'CheckBox' => { 'isOn' => '@{on}' },
    'Radio' => { 'items' => %w[a b], 'selectedValue' => '@{sel}' }, 'Segment' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' },
    'Slider' => { 'value' => '@{v}' }, 'SelectBox' => { 'items' => %w[a b], 'selectedIndex' => '@{idx}' },
    'TextField' => { 'text' => '@{t}' }, 'TextView' => { 'text' => '@{t}' }
  }
  node = ->(type) { { 'type' => type, 'id' => 'c' }.merge(controls[type]) }
  stopping = ->(flag, child) { { 'type' => 'View', 'id' => 'stop', 'userInteractionEnabled' => flag, 'child' => [child] } }

  it 'the rule marks a control a stop holds, and not a container' do
    tree = JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(
      stopping.call(false, { 'type' => 'View', 'child' => [node.call('Switch'), { 'type' => 'ScrollView', 'id' => 's' }] })
    )))
    marked = []
    JsonUIShared::TapAccessibility.walk(tree) { |n| marked << n['type'] if n[JsonUIShared::TapAccessibility::STOPPED_KEY] }
    expect(marked).to eq(['Switch'])
    bound = JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(stopping.call('@{u}', node.call('Slider')))))
    expect(bound['child'][0][JsonUIShared::TapAccessibility::GATES_KEY]).to eq(['@{u}'])
  end

  controls.each_key do |type|
    it "#{type}: inside false, with false of its own, inside a binding, reached by a stop handed down — and nothing beside no stop" do
      expect(convert.call(stopping.call(false, node.call(type))).scan('.jsonuiStoppedControl(true)').size).to eq(1)
      expect(convert.call(node.call(type).merge('userInteractionEnabled' => false)).scan('.jsonuiStoppedControl(true)').size).to eq(1)
      expect(convert.call(stopping.call('@{u}', node.call(type)))).to include('.jsonuiStoppedControl(!((data.u ?? false)))')
      expect(convert.call(node.call(type), reads: true)).to include('.jsonuiStoppedControl()')
      expect(convert.call(node.call(type))).not_to include('jsonuiStoppedControl')
      expect(convert.call(node.call(type).merge('userInteractionEnabled' => true))).not_to include('jsonuiStoppedControl')
    end
  end

  it 'not on what is not a control: a Label, a View, a container' do
    code = convert.call(stopping.call(false, { 'type' => 'View', 'child' => [
      { 'type' => 'Label', 'text' => 'x', 'onClick' => '@{onTap}' },
      { 'type' => 'ScrollView', 'id' => 's', 'child' => [{ 'type' => 'Label', 'text' => 'y' }] }
    ] }))
    expect(code).not_to include('jsonuiStoppedControl')
  end

  it 'a Switch inside a bound stop compiles with the modifier the library declares', :swift_compile do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason
    code = convert.call(stopping.call('@{u}', node.call('Switch')))
    # The data is @State here: the Switch binds `$data.on`.
    source = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      extension View { func jsonuiStoppedControl(_ stopped: Bool = false) -> some View { self } }
      struct TestData { var u: Bool? = false; var on: Bool = false }
      struct EmittedHost: View {
          @State var data = TestData()
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      }
    SWIFT
    expect(source).to compile_as_swift
  end
end
