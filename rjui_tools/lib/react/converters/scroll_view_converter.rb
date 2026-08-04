# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ScrollViewConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          children = convert_children(indent)
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          jsx = if children.empty?
            "#{indent_str(indent)}<div#{id_attr} className=\"#{class_name}\"#{style_attr}#{testid_attr}#{tag_attr} />"
          else
            <<~JSX.chomp
              #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
              #{children}
              #{indent_str(indent)}</div>
            JSX
          end

          # Wrap with visibility condition (for gone type)
          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Scroll direction
          orientation = attributes['orientation']
          horizontal_scroll = attributes['horizontalScroll']

          # scrollMode: "window" opts out of emitting `overflow-y-auto` /
          # `overflow-x-auto`. Rationale: on web, an inner-scroll container
          # establishes a `position: sticky` ancestry anchor even when the
          # container isn't actually bounded and the window does the
          # scrolling — sticky descendants end up waiting for a container
          # that never scrolls. Setting `scrollMode: "window"` lets authors
          # keep the ScrollView node for iOS/Android semantics while letting
          # the browser's window scroll naturally on web.
          window_mode = attributes['scrollMode'] == 'window'

          if horizontal_scroll || orientation == 'horizontal'
            classes << 'overflow-x-auto' unless window_mode
            classes << 'flex flex-row' unless attributes['orientation']
          else
            classes << 'overflow-y-auto' unless window_mode
            classes << 'flex flex-col' unless attributes['orientation']
          end

          # Hide scrollbar options
          if attributes['showsHorizontalScrollIndicator'] == false
            classes << 'scrollbar-hide'
          end
          if attributes['showsVerticalScrollIndicator'] == false
            classes << 'scrollbar-hide'
          end

          # Scroll snap (paging) — only meaningful when this div actually
          # scrolls, so skip for window-mode.
          if attributes['paging'] && !window_mode
            if horizontal_scroll || orientation == 'horizontal'
              classes << 'snap-x snap-mandatory'
            else
              classes << 'snap-y snap-mandatory'
            end
          end

          # Scroll enabled — same gate as above; window-mode lets the page
          # scroll regardless, and emitting overflow-hidden would actively
          # clip the rail.
          if attributes['scrollEnabled'] == false && !window_mode
            classes << 'overflow-hidden'
            classes.reject! { |c| c.start_with?('overflow-x-auto', 'overflow-y-auto') }
          end

          # Bounces (overscroll behavior)
          if attributes['bounces'] == false
            classes << 'overscroll-none'
          end

          # Content inset adjustment behavior
          if attributes['contentInsetAdjustmentBehavior'] == 'never'
            classes << 'scroll-p-0'
          end

          finalize_classes(classes)
        end

        def build_style_attr
          super

          # Content inset
          if attributes['contentInset']
            inset = attributes['contentInset']
            if inset.is_a?(Array)
              case inset.length
              when 1
                @dynamic_styles['padding'] = "'#{inset[0]}px'"
              when 2
                @dynamic_styles['padding'] = "'#{inset[0]}px #{inset[1]}px'"
              when 4
                @dynamic_styles['padding'] = "'#{inset[0]}px #{inset[1]}px #{inset[2]}px #{inset[3]}px'"
              end
            elsif inset.is_a?(Hash)
              top = inset['top'] || 0
              right = inset['right'] || 0
              bottom = inset['bottom'] || 0
              left = inset['left'] || 0
              @dynamic_styles['padding'] = "'#{top}px #{right}px #{bottom}px #{left}px'"
            else
              @dynamic_styles['padding'] = "'#{inset}px'"
            end
          end

          # Max zoom (for zoomable content)
          if attributes['maxZoom']
            @dynamic_styles['touchAction'] = "'pan-x pan-y pinch-zoom'"
          end

          # scrollBehavior — declared `platform: react`, i.e. it exists for the
          # web, and maps straight onto the CSS property of the same name. It
          # governs programmatic scrolling (scrollIntoView, anchor jumps), not
          # the user's own dragging.
          if %w[auto smooth].include?(attributes['scrollBehavior'])
            @dynamic_styles['scrollBehavior'] = "'#{attributes['scrollBehavior']}'"
          end

          # One renderer for every converter (BaseConverter#style_attr_for):
          # the SPREAD sentinel and the `React.CSSProperties` assertion a
          # custom-property key needs are handled in ONE place. Six converters
          # had hand-copied this loop, and four of the copies had lost the
          # assertion — which only surfaced when a bound colour started
          # writing `--jui-*` keys and the host's tsc rejected them.
          style_attr_for(@dynamic_styles)
        end
      end
    end
  end
end
