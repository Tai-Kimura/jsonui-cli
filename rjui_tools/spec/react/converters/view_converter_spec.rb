# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/view_converter'
require 'react/converters/select_box_converter'
require 'react/react_generator'
require 'json'
require 'open3'
require 'tmpdir'

RSpec.describe RjuiTools::React::Converters::ViewConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#build_class_name' do
    context 'with spacing' do
      it 'adds gap class for spacing (1rem -> gap-4)' do
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
        expect(classes).to include('gap-[1rem]')
      end

      it 'maps spacing to Tailwind gap values (0.5rem -> gap-2)' do
        converter = create_converter({
          'type' => 'View',
          'orientation' => 'vertical',
          'spacing' => 8,
          'child' => []
        })
        classes = converter.send(:build_class_name)
        # 8px maps to Tailwind gap-2
        expect(classes).to include('gap-[0.5rem]')
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
        expect(classes).to include('gap-[0.75rem]')
        expect(classes).not_to match(/justify-/)
      end

      it 'keeps the size half working underneath an explicit spacing' do
        node = {
          'type' => 'View', 'orientation' => 'horizontal', 'spacing' => 12,
          'distribution' => 'fill', 'child' => [{ 'type' => 'View', 'id' => 'a' }]
        }
        out = create_converter(node).convert_node(2)
        expect(out).to include('gap-[0.75rem]')
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
      # (The ticket this used to cite, `rjui-flex-grow-missing-min-w-0`, is not in
      # this tree — `docs/` is gitignored, so a cited path can outlive its file.
      # The mechanism above is the whole of it.)
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
      expect(attrs).to include('onContextMenu={(e) => { e.preventDefault(); data.handleLongPress?.(); }}')
    end

    it 'emits data-prefixed guarded handler for onLongPress selector format' do
      converter = create_converter({
        'type' => 'View',
        'onLongPress' => 'handleLongPress',
        'child' => []
      })
      attrs = converter.send(:build_event_attrs)
      expect(attrs).to include('data.handleLongPress?.()')
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

    # The axis a constraint does not name keeps the absolute child's static
    # position. In a block that was below the anchor (web y 170 where the
    # zstack default is y 0, frame-parity inventory 2026-10-05; ticket
    # rjui-relative-child-stacks-on-the-axis-it-does-not-align). A grid puts
    # an absolute child's static position at the content box's start.
    it 'is a grid without an orientation, so the free axis starts at the container default' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                                    'alignLeftView' => 'header' }])
      root = result.lines.first[/className="([^"]*)"/, 1].split
      expect(root).to include('grid', 'content-start')
    end

    it 'stays a flex container when an orientation is declared' do
      result = create_converter({
        'type' => 'View', 'orientation' => 'vertical',
        'child' => [header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                              'alignLeftView' => 'header' }]
      }).convert
      expect(result.lines.first[/className="([^"]*)"/, 1].split).not_to include('grid')
    end

    it 'leaves a plain overlay untouched' do
      result = container([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B' }])
      expect(result).not_to include('ref=')
      expect(result.lines.find { |l| l.include?('id="header"') }).to include('absolute inset-0')
    end
  end

  # A plain overlay sized wrapContent on an axis measured 0 on that axis on
  # web: every child was absolute, and an absolute child does not size its
  # container. It stacks the children in one grid cell instead, each placed
  # where its absolute counterpart sat (frame-parity inventory 2026-10-05;
  # rjui-wrapcontent-view-collapses-around-overlaid-children).
  describe 'an overlay sized from its children' do
    let(:box) { { 'type' => 'View', 'width' => 40, 'height' => 40 } }

    def overlay(size, children)
      create_converter({ 'type' => 'View', 'id' => 'target', 'child' => children }.merge(size)).convert
    end

    def line_of(result, id)
      result.lines.find { |l| l.include?("id=\"#{id}\"") }
    end

    %w[width height].each do |axis|
      it "stacks the children in one grid cell when #{axis} is wrapContent" do
        other = axis == 'width' ? 'height' : 'width'
        result = overlay({ axis => 'wrapContent', other => 200 },
                         [box.merge('id' => 'a'), box.merge('id' => 'b')])
        expect(line_of(result, 'target').split('"')[-2].split).to include('grid')
        %w[a b].each do |id|
          classes = line_of(result, id)[/className="([^"]*)"/, 1].split
          expect(classes).to include('col-start-1', 'row-start-1')
          expect(classes).not_to include('absolute')
        end
      end
    end

    it 'places each child where the absolute overlay placed it' do
      result = overlay({ 'width' => 'wrapContent', 'height' => 'wrapContent' }, [
                         box.merge('id' => 'sized'),
                         { 'type' => 'View', 'id' => 'fill' },
                         box.merge('id' => 'br', 'alignBottom' => true, 'alignRight' => true),
                         box.merge('id' => 'mid', 'centerInParent' => true),
                         box.merge('id' => 'bottom', 'alignBottom' => true)
                       ])
      expect(line_of(result, 'sized')).to include('self-start justify-self-start')
      expect(line_of(result, 'fill')).to include('self-stretch justify-self-stretch')
      expect(line_of(result, 'br')).to include('self-end [justify-self:right]')
      expect(line_of(result, 'mid')).to include('self-center justify-self-center')
      expect(line_of(result, 'bottom')).to include('self-end justify-self-start')
    end

    it 'keeps the absolute overlay when no axis is wrapContent' do
      result = overlay({ 'width' => 200, 'height' => 200 }, [box.merge('id' => 'a'), box.merge('id' => 'b')])
      expect(line_of(result, 'a')).to include('absolute')
      expect(line_of(result, 'target')).not_to include('grid')
    end
  end

  # A row's children start the cross axis unless a gravity says otherwise
  # (gravityDefaults: top|start on every container). The flex default,
  # `align-items: stretch`, drew a child without a height at the row's full
  # height on web only (frame-parity inventory 2026-10-05; ticket
  # rjui-stack-stretches-children-on-the-cross-axis).
  describe "a row's cross axis" do
    def row_classes(extra)
      create_converter({
        'type' => 'View', 'id' => 'row', 'width' => 300, 'height' => 200,
        'child' => [{ 'type' => 'Label', 'id' => 'b', 'text' => 'B' }]
      }.merge(extra)).convert.lines.first[/className="([^"]*)"/, 1].split
    end

    it 'starts at the top by default' do
      expect(row_classes('orientation' => 'horizontal')).to include('items-start')
    end

    it 'follows a gravity that names the vertical axis, with no second items-* class' do
      classes = row_classes('orientation' => 'horizontal', 'gravity' => 'centerVertical')
      expect(classes.grep(/\Aitems-/)).to eq(['items-center'])
    end

    it 'keeps the top when the gravity names only the horizontal axis' do
      expect(row_classes('orientation' => 'horizontal', 'gravity' => 'right')).to include('items-start', 'justify-end')
    end

    it 'gives way to a static centerInParent / centerHorizontal' do
      expect(row_classes('orientation' => 'horizontal', 'centerInParent' => true).grep(/\Aitems-/)).to eq(['items-center'])
      expect(row_classes('orientation' => 'horizontal', 'centerHorizontal' => true).grep(/\Aitems-/)).to eq(['items-center'])
    end

    it 'keeps the start under a bound centerInParent, whose inline style wins while true' do
      expect(row_classes('orientation' => 'horizontal', 'centerInParent' => '@{c}')).to include('items-start')
    end

    it 'leaves a column alone' do
      expect(row_classes('orientation' => 'vertical').grep(/\Aitems-/)).to be_empty
    end

    # A CheckBox or Radio with a label lays its own parts out as a row and
    # writes its own items-center after the base classes. A default start
    # beside it was a second items-* class, and stylesheet order let the start
    # win: the box moved off the label's centre line (CheckBox / Radio
    # spacing and orientation-horizontal fixtures, caught by the web
    # screenshots while this was being fixed).
    it 'is not added to a control that lays its own parts out as a row' do
      require 'react/converters/toggle_converter'
      require 'react/converters/radio_converter'
      node = { 'id' => 't', 'width' => 200, 'height' => 'wrapContent', 'text' => 'S',
               'orientation' => 'horizontal', 'spacing' => 16 }
      [RjuiTools::React::Converters::ToggleConverter.new(node.merge('type' => 'CheckBox'), default_config),
       RjuiTools::React::Converters::RadioConverter.new(node.merge('type' => 'Radio'), default_config)].each do |conv|
        classes = conv.convert_node(2).lines.first[/className="([^"]*)"/, 1].split
        expect(classes.grep(/\Aitems-/)).to eq(['items-center'])
      end
    end
  end

  # distribution's SIZE half (fill / fillEqually) yields to a size the child
  # declares on the distribution axis (attribute_semantics.json distribution
  # .explicitChildSizeWins). fillEqually's `flex-1` drew a width-60 child at
  # an equal 100 on web where Android draws 60 (frame-parity inventory
  # 2026-10-05; ticket rjui-fillequally-overrides-a-childs-declared-width).
  describe "a declared size inside a distribution's size half" do
    def child_classes(orientation, distribution, child)
      result = create_converter({
        'type' => 'View', 'id' => 'stack', 'width' => 300, 'height' => 200,
        'orientation' => orientation, 'distribution' => distribution,
        'child' => [child.merge('id' => 'c'), { 'type' => 'Label', 'id' => 'free', 'text' => 'F' }]
      }).convert
      [result.lines.find { |l| l.include?('id="c"') }, result.lines.find { |l| l.include?('id="free"') }]
        .map { |l| l[/className="([^"]*)"/, 1].split }
    end

    it 'keeps the declared width in a fillEqually row, while an undeclared sibling takes its share' do
      sized, free = child_classes('horizontal', 'fillEqually', { 'type' => 'View', 'width' => 60, 'height' => 40 })
      expect(sized).to include('w-[60px]', 'shrink-0')
      expect(sized).not_to include('flex-1')
      expect(free).to include('flex-1')
    end

    it 'does not grow a declared width in a fill row' do
      sized, free = child_classes('horizontal', 'fill', { 'type' => 'View', 'width' => 60, 'height' => 40 })
      expect(sized).not_to include('grow')
      expect(free).to include('grow')
    end

    it 'reads the axis from the parent: a column keeps a declared height, not a width' do
      by_height, = child_classes('vertical', 'fillEqually', { 'type' => 'View', 'width' => 60, 'height' => 40 })
      expect(by_height).not_to include('flex-1')
      by_width_only, = child_classes('vertical', 'fillEqually', { 'type' => 'View', 'width' => 60 })
      expect(by_width_only).to include('flex-1')
    end

    it 'treats a bound size on the axis as declared' do
      sized, = child_classes('horizontal', 'fillEqually', { 'type' => 'View', 'width' => '@{w}', 'height' => 40 })
      expect(sized).not_to include('flex-1')
    end
  end

  # A border is drawn over the content and does not push it inward (user
  # ruling B, 2026-10-05). A CSS border takes layout space: the children sat
  # at (2, 2) for borderWidth 2 and a Label drew 4 taller, on web only
  # (frame-parity inventory, 16 fixtures). The border is the element's
  # ::after, laid over the whole box — above the children (an inset
  # box-shadow paints under a child touching the edge, measured), along the
  # corner radius in every browser, dashed / dotted as declared. A replaced
  # element (<img>) falls back to an outline; a text input keeps a CSS border.
  describe 'a border over the content' do
    def first_classes(converter)
      converter.convert_node(2).lines.first[/className="([^"]*)"/, 1].split
    end

    let(:border) { { 'borderWidth' => 2, 'borderColor' => '#FF0000' } }

    it "draws a View's and a Label's border on ::after over the box, with no border or outline on the element" do
      require 'react/converters/label_converter'
      [create_converter({ 'type' => 'View', 'id' => 'v', 'width' => 200, 'height' => 200 }.merge(border)),
       RjuiTools::React::Converters::LabelConverter.new({ 'type' => 'Label', 'id' => 'l', 'text' => 'x' }.merge(border),
                                                        default_config)].each do |conv|
        classes = first_classes(conv)
        expect(classes).to include('after:absolute', 'after:inset-0', 'after:rounded-[inherit]', 'after:pointer-events-none',
                                   'after:border-[length:2px]', 'after:border-[#FF0000]', 'after:border-solid', 'relative')
        expect(classes.grep(/\A(border|outline)/)).to be_empty
      end
    end

    it 'keeps the declared style' do
      classes = first_classes(create_converter({ 'type' => 'View', 'id' => 'v', 'borderStyle' => 'dotted' }.merge(border)))
      expect(classes).to include('after:border-dotted')
      expect(classes).not_to include('after:border-solid')
    end

    it 'hands a bound width to the ::after through a custom property' do
      out = create_converter({ 'type' => 'View', 'id' => 'v', 'borderWidth' => '@{w}', 'borderColor' => '#FF0000' }).convert
      expect(out).to include("'--jui-border-width': `${data.w}px`", 'after:border-[length:var(--jui-border-width)]')
      expect(out).not_to include('borderWidth')
    end

    it 'does not add relative to an element that is absolutely positioned already' do
      result = create_converter({
        'type' => 'View', 'id' => 'overlay', 'width' => 200, 'height' => 200,
        'child' => [{ 'type' => 'View', 'id' => 'a', 'width' => 40, 'height' => 40 }.merge(border),
                    { 'type' => 'View', 'id' => 'b', 'width' => 40, 'height' => 40 }]
      }).convert
      a = result.lines.find { |l| l.include?('id="a"') }[/className="([^"]*)"/, 1].split
      expect(a).to include('absolute', 'after:border-[length:2px]')
      expect(a).not_to include('relative')
    end

    it 'falls back to an outline on an <img>, which has no ::after' do
      require 'react/converters/image_converter'
      classes = first_classes(RjuiTools::React::Converters::ImageConverter.new(
        { 'type' => 'Image', 'id' => 'i', 'srcName' => 'a', 'width' => 40, 'height' => 40 }.merge(border), default_config
      ))
      expect(classes).to include('outline-[length:2px]', 'outline-offset-[-2px]')
      expect(classes.grep(/\Aafter:/)).to be_empty
    end

    it 'leaves a text input its CSS border, whose outline is the focus ring' do
      require 'react/converters/text_field_converter'
      classes = first_classes(RjuiTools::React::Converters::TextFieldConverter.new(
        { 'type' => 'TextField', 'id' => 't', 'width' => 200, 'height' => 40 }.merge(border), default_config
      ))
      expect(classes).to include('border-2', 'outline-none')
      expect(classes.grep(/\A(after:|outline-\[)/)).to be_empty
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
      expect(all).to include('paddingInlineStart').and include('paddingInlineEnd')
      expect(styled('safeAreaInsetPositions' => ['vertical'])).to include('paddingBottom')
    end

    # leading / trailing are the start and end of the reading direction
    # (jsonui-cli 1.9.0). env() only exposes physical insets, so the logical
    # padding reads a custom property that a class sets per direction; the
    # `rtl:` form swaps the side. The render arm below draws both directions.
    it 'maps leading and trailing to the reading direction' do
      result = styled('safeAreaInsetPositions' => %w[leading trailing])
      expect(result).to include("paddingInlineStart: 'var(--jui-safe-start)'")
      expect(result).to include("paddingInlineEnd: 'var(--jui-safe-end)'")
      expect(result).to include('[--jui-safe-start:env(safe-area-inset-left)]')
      expect(result).to include('rtl:[--jui-safe-start:env(safe-area-inset-right)]')
      expect(result).to include('[--jui-safe-end:env(safe-area-inset-right)]')
      expect(result).to include('rtl:[--jui-safe-end:env(safe-area-inset-left)]')
      expect(result).not_to include('paddingLeft')
      expect(result).not_to include('paddingRight')
    end

    # An inline style beats the Tailwind class outright, so emitting the inset
    # alone would silently delete the padding the layout asked for.
    it "folds the element's own padding into a calc" do
      expect(styled('safeAreaInsetPositions' => ['top'], 'paddings' => [8, 4, 8, 4]))
        .to include("paddingTop: 'calc(0.5rem + env(safe-area-inset-top))'")
      expect(styled('safeAreaInsetPositions' => ['leading'], 'paddingStart' => 12))
        .to include('[--jui-safe-start:calc(0.75rem_+_env(safe-area-inset-left))]')
        .and include('rtl:[--jui-safe-start:calc(0.75rem_+_env(safe-area-inset-right))]')
      expect(styled('safeAreaInsetPositions' => ['top'], 'padding' => 6))
        .to include("paddingTop: 'calc(0.375rem + env(safe-area-inset-top))'")
    end

    # A physical padding stays on its side: in RTL the start is the right
    # side, so the right padding (not the left) is what the inset adds to.
    it "folds the padding of the side the start is on in each direction" do
      result = styled('safeAreaInsetPositions' => %w[leading trailing], 'paddings' => [0, 5, 0, 7])
      expect(result).to include('[--jui-safe-start:calc(0.4375rem_+_env(safe-area-inset-left))]')
      expect(result).to include('rtl:[--jui-safe-start:calc(0.3125rem_+_env(safe-area-inset-right))]')
      expect(result).to include('[--jui-safe-end:calc(0.3125rem_+_env(safe-area-inset-right))]')
      expect(result).to include('rtl:[--jui-safe-end:calc(0.4375rem_+_env(safe-area-inset-left))]')
    end

    it 'ignores an unknown edge and emits nothing when absent' do
      expect(styled('safeAreaInsetPositions' => ['sideways'])).not_to include('safe-area-inset')
      expect(styled({})).not_to include('safe-area-inset')
    end

    # Drawn: headless Chromium lays the emitted element out once under
    # dir="ltr" and once under dir="rtl", and reads the computed padding of
    # each physical side. A desktop browser's env(safe-area-inset-*) is 0, so
    # the arm stands px in for it — left 11, right 22 — in the stylesheet and
    # the inline style (the class names are left as emitted).
    #
    # The CSS for each class is what Tailwind v4 generates for it (compiled
    # with tailwindcss 4.3.3 and 4.2.2 on 2026-09-26): `[--p:v]` sets the
    # property; `rtl:` adds `:where(:dir(rtl), [dir="rtl"], [dir="rtl"] *)`,
    # which has no specificity, and Tailwind puts variant rules after the
    # plain ones — so the RTL value wins by order, as here.
    describe 'drawn in both reading directions' do
      STAND_IN = { 'left' => '11px', 'right' => '22px', 'top' => '33px', 'bottom' => '44px' }.freeze
      TAILWIND_PLAIN = { 'shrink-0' => 'flex-shrink:0', 'ps-[0.25rem]' => 'padding-inline-start:0.25rem',
                         'pe-[0.25rem]' => 'padding-inline-end:0.25rem' }.freeze

      def chromium
        HeadlessChromium.path
      end

      def stand_in(text)
        text.gsub(/env\(safe-area-inset-(\w+)\)/) { STAND_IN.fetch(Regexp.last_match(1)) }
      end

      def rule_for(klass)
        escaped = klass.gsub(/[\[\]:()+,.]/) { |ch| "\\#{ch}" }
        body = klass.sub(/\Artl:/, '')
        decl = if body =~ /\A\[(--[\w-]+):(.+)\]\z/
                 "#{Regexp.last_match(1)}: #{stand_in(Regexp.last_match(2).tr('_', ' '))}"
               elsif body =~ /\A([wh])-\[(\d+)px\]\z/
                 "#{Regexp.last_match(1) == 'w' ? 'width' : 'height'}: #{Regexp.last_match(2)}px"
               else
                 TAILWIND_PLAIN[body] or raise "no definition for #{klass}"
               end
        selector = klass.start_with?('rtl:') ? %(.#{escaped}:where(:dir(rtl), [dir="rtl"], [dir="rtl"] *)) : ".#{escaped}"
        "#{selector} { #{decl} }"
      end

      # { "ltr" => [left, right], "rtl" => [left, right] } computed padding in px.
      def paddings(jsx)
        esbuild = File.expand_path('../../support/node_modules/.bin/esbuild', __dir__)
        skip 'esbuild is not installed under spec/support' unless File.executable?(esbuild)
        HeadlessChromium.ensure!(self)

        classes = jsx.scan(/className="([^"]*)"/).flatten.flat_map(&:split).uniq
        plain, variant = classes.partition { |c| !c.start_with?('rtl:') }
        css = (plain + variant).map { |c| rule_for(c) }.join("\n")
        Dir.mktmpdir('rjui_safe_area_rtl') do |dir|
          File.write(File.join(dir, 'app.jsx'), <<~JSX)
            function h(tag, props, ...children) {
              const el = document.createElement(tag);
              for (const [k, v] of Object.entries(props || {})) {
                if (k === 'className') el.className = v;
                else if (k === 'style') for (const [p, x] of Object.entries(v)) el.style.setProperty(p.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()), x);
                else el.setAttribute(k, v);
              }
              for (const c of children.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
              return el;
            }
            const out = {};
            for (const dir of ['ltr', 'rtl']) {
              const holder = document.createElement('div');
              holder.setAttribute('dir', dir);
              const el = (#{jsx.strip.gsub(/style=\{\{.*?\}\}/m) { |style| stand_in(style) }});
              holder.append(el);
              document.body.append(holder);
              const cs = getComputedStyle(el);
              out[dir] = [parseFloat(cs.paddingLeft), parseFloat(cs.paddingRight)];
            }
            document.body.textContent = 'PAD' + JSON.stringify(out);
          JSX
          out, status = Open3.capture2e(esbuild, File.join(dir, 'app.jsx'), '--jsx-factory=h', '--outfile=' + File.join(dir, 'app.js'))
          raise "esbuild: #{out}" unless status.success?

          File.write(File.join(dir, 'page.html'),
                     "<html><head><style>body{margin:0} #{css}</style></head><body><script src=\"app.js\"></script></body></html>")
          dom, = Open3.capture2e(chromium, *HeadlessChromium::FLAGS, '--allow-file-access-from-files', '--dump-dom',
                                 "file://#{File.join(dir, 'page.html')}")
          JSON.parse(dom[/PAD(\{.*?\})</m, 1] || raise("no layout in:\n#{dom}\ncss:\n#{css}"))
        end
      end

      it 'puts leading on the left in LTR and on the right in RTL, with the start padding' do
        pad = paddings(styled('safeAreaInsetPositions' => ['leading'], 'paddingStart' => 4))
        expect(pad['ltr']).to eq([4 + 11, 0]), pad.inspect
        expect(pad['rtl']).to eq([0, 4 + 22]), pad.inspect
      end

      it 'puts trailing on the right in LTR and on the left in RTL' do
        pad = paddings(styled('safeAreaInsetPositions' => ['trailing']))
        expect(pad['ltr']).to eq([0, 22]), pad.inspect
        expect(pad['rtl']).to eq([11, 0]), pad.inspect
      end
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
        .to include('onClick={() => { if (data.isTappable) data.tap?.(); }}')
    end

    it 'leaves the handler alone for true or absent' do
      expect(view('canTap' => true)).to include('onClick={() => data.tap?.()}')
      expect(view({})).to include('onClick={() => data.tap?.()}')
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
require_relative '../../support/headless_chromium'

RSpec.describe 'pair-scan closure (web)' do
  let(:config) { { 'use_tailwind' => true } }

  def conv(klass, json)
    klass.new(json, config)
  end

  it 'Radio: label alias, spacing gap, single-radio checked' do
    r = conv(RjuiTools::React::Converters::RadioConverter,
             'type' => 'Radio', 'label' => 'Opt', 'spacing' => 12, 'checked' => true).convert
    expect(r).to include('Opt')
    expect(r).to include('gap-[0.75rem]')
    expect(r).to include('defaultChecked')
  end

  it 'CheckBox (ToggleConverter): spacing replaces the fixed gap' do
    r = conv(RjuiTools::React::Converters::ToggleConverter,
             'type' => 'CheckBox', 'label' => 'A', 'spacing' => 10).convert
    expect(r).to include('gap-[0.625rem]')
    expect(r).not_to include('gap-[0.5rem]')
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

  it 'Label: a hint swaps in for an empty text, with or without hintAttributes (user ruling 2026-10-05)' do
    hinted = conv(RjuiTools::React::Converters::LabelConverter,
                  'type' => 'Label', 'text' => '',
                  'hint' => 'Nothing here', 'hintColor' => '#999999',
                  'hintAttributes' => { 'fontSize' => 12 }).convert
    expect(hinted).to include('Nothing here')
    expect(hinted).to include("fontSize: '0.75rem'")
    expect(hinted).to include("color: '#999999'")

    # binding text: runtime emptiness ternary, one span per state
    bound = conv(RjuiTools::React::Converters::LabelConverter,
                 'type' => 'Label', 'text' => '@{title}',
                 'hint' => 'No title', 'hintAttributes' => { 'fontColor' => '#888888' }).convert
    expect(bound).to include('data.title) ? (')
    expect(bound).to include('No title')

    # hint without hintAttributes shows too, in the default subdued colour
    # (attribute_semantics labelHint; it used to show nothing, after UIKit
    # SJUILabel)
    bare = conv(RjuiTools::React::Converters::LabelConverter,
                'type' => 'Label', 'text' => '', 'hint' => 'X').convert
    expect(bare).to include('X</span>')
    expect(bare).to include("color: '#9CA3AF'")
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

  # Per edge, so it adds to a declared insets (collection_insets_additive_spec).
  it 'Collection: insetVertical becomes vertical content padding' do
    r = RjuiTools::React::Converters::CollectionConverter.new(
      { 'type' => 'Collection', 'insetVertical' => 16, 'items' => '@{rows}' }, config
    ).convert
    expect(r).to include('pt-[1rem] pb-[1rem]')
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

# tapBackground is the background while pressed, on every node with a click
# (onClick) and on a Button (jsonui-cli 1.9.0) — BaseConverter
# #pressed_background_classes. It was a View's alone, with a click or without
# one, falling back to highlightBackground (on a View, the colour while
# `highlighted` holds); a Label, an Image and the other clickable types drew
# nothing.
RSpec.describe RjuiTools::React::Converters::BaseConverter, 'tapBackground' do
  let(:config) { { 'use_tailwind' => true } }

  CLICKABLE = {
    'View' => { 'child' => [] }, 'Label' => { 'text' => 'x' }, 'Image' => { 'srcName' => 'x' },
    'NetworkImage' => { 'url' => 'https://e/x.png' }, 'IconLabel' => { 'text' => 'i' },
    'CircleView' => {}, 'GradientView' => { 'items' => %w[#FFFFFF #000000] }, 'Blur' => {}
  }.freeze

  def classes_of(type, extra)
    node = { 'type' => type }.merge(CLICKABLE.fetch(type)).merge(extra)
    klass = RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config).send(:get_converter_class, type)
    out = klass.new(node, config).convert(2)
    [out[/className="([^"]*)"/, 1].to_s.split, out]
  end

  it 'is the pressed background of every type with a click' do
    CLICKABLE.each_key do |type|
      classes, out = classes_of(type, 'onClick' => '@{t}', 'tapBackground' => '#FF0000')
      expect(classes).to include('active:bg-[#FF0000]', 'transition-colors'), "#{type}: #{out}"
    end
  end

  it 'draws nothing on a node without a click' do
    CLICKABLE.each_key do |type|
      classes, out = classes_of(type, 'tapBackground' => '#FF0000')
      expect(classes.grep(/\Aactive:/)).to be_empty, "#{type}: #{out}"
    end
    classes, = classes_of('View', 'onClick' => '@{t}', 'canTap' => false, 'tapBackground' => '#FF0000')
    expect(classes.grep(/\Aactive:/)).to be_empty
  end

  # On a View, highlightBackground is the colour while `highlighted` holds —
  # not the pressed one (a Button's highlightBackground is, ButtonConverter).
  it "does not take a View's highlightBackground as the pressed colour" do
    classes, = classes_of('View', 'onClick' => '@{t}', 'highlightBackground' => '#00FF00')
    expect(classes.grep(/\Aactive:/)).to be_empty
    _, out = classes_of('View', 'highlighted' => true, 'highlightBackground' => '#00FF00')
    expect(out).to include('#00FF00')
  end

  it 'reads a bound tapBackground back through the custom property' do
    classes, out = classes_of('Label', 'onClick' => '@{t}', 'tapBackground' => '@{tb}')
    expect(classes).to include('active:bg-[var(--jui-tap-bg)]')
    expect(out).to include("'--jui-tap-bg'")
  end
end
