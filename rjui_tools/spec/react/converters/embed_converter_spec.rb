# frozen_string_literal: true

require_relative '../../spec_helper'
require_relative '../../support/typescript_compiler'
require 'react/converters/embed_converter'
require 'react/react_generator'
require 'react/data_model_generator'
require 'react/viewmodel_generator'
require 'core/frameworks'

RSpec.describe RjuiTools::React::Converters::EmbedConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'minimal Embed (P1)' do
      it 'wraps the embedded component in EmbedContainer with required props' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail'
        )
        result = converter.convert
        expect(result).to include('<EmbedContainer')
        expect(result).to include('embedId="detailPane"')
        expect(result).to include('screen="order_detail"')
        expect(result).to include('navigationMode="delegate"')
        expect(result).to include('<OrderDetail />')
        expect(result).to include('</EmbedContainer>')
      end

      it 'converts snake_case screen to PascalCase component name' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'pane',
          'screen' => 'user_profile_summary'
        )
        result = converter.convert
        expect(result).to include('<UserProfileSummary />')
      end

      it 'passes PascalCase screen through unchanged (backward compat)' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'pane',
          'screen' => 'Counter'
        )
        result = converter.convert
        expect(result).to include('screen="Counter"')
        expect(result).to include('<Counter />')
      end

      it 'emits a JSX comment when screen attribute is missing' do
        converter = create_converter('type' => 'Embed', 'id' => 'oops')
        result = converter.convert
        expect(result).to include('Embed: missing required `screen` attribute')
      end
    end

    context 'params wiring (P2)' do
      it 'renders literal params as JS object entries' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail',
          'params' => { 'orderId' => 'abc-123', 'count' => 5, 'open' => true }
        )
        result = converter.convert
        expect(result).to match(/params=\{\{ .*orderId: 'abc-123'.* \}\}/)
        expect(result).to match(/params=\{\{ .*count: 5.* \}\}/)
        expect(result).to match(/params=\{\{ .*open: true.* \}\}/)
      end

      it 'rewrites @{binding} params to `data.{prop}` references' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail',
          'params' => { 'orderId' => '@{selectedOrderId}' }
        )
        result = converter.convert
        expect(result).to include('orderId: data.selectedOrderId')
      end

      it 'omits the params prop when params dict is empty' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail'
        )
        result = converter.convert
        expect(result).not_to include('params={')
      end
    end

    # An event calls the handler it names on `data`, with the event's
    # payload: a generated component has no ViewModel, and the
    # `viewModel.<name>(…)` it wrote until 1.9.0 named nothing (ticket
    # rjui-embed-event-bridge-calls-an-undeclared-view-model).
    context 'events wiring (P2)' do
      it 'emits an eventBridge that dispatches to the data handlers by event name' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail',
          'events' => { 'onOrderUpdated' => 'handleOrderUpdated', 'onClose' => 'closePane' }
        )
        result = converter.convert
        expect(result).to include('eventBridge=')
        expect(result).to include("event.type === 'onOrderUpdated'")
        expect(result).to include('data.handleOrderUpdated?.(event.payload ?? {})')
        expect(result).to include("event.type === 'onClose'")
        expect(result).to include('data.closePane?.(event.payload ?? {})')
        expect(result).not_to include('viewModel')
      end

      # `@{name}` is the binding spelling, and a handler is named as it is:
      # it is not called, and the bridge says so where the call would be.
      # It was written into code as it stood — `viewModel.@{name}(…)`.
      it 'calls no value that names no handler, and writes nothing of it into code' do
        result = create_converter(
          'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'order_detail',
          'events' => { 'onOrderUpdated' => 'handleOrderUpdated', 'onClose' => '@{closePane}', 'onOpen' => 'a b' }
        ).convert
        expect(result).to include('data.handleOrderUpdated?.(event.payload ?? {})')
        expect(result).to include('/* ERROR: Embed event onClose names no handler, and is not called */')
        expect(result).to include('/* ERROR: Embed event onOpen names no handler, and is not called */')
        expect(result).not_to include('@{')
        expect(result).not_to include('closePane')
      end

      # The screen, its data model and its ViewModel base as the build
      # writes them — each from its own generator, imports cut — compiled
      # together under --strict: the bridge's call, the data model's
      # declaration of the handler and the ViewModel base's stub that
      # supplies it name the same thing with the same type. The template's
      # own props are read from lib/react/templates; the router's type is
      # opaque here (next's AppRouterInstance).
      it 'writes a screen, data model and ViewModel base that compile together', :typescript_compile do
        layout = { 'type' => 'View', 'id' => 'root', 'child' => [
          { 'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'order_detail',
            'events' => { 'onOrderUpdated' => 'handleOrderUpdated', 'onClose' => '@{closePane}' } }
        ] }
        screen = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                                 .generate('Home', layout, screen_id: 'home')
        model_writer = RjuiTools::React::DataModelGenerator.allocate
        model_writer.instance_variable_set(:@use_typescript, true)
        model = model_writer.send(:generate_typescript_content, 'Home', [], [], [],
                                  model_writer.send(:extract_event_handler_bindings, layout), {})
        base_writer = RjuiTools::React::ViewModelGenerator.allocate
        base_writer.instance_variable_set(:@framework, RjuiTools::Core::Frameworks.for({ 'web_framework' => 'next' }))
        base = base_writer.send(:generate_typescript_base, 'Home', [], [],
                                base_writer.send(:extract_event_handler_bindings, layout))
        expect(model).to include('handleOrderUpdated?: (value: Record<string, unknown>) => void;')
        expect(model).not_to include('closePane')
        expect(base).to include('handleOrderUpdated: this.handleOrderUpdated,')
        source = [model, screen, base].map { |file| file.lines.reject { |l| l.start_with?('import ') }.join }.join("\n")
        expect(source).to compile_as_typescript.with_ambient(<<~TS)
          declare namespace React {
            type ReactNode = unknown;
            type ComponentType<P> = (props: P) => JSX.Element;
          }
          #{TypeScriptCompiler.template_declarations('EmbedContainer.tsx', 'EmbedContainerProps', 'EmbedNavigationMode',
                                                     'EmbedScreenResolver', 'EmbeddedEvent', 'EmbedStackEntry')}
          declare const EmbedContainer: (props: EmbedContainerProps) => JSX.Element;
          declare const OrderDetail: (props: { data?: Record<string, unknown> }) => JSX.Element;
          declare function useStringManager(): Record<string, string>;
          declare function screenMarker(screenId: string): Record<string, string>;
          interface AppRouterInstance {}
        TS
      end

      it 'omits eventBridge when events dict is empty' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail'
        )
        result = converter.convert
        expect(result).not_to include('eventBridge=')
      end
    end

    context 'navigationMode' do
      it 'emits delegate by default (v1)' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo'
        )
        expect(converter.convert).to include('navigationMode="delegate"')
      end

      it 'passes through explicit isolated value' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'navigationMode' => 'isolated'
        )
        expect(converter.convert).to include('navigationMode="isolated"')
      end
    end

    context 'isolated navigation mode (v1.5)' do
      it 'emits screenResolver via buildEmbedScreenResolver and the skew-guard comment' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'pane', 'screen' => 'order_detail',
          'navigationMode' => 'isolated'
        )
        result = converter.convert
        expect(result).to include('{/* Requires EmbedContainer.tsx template v2 (navigationMode: "isolated") */}')
        expect(result).to include("screenResolver={buildEmbedScreenResolver({ 'order_detail': OrderDetail })}")
      end

      it 'keeps the delegate call site free of isolated-only symbols (snapshot invariance)' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo'
        )
        result = converter.convert
        expect(result).not_to include('screenResolver')
        expect(result).not_to include('Requires EmbedContainer.tsx')
      end
    end

    context 'nested params (v1.5)' do
      it 'emits nested literal objects as JS object literals with leaf binding rewrite' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'profile' => { 'name' => '@{userName}', 'meta' => { 'age' => 36 } } }
        )
        result = converter.convert
        expect(result).to include('profile: { name: data.userName, meta: { age: 36 } }')
      end

      it 'emits {} for an empty nested object' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'extra' => {} }
        )
        expect(converter.convert).to include('extra: {}')
      end
    end
  end
end
