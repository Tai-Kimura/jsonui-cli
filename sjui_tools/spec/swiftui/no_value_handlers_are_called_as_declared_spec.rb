# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'core/stage_failures'
require_relative '../support/emitted_swift'

# A handler that takes no value — a tap (onClick on any type, the onclick
# selector), a long press, onAppear / onDisappear — is called as the data
# declares it (4f's ruling on control-onclick-is-called-differently-on-every-
# path, 1.9.0): `(String)` with the viewId (the id, else the drawn type and
# the position — JsonUIShared::LayoutPath.view_id), `()` with no argument.
#
# Every one of these was `data.x?()` whatever the handler took — a
# `((String) -> Void)?` one did not compile — while a Button's and a
# control's onClick were already handed the viewId. An Image registered its
# own viewId call, replaced by the shared tap for every gate but
# `enabled: false`, where it stayed: a disabled Image still tapped on this
# path only (SwiftJsonUI's Dynamic runtime attaches no tap to it). Measured
# end to end by SwiftJsonUI ConformanceHost TapArityProbeUITests.
RSpec.describe 'sjui: a handler that takes no value is called as its declaration asks' do
  include EmittedSwift

  let(:converter) { SjuiTools::SwiftUI::JsonToSwiftUIConverter.new }
  let(:dir) { Dir.mktmpdir('no_value_handlers') }

  before { JsonUI::StageFailures.clear! }
  after { FileUtils.rm_rf(dir) }

  DATA = [
    { 'name' => 'named', 'class' => '((String) -> Void)?' },
    { 'name' => 'bare', 'class' => '(() -> Void)?' }
  ].freeze

  def convert(children)
    path = File.join(dir, 'probe.json')
    File.write(path, JSON.generate('type' => 'View', 'data' => DATA, 'child' => children))
    converter.convert_json_to_view(path).first.to_s
  end

  # The node second in the layout (a Label first), so its viewId is
  # `<type>_0_1`.
  def at_one(node)
    convert([{ 'type' => 'Label', 'text' => 'first' }, node])
  end

  PORTS = {
    'a View tap' => [{ 'type' => 'View', 'height' => 30, 'onClick' => '@{H}' }, 'view'],
    'an Image tap' => [{ 'type' => 'Image', 'srcName' => 'x', 'onClick' => '@{H}' }, 'image'],
    'a Label tap' => [{ 'type' => 'Label', 'text' => 'x', 'onClick' => '@{H}' }, 'label'],
    'the onclick selector' => [{ 'type' => 'View', 'height' => 30, 'onclick' => 'H' }, 'view'],
    'a long press' => [{ 'type' => 'View', 'height' => 30, 'onLongPress' => '@{H}' }, 'view'],
    'onAppear' => [{ 'type' => 'View', 'height' => 30, 'onAppear' => 'H' }, 'view'],
    'onDisappear' => [{ 'type' => 'View', 'height' => 30, 'onDisappear' => 'H' }, 'view']
  }.freeze

  def with(node, handler)
    node.to_h { |k, v| [k, v.is_a?(String) ? v.sub('H', handler) : v] }
  end

  PORTS.each do |port, (node, drawn)|
    it "#{port}: `(String)` is handed the viewId, `()` nothing" do
      expect(at_one(with(node, 'named'))).to include("data.named?(\"#{drawn}_0_1\")")
      bare = at_one(with(node, 'bare'))
      expect(bare).to include('data.bare?()')
      expect(bare).not_to include('data.bare?("')
    end

    it "#{port}: an explicit id is the viewId" do
      expect(at_one(with(node, 'named').merge('id' => 'mine'))).to include('data.named?("mine")')
    end
  end

  # As the binding spelling was; the onclick selector wrote `data.tapped:?()`,
  # which does not parse.
  it 'the selector spelling with a sender is handed `self`' do
    expect(at_one({ 'type' => 'View', 'height' => 30, 'onclick' => 'tapped:' })).to include('data.tapped?(self)')
  end

  it 'an Image with enabled false has no tap, as every other type' do
    code = at_one({ 'type' => 'Image', 'srcName' => 'x', 'enabled' => false, 'onClick' => '@{named}' })
    expect(code).not_to include('data.named?')
    expect(code).not_to include('onTapGesture')
  end

  # Every call above, type-checked over the declared handlers.
  it 'compiles: every call, over its declaration' do
    calls = PORTS.values.flat_map do |node, _|
      %w[named bare].flat_map { |h| at_one(with(node, h)).scan(/data\.(?:named|bare)\?\([^()\n]*\)/) }
    end
    expect(calls.size).to be >= PORTS.size * 2
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {
          var named: ((String) -> Void)? = nil
          var bare: (() -> Void)? = nil
      }
      struct EmittedHost {
          let data = TestData()
      #{calls.each_with_index.map { |c, i| "    func c#{i}() { #{c} }" }.join("\n")}
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end
end
