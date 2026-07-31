# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/select_box_converter'

RSpec.describe RjuiTools::React::Converters::ViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#build_class_name' do
    context 'with spacing' do
      it 'adds gap class for spacing (16px -> gap-4)' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'spacing' => 16,
          'child' => [
            { 'type' => 'Label', 'text' => 'A' }
          ]
        })
        classes = converter.send(:build_class_name)
        # 16px maps to Tailwind gap-4
        expect(classes).to include('gap-4')
      end

      it 'maps spacing to Tailwind gap values (8px -> gap-2)' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'spacing' => 8,
          'child' => []
        })
        classes = converter.send(:build_class_name)
        # 8px maps to Tailwind gap-2
        expect(classes).to include('gap-2')
      end
    end

    context 'with distribution' do
      it 'adds justify-between for fill distribution' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'distribution' => 'fill',
          'child' => []
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('justify-between')
      end

      it 'adds justify-evenly for fillEqually distribution' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'distribution' => 'fillEqually',
          'child' => []
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('justify-evenly')
      end

      it 'adds justify-around for equalSpacing distribution' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'distribution' => 'equalSpacing',
          'child' => []
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('justify-around')
      end

      it 'adds justify-evenly for equalCentering distribution' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'distribution' => 'equalCentering',
          'child' => []
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('justify-evenly')
      end
    end

    context 'with spacing and distribution combined' do
      it 'applies both spacing and distribution classes' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'horizontal',
          'spacing' => 12,
          'distribution' => 'equalSpacing',
          'child' => []
        })
        classes = converter.send(:build_class_name)
        # 12px maps to Tailwind gap-3
        expect(classes).to include('gap-3')
        expect(classes).to include('justify-around')
      end
    end
  end

  describe 'cross-axis matchParent (parent orientation propagation)' do
    # Reported bug: a fixed-width accent bar (width: 3, height: matchParent)
    # inside a horizontal View got `flex-1` appended by base_converter's
    # height handling, which in a flex-row parent grows the MAIN (horizontal)
    # axis — hijacking width from the sibling content column. The fix:
    # propagate parent orientation to children so `height: matchParent` in a
    # flex-row parent emits `self-stretch` (cross-axis) instead of `flex-1`
    # (main-axis).
    it 'emits self-stretch (not flex-1) for height:matchParent child of a horizontal View' do
      converter = create_converter({
        'type' => 'View',
        'orientation' => 'horizontal',
        'width' => 'matchParent',
        'height' => 'wrapContent',
        'child' => [
          { 'type' => 'View', 'width' => 3, 'height' => 'matchParent', 'background' => '#DC2626' },
          { 'type' => 'View', 'weight' => 1, 'child' => [] }
        ]
      })
      jsx = converter.convert(2)
      # The accent bar (first child, 3px wide) should NOT grow horizontally.
      expect(jsx).to include('self-stretch')
      # Specifically, the fixed-width bar's class string should contain
      # `w-[3px]` AND `self-stretch` AND `shrink-0` — and NOT `flex-1`, which
      # was the old buggy output.
      bar_line = jsx.lines.find { |l| l.include?('w-[3px]') }
      expect(bar_line).not_to be_nil
      expect(bar_line).to include('self-stretch')
      expect(bar_line).not_to include('flex-1')
    end

    it 'still emits flex-1 for height:matchParent child of a vertical View (main-axis fill)' do
      converter = create_converter({
        'type' => 'View',
        'orientation' => 'vertical',
        'width' => 'matchParent',
        'height' => 'matchParent',
        'child' => [
          { 'type' => 'View', 'width' => 'matchParent', 'height' => 'matchParent', 'background' => '#CCCCCC' }
        ]
      })
      jsx = converter.convert(2)
      # flex-col parent: height matchParent is still a main-axis instruction,
      # so the child correctly flex-grows to fill vertical space.
      expect(jsx).to include('flex-1')
    end

    it 'falls back to flex-1 when parent orientation is unknown (root layout)' do
      # Root-level View has no injected _parent_orientation — keep the
      # historical flex-1 behavior so we don't regress root-level layouts
      # that relied on it.
      converter = create_converter({
        'type' => 'View', 'height' => 'matchParent', 'child' => []
      })
      classes = converter.send(:build_class_name)
      expect(classes).to include('flex-1')
    end

    it 'pairs flex-1 with min-w-0 min-h-0 for height matchParent' do
      # Prevents long descendants (long <pre>, prose) from pushing the
      # flex container past its weight slice via `min-*-size: auto`.
      # See docs/bugs/rjui-flex-grow-missing-min-w-0.md.
      converter = create_converter({
        'type' => 'View', 'height' => 'matchParent', 'child' => []
      })
      classes = converter.send(:build_class_name)
      expect(classes).to include('flex-1')
      expect(classes).to include('min-w-0')
      expect(classes).to include('min-h-0')
    end
  end

  describe '#build_event_attrs gesture handlers' do
    it 'emits data-prefixed guarded handler for onLongPress binding format' do
      converter = create_converter({
        'type' => 'View',
        'onLongPress' => '@{handleLongPress}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('onContextMenu={(e) => { e.preventDefault(); data.handleLongPress?.(e); }}')
    end

    it 'emits data-prefixed guarded handler for onLongPress selector format' do
      converter = create_converter({
        'type' => 'View',
        'onLongPress' => 'handleLongPress',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('data.handleLongPress?.(e)')
    end

    # Canonical contract: the bound value is a FUNCTION, not an
    # {onStart,onMove,onEnd} object (the pre-2026-07 emit expected one;
    # nothing declared or used that shape and it contradicted the SSoT).
    it 'calls the onPan handler on pressed pointer moves only' do
      converter = create_converter({
        'type' => 'View',
        'onPan' => '@{panHandler}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('onPointerMove={(e) => { if (e.buttons !== 0) data.panHandler?.(e); }}')
      expect(attrs).not_to include('onStart')
      expect(attrs).not_to include('onPointerDown')
    end

    it 'calls the onPinch handler on multi-touch moves only' do
      converter = create_converter({
        'type' => 'View',
        'onPinch' => '@{pinchHandler}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('onTouchMove={(e) => { if (e.touches.length >= 2) data.pinchHandler?.(e); }}')
      expect(attrs).not_to include('onTouchStart')
    end

    it 'suppresses native touch handling with touch-none for pan/pinch nodes' do
      with_pan = create_converter({ 'type' => 'View', 'onPan' => '@{panHandler}', 'child' => [] })
      expect(with_pan.convert).to include('touch-none')

      without = create_converter({ 'type' => 'View', 'child' => [] })
      expect(without.convert).not_to include('touch-none')
    end

    it 'never emits a bare (un-prefixed) gesture handler identifier' do
      converter = create_converter({
        'type' => 'View',
        'onLongPress' => '@{handleLongPress}',
        'onPan' => '@{panHandler}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).not_to include(' handleLongPress(e)')
      expect(attrs).not_to match(/[^.]\bpanHandler\?\./)
    end
  end

  # align*OfView / align*View: CSS cannot express a sibling-relative offset
  # statically, so the element side is `position: absolute` plus a ref, and the
  # hoisted effect writes the measured offsets.
  describe 'sibling-relative positioning' do
    let(:header) { { 'type' => 'Label', 'id' => 'header', 'text' => 'Header' } }

    def container(children)
      create_converter({ 'type' => 'View', 'child' => children }).convert
    end

    it 'becomes the containing block and takes the ref' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                                    'alignBottomOfView' => 'header' }])
      expect(result).to include('ref={bodyRelRef}')
      expect(result).to include('relative')
    end

    it 'is the containing block even when an orientation already made it flex' do
      result = create_converter({
        'type' => 'View', 'orientation' => 'vertical',
        'child' => [header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                              'alignLeftView' => 'header' }]
      }).convert
      expect(result).to include('relative')
      expect(result).to include('ref={bodyRelRef}')
    end

    it 'absolutely positions the constrained child only' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                                    'alignBottomOfView' => 'header' }])
      body = result.lines.find { |l| l.include?('id="body"') }
      anchor = result.lines.find { |l| l.include?('id="header"') }
      expect(body).to include('absolute')
      # The anchor stays in the flow: `inset-0` would stretch it across the
      # container and make every constraint pointing at it meaningless.
      expect(anchor).not_to include('absolute')
      expect(anchor).not_to include('inset-0')
    end

    # The inline style owns a constrained axis; a class must not fight it.
    it 'emits no offset class for a sibling-constrained axis' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                                    'alignBottomOfView' => 'header', 'alignTop' => true }])
      body = result.lines.find { |l| l.include?('id="body"') }
      expect(body).not_to include('inset-0')
      expect(body).not_to include('top-0')
    end

    it 'still honours parent alignment on the unconstrained axis' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                                    'alignBottomOfView' => 'header', 'alignRight' => true }])
      body = result.lines.find { |l| l.include?('id="body"') }
      expect(body).to include('right-0')
    end

    it 'leaves a plain overlay untouched' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B' }])
      expect(result).not_to include('ref=')
      expect(result.lines.find { |l| l.include?('id="header"') }).to include('absolute inset-0')
    end
  end

  # safeAreaInsetPositions — which edges reserve the safe area. On web that is
  # `env(safe-area-inset-*)` padding: the notch, the home indicator, a rounded
  # display's corners.
  describe 'safeAreaInsetPositions' do
    def styled(extra)
      create_converter({ 'type' => 'SafeAreaView', 'width' => 10, 'height' => 10 }.merge(extra)).convert
    end

    it 'pads the named edges' do
      result = styled('safeAreaInsetPositions' => %w[top bottom])
      expect(result).to include("paddingTop: 'env(safe-area-inset-top)'")
      expect(result).to include("paddingBottom: 'env(safe-area-inset-bottom)'")
      expect(result).not_to include('paddingLeft')
    end

    it 'expands all and vertical' do
      all = styled('safeAreaInsetPositions' => ['all'])
      expect(all).to include('paddingTop').and include('paddingBottom')
      expect(all).to include('paddingLeft').and include('paddingRight')
      expect(styled('safeAreaInsetPositions' => ['vertical'])).to include('paddingBottom')
    end

    # leading/trailing are logical names, but env() only exposes physical
    # insets and this codebase is LTR throughout.
    it 'maps leading and trailing to the physical sides' do
      result = styled('safeAreaInsetPositions' => %w[leading trailing])
      expect(result).to include("paddingLeft: 'env(safe-area-inset-left)'")
      expect(result).to include("paddingRight: 'env(safe-area-inset-right)'")
    end

    # An inline style beats the Tailwind class outright, so emitting the inset
    # alone would silently delete the padding the layout asked for.
    it "folds the element's own padding into a calc" do
      expect(styled('safeAreaInsetPositions' => ['top'], 'paddings' => [8, 4, 8, 4]))
        .to include("paddingTop: 'calc(8px + env(safe-area-inset-top))'")
      expect(styled('safeAreaInsetPositions' => ['leading'], 'paddingStart' => 12))
        .to include("paddingLeft: 'calc(12px + env(safe-area-inset-left))'")
      expect(styled('safeAreaInsetPositions' => ['top'], 'padding' => 6))
        .to include("paddingTop: 'calc(6px + env(safe-area-inset-top))'")
    end

    it 'ignores an unknown edge and emits nothing when absent' do
      expect(styled('safeAreaInsetPositions' => ['sideways'])).not_to include('safe-area-inset')
      expect(styled({})).not_to include('safe-area-inset')
    end
  end
end

# `enabled` is declared boolean|binding on `common`. The literal false was a
# plain class; the binding form was read nowhere, so a layout that wrote
# `enabled: "@{x}"` rendered a fully interactive node.
RSpec.describe RjuiTools::React::Converters::ViewConverter, 'enabled' do
  let(:config) { { 'use_tailwind' => true } }

  def view(value)
    json = { 'type' => 'View', 'width' => 10, 'height' => 10, 'onClick' => '@{tap}' }
    json['enabled'] = value unless value == :absent
    described_class.new(json, config).convert(2)
  end

  # The expression must stay out of the class list: finalize_classes splits on
  # whitespace and would tear it apart, and a plain className="…" renders a
  # `${...}` as literal text.
  it 'dims and blocks pointer events through the class template literal' do
    result = view('@{isEnabled}')
    expect(result).to include("className={`")
    expect(result).to include("${!data.isEnabled ? 'opacity-50 pointer-events-none' : ''}")
  end

  # A dimmed, click-through node is still `enabled` in the a11y tree, and the
  # a11y tree is the only thing a UI test can observe.
  it 'reports the state to the a11y tree' do
    expect(view('@{isEnabled}')).to include('aria-disabled={!data.isEnabled}')
    expect(view(false)).to include('aria-disabled="true"')
  end

  it 'keeps the static classes for the literal false' do
    result = view(false)
    expect(result).to include('opacity-50')
    expect(result).to include('pointer-events-none')
    expect(result).to include('className="')
  end

  it 'emits nothing for true or absent' do
    expect(view(true)).not_to include('aria-disabled')
    expect(view(:absent)).not_to include('aria-disabled')
    expect(view(:absent)).not_to include('opacity-50')
  end
end

# The SelectBox binding form pushed a `${...}` into the class list, which
# finalize_classes split on whitespace; with no value binding to make the
# className a template literal, React rendered the expression as literal text.
RSpec.describe RjuiTools::React::Converters::SelectBoxConverter, 'enabled binding' do
  let(:config) { { 'use_tailwind' => true } }

  def select(extra)
    RjuiTools::React::Converters::SelectBoxConverter.new(
      { 'class' => 'SelectBox', 'items' => %w[a] }.merge(extra), config
    ).convert(2)
  end

  it 'puts the expression in a template literal even with no value binding' do
    result = select('enabled' => '@{isEnabled}')
    expect(result).to include('className={`')
    expect(result).to include("${!data.isEnabled ? 'opacity-50 cursor-not-allowed' : ''}")
  end

  it 'keeps both expressions when a value binding is also present' do
    result = select('enabled' => '@{isEnabled}', 'selectedValue' => '@{v}')
    expect(result).to include('className={`')
    expect(result.scan('${').length).to eq(2)
  end

  # The functional half was never affected.
  it 'still emits the real disabled attribute' do
    expect(select('enabled' => '@{isEnabled}')).to include('disabled={!data.isEnabled}')
  end

  it 'leaves a plain select with a quoted className' do
    expect(select({})).to include('className="')
  end
end

# canTap gates the TAP; userInteractionEnabled blocks the whole subtree. Both
# are declared boolean|binding on `common`, and web read only the literal
# `userInteractionEnabled: false`.
RSpec.describe RjuiTools::React::Converters::ViewConverter, 'touch gating' do
  let(:config) { { 'use_tailwind' => true } }

  def view(extra)
    described_class.new(
      { 'type' => 'View', 'width' => 10, 'height' => 10, 'onClick' => '@{tap}' }.merge(extra), config
    ).convert(2)
  end

  describe 'canTap' do
    # A child of a non-tappable view is still tappable — this is not
    # pointer-events. UIKit's SJUIView.canTap gates the recogniser the same way.
    it 'drops the handler for the literal false' do
      result = view('canTap' => false)
      expect(result).not_to include('onClick')
      expect(result).not_to include('pointer-events-none')
    end

    it 'gates the handler on a binding' do
      expect(view('canTap' => '@{isTappable}'))
        .to include('onClick={(e) => { if (data.isTappable) data.tap?.(e); }}')
    end

    it 'leaves the handler alone for true or absent' do
      expect(view('canTap' => true)).to include('onClick={data.tap}')
      expect(view({})).to include('onClick={data.tap}')
    end
  end

  describe 'userInteractionEnabled' do
    it 'blocks pointer events on a binding' do
      expect(view('userInteractionEnabled' => '@{isInteractive}'))
        .to include("${!data.isInteractive ? 'pointer-events-none' : ''}")
    end

    # Unlike `enabled` this is not a visual state, so it does not dim.
    it 'does not dim' do
      expect(view('userInteractionEnabled' => '@{isInteractive}')).not_to include('opacity-50')
    end

    it 'keeps the static class for the literal false' do
      expect(view('userInteractionEnabled' => false)).to include('pointer-events-none')
    end

    it 'emits nothing for true or absent' do
      expect(view('userInteractionEnabled' => true)).not_to include('pointer-events-none')
      expect(view({})).not_to include('pointer-events-none')
    end
  end
end
