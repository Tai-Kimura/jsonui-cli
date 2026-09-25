# frozen_string_literal: true

require 'swiftui/converter_factory'
require 'swiftui/data_model_updater'
require 'core/tap_accessibility'
require_relative '../support/emitted_swift'

# An empty or blank onClick names no method (shared/core/tap_accessibility.rb
# `handler?`), so it is no handler on every converter that reads one, and no
# Data callback. They emitted `data.?()` / `data.   ?()` and declared
# `var : (() -> Void)? = nil` — not Swift (ticket
# kjui-empty-onclick-emits-invalid-kotlin, all three codegens). The tap on a
# plain view is covered per vector in views/tap_accessibility_emission_spec.rb.
RSpec.describe 'sjui empty and blank onClick' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  EMPTY_TAP_HANDLERS = ['', '   ', '@{}', '@{ }'].freeze
  # A call on a blank name: `data.?()`, `data.   ?()`, `data.@{}?()`.
  EMPTY_TAP_CALL = /data\.(\s*|@\{\s*\})\?/.freeze

  def convert(layout)
    JsonUIShared::TapAccessibility.annotate!(layout)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(layout).convert
  end

  include EmittedSwift

  # The generated Data file for these onClick values, as swiftc can read it
  # here: `import SwiftJsonUI` is the one line dropped (the module is not on
  # this machine's search path, and nothing in the file uses it).
  def data_file(handlers)
    updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
    actions = handlers.map { |h| updater.send(:onclick_action_name, 'type' => 'Label', 'onClick' => h) }.compact
    updater.send(:generate_data_content, 'Probe', [], actions).sub("import SwiftJsonUI\n", '')
  end

  def partial(type, handler)
    { 'type' => type, 'id' => 'p', 'text' => 'Open terms',
      'partialAttributes' => [{ 'range' => [0, 4], 'fontColor' => '#FF0000', 'onClick' => handler }] }
  end

  EMPTY_TAP_HANDLERS.each do |blank|
    context blank.inspect do
      it 'gives a Button an empty action' do
        code = convert('type' => 'Button', 'id' => 'b', 'text' => 'Go', 'onClick' => blank)
        expect(code).to include('action: { },')
        expect(code).not_to match(EMPTY_TAP_CALL)
      end

      it 'gives a Button range and a Label range no onClick' do
        %w[Button Label].each do |type|
          code = convert(partial(type, blank))
          expect(code).not_to include('onClick:'), type
          expect(code).not_to match(EMPTY_TAP_CALL), type
        end
      end

      it 'gives a CheckBox no value-change callback' do
        code = convert('type' => 'CheckBox', 'id' => 'c', 'onClick' => blank)
        expect(code).not_to include('onValueChanged:')
        expect(code).not_to match(EMPTY_TAP_CALL)
      end

      it 'keeps an IconLabel a view' do
        code = convert('type' => 'IconLabel', 'id' => 'l', 'text' => 'x', 'onClick' => blank)
        expect(code).to include('IconLabelView(')
        expect(code).not_to include('IconLabelButton(')
        expect(code).not_to match(EMPTY_TAP_CALL)
      end

      it 'gives an Image no tap' do
        code = convert('type' => 'Image', 'id' => 'i', 'src' => 'icon', 'onClick' => blank)
        expect(code).not_to include('.onTapGesture')
        expect(code).not_to match(EMPTY_TAP_CALL)
      end

      it 'calls nothing from a Radio tap' do
        code = convert('type' => 'Radio', 'id' => 'r', 'group' => 'g', 'text' => 'A', 'onClick' => blank)
        expect(code).not_to match(EMPTY_TAP_CALL)
      end

      it 'declares no Data callback, and the Data file compiles' do
        updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
        expect(updater.send(:onclick_action_name, 'type' => 'Label', 'onClick' => blank)).to be_nil
        expect(data_file([blank, '@{onGo}'])).to compile_as_swift
      end

      it 'emits an Image and a Label range that compile' do
        views = [convert('type' => 'Image', 'id' => 'i', 'src' => 'icon', 'onClick' => blank), convert(partial('Label', blank))]
        expect(compilable_view("VStack {\n#{views.join("\n")}\n}", data: ['var onGo: (() -> Void)? = nil'])).to compile_as_swift
      end
    end
  end

  # The control: a real handler still reaches every one of them.
  it 'still wires a real onClick on each' do
    handler = '@{onGo}'
    expect(convert('type' => 'Button', 'id' => 'b', 'text' => 'Go', 'onClick' => handler)).to include('data.onGo?()')
    expect(convert(partial('Button', handler))).to include('onClick: { data.onGo?() }')
    expect(convert(partial('Label', handler))).to include('onClick: { data.onGo?() }')
    expect(convert('type' => 'CheckBox', 'id' => 'c', 'onClick' => handler)).to include('onValueChanged:')
    expect(convert('type' => 'IconLabel', 'id' => 'l', 'text' => 'x', 'onClick' => handler)).to include('IconLabelButton(')
    expect(convert('type' => 'Image', 'id' => 'i', 'src' => 'icon', 'onClick' => handler)).to include('.onTapGesture')
    expect(convert('type' => 'Radio', 'id' => 'r', 'group' => 'g', 'text' => 'A', 'onClick' => handler)).to include('data.onGo?()')
    updater = SjuiTools::SwiftUI::DataModelUpdater.allocate
    expect(updater.send(:onclick_action_name, 'type' => 'Label', 'onClick' => handler)).to eq('onGo')
    expect(data_file([handler])).to include('var onGo: (() -> Void)? = nil')
    views = [convert('type' => 'Image', 'id' => 'i', 'src' => 'icon', 'onClick' => handler), convert(partial('Label', handler))]
    expect(compilable_view("VStack {\n#{views.join("\n")}\n}", data: ['var onGo: (() -> Void)? = nil'])).to compile_as_swift
  end
end
