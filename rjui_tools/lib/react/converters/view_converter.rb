# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ViewConverter < BaseConverter
        def convert(indent = 2)
          @indent = indent
          class_name = build_class_name
          class_attr = build_responsive_class_attr(class_name)
          style_attr = build_style_attr_with_visibility
          children = convert_children(indent)
          id_attr = build_id_attr
          event_attrs = build_event_attrs
          rel_ref_attr = build_relative_position_ref_attr
          # A dimmed, click-through node is still `enabled` in the a11y tree, and
          # the a11y tree is the only thing a UI test can observe — `assert:
          # "disabled"` reads it. Without this the disable is invisible to tests.
          aria_disabled_attr = build_aria_disabled_attr

          jsx = if children.empty?
            "#{indent_str(indent)}<div#{id_attr}#{rel_ref_attr}#{class_attr}#{style_attr}#{aria_disabled_attr}#{event_attrs} />"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<div#{id_attr}#{rel_ref_attr}#{class_attr}#{style_attr}#{aria_disabled_attr}#{event_attrs}>
              #{children}
              #{indent_str(indent)}</div>
            JSX
          end

          # Wrap with visibility condition (for 'gone' type)
          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_style_attr_with_visibility
          apply_safe_area_insets
          build_style_attr
        end

        #: The physical edges. `leading` / `trailing` are the start and end of
        #: the reading direction (jsonui-cli 1.9.0), not left and right.
        SAFE_AREA_PHYSICAL = { 'top' => 'Top', 'bottom' => 'Bottom' }.freeze
        SAFE_AREA_EDGES = %w[top bottom leading trailing].freeze

        #: leading / trailing -> the logical padding, the custom property that
        #: carries its value, and the physical inset `env()` has for it in each
        #: reading direction. `env()` only exposes physical insets, so the
        #: direction is chosen by a class: its `rtl:` form swaps the side.
        SAFE_AREA_INLINE = {
          'leading' => { style: 'paddingInlineStart', var: '--jui-safe-start', ltr: 'left', rtl: 'right' },
          'trailing' => { style: 'paddingInlineEnd', var: '--jui-safe-end', ltr: 'right', rtl: 'left' }
        }.freeze

        # safeAreaInsetPositions — which edges reserve the safe area. On iOS the
        # SafeAreaView holds the inset; on Compose it is a windowInsetsPadding;
        # on web the equivalent is `env(safe-area-inset-*)` padding on the named
        # edges (the notch, the home indicator, a rounded display's corners).
        #
        # The author's own padding on that edge is folded into a calc() rather
        # than replaced: an inline style beats the Tailwind class outright, so
        # emitting the inset alone would silently delete the padding the layout
        # asked for.
        #
        # top / bottom are inline. leading / trailing are the inline-start /
        # inline-end padding, whose value is a custom property set by a class
        # per reading direction (safe_area_direction_classes): the inset of the
        # physical side that is the start (or end) there, plus the author's own
        # padding on that side.
        def apply_safe_area_insets
          edges = safe_area_edges
          return if edges.empty?

          @dynamic_styles ||= {}
          edges.each do |edge|
            if (inline = SAFE_AREA_INLINE[edge])
              @dynamic_styles[inline[:style]] = "'var(#{inline[:var]})'"
              next
            end

            side = SAFE_AREA_PHYSICAL[edge]
            @dynamic_styles["padding#{side}"] = "'#{inset_with_own(own_padding_px(edge.to_sym, :ltr), edge)}'"
          end
        end

        # `[--jui-safe-start:…] rtl:[--jui-safe-start:…]` for each of leading /
        # trailing that is reserved. Spaces are `_` inside a Tailwind arbitrary
        # value.
        def safe_area_direction_classes
          (safe_area_edges & SAFE_AREA_INLINE.keys).flat_map do |edge|
            inline = SAFE_AREA_INLINE[edge]
            %i[ltr rtl].map do |dir|
              side = inline[dir]
              value = inset_with_own(own_padding_px(side.to_sym, dir), side).tr(' ', '_')
              "#{dir == :rtl ? 'rtl:' : ''}[#{inline[:var]}:#{value}]"
            end
          end
        end

        def inset_with_own(own, side)
          inset = "env(safe-area-inset-#{side})"
          own.positive? ? "calc(#{format_px(own)}px + #{inset})" : inset
        end

        # 8.0px reads as a mistake; 8px does not.
        def format_px(value)
          value == value.to_i ? value.to_i.to_s : value.to_s
        end

        def safe_area_edges
          raw = attributes['safeAreaInsetPositions']
          return [] if raw.nil?

          named = (raw.is_a?(Array) ? raw : [raw]).map { |e| e.to_s }
          return SAFE_AREA_EDGES if named.include?('all')

          expanded = named.flat_map { |e| e == 'vertical' ? %w[top bottom] : [e] }
          expanded.uniq.select { |e| SAFE_AREA_EDGES.include?(e) }
        end

        # The padding this element already has on one PHYSICAL side (:top,
        # :right, :bottom, :left) in reading direction `dir`, in px. Mirrors the
        # attributes base_converter turns into padding classes; the logical
        # spelling is read first, as before — paddingStart is the left side's in
        # LTR and the right side's in RTL.
        def own_padding_px(side, dir)
          per_side = case side
                     when :top then attributes['topPadding'] || attributes['paddingTop']
                     when :bottom then attributes['bottomPadding'] || attributes['paddingBottom']
                     when :left then attributes['leftPadding'] || attributes['paddingLeft']
                     else attributes['rightPadding'] || attributes['paddingRight']
                     end
          start_side = dir == :rtl ? :right : :left
          logical = case side
                    when start_side then attributes['paddingStart']
                    when :left, :right then attributes['paddingEnd']
                    end
          per_side = logical || per_side
          return per_side.to_f if per_side.is_a?(Numeric)

          index = { top: 0, right: 1, bottom: 2, left: 3 }[side]
          all = attributes['padding'] || attributes['paddings']
          case all
          when Numeric then all.to_f
          when Array
            case all.length
            when 1 then all[0].to_f
            when 2 then (%i[top bottom].include?(side) ? all[0] : all[1]).to_f
            when 4 then all[index].to_f
            else 0.0
            end
          else 0.0
          end
        end

        def build_class_name
          classes = [super]

          # Root view with matchParent should fill its parent container (not viewport)
          if @indent == 2 && attributes['height'] == 'matchParent'
            classes << 'h-full'
          end

          # Layout mode for View with children
          if child_array.is_a?(Array)
            if attributes['orientation']
              # orientation specified - handled by base_converter's map_orientation
            elsif ui_children_count > 1
              # No orientation + multiple UI children = overlay (FrameLayout).
              # An element that is itself absolutely positioned is already a
              # containing block for its absolute descendants, and `absolute`
              # + `relative` on one element is a cascade coin-toss — both set
              # `position`, so the winner is decided by stylesheet order, not
              # class order (Tailwind emits `relative` last, which would undo
              # the absolute placement).
              classes << 'relative' unless json['_overlay']
            else
              # No orientation + single child = simple wrapper
              classes.unshift('flex flex-col')
            end
          end

          # A child positioned against a sibling needs this element to be the
          # containing block its inline offsets resolve against — including when
          # an orientation already made it a flex container, where the sibling
          # constraint is the reason the child leaves the flow at all.
          if relative_positioned_children? && !json['_overlay'] && !classes.include?('relative')
            classes << 'relative'
          end

          # Wrapping. Only meaningful on a flex container, which every View
          # with an orientation is.
          if attributes['flexWrap']
            wrap = TailwindMapper.map_flex_wrap(attributes['flexWrap'])
            classes << wrap unless wrap.empty?
          end

          # Center alignment. The container spelling of the same frozen family
          # BaseConverter fixes for the self-centering margins: a `"@{v}"`
          # string is truthy in Ruby, so the children were centered whatever
          # the binding resolved to.
          classes << 'items-center' if bound_flag_style('alignItems', attributes['centerHorizontal'], on: 'center')
          classes << 'justify-center' if bound_flag_style('justifyContent', attributes['centerVertical'], on: 'center')
          center_in_parent = attributes['centerInParent']
          if (center_expr = bound_value_expr(center_in_parent))
            dynamic_styles['alignItems']     = "#{center_expr} ? 'center' : undefined"
            dynamic_styles['justifyContent'] = "#{center_expr} ? 'center' : undefined"
          elsif center_in_parent
            classes << 'items-center justify-center'
          end

          # Gap/Spacing. A bound value fell through the PADDING_MAP lookup to
          # its own raw text and built `gap-@{v}`, a class that matches
          # nothing.
          spacing_value = bound_length_style('gap', attributes['spacing'])
          if spacing_value
            spacing = TailwindMapper::PADDING_MAP[spacing_value] || spacing_value
            classes << "gap-#{spacing}"
          end

          # Distribution. Only the GAP half is a justify-content — the SIZE
          # half (fill / fillEqually) is carried to the children as a flex
          # instruction (BaseConverter::DISTRIBUTION_CHILD_CLASS), because
          # `fill` means there is no free space left to distribute.
          #
          # An explicit `spacing` above pins the GAP, so it overrides what
          # equalSpacing / equalCentering would compute; it says nothing about
          # size, so the size values still apply underneath it (the canon's
          # spacingWins clause).
          distribution = JsonUIShared::EnumSpelling.lowered(attributes['distribution'], 'View', 'distribution').to_s
          if (justify = DISTRIBUTION_JUSTIFY[distribution]) && !attributes['spacing']
            classes << justify
          end

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if tap_handler?(attributes['onClick'], attributes['onclick'])
          # touch-action: none — without it the browser turns the touches into
          # scrolling/pinch-zoom before the element's pan/pinch handlers see them.
          classes << 'touch-none' if attributes['onPan'] || attributes['onPinch']

          # tapBackground (the background while pressed) is BaseConverter's,
          # for every node with a click (pressed_background_classes). This drew
          # it on a View with no click too, and fell back to highlightBackground
          # — on a View that is the colour while `highlighted` holds (below),
          # not while pressed.

          # Highlighted state (initial highlight).
          #
          # This used to APPEND a second `bg-*` to a class list that already
          # carried the base `background` — and Tailwind precedence comes from
          # the order rules appear in the stylesheet, not from the order they
          # appear in the attribute, so which colour won was arbitrary (the
          # same trap LabelConverter documents for two `text-*` classes). The
          # highlight is a state that REPLACES the base, so it goes to the
          # inline style, which beats any class deterministically.
          if attributes['highlighted']
            highlight_bg = attributes['highlightBackground'] || '#E5E7EB'
            dynamic_styles['backgroundColor'] = color_style_expr(highlight_bg)
          end

          # The reading-direction half of leading / trailing safe area
          # (apply_safe_area_insets reads the custom properties these set).
          classes.concat(safe_area_direction_classes)

          finalize_classes(classes)
        end

        def child_array
          json['child'] || json['children']
        end

        # Count UI children (excluding data-only elements)
        def ui_children_count
          arr = child_array
          return 0 unless arr.is_a?(Array)

          arr.count { |child| !data_only_element?(child) }
        end

        # No orientation + multiple UI children = overlay (FrameLayout)
        def overlay_layout?
          child_array.is_a?(Array) && ui_children_count > 1 && !attributes['orientation']
        end

        #: align*OfView / align*View / alignCenter*View on a child. MUST stay in
        #: sync with ReactGenerator#relative_constraint_for, which builds the
        #: spec the hoisted effect applies.
        RELATIVE_POSITION_ATTRS = %w[
          alignTopOfView alignBottomOfView alignLeftOfView alignRightOfView
          alignTopView alignBottomView alignLeftView alignRightView
          alignCenterVerticalView alignCenterHorizontalView
        ].freeze

        def relative_positioned?(child)
          return false unless child.is_a?(Hash)

          id = child['id']
          return false unless id.is_a?(String) && !id.empty? && !id.include?('@{')

          RELATIVE_POSITION_ATTRS.any? { |attr| child[attr] }
        end

        def relative_positioned_children?
          items = child_array.is_a?(Array) ? child_array : [child_array]
          items.any? { |child| relative_positioned?(child) }
        end

        # The ref the hoisted `applyRelativePositions` effect measures against.
        # Named after the first constrained child rather than the container: the
        # child is required to have a literal id (it is the anchor lookup key),
        # the container is not, and both sides derive the name the same way.
        # MUST stay in sync with ReactGenerator#relative_position_ref_name.
        def build_relative_position_ref_attr
          items = child_array.is_a?(Array) ? child_array : [child_array]
          first = items.find { |child| relative_positioned?(child) }
          return '' unless first

          " ref={#{snake_to_camel_id(first['id'])}RelRef}"
        end

        def convert_children(indent)
          if overlay_layout? || relative_positioned_children?
            items = child_array.is_a?(Array) ? child_array : [child_array]
            items.map do |child|
              next nil if data_only_element?(child)

              # Absolute positioning. In a plain overlay every child is
              # absolute, as before. Once a sibling constraint is in play only
              # the constrained children leave the flow: an unconstrained child
              # is there to be measured against, and the overlay default
              # (`inset-0`) would stretch it across the container and make every
              # constraint pointing at it meaningless.
              absolute = relative_positioned?(child) ||
                         (overlay_layout? && !relative_positioned_children?)
              child = child.merge('_overlay' => true) if absolute
              converter = create_converter_for_child(child)
              converter.convert_node(indent + 2)
            end.compact.join("\n")
          else
            super
          end
        end

        # Build all event handler attributes
        def build_event_attrs
          attrs = []

          # onClick
          attrs << build_onclick_attr

          # onLongPress (using onContextMenu as fallback, or custom
          # implementation), its handler called as the data declares it
          # (declared_tap_call) — it was handed the event whatever it took.
          if attributes['onLongPress']
            prop = resolve_handler_property(attributes['onLongPress'])
            attrs << " onContextMenu={(e) => { e.preventDefault(); #{declared_tap_call(prop)}; }}"
          end

          # onPan — the bound value is a function (canonical contract shared
          # with iOS/Android), invoked repeatedly while the user drags with the
          # PointerEvent as payload. `e.buttons !== 0` keeps hover-only mouse
          # moves out — a pan is a move with a button or touch held down.
          # (An earlier emit expected an {onStart,onMove,onEnd} object; nothing
          # declared or used that shape, and it contradicted the declaration.)
          if attributes['onPan']
            prop = resolve_handler_property(attributes['onPan'])
            attrs << " onPointerMove={(e) => { if (e.buttons !== 0) #{prop}?.(e); }}"
          end

          # onPinch — fires while two or more touch points move, with the
          # TouchEvent as payload. The touch-none class (build_class_name)
          # keeps the browser's own pinch-zoom/scroll from consuming the
          # gesture first.
          if attributes['onPinch']
            prop = resolve_handler_property(attributes['onPinch'])
            attrs << " onTouchMove={(e) => { if (e.touches.length >= 2) #{prop}?.(e); }}"
          end

          # Drag and Drop
          attrs << ' draggable' if attributes['draggable']

          if attributes['onDragStart']
            prop = extract_binding_property(attributes['onDragStart'])
            attrs << " onDragStart={(e) => #{prop}?.(e)}"
          end

          if attributes['onDrop']
            prop = extract_binding_property(attributes['onDrop'])
            attrs << " onDrop={(e) => { e.preventDefault(); #{prop}?.(e); }}"
          end

          if attributes['onDragOver']
            prop = extract_binding_property(attributes['onDragOver'])
            attrs << " onDragOver={(e) => { e.preventDefault(); #{prop}?.(e); }}"
          end

          if attributes['onDragEnter']
            prop = extract_binding_property(attributes['onDragEnter'])
            attrs << " onDragEnter={(e) => #{prop}?.(e)}"
          end

          if attributes['onDragLeave']
            prop = extract_binding_property(attributes['onDragLeave'])
            attrs << " onDragLeave={(e) => #{prop}?.(e)}"
          end

          attrs.compact.join('')
        end
      end
    end
  end
end
