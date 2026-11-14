# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# Every text kjui emits goes through the app's fontProvider, a font attribute or not (the requester's P1, 2026-11-13;
# ticket jui-font-provider-not-reached-without-font-attributes-android-web): each of the ten components resolves its
# FontSpec through Configuration.Font.resolve and draws the family, weight, size and style it gives back. Before,
# only Label always did; Button, TextField and TextView did when a font attribute was written, and SelectBox,
# DateSelectBox, Switch, CheckBox, Radio, IconLabel and Segment never did, so a provider answering a size or a family
# changed nothing on them. A slot the provider leaves null falls to what the component drew before — the
# KotlinJsonUI device test ProviderReachesEveryTextDeviceTest draws both.
RSpec.describe 'kjui codegen: the font provider reaches every text' do
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

  # The ten components, each with no font attribute.
  PLAIN_TEXTS = {
    'Label' => { 'text' => 't' }, 'Button' => { 'text' => 't' }, 'TextField' => { 'text' => '@{t}' },
    'TextView' => { 'text' => '@{t}' }, 'SelectBox' => { 'items' => %w[a b] },
    'DateSelectBox' => { 'type' => 'SelectBox', 'selectItemType' => 'Date' }, 'Switch' => { 'label' => 'l' },
    'CheckBox' => { 'label' => 'l' }, 'Radio' => { 'text' => 'r' }, 'IconLabel' => { 'text' => 't' },
    'Segment' => { 'items' => %w[a b] }
  }.freeze

  def node(name, extra) = { 'type' => name }.merge(extra)

  it 'each of the ten resolves its FontSpec and draws the result, with no font attribute written' do
    PLAIN_TEXTS.each do |name, extra|
      code = emit(node(name, extra))
      var = code[/val (\w+) = Configuration\.Font\.resolve\(FontSpec\(/, 1]
      expect(var).not_to be_nil, "#{name} resolves no FontSpec:\n#{code}"
      # The family and the size the provider gives are what the text draws (a SelectBox hands them to the library).
      drawn = if name.end_with?('SelectBox')
                code.include?("resolvedFont = #{var},")
              else
                code.include?("fontFamily = #{var}.family") || code.include?("fontFamily = (#{var}.family")
              end
      expect(drawn).to be(true), "#{name} does not draw the resolved family:\n#{code}"
      expect(code).to match(/#{var}\.size \?:/), name unless name.end_with?('SelectBox')
    end
  end

  it 'a declared weight and size are the FontSpec the provider is asked with' do
    expect(emit(node('Switch', 'label' => 'l', 'fontSize' => 18, 'font' => 'bold'))).to include("weight = FontWeight.Bold,\n", 'size = 18.sp,')
    expect(emit(node('CheckBox', 'label' => 'l', 'fontSize' => 18))).to include('size = 18.sp,')
    expect(emit(node('Radio', 'text' => 'r', 'fontSize' => 18, 'font' => 'bold'))).to include('weight = FontWeight.Bold,', 'size = 18.sp,')
    expect(emit(node('SelectBox', 'items' => %w[a], 'fontSize' => 15, 'font' => 'medium'))).to include('weight = FontWeight.Medium,', 'size = 15.sp,')
  end

  # An app's provider may pick a font file by the weight (client's and bar's do: no weight is Regular). A component
  # that names no weight hands over the weight it draws, its text style's — a Button's labelLarge is Medium, a
  # Segment's tab Medium — so the file it drew before comes back. The Segment resolves inside each tab's text, where
  # the tab's style is the current one. A component that declares a font attribute keeps the spec it always had.
  it 'a component naming no weight asks with the weight it draws; one with a font attribute keeps its spec' do
    expect(emit(node('Button', 'text' => 't'))).to include('weight = LocalTextStyle.current.fontWeight,')
    expect(emit(node('Button', 'text' => 't', 'fontSize' => 15))).to include('weight = null,')
    expect(emit(node('TextField', 'text' => '@{t}'))).to include('weight = LocalTextStyle.current.fontWeight,')
    expect(emit(node('Switch', 'label' => 'l'))).to include('weight = LocalTextStyle.current.fontWeight,')
    expect(emit(node('SelectBox', 'items' => %w[a]))).to include('weight = FontWeight.Normal,')
    segment = emit(node('Segment', 'items' => %w[a b]))
    expect(segment.scan(/text = \{\n\s+val segmentFont = Configuration\.Font\.resolve\(FontSpec\(\n\s+family = null,\n\s+weight = LocalTextStyle\.current\.fontWeight,/).size).to eq(2)
  end

  # The line box is drawn by the rule from the size drawn — the provider's when it gives one — on the five that name no
  # size and declare nothing (ruling 2026-11-14). They drew no lineHeight: a provider size under
  # Configuration.Font.scaling false left the theme's sp line growing under a text that stood still (KotlinJsonUI
  # ProviderLineFollowsTextDeviceTest draws both). Under the default configuration jsonUILineHeight hands the line back.
  it 'the five that declare nothing draw their line from the size drawn' do
    %w[Button Switch CheckBox Radio IconLabel].each do |name|
      code = emit(node(name, PLAIN_TEXTS[name]))
      var = code[/val (\w+) = Configuration\.Font\.resolve\(FontSpec\(/, 1]
      expect(code).to include("lineHeight = jsonUILineHeight(jsonUIFontSize(#{var}.size ?: TextUnit.Unspecified))"), "#{name}:\n#{code}"
    end
  end

  it 'the emitted code compiles, each of the ten' do
    nodes = PLAIN_TEXTS.map { |name, extra| node(name, extra) }
    functions = nodes.each_with_index.map do |n, i|
      "// #{n['type']}\nfun plain#{i}(data: Data, viewModel: ViewModel) {\n#{emit(n)}\n}"
    end.join("\n\n")
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val t: String = "", val selectedValue: String = "")
      class DataFlow { val value = Data(); suspend fun first(predicate: (Data) -> Boolean): Data = value }
      class ViewModel { val data = DataFlow(); fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end
end
