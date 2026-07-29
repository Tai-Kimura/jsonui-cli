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

          jsx = if children.empty?
            "#{indent_str(indent)}<div#{id_attr}#{class_attr}#{style_attr}#{event_attrs} />"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<div#{id_attr}#{class_attr}#{style_attr}#{event_attrs}>
              #{children}
              #{indent_str(indent)}</div>
            JSX
          end

          # Wrap with visibility condition (for 'gone' type)
          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_style_attr_with_visibility
          build_style_attr
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
              # No orientation + multiple UI children = overlay (FrameLayout)
              classes << 'relative'
            else
              # No orientation + single child = simple wrapper
              classes.unshift('flex flex-col')
            end
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

          classes.compact.reject(&:empty?).join(' ')
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

        def convert_children(indent)
          if overlay_layout?
            items = child_array.is_a?(Array) ? child_array : [child_array]
            items.filter_map do |child|
              next nil if data_only_element?(child)

              # Inject absolute positioning for overlay children
              overlay_child = child.merge('_overlay' => true)
              converter = create_converter_for_child(overlay_child)
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
