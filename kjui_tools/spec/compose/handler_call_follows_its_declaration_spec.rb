# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/textfield_component'
require 'compose/components/textview_component'
require_relative '../support/kotlin_compiler'

# The call kjui emits for a bound event handler is the declared handler's
# shape — its parameter count — the shapes KotlinJsonUI Dynamic's
# resolveEventHandler accepts: none -> `()`; one -> the event's value when it
# has one, else the view id; two -> (view id, value).
#
# Through jsonui-cli 1.9.5 the shape was guessed from the spelling:
# - kjui-text-change-callback-passes-the-id-to-a-one-parameter-handler:
#   `(String) -> Void` on onTextChange was read as (viewId, value) and got
#   `invoke("f", newValue)` — "Too many arguments";
# - kjui-pan-callback-is-called-without-its-payload: `(Any) -> Void` on onPan
#   was outside the one-argument type list and got `invoke()` — "No value
#   passed for parameter 'p1'".
# Every shape that compiled then is called as it was (the table's `same` rows).
RSpec.describe 'kjui: an event handler is called as it is declared' do
  HANDLER_CALL_MB = KjuiTools::Compose::Helpers::ModifierBuilder
  HANDLER_CALL_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  # [class, value expression, expected call, through 1.9.5]
  rows = [
    ['((String) -> Void)?', 'newValue', 'data.h?.invoke(newValue)', 'data.h?.invoke("f", newValue)'],
    ['(Any) -> Void', 'total', 'data.h?.invoke(total)', 'data.h?.invoke()'],
    ['((String) -> Void)?', nil, 'data.h?.invoke("f")', :same],
    ['(() -> Void)?', 'newValue', 'data.h?.invoke()', :same],
    ['() -> Void', nil, 'data.h?.invoke()', :same],
    ['((String, String) -> Void)?', 'newValue', 'data.h?.invoke("f", newValue)', :same],
    ['((String, Int) -> Void)?', 'index', 'data.h?.invoke("f", index)', :same],
    ['((Bool) -> Void)?', 'newValue', 'data.h?.invoke(newValue)', :same],
    ['((Int) -> Void)?', 'index', 'data.h?.invoke(index)', :same],
    ['((Float) -> Void)?', 'scale', 'data.h?.invoke(scale)', :same],
    ['((Event) -> Void)?', 'newValue', 'data.h?.invoke("f", newValue)', :same],
    ['((Event) -> Void)?', nil, 'data.h?.invoke("f")', :same],
    [nil, 'newValue', 'data.h?.invoke()', :same]
  ]

  def call_for(class_type, value_expr)
    HANDLER_CALL_RESOLVER.data_definitions = class_type ? { 'h' => { 'name' => 'h', 'class' => class_type } } : {}
    HANDLER_CALL_MB.get_event_handler_invocation('@{h}', 'f', value_expr)
  ensure
    HANDLER_CALL_RESOLVER.data_definitions = {}
  end

  rows.each do |class_type, value_expr, expected, _before|
    it "calls #{class_type.inspect} with #{value_expr.inspect} as #{expected}" do
      expect(call_for(class_type, value_expr)).to eq(expected)
    end
  end

  it 'reaches onTextChange on TextField and TextView, and onPan' do
    HANDLER_CALL_RESOLVER.data_definitions = {
      'h' => { 'name' => 'h', 'class' => '((String) -> Void)?' },
      'p' => { 'name' => 'p', 'class' => '(Any) -> Void' },
      't' => { 'name' => 't', 'class' => 'String' }
    }
    field = KjuiTools::Compose::Components::TextFieldComponent.generate(
      { 'type' => 'TextField', 'id' => 'f', 'text' => '@{t}', 'onTextChange' => '@{h}' }, 0, Set.new
    )
    view = KjuiTools::Compose::Components::TextViewComponent.generate(
      { 'type' => 'TextView', 'id' => 'v', 'text' => '@{t}', 'onTextChange' => '@{h}' }, 0, Set.new
    )
    pan = HANDLER_CALL_MB.build_pannable({ 'id' => 'g', 'onPan' => '@{p}' }, Set.new).join
    expect(field).to include('data.h?.invoke(newValue)')
    expect(view).to include('data.h?.invoke(newValue)')
    expect(pan).to include('data.p?.invoke(total)')
  ensure
    HANDLER_CALL_RESOLVER.data_definitions = {}
  end

  # The Kotlin type each declaration maps to and the value the event has.
  KOTLIN_SHAPES = {
    '((String) -> Void)?' => ['((String) -> Unit)?', 'newValue', '"typed"'],
    '(Any) -> Void' => ['((Any) -> Unit)?', 'total', 'Offset(3f, 4f)'],
    '(() -> Void)?' => ['(() -> Unit)?', 'newValue', '"typed"'],
    '((String, String) -> Void)?' => ['((String, String) -> Unit)?', 'newValue', '"typed"'],
    '((String, Int) -> Void)?' => ['((String, Int) -> Unit)?', 'index', '2'],
    '((Bool) -> Void)?' => ['((Boolean) -> Unit)?', 'newValue', 'true'],
    '((Int) -> Void)?' => ['((Int) -> Unit)?', 'index', '2'],
    '((Float) -> Void)?' => ['((Float) -> Unit)?', 'scale', '1.5f']
  }.freeze

  it 'emits calls that compile, and the handler receives the value, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    functions = KOTLIN_SHAPES.each_with_index.map do |(declared, (kotlin_type, name, value)), i|
      call = call_for(declared, name)
      <<~KT
        fun shape#{i}(): String {
            var got = "not called"
            class Data(val h: #{kotlin_type})
            val data = Data { #{lambda_params(kotlin_type)} -> got = listOf<Any?>(#{lambda_params(kotlin_type)}).joinToString(",") }
            val #{name} = #{value}
            #{call}
            return "#{declared}=" + got
        }
      KT
    end
    source = <<~KT
      data class Offset(val x: Float, val y: Float)
      #{functions.join("\n")}
      fun main() {
      #{KOTLIN_SHAPES.size.times.map { |i| "    println(shape#{i}())" }.join("\n")}
      }
    KT
    run = KotlinCompiler.run(source.gsub(/\{  -> /, '{ '))
    expect(run.errors).to eq([])
    expect(run.output.lines.map(&:strip)).to eq([
      '((String) -> Void)?=typed',
      '(Any) -> Void=Offset(x=3.0, y=4.0)',
      '(() -> Void)?=',
      '((String, String) -> Void)?=f,typed',
      '((String, Int) -> Void)?=f,2',
      '((Bool) -> Void)?=true',
      '((Int) -> Void)?=2',
      '((Float) -> Void)?=1.5'
    ])
  end

  def lambda_params(kotlin_type)
    count = kotlin_type[/\(\(([^()]*)\)/, 1].to_s.split(',').reject { |s| s.strip.empty? }.size
    (1..count).map { |n| "a#{n}" }.join(', ')
  end
end
