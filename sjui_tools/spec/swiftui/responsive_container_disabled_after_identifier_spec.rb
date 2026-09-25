# frozen_string_literal: true

require 'swiftui/json_to_swiftui_converter'
require 'tmpdir'
require_relative '../support/emitted_swift'

# A container with `responsive` emits its modifiers per size class INSIDE its
# `responsiveN` wrapper, and its identifier at the call site, OUTSIDE it. So
# its `.disabled` sat inside the wrapper, outside the accessibility element
# the identifier forms, and nothing followed the identifier: XCUITest read
# the node as enabled while it was disabled (a UI test on an iOS
# simulator). Every other path writes `.disabled` again after the identifier
# (BaseViewConverter#apply_outer_disabled). The wrapper is built at the
# view-generation stage, so these arms go through it.
RSpec.describe SjuiTools::SwiftUI::JsonToSwiftUIConverter, 'a responsive container and .disabled' do
  before do
    allow(SjuiTools::SwiftUI::StyleLoader).to receive(:load_and_merge) { |data| data }
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  include EmittedSwift

  def emit(node)
    Dir.mktmpdir do |dir|
      file = File.join(dir, 'screen.json')
      File.write(file, JSON.generate('type' => 'View', 'orientation' => 'vertical', 'child' => [node]))
      code, _actions, _state, _children, functions = described_class.new.convert_json_to_view(file)
      [code, Array(functions).join("\n")]
    end
  end

  def call_site(node)
    code, functions = emit(node)
    [code.lines.map(&:strip), functions]
  end

  # The modifier right after the node's identifier.
  def after_identifier(lines, id)
    at = lines.index(".accessibilityIdentifier(\"#{id}\")")
    expect(at).not_to be_nil
    lines[at + 1]
  end

  button = { 'type' => 'View', 'id' => 'next_button', 'onClick' => '@{onNext}',
             'child' => [{ 'type' => 'Label', 'text' => 'Next' }] }
  responsive = { 'responsive' => { 'regular' => { 'maxWidth' => 400, 'centerHorizontal' => true } } }

  {
    'a bound enabled' => ['@{nextButtonEnabled}', '.disabled(!((data.nextButtonEnabled ?? false)))'],
    'enabled: false' => [false, '.disabled(true)']
  }.each do |name, (enabled, line)|
    it "#{name}: .disabled follows the identifier with responsive, as without it" do
      plain, = call_site(button.merge('enabled' => enabled))
      wrapped, functions = call_site(button.merge('enabled' => enabled).merge(responsive))
      expect(functions).to include('responsive0')   # the wrapper path was taken
      expect(functions).to include(line)             # inside it, per size class
      expect(after_identifier(plain, 'next_button')).to eq(line)
      expect(after_identifier(wrapped, 'next_button')).to eq(line)
    end
  end

  it 'the call site and its wrapper compile' do
    code, functions = emit(button.merge('enabled' => '@{nextButtonEnabled}').merge(responsive))
    # The wrapper is a member of the view it is emitted into, reading its
    # size classes; the host declares them as the generated view does.
    host = "extension EmittedHost {\n" \
           "    var horizontalSizeClass: UserInterfaceSizeClass? { .regular }\n" \
           "    var verticalSizeClass: UserInterfaceSizeClass? { .regular }\n" \
           "#{functions}\n}\n"
    data = ['var onNext: (() -> Void)? = nil', 'var nextButtonEnabled: Bool? = nil']
    expect(compilable_view(code, data: data, stubs: host)).to compile_as_swift
  end

  it 'control: no enabled, nothing after the identifier' do
    wrapped, functions = call_site(button.merge(responsive))
    expect(functions).to include('responsive0')
    at = wrapped.index('.accessibilityIdentifier("next_button")')
    expect(wrapped[at + 1].to_s).not_to start_with('.disabled')
  end

  # Control, not a finding: the tap gate was never lost on this path (before
  # register_interaction_gates it sat at the call site, from the binding
  # handler; now it is inside the wrapper with the tap). Either gates the tap.
  it 'the tap gate is not dropped on this path' do
    wrapped, functions = call_site(button.merge('canTap' => '@{canNext}').merge(responsive))
    expect(functions).to include('.onTapGesture')
    expect((wrapped.join("\n") + functions)).to include('.allowsHitTesting((data.canNext ?? false))')
  end
end
