# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/data_model_generator'
require 'core/layout_path'

# A SelectBox calls its declared onValueChange as the class the layout's data
# declares it with says (attribute_definitions SelectBox.onValueChange, "the
# same on every platform"): `(() -> Void)?` with nothing; `(String, X)` with
# the viewId (JsonUIShared::LayoutPath.view_id — the id, else
# `selectBox_<path>`) and the new value, the index where selectedIndex is
# bound and the item otherwise. Until 1.9.0 web called every one with the
# value alone: a declared `(String, String)` took the value where the viewId
# goes, a declared `()` one it has no place for — TS2554 under strict, both.
#
# Undeclared (the build's binding warning asks for the declaration), and a
# lone `(String)`, are called with the value as before: the definition says a
# lone (String) is the selected item, with selectedIndex bound too.
#
# A lone `(Int)` is the index — the definition's "with selectedIndex bound it
# is the Int index (declare ((Int) -> Void)?)". Through 1.9.33 web called it
# with the item string (`e.target.value`): TS2345 under strict, and at run
# time the handler got the label, not the index. With a placeholder row the
# index is one less than the DOM's, -1 for the placeholder itself — the same
# index the undeclared write-back reports.
#
# The shape decides the argument, not the binding, as on sjui
# (pick_invocation) and kjui (value_change_call): an Int parameter takes the
# picked row's place in the items with selectedItem bound too, and
# `(String, String)` takes the item with selectedIndex bound too. Through
# 1.9.33 those two took the string for the Int and the index for the String.
RSpec.describe 'a SelectBox calls its onValueChange as its data declares it' do
  classes = {
    'undeclared' => nil,
    'none' => '(() -> Void)?',
    'viewIdIndex' => '((String, Int) -> Void)?',
    'viewIdItem' => '((String, String) -> Void)?',
    'lone' => '((String) -> Void)?',
    'loneIndex' => '((Int) -> Void)?',
    'loneIndexHint' => '((Int) -> Void)?',
    'loneIndexByItem' => '((Int) -> Void)?',
    'viewIdIndexByItem' => '((String, Int) -> Void)?',
    'viewIdItemByIndex' => '((String, String) -> Void)?',
    'viewIdDate' => '((String, String) -> Void)?'
  }

  layout = lambda do
    data = classes.reject { |_, c| c.nil? }.map { |name, c| { 'name' => name, 'class' => c } } +
           [{ 'name' => 'idx', 'class' => 'Int' }, { 'name' => 'opts', 'class' => '[String]' },
            { 'name' => 'item', 'class' => 'String' }, { 'name' => 'day', 'class' => 'String' }]
    by_item = %w[viewIdItem loneIndexByItem viewIdIndexByItem]
    boxes = %w[undeclared none viewIdIndex viewIdItem lone loneIndex loneIndexHint
               loneIndexByItem viewIdIndexByItem viewIdItemByIndex].map do |handler|
      selection = by_item.include?(handler) ? { 'selectedItem' => '@{item}' } : { 'selectedIndex' => '@{idx}' }
      selection['hint'] = 'Pick one' if handler == 'loneIndexHint'
      { 'type' => 'SelectBox', 'items' => '@{opts}', 'onValueChange' => "@{#{handler}}" }.merge(selection)
    end
    boxes << { 'type' => 'SelectBox', 'id' => 'when', 'selectItemType' => 'Date', 'selectedDate' => '@{day}',
               'onValueChange' => '@{viewIdDate}' }
    { 'type' => 'View', 'id' => 'root', 'data' => data, 'child' => boxes }
  end

  let(:screen) do
    RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true }).generate('Home', layout.call, screen_id: 'home')
  end

  def call_of(screen, handler)
    screen[/onChange=\{\(e\) => (data\.#{handler}\?\.\([^\n]*?\))\}/, 1]
  end

  it 'calls each declared shape with its arguments' do
    expect(call_of(screen, 'undeclared')).to eq('data.undeclared?.(e.target.value)')
    expect(call_of(screen, 'none')).to eq('data.none?.()')
    expect(call_of(screen, 'viewIdIndex')).to eq('data.viewIdIndex?.("selectBox_0_2", e.target.selectedIndex)')
    expect(call_of(screen, 'viewIdItem')).to eq('data.viewIdItem?.("selectBox_0_3", e.target.value)')
    expect(call_of(screen, 'lone')).to eq('data.lone?.(e.target.value)')
    expect(call_of(screen, 'loneIndex')).to eq('data.loneIndex?.(e.target.selectedIndex)')
    expect(call_of(screen, 'loneIndexHint')).to eq('data.loneIndexHint?.(e.target.selectedIndex - 1)')
    expect(call_of(screen, 'loneIndexByItem')).to eq('data.loneIndexByItem?.(e.target.selectedIndex)')
    expect(call_of(screen, 'viewIdIndexByItem')).to eq('data.viewIdIndexByItem?.("selectBox_0_8", e.target.selectedIndex)')
    expect(call_of(screen, 'viewIdItemByIndex')).to eq('data.viewIdItemByIndex?.("selectBox_0_9", e.target.value)')
    expect(call_of(screen, 'viewIdDate')).to eq('data.viewIdDate?.("when", e.target.value)')
  end

  # The viewId is the shared rule's, on the tree the screen was generated
  # from: an id-less node's position, an id where there is one.
  it 'hands the viewId LayoutPath gives the node' do
    tree = JsonUIShared::LayoutPath.stamp!(layout.call)
    expect(JsonUIShared::LayoutPath.view_id(tree['child'][2])).to eq('selectBox_0_2')
    expect(JsonUIShared::LayoutPath.view_id(tree['child'][10])).to eq('when')
  end

  # The screen and the data model the build writes for it — each from its
  # own generator, imports cut — under tsc --strict: every declared call
  # against the type the data model declares for its handler
  # (`((String, Int) -> Void)?` is `(arg0: string, arg1: number) => void`,
  # TypeConverter's mapping). The value-alone call web wrote for a declared
  # `()` or `(String, String)` is TS2554 here. The undeclared handler is left
  # out: nothing declares it until the layout does.
  it 'writes calls that compile against the data model the build declares', :typescript_compile do
    model_writer = RjuiTools::React::DataModelGenerator.allocate
    model_writer.instance_variable_set(:@use_typescript, true)
    tree = layout.call
    tree['child'].shift
    screen = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                             .generate('Home', JSON.parse(JSON.generate(tree)), screen_id: 'home')
    properties = model_writer.send(:extract_data_properties, tree)
    model = model_writer.send(:generate_typescript_content, 'Home', properties, [], [],
                              model_writer.send(:extract_event_handler_bindings, tree),
                              model_writer.send(:extract_value_bindings, tree))
    expect(model).to include('viewIdIndex?: ((arg0: string, arg1: number) => void) | undefined;')
    expect(model).to include('loneIndex?: ((arg0: number) => void) | undefined;')
    source = [model, screen].map { |file| file.lines.reject { |l| l.start_with?('import ') }.join }.join("\n")
    expect(source).to compile_as_typescript.with_ambient(<<~TS)
      declare function useStringManager(): Record<string, string>;
      declare function screenMarker(screenId: string): Record<string, string>;
      declare namespace JSX {
        interface IntrinsicElements {
          select: { [attr: string]: unknown; onChange?: (e: { target: HTMLSelectElement }) => void };
          input: { [attr: string]: unknown; onChange?: (e: { target: HTMLInputElement }) => void;
                   onClick?: (e: { currentTarget: HTMLInputElement }) => void };
        }
      }
    TS
  end
end
