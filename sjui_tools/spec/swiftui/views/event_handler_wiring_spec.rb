# frozen_string_literal: true

require 'swiftui/views/base_view_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require 'swiftui/views/color_helper'
require_relative '../../support/emitted_swift'

# A handler written the way the SSoT declares it is called, on the iOS
# codegen path. Measured 2026-10-03 with the event x declared-form
# conformance probes (support lane 2), each of these built with warning 0 and
# called nothing, or did not compile:
#   - a TextField with no `text` got `.constant("")`: not editable, and its
#     onTextChange dropped (sjui-textfield-without-a-text-binding-cannot-be-
#     typed-into-and-drops-ontextchange);
#   - a Button's `onclick` and `onLongPress` were never attached
#     (sjui-button-onclick-selector-and-onlongpress-are-never-called);
#   - SelectBox read `onValueChange` only (sjui-selectbox-onvaluechanged-
#     alias-is-never-called);
#   - Radio's group form wrote the selection and called nothing
#     (sjui-radio-group-form-never-calls-onvaluechange);
#   - Segment `valueChange: "@{h}"` was dropped (sjui-segment-valuechange-
#     binding-is-never-called);
#   - TextField focus events wrote `data.@{h}?()` (sjui-textfield-focus-
#     events-write-the-binding-braces);
#   - a one-parameter handler was called by its spelling, not its arity:
#     `(String) -> Void` with (id, value), `(Any) -> Void` with nothing
#     (sjui-radio-items-calls-a-one-parameter-handler-with-two-arguments).
#
# The drawn and called arm is the probe run on SwiftJsonUI's ConformanceHost
# codegen face. Here: the wiring as text, and the call shapes compiled.
RSpec.describe 'sjui: event handlers in their declared forms' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }
  after { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def declare(classes)
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions =
      classes.to_h { |name, klass| [name, { 'name' => name, 'class' => klass }] }
  end

  def emit(component)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter({ 'id' => 'target' }.merge(component), 0, nil, factory).convert.to_s
  end

  describe 'TextField with no text' do
    it 'keeps its own @State, so it is editable and onTextChange is wired' do
      declare('h' => '(String) -> Void')
      out = emit('type' => 'TextField', 'onTextChange' => '@{h}')
      expect(out).not_to include('.constant("")')
      expect(out).to include('text: $targetText', '.onChange(of: targetText)', 'data.h?(newValue)')
    end

    it 'focus events written as a binding call the handler by name' do
      declare('f' => '() -> Void', 'b' => '() -> Void')
      out = emit('type' => 'TextField', 'text' => '@{t}', 'onFocus' => '@{f}', 'onEndEditing' => '@{b}')
      expect(out).to include('data.f?()', 'data.b?()')
      expect(out).not_to include('@{')
    end
  end

  describe 'Button' do
    it 'calls `onclick` from its action, and attaches onLongPress beside it' do
      declare('tapped' => '() -> Void', 'held' => '() -> Void')
      out = emit('type' => 'Button', 'text' => 'Go', 'onclick' => 'tapped', 'onLongPress' => '@{held}')
      expect(out).to include('action: { data.tapped?() },', '.simultaneousGesture(LongPressGesture().onEnded { _ in', 'data.held?()')
    end

    it 'control: onClick still wins over onclick' do
      declare('a' => '() -> Void', 'b' => '() -> Void')
      expect(emit('type' => 'Button', 'text' => 'Go', 'onClick' => '@{a}', 'onclick' => 'b')).to include('action: { data.a?() },')
    end
  end

  it "SelectBox: onValueChanged, onValueChange's alias, reaches the same call" do
    declare('pick' => '(String) -> Void', 'sel' => 'String')
    out = emit('type' => 'SelectBox', 'items' => %w[One Two], 'selectedItem' => '@{sel}', 'onValueChanged' => '@{pick}')
    expect(out).to include('data.pick?(')
  end

  it "Radio's group form calls onValueChange with its value" do
    declare('pick' => '(String) -> Void')
    out = emit('type' => 'Radio', 'group' => 'g', 'value' => 'a', 'onValueChange' => '@{pick}')
    expect(out).to include('selectedG = "a"', 'data.pick?("a")')
  end

  it 'Segment valueChange: the binding is called as the bare name is' do
    declare('pick' => '(Int) -> Void')
    binding = emit('type' => 'Segment', 'items' => %w[A B], 'valueChange' => '@{pick}')
    bare = emit('type' => 'Segment', 'items' => %w[A B], 'valueChange' => 'pick')
    expect(binding).to include('data.pick?(newValue)')
    expect(binding[/Picker\(.*\{$/]).to eq(bare[/Picker\(.*\{$/])
  end

  describe 'the call follows the declared parameter count' do
    def call(klass, value)
      declare('h' => klass)
      factory = SjuiTools::SwiftUI::ConverterFactory.new
      factory.create_converter({ 'type' => 'View', 'id' => 'target' }, 0, nil, factory)
             .send(:get_event_handler_invocation, '@{h}', 'target', value)
    end

    it 'one parameter takes the value; two take (id, value); none take nothing' do
      expect(call('(String) -> Void', 'newValue')).to eq('data.h?(newValue)')
      expect(call('(Any) -> Void', 'value.translation')).to eq('data.h?(value.translation)')
      expect(call('(String, Int) -> Void', 'newValue')).to eq('data.h?("target", newValue)')
      expect(call('() -> Void', 'newValue')).to eq('data.h?()')
      expect(call('(String) -> Void', nil)).to eq('data.h?("target")')
    end

    it 'each call type-checks against its declared closure', :swift_compile do
      cases = [['(String) -> Void', 'String', '"x"'], ['(Any) -> Void', 'CGSize', 'CGSize.zero'],
               ['(String, Int) -> Void', 'Int', '1'], ['() -> Void', 'Int', '1']]
      data = cases.each_with_index.map { |(klass, _, _), i| "var h#{i}: (#{klass})? = nil" }
      body = cases.each_with_index.map do |(klass, vtype, literal), i|
        call_text = call(klass, 'newValue').sub('data.h?', "data.h#{i}?")
        "let _: () -> Void = { let newValue: #{vtype} = #{literal}; _ = newValue; #{call_text} }"
      end
      fragment = "VStack {}.onAppear {\n#{body.join("\n")}\n}"
      expect(compilable_view(fragment, data: data)).to compile_as_swift
    end
  end
end
