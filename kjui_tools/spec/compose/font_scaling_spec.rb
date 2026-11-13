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
    end
  end

  it 'with no fontSize, a declaration still reaches the size (the library takes the drawn default: noFontSize)' do
    code = emit('type' => 'Label', 'text' => 't', 'fontScaling' => false)
    expect(code).to match(/jsonUIFontSize\(resolved_text\d+\.size \?: TextUnit\.Unspecified, fontScaling = false\)/)
  end

  it "a Label's line heights follow as its size does" do
    code = emit('type' => 'Label', 'text' => 't', 'fontSize' => 15, 'lineHeightMultiple' => 1.4, 'maxFontScale' => 1.2)
    expect(code).to include('lineHeight = jsonUIFontSize(LabelLineHeight.multiple(15f, 1.4f, LocalTextStyle.current, LocalDensity.current), maxFontScale = 1.2f)')
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
    compiled = FONT_SCALING_TYPES.slice(*%w[Label Button IconLabel Switch CheckBox Radio])
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
