# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# Text size following (ticket sjui-label-font-size-ignores-dynamic-type; shared/core/font_scale_vectors.json): every
# text size kjui emits goes through KotlinJsonUI's `jsonUIFontSize(<size>)`, with the component's fontScaling /
# maxFontScale when it declares them — so the rule, and an app's Configuration.Font.scaling / maxScale, reach the
# generated code. SelectBox draws through the library's SelectBox, which takes the two as arguments.
RSpec.describe 'kjui codegen: text size following' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
  end

  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def emit(node)
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.send(:generate_component, comp, 0).to_s
  end

  FONT_SCALING_TYPES = {
    'Label' => { 'text' => 't' }, 'Button' => { 'text' => 't' }, 'TextField' => { 'text' => '@{t}', 'hint' => 'h' },
    'TextView' => { 'text' => '@{t}', 'hint' => 'h' }, 'IconLabel' => { 'text' => 't' }, 'Switch' => { 'label' => 'l' },
    'CheckBox' => { 'label' => 'l' }, 'Radio' => { 'text' => 'r' }
  }.freeze

  it 'declaration_args spells what the component declares, literal only' do
    fs = KjuiTools::Compose::Helpers::FontScale
    expect(fs.declaration_args({})).to eq('')
    expect(fs.declaration_args('fontScaling' => false)).to eq(', fontScaling = false')
    expect(fs.declaration_args('fontScaling' => true, 'maxFontScale' => 1.5)).to eq(', fontScaling = true, maxFontScale = 1.5f')
    expect(fs.declaration_args('maxFontScale' => 2)).to eq(', maxFontScale = 2f')
    # A binding is not a declaration here (attribute_definitions types both as literals).
    expect(fs.declaration_args('fontScaling' => '@{x}', 'maxFontScale' => '@{m}')).to eq('')
  end

  it "every component with a text size draws it through jsonUIFontSize, with the component's declarations" do
    FONT_SCALING_TYPES.each do |type, extra|
      plain = emit({ 'type' => type, 'fontSize' => 15 }.merge(extra))
      expect(plain).to match(/jsonUIFontSize\([^\n]*\)/), type
      expect(plain).not_to include('fontScaling ='), type
      declared = emit({ 'type' => type, 'fontSize' => 15, 'fontScaling' => false, 'maxFontScale' => 1.5 }.merge(extra))
      expect(declared).to match(/jsonUIFontSize\([^\n]*, fontScaling = false, maxFontScale = 1\.5f\)/), type
      expect(declared.scan(/jsonUIFontSize\(/).size).to eq(plain.scan(/jsonUIFontSize\(/).size), type
      # The letter spacing beside the size, by the same declarations (rule.letterSpacing).
      expect(declared).to include('jsonUILetterSpacing(fontScaling = false, maxFontScale = 1.5f)'), type
      expect(plain).to include('jsonUILetterSpacing()'), type
    end
  end

  it 'with no fontSize, a declaration still reaches the size (the library takes the drawn default: noFontSize)' do
    code = emit('type' => 'Label', 'text' => 't', 'fontScaling' => false)
    expect(code).to match(/jsonUIFontSize\(resolved_text\d+\.size \?: TextUnit\.Unspecified, fontScaling = false\)/)
  end

  it 'with no fontSize, every component draws its own size by its declarations; undeclared, nothing changes' do
    # codegen_effect C0/unread-spelling (release-check 43471698693): Button, TextView, IconLabel, Switch, CheckBox and
    # Radio emitted a size only beside a fontSize, so fontScaling / maxFontScale on a component with none (the
    # conformance fixtures' shape) read nothing.
    FONT_SCALING_TYPES.except('Label', 'TextField', 'TextView').each do |type, extra|
      declared = emit({ 'type' => type, 'fontScaling' => false, 'maxFontScale' => 1.5 }.merge(extra))
      expect(declared).to include('fontSize = jsonUIFontSize(TextUnit.Unspecified, fontScaling = false, maxFontScale = 1.5f)'), type
      expect(declared).to include('letterSpacing = jsonUILetterSpacing(fontScaling = false, maxFontScale = 1.5f)'), type
      expect(emit({ 'type' => type, 'maxFontScale' => 2 }.merge(extra))).to include('jsonUIFontSize(TextUnit.Unspecified, maxFontScale = 2f)'), type
      # The library leaves an unspecified size alone when nothing is declared: the plain emit stays as it was.
      expect(emit({ 'type' => type }.merge(extra))).not_to include('jsonUIFontSize('), type
    end
    # A TextView draws Configuration.TextField.defaultFontSize without a size (rule.noFontSize), on a bare TextStyle as
    # the Dynamic TextView does (codegen parity, run 43488822719).
    expect(emit('type' => 'TextView', 'text' => '@{t}', 'fontScaling' => false))
      .to include('textStyle = TextStyle(fontSize = jsonUIFontSize(Configuration.TextField.defaultFontSize.sp, fontScaling = false), letterSpacing = jsonUILetterSpacing(fontScaling = false))')
  end

  it "a Label's line heights follow as its size does: its own, relative to the size drawn" do
    code = emit('type' => 'Label', 'text' => 't', 'fontSize' => 15, 'lineHeightMultiple' => 1.4, 'maxFontScale' => 1.2)
    expect(code).to match(/lineHeight = jsonUILineHeight\(jsonUIFontSize\(resolved_text\d+\.size \?: TextUnit\.Unspecified, maxFontScale = 1\.2f\), maxFontScale = 1\.2f, lineHeight = LabelLineHeight\.multiple\(15f, 1\.4f, LocalTextStyle\.current, LocalDensity\.current\)\)/)
  end

  it "every text with a size drawn by the rule draws its line box by it too (the theme's, or its own)" do
    # Ticket kjui-theme-line-height-scales-under-font-scaling-false: the theme's line height is sp, so a text that does
    # not follow grew its line box with the system. Each such text now takes jsonUILineHeight beside its letter spacing,
    # relative to the size drawn; the library leaves a following text's line unchanged.
    FONT_SCALING_TYPES.except('TextField', 'TextView').each do |type, extra|
      code = emit({ 'type' => type, 'fontScaling' => false }.merge(extra))
      expect(code).to match(/lineHeight = jsonUILineHeight\([^\n]*fontScaling = false/), type
    end
    # A TextField's placeholder with a hint size takes it.
    # A TextView's text is on a bare TextStyle (as the Dynamic face's): no line height of its own to draw.
    expect(emit('type' => 'TextView', 'text' => '@{t}', 'fontScaling' => false))
      .to include('textStyle = TextStyle(fontSize = jsonUIFontSize(Configuration.TextField.defaultFontSize.sp, fontScaling = false), letterSpacing = jsonUILetterSpacing(fontScaling = false))')
    expect(emit('type' => 'TextField', 'text' => '@{t}', 'hint' => 'h', 'hintFontSize' => 12, 'fontScaling' => false))
      .to include('style = LocalTextStyle.current.copy(lineHeight = jsonUILineHeight(jsonUIFontSize(12.sp, fontScaling = false), fontScaling = false))')
    # An undeclared hint size follows the system, and so does its line: nothing is added there.
    expect(emit('type' => 'TextField', 'text' => '@{t}', 'hint' => 'h', 'fontScaling' => false)).not_to include('lineHeight = jsonUILineHeight(')
  end

  it "partialAttributes' sizes follow the Label: PartialAttributesText takes its declarations" do
    code = emit('type' => 'Label', 'text' => 'Hello', 'fontSize' => 15, 'fontScaling' => false, 'maxFontScale' => 2,
                'partialAttributes' => [{ 'range' => [0, 2], 'fontSize' => 20 }])
    expect(code).to match(/PartialAttributesText\(\n\s+text = [^\n]+\n\s+fontScaling = false,\n\s+maxFontScale = 2f,/)
    plain = emit('type' => 'Label', 'text' => 'Hello', 'partialAttributes' => [{ 'range' => [0, 2], 'fontSize' => 20 }])
    expect(plain).not_to include('fontScaling =')
  end

  it 'SelectBox passes its declarations to the library SelectBox' do
    code = emit('type' => 'SelectBox', 'items' => %w[a b], 'fontSize' => 15, 'fontScaling' => false, 'maxFontScale' => 1.3)
    expect(code).to match(/fontSize = 15,\n\s+fontScaling = false,\n\s+maxFontScale = 1\.3f,/)
    expect(emit('type' => 'SelectBox', 'items' => %w[a b])).not_to include('fontScaling =')
  end

  it 'the emitted code compiles, declared and not' do
    # Without a fontSize: the common stub universe's FontSpec takes the size as an Int (the declared-size emits are
    # compiled by their own specs). What this arm holds is jsonUIFontSize's call with the declarations as named
    # arguments, on each type the universe draws in full.
    compiled = FONT_SCALING_TYPES.slice(*%w[Label Button TextView IconLabel Switch CheckBox Radio])
    nodes = compiled.flat_map do |type, extra|
      [{ 'type' => type }.merge(extra), { 'type' => type, 'fontScaling' => false, 'maxFontScale' => 1.5 }.merge(extra)]
    end
    functions = nodes.each_with_index.map do |node, i|
      "// #{node['type']}\nfun scaled#{i}(data: Data, viewModel: ViewModel) {\n#{emit(node)}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val t: String = "")
      class DataFlow { val value = Data(); suspend fun first(predicate: (Data) -> Boolean): Data = value }
      class ViewModel { val data = DataFlow(); fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end
end
