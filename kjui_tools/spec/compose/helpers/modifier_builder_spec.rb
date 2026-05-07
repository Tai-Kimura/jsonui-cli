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

    it 'builds aspect ratio' do
      json_data = { 'aspectWidth' => 16, 'aspectHeight' => 9 }
      result = described_class.build_size(json_data)
      ratio = 16.0 / 9.0
      expect(result).to include(".aspectRatio(#{ratio}f)")
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
end
