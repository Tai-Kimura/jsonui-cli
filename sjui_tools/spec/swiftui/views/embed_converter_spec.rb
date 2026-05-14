# frozen_string_literal: true

require 'swiftui/views/embed_converter'

RSpec.describe SjuiTools::SwiftUI::Views::EmbedConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def convert(component)
    result = described_class.new(component, 0, nil, nil, nil, nil).convert
    result.is_a?(Array) ? result.join("\n") : result.to_s
  end

  describe '#convert' do
    context 'minimal Embed (P1)' do
      it 'emits an EmbedContainer call with required attributes' do
        code = convert(
          'type' => 'Embed',
          'id' => 'detailPane',
          'screen' => 'order_detail'
        )
        expect(code).to include('EmbedContainer(')
        expect(code).to include('embedId: "detailPane"')
        expect(code).to include('screen: "order_detail"')
        expect(code).to include('navigationMode: .delegate')
        expect(code).to include('OrderDetailView()')
      end

      it 'converts snake_case screen to PascalCase View class name' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'user_profile_summary'
        )
        expect(code).to include('UserProfileSummaryView()')
      end

      it 'accepts PascalCase screen as-is (backward compat)' do
        code = convert('type' => 'Embed', 'id' => 'p', 'screen' => 'Counter')
        expect(code).to include('CounterView()')
        expect(code).to include('screen: "Counter"')
      end

      it 'emits a comment when screen is missing' do
        code = convert('type' => 'Embed', 'id' => 'p')
        expect(code).to include('Embed: missing required `screen` attribute')
      end
    end

    context 'params wiring (P2)' do
      it 'emits literal params using Swift dict literal syntax' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'orderId' => 'abc', 'count' => 5, 'open' => true }
        )
        expect(code).to include('params: [')
        expect(code).to include('"orderId": "abc"')
        expect(code).to include('"count": 5')
        expect(code).to include('"open": true')
      end

      it 'rewrites @{binding} params to `data.{prop}` references' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'orderId' => '@{selectedOrderId}' }
        )
        expect(code).to include('"orderId": data.selectedOrderId')
      end

      it 'omits the params arg when params dict is empty' do
        code = convert('type' => 'Embed', 'id' => 'p', 'screen' => 'foo')
        expect(code).not_to include('params:')
      end
    end

    context 'responsive block (regression: sjui-embed-ignores-responsive-block-on-child)' do
      it 'wraps the EmbedContainer in if/else when responsive overrides width' do
        code = convert(
          'type' => 'Embed', 'id' => 'capturePane', 'screen' => 'photo_registration',
          'width' => 420,
          'responsive' => { 'regular' => { 'width' => 360 } }
        )
        expect(code).to include('if horizontalSizeClass == .regular {')
        expect(code).to include('} else {')
        expect(code).to include('.frame(width: 360)')
        expect(code).to include('.frame(width: 420)')
      end

      it 'leaves non-responsive Embeds untouched (regression)' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'width' => 360
        )
        expect(code).not_to include('horizontalSizeClass')
        expect(code).to include('.frame(width: 360)')
      end
    end

    context 'events wiring (P2)' do
      it 'emits an eventBridge dispatching to viewModel handlers by event name' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'events' => { 'onOrderUpdated' => 'handleOrderUpdated' }
        )
        expect(code).to include('eventBridge: { event in')
        expect(code).to include('case .named(let name, let payload) = event')
        expect(code).to include('if name == "onOrderUpdated" { viewModel.handleOrderUpdated(payload) }')
      end

      it 'omits eventBridge when events dict is empty' do
        code = convert('type' => 'Embed', 'id' => 'p', 'screen' => 'foo')
        expect(code).not_to include('eventBridge:')
      end
    end
  end
end
