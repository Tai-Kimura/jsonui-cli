# frozen_string_literal: true

require 'compose/compose_builder'
require 'core/tap_accessibility'
require 'core/type_converter'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'
require_relative '../support/compose_stub_universe'

# Compose hands a Slider's onValueChange and a pinch's scale a Float; SwiftUI
# hands the same handler a Double (the Slider) or a CGFloat (the pinch), and
# one declaration serves both faces. A handler declared `((Double) -> Void)?`
# was given the Float as it stood and the screen did not compile ("actual type
# is 'Float', but 'Double' was expected"; ticket
# kjui-slider-on-value-change-passes-float-to-double-handler). The family, as
# measured before the fix: every Slider shape (bound, nullable bound, static,
# none; onValueChange and its alias) and onPinch, against `(Double)`,
# `(Double?)` and `(String, Double)`. `(Float)`, `(CGFloat)` (written Float),
# `(Any)`, `(String, Float)` and `()` compiled and still take what they took.
RSpec.describe 'kjui a Float event value reaches a Double handler' do
  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = declared.to_h { |n, t| [n, { 'name' => n, 'class' => t }] }
  end

  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  let(:declared) do
    { 'hD' => '((Double) -> Void)?', 'hDN' => '((Double?) -> Void)?', 'hSD' => '((String, Double) -> Void)?',
      'hF' => '((Float) -> Void)?', 'hG' => '((CGFloat) -> Void)?', 'hA' => '((Any) -> Void)?',
      'hSF' => '((String, Float) -> Void)?', 'hN' => '(() -> Void)?' }
  end

  shapes = {
    'Slider bound value' => ->(h) { { 'type' => 'Slider', 'id' => 's', 'value' => '@{v}', 'onValueChange' => "@{#{h}}" } },
    'Slider nullable bound value' => ->(h) { { 'type' => 'Slider', 'id' => 's', 'value' => '@{vn}', 'onValueChange' => "@{#{h}}" } },
    'Slider static value' => ->(h) { { 'type' => 'Slider', 'id' => 's', 'value' => 0.5, 'onValueChange' => "@{#{h}}" } },
    'Slider no value' => ->(h) { { 'type' => 'Slider', 'id' => 's', 'onValueChange' => "@{#{h}}" } },
    'Slider onValueChanged' => ->(h) { { 'type' => 'Slider', 'id' => 's', 'value' => '@{v}', 'onValueChanged' => "@{#{h}}" } },
    'View onPinch' => ->(h) { { 'type' => 'View', 'id' => 'p', 'width' => 10, 'height' => 10, 'onPinch' => "@{#{h}}" } }
  }

  emit = lambda do |node|
    comp = JSON.parse(JSON.generate(node))
    JsonUIShared::TapAccessibility.annotate!(comp)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@responsive_counter, 0)
    builder.instance_variable_set(:@responsive_functions, [])
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.send(:generate_component, comp, 0).to_s
  end

  def call_of(code) = code[/data\.h\w+\?\.invoke\([^\n]*?\)(?=\s*(?:\}|$))/]

  it 'a Double parameter is given the value as a Double, every other one as before' do
    expected = { 'hD' => '(VAL.toDouble())', 'hDN' => '(VAL.toDouble())', 'hSD' => '("ID", VAL.toDouble())',
                 'hF' => '(VAL)', 'hG' => '(VAL)', 'hA' => '(VAL)', 'hSF' => '("ID", VAL)', 'hN' => '()' }
    shapes.each do |label, node|
      expected.each do |h, args|
        code = emit.call(node.call(h))
        val = label == 'View onPinch' ? 'scale' : (code.include?('newValue ->') ? 'newValue' : 'it')
        id = label == 'View onPinch' ? 'p' : 's'
        expect(call_of(code)).to eq("data.#{h}?.invoke#{args.sub('VAL', val).sub('ID', id)}"), "#{label} / #{declared[h]}\n#{code}"
      end
    end
  end

  it 'every shape against every declaration type-checks with kotlinc' do
    skip("kotlinc: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason && ENV['KJUI_REQUIRE_KOTLINC'] != '1'
    functions = shapes.flat_map do |label, node|
      declared.keys.map { |h| "// #{label} / #{declared[h]}\nfun c_#{label.gsub(/\W/, '')}_#{h}(data: Data, viewModel: ViewModel) {\n#{emit.call(node.call(h))}\n}" }
    end.join("\n\n")
    props = declared.map { |n, t| "var #{n}: #{KjuiTools::Core::TypeConverter.to_kotlin_type(t, 'compose')} = null" }
    expect(<<~KOTLIN).to compile_as_kotlin
      #{ComposeStubUniverse.common_stages(functions)}
      class Data(val v: Double = 0.0, val vn: Double? = null, #{props.join(', ')})
      class DataFlow { val value = Data(); suspend fun first(predicate: (Data) -> Boolean): Data = value }
      class ViewModel { val data = DataFlow(); fun updateData(values: Map<String, Any?>) {} }
      #{functions}
    KOTLIN
  end

  it 'the control: the Float as it was given does not compile against a Double handler' do
    skip("kotlinc: #{KotlinCompiler.unavailable_reason}") if KotlinCompiler.unavailable_reason && ENV['KJUI_REQUIRE_KOTLINC'] != '1'
    result = KotlinCompiler.compile(<<~KOTLIN)
      class Data(var hD: ((Double) -> Unit)? = null)
      fun probe(data: Data) { val f: (Float) -> Unit = { newValue -> data.hD?.invoke(newValue) }; f(0f) }
    KOTLIN
    expect(result.errors.join).to include("'kotlin.Double' was expected")
  end
end
