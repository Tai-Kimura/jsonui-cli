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
end
