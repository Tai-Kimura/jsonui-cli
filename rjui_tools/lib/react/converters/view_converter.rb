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
          if @indent == 2 && json['height'] == 'matchParent'
            classes << 'h-full'
          end

          # Layout mode for View with children
          if child_array.is_a?(Array)
            if json['orientation']
              # orientation specified - handled by base_converter's map_orientation
            elsif ui_children_count > 1
              # No orientation + multiple UI children = overlay (FrameLayout)
              classes << 'relative'
            else
              # No orientation + single child = simple wrapper
              classes.unshift('flex flex-col')
            end
          end

          # Center alignment
          classes << 'items-center' if json['centerHorizontal']
          classes << 'justify-center' if json['centerVertical']
          classes << 'items-center justify-center' if json['centerInParent']

          # Gap/Spacing
          if json['spacing']
            spacing = TailwindMapper::PADDING_MAP[json['spacing']] || json['spacing']
            classes << "gap-#{spacing}"
          end

          # Distribution (justify-content for flex containers)
          if json['distribution']
            case json['distribution']
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
          classes << 'cursor-pointer' if json['onClick'] || json['onclick']

          # Highlight/Tap background effects (using hover/active states)
          if json['tapBackground'] || json['highlightBackground']
            tap_bg = json['tapBackground'] || json['highlightBackground']
            classes << "active:#{TailwindMapper.map_color(tap_bg, 'bg')}" if tap_bg.is_a?(String)
          end

          # Highlighted state (initial highlight)
          if json['highlighted']
            highlight_bg = json['highlightBackground'] || '#E5E7EB'
            classes << TailwindMapper.map_color(highlight_bg, 'bg')
          end

          # Transition for smooth effects
          classes << 'transition-colors' if json['tapBackground'] || json['highlightBackground']

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
          child_array.is_a?(Array) && ui_children_count > 1 && !json['orientation']
        end

        def convert_children(indent)
          if overlay_layout?
            items = child_array.is_a?(Array) ? child_array : [child_array]
            items.filter_map do |child|
              next nil if data_only_element?(child)

              # Inject absolute positioning for overlay children
              overlay_child = child.merge('_overlay' => true)
              converter = create_converter_for_child(overlay_child)
              converter.convert(indent + 2)
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
          if json['onLongPress']
            handler = json['onLongPress']
            if handler.start_with?('@{')
              attrs << " onContextMenu={(e) => { e.preventDefault(); #{handler.gsub(/@\{|\}/, '')}(e); }}"
            else
              attrs << " onContextMenu={(e) => { e.preventDefault(); #{handler}(e); }}"
            end
          end

          # onPan (using pointer events for drag)
          if json['onPan']
            handler = json['onPan']
            handler_name = handler.start_with?('@{') ? handler.gsub(/@\{|\}/, '') : handler
            attrs << " onPointerDown={(e) => #{handler_name}?.onStart?.(e)}"
            attrs << " onPointerMove={(e) => #{handler_name}?.onMove?.(e)}"
            attrs << " onPointerUp={(e) => #{handler_name}?.onEnd?.(e)}"
          end

          # onPinch (using touch events)
          if json['onPinch']
            handler = json['onPinch']
            handler_name = handler.start_with?('@{') ? handler.gsub(/@\{|\}/, '') : handler
            attrs << " onTouchStart={(e) => #{handler_name}?.onStart?.(e)}"
            attrs << " onTouchMove={(e) => #{handler_name}?.onMove?.(e)}"
            attrs << " onTouchEnd={(e) => #{handler_name}?.onEnd?.(e)}"
          end

          # Drag and Drop
          attrs << ' draggable' if json['draggable']

          if json['onDragStart']
            prop = extract_binding_property(json['onDragStart'])
            attrs << " onDragStart={(e) => #{prop}?.(e)}"
          end

          if json['onDrop']
            prop = extract_binding_property(json['onDrop'])
            attrs << " onDrop={(e) => { e.preventDefault(); #{prop}?.(e); }}"
          end

          if json['onDragOver']
            prop = extract_binding_property(json['onDragOver'])
            attrs << " onDragOver={(e) => { e.preventDefault(); #{prop}?.(e); }}"
          end

          if json['onDragEnter']
            prop = extract_binding_property(json['onDragEnter'])
            attrs << " onDragEnter={(e) => #{prop}?.(e)}"
          end

          if json['onDragLeave']
            prop = extract_binding_property(json['onDragLeave'])
            attrs << " onDragLeave={(e) => #{prop}?.(e)}"
          end

          attrs.compact.join('')
        end
      end
    end
  end
end
