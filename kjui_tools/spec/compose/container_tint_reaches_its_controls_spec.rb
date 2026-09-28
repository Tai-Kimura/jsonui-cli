# frozen_string_literal: true

require 'compose/compose_builder'
require 'compose/helpers/inherited_tint'
require 'core/tap_accessibility'
require 'core/image_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# tintColor is the accent of a node's operable parts (jsonui-cli 1.9.0 ruling),
# and on iOS `.tint` on a container reaches the controls inside it. Here a node
# that holds other nodes provides KotlinJsonUI's own LocalJsonUITint around what
# it composes, and a control reads its own tintColor first and the local second
# (jsonUITintOr) — not LocalContentColor, which is the text colour. Before this
# a View's tintColor emitted nothing (the codegen differential's common.tintColor
# C0 / C1 on a View).
RSpec.describe 'kjui a container\'s tintColor reaches the controls inside it' do
  counters = %w[TextComponent TextFieldComponent TextViewComponent ButtonComponent ConstraintLayoutComponent]
  emit = lambda do |node|
    counters.each { |c| KjuiTools::Compose::Components.const_get(c).reset_counter! }
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::ImageAccessibility.annotate!(comp, source_path: 'probe.json')
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    code = builder.send(:generate_component, comp, 1)
    [code, builder.instance_variable_get(:@required_imports)]
  end

  provider = 'CompositionLocalProvider(LocalJsonUITint provides ('
  inherited = 'jsonUITintOr(MaterialTheme.colorScheme.primary)'
  tinted_view = lambda do |children, more = {}|
    { 'type' => 'View', 'id' => 'group', 'orientation' => 'vertical', 'tintColor' => '#FF0000', 'child' => children }.merge(more)
  end

  controls = {
    'Switch' => { 'type' => 'Switch', 'id' => 'sw', 'isOn' => '@{on}' },
    'CheckBox' => { 'type' => 'CheckBox', 'id' => 'cb', 'checked' => '@{on}' },
    'Slider' => { 'type' => 'Slider', 'id' => 'sl', 'value' => '@{v}' },
    'Progress' => { 'type' => 'Progress', 'id' => 'pr', 'progress' => 0.5 },
    'Radio' => { 'type' => 'Radio', 'id' => 'ra', 'group' => 'g', 'text' => 'A' }
  }

  describe 'the container' do
    it 'provides its tint around what it composes, once' do
      code, imports = emit.call(tinted_view.call([controls['Switch']]))
      expect(code.scan(provider).size).to eq(1), code
      expect(code.lstrip).to start_with("#{provider}Color(android.graphics.Color.parseColor(\"#FF0000\")))) {"), code
      expect(imports).to include(:composition_local_provider, :local_jsonui_tint)
    end

    it 'provides a bound tint as the binding reads' do
      code, = emit.call(tinted_view.call([controls['Switch']], 'tintColor' => '@{accent}'))
      expect(code).to include("#{provider}data.accent"), code
    end

    it 'a Collection, an Embed or a TabView provides it to the layout it draws' do
      holders = [
        { 'type' => 'Collection', 'id' => 'list', 'cellClasses' => ['row_cell'], 'items' => '@{rows}', 'tintColor' => '#FF0000' },
        { 'type' => 'Embed', 'id' => 'e', 'screen' => 'card', 'tintColor' => '#FF0000' },
        { 'type' => 'TabView', 'id' => 't', 'tintColor' => '#FF0000', 'tabs' => [{ 'title' => 'A', 'view' => 'first' }] }
      ]
      holders.each do |node|
        code, = emit.call(node)
        expect(code.scan(provider).size).to eq(1), "#{node['type']}:\n#{code}"
      end
    end

    it 'with no children, or no tintColor, provides nothing' do
      expect(emit.call({ 'type' => 'View', 'id' => 'empty', 'tintColor' => '#FF0000' }).first).not_to include(provider)
      expect(emit.call(tinted_view.call([controls['Switch']]).tap { |n| n.delete('tintColor') }).first).not_to include(provider)
    end

    it 'a control with its own tintColor provides nothing: it holds no other node' do
      code, = emit.call(controls['Switch'].merge('tintColor' => '#00FF00'))
      expect(code).not_to include(provider)
    end

    it 'the helper names a holder by the type it is drawn as' do
      helper = KjuiTools::Compose::Helpers::InheritedTint
      expect(helper.hands_down?({ 'type' => 'HStack', 'tintColor' => '#FF0000', 'child' => [{ 'type' => 'Label' }] })).to be(true)
      expect(helper.hands_down?({ 'type' => 'Collection', 'tintColor' => '#FF0000' })).to be(true)
      expect(helper.hands_down?({ 'type' => 'View', 'tintColor' => '', 'child' => [{ 'type' => 'Label' }] })).to be(false)
      expect(helper.hands_down?({ 'type' => 'Switch', 'tintColor' => '#FF0000' })).to be(false)
    end
  end

  describe 'a control inside it' do
    it 'with no tintColor of its own, reads the handed-down tint' do
      controls.each do |label, node|
        code, imports = emit.call(node)
        expect(code).to include(inherited), "#{label}:\n#{code}"
        expect(imports).to include(:jsonui_tint_or), label
      end
    end

    it 'reads it where each control draws its accent' do
      expect(emit.call(controls['Switch']).first).to include("checkedTrackColor = #{inherited}")
      expect(emit.call(controls['CheckBox']).first).to include("checkedColor = #{inherited}")
      slider = emit.call(controls['Slider']).first
      expect(slider).to include("thumbColor = #{inherited}", "activeTrackColor = #{inherited}")
      expect(emit.call(controls['Progress']).first).to include("color = #{inherited}")
      expect(emit.call(controls['Radio']).first).to include("selectedColor = #{inherited}")
      tabs = emit.call({ 'type' => 'TabView', 'id' => 't', 'tabs' => [{ 'title' => 'A', 'view' => 'first' }] }).first
      expect(tabs).to include("selectedIconColor = #{inherited}", "selectedTextColor = #{inherited}")
    end

    it 'with its own tintColor, draws its own: the handed-down tint does not win' do
      controls.each do |label, node|
        code, = emit.call(node.merge('tintColor' => '#00FF00'))
        expect(code).to include('parseColor("#00FF00")'), "#{label}:\n#{code}"
        # the Slider's inactive track and the Radio's glyph keep their
        # defaults; the accent itself is the control's own
        expect(code).not_to include(inherited), "#{label}:\n#{code}"
      end
    end

    it 'a more specific accent of its own wins too' do
      expect(emit.call(controls['Switch'].merge('onTintColor' => '#0000FF')).first).not_to include(inherited)
      expect(emit.call(controls['Progress'].merge('progressTintColor' => '#0000FF')).first).not_to include(inherited)
      expect(emit.call(controls['Radio'].merge('selectedColor' => '#0000FF')).first).not_to include(inherited)
    end
  end

  # Stubs, types only (ComposeStubUniverse.common_stages): "well-typed Kotlin",
  # not "valid Compose".
  it 'a tinted container holding every control compiles' do
    code, = emit.call(tinted_view.call(controls.values + [tinted_view.call([controls['Switch'].merge('id' => 'inner')], 'id' => 'inner_group', 'tintColor' => '@{accent}')]))
    expect(code.scan(provider).size).to eq(2), code
    emitted = "fun emitted(data: Data, viewModel: ViewModel) {\n#{code}\n}"
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(emitted)}
      class Data(val on: Boolean = false, val v: Double = 0.0, val selectedG: String = "", val accent: Color = Color())
      class ViewModel { fun updateData(values: Map<String, Any?>) {} }
      #{emitted}
    KOTLIN
  end
end
