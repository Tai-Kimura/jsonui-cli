# frozen_string_literal: true

require 'uikit/ui_control_event_manager'
require 'uikit/handlers/label_binding_handler'
require_relative '../support/swift_compiler'

# The UIKit codegen reads an empty or blank onClick the way the SwiftUI one
# does (shared/core/tap_accessibility.rb `handler?`): no click, and a
# partialAttributes range with `"@{}"` gets no handler. They emitted
# `row?.click{ [weak self] _ in self?.?() }` and
# `setPartialAttributeOnClick(at: 0, handler: )` — not Swift (ticket
# kjui-empty-onclick-emits-invalid-kotlin, all three codegens).
RSpec.describe 'sjui UIKit empty and blank onClick' do
  UIKIT_EMPTY_TAPS = ['', '   ', '@{}', '@{ }'].freeze

  it 'binds no click for an empty or blank onClick, and bindView compiles' do
    manager = SjuiTools::UIKit::UIControlEventManager.new
    UIKIT_EMPTY_TAPS.each_with_index { |value, i| manager.add_click_event("blank#{i}", value) }
    manager.add_click_event('named', '@{onGo}')
    bind_view = manager.generate_bind_view_method
    expect(bind_view.scan('?.click{').size).to eq(1)
    expect(bind_view).to include('named?.click{ [weak self] _ in self?.onGo?() }')
    expect(<<~SWIFT).to compile_as_swift
      class TapView {
          var isUserInteractionEnabled = false
          func click(_ handler: @escaping (Any) -> Void) {}
      }
      class BindingBase { func bindView() {} }
      final class ProbeBinding: BindingBase {
          var named: TapView? = TapView()
          var onGo: (() -> Void)?
      #{bind_view}
      }
    SWIFT
  end

  it 'gives a range with an empty binding no click handler' do
    %w[@{} @{\ }].each do |value|
      content = []
      handler = SjuiTools::UIKit::LabelBindingHandler.new(content, {}, {})
      handler.handle_specific_binding('label', 'partialAttributes', [{ 'range' => [0, 4], 'onClick' => value }])
      expect(content.join).not_to include('setPartialAttributeOnClick'), value
    end
    # The control: a named one still gets it.
    content = []
    SjuiTools::UIKit::LabelBindingHandler.new(content, {}, {})
                                         .handle_specific_binding('label', 'partialAttributes', [{ 'range' => [0, 4], 'onClick' => '@{onTerms}' }])
    expect(content.join).to include('label?.setPartialAttributeOnClick(at: 0, handler: onTerms)')
  end
end
