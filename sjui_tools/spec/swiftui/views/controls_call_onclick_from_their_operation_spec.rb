# frozen_string_literal: true

require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'

# A control's declared onClick is called ONCE, from the control's own
# operation, after its own update (ticket
# control-onclick-is-called-differently-on-every-path; 4f's ruling): a
# Switch / Toggle's flip, a CheckBox's check, a Radio's selection, a Segment's
# segment, the end of a Slider's change, a SelectBox's pick. No plain tap
# around them; canTap gates the call; `enabled: false` stops the operation and
# so the call. A TextField / TextView does not call it — its tap focuses it.
#
# Before, register_click_lines gave every one of them a tap. Around a control
# it never fired where the control has a gesture of its own, and fired beside
# it where it has none: measured on both iOS paths (SwiftJsonUI
# ConformanceHost OnClickProbeUITests), a Switch, a Segment, a Slider and a
# SelectBox called nothing; a labelled Switch called it from a tap on its
# label, which flips nothing; a Radio over items called nothing. That probe
# runs what this file pins, end to end.
RSpec.describe 'sjui: a control calls its declared onClick from its own operation' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  call = 'data.onTap?()'
  gated_call = "if (data.c ?? false) { #{call} }"

  convert = lambda do |comp|
    comp = JSON.parse(JSON.generate(comp))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    SjuiTools::SwiftUI::ConverterFactory.new.create_converter(comp).convert.to_s
  end

  # Each control, as a node, where its call sits (the text around it), and
  # how many places call it: a Radio over two items has two selections.
  flip = ->(binding) { /Toggle\(isOn: SwiftUI\.Binding\(get: \{ #{binding}\.wrappedValue \}, set: \{ #{binding}\.wrappedValue = \$0; CALL \}\)\)/ }
  variants = {
    'Switch' => [{ 'type' => 'Switch', 'isOn' => false }, flip.call('\$\w+IsOn'), 1],
    'Switch, bound' => [{ 'type' => 'Switch', 'isOn' => '@{on}' }, flip.call('\$data\.on'), 1],
    'Switch, labelled' => [{ 'type' => 'Switch', 'isOn' => false, 'text' => 'Wi-Fi' }, flip.call('\$\w+IsOn'), 1],
    'Toggle' => [{ 'type' => 'Toggle', 'checked' => false }, flip.call('\$\w+IsOn'), 1],
    'CheckBox' => [{ 'type' => 'CheckBox', 'label' => 'x' }, /onValueChanged: \{ newValue in CALL \}/, 1],
    'Check' => [{ 'type' => 'Check', 'label' => 'x' }, /onValueChanged: \{ newValue in CALL \}/, 1],
    'Checkbox' => [{ 'type' => 'Checkbox', 'label' => 'x' }, /onValueChanged: \{ newValue in CALL \}/, 1],
    'Radio over items' => [{ 'type' => 'Radio', 'items' => %w[a b] }, /selected\w+ = "b"\n\s*CALL\n/, 2],
    'Radio in a group' => [{ 'type' => 'Radio', 'group' => 'g', 'text' => 'A' }, /selectedG = "n"\n\s*CALL\n/, 1],
    'Segment' => [{ 'type' => 'Segment', 'items' => %w[a b] },
                  /Picker\("", selection: SwiftUI\.Binding\(get: \{ \$selected\w+\.wrappedValue \}, set: \{ \$selected\w+\.wrappedValue = \$0; CALL \}\)\)/, 1],
    'Slider' => [{ 'type' => 'Slider' }, /Slider\(value: \$\w+, in: 0\.\.\.1, onEditingChanged: \{ editing in if !editing \{ CALL \} \}\)/, 1],
    'SelectBox' => [{ 'type' => 'SelectBox', 'items' => %w[a b] }, /onValueChange: \{ _ in CALL \}\n\s*\)/, 1],
    'SelectBox, date' => [{ 'type' => 'SelectBox', 'selectItemType' => 'Date' }, /onValueChange: \{ newValue in\n\s*CALL\n\s*\}/, 1]
  }

  node = ->(base, more = {}) { base.merge('id' => 'n').merge(more) }
  emit = ->(base, more = {}) { convert.call(node.call(base, { 'onClick' => '@{onTap}' }.merge(more))) }

  variants.each do |name, (base, where, places)|
    describe name do
      it 'calls it from the operation, once per place' do
        code = emit.call(base)
        expect(code).to match(Regexp.new(where.source.gsub('CALL', Regexp.escape(call)))), code
        expect(code.scan(call).size).to eq(places), code
      end

      it 'has no plain tap around it' do
        code = emit.call(base)
        expect(code).not_to match(/\.onTapGesture \{\s*#{Regexp.escape(call)}\s*\}/), code
        expect(code).not_to include('.gesture(TapGesture()'), code
        expect(code).not_to include('.accessibilityAddTraits(.isButton)'), code
      end

      it 'canTap: false emits what no onClick emits' do
        expect(emit.call(base, 'canTap' => false)).to eq(convert.call(node.call(base)))
      end

      it 'a bound canTap gates every call and changes nothing else' do
        expect(emit.call(base, 'canTap' => '@{c}')).to eq(emit.call(base).gsub(call, gated_call))
      end

      it 'enabled: false stops the operation' do
        code = emit.call(base, 'enabled' => false)
        expect(code.include?('.disabled(true)') || code.include?('isEnabled: false')).to be(true), code
      end

      it 'calls every name of an onclick array, in order' do
        code = convert.call(node.call(base, 'onclick' => %w[first second]))
        expect(code.scan('data.first?(); data.second?()').size).to eq(places), code
      end
    end
  end

  it 'a SelectBox that is not enabled is disabled — it opened and took a pick' do
    code = convert.call(node.call({ 'type' => 'SelectBox', 'items' => %w[a b] }, 'enabled' => false))
    expect(code).to include('.disabled(true)')
    bound = convert.call(node.call({ 'type' => 'SelectBox', 'items' => %w[a b] }, 'enabled' => '@{on}'))
    expect(bound).to include('.disabled(!((data.on ?? false)))')
  end

  describe 'after the update and onValueChange' do
    it 'CheckBox: onValueChange, then onClick' do
      code = emit.call({ 'type' => 'CheckBox', 'label' => 'x', 'onValueChange' => '@{changed}' })
      expect(code).to match(/onValueChanged: \{ newValue in data\.changed\?\([^)]*\); #{Regexp.escape(call)} \}/), code
    end

    it 'CheckBox: onClick is not onValueChange — a CheckBox with both calls both' do
      code = emit.call({ 'type' => 'CheckBox', 'label' => 'x', 'onValueChange' => '@{changed}' })
      expect(code.scan('data.changed?(').size).to eq(1)
      expect(code.scan(call).size).to eq(1)
    end

    it 'Radio over items: the selection, onValueChange, then onClick' do
      code = emit.call({ 'type' => 'Radio', 'items' => %w[a b], 'onValueChange' => '@{changed}' })
      expect(code).to match(/selected\w+ = "a"\n\s*data\.changed\?\([^\n]*\n\s*#{Regexp.escape(call)}\n/), code
    end

    it 'SelectBox date: the write back, onValueChange, then onClick' do
      code = emit.call({ 'type' => 'SelectBox', 'selectItemType' => 'Date', 'selectedDate' => '@{day}',
                         'onValueChange' => '@{changed}' })
      expect(code).to match(/data\.day = newValue\n\s*data\.changed\?\([^\n]*\n\s*#{Regexp.escape(call)}\n/), code
    end
  end

  # A text field's tap focuses it; its onClick is not called (the shared
  # validator names it at build time), and nothing is attached for it.
  %w[TextField EditText Input TextView].each do |type|
    it "#{type}: emits what no onClick emits" do
      base = { 'type' => type, 'text' => '@{t}' }
      expect(emit.call(base)).to eq(convert.call(node.call(base)))
    end
  end

  # The Swift the flip, the segment and the slider now carry, type-checked
  # over a view model the way a generated view holds one (`@Binding var
  # data`), with every gate bound. CheckBoxView and SelectBoxView are
  # SwiftJsonUI's and not on this machine's search path; their closures are
  # the ones they always took (and the ConformanceHost probe compiles all of
  # it against the library).
  it 'compiles, bound and gated' do
    fragments = [
      emit.call({ 'type' => 'Switch', 'isOn' => '@{on}' }, 'canTap' => '@{c}'),
      emit.call({ 'type' => 'Segment', 'items' => %w[a b], 'selectedIndex' => '@{index}' }, 'canTap' => '@{c}'),
      emit.call({ 'type' => 'Slider', 'value' => '@{level}' }, 'canTap' => '@{c}')
    ]
    body = fragments.join("\n").lines.map { |l| "            #{l}" }.join
    swift = <<~SWIFT
      #{EmittedSwift::LIBRARY_STUBS}
      struct TestData {
          var on: Bool = false
          var index: Int = 0
          var level: Double = 0
          var c: Bool? = nil
          var onTap: (() -> Void)? = nil
      }
      struct EmittedHost: View {
          @Binding var data: TestData
          var body: some View {
              VStack {
      #{body}
              }
          }
      }
    SWIFT
    expect(swift).to compile_as_swift.with_imports('SwiftUI')
  end
end
