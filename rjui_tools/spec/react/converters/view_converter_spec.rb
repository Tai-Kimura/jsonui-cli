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

    # The canon (shared/core/attribute_semantics.json, semantics.distribution,
    # 2026-08-05 user-raised ruling) splits the four values into TWO KINDS:
    # fill / fillEqually distribute SIZE among the children, equalSpacing /
    # equalCentering distribute the FREE SPACE between them.
    #
    # These pins used to hold the opposite: `fill` -> justify-between, which
    # the ruling calls precisely backwards (fill means no free space is LEFT
    # to distribute), and fillEqually / equalCentering BOTH -> justify-evenly,
    # so no fixture comparing those two could tell them apart.
    context 'with distribution' do
      it 'keeps the size values off justify-content entirely' do
        %w[fill fillEqually].each do |value|
          converter = create_converter({
            'type' => 'View', 'orientation' => 'horizontal',
            'distribution' => value, 'child' => []
          })
          classes = converter.send(:build_class_name)
          expect(classes).not_to match(/justify-/), value
        end
      end

      it 'maps equalSpacing to justify-between — equal gaps, no outer gap' do
        converter = create_converter({
          'type' => 'View', 'orientation' => 'vertical',
          'distribution' => 'equalSpacing', 'child' => []
        })
        expect(converter.send(:build_class_name)).to include('justify-between')
      end

      it 'maps equalCentering to justify-around — equal centre-to-centre' do
        converter = create_converter({
          'type' => 'View', 'orientation' => 'horizontal',
          'distribution' => 'equalCentering', 'child' => []
        })
        expect(converter.send(:build_class_name)).to include('justify-around')
      end

      it 'gives the four values four distinct answers' do
        outputs = %w[fill fillEqually equalSpacing equalCentering].map do |value|
          create_converter({
            'type' => 'View', 'orientation' => 'horizontal', 'distribution' => value,
            'child' => [{ 'type' => 'View', 'id' => 'a' }, { 'type' => 'View', 'id' => 'b' }]
          }).convert_node(2)
        end
        expect(outputs.uniq.length).to eq(4), 'two declared values collapsed into one output'
      end

      it 'sends the size values to the CHILDREN as a flex instruction' do
        node = {
          'type' => 'View', 'orientation' => 'horizontal', 'distribution' => 'fill',
          'child' => [{ 'type' => 'View', 'id' => 'a' }, { 'type' => 'View', 'id' => 'b' }]
        }
        out = create_converter(node).convert_node(2)
        expect(out.scan(/id="[ab]"[^>]*\bgrow\b/).length).to eq(2)
      end

      it 'gives fillEqually the equal-size flex, not the grow-from-content one' do
        node = {
          'type' => 'View', 'orientation' => 'horizontal', 'distribution' => 'fillEqually',
          'child' => [{ 'type' => 'View', 'id' => 'a' }]
        }
        out = create_converter(node).convert_node(2)
        expect(out).to match(/id="a"[^>]*flex-1/)
      end

      it 'lets an explicit weight on a child win over the parent distribution' do
        node = {
          'type' => 'View', 'orientation' => 'horizontal', 'distribution' => 'fillEqually',
          'child' => [{ 'type' => 'View', 'id' => 'a', 'weight' => 2 }]
        }
        out = create_converter(node).convert_node(2)
        expect(out).to include('flex-[2]')
      end
    end

    context 'with spacing and distribution combined' do
      # The canon's spacingWins clause: an explicit `spacing` pins the GAP, so
      # it overrides the gap equalSpacing would compute. It says nothing about
      # size, so the SIZE values still apply underneath it.
      it 'lets spacing pin the gap and drops the gap-distributing justify' do
        converter = create_converter({
          'type' => 'View', 'orientation' => 'horizontal',
          'spacing' => 12, 'distribution' => 'equalSpacing', 'child' => []
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('gap-3')
        expect(classes).not_to match(/justify-/)
      end

      it 'keeps the size half working underneath an explicit spacing' do
        node = {
          'type' => 'View', 'orientation' => 'horizontal', 'spacing' => 12,
          'distribution' => 'fill', 'child' => [{ 'type' => 'View', 'id' => 'a' }]
        }
        out = create_converter(node).convert_node(2)
        expect(out).to include('gap-3')
        expect(out).to match(/id="a"[^>]*\bgrow\b/)
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

# 2026-07-31 pair-scan closure — web behaviours added when the component-
# aware coverage scan exposed 21 silently-dropped attributes.
require 'react/converters/radio_converter'
require 'react/converters/toggle_converter'
require 'react/converters/collection_converter'
require 'react/converters/icon_label_converter'
require 'react/converters/image_converter'
require 'react/converters/network_image_converter'
require 'react/converters/label_converter'
require 'react/converters/text_view_converter'
require 'react/converters/segment_converter'

RSpec.describe 'pair-scan closure (web)' do
  let(:config) { { 'use_tailwind' => true } }

  def conv(klass, json)
    klass.new(json, config)
  end

  it 'Radio: label alias, spacing gap, single-radio checked' do
    r = conv(RjuiTools::React::Converters::RadioConverter,
             'type' => 'Radio', 'label' => 'Opt', 'spacing' => 12, 'checked' => true).convert
    expect(r).to include('Opt')
    expect(r).to include('gap-[12px]')
    expect(r).to include('defaultChecked')
  end

  it 'CheckBox (ToggleConverter): spacing replaces the fixed gap' do
    r = conv(RjuiTools::React::Converters::ToggleConverter,
             'type' => 'CheckBox', 'label' => 'A', 'spacing' => 10).convert
    expect(r).to include('gap-[10px]')
    expect(r).not_to include('gap-2')
  end

  it 'Collection: horizontalScroll flips direction; indicators and inset map like ScrollView' do
    r = conv(RjuiTools::React::Converters::CollectionConverter,
             'type' => 'Collection', 'horizontalScroll' => true,
             'showsHorizontalScrollIndicator' => false,
             'contentInsetAdjustmentBehavior' => 'never',
             'items' => '@{rows}', 'child' => []).convert
    expect(r).to include('flex-row')
    expect(r).to include('scrollbar-hide')
    expect(r).to include('scroll-p-0')
  end

  it 'IconLabel: selectedFontColor statically and via a bound selected' do
    static = conv(RjuiTools::React::Converters::IconLabelConverter,
                  'type' => 'IconLabel', 'text' => 'T', 'selected' => true,
                  'selectedFontColor' => '#FF0000', 'icon' => 'star.png').convert
    expect(static).to include('text-[#FF0000]')

    bound = conv(RjuiTools::React::Converters::IconLabelConverter,
                 'type' => 'IconLabel', 'text' => 'T', 'selected' => '@{isOn}',
                 'selectedFontColor' => '#FF0000', 'icon_on' => 'a.png', 'icon_off' => 'b.png').convert
    expect(bound).to include("data.isOn ? '#FF0000'")
  end

  it 'Image and NetworkImage: native loading passthrough, canonical hint' do
    img = conv(RjuiTools::React::Converters::ImageConverter,
               'type' => 'Image', 'src' => 'a.png', 'loading' => 'lazy').convert
    expect(img).to include('loading="lazy"')

    net = conv(RjuiTools::React::Converters::NetworkImageConverter,
               'type' => 'NetworkImage', 'src' => 'https://x/y.png',
               'hint' => 'ph.png', 'loading' => 'eager').convert
    expect(net).to include('placeholder="ph.png"')
    expect(net).to include('loading="eager"')
  end

  it 'Label: styled hint swaps in for an empty text (canonical: both keys required)' do
    hinted = conv(RjuiTools::React::Converters::LabelConverter,
                  'type' => 'Label', 'text' => '',
                  'hint' => 'Nothing here', 'hintColor' => '#999999',
                  'hintAttributes' => { 'fontSize' => 12 }).convert
    expect(hinted).to include('Nothing here')
    expect(hinted).to include("fontSize: '12px'")
    expect(hinted).to include("color: '#999999'")

    # binding text: runtime emptiness ternary, one span per state
    bound = conv(RjuiTools::React::Converters::LabelConverter,
                 'type' => 'Label', 'text' => '@{title}',
                 'hint' => 'No title', 'hintAttributes' => { 'fontColor' => '#888888' }).convert
    expect(bound).to include('data.title) ? (')
    expect(bound).to include('No title')

    # hint without hintAttributes shows nothing (UIKit SJUILabel contract)
    bare = conv(RjuiTools::React::Converters::LabelConverter,
                'type' => 'Label', 'text' => '', 'hint' => 'X').convert
    expect(bare).not_to include('X</span>')
  end

  it 'TextView: input mode, enter key hint, truncation' do
    r = conv(RjuiTools::React::Converters::TextViewConverter,
             'type' => 'TextView', 'text' => '', 'input' => 'email',
             'returnKeyType' => 'Done', 'lineBreakMode' => 'Tail').convert
    expect(r).to include('inputMode="email"')
    expect(r).to include('enterKeyHint="done"')
    expect(r).to include("textOverflow: 'ellipsis'")
  end
end

# Group-2 backlog closure (2026-07-31): the implementable leftovers.
RSpec.describe 'backlog closure group 2 (web)' do
  let(:config) { { 'use_tailwind' => true } }

  it 'Label/IconLabel: canonical textShadow object maps to CSS text-shadow' do
    label = RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'text' => 'T',
        'textShadow' => { 'color' => '#000000', 'blur' => 4, 'offset' => [1, 2] } }, config
    ).convert
    expect(label).to include("textShadow: '1px 2px 4px #000000'")

    icon = RjuiTools::React::Converters::IconLabelConverter.new(
      { 'type' => 'IconLabel', 'text' => 'T', 'icon' => 'i.png',
        'textShadow' => { 'color' => 'dark_red', 'blur' => 2, 'offset' => [0, 1] } }, config
    ).convert
    expect(icon).to include("textShadow: '0px 1px 2px var(--color-dark_red)'")
  end

  it 'Collection: insetVertical becomes vertical content padding' do
    r = RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'insetVertical' => 16, 'items' => '@{rows}' }, config
    ).convert
    expect(r).to include('py-[16px]')
  end

  it 'common.indexAbove degrades to z 1, and an explicit zIndex wins' do
    above = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'indexAbove' => 'other', 'child' => [] }, config
    ).convert
    expect(above).to include('z-[1]')

    explicit = RjuiTools::React::Converters::ViewConverter.new(
      { 'type' => 'View', 'indexAbove' => 'other', 'zIndex' => 5, 'child' => [] }, config
    ).convert
    expect(explicit).not_to include('z-[1]')
  end

  it 'Segment: legacy valueChange selector calls the named method' do
    r = RjuiTools::React::Converters::SegmentConverter.new(
      { 'type' => 'Segment', 'items' => %w[A B], 'valueChange' => 'on_tab_change' }, config
    ).convert
    expect(r).to include('data.onTabChange')
  end
end
