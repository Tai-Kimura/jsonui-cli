# frozen_string_literal: true

require 'set'
require 'compose/compose_builder'
require 'compose/components/collection_component'
require_relative '../support/kotlin_compiler'

# kjui-collection-index-handlers-ignore-the-declared-shape: a Collection's
# onItemAppear (the cell index, or the page on the pager) and its page change
# wrote `invoke(index)` by hand at seven sites, so a handler declared
# `() -> Void` did not compile ("Too many arguments for 'fun invoke(): Unit'" —
# 3 cases of the runtime census). The calls are now
# get_event_handler_invocation's, as every other handler's.
RSpec.describe 'kjui Collection: an index handler is called as declared' do
  CIH_COMPONENT = KjuiTools::Compose::Components::CollectionComponent
  CIH_RESOLVER = KjuiTools::Compose::Helpers::ResourceResolver
  CIH_SOURCE = File.expand_path('../../lib/compose/components/collection_component.rb', __dir__)

  def call(klass, index, receiver: nil)
    CIH_RESOLVER.data_definitions = { 'h' => { 'name' => 'h', 'class' => klass } }
    CIH_COMPONENT.index_handler_call('h', { 'type' => 'Collection', 'id' => 'c' }, index, receiver: receiver)
  ensure
    CIH_RESOLVER.data_definitions = {}
  end

  it 'calls () with nothing and one parameter with the index' do
    expect(call('(() -> Void)?', 'cellIndex')).to eq('data.h?.invoke()')
    expect(call('((Any) -> Void)?', 'cellIndex')).to eq('data.h?.invoke(cellIndex)')
    expect(call('((Int) -> Void)?', 'page', receiver: 'pageChangeHandler')).to eq('pageChangeHandler?.invoke(page)')
    expect(call('(() -> Void)?', 'page', receiver: 'pageChangeHandler')).to eq('pageChangeHandler?.invoke()')
  end

  it 'calls an undeclared handler with the index, as before (control)' do
    CIH_RESOLVER.data_definitions = {}
    expect(CIH_COMPONENT.index_handler_call('h', { 'type' => 'Collection' }, 'page', receiver: 'pageChangeHandler')).to eq('pageChangeHandler?.invoke(page)')
    expect(CIH_COMPONENT.index_handler_call('h', { 'type' => 'Collection' }, 'cellIndex')).to eq('data.h?.invoke(cellIndex)')
  end

  it 'leaves no hand-written index call in the component' do
    source = File.read(CIH_SOURCE)
    expect(source.scan(/\?\.invoke\((?:cellIndex|page|pagerState\.currentPage)\)/)).to eq([])
  end

  it 'emits calls that compile against both declarations, when run' do
    skip "compile: #{KotlinCompiler.unavailable_reason}" if KotlinCompiler.unavailable_reason

    source = <<~KT
      class D0(val h: (() -> Unit)? = null)
      class D1(val h: ((Int) -> Unit)? = null)
      fun main() {
          val log = mutableListOf<String>()
          val cellIndex = 2
          run { val data = D0 { log += "none" }; #{call('(() -> Void)?', 'cellIndex')} }
          run { val data = D1 { log += "index $it" }; #{call('((Int) -> Void)?', 'cellIndex')} }
          run { val pageChangeHandler: (() -> Unit)? = { log += "page none" }; val page = 1; #{call('(() -> Void)?', 'page', receiver: 'pageChangeHandler')} }
          println(log)
      }
    KT
    run = KotlinCompiler.run(source)
    expect(run.errors).to eq([])
    expect(run.output.strip).to eq('[none, index 2, page none]')
  end
end
