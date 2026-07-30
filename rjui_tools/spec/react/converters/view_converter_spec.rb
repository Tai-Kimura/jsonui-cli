# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'

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

    it 'emits data-prefixed pointer handlers for onPan' do
      converter = create_converter({
        'type' => 'View',
        'onPan' => '@{panHandler}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('onPointerDown={(e) => data.panHandler?.onStart?.(e)}')
      expect(attrs).to include('onPointerMove={(e) => data.panHandler?.onMove?.(e)}')
      expect(attrs).to include('onPointerUp={(e) => data.panHandler?.onEnd?.(e)}')
    end

    it 'emits data-prefixed touch handlers for onPinch' do
      converter = create_converter({
        'type' => 'View',
        'onPinch' => '@{pinchHandler}',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('onTouchStart={(e) => data.pinchHandler?.onStart?.(e)}')
      expect(attrs).to include('onTouchEnd={(e) => data.pinchHandler?.onEnd?.(e)}')
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
end
