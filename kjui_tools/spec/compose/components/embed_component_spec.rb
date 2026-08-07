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

    # Regression: kjui-embed-modifier-attributes-not-emitted.
    # Authoring-time attrs (weight, width/height, margins, paddings) were
    # silently dropped — `Row { Embed(weight=1) Embed(weight=1) }` rendered
    # as a full-width first pane with the second pane sized to 0px on
    # Android. The fix emits `modifier = Modifier.<chain>` as a leading
    # named arg to EmbedContainer. Library support added in KotlinJsonUI
    # 2.8.4 (EmbedContainer now wraps content in Box(modifier=modifier)
    # so scope-bound modifiers like RowScope.weight reach a Layout node).
    context 'modifier emit (regression: kjui-embed-modifier-attributes-not-emitted)' do
      it 'emits weight when parent_type is Row' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'detailPane', 'screen' => 'item_detail', 'weight' => 1 },
          0,
          required_imports,
          'Row'
        )
        expect(result).to include('modifier = Modifier')
        expect(result).to include('.weight(1f)')
      end

      it 'emits weight when parent_type is Column' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'weight' => 2 },
          0,
          required_imports,
          'Column'
        )
        expect(result).to include('.weight(2f)')
      end

      it 'omits weight when parent_type is neither Row nor Column' do
        # weight only makes sense for Row/Column. Box-parent or root usage
        # should silently skip the weight emit (RowScope.weight is a scope-
        # bound extension and wouldn\'t resolve outside its scope anyway).
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'weight' => 1 },
          0,
          required_imports,
          'Box'
        )
        expect(result).not_to include('.weight(')
      end

      it 'emits width/height when set to literal Int or matchParent' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'bar_list', 'width' => 360, 'height' => 'matchParent' },
          0,
          required_imports,
          'Row'
        )
        expect(result).to include('.requiredWidth(360.dp)')
        expect(result).to include('.fillMaxHeight()')
      end

      it 'emits margins from topMargin and paddings' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'topMargin' => 16, 'paddings' => [8, 12, 8, 12] },
          0,
          required_imports
        )
        # topMargin lives in the margin-as-outer-padding emit; the
        # inner-padding emit handles `paddings`. Both should be present.
        expect(result).to include('.padding(top = 16.dp)')
        expect(result).to include('.padding(top = 8.dp, end = 12.dp, bottom = 8.dp, start = 12.dp)')
      end

      it 'emits no modifier arg when no relevant attrs are present' do
        # Backward compat: a bare Embed with just id+screen must emit the
        # same shape as before this fix (no `modifier = Modifier` arg).
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          Set.new,
          nil
        )
        # id triggers testTag — that\'s independent of this regression and
        # the test above ('requests embed_container and hilt_viewmodel imports')
        # already confirms imports. Here we just check there\'s no
        # `weight` / `width` / `height` / `padding` modifier when none are set.
        expect(result).not_to include('.weight(')
        expect(result).not_to include('.width(')
        expect(result).not_to include('.fillMaxWidth(')
        expect(result).not_to include('.fillMaxHeight(')
        expect(result).not_to include('.padding(')
      end

      it 'places modifier as the first named arg (before embedId)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo', 'weight' => 1 },
          0,
          required_imports,
          'Row'
        )
        # The modifier block must appear before `embedId = ...` so the
        # comma-handling in format() works: format() emits no leading or
        # trailing comma, and we suffix a `,` ourselves; embedId follows.
        modifier_idx = result.index('modifier = Modifier')
        embed_id_idx = result.index('embedId = "p"')
        expect(modifier_idx).not_to be_nil
        expect(embed_id_idx).not_to be_nil
        expect(modifier_idx).to be < embed_id_idx
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

    context 'isolated navigation mode (v1.5)' do
      it 'emits isolatedNavigation, the skew-guard comment, and the import key' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'pane', 'screen' => 'order_detail',
            'navigationMode' => 'isolated' },
          0,
          required_imports
        )
        expect(result).to include('// Requires KotlinJsonUI >= 2.12.0 (navigationMode: "isolated")')
        expect(result).to include('navigationMode = EmbedNavigationMode.Isolated,')
        expect(result).to include('isolatedNavigation = EmbedIsolatedNavigation.Automatic')
        expect(required_imports).to include(:embed_isolated_navigation)
      end

      it 'orders isolatedNavigation before eventBridge when both present' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'pane', 'screen' => 'foo',
            'navigationMode' => 'isolated',
            'events' => { 'onClose' => 'handleClose' } },
          0,
          required_imports
        )
        expect(result).to include('isolatedNavigation = EmbedIsolatedNavigation.Automatic,')
        expect(result.index('isolatedNavigation')).to be < result.index('eventBridge')
      end

      it 'keeps the delegate call site free of isolated-only symbols (snapshot invariance)' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo' },
          0,
          required_imports
        )
        expect(result).not_to include('isolatedNavigation')
        expect(result).not_to include('Requires KotlinJsonUI')
        expect(required_imports).not_to include(:embed_isolated_navigation)
      end
    end

    context 'nested params (v1.5)' do
      it 'emits nested literal objects as nested mapOf literals' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'params' => { 'profile' => { 'name' => 'Ada', 'meta' => { 'age' => 36 } } } },
          0,
          required_imports
        )
        expect(result).to include('"profile" to mapOf("name" to "Ada", "meta" to mapOf("age" to 36))')
      end

      it 'rewrites @{binding} leaves at any depth' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'params' => { 'profile' => { 'name' => '@{userName}' } } },
          0,
          required_imports
        )
        expect(result).to include('"profile" to mapOf("name" to data.userName)')
      end

      it 'emits emptyMap for an empty nested object' do
        result = described_class.generate(
          { 'type' => 'Embed', 'id' => 'p', 'screen' => 'foo',
            'params' => { 'extra' => {} } },
          0,
          required_imports
        )
        expect(result).to include('"extra" to emptyMap<String, Any>()')
      end
    end
  end
end
