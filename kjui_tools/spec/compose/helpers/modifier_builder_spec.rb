# frozen_string_literal: true

require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Helpers::ModifierBuilder do
  describe '.build_padding' do
    it 'builds single value padding' do
      json_data = { 'padding' => 16 }
      result = described_class.build_padding(json_data)
      expect(result).to include('.padding(16.dp)')
    end

    it 'builds array padding with 4 values' do
      json_data = { 'padding' => [10, 20, 30, 40] }
      result = described_class.build_padding(json_data)
      expect(result.first).to include('top = 10.dp')
      expect(result.first).to include('end = 20.dp')
      expect(result.first).to include('bottom = 30.dp')
      expect(result.first).to include('start = 40.dp')
    end

    it 'builds individual padding attributes' do
      json_data = { 'paddingTop' => 10, 'paddingBottom' => 20 }
      result = described_class.build_padding(json_data)
      expect(result).to include('.padding(top = 10.dp)')
      expect(result).to include('.padding(bottom = 20.dp)')
    end

    it 'handles paddings attribute' do
      json_data = { 'paddings' => 16 }
      result = described_class.build_padding(json_data)
      expect(result).to include('.padding(16.dp)')
    end
  end

  describe '.build_margins' do
    it 'builds single value margins' do
      json_data = { 'margins' => 8 }
      result = described_class.build_margins(json_data)
      expect(result).to include('.padding(8.dp)')
    end

    it 'builds array margins with 4 values' do
      json_data = { 'margins' => [5, 10, 15, 20] }
      result = described_class.build_margins(json_data)
      expect(result.first).to include('top = 5.dp')
    end

    it 'builds individual margin attributes' do
      json_data = { 'topMargin' => 10, 'leftMargin' => 20 }
      result = described_class.build_margins(json_data)
      expect(result).to include('.padding(top = 10.dp)')
      expect(result).to include('.padding(start = 20.dp)')
    end
  end

  describe '.build_weight' do
    it 'builds weight modifier when in Row/Column' do
      json_data = { 'weight' => 1 }
      result = described_class.build_weight(json_data, 'Row')
      expect(result).to include('.weight(1f)')
    end

    it 'returns empty when weight is 0' do
      json_data = { 'weight' => 0 }
      result = described_class.build_weight(json_data, 'Row')
      expect(result).to be_empty
    end

    it 'returns empty when no parent orientation' do
      json_data = { 'weight' => 1 }
      result = described_class.build_weight(json_data, nil)
      expect(result).to be_empty
    end
  end

  describe '.build_size' do
    it 'builds width modifier' do
      json_data = { 'width' => 100 }
      result = described_class.build_size(json_data)
      expect(result).to include('.width(100.dp)')
    end

    it 'builds height modifier' do
      json_data = { 'height' => 50 }
      result = described_class.build_size(json_data)
      expect(result).to include('.height(50.dp)')
    end

    it 'builds fillMaxWidth for matchParent' do
      json_data = { 'width' => 'matchParent' }
      result = described_class.build_size(json_data)
      expect(result).to include('.fillMaxWidth()')
    end

    it 'builds fillMaxHeight for matchParent' do
      json_data = { 'height' => 'matchParent' }
      result = described_class.build_size(json_data)
      expect(result).to include('.fillMaxHeight()')
    end

    it 'builds wrapContentWidth for wrapContent' do
      json_data = { 'width' => 'wrapContent' }
      result = described_class.build_size(json_data)
      expect(result).to include('.wrapContentWidth()')
    end

    it 'builds min/max width constraints' do
      json_data = { 'minWidth' => 50, 'maxWidth' => 200 }
      result = described_class.build_size(json_data)
      expect(result).to include('.widthIn(min = 50.dp, max = 200.dp)')
    end

    # Regression: kjui-responsive-widthin-after-fillmaxwidth-no-op.
    # `.fillMaxWidth()` pins min = max = parent's maxWidth. A trailing
    # `.widthIn(max = N.dp)` then can't narrow maxWidth because minWidth
    # is already pinned to parent's width — the constraint clamps back to
    # 940dp on a tablet chat pane and the bordered button overflows.
    # Order must be: widthIn (cap) FIRST, then fillMaxWidth (fill within
    # the cap). Same applies to heightIn / fillMaxHeight.
    it 'emits widthIn(max=...) before fillMaxWidth when both width:matchParent and maxWidth are present' do
      json_data = { 'width' => 'matchParent', 'maxWidth' => 320 }
      result = described_class.build_size(json_data)
      width_in_idx = result.index('.widthIn(max = 320.dp)')
      fill_idx = result.index('.fillMaxWidth()')
      expect(width_in_idx).not_to be_nil
      expect(fill_idx).not_to be_nil
      expect(width_in_idx).to be < fill_idx
    end

    it 'emits combined widthIn(min,max) before fillMaxWidth' do
      json_data = { 'width' => 'matchParent', 'minWidth' => 100, 'maxWidth' => 320 }
      result = described_class.build_size(json_data)
      width_in_idx = result.index('.widthIn(min = 100.dp, max = 320.dp)')
      fill_idx = result.index('.fillMaxWidth()')
      expect(width_in_idx).not_to be_nil
      expect(fill_idx).not_to be_nil
      expect(width_in_idx).to be < fill_idx
    end

    it 'emits heightIn(max=...) before fillMaxHeight when both height:matchParent and maxHeight are present' do
      json_data = { 'height' => 'matchParent', 'maxHeight' => 240 }
      result = described_class.build_size(json_data)
      height_in_idx = result.index('.heightIn(max = 240.dp)')
      fill_idx = result.index('.fillMaxHeight()')
      expect(height_in_idx).not_to be_nil
      expect(fill_idx).not_to be_nil
      expect(height_in_idx).to be < fill_idx
    end

    it 'builds aspect ratio' do
      json_data = { 'aspectWidth' => 16, 'aspectHeight' => 9 }
      result = described_class.build_size(json_data)
      ratio = 16.0 / 9.0
      expect(result).to include(".aspectRatio(#{ratio}f)")
    end

    # Regression: kjui-label-gravity-center-not-vertically-centered.
    # Compose `Text` has no vertical text-align, so a height-filling Label with
    # `gravity: center` must pair the fill with wrapContentHeight(align) to
    # vertically center its glyphs (iOS `.frame(alignment: .center)` parity).
    context 'Label vertical gravity centering' do
      it 'pairs fillMaxHeight with wrapContentHeight(center) for height:matchParent + gravity:center' do
        json_data = { 'type' => 'Label', 'height' => 'matchParent', 'gravity' => 'center' }
        result = described_class.build_size(json_data)
        fill_idx = result.index('.fillMaxHeight()')
        wrap_idx = result.index('.wrapContentHeight(align = Alignment.CenterVertically)')
        expect(fill_idx).not_to be_nil
        expect(wrap_idx).not_to be_nil
        expect(fill_idx).to be < wrap_idx
      end

      it 'emits wrapContentHeight(center) for a vertical-container weight + gravity:center' do
        json_data = { 'type' => 'Label', 'weight' => 1, 'gravity' => 'center' }
        result = described_class.build_size(json_data, 'Column')
        expect(result).to include('.wrapContentHeight(align = Alignment.CenterVertically)')
      end

      it 'does NOT emit wrapContentHeight for a weight in a horizontal (Row) container' do
        json_data = { 'type' => 'Label', 'weight' => 1, 'gravity' => 'center' }
        result = described_class.build_size(json_data, 'Row')
        expect(result.join).not_to include('wrapContentHeight(align')
      end

      it 'uses Alignment.Bottom for gravity:bottom' do
        json_data = { 'type' => 'Label', 'height' => 'matchParent', 'gravity' => 'bottom' }
        result = described_class.build_size(json_data)
        expect(result).to include('.wrapContentHeight(align = Alignment.Bottom)')
      end

      it 'preserves the minHeight + gravity defaultMinSize/wrapContentHeight pair' do
        json_data = { 'type' => 'Label', 'minHeight' => 44, 'gravity' => 'center' }
        result = described_class.build_size(json_data)
        expect(result).to include('.defaultMinSize(minHeight = 44.dp)')
        expect(result).to include('.wrapContentHeight(align = Alignment.CenterVertically)')
        # Only one wrapContentHeight(align) — minHeight path must not double-emit.
        expect(result.count { |m| m.include?('wrapContentHeight(align') }).to eq(1)
      end

      it 'does NOT vertically center a non-Label View even with gravity:center' do
        json_data = { 'type' => 'View', 'height' => 'matchParent', 'gravity' => 'center' }
        result = described_class.build_size(json_data)
        expect(result).to include('.fillMaxHeight()')
        expect(result.join).not_to include('wrapContentHeight(align')
      end

      it 'does NOT emit wrapContentHeight for a filling Label without gravity' do
        json_data = { 'type' => 'Label', 'height' => 'matchParent' }
        result = described_class.build_size(json_data)
        expect(result).to include('.fillMaxHeight()')
        expect(result.join).not_to include('wrapContentHeight(align')
      end
    end
  end

  describe '.build_shadow' do
    let(:imports) { Set.new }

    it 'builds simple shadow' do
      json_data = { 'shadow' => '#000000' }
      result = described_class.build_shadow(json_data, imports)
      expect(result.first).to include('.dropShadow(')
      expect(result.first).to include('radius = 4.dp')
    end

    it 'builds complex shadow with radius' do
      json_data = { 'shadow' => { 'radius' => 8 }, 'cornerRadius' => 12 }
      result = described_class.build_shadow(json_data, imports)
      expect(result.first).to include('radius = 8.dp')
      expect(result.first).to include('RoundedCornerShape(12.dp)')
    end

    it 'adds drop_shadow import' do
      json_data = { 'shadow' => '#000000' }
      described_class.build_shadow(json_data, imports)
      expect(imports).to include(:drop_shadow)
    end
  end

  describe '.build_background' do
    let(:imports) { Set.new }

    it 'builds simple background' do
      json_data = { 'background' => '#FF0000' }
      result = described_class.build_background(json_data, imports)
      # ResourceResolver.process_color returns parseColor format
      expect(result.first).to include('.background(')
      expect(result.first).to include('#FF0000')
    end

    it 'builds background with corner radius' do
      json_data = { 'background' => '#FF0000', 'cornerRadius' => 8 }
      result = described_class.build_background(json_data, imports)
      expect(result).to include('.clip(RoundedCornerShape(8.dp))')
      expect(result.join).to include('.background(')
    end

    it 'builds border without background' do
      json_data = { 'borderColor' => '#0000FF', 'borderWidth' => 2, 'cornerRadius' => 4 }
      result = described_class.build_background(json_data, imports)
      expect(result.join).to include('.border(2.dp,')
      expect(result.join).to include('RoundedCornerShape(4.dp)')
    end

    # Regression: kjui-border-without-corner-radius-missing-rectangle-shape-import.
    # `RectangleShape` lives in `androidx.compose.ui.graphics`, NOT in the
    # `androidx.compose.foundation.shape` namespace registered by `:shape`.
    # Border emit without `cornerRadius` referenced `RectangleShape` but
    # never asked for its import, blowing up Kotlin compile with
    # "Unresolved reference 'RectangleShape'".
    it 'registers :rectangle_shape import when border has no cornerRadius' do
      json_data = { 'borderColor' => '#0000FF', 'borderWidth' => 1 }
      described_class.build_background(json_data, imports)
      expect(imports).to include(:rectangle_shape)
    end

    it 'does NOT register :rectangle_shape when cornerRadius is present' do
      json_data = { 'borderColor' => '#0000FF', 'borderWidth' => 1, 'cornerRadius' => 4 }
      described_class.build_background(json_data, imports)
      expect(imports).not_to include(:rectangle_shape)
    end

    it 'emits .border(...) with RectangleShape literal when no cornerRadius' do
      json_data = { 'borderColor' => '#0000FF', 'borderWidth' => 1 }
      result = described_class.build_background(json_data, imports)
      expect(result.join).to include('RectangleShape')
      expect(result.join).not_to include('RoundedCornerShape')
    end
  end

  describe '.build_shadow (RectangleShape import — regression)' do
    let(:imports) { Set.new }

    it 'registers :rectangle_shape when shadow has no cornerRadius (string form)' do
      json_data = { 'shadow' => '#000000' }
      described_class.build_shadow(json_data, imports)
      expect(imports).to include(:rectangle_shape)
    end

    it 'registers :rectangle_shape when shadow has no cornerRadius (hash form)' do
      json_data = { 'shadow' => { 'radius' => 6 } }
      described_class.build_shadow(json_data, imports)
      expect(imports).to include(:rectangle_shape)
    end

    it 'does NOT register :rectangle_shape when cornerRadius is present' do
      json_data = { 'shadow' => { 'radius' => 6 }, 'cornerRadius' => 8 }
      described_class.build_shadow(json_data, imports)
      expect(imports).not_to include(:rectangle_shape)
    end
  end

  describe '.build_visibility' do
    let(:imports) { Set.new }

    it 'handles static visibility' do
      json_data = { 'visibility' => 'gone' }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:visibility]).to eq('gone')
    end

    it 'handles data binding visibility' do
      json_data = { 'visibility' => '@{isVisible}' }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:visibility_binding]).to eq('data.isVisible')
    end

    it 'handles hidden attribute' do
      json_data = { 'hidden' => true }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:hidden]).to be true
    end

    it 'handles hidden data binding' do
      json_data = { 'hidden' => '@{isHidden}' }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:hidden_binding]).to eq('data.isHidden')
    end

    # Canonical negation emit (binding_semantics.json): hidden is a boolean
    # value context, so '@{!prop}' must produce valid Kotlin. The old emit
    # produced 'data.!isLogin' (compile error); a bare nullable boolean is
    # coerced so the '!' operator always has a non-null receiver.
    it 'emits a real Kotlin negation for hidden negation bindings' do
      json_data = { 'hidden' => '@{!isLogin}' }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:hidden_binding]).to eq('!(data.isLogin ?: false)')
    end

    it 'emits an elvis default for hidden ?? bindings' do
      json_data = { 'hidden' => '@{isHidden ?? false}' }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:hidden_binding]).to eq('(data.isHidden ?: false)')
    end

    it 'emits an elvis default for visibility ?? bindings' do
      json_data = { 'visibility' => "@{paneVisibility ?? 'gone'}" }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:visibility_info][:visibility_binding]).to eq('(data.paneVisibility ?: "gone")')
    end

    it 'builds alpha modifier' do
      json_data = { 'alpha' => 0.5 }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:modifiers]).to include('.alpha(0.5f)')
    end

    it 'handles opacity as alpha' do
      json_data = { 'opacity' => 0.8 }
      result = described_class.build_visibility(json_data, imports)
      expect(result[:modifiers]).to include('.alpha(0.8f)')
    end
  end

  describe '.build_alignment' do
    let(:imports) { Set.new }

    context 'in Row' do
      it 'builds vertical alignment' do
        json_data = { 'alignTop' => true }
        result = described_class.build_alignment(json_data, imports, 'Row')
        expect(result).to include('.align(Alignment.Top)')
      end

      it 'builds center vertical' do
        json_data = { 'centerVertical' => true }
        result = described_class.build_alignment(json_data, imports, 'Row')
        expect(result).to include('.align(Alignment.CenterVertically)')
      end
    end

    context 'in Column' do
      it 'builds horizontal alignment' do
        json_data = { 'alignLeft' => true }
        result = described_class.build_alignment(json_data, imports, 'Column')
        expect(result).to include('.align(Alignment.Start)')
      end

      it 'builds center horizontal' do
        json_data = { 'centerHorizontal' => true }
        result = described_class.build_alignment(json_data, imports, 'Column')
        expect(result).to include('.align(Alignment.CenterHorizontally)')
      end
    end

    context 'in Box' do
      it 'builds top-left alignment' do
        json_data = { 'alignTop' => true, 'alignLeft' => true }
        result = described_class.build_alignment(json_data, imports, 'Box')
        expect(result).to include('.align(Alignment.TopStart)')
      end

      it 'builds center alignment' do
        json_data = { 'centerInParent' => true }
        result = described_class.build_alignment(json_data, imports, 'Box')
        expect(result).to include('.align(Alignment.Center)')
      end

      it 'builds bottom-right alignment' do
        json_data = { 'alignBottom' => true, 'alignRight' => true }
        result = described_class.build_alignment(json_data, imports, 'Box')
        expect(result).to include('.align(Alignment.BottomEnd)')
      end

      it 'uses BiasAlignment for centered horizontal with top' do
        json_data = { 'alignTop' => true, 'centerHorizontal' => true }
        result = described_class.build_alignment(json_data, imports, 'Box')
        expect(result.first).to include('BiasAlignment(0f, -1f)')
      end
    end
  end

  describe '.build_relative_positioning' do
    it 'builds constraints for alignTopOfView' do
      json_data = { 'alignTopOfView' => 'other' }
      result = described_class.build_relative_positioning(json_data)
      expect(result).to include('bottom.linkTo(other.top)')
    end

    it 'builds constraints with margins' do
      json_data = { 'alignTopOfView' => 'other', 'bottomMargin' => 8 }
      result = described_class.build_relative_positioning(json_data)
      expect(result).to include('bottom.linkTo(other.top, margin = 8.dp)')
    end

    it 'builds parent constraints' do
      json_data = { 'alignTop' => true, 'alignLeft' => true }
      result = described_class.build_relative_positioning(json_data)
      expect(result).to include('top.linkTo(parent.top)')
      expect(result).to include('start.linkTo(parent.start)')
    end

    it 'builds center constraints' do
      json_data = { 'centerInParent' => true }
      result = described_class.build_relative_positioning(json_data)
      expect(result).to include('top.linkTo(parent.top)')
      expect(result).to include('bottom.linkTo(parent.bottom)')
      expect(result).to include('start.linkTo(parent.start)')
      expect(result).to include('end.linkTo(parent.end)')
    end
  end

  describe '.format' do
    it 'formats single modifier' do
      modifiers = ['.padding(16.dp)']
      result = described_class.format(modifiers, 0)
      expect(result).to include('modifier = Modifier')
      expect(result).to include('.padding(16.dp)')
    end

    it 'formats multiple modifiers' do
      modifiers = ['.width(100.dp)', '.height(50.dp)']
      result = described_class.format(modifiers, 0)
      expect(result).to include('.width(100.dp)')
      expect(result).to include('.height(50.dp)')
    end

    it 'returns empty string for empty modifiers' do
      result = described_class.format([], 0)
      expect(result).to eq('')
    end

    context 'with is_root: true (caller modifier propagation)' do
      it 'starts the chain from lowercase `modifier`' do
        modifiers = ['.padding(16.dp)']
        result = described_class.format(modifiers, 0, is_root: true)
        expect(result).to include('modifier = modifier')
        expect(result).not_to include('modifier = Modifier')
        expect(result).to include('.padding(16.dp)')
      end

      it 'emits a standalone `modifier = modifier` for an empty chain' do
        result = described_class.format([], 0, is_root: true)
        expect(result).to include('modifier = modifier')
        # No fresh `Modifier` starting point should appear.
        expect(result).not_to include('modifier = Modifier')
      end

      it 'works when modifiers start with the literal "Modifier" sentinel' do
        # Some callers prepend "Modifier" as a sentinel — the chain still
        # opens from caller's `modifier` when is_root.
        modifiers = ['Modifier', '.fillMaxSize()']
        result = described_class.format(modifiers, 0, is_root: true)
        expect(result).to include('modifier = modifier')
        expect(result).to include('.fillMaxSize()')
      end
    end

    context 'with is_root: false (default, nested)' do
      it 'starts the chain from uppercase `Modifier` (regression guard)' do
        modifiers = ['.padding(16.dp)']
        result = described_class.format(modifiers, 0)
        expect(result).to include('modifier = Modifier')
        expect(result).not_to match(/modifier = modifier\b/)
      end

      it 'returns "" for an empty chain when not root (regression guard)' do
        result = described_class.format([], 0)
        expect(result).to eq('')
      end
    end
  end

  describe '.process_dimension' do
    it 'returns dp for numeric value' do
      result = described_class.send(:process_dimension, 16)
      expect(result).to eq('16.dp')
    end

    it 'returns dp for float value' do
      result = described_class.send(:process_dimension, 8.5)
      expect(result).to eq('8.5.dp')
    end

    it 'handles data binding syntax' do
      result = described_class.send(:process_dimension, '@{paddingValue}')
      expect(result).to eq('data.paddingValue.dp')
    end

    it 'handles data binding with complex variable name' do
      result = described_class.send(:process_dimension, '@{item.padding}')
      expect(result).to eq('data.item.padding.dp')
    end

    it 'returns dp for regular string value' do
      result = described_class.send(:process_dimension, '24')
      expect(result).to eq('24.dp')
    end

    it 'returns 0.dp for nil or unsupported types' do
      result = described_class.send(:process_dimension, nil)
      expect(result).to eq('0.dp')
    end
  end

  describe '.has_lifecycle_events?' do
    it 'returns truthy when onAppear is present' do
      json_data = { 'onAppear' => 'loadData' }
      expect(described_class.has_lifecycle_events?(json_data)).to be_truthy
    end

    it 'returns truthy when onDisappear is present' do
      json_data = { 'onDisappear' => 'cleanup' }
      expect(described_class.has_lifecycle_events?(json_data)).to be_truthy
    end

    it 'returns truthy when both are present' do
      json_data = { 'onAppear' => 'loadData', 'onDisappear' => 'cleanup' }
      expect(described_class.has_lifecycle_events?(json_data)).to be_truthy
    end

    it 'returns falsy when neither is present' do
      json_data = { 'type' => 'View' }
      expect(described_class.has_lifecycle_events?(json_data)).to be_falsy
    end
  end

  describe '.build_lifecycle_effects' do
    let(:imports) { Set.new }

    context 'with onAppear' do
      it 'generates LaunchedEffect code' do
        json_data = { 'onAppear' => 'loadData' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('LaunchedEffect(Unit)')
        expect(result[:before]).to include('data.loadData?.invoke()')
      end

      it 'handles handler with colon' do
        json_data = { 'onAppear' => 'loadData:' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('data.loadData?.invoke()')
      end

      it 'strips @{} binding syntax' do
        json_data = { 'onAppear' => '@{onInitComplete}' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('data.onInitComplete?.invoke()')
        expect(result[:before]).not_to include('@{')
      end

      it 'adds launched_effect import' do
        json_data = { 'onAppear' => 'loadData' }
        described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(imports).to include(:launched_effect)
      end

      it 'includes onAppear comment' do
        json_data = { 'onAppear' => 'loadData' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('// onAppear lifecycle event')
      end
    end

    context 'with onDisappear' do
      it 'generates DisposableEffect code' do
        json_data = { 'onDisappear' => 'cleanup' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('DisposableEffect(Unit)')
        expect(result[:before]).to include('onDispose {')
        expect(result[:before]).to include('data.cleanup?.invoke()')
      end

      it 'handles handler with colon' do
        json_data = { 'onDisappear' => 'cleanup:' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('data.cleanup?.invoke()')
      end

      it 'strips @{} binding syntax' do
        json_data = { 'onDisappear' => '@{onCleanup}' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('data.onCleanup?.invoke()')
        expect(result[:before]).not_to include('@{')
      end

      it 'adds disposable_effect import' do
        json_data = { 'onDisappear' => 'cleanup' }
        described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(imports).to include(:disposable_effect)
      end

      it 'includes onDisappear comment' do
        json_data = { 'onDisappear' => 'cleanup' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('// onDisappear lifecycle event')
      end
    end

    context 'with both lifecycle events' do
      it 'generates both effects' do
        json_data = { 'onAppear' => 'loadData', 'onDisappear' => 'cleanup' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to include('LaunchedEffect(Unit)')
        expect(result[:before]).to include('DisposableEffect(Unit)')
        expect(result[:before]).to include('data.loadData?.invoke()')
        expect(result[:before]).to include('data.cleanup?.invoke()')
      end

      it 'adds both imports' do
        json_data = { 'onAppear' => 'loadData', 'onDisappear' => 'cleanup' }
        described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(imports).to include(:launched_effect)
        expect(imports).to include(:disposable_effect)
      end
    end

    context 'without lifecycle events' do
      it 'returns empty before/after' do
        json_data = { 'type' => 'View' }
        result = described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(result[:before]).to eq('')
        expect(result[:after]).to eq('')
      end

      it 'does not add imports' do
        json_data = { 'type' => 'View' }
        described_class.build_lifecycle_effects(json_data, 1, imports)
        expect(imports).not_to include(:launched_effect)
        expect(imports).not_to include(:disposable_effect)
      end
    end

    context 'with depth indentation' do
      it 'applies correct indentation at depth 0' do
        json_data = { 'onAppear' => 'loadData' }
        result = described_class.build_lifecycle_effects(json_data, 0, imports)
        expect(result[:before]).to include('LaunchedEffect(Unit) {')
        expect(result[:before]).to include('    data.loadData?.invoke()')
      end

      it 'applies correct indentation at depth 2' do
        json_data = { 'onAppear' => 'loadData' }
        result = described_class.build_lifecycle_effects(json_data, 2, imports)
        expect(result[:before]).to include('        LaunchedEffect(Unit) {')
        expect(result[:before]).to include('            data.loadData?.invoke()')
      end
    end
  end

  # Regression: kjui-responsive-centerhorizontal-modifier-order-not-centered.
  # When `width: matchParent` (→ `.fillMaxWidth()`), `maxWidth: N` (→
  # `.widthIn(max = N.dp)`), and an alignment anchor like `centerHorizontal:
  # true` (→ `.wrapContentWidth(Alignment.CenterHorizontally)` via the
  # ScopeFree branch of build_alignment) all coexist, the chain must end up
  # as `.fillMax<Axis>() → .wrapContent<Axis>(Alignment.X) → .<axis>In(...)`.
  # The default concat order produces `wrapContent → axisIn → fillMax`,
  # which leaves the maxWidth-clamped child flush-left on Android because
  # `wrapContentWidth` aligns within the child's own (clamped) bounds, not
  # the parent's full width.
  describe '.reorder_alignment_anchor!' do
    it 'moves fillMaxWidth before wrapContentWidth(CenterHorizontally) when widthIn is also present' do
      modifiers = [
        '.testTag("mypage_content_container")',
        '.semantics { testTagsAsResourceId = true }',
        '.wrapContentWidth(Alignment.CenterHorizontally)',
        '.widthIn(max = 960.dp)',
        '.fillMaxWidth()',
        '.wrapContentHeight()',
        '.padding(bottom = 40.dp)'
      ]
      described_class.reorder_alignment_anchor!(modifiers)

      fill_idx = modifiers.index('.fillMaxWidth()')
      wrap_idx = modifiers.index('.wrapContentWidth(Alignment.CenterHorizontally)')
      in_idx = modifiers.index('.widthIn(max = 960.dp)')

      expect(fill_idx).to be < wrap_idx
      expect(wrap_idx).to be < in_idx
    end

    it 'reorders the same pattern with Alignment.Start (alignLeft + maxWidth)' do
      modifiers = [
        '.wrapContentWidth(Alignment.Start)',
        '.widthIn(max = 480.dp)',
        '.fillMaxWidth()'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.fillMaxWidth()',
        '.wrapContentWidth(Alignment.Start)',
        '.widthIn(max = 480.dp)'
      ])
    end

    it 'reorders the same pattern with Alignment.End (alignRight + maxWidth)' do
      modifiers = [
        '.wrapContentWidth(Alignment.End)',
        '.widthIn(max = 480.dp)',
        '.fillMaxWidth()'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.fillMaxWidth()',
        '.wrapContentWidth(Alignment.End)',
        '.widthIn(max = 480.dp)'
      ])
    end

    it 'applies symmetrically on the height axis when heightIn coexists with wrapContentHeight(Alignment.X)' do
      modifiers = [
        '.wrapContentHeight(Alignment.Bottom)',
        '.heightIn(max = 400.dp)',
        '.fillMaxHeight()'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.fillMaxHeight()',
        '.wrapContentHeight(Alignment.Bottom)',
        '.heightIn(max = 400.dp)'
      ])
    end

    it 'leaves the chain alone when widthIn is absent (no maxWidth cap, no misalignment risk)' do
      modifiers = [
        '.wrapContentWidth(Alignment.CenterHorizontally)',
        '.fillMaxWidth()'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.wrapContentWidth(Alignment.CenterHorizontally)',
        '.fillMaxWidth()'
      ])
    end

    it 'leaves the chain alone when wrapContent<Axis> has no Alignment argument (plain wrapContent)' do
      modifiers = [
        '.wrapContentWidth()',
        '.widthIn(max = 960.dp)',
        '.fillMaxWidth()'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.wrapContentWidth()',
        '.widthIn(max = 960.dp)',
        '.fillMaxWidth()'
      ])
    end

    it 'is a no-op when the chain is already in the correct order' do
      modifiers = [
        '.fillMaxWidth()',
        '.wrapContentWidth(Alignment.CenterHorizontally)',
        '.widthIn(max = 960.dp)'
      ]
      described_class.reorder_alignment_anchor!(modifiers)
      expect(modifiers).to eq([
        '.fillMaxWidth()',
        '.wrapContentWidth(Alignment.CenterHorizontally)',
        '.widthIn(max = 960.dp)'
      ])
    end
  end

  describe '.build_long_pressable' do
    before do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    end

    it 'emits an Initial-pass pointerInput long-press detector for a binding handler' do
      imports = Set.new
      json_data = { 'onLongPress' => '@{onCellLongPress}' }
      result = described_class.build_long_pressable(json_data, imports)

      expect(result.length).to eq(1)
      gesture = result.first
      expect(gesture).to include('.pointerInput(data) {')
      expect(gesture).to include('awaitEachGesture {')
      # Initial pass so inner clickables (Button etc.) cannot starve the detector
      expect(gesture).to include('awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)')
      expect(gesture).to include('withTimeout(viewConfiguration.longPressTimeoutMillis)')
      expect(gesture).to include('PointerEventTimeoutCancellationException')
      expect(gesture).to include('data.onCellLongPress?.invoke()')
      # Remaining events consumed so the inner onClick does not also fire
      expect(gesture).to include('it.consume()')
      expect(imports).to include(:long_press_gesture)
    end

    it 'returns no modifiers without onLongPress' do
      result = described_class.build_long_pressable({ 'onClick' => '@{onTap}' }, Set.new)
      expect(result).to be_empty
    end

    it 'resolves binding handlers with viewId argument via data definitions' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onRowLongPress' => { 'class' => '((String) -> Unit)?' }
      }
      json_data = { 'id' => 'row_item', 'onLongPress' => '@{onRowLongPress}' }
      result = described_class.build_long_pressable(json_data, Set.new)
      expect(result.first).to include('data.onRowLongPress?.invoke("row_item")')
    end

    it 'resolves plain method-name handlers like camelCase onClick' do
      json_data = { 'onLongPress' => 'handleLongPress' }
      result = described_class.build_long_pressable(json_data, Set.new)
      expect(result.first).to include('data.handleLongPress?.invoke()')
    end
  end

  describe '.build_clickable with onLongPress' do
    before do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
    end

    it 'emits the long-press detector before .clickable so long press cancels click' do
      imports = Set.new
      json_data = { 'onClick' => '@{onTap}', 'onLongPress' => '@{onHold}' }
      result = described_class.build_clickable(json_data, imports)

      expect(result.length).to eq(2)
      expect(result.first).to include('.pointerInput(data) {')
      expect(result.first).to include('data.onHold?.invoke()')
      expect(result.last).to include('.clickable { data.onTap?.invoke() }')
      expect(imports).to include(:clickable)
      expect(imports).to include(:long_press_gesture)
    end

    it 'emits only the long-press detector when no onClick is present' do
      imports = Set.new
      json_data = { 'onLongPress' => '@{onHold}' }
      result = described_class.build_clickable(json_data, imports)

      expect(result.length).to eq(1)
      expect(result.first).to include('.pointerInput(data) {')
      expect(result.join).not_to include('.clickable')
      expect(imports).not_to include(:clickable)
    end

    it 'keeps plain .clickable output unchanged without onLongPress' do
      imports = Set.new
      json_data = { 'onClick' => '@{onTap}' }
      result = described_class.build_clickable(json_data, imports)
      expect(result).to eq(['.clickable { data.onTap?.invoke() }'])
    end
  end

  describe '.format with multi-line modifiers' do
    it 'indents every line of a single multi-line modifier' do
      gesture = ".pointerInput(data) {\n    awaitEachGesture {\n    }\n}"
      result = described_class.format([gesture], 0)
      lines = result.split("\n")
      expect(lines).to include('    modifier = Modifier')
      expect(lines).to include('        .pointerInput(data) {')
      expect(lines).to include('            awaitEachGesture {')
      expect(lines).to include('        }')
    end
  end
end

# `enabled` is declared boolean|binding on `common`, so it may appear on any
# node — and the Compose codegen read it on none of them: a View with
# `enabled: "@{x}"` stayed clickable.
RSpec.describe KjuiTools::Compose::Helpers::ModifierBuilder, 'enabled' do
  let(:required_imports) { Set.new }

  def clickable(extra)
    described_class.build_clickable(
      { 'type' => 'View', 'id' => 'w', 'onClick' => '@{tap}' }.merge(extra), required_imports
    ).join("\n")
  end

  it 'gates the click on a binding' do
    expect(clickable('enabled' => '@{isEnabled}'))
      .to include('.clickable(enabled = data.isEnabled) {')
  end

  it 'gates it on the literal false' do
    expect(clickable('enabled' => false)).to include('.clickable(enabled = false) {')
  end

  # true is the default and needs no gate.
  it 'leaves the click ungated for true or absent' do
    expect(clickable('enabled' => true)).to include('.clickable {')
    expect(clickable({})).to include('.clickable {')
  end

  # A click-gated node is still `enabled` in the a11y tree, and the a11y tree is
  # the only thing a UI test can observe (`assert: "disabled"` reads it).
  describe 'a11y' do
    it 'marks the node disabled, checking inside the semantics lambda' do
      expect(clickable('enabled' => '@{isEnabled}'))
        .to include('.semantics { if (!data.isEnabled) disabled() }')
      expect(required_imports).to include(:semantics_disabled)
    end

    it 'marks it unconditionally for the literal false' do
      expect(clickable('enabled' => false)).to include('.semantics { disabled() }')
    end

    it 'marks a node with no click handler too' do
      result = described_class.build_clickable(
        { 'type' => 'View', 'id' => 'w', 'enabled' => '@{isEnabled}' }, required_imports
      ).join("\n")
      expect(result).to include('disabled()')
      expect(result).not_to include('.clickable')
    end

    it 'adds nothing when enabled is absent' do
      expect(clickable({})).not_to include('disabled()')
    end
  end
end
