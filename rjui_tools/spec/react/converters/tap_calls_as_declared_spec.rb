# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/react_generator'
require 'react/data_model_generator'
require 'react/include_paths'
require 'core/layout_path'

# A tap calls its handler as the layout's data declares the closure (4f's
# ruling on control-onclick-is-called-differently-on-every-path, jsonui-cli
# 1.9.0 — sjui's no_value_call, kjui's call as declared): `(String)` with the
# viewId (JsonUIShared::LayoutPath.view_id: the id, else the drawn type and
# the position), `(Event)` with the element's event (the React event the Data
# model types it as), and `()` — or a handler the data does not declare, or
# any other shape — with nothing. Every path a tap is called from: onClick
# (and under a bound canTap), the onclick selectors, onLongPress, an Image's
# tap, and a control's onClick from its own operation.
#
# web handed every bound tap the event it was given: `onClick={data.onTap}`,
# and `data.onTap?.(e)` under a bound canTap — TS2554 for a declared
# `() => void` — so a declared `(String)` took the event where the viewId
# goes (a type error against the Data model, and the wrong value at run time).
RSpec.describe 'rjui calls a tap as its data declares it' do
  data = [
    { 'name' => 'onNone', 'class' => '(() -> Void)?' },
    { 'name' => 'onPick', 'class' => '((String) -> Void)?' },
    { 'name' => 'onEv', 'class' => '((Event) -> Void)?' },
    { 'name' => 'gate', 'class' => 'Bool' },
    { 'name' => 'on', 'class' => 'Bool' }
  ]
  children = [
    { 'type' => 'Label', 'text' => 'a', 'onClick' => '@{onNone}' },
    { 'type' => 'Label', 'text' => 'b', 'onClick' => '@{onNone}', 'canTap' => '@{gate}' },
    { 'type' => 'Label', 'text' => 'c', 'onClick' => '@{onPick}' },
    { 'type' => 'Label', 'id' => 'pick', 'text' => 'd', 'onClick' => '@{onPick}', 'canTap' => '@{gate}' },
    { 'type' => 'View', 'width' => 10, 'height' => 10, 'onclick' => 'onPick' },
    { 'type' => 'View', 'width' => 10, 'height' => 10, 'onclick' => %w[onNone onPick] },
    { 'type' => 'View', 'width' => 10, 'height' => 10, 'onLongPress' => '@{onPick}' },
    { 'type' => 'Image', 'srcName' => 'logo', 'onClick' => '@{onPick}' },
    { 'type' => 'Switch', 'isOn' => '@{on}', 'onClick' => '@{onPick}' },
    { 'type' => 'Button', 'text' => 'go', 'onClick' => '@{onEv}' }
  ]
  layout = -> { { 'type' => 'View', 'id' => 'root', 'data' => data, 'child' => JSON.parse(JSON.generate(children)) } }

  let(:screen) do
    RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                    .generate('Home', layout.call, screen_id: 'home')
  end

  it 'onClick: `()` with nothing, under a bound canTap too' do
    expect(screen).to include('onClick={() => data.onNone?.()}')
    expect(screen).to include('onClick={() => { if (data.gate) data.onNone?.(); }}')
  end

  it 'onClick: `(String)` with the viewId — the position, or the id' do
    expect(screen).to include('onClick={() => data.onPick?.("label_0_2")}')
    expect(screen).to include('onClick={() => { if (data.gate) data.onPick?.("pick"); }}')
  end

  it 'the onclick selectors, one and several' do
    expect(screen).to include('onClick={() => data.onPick?.("view_0_4")}')
    expect(screen).to include('onClick={() => { data.onNone?.(); data.onPick?.("view_0_5"); }}')
  end

  it 'onLongPress, an Image, a control\'s operation, and `(Event)` with the event' do
    expect(screen).to include('onContextMenu={(e) => { e.preventDefault(); data.onPick?.("view_0_6"); }}')
    expect(screen).to include('onClick={() => data.onPick?.("image_0_7")}')
    expect(screen).to include('data.onPick?.("switch_0_8");')
    expect(screen).to include('onClick={(e) => data.onEv?.(e)}')
  end

  it 'a handler the data does not declare, or declares another shape, with nothing' do
    other = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true }).generate('Other', {
      'type' => 'View', 'data' => [{ 'name' => 'onFlag', 'class' => '((Bool) -> Void)?' }],
      'child' => [{ 'type' => 'Label', 'text' => 'x', 'onClick' => '@{onFlag}' },
                  { 'type' => 'Label', 'text' => 'y', 'onClick' => '@{onMissing}' }]
    }, screen_id: 'other')
    expect(other).to include('onClick={() => data.onFlag?.()}')
    expect(other).to include('onClick={() => data.onMissing?.()}')
  end

  # A class keyed by platform is read for the web (`typescript`), as the Data
  # model reads it; a control's operation has no event to hand on, so a
  # declared `(Event)` is called there with nothing.
  it 'the web class of a class keyed by platform; `(Event)` from a control\'s operation' do
    keyed = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true }).generate('Keyed', {
      'type' => 'View',
      'data' => [{ 'name' => 'onWeb', 'class' => { 'swift' => '(() -> Void)?', 'typescript' => '((String) -> Void)?' } },
                 { 'name' => 'onEv', 'class' => '((Event) -> Void)?' }, { 'name' => 'on', 'class' => 'Bool' }],
      'child' => [{ 'type' => 'Label', 'id' => 'w', 'text' => 'x', 'onClick' => '@{onWeb}' },
                  { 'type' => 'Switch', 'isOn' => '@{on}', 'onClick' => '@{onEv}' }]
    }, screen_id: 'keyed')
    expect(keyed).to include('onClick={() => data.onWeb?.("w")}')
    expect(keyed).to include('data.onEv?.();')
    expect(keyed).not_to include('data.onEv?.(e)')
  end

  # An included layout's id-less tap that hands a viewId takes `jsonuiPath`
  # (IncludePaths), as a SelectBox's does: its position above the layout's
  # root comes in at run time.
  it 'a layout someone includes, holding an id-less tap that hands a viewId, takes jsonuiPath' do
    trees = {
      'home' => { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'x' }, { 'include' => 'row' }] },
      'row' => { 'type' => 'View', 'data' => [{ 'name' => 'onPick', 'class' => '((String) -> Void)?' }],
                 'child' => [{ 'type' => 'Label', 'text' => 'r', 'onClick' => '@{onPick}' }] },
      'plain' => { 'type' => 'View', 'data' => [{ 'name' => 'onNone', 'class' => '(() -> Void)?' }],
                   'child' => [{ 'type' => 'Label', 'text' => 'p', 'onClick' => '@{onNone}' }] },
      'home2' => { 'type' => 'View', 'child' => [{ 'include' => 'plain' }] }
    }
    expect(RjuiTools::React::IncludePaths.stems_taking_path(trees).to_a).to eq(['row'])
    row = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true, '_path_stems' => ['row'] })
                                          .generate('Row', trees['row'], namespace_stem: 'row')
    expect(row).to include('onClick={() => data.onPick?.(`label_${jsonuiPath}_0`)}')
  end

  # The screen and the data model the build writes for it — imports cut —
  # under tsc --strict: each call against the type the Data model declares
  # (`(() -> Void)?` is `() => void`, `((String) -> Void)?`
  # `(arg0: string) => void`, a Button's `(Event)` the React event).
  it 'writes calls that compile against the data model the build declares', :typescript_compile do
    model_writer = RjuiTools::React::DataModelGenerator.allocate
    model_writer.instance_variable_set(:@use_typescript, true)
    tree = layout.call
    # As the build writes it: an `Event` a Button's onClick is bound to is
    # the React event (type_mapping.json events).
    properties = model_writer.send(:extract_data_properties, tree, [], true,
                                   model_writer.send(:extract_event_bindings_for_type, tree))
    model = model_writer.send(:generate_typescript_content, 'Home', properties, [], [],
                              model_writer.send(:extract_event_handler_bindings, tree),
                              model_writer.send(:extract_value_bindings, tree))
    expect(model).to include('onNone?: (() => void) | undefined;')
    expect(model).to include('onPick?: ((arg0: string) => void) | undefined;')
    expect(model).to include('onEv?: ((arg0: React.MouseEvent<HTMLButtonElement>) => void) | undefined;')
    source = [model, screen].map { |file| file.lines.reject { |l| l.start_with?('import ') }.join }.join("\n")
    expect(source).to compile_as_typescript.with_ambient(<<~TS)
      declare function useStringManager(): Record<string, string>;
      declare function screenMarker(screenId: string): Record<string, string>;
      declare namespace React { interface MouseEvent<T = Element> { currentTarget: T } }
      type Tap<T> = { [attr: string]: unknown; onClick?: (e: React.MouseEvent<T>) => void;
                      onKeyDown?: (e: { key: string; preventDefault(): void; currentTarget: HTMLElement }) => void;
                      onContextMenu?: (e: { preventDefault(): void }) => void };
      declare namespace JSX {
        interface IntrinsicElements {
          span: Tap<HTMLSpanElement>; div: Tap<HTMLDivElement>; img: Tap<HTMLImageElement>;
          button: Tap<HTMLButtonElement>;
          input: { [attr: string]: unknown; onChange?: (e: { target: HTMLInputElement }) => void };
        }
      }
    TS
  end
end
