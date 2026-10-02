# frozen_string_literal: true

require 'compose/compose_builder'
require 'json'
require 'set'
require_relative '../support/kotlin_compiler'

# An event attribute the SSoT declares with a "string" type takes the bare
# name as a declared form: a Collection's onValueChange (onPageChanged /
# onValueChanged are its aliases) and onItemAppear, TabView onValueChange.
# Until jsonui-cli 1.9.6 the generator read the binding form only and dropped
# a bare name with no report, so "onPageChanged": "onPage" built and never
# called onPage (ticket bare-event-handler-is-dropped-without-a-warning). The
# bare name now generates what the binding generates.
RSpec.describe 'kjui: a bare handler name on an event the SSoT declares with a string type' do
  # The handler declared as a layout's data declares one, so a call is
  # generated with the argument the build gives it.
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'h' => { 'name' => 'h', 'class' => '(Int) -> Unit' } } }
  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def generate(node)
    builder = KjuiTools::Compose::ComposeBuilder.new
    builder.instance_variable_set(:@required_imports, Set.new)
    builder.instance_variable_set(:@responsive_counter, 0)
    [builder.send(:generate_component, JSON.parse(JSON.generate(node)), 1).to_s,
     builder.instance_variable_get(:@required_imports).to_a.sort_by(&:to_s)]
  end

  def self.shapes
    {
      # The pager calls its handler from three places — the page collector,
      # a currentPage landing and a scrollTo landing — each through the one
      # resolution (pageChangeHandler); this shape draws all three.
      'Collection.onPageChanged' => { 'type' => 'Collection', 'id' => 'pager', 'items' => '@{rows}', 'layout' => 'horizontal',
                                      'paging' => true, 'currentPage' => '@{page}', 'scrollTo' => '@{target}',
                                      'sections' => [{ 'cell' => 'ACell' }] },
      'Collection.onItemAppear' => { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] },
      'Collection.onItemAppear (paging)' => { 'type' => 'Collection', 'id' => 'pager2', 'items' => '@{rows}', 'layout' => 'horizontal',
                                               'paging' => true, 'sections' => [{ 'cell' => 'ACell' }] },
      'TabView.onValueChange' => { 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => 'a', 'view' => 'a_view' }] }
    }
  end

  shapes.each do |name, node|
    attr = name.split(' ').first.split('.').last
    it "#{name}: the bare name generates what the binding generates, and calls the handler" do
      bound = generate(node.merge(attr => '@{h}'))
      expect(bound.first).to match(/data\.h\?\.invoke\(|rememberUpdatedState\(data\.h\)/)
      expect(generate(node.merge(attr => 'h'))).to eq(bound)
    end
  end

  it 'control: no handler, or a value that is not a name, calls nothing' do
    self.class.shapes.each do |name, node|
      attr = name.split(' ').first.split('.').last
      [nil, '', 'not a name'].each do |value|
        code, = generate(value.nil? ? node : node.merge(attr => value))
        expect(code).not_to match(/data\.h\?\.invoke\(|data\.h\)/), "#{name} = #{value.inspect}"
      end
    end
  end

  # The call each bare name generates, against a handler declared as the
  # data model declares one ((Int) -> Unit): the call expressions only, not
  # the Compose around them (the bare file equals the binding's, above).
  it 'the calls a bare name generates compile against the declared handler', :kotlin_compile do
    calls = self.class.shapes.flat_map do |name, node|
      attr = name.split(' ').first.split('.').last
      generate(node.merge(attr => 'h')).first.scan(/data\.h\?\.invoke\([^)]*\)/)
    end.uniq
    expect(calls).not_to be_empty
    expect(<<~KOTLIN).to compile_as_kotlin
      class Data(val h: ((Int) -> Unit)? = null)
      fun calls(data: Data, cellIndex: Int, page: Int, index: Int) {
      #{calls.map { |c| "    #{c}" }.join("\n")}
      }
    KOTLIN
  end
end
