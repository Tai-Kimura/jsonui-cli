# frozen_string_literal: true

require_relative '../spec_helper'
require 'json'
require 'stringio'
require_relative '../support/typescript_compiler'
require 'react/converters/converter_table'

# A size class writes each of its classes once (ticket rjui-size-class-width-
# class-emitted-twice). Four places add a size class's classes: the mappers
# (2.3.29), the converter's own classes for the merged node (2.3.31), the
# width a calc of the margins needs (2.3.32), and the --jui-sc-* class a bound
# value moves to (2.3.30, unprefixed). From 2.3.32 a size class that set the
# width wrote its width class twice — the width mapper's and the calc's
# (`lg:w-fit … lg:w-fit`): in a census of 1050 type x override x size class
# pairs, 238 wrote one twice, every one those two; a reservation site's admin
# and user generated it on 94 and 12 nodes. The calc now adds only what the
# mappers have not written, so those nodes are as 2.3.31 drew them.
RSpec.describe 'a size class writes each of its classes once' do
  def converters = RjuiTools::React::Converters::ConverterTable.table

  def class_tokens(node)
    old = $stdout
    $stdout = StringIO.new
    jsx = converters.fetch(node['type']).new(JSON.parse(JSON.generate(node)), { 'use_tailwind' => true }).convert_node(0)
    jsx[/className=(?:"([^"]*)"|\{`([^`]*)`\})/] && ($1 || $2).split
  ensure
    $stdout = old
  end

  def duplicated(tokens) = tokens.tally.select { |t, n| n > 1 && t.include?(':') }.keys

  it "the ticket's shape: a regular width and weight, the width class once, in 2.3.31's order" do
    tokens = class_tokens({ 'type' => 'View', 'id' => 'v', 'child' => [], 'responsive' => { 'regular' => { 'width' => 'wrapContent', 'weight' => 1 } } })
    expect(duplicated(tokens)).to eq([])
    expect(tokens.select { |t| t.start_with?('lg:') }).to eq(%w[lg:w-fit lg:flex-1 lg:min-w-0 lg:min-h-0])
  end

  it 'every width a size class sets beside a matchParent base with margins, once' do
    base = { 'type' => 'View', 'id' => 'v', 'child' => [], 'width' => 'matchParent', 'leftMargin' => 44 }
    [{ 'width' => 'matchParent' }, { 'width' => 'wrapContent' }, { 'width' => 120, 'leftMargin' => 8 },
     { 'width' => 'matchParent', 'leftMargin' => 0 }].each do |block|
      tokens = class_tokens(base.merge('responsive' => { 'compact' => block }))
      expect(duplicated(tokens)).to eq([]), block.inspect
    end
  end

  it 'control: a margin alone still brings the calc of the new margins (2.3.32)' do
    tokens = class_tokens({ 'type' => 'View', 'id' => 'v', 'child' => [], 'width' => 'matchParent', 'leftMargin' => 44,
                            'responsive' => { 'compact' => { 'leftMargin' => 12 } } })
    expect(tokens).to include('max-md:ml-[0.75rem]', 'max-md:w-[calc(100%_-_0.75rem)]')
    expect(duplicated(tokens)).to eq([])
  end

  it 'the emit compiles as TypeScript', :typescript_compile do
    node = { 'type' => 'View', 'id' => 'v', 'child' => [], 'responsive' => { 'regular' => { 'width' => 'wrapContent', 'weight' => 1 } } }
    old = $stdout
    $stdout = StringIO.new
    element = converters.fetch('View').new(node, { 'use_tailwind' => true, 'typescript' => true }).convert_node(0)
    $stdout = old
    expect(TypeScriptCompiler.component(element)).to compile_as_typescript
  end
end
