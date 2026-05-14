# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/embed_converter'

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

    context 'events wiring (P2)' do
      it 'emits an eventBridge that dispatches to viewModel handlers by event name' do
        converter = create_converter(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail',
          'events' => { 'onOrderUpdated' => 'handleOrderUpdated', 'onClose' => 'closePane' }
        )
        result = converter.convert
        expect(result).to include('eventBridge=')
        expect(result).to include("event.type === 'onOrderUpdated'")
        expect(result).to include('viewModel.handleOrderUpdated(event.payload)')
        expect(result).to include("event.type === 'onClose'")
        expect(result).to include('viewModel.closePane(event.payload)')
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

      it 'passes through explicit isolated value (v1.5 placeholder)' do
        converter = create_converter(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'navigationMode' => 'isolated'
        )
        expect(converter.convert).to include('navigationMode="isolated"')
      end
    end
  end
end
