# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/modifier_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'

# A control's screen-reader name and a node read out when it changes
# (shared/core/control_accessibility.rb), on the modifier chain every
# component takes (ModifierBuilder.build_test_tag): `accessibilityLabel`
# (alias `contentDescription`) is `contentDescription`, evaluated outside the
# semantics block (stringResource is composable, the block is not), and
# `accessibilityLiveRegion` is `liveRegion`. Until jsonui-cli 2.3.38 neither
# was declared on these types, and nothing was emitted for them.
RSpec.describe 'kjui control accessibility' do
  NAMED = '.then(("Name").let { label -> Modifier.semantics { contentDescription = label } })'

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
  end

  def emit(node)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.instance_variable_set(:@required_imports, Set.new)
    tree = JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(node)))
    code = builder.send(:generate_component, tree, 0).to_s
    [code, builder.instance_variable_get(:@required_imports)]
  end

  describe 'accessibilityLabel' do
    {
      'Button' => { 'type' => 'Button', 'text' => 'Open', 'onClick' => '@{open}' },
      'TextField' => { 'type' => 'TextField', 'id' => 'f', 'text' => '@{q}' },
      'Slider' => { 'type' => 'Slider', 'id' => 's', 'value' => '@{v}' },
      'SelectBox' => { 'type' => 'SelectBox', 'id' => 'b', 'items' => %w[a b] },
      'CheckBox' => { 'type' => 'CheckBox', 'id' => 'c', 'checked' => '@{on}' },
      'Check (the alias section)' => { 'type' => 'Check', 'checked' => '@{on}' },
      'Switch' => { 'type' => 'Switch', 'isOn' => '@{on}' },
      'Radio' => { 'type' => 'Radio', 'id' => 'r', 'text' => 'A' },
      'Segment' => { 'type' => 'Segment', 'id' => 'sg', 'items' => %w[a b] },
      'a View that is one button' => { 'type' => 'View', 'onClick' => '@{open}', 'child' => [{ 'type' => 'Label', 'text' => 'Card' }] }
    }.each do |what, node|
      it "names #{what}" do
        code, imports = emit(node.merge('accessibilityLabel' => 'Name'))
        expect(code.scan(NAMED).size).to eq(1)
        expect(imports).to include(:semantics_content_description)
      end
    end

    it 'reads the contentDescription spelling the same' do
      code, = emit({ 'type' => 'Button', 'text' => 'Open', 'contentDescription' => 'Name' })
      expect(code).to include(NAMED)
    end

    it 'takes a binding' do
      code, = emit({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => '@{name}' })
      expect(code).to include('.then(("${data.name ?: ""}").let { label -> Modifier.semantics { contentDescription = label } })')
    end

    it 'names nothing on a View that taps nothing' do
      code, = emit({ 'type' => 'View', 'accessibilityLabel' => 'Name', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(code).not_to include('contentDescription = label')
    end
  end

  describe 'accessibilityLiveRegion' do
    it 'reads a Label out politely' do
      code, imports = emit({ 'type' => 'Label', 'text' => '@{status}', 'accessibilityLiveRegion' => 'polite' })
      expect(code).to include('.semantics { liveRegion = LiveRegionMode.Polite }')
      expect(imports).to include(:semantics_live_region)
    end

    it 'reads a View out at once when assertive' do
      code, = emit({ 'type' => 'View', 'accessibilityLiveRegion' => 'assertive', 'child' => [{ 'type' => 'Label', 'text' => '@{s}' }] })
      expect(code).to include('.semantics { liveRegion = LiveRegionMode.Assertive }')
    end

    it 'reads nothing out when off' do
      code, = emit({ 'type' => 'Label', 'text' => '@{s}', 'accessibilityLiveRegion' => 'off' })
      expect(code).not_to include('liveRegion')
    end
  end

  # The modifiers it adds reach a compiler, on stubs shaped as
  # androidx.compose.ui.semantics declares them.
  it 'adds modifiers that compile' do
    named, = emit({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => '@{name}' })
    live, = emit({ 'type' => 'Label', 'text' => '@{s}', 'accessibilityLiveRegion' => 'assertive' })
    added = (named.lines + live.lines).map(&:strip).select { |l| l.include?('contentDescription = label') || l.include?('liveRegion =') }
                                      .map { |l| l.sub(/\Amodifier = Modifier/, '').sub(/,\z/, '') }
    expect(added.size).to eq(2)
    source = <<~KOTLIN
      interface Modifier {
          fun then(other: Modifier): Modifier = other
          companion object : Modifier
      }
      enum class LiveRegionMode { Polite, Assertive }
      class SemanticsPropertyReceiver {
          var contentDescription: String = ""
          var liveRegion: LiveRegionMode = LiveRegionMode.Polite
      }
      fun Modifier.semantics(properties: SemanticsPropertyReceiver.() -> Unit): Modifier = this
      class Data(val name: String?)
      fun screen(data: Data): Modifier = Modifier
      #{added.map { |l| "    #{l}" }.join("\n")}
    KOTLIN
    expect(source).to compile_as_kotlin
  end
end
