# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class ScrollViewConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          box = @still_box
          inner = box ? indent + 2 : indent
          children = convert_children(inner)
          id_attr = "#{build_id_attr}#{build_scroll_ref_attr}"
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          jsx = if children.empty?
            "#{indent_str(inner)}<div#{id_attr} className=\"#{class_name}\"#{style_attr}#{testid_attr}#{tag_attr} />"
          else
            <<~JSX.chomp
              #{indent_str(inner)}<div#{id_attr}#{class_name_attr(class_name)}#{style_attr}#{testid_attr}#{tag_attr}>
              #{children}
              #{indent_str(inner)}</div>
            JSX
          end
          if box
            jsx = <<~JSX.chomp
              #{indent_str(indent)}<div className="#{box[:classes]}"#{style_attr_for(box[:styles])}>
              #{jsx}
              #{indent_str(indent)}</div>
            JSX
          end

          # Wrap with visibility condition (for gone type)
          wrap_with_visibility(jsx, indent)
        end

        protected

        # Its own box scrolls, unless the window does (scrollMode window)
        # (BaseConverter#scrolls_its_content?: the border is an outline).
        def scrolls_its_content?
          return false if @box_pass

          attributes['scrollMode'] != 'window' || super
        end

        def border_box?
          attributes['borderWidth'] && attributes['borderColor'] && attributes['scrollMode'] != 'window'
        end

        # On the still box's pass through BaseConverter the children's layout
        # classes are left out: they go on the scroll box.
        def lays_out_children?
          !@box_pass
        end

        # With a still box the id — and the carried size-class classes,
        # measured on the element with the id — are on the scroll box.
        def carries_size_classes_inside?
          !!@box_pass
        end

        def still_box_pass?
          !!@box_pass
        end

        # `defaultScrollAnchor` says where the view STARTS, which no CSS
        # property expresses — the scroll offset has to be written once on
        # mount. The generator hoists the ref and the effect (the same
        # `applyCollectionDefaultAnchor` helper a Collection uses: it takes any
        # scrollable element), and this attaches the ref they address. A
        # literal id is the contract between the two halves — MUST stay in sync
        # with ReactGenerator::SCROLL_CONTAINER_TYPES.
        # The axis the content scrolls along: its parent-bounds stop there
        # (BaseConverter#with_parent_bounds) — Android measures a scroll's
        # content unbounded on that axis.
        def scroll_axis
          attributes['horizontalScroll'] || attributes['orientation'] == 'horizontal' ? 'width' : 'height'
        end

        def scroll_axis_letter
          scroll_axis == 'width' ? 'x' : 'y'
        end

        def build_scroll_ref_attr
          return '' unless attributes['defaultScrollAnchor']

          id = extract_id
          return '' unless id.is_a?(String) && !id.empty? && !id.include?('@{')

          " ref={#{snake_to_camel_id(id)}Ref}"
        end

        def build_class_name
          # A border on a ScrollView that scrolls its own box is drawn by a
          # still box around it, as a Collection's is (CollectionConverter
          # #border_box?): the box takes BaseConverter's classes and styles —
          # size, margins, background, corners, the border's ::after — and the
          # scroll box inside it the scroll, the children's layout, the id and
          # the ref. Until jsonui-cli 2.3.32 the border was the scroll box's
          # own outline (2.3.29), which an app's :focus-visible outline
          # replaced (ticket rjui-scroll-border-outline-replaced-by-focus-ring).
          @still_box = nil
          if border_box?
            @box_pass = true
            box_classes = super
            @box_pass = false
            @still_box = { classes: finalize_classes([box_classes, 'flex flex-col']), styles: @dynamic_styles }
            @dynamic_styles = {}
            # isolate: the children's z-index stays inside the scroll box, so
            # the still box's ::after border is drawn over a sticky header
            # (z-10) or a cell with a z-index, which covered it until
            # jsonui-cli 2.3.34 (ticket rjui-sticky-child-covers-still-box-
            # border; an overlay a portal draws is not inside it).
            classes = ['flex-1 min-w-0 min-h-0', 'isolate', ('rounded-[inherit]' if attributes['cornerRadius']), *children_layout_classes,
                       *(@responsive_result && @responsive_result[:carried])]
            warn_class_name_stops_scrolling
          else
            classes = [super]
          end

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
          elsif !window_mode && (expr = bound_value_expr(attributes['scrollEnabled']))
            # A bound false is the declared false, decided at run time: the
            # inline overflow wins over the overflow-*-auto class. Any other
            # value (true, not loaded yet) scrolls, as an undeclared one does.
            # Until jsonui-cli 2.3.28 nothing came and a bound false scrolled.
            dynamic_styles['overflow'] = "#{expr} === false ? 'hidden' : undefined"
          end

          # Bounces (overscroll behavior)
          if attributes['bounces'] == false
            classes << 'overscroll-none'
          end

          # Content inset adjustment behavior
          if attributes['contentInsetAdjustmentBehavior'] == 'never'
            classes << 'scroll-p-0'
          end

          classes.concat(split_scroll_class_name[:inside]) if @still_box
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
                @dynamic_styles['padding'] = "'#{TailwindMapper.rem(inset[0])}'"
              when 2
                @dynamic_styles['padding'] = "'#{TailwindMapper.rem(inset[0])} #{TailwindMapper.rem(inset[1])}'"
              when 4
                @dynamic_styles['padding'] = "'#{TailwindMapper.rem(inset[0])} #{TailwindMapper.rem(inset[1])} #{TailwindMapper.rem(inset[2])} #{TailwindMapper.rem(inset[3])}'"
              end
            elsif inset.is_a?(Hash)
              top = inset['top'] || 0
              right = inset['right'] || 0
              bottom = inset['bottom'] || 0
              left = inset['left'] || 0
              @dynamic_styles['padding'] = "'#{[top, right, bottom, left].map { |v| TailwindMapper.rem(v) }.join(' ')}'"
            else
              @dynamic_styles['padding'] = "'#{TailwindMapper.rem(inset)}'"
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
