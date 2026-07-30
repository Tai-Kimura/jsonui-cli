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

        #: JsonUI edge -> the physical CSS side. `leading`/`trailing` are logical
        #: names, but `env()` only exposes physical insets and this codebase is
        #: LTR throughout (startMargin already becomes a left padding), so they
        #: map straight to left/right.
        SAFE_AREA_SIDES = {
          'top' => 'Top', 'bottom' => 'Bottom',
          'leading' => 'Left', 'trailing' => 'Right'
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
        def apply_safe_area_insets
          edges = safe_area_edges
          return if edges.empty?

          @dynamic_styles ||= {}
          edges.each do |edge|
            side = SAFE_AREA_SIDES[edge]
            inset = "env(safe-area-inset-#{side.downcase})"
            own = own_padding_px(edge)
            @dynamic_styles["padding#{side}"] =
              own.positive? ? "'calc(#{format_px(own)}px + #{inset})'" : "'#{inset}'"
          end
        end

        # 8.0px reads as a mistake; 8px does not.
        def format_px(value)
          value == value.to_i ? value.to_i.to_s : value.to_s
        end

        def safe_area_edges
          raw = attributes['safeAreaInsetPositions']
          return [] if raw.nil?

          named = (raw.is_a?(Array) ? raw : [raw]).map { |e| e.to_s }
          return SAFE_AREA_SIDES.keys if named.include?('all')

          expanded = named.flat_map { |e| e == 'vertical' ? %w[top bottom] : [e] }
          expanded.uniq.select { |e| SAFE_AREA_SIDES.key?(e) }
        end

        # The padding this element already has on one edge, in px. Mirrors the
        # attributes base_converter turns into padding classes.
        def own_padding_px(edge)
          index = { 'top' => 0, 'trailing' => 1, 'bottom' => 2, 'leading' => 3 }[edge]
          per_edge = case edge
                     when 'top' then attributes['topPadding'] || attributes['paddingTop']
                     when 'bottom' then attributes['bottomPadding'] || attributes['paddingBottom']
                     when 'leading' then attributes['paddingStart'] || attributes['leftPadding'] || attributes['paddingLeft']
                     else attributes['paddingEnd'] || attributes['rightPadding'] || attributes['paddingRight']
                     end
          return per_edge.to_f if per_edge.is_a?(Numeric)

          all = attributes['padding'] || attributes['paddings']
          case all
          when Numeric then all.to_f
          when Array
            case all.length
            when 1 then all[0].to_f
            when 2 then (%w[top bottom].include?(edge) ? all[0] : all[1]).to_f
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

          # Center alignment
          classes << 'items-center' if attributes['centerHorizontal']
          classes << 'justify-center' if attributes['centerVertical']
          classes << 'items-center justify-center' if attributes['centerInParent']

          # Gap/Spacing
          if attributes['spacing']
            spacing = TailwindMapper::PADDING_MAP[attributes['spacing']] || attributes['spacing']
            classes << "gap-#{spacing}"
          end

          # Distribution (justify-content for flex containers)
          if attributes['distribution']
            case attributes['distribution']
            when 'fill'
              classes << 'justify-between'
            when 'fillEqually'
              classes << 'justify-evenly'
            when 'equalSpacing'
              classes << 'justify-around'
            when 'equalCentering'
              classes << 'justify-evenly'
            end
          end

          # Cursor pointer for clickable items
          classes << 'cursor-pointer' if attributes['onClick'] || attributes['onclick']

          # Highlight/Tap background effects (using hover/active states)
          if attributes['tapBackground'] || attributes['highlightBackground']
            tap_bg = attributes['tapBackground'] || attributes['highlightBackground']
            classes << "active:#{TailwindMapper.map_color(tap_bg, 'bg')}" if tap_bg.is_a?(String)
          end

          # Highlighted state (initial highlight)
          if attributes['highlighted']
            highlight_bg = attributes['highlightBackground'] || '#E5E7EB'
            classes << TailwindMapper.map_color(highlight_bg, 'bg')
          end

          # Transition for smooth effects
          classes << 'transition-colors' if attributes['tapBackground'] || attributes['highlightBackground']

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
            items.filter_map do |child|
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
            end.join("\n")
          else
            super
          end
        end

        # Build all event handler attributes
        def build_event_attrs
          attrs = []

          # onClick
          attrs << build_onclick_attr

          # onLongPress (using onContextMenu as fallback, or custom implementation)
          if attributes['onLongPress']
            prop = resolve_handler_property(attributes['onLongPress'])
            attrs << " onContextMenu={(e) => { e.preventDefault(); #{prop}?.(e); }}"
          end

          # onPan (using pointer events for drag)
          if attributes['onPan']
            prop = resolve_handler_property(attributes['onPan'])
            attrs << " onPointerDown={(e) => #{prop}?.onStart?.(e)}"
            attrs << " onPointerMove={(e) => #{prop}?.onMove?.(e)}"
            attrs << " onPointerUp={(e) => #{prop}?.onEnd?.(e)}"
          end

          # onPinch (using touch events)
          if attributes['onPinch']
            prop = resolve_handler_property(attributes['onPinch'])
            attrs << " onTouchStart={(e) => #{prop}?.onStart?.(e)}"
            attrs << " onTouchMove={(e) => #{prop}?.onMove?.(e)}"
            attrs << " onTouchEnd={(e) => #{prop}?.onEnd?.(e)}"
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
