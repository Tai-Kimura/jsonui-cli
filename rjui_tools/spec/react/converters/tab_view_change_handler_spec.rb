# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/data_model_generator'

# A TabView's bound onValueChange is called — on a change of the selection
# (JsonUIValueChange, ruling 2026-10-02; until jsonui-cli 1.9.6 from each
# tab's onClick) — as the layout's data declares it: `()` with nothing, `(String, X)` with the viewId first,
# anything else — and a handler the data does not declare, which the Data
# model types as taking the index — with the index. It was called with the
# index whatever it took: TS2554 against a declared `() => void`, and a
# declared `(String, Int)` took the index where the viewId goes. sjui and kjui
# call it as declared too (get_event_handler_invocation).
RSpec.describe 'rjui calls a TabView onValueChange as its data declares it' do
  classes = { 'onNone' => '(() -> Void)?', 'onIndex' => '((Int) -> Void)?', 'onIdIndex' => '((String, Int) -> Void)?' }

  layout = lambda do |handler, declared: true|
    data = [{ 'name' => 'sel', 'class' => 'Int' }]
    data << { 'name' => handler, 'class' => classes.fetch(handler) } if declared
    { 'type' => 'View', 'data' => data, 'child' => [
      { 'type' => 'TabView', 'id' => 'tv', 'selectedIndex' => '@{sel}', 'onValueChange' => "@{#{handler}}",
        'tabs' => [{ 'title' => 'A' }, { 'title' => 'B' }] }
    ] }
  end
  generate = ->(tree) { RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true }).generate('Home', tree, screen_id: 'home') }

  it 'calls each declared shape with its arguments, and an undeclared one with the index' do
    change = ->(call) { "<JsonUIValueChange value={(data.sel ?? 0)} onChange={(value) => #{call}} />" }
    expect(generate.call(layout.call('onNone'))).to include(change.call('data.onNone?.()'))
    expect(generate.call(layout.call('onIndex'))).to include(change.call('data.onIndex?.(value)'))
    expect(generate.call(layout.call('onIdIndex'))).to include(change.call('data.onIdIndex?.("tv", value)'))
    expect(generate.call(layout.call('onIndex', declared: false))).to include(change.call('data.onIndex?.(value)'))
    # A tap writes the bound selection; it calls no handler.
    expect(generate.call(layout.call('onIndex'))).to include('onClick={() => data.setSel?.(1)}')
  end

  it 'writes calls that compile against the data model the build declares', :typescript_compile do
    sources = classes.keys.map do |handler|
      tree = layout.call(handler)
      model_writer = RjuiTools::React::DataModelGenerator.allocate
      model_writer.instance_variable_set(:@use_typescript, true)
      properties = model_writer.send(:extract_data_properties, tree, [], true,
                                     model_writer.send(:extract_event_bindings_for_type, tree))
      model = model_writer.send(:generate_typescript_content, 'Home', properties, [], [],
                                model_writer.send(:extract_event_handler_bindings, tree),
                                model_writer.send(:extract_value_bindings, tree))
      [model, generate.call(tree)].map { |file| file.lines.reject { |l| l.start_with?('import ', 'export default') }.join }
                                  .join("\n").gsub(/\bHome(Data|Props)?\b/) { "#{handler}Home#{Regexp.last_match(1)}" }
                                  .gsub('createHomeData', "create#{handler}HomeData")
    end
    # The file's own helpers live once per file; the three are joined into
    # one source here, so JsonUIValueChange is declared once and its hooks are
    # declared as React's.
    joined = sources.each_with_index.map { |src, i| i.zero? ? src : src.sub(/^const JsonUIValueChange = .*?^};\n/m, '') }
    expect(joined.join("\n")).to compile_as_typescript.with_ambient(<<~TS)
      declare namespace React { type ReactNode = unknown }
      declare function useRef<T>(initial: T): { current: T };
      declare function useEffect(effect: () => void, deps: unknown[]): void;
      declare function screenMarker(screenId: string): Record<string, string>;
      declare const Circle: (props: { className?: string }) => JSX.Element;
      declare namespace JSX {
        interface IntrinsicElements {
          div: { [attr: string]: unknown }; nav: { [attr: string]: unknown }; span: { [attr: string]: unknown };
          button: { [attr: string]: unknown; onClick?: () => void };
        }
      }
    TS
  end
end
