# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

# An event attribute the SSoT declares with a "string" type takes the bare
# name as a declared form: a Collection's onValueChange (onPageChanged /
# onValueChanged are its aliases) and onItemAppear, TabView onValueChange.
# Until jsonui-cli 1.9.6 the generator read the binding form only and dropped
# a bare name with no report, so "onPageChanged": "onPage" built and never
# called onPage (ticket bare-event-handler-is-dropped-without-a-warning). The
# bare name now generates what the binding generates, file for file.
RSpec.describe 'rjui: a bare handler name on an event the SSoT declares with a string type' do
  def generate(node)
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [
      { 'data' => [{ 'name' => 'h', 'class' => '(Int) -> Void' }, { 'name' => 'rows', 'class' => 'CollectionDataSource' }] }, node
    ] }
    RjuiTools::React::ReactGenerator.new({ 'typescript' => true }).generate('Home', layout, screen_id: 'home').to_s
  end

  def self.shapes
    {
      'Collection.onPageChanged' => { 'type' => 'Collection', 'id' => 'pager', 'items' => '@{rows}', 'layout' => 'horizontal',
                                      'paging' => true, 'sections' => [{ 'cell' => 'ACell' }] },
      'Collection.onItemAppear' => { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] },
      'TabView.onValueChange' => { 'type' => 'TabView', 'id' => 'tabs', 'tabs' => [{ 'title' => 'a', 'view' => 'a_view' }] }
    }
  end

  shapes.each do |name, node|
    attr = name.split('.').last
    it "#{name}: the bare name generates what the binding generates, and calls the handler" do
      bound = generate(node.merge(attr => '@{h}'))
      expect(bound).to match(/data\.h\?\.\(/)
      expect(generate(node.merge(attr => 'h'))).to eq(bound)
    end
  end

  it 'control: no handler, or a value that is not a name, calls nothing' do
    self.class.shapes.each do |name, node|
      attr = name.split('.').last
      [nil, '', 'not a name'].each do |value|
        code = generate(value.nil? ? node : node.merge(attr => value))
        expect(code).not_to match(/data\.h\?\.\(/), "#{name} = #{value.inspect}"
      end
    end
  end

  # The pager's file — the ticket's case — with a bare onPageChanged, imports
  # cut, under --strict: the imports are declared as the build writes them.
  it 'writes a pager file with a bare onPageChanged that compiles', :typescript_compile do
    node = self.class.shapes['Collection.onPageChanged'].merge('onPageChanged' => 'h')
    body = generate(node).lines.reject { |l| l.start_with?('import ') }.join
    expect(body).to include('data.h?.(page)')
    expect(body).to compile_as_typescript.with_ambient(<<~TS)
      interface HomeData { h?: (page: number) => void; rows?: { sections?: { cells?: { data?: Record<string, unknown>[] } }[] } }
      declare function createHomeData(): HomeData;
      declare function screenMarker(screenId: string): Record<string, string>;
      declare function currentCollectionPage(container: HTMLElement | null, horizontal: boolean): number;
      type ACellData = Record<string, unknown>;
      declare function ACell(props: { key?: number; id: string; data: ACellData }): JSX.Element;
      declare function useRef<T>(initial: T): { current: T };
    TS
  end
end
