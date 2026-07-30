# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/scroll_view_converter'

RSpec.describe RjuiTools::React::Converters::ScrollViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#build_class_name' do
    context 'with vertical scroll (default)' do
      it 'includes overflow-y-auto' do
        converter = create_converter({
          'type' => 'ScrollView'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-y-auto')
      end

      it 'includes flex flex-col' do
        converter = create_converter({
          'type' => 'ScrollView'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('flex')
        expect(classes).to include('flex-col')
      end
    end

    context 'with horizontal scroll' do
      it 'includes overflow-x-auto for horizontalScroll' do
        converter = create_converter({
          'type' => 'ScrollView',
          'horizontalScroll' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-x-auto')
      end

      it 'includes overflow-x-auto for orientation horizontal' do
        converter = create_converter({
          'type' => 'ScrollView',
          'orientation' => 'horizontal'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-x-auto')
      end

      it 'includes flex flex-row' do
        converter = create_converter({
          'type' => 'ScrollView',
          'horizontalScroll' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('flex')
        expect(classes).to include('flex-row')
      end
    end

    context 'with hidden scrollbar' do
      it 'adds scrollbar-hide for showsHorizontalScrollIndicator false' do
        converter = create_converter({
          'type' => 'ScrollView',
          'showsHorizontalScrollIndicator' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('scrollbar-hide')
      end

      it 'adds scrollbar-hide for showsVerticalScrollIndicator false' do
        converter = create_converter({
          'type' => 'ScrollView',
          'showsVerticalScrollIndicator' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('scrollbar-hide')
      end
    end

    context 'with paging' do
      it 'adds snap classes for vertical paging' do
        converter = create_converter({
          'type' => 'ScrollView',
          'paging' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('snap-y')
        expect(classes).to include('snap-mandatory')
      end

      it 'adds snap classes for horizontal paging' do
        converter = create_converter({
          'type' => 'ScrollView',
          'horizontalScroll' => true,
          'paging' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('snap-x')
        expect(classes).to include('snap-mandatory')
      end
    end

    context 'with scrollEnabled false' do
      it 'adds overflow-hidden and removes overflow-auto' do
        converter = create_converter({
          'type' => 'ScrollView',
          'scrollEnabled' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-hidden')
        expect(classes).not_to include('overflow-y-auto')
        expect(classes).not_to include('overflow-x-auto')
      end
    end

    context 'with bounces false' do
      it 'adds overscroll-none' do
        converter = create_converter({
          'type' => 'ScrollView',
          'bounces' => false
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overscroll-none')
      end
    end

    context 'with contentInsetAdjustmentBehavior never' do
      it 'adds scroll-p-0' do
        converter = create_converter({
          'type' => 'ScrollView',
          'contentInsetAdjustmentBehavior' => 'never'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('scroll-p-0')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with contentInset single value' do
      it 'adds padding style' do
        converter = create_converter({
          'type' => 'ScrollView',
          'contentInset' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '16px'")
      end
    end

    context 'with contentInset array' do
      it 'handles 2-element array' do
        converter = create_converter({
          'type' => 'ScrollView',
          'contentInset' => [10, 20]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px'")
      end

      it 'handles 4-element array' do
        converter = create_converter({
          'type' => 'ScrollView',
          'contentInset' => [10, 20, 30, 40]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end
    end

    context 'with contentInset hash' do
      it 'converts hash to padding' do
        converter = create_converter({
          'type' => 'ScrollView',
          'contentInset' => { 'top' => 10, 'right' => 20, 'bottom' => 30, 'left' => 40 }
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end
    end

    context 'with maxZoom' do
      it 'adds touchAction for pinch zoom' do
        converter = create_converter({
          'type' => 'ScrollView',
          'maxZoom' => 3.0
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("touchAction: 'pan-x pan-y pinch-zoom'")
      end
    end
  end

  describe 'scrollMode (inner vs window)' do
    # Reported bug: default `overflow-y-auto` emission establishes a
    # position:sticky anchor on a div that never actually scrolls when
    # ancestors are flex-auto, breaking sticky descendants (right-rail
    # TOC on doc pages). Opt-out via `scrollMode: "window"`.

    context 'with default scrollMode (inner)' do
      it 'keeps overflow-y-auto on vertical scroll (backward-compat)' do
        converter = create_converter({ 'type' => 'ScrollView' })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-y-auto')
      end

      it 'keeps overflow-x-auto on horizontal scroll (backward-compat)' do
        converter = create_converter({
          'type' => 'ScrollView', 'orientation' => 'horizontal'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('overflow-x-auto')
      end
    end

    context 'with scrollMode: "window"' do
      it 'skips overflow-y-auto on vertical scroll' do
        converter = create_converter({
          'type' => 'ScrollView', 'scrollMode' => 'window'
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('overflow-y-auto')
      end

      it 'skips overflow-x-auto on horizontal scroll' do
        converter = create_converter({
          'type' => 'ScrollView',
          'orientation' => 'horizontal',
          'scrollMode' => 'window'
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('overflow-x-auto')
      end

      it 'still emits flex direction classes (structure unchanged)' do
        converter = create_converter({
          'type' => 'ScrollView', 'scrollMode' => 'window'
        })
        classes = converter.send(:build_class_name)
        # flex-col is emitted when `orientation` is not explicitly set,
        # regardless of scrollMode — the node still acts as a layout div.
        expect(classes).to include('flex')
        expect(classes).to include('flex-col')
      end

      it 'does not emit snap-y/snap-mandatory even when paging is set' do
        # Snap only makes sense when the element itself scrolls, so
        # window-mode + paging is a no-op (no Tailwind snap classes).
        converter = create_converter({
          'type' => 'ScrollView',
          'paging' => true,
          'scrollMode' => 'window'
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('snap-y')
        expect(classes).not_to include('snap-mandatory')
      end

      it 'does not emit overflow-hidden when scrollEnabled is false' do
        # In window mode, there is no inner scroll to disable, and emitting
        # overflow-hidden would actively clip descendants (e.g. a sticky
        # nav poking into a parent column).
        converter = create_converter({
          'type' => 'ScrollView',
          'scrollEnabled' => false,
          'scrollMode' => 'window'
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('overflow-hidden')
      end
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'ScrollView',
        'testId' => 'main-scroll'
      })
      result = converter.convert
      expect(result).to include('data-testid="main-scroll"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'ScrollView',
        'tag' => 'content-area'
      })
      result = converter.convert
      expect(result).to include('data-tag="content-area"')
    end
  end
  # Declared `platform: react` — it exists for the web, and maps onto the CSS
  # property of the same name.
  describe 'scrollBehavior' do
    it 'emits the CSS property for each declared value' do
      %w[auto smooth].each do |value|
        result = create_converter({ 'type' => 'ScrollView', 'scrollBehavior' => value }).convert
        expect(result).to include("scrollBehavior: '#{value}'")
      end
    end

    it 'ignores a value outside the declared enum' do
      result = create_converter({ 'type' => 'ScrollView', 'scrollBehavior' => 'instant' }).convert
      expect(result).not_to include('scrollBehavior')
    end

    it 'emits nothing when absent' do
      result = create_converter({ 'type' => 'ScrollView' }).convert
      expect(result).not_to include('scrollBehavior')
    end
  end
end
