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

    # Regression: sjui-embed-pane-container-root-ids-not-queryable-xcuitest —
    # EmbedContainer is a plain wrapper view, so a bare
    # .accessibilityIdentifier on it was pushed down into the embedded screen
    # and clobbered the embedded root container's own identifier (the root id
    # never resolved in XCUITest inside a pane while leaves still did).
    context 'accessibility exposure of an id-bearing Embed' do
      it 'becomes an explicit accessibility container with the anchor overlay' do
        code = convert(
          'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'order_detail'
        )
        expect(code).to include('.accessibilityElement(children: .contain)')
        expect(code).to include('.accessibilityIdentifier("detailPane")')
        expect(code.index('.accessibilityElement(children: .contain)'))
          .to be < code.index('.accessibilityIdentifier("detailPane")')
        # subtree is unknown at codegen time -> always merge-hazard anchored
        expect(code).to include('.overlay(alignment: .topLeading) {')
        expect(code).to include('.accessibilityElement(children: .ignore)')
      end

      it 'emits no accessibility modifiers for an Embed without id' do
        code = convert('type' => 'Embed', 'screen' => 'order_detail')
        expect(code).not_to include('.accessibilityIdentifier(')
        expect(code).not_to include('.accessibilityElement(children: .contain)')
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

    context 'responsive block (regression: sjui-embed-ignores-responsive-block-on-child + jui-embed-responsive-block-codegen-broken)' do
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

      it 'wraps the if/else chain in Group { } so AnyView(...) embedding is valid' do
        code = convert(
          'type' => 'Embed', 'id' => 'capturePane', 'screen' => 'photo_registration',
          'width' => 420,
          'responsive' => { 'regular' => { 'width' => 360 } }
        )
        # First line should be `Group {` and the chain should sit inside it.
        first_line = code.lines.first.strip
        expect(first_line).to eq('Group {')
        # Group must include both branches.
        expect(code).to include('Group {')
        expect(code.lines.last.strip).to eq('}')
      end

      it 'leaves non-responsive Embeds untouched (regression)' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'width' => 360
        )
        expect(code).not_to include('horizontalSizeClass')
        expect(code).not_to include('Group {')
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

    context 'isolated navigation mode (v1.5)' do
      it 'emits isolatedNavigation and the min-version skew-guard comment' do
        code = convert(
          'type' => 'Embed', 'id' => 'pane', 'screen' => 'order_detail',
          'navigationMode' => 'isolated'
        )
        expect(code).to include('// Requires SwiftJsonUI >= 10.5.0 (navigationMode: "isolated")')
        expect(code).to include('navigationMode: .isolated,')
        expect(code).to include('isolatedNavigation: .automatic')
      end

      it 'orders isolatedNavigation before eventBridge when both present' do
        code = convert(
          'type' => 'Embed', 'id' => 'pane', 'screen' => 'foo',
          'navigationMode' => 'isolated',
          'events' => { 'onClose' => 'handleClose' }
        )
        expect(code).to include('isolatedNavigation: .automatic,')
        expect(code.index('isolatedNavigation: .automatic')).to be < code.index('eventBridge:')
      end

      it 'keeps the delegate call site free of isolated-only symbols (snapshot invariance)' do
        code = convert('type' => 'Embed', 'id' => 'p', 'screen' => 'foo')
        expect(code).not_to include('isolatedNavigation')
        expect(code).not_to include('Requires SwiftJsonUI')
      end
    end

    context 'nested params (v1.5)' do
      it 'emits nested literal objects as nested Swift dict literals' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'profile' => { 'name' => 'Ada', 'meta' => { 'age' => 36 } } }
        )
        expect(code).to include('"profile": ["name": "Ada", "meta": ["age": 36]]')
      end

      it 'rewrites @{binding} leaves at any depth' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'profile' => { 'name' => '@{userName}' } }
        )
        expect(code).to include('"profile": ["name": data.userName]')
      end

      it 'emits [:] for an empty nested object' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'extra' => {} }
        )
        expect(code).to include('"extra": [:]')
      end

      it 'keeps flat params emission byte-stable (non-regression)' do
        code = convert(
          'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
          'params' => { 'orderId' => 'abc', 'count' => 5, 'open' => true }
        )
        expect(code).to include('"orderId": "abc",')
        expect(code).to include('"count": 5,')
        expect(code).to include('"open": true')
      end
    end
  end
end
