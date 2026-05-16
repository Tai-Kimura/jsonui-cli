# frozen_string_literal: true

require 'compose/components/embed_component'

RSpec.describe KjuiTools::Compose::Components::EmbedComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    context 'minimal Embed (P1)' do
      it 'emits an EmbedContainer call with required arguments' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'order_detail' },
          0,
          required_imports
        )
        expect(result).to include('EmbedContainer(')
        expect(result).to include('embedId = "detailPane"')
        expect(result).to include('navigationMode = EmbedNavigationMode.Delegate')
        expect(result).to include('OrderDetailView(')
        expect(result).to include('key = "detailPane"')
      end

      it 'requests embed_container and hilt_viewmodel imports' do
        described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          required_imports
        )
        expect(required_imports).to include(:embed_container)
        expect(required_imports).to include(:hilt_viewmodel)
        # Old emit path is gone — `viewmodel_compose` would pull in the
        # NewInstanceFactory-only `viewModel(...)` API.
        expect(required_imports).not_to include(:viewmodel_compose)
      end

      it 'converts snake_case screen to PascalCase composable' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'user_profile_summary' },
          0,
          required_imports
        )
        expect(result).to include('UserProfileSummaryView(')
      end

      it 'passes PascalCase screen through unchanged (backward compat)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'Counter' },
          0,
          required_imports
        )
        expect(result).to include('CounterView(')
      end

      it 'emits a comment when screen is missing' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p' },
          0,
          required_imports
        )
        expect(result).to include('Embed: missing required `screen` attribute')
      end
    end

    context 'params wiring (P2)' do
      it 'emits literal params as Kotlin mapOf entries' do
        result = described_class.generate(
          {
            'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'params' => { 'orderId' => 'abc', 'count' => 5, 'open' => true }
          },
          0,
          required_imports
        )
        expect(result).to include('params = mapOf(')
        expect(result).to include('"orderId" to "abc"')
        expect(result).to include('"count" to 5')
        expect(result).to include('"open" to true')
      end

      it 'rewrites @{binding} params to `data.{prop}` references' do
        result = described_class.generate(
          {
            'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'params' => { 'orderId' => '@{selectedOrderId}' }
          },
          0,
          required_imports
        )
        expect(result).to include('"orderId" to data.selectedOrderId')
      end

      it 'omits the params arg when params dict is empty' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          required_imports
        )
        expect(result).not_to include('params = mapOf')
      end
    end

    context 'events wiring (P2)' do
      it 'emits an eventBridge dispatching to viewModel handlers by event name' do
        result = described_class.generate(
          {
            'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'events' => { 'onOrderUpdated' => 'handleOrderUpdated' }
          },
          0,
          required_imports
        )
        expect(result).to include('eventBridge = { event ->')
        expect(result).to include('event is EmbeddedEvent.Named')
        expect(result).to include('"onOrderUpdated" -> viewModel.handleOrderUpdated(event.payload)')
        expect(required_imports).to include(:embedded_event)
      end

      it 'omits eventBridge when events dict is empty' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          required_imports
        )
        expect(result).not_to include('eventBridge')
        expect(required_imports).not_to include(:embedded_event)
      end
    end

    context 'import key convention (regression: kjui-embed-with-responsive-codegen-malformed issue 3)' do
      it 'registers tabview: import key without View suffix (resolver appends it)' do
        described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'home' },
          0,
          required_imports
        )
        expect(required_imports).to include('tabview:Home')
        expect(required_imports).not_to include('tabview:HomeView')
      end

      it 'registers PascalCase snake_case screen without View suffix' do
        described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'photo_registration' },
          0,
          required_imports
        )
        expect(required_imports).to include('tabview:PhotoRegistration')
        expect(required_imports).not_to include('tabview:PhotoRegistrationView')
      end
    end

    # Regression: kjui-embed-child-vm-non-hilt-factory.
    # Previously emitted `androidx.lifecycle.viewmodel.compose.viewModel(...)`
    # which uses NewInstanceFactory and crashes on @HiltViewModel-annotated VMs
    # with NoSuchMethodException (no no-arg ctor). The replacement
    # `hiltViewModel(viewModelStoreOwner, key)` works for BOTH Hilt and plain
    # VMs — Hilt VMs resolve via HiltViewModelFactory, plain VMs fall back to
    # NewInstanceFactory.
    context 'child VM factory (regression: kjui-embed-child-vm-non-hilt-factory)' do
      it 'emits hiltViewModel(...) for the embedded screen, not viewModel(...)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'item_detail' },
          0,
          required_imports
        )
        expect(result).to include('viewModel = androidx.hilt.navigation.compose.hiltViewModel(')
        expect(result).not_to include('viewModel = androidx.lifecycle.viewmodel.compose.viewModel(')
      end

      it 'forwards viewModelStoreOwner and a stable key to hiltViewModel' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'item_detail' },
          0,
          required_imports
        )
        expect(result).to include('viewModelStoreOwner = embedScope.viewModelStoreOwner,')
        expect(result).to include('key = "detailPane"')
      end
    end

    context 'navigationMode' do
      it 'emits Delegate by default (v1)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          required_imports
        )
        expect(result).to include('navigationMode = EmbedNavigationMode.Delegate')
      end

      it 'emits Isolated for explicit isolated value (v1.5 placeholder)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'navigationMode' => 'isolated' },
          0,
          required_imports
        )
        expect(result).to include('navigationMode = EmbedNavigationMode.Isolated')
      end
    end
  end
end
