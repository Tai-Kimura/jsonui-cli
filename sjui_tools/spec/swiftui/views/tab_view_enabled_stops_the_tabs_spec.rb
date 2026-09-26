# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require_relative '../../support/swift_compiler'
require 'core/tap_accessibility'
require 'json'

# A TabView's `enabled` stops its tab items, not the tab view (4f's ruling,
# jsonui-cli 1.9.0 — kjui's NavigationBarItem `enabled`, web's
# `<button disabled>` per tab). The tab view's control is its row of tabs;
# what a tab shows is a layout of its own, which `userInteractionEnabled`
# stops. `.disabled` on the whole TabView — emitted twice, the bag's and
# apply_outer_disabled's — disabled every control in the tab shown as well
# (measured, SwiftJsonUI ConformanceHost -tabEnabledProbe: a Button in the
# first tab read disabled and did not call). SwiftJsonUI's
# `.jsonuiTabItemsEnabled` sets the tab bar items' isEnabled from each tab's
# content (only the tab on screen is in the window to reach the tab bar).
RSpec.describe 'sjui a TabView\'s enabled stops its tabs' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  convert = lambda do |comp|
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::TapAccessibility.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end
  tabs = [{ 'title' => 'One', 'view' => 'te_one' }, { 'title' => 'Two', 'view' => 'te_two' }, { 'title' => 'Three' }]
  tab_view = ->(more = {}) { { 'type' => 'TabView', 'id' => 'tv', 'tabs' => tabs }.merge(more) }

  it 'enabled: false — every tab tells the tab bar, and nothing is disabled' do
    code = convert.call(tab_view.call('enabled' => false))
    expect(code).not_to include('.disabled(')
    expect(code.scan('.jsonuiTabItemsEnabled(false)').size).to eq(tabs.size), code
    # Each on the tab's content, before its tab item.
    expect(code).to match(/TeOneView\(\)\n\s*\.jsonuiTabItemsEnabled\(false\)\n\s*\.tabItem \{/)
  end

  it 'a bound enabled — every tab tells the tab bar the binding, and nothing is disabled' do
    code = convert.call(tab_view.call('enabled' => '@{on}'))
    expect(code).not_to include('.disabled(')
    expect(code.scan('.jsonuiTabItemsEnabled((data.on ?? false))').size).to eq(tabs.size), code
  end

  it 'enabled: true, or none — as before: no tab bar call' do
    expect(convert.call(tab_view.call('enabled' => true))).not_to include('jsonuiTabItemsEnabled')
    expect(convert.call(tab_view.call)).not_to include('jsonuiTabItemsEnabled')
  end

  it 'userInteractionEnabled stops the tab view and what it shows, as before' do
    code = convert.call(tab_view.call('userInteractionEnabled' => false))
    expect(code).to include('.allowsHitTesting(false)')
    expect(code).to include('.environment(\\.jsonuiInteractionStopped, true)')
    expect(code).not_to include('jsonuiTabItemsEnabled')
  end

  # The tab view's own tap and gestures follow `enabled` as kjui's Scaffold
  # gates them (gesture_gate): none for false, the binding for a bound one.
  gestures = { 'onClick' => '@{onTap}', 'onLongPress' => '@{onLP}', 'onPan' => '@{onDrag}', 'onPinch' => '@{onZoom}' }

  it 'enabled: false — no tap and no gesture of its own' do
    code = convert.call(tab_view.call({ 'enabled' => false }.merge(gestures)))
    %w[onTap onLP onDrag onZoom].each { |name| expect(code).not_to include("data.#{name}"), code }
  end

  it 'a bound enabled — its tap masked, each gesture\'s call gated' do
    code = convert.call(tab_view.call({ 'enabled' => '@{on}' }.merge(gestures)))
    expect(code).to include('including: (data.on ?? false) ? .all : .subviews)')
    %w[onLP onDrag onZoom].each { |name| expect(code).to include("if (data.on ?? false) { data.#{name}?() }"), code }
  end

  it 'no enabled — its gestures as before' do
    code = convert.call(tab_view.call(gestures))
    expect(code).to include(".onLongPressGesture {\n")
    expect(code).not_to include('if (data.on')
  end

  it 'a bound enabled compiles against the modifier the library declares', :swift_compile do
    skip("swiftc: #{SwiftCompiler.unavailable_reason}") if SwiftCompiler.unavailable_reason
    code = convert.call(tab_view.call({ 'enabled' => '@{on}' }.merge(gestures)))
    source = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      extension View { func jsonuiTabItemsEnabled(_ enabled: Bool) -> some View { self } }
      struct TeOneView: View { var body: some View { Text("1") } }
      struct TeTwoView: View { var body: some View { Text("2") } }
      struct TestData {
          var on: Bool? = false
          var onTap: (() -> Void)? = nil
          var onLP: (() -> Void)? = nil
          var onDrag: (() -> Void)? = nil
          var onZoom: (() -> Void)? = nil
      }
      struct EmittedHost: View {
          var data = TestData()
          var body: some View {
      #{code.lines.map { |l| "        #{l}" }.join}
          }
      }
    SWIFT
    expect(source).to compile_as_swift
  end
end
