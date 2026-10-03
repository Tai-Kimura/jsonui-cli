# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/textfield_component'
require 'compose/components/textview_component'
require_relative '../support/kotlin_compiler'

# kjui-bare-ontextchange-ignores-the-declared-shape: onTextChange is declared
# `string`, so a bare name is one of its spellings; it was written
# `data.<name>?.invoke()` whatever the handler declared, and a one-parameter
# handler did not compile (6 of 6 cases on the conformance host). It is now
# called as `@{name}` is — as declared, the text as the value; an undeclared
# or `()` handler is still `invoke()`.
RSpec.describe 'kjui onTextChange: a bare name is called as its declaration takes it' do
  BTC_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver

  def calls(type, klass, node = {})
    defs = { 't' => { 'name' => 't', 'class' => 'String' } }
    defs['h'] = { 'name' => 'h', 'class' => klass } if klass
    BTC_RESOLVER.data_definitions = defs
    KjuiTools::Compose::Components.const_get("#{type}Component")
                                  .generate({ 'type' => type, 'id' => 'f', 'onTextChange' => 'h' }.merge(node), 0, Set.new)
                                  .scan(/data\.h\?\.invoke\([^)]*\)/).uniq
  ensure
    BTC_RESOLVER.data_definitions = {}
  end

  %w[TextField TextView].each do |type|
    it "#{type}: a one-parameter handler gets the text, unbound and bound" do
      # Through 1.9.6: data.h?.invoke() — "No value passed for parameter 'p1'".
      expect(calls(type, '((Any) -> Void)?')).to eq(['data.h?.invoke(newValue)'])
      expect(calls(type, '((Any) -> Void)?', 'text' => '@{t}')).to eq(['data.h?.invoke(newValue)'])
    end

    it "#{type}: () and an undeclared name stay invoke() (control)" do
      expect(calls(type, '(() -> Void)?')).to eq(['data.h?.invoke()'])
      expect(calls(type, nil, 'text' => '@{t}')).to eq(['data.h?.invoke()'])
    end
  end

  it 'compiles and passes the text, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    call = calls('TextField', '((Any) -> Void)?').first
    run = KotlinCompiler.run(<<~KT)
      class Data(val h: ((Any) -> Unit)? = null)
      fun main() {
          val got = mutableListOf<Any>()
          val data = Data { got += it }
          val newValue = "ab"
          #{call}
          println(got)
      }
    KT
    expect(run.errors).to eq([])
    expect(run.output.strip).to eq('[ab]')
  end
end
