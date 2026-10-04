# frozen_string_literal: true

require_relative 'base_converter'
require_relative '../../core/logger'
require_relative '../component_name'
require_relative '../../core/attribute_types'

module RjuiTools
  module React
    module Converters
      class CollectionConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          ref_attr = build_collection_ref_attr
          scroll_attr = build_current_page_scroll_attr

          box = @padding_box
          inner = box ? indent + 2 : indent
          content = generate_collection_content(inner + 2)

          jsx = <<~JSX.chomp
            #{indent_str(inner)}<div#{id_attr}#{ref_attr} className="#{class_name}"#{style_attr}#{scroll_attr}#{testid_attr}#{tag_attr}>
            #{content}
            #{indent_str(inner)}</div>
          JSX
          if box
            jsx = <<~JSX.chomp
              #{indent_str(indent)}<div className="#{box[:classes]}"#{style_attr_for(box[:styles])}>
              #{jsx}
              #{indent_str(indent)}</div>
            JSX
          end

          wrap_with_visibility(jsx, indent)
        end

        # The collection is horizontal when its layout says so — the same
        # decision `build_class_name` makes, hoisted so the scroll helpers can
        # be told which axis to measure.
        def horizontal_collection?
          # `horizontalScroll: true` is the boolean spelling of the same fact
          # (ScrollView vocabulary; the ledger showed real layouts using it on
          # Collection carousels).
          return true if attributes['horizontalScroll'] == true

          layout = attributes['orientation'] || attributes['layout'] ||
                   attributes['scrollDirection'] || 'vertical'
          JsonUIShared::EnumSpelling.lowered(layout, 'Collection', 'layout') == 'horizontal'
        end

        # layout: flow — wrapping layout, packed to the top-left. Unified
        # 2026-08-03: 'LeftAligned' IS flow (the accepted spellings survive
        # as aliases, same case-insensitive read sjui/kjui use for 'Flow').
        # sjui renders a custom flow layout, kjui a FlowRow; the CSS shape
        # of the same thing is a wrapping flex row.
        def flow_collection?
          layout = attributes['orientation'] || attributes['layout'] || ''
          %w[flow leftaligned].include?(JsonUIShared::EnumSpelling.lowered(layout, 'Collection', 'layout'))
        end

        # A horizontal Collection (4f ruling, 2026-09-26; the rule sjui
        # codegen and SwiftJsonUI Dynamic dde0628 draw): `columns` is its
        # number of lanes, and a section's own `columns` is that section
        # block's lanes. A section has more than one lane when its own
        # `columns`, else the Collection's, is above 1; a bound `columns` keeps
        # the grid even at 1 lane, and a section's own count overrides it.
        # Paging is unchanged. The lane count as a JS expression, or nil for
        # one lane (the flex row as it was). Until jsonui-cli 1.9.0 the
        # horizontal row drew one lane whatever `columns` said.
        def horizontal_lanes(section = {})
          return nil unless horizontal_collection? && !flow_collection? && !attributes['paging']

          own = section.is_a?(Hash) ? section['columns'] : nil
          return (own.to_i > 1 ? own.to_i.to_s : nil) if own.is_a?(Numeric)

          raw = attributes['columnCount'] || attributes['columns']
          return extract_binding_property(raw) if raw.is_a?(String) && has_binding?(raw)

          raw.to_i > 1 ? raw.to_i.to_s : nil
        end

        # Along the scroll axis lineSpacing (its alias sectionSpacing), else
        # itemSpacing; between lanes columnSpacing, else itemSpacing — on
        # every horizontal Collection, one lane or many. nil: nothing declared.
        def horizontal_scroll_spacing
          attributes['lineSpacing'] || attributes['sectionSpacing'] || attributes['itemSpacing'] || attributes['spacing']
        end

        def horizontal_lane_spacing
          attributes['columnSpacing'] || attributes['itemSpacing'] || attributes['spacing']
        end

        # A section block of `lanes` rows: a grid that flows by column, so a
        # column is filled top to bottom and then the next
        # (LazyHorizontalGrid's order), the block starting a new column in the
        # flex row; cells keep their own size at the top-leading corner of
        # their slot, as on the other faces.
        def horizontal_lanes_open(lanes, indent)
          rows = lanes.match?(/\A\d+\z/) ? "'repeat(#{lanes}, minmax(0, 1fr))'" : "`repeat(${#{lanes}}, minmax(0, 1fr))`"
          style = { 'gridTemplateRows' => rows }
          (along = horizontal_scroll_spacing) && style['columnGap'] = "'#{TailwindMapper.rem(along)}'"
          (between = horizontal_lane_spacing) && style['rowGap'] = "'#{TailwindMapper.rem(between)}'"
          "#{indent_str(indent)}<div className=\"grid grid-flow-col auto-cols-max items-start justify-items-start shrink-0\"#{style_attr_for(style)}>"
        end

        # A literal id is what ties the element to the hoisted ref, exactly as
        # it does for the focus bindings and for `{id}_item_{index}`. Without
        # one there is no stable variable name to agree on, so the attributes
        # would silently do nothing — say so instead.
        def scroll_control_id
          id = attributes['id']
          return nil unless id.is_a?(String) && !id.empty? && !has_binding?(id)

          id
        end

        # Scroll control that needs a ref on the collection element.
        # ReactGenerator hoists the matching declarations from its own walk
        # (`extract_collection_scrolls`); the two must agree on which
        # collections participate.
        #
        # Written out rather than looped over a name list: the consumed-
        # attribute scan (and the conformance coverage ratchet) match literal
        # single-quoted attribute reads, so a loop reads as "nobody consumes
        # these" and the ledger keeps counting them as unimplemented.
        def scroll_control_attrs
          {
            'scrollTo' => attributes['scrollTo'],
            'defaultScrollAnchor' => attributes['defaultScrollAnchor'],
            'currentPage' => attributes['currentPage'],
            'onItemAppear' => attributes['onItemAppear'],
            'onValueChange' => page_change_handler
          }.compact.keys
        end

        # The page-change callback (`onValueChange`, alias `onPageChanged`):
        # a paging Collection's, called with the page index when the page the
        # user scrolled to changes — what sjui's TabView onChange and kjui's
        # pager snapshotFlow call. Until 1.9.0 rjui read it nowhere, so the
        # callback never fired on web (ticket
        # collection-attributes-declared-but-not-drawn-on-some-paths).
        def page_change_handler
          handler = attributes['onValueChange']
          return nil unless attributes['paging'] == true && string_event_handler?(handler)

          resolve_handler_property(has_binding?(handler) ? handler : string_event_name(handler))
        end

        def build_collection_ref_attr
          declared = scroll_control_attrs
          return '' if declared.empty?

          id = scroll_control_id
          unless id
            RjuiTools::Core::Logger.warn "[rjui] Collection: #{declared.join(', ')} " \
                                         "#{declared.one? ? 'needs' : 'need'} " \
                 'a literal `id` on the collection to bind to; ignoring.'
            return ''
          end

          " ref={#{snake_to_camel_id(id)}Ref}"
        end

        # currentPage read-back. `data.on<Prop>Change` is the same write-back
        # convention the inputs use (TextField text, Switch isOn), and comparing
        # against the bound value is what keeps a scroll event from firing the
        # handler on every frame.
        def build_current_page_scroll_attr
          return '' unless scroll_control_id

          calls = []
          current_page = attributes['currentPage']
          if current_page.is_a?(String) && has_binding?(current_page)
            prop = extract_binding_property(current_page)
            handler = "data.on#{capitalize_first(extract_raw_binding_property(current_page))}Change"
            calls << "if (page !== #{prop}) #{handler}?.(page);"
          end
          # The callback fires once per page change: the element remembers
          # the page it last reported (a scroll fires many events per page).
          # It starts remembering the page the pager first shows — the bound
          # currentPage, else 0 — because the callback is called when the
          # page CHANGES and not when the pager appears (attribute_definitions
          # Collection.onValueChange, ruling 2026-10-02). Until jsonui-cli
          # 1.9.6 it started empty, so the first scroll event reported the
          # page it was already on: a nudge that snapped back to page 0 called
          # the callback with 0 (measured in Chromium, ticket
          # pager-page-change-callback-initial-call-differs-by-platform).
          # React writes the attribute only when its value changes, so the
          # page the handler records between renders is kept.
          seed = ''
          if (callback = page_change_handler)
            calls << "const el = #{ref_var}; if (el && el.dataset.jsonuiPage !== String(page)) " \
                     "{ el.dataset.jsonuiPage = String(page); #{callback}?.(page); }"
            seed = if current_page.is_a?(String) && has_binding?(current_page)
                     " data-jsonui-page={String(#{extract_binding_property(current_page)} ?? 0)}"
                   else
                     ' data-jsonui-page="0"'
                   end
          end
          return '' if calls.empty?

          "#{seed} onScroll={() => { const page = currentCollectionPage(#{ref_var}, #{horizontal_collection?}); " \
            "#{calls.join(' ')} }}"
        end

        def ref_var
          id = scroll_control_id
          id ? "#{snake_to_camel_id(id)}Ref.current" : 'null'
        end

        def capitalize_first(str)
          return str if str.nil? || str.empty?

          str[0].upcase + str[1..]
        end

        protected

        def build_class_name
          # The node's own padding goes outside the scroll, its insets inside
          # (user ruling 2026-09-28, as iOS and both Compose paths draw them):
          # with a padding declared, the node's box is a padding box around
          # the scroll container (padding_box?). That box takes BaseConverter's
          # classes and styles — size, margins, padding, background, border,
          # visibility, … — except the ones that lay the cells out
          # (orientation, gravity, direction), which stay on the scroll
          # container with the Collection's own; the scroll container fills
          # the box's content (flex-1 in a flex column) and keeps the id, the
          # test id, the ref and the scroll handler, so what scrolls is still
          # the element the id names.
          @padding_box = nil
          if padding_box?
            @padding_box_pass = true
            box_classes = super
            @padding_box_pass = false
            @padding_box = { classes: finalize_classes([box_classes, 'flex flex-col']), styles: @dynamic_styles }
            @dynamic_styles = {}
            classes = ['flex-1 min-w-0 min-h-0', *children_layout_classes]
          else
            classes = [super]
          end

          # Resolve the column count. A `@{prop}` binding can't be baked
          # into a Tailwind `grid-cols-N` class — Tailwind's JIT only sees
          # class names at build time. Emit the bare `grid` class and push
          # a runtime `gridTemplateColumns: repeat(${data.prop}, minmax(0,
          # 1fr))` into `@dynamic_styles` instead. A literal int keeps the
          # existing `grid-cols-N` shortcut, which is one byte shorter
          # than the inline-style equivalent.
          raw_columns = attributes['columnCount'] || attributes['columns']
          columns_binding = raw_columns.is_a?(String) && has_binding?(raw_columns)
          columns = columns_binding ? nil : (raw_columns || 1)
          is_horizontal = horizontal_collection?
          # lazy: "none" → drop overflow scroll classes; Collection is expected to
          # render inside an already-scrollable parent.
          #
          # A BOUND value is a string, and `"@{v}" != 'none'` is always true,
          # so a Collection whose container shape is chosen at runtime could
          # never reach the `none` shape — it froze on scrolling. (`lazy` vs
          # `eager` is not a distinction web makes: the emit is a plain
          # `.map()` either way, so there is no virtualization to switch off.
          # `none` is the only one of the three that changes the DOM here.)
          # The scroll classes stay as the default and the inline style
          # overrides them when the runtime value turns out to be `none`.
          lazy = attributes['lazy']
          lazy_expr = bound_value_expr(lazy)
          is_lazy = lazy_expr ? true : lazy != 'none'

          if flow_collection?
            # Flow is checked before horizontal, like sjui/kjui route to
            # their flow generators first — the declared layout wins over
            # the horizontalScroll boolean.
            # One wrap, or — with two or more sections (flow_per_section?) —
            # a column of them, one per section, the blocks spaced as the
            # lines. The gaps: grid_gap_classes.
            classes << (flow_per_section? ? 'flex flex-col' : 'flex flex-row flex-wrap content-start')
            if is_lazy && attributes['scrollEnabled'] != false
              classes << 'overflow-y-auto'
              dynamic_styles['overflowY'] = "#{lazy_expr} === 'none' ? 'visible' : 'auto'" if lazy_expr
            end
            if flow_per_section?
              row_gap = grid_row_gap
              classes << "gap-y-#{TailwindMapper.spacing_value(row_gap)}" if row_gap
            else
              classes.concat(grid_gap_classes)
            end
          elsif is_horizontal
            # Horizontal scroll collection
            if is_lazy
              classes << 'overflow-x-auto'
              dynamic_styles['overflowX'] = "#{lazy_expr} === 'none' ? 'visible' : 'auto'" if lazy_expr
            end
            classes << 'flex flex-row'
            if is_lazy && attributes['scrollEnabled'] != false
              classes << 'flex-nowrap'
              dynamic_styles['flexWrap'] = "#{lazy_expr} === 'none' ? 'wrap' : 'nowrap'" if lazy_expr
            end
            # Along the scroll axis — between cells, between section blocks,
            # between pages — lineSpacing, else itemSpacing (the horizontal
            # rule, horizontal_scroll_spacing). This read columnSpacing
            # first until jsonui-cli 1.9.0; columnSpacing spaces the lanes.
            spacing = horizontal_scroll_spacing
            classes << "gap-#{TailwindMapper.spacing_value(spacing)}" if spacing
          elsif !columns_binding && columns == 1
            # List style (single column). A binding-form `columns` can't
            # reach this branch — the runtime count is unknown at codegen
            # time so we always route through the grid path below to keep
            # the layout structure stable across runtime column changes.
            classes << 'flex flex-col'
            if is_lazy && attributes['scrollEnabled'] != false
              classes << 'overflow-y-auto'
              dynamic_styles['overflowY'] = "#{lazy_expr} === 'none' ? 'visible' : 'auto'" if lazy_expr
            end
            # lineSpacing for vertical spacing between items
            spacing = attributes['lineSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            classes << "gap-#{TailwindMapper.spacing_value(spacing)}" if spacing
            # listStyle / hideSeparator — the List chrome, on the one branch
            # that IS a list (sjui parity: TableConverter takes the List path
            # only for the unsectioned single-column shape).
            classes.concat(list_style_classes)
          elsif grid_per_section?
            # A grid per section (grid_per_section?): a column of blocks —
            # each section's header row, its grid, its footer row — spaced as
            # the rows; each block's grid carries the columns and the gaps.
            classes << 'flex flex-col'
            classes.concat(vertical_scroll_classes(is_lazy, lazy_expr))
            row_gap = grid_row_gap
            classes << "gap-y-#{TailwindMapper.spacing_value(row_gap)}" if row_gap
          else
            # Grid layout
            classes << 'grid'
            classes.concat(vertical_scroll_classes(is_lazy, lazy_expr))
            if columns_binding
              # extract_binding_property already prepends `data.` (see
              # base_converter#extract_binding_property), so just splice
              # the returned expression into the template literal.
              expr = extract_binding_property(raw_columns)
              @dynamic_styles['gridTemplateColumns'] =
                "`repeat(${#{expr}}, minmax(0, 1fr))`"
            else
              classes << "grid-cols-#{columns}"
            end
            classes.concat(grid_gap_classes)
          end

          # lazy vs eager, the rendering half. The scroll-container half above
          # only distinguishes `none`; `lazy` and `eager` differ in whether
          # off-screen CELLS are rendered, and the web's native spelling of
          # that is `content-visibility` on the items — `auto` lets the
          # browser skip off-screen rendering work (the virtualization the
          # LazyVStack/LazyColumn faces get from their containers), `visible`
          # renders everything eagerly. Only an EXPLICIT declaration is
          # spelled out (same rule as Label's `textTransform: none`): the
          # undeclared default keeps the browser default, so no existing
          # layout changes shape by omission.
          case lazy
          when 'lazy'
            classes << '[&>*]:[content-visibility:auto]'
          when 'eager'
            classes << '[&>*]:[content-visibility:visible]'
          end
          if lazy_expr
            # The bound form switches at runtime. A class cannot, so the
            # per-child arbitrary variant reads a custom property the style
            # object writes — the same trick the Switch uses for its
            # peer-checked track colour.
            classes << '[&>*]:[content-visibility:var(--jui-lazy-cv,visible)]'
            dynamic_styles['--jui-lazy-cv'] = "(#{lazy_expr} === 'lazy' ? 'auto' : 'visible')"
          end

          # paging: CSS scroll snapping is the web's page model, and it is what
          # gives `currentPage` a page to be the index of. iOS uses a TabView
          # and Compose a HorizontalPager for the same attribute.
          # The snap points have to be on the children, and the children are
          # user cell components — hence the arbitrary-variant class rather than
          # a class on each cell.
          if attributes['paging']
            classes << (is_horizontal ? 'snap-x snap-mandatory' : 'snap-y snap-mandatory')
            classes << '[&>*]:snap-start'
          end

          # Content insets as padding
          content_inset = attributes['contentInset']
          if content_inset.is_a?(Array) && content_inset.length == 4
            top, left, bottom, right = content_inset
            classes << "pt-#{TailwindMapper.spacing_value(top)}" if top&.positive?
            classes << "pl-#{TailwindMapper.spacing_value(left)}" if left&.positive?
            classes << "pb-#{TailwindMapper.spacing_value(bottom)}" if bottom&.positive?
            classes << "pr-#{TailwindMapper.spacing_value(right)}" if right&.positive?
          end

          # The content insets: insets with insetHorizontal / insetVertical,
          # added per edge (content_inset_classes).
          classes.concat(content_inset_classes)

          # Same web semantics as ScrollView for its shared vocabulary:
          # indicator switches hide the scrollbar, and 'never' inset
          # adjustment zeroes the scroll padding.
          if attributes['showsHorizontalScrollIndicator'] == false ||
             attributes['showsVerticalScrollIndicator'] == false
            classes << 'scrollbar-hide'
          end
          if attributes['contentInsetAdjustmentBehavior'] == 'never'
            classes << 'scroll-p-0'
          end


          finalize_classes(classes)
        end

        # The Collection pads its content with its insets itself
        # (content_inset_classes), not with BaseConverter's padding classes.
        def owns_insets?
          true
        end

        # On the padding box's pass through BaseConverter the cells' layout
        # classes are left out: they go on the scroll container.
        def lays_out_children?
          !@padding_box_pass
        end

        #: The node padding spellings BaseConverter#build_class_name reads.
        NODE_PADDING_KEYS = %w[padding paddings topPadding paddingTop rightPadding paddingRight
                               bottomPadding paddingBottom leftPadding paddingLeft paddingStart paddingEnd].freeze

        # The Collection declares a padding that pads (a bound value counts;
        # 0, or zeros, pads nothing): its box is then a padding box around
        # the scroll container (build_class_name). Until jsonui-cli 1.9.0 the
        # padding classes and the insets classes sat on the one scroll
        # container, so an inset's side class replaced the padding on that
        # edge (padding 16, insets [0, 0, 0, 30]: the first cell at 30, not
        # 46), a bound inset's four inline edges replaced it on every edge,
        # and the padding scrolled with the cells.
        def padding_box?
          NODE_PADDING_KEYS.any? { |key| padding_pads?(attributes[key]) }
        end

        def padding_pads?(value)
          case value
          when Numeric then !value.zero?
          when Array then value.any? { |v| padding_pads?(v) }
          when String
            return true if has_binding?(value)

            value.split('|').any? { |part| (n = inset_number(part)) && !n.zero? }
          else false
          end
        end

        # The Collection's content insets on its own box — the scroll
        # container, so the padding is inside the scroll: per edge, the sum of
        # `insets` (1, 2 or 4 values, an array or a `|` string, read as
        # `paddings` reads them: one, every side; two, [vertical,
        # horizontal]; four, [top, right, bottom, left]; any other value pads
        # nothing), insetHorizontal (left and right) and insetVertical (top
        # and bottom) — added, no precedence, as iOS and both Compose paths
        # draw them (the SSoT's Collection.insets). Exact values: an arbitrary
        # `pt-[30px]`, not a class of Tailwind's spacing scale. A bound value
        # in the array (a number; unset, 0) makes the four edges inline
        # styles. Until jsonui-cli 1.9.0 the insets were BaseConverter's
        # padding classes: rounded to the scale (30 became pt-7, 28px), four
        # values replaced insetHorizontal / insetVertical (pt-/pr-/pb-/pl-
        # come after px-/py- in Tailwind's CSS), two values lost to
        # insetHorizontal, and the string form was not read. On a pager the
        # snap points keep the insets (scroll-padding on the same edges), so
        # a page snaps to where the insets put it.
        def content_inset_classes
          edges = content_inset_edges
          return [] unless edges

          classes = []
          if edges.any? { |e| e.is_a?(String) }
            styles = paging? ? %w[padding scrollPadding] : %w[padding]
            styles.each do |base|
              %w[Top Right Bottom Left].zip(edges).each do |side, e|
                dynamic_styles["#{base}#{side}"] = e.is_a?(String) ? "`${Number(#{e}) / 16}rem`" : "'#{TailwindMapper.rem(e)}'"
              end
            end
            return classes
          end

          %w[t r b l].zip(edges).each do |side, e|
            next if e.zero?

            classes << "p#{side}-#{TailwindMapper.spacing_value(e)}"
            classes << "scroll-p#{side}-#{TailwindMapper.spacing_value(e)}" if paging?
          end
          classes
        end

        # [top, right, bottom, left] — each a number, or a JS expression when
        # a value of `insets` is bound — or nil when nothing pads.
        def content_inset_edges
          edges = parse_collection_insets(attributes['insets']) || [0, 0, 0, 0]
          h = inset_number(attributes['insetHorizontal'])
          v = inset_number(attributes['insetVertical'])
          edges = [add_edge(edges[0], v), add_edge(edges[1], h), add_edge(edges[2], v), add_edge(edges[3], h)]
          return nil if edges.all? { |e| e.is_a?(Numeric) && e.zero? }

          edges
        end

        # The declared insets as [top, right, bottom, left], or nil when the
        # value pads nothing.
        def parse_collection_insets(value)
          parts = case value
                  when Array then value
                  when String
                    return nil if value.strip.empty?

                    has_binding?(value) && !value.include?('|') ? [value] : value.split('|', -1)
                  else return nil
                  end
          values = parts.map do |part|
            expr = has_binding?(part.to_s) ? bound_value_expr(part.to_s) : nil
            expr ? "(Number(#{expr}) || 0)" : inset_number(part)
          end
          return nil if values.empty? || values.any?(&:nil?)

          case values.length
          when 1 then [values[0]] * 4
          when 2 then [values[0], values[1], values[0], values[1]]
          when 4 then values
          end
        end

        # One inset value: a number, or a string that is one; else nil.
        def inset_number(value)
          number = case value
                   when Numeric then value
                   when String then Float(value.strip, exception: false)
                   end
          return nil if number.nil? || !number.finite?

          number
        end

        def add_edge(edge, extra)
          return edge if extra.nil? || extra.zero?
          return "(#{edge} + #{css_px(extra)})" if edge.is_a?(String)

          edge + extra
        end

        # A number as CSS writes it: 30, not 30.0.
        def css_px(number)
          number == number.to_i ? number.to_i : number
        end

        # The vertical scroll container of the grid routes, as the list and
        # the flow are one: `overflow-y-auto` unless `lazy: none` (a bound
        # `lazy` switches it at run time) or `scrollEnabled: false`. The grid
        # had none until jsonui-cli 1.9.0, so a grid of a declared height
        # drew its overflow past its box, and a scrollTo — which scrolls the
        # Collection's own box (collectionScroll's scrollCollectionToCell) —
        # moved nothing.
        def vertical_scroll_classes(is_lazy, lazy_expr)
          return [] unless is_lazy && attributes['scrollEnabled'] != false

          dynamic_styles['overflowY'] = "#{lazy_expr} === 'none' ? 'visible' : 'auto'" if lazy_expr
          ['overflow-y-auto']
        end

        # A grid's or a flow's gaps (attribute_semantics.json ->
        # collectionSpacing): between rows lineSpacing, else itemSpacing;
        # between columns columnSpacing, else itemSpacing; each else none (0).
        # `columnSpacing` spaces only the columns. Until jsonui-cli 1.9.0 a
        # columnSpacing with no lineSpacing wrote `gap-[x]`, which spaced the
        # rows by it too, and itemSpacing did not reach the rows when a
        # columnSpacing was declared. (`spacing` is the undeclared legacy
        # spelling of itemSpacing this path has always read.)
        def grid_gap_classes
          line = attributes['lineSpacing']
          column = attributes['columnSpacing']
          both = attributes['itemSpacing'] || attributes['spacing']
          return both ? ["gap-#{TailwindMapper.spacing_value(both)}"] : [] if line.nil? && column.nil?

          row = line || both
          col = column || both
          [[col && "gap-x-#{TailwindMapper.spacing_value(col)}", row && "gap-y-#{TailwindMapper.spacing_value(row)}"].compact.join(' ')]
        end

        def grid_row_gap
          attributes['lineSpacing'] || attributes['itemSpacing'] || attributes['spacing']
        end

        # A grid per section (4f round 9): with two or more sections that
        # draw cells, or a declared header or footer, each section is a grid
        # of its own in a column of blocks — its header a full-width row above
        # it, its footer below — so a section's cells start a row of their
        # own and a header spans the row, as sjui (a LazyVGrid per section)
        # and kjui (full-span header items, a filler to end a part-filled
        # row) draw it. Until jsonui-cli 1.9.0 every section went into the one
        # grid: a header was one grid item beside the cells and section 2
        # continued section 1's last row.
        def grid_per_section?
          return false if flow_collection? || horizontal_collection?
          return false unless extract_collection_binding(attributes['items'])

          raw = attributes['columnCount'] || attributes['columns']
          return false unless (raw.is_a?(String) && has_binding?(raw)) || (raw || 1).to_i != 1

          sections = (attributes['sections'] || []).select { |section| section.is_a?(Hash) }
          sections.count { |section| section['cell'] } > 1 || sections.any? { |section| section['header'] || section['footer'] }
        end

        # One section's grid: the section's own `columns`, else the
        # Collection's (a bound count as the style it is on the one-grid
        # route), and the grid gaps.
        def grid_section_open(section, indent)
          own = section['columns']
          raw = attributes['columnCount'] || attributes['columns']
          classes = ['grid']
          style = ''
          if own.is_a?(Numeric) && own.to_i.positive?
            classes << "grid-cols-#{own.to_i}"
          elsif raw.is_a?(String) && has_binding?(raw)
            style = " style={{ gridTemplateColumns: `repeat(${#{extract_binding_property(raw)}}, minmax(0, 1fr))` }}"
          else
            classes << "grid-cols-#{raw || 1}"
          end
          classes.concat(grid_gap_classes)
          "#{indent_str(indent)}<div className=\"#{classes.join(' ')}\"#{style}>"
        end

        # A flow per section (4f ruling, 2026-09-26): with two or more
        # sections that draw cells, each section wraps in a block of its own,
        # one under the other — sjui's FlowLayout per section in a VStack,
        # kjui's FlowRow per section in a Column (the same count decides it
        # there). Until jsonui-cli 1.9.0 every section went into the one
        # wrap, so section 2 continued section 1's last line.
        def flow_per_section?
          return false unless flow_collection? && extract_collection_binding(attributes['items'])

          sections = (attributes['sections'] || []).select { |section| section.is_a?(Hash) }
          # A declared header or footer is a row of its own too (round 7).
          sections.count { |section| section['cell'] } > 1 || sections.any? { |section| section['header'] || section['footer'] }
        end

        #: listStyle -> the chrome that draws it. Enumerated from the SSoT
        #: (plain / grouped / insetGrouped / sidebar, TableConverter's own
        #: vocabulary); an unrecognised value falls back to plain, which is
        #: the declared default. The greys are the iOS system list colours
        #: (#C6C6C8 separator, #F2F2F7 grouped background) — the same
        #: constants the chrome imitates. The spacing is rem (16px / 8px at the
        #: default root), as every spacing is (TailwindMapper.spacing_value).
        #: The chrome stays inside the declared box: insetGrouped's inset is
        #: padding, and its rounded fill is clipped to the inset, the order
        #: KotlinJsonUI draws it in (padding, clip, background). A margin
        #: moved the box itself — x 16 on web where the declaration puts it at
        #: x 0 (frame-parity inventory 2026-10-05; ticket
        #: rjui-insetgrouped-collection-moves-its-own-box).
        LIST_STYLE_CHROME = {
          'plain' => [].freeze,
          'grouped' => %w[bg-[#F2F2F7]].freeze,
          'insetgrouped' => %w[bg-[#F2F2F7] px-[1rem] [clip-path:inset(0_1rem_round_10px)]].freeze,
          'sidebar' => %w[bg-[#F2F2F7] rounded-[8px] px-[0.5rem]].freeze
        }.freeze

        # The List chrome, or nothing when the collection never asked to be
        # drawn as a list. DECLARATION-GATED on purpose: the web has no native
        # List widget, so an undeclared collection keeps today's bare flex
        # column and no existing layout gains separators by default. Declaring
        # `listStyle` (any value, `plain` included) is what opts the
        # collection into list chrome. Sectioned single-column collections
        # come along too (2026-08-08): SwiftUI's List holds Sections
        # natively, the android chrome already applies on its sectioned lazy
        # path, and the ios face now takes the sectioned List path — the
        # three faces agree on the WIDER gate, not the old unsectioned one.
        def list_style_classes
          style = attributes['listStyle']
          return [] unless style.is_a?(String) && !style.empty?

          chrome = LIST_STYLE_CHROME[JsonUIShared::EnumSpelling.lowered(style, 'Collection', 'listStyle')] || LIST_STYLE_CHROME['plain']
          chrome + separator_classes
        end

        # The row separators the list draws — unless hideSeparator says not
        # to. ORTHOGONAL to listStyle by contract (attribute_semantics ->
        # collectionSeparators): this method answers only the separator
        # question, list_style_classes only the chrome one. Outside a List
        # context the container draws no separators, so hideSeparator is the
        # ruled vacuous no-op there — nothing to remove.
        def separator_classes
          hide = attributes['hideSeparator']
          return [] if hide == true || hide == 'true'

          %w[divide-y divide-[#C6C6C8]]
        end

        # Fixed per-cell size (cellWidth / cellHeight), as the style attr for
        # the sizing wrapper each cell renders into — or nil when neither is
        # declared, in which case no wrapper is emitted at all and the DOM
        # keeps its current shape. The canonical semantics (sjui, the
        # declaring implementation) apply the size to the cell view AFTER it
        # is built, overriding whatever the cell layout asked for; a fixed
        # wrapper box that clips its content is the CSS spelling of that
        # override. `shrink-0` keeps the fixed size honest inside the
        # horizontal flex container.
        def cell_size_style
          height = cell_size_px(attributes['cellHeight'])
          width = cell_size_px(attributes['cellWidth'])
          return nil unless height || width

          pairs = {}
          pairs['width'] = "'#{width}px'" if width
          pairs['height'] = "'#{height}px'" if height
          style_attr_for(pairs)
        end

        # A number passes through; its numeric-string spelling takes the SAME
        # path (plan 43's C3 rule — `"8"` and `8` are two spellings of one
        # value and must emit one text). Anything else is not a size.
        def cell_size_px(value)
          return value if value.is_a?(Numeric)
          if value.is_a?(String) && value.match?(/\A-?\d+(\.\d+)?\z/)
            return value.include?('.') ? value.to_f : value.to_i
          end

          nil
        end

        private

        def generate_collection_content(indent)
          sections = attributes['sections'] || []
          items_binding = extract_collection_binding(attributes['items'])

          content_lines = []

          if sections.any?
            # Section-based rendering. No `items`: nothing to draw the
            # sections from — no header, cell or footer, as sjui and kjui
            # codegen draw. Until jsonui-cli 1.9.0 this wrote each section's
            # header and footer reading `?.sections` off nothing
            # (`data={?.sections?.[0]?.header || {}}`, which is not JSX) and
            # one cell with no data.
            if items_binding && (flow_per_section? || grid_per_section?)
              # Each section: its header, a row of its own above the block;
              # the block of its cells — a wrap on the flow, a grid on the
              # grid; its footer below (4f ruling 2026-09-26, round 7; the
              # grid round 9) — rows of the flex column, full width, spaced
              # as the lines. Until jsonui-cli 1.9.0 the header and footer
              # sat inside the wrap / grid, items on the cells' line.
              wrap = (['flex flex-row flex-wrap content-start'] + grid_gap_classes).join(' ')
              sections.each_with_index do |section, section_index|
                edge = section_edge_line(section, 'header', section_index, items_binding, indent)
                content_lines << edge if edge
                if section.is_a?(Hash) && section['cell']
                  content_lines << (flow_per_section? ? "#{indent_str(indent)}<div className=\"#{wrap}\">" : grid_section_open(section, indent))
                  content_lines << generate_section_content(section, section_index, items_binding, indent + 2, edges: false)
                  content_lines << "#{indent_str(indent)}</div>"
                end
                edge = section_edge_line(section, 'footer', section_index, items_binding, indent)
                content_lines << edge if edge
              end
            elsif items_binding
              # A pager's pages are its cells, every drawn section in order
              # (4f ruling 2026-09-26, round 6) — a section's header and footer
              # are not pages, as sjui's TabView, kjui's HorizontalPager and
              # both Dynamic pagers draw. Until jsonui-cli 1.9.0 they were
              # children of the snap container here, each a page of its own
              # with no `_item_` address.
              edges = !paging?
              sections.each_with_index do |section, section_index|
                content = generate_section_content(section, section_index, items_binding, indent, edges: edges)
                content_lines << content unless content.empty?
              end
            end
          else
            # Legacy cellClasses-based rendering
            content_lines << generate_legacy_content(indent)
          end

          content_lines.join("\n")
        end

        # A section's header or footer: its view with the section's data, and
        # only when the section has that data — as sjui (`if let headerData =
        # section.header?.data`), kjui (`section.header?.let`) and both Dynamic
        # renderers draw it (4f ruling 2026-09-26, round 8). Until jsonui-cli
        # 1.9.0 it was drawn with `{}` when the section had none, on every
        # route.
        def section_edge_line(section, kind, section_index, items_binding, indent)
          view = section.is_a?(Hash) && extract_view_name(section[kind])
          return nil unless view

          edge = "#{items_binding}?.sections?.[#{section_index}]?.#{kind}"
          "#{indent_str(indent)}{#{edge} && <#{view} data={#{edge}} />}"
        end

        # `edges: false` leaves the header and footer to the caller (the
        # flow, which draws them as rows around the section's wrap).
        def generate_section_content(section, section_index, items_binding, indent, edges: true)
          lines = []

          header_view = extract_view_name(section['header'])
          cell_view = extract_view_name(section['cell'])
          footer_view = extract_view_name(section['footer'])
          cell_id_prop = attributes['cellIdProperty']
          auto_tracking = attributes['autoChangeTrackingId'] == true

          # Header
          lines << section_edge_line(section, 'header', section_index, items_binding, indent) if header_view && edges

          # Cells with map
          if cell_view && items_binding
            cell_cast = config['typescript'] ? " as unknown as #{cell_view}Data" : ''
            source_expr = "(#{items_binding}?.sections?.[#{section_index}]?.cells?.data ?? [])"
            item_index = paging_item_index(section_index, items_binding)
            # Wrap the key in String(...) so the result always conforms to
            # React's Key type (string | number) even when cellData is typed
            # as a user-defined closed shape. Bracket-indexing cellId avoids
            # TS2322 on T types that don't declare cellId as a member.
            # Cast to Record<string, unknown> in TS mode because
            # CollectionDataSource<T = unknown> leaves cellData: unknown,
            # and `unknown[...]` is a TS18046 error.
            key_expr =
              if auto_tracking && cell_id_prop
                'String(cellData.cellId ?? cellIndex)'
              elsif cell_id_prop
                if config['typescript']
                  cast = '(cellData as Record<string, unknown>)'
                  "String(#{cast}[\"cellId\"] ?? #{cast}[\"#{cell_id_prop}\"] ?? cellIndex)"
                else
                  "String(cellData[\"cellId\"] ?? cellData[\"#{cell_id_prop}\"] ?? cellIndex)"
                end
              else
                'cellIndex'
              end

            lanes = horizontal_lanes(section)
            if lanes
              lines << horizontal_lanes_open(lanes, indent)
              indent += 2
            end
            if auto_tracking && cell_id_prop
              lines << "#{indent_str(indent)}{enrichCellIds(#{source_expr}, \"#{cell_id_prop}\").map((cellData, cellIndex) => ("
            else
              lines << "#{indent_str(indent)}{#{source_expr}.map((cellData, cellIndex) => ("
            end
            # cellWidth / cellHeight: the sizing wrapper is the map's outer
            # element, so the React key moves onto it — a key inside the
            # wrapper is a key React never sees.
            if (cell_size = cell_size_style)
              lines << "#{indent_str(indent + 2)}<div key={#{key_expr}} className=\"shrink-0 overflow-hidden\"#{cell_size}>"
              lines << "#{indent_str(indent + 4)}<#{cell_view}#{cell_item_id_attr(item_index)} data={cellData#{cell_cast}} />"
              lines << "#{indent_str(indent + 2)}</div>"
            else
              lines << "#{indent_str(indent + 2)}<#{cell_view} key={#{key_expr}}#{cell_item_id_attr(item_index)} data={cellData#{cell_cast}} />"
            end
            lines << "#{indent_str(indent)}))}"
            if lanes
              indent -= 2
              lines << "#{indent_str(indent)}</div>"
            end
          end

          # Footer
          lines << section_edge_line(section, 'footer', section_index, items_binding, indent) if footer_view && edges

          lines.join("\n")
        end

        # A paging Collection's item address counts across the sections — a
        # page's place among all the pages, as sjui's page tag and kjui's
        # pager index do (4f ruling 2026-09-26, round 7): the cells of the
        # drawn sections before this one, then its own index. Until
        # jsonui-cli 1.9.0 each section's items were `<id>_item_0…` again.
        # Every other route, and a pager's first drawn section, keep
        # `cellIndex`.
        def paging_item_index(section_index, items_binding)
          return 'cellIndex' unless paging?

          before = (attributes['sections'] || []).first(section_index).each_with_index
                                                 .select { |section, _| section.is_a?(Hash) && section['cell'] }
                                                 .map { |_, index| "(#{items_binding}?.sections?.[#{index}]?.cells?.data?.length ?? 0)" }
          before.empty? ? 'cellIndex' : "#{before.join(' + ')} + cellIndex"
        end

        # A horizontal paging Collection: a pager, one cell per page.
        def paging?
          horizontal_collection? && attributes['paging'] == true
        end

        # `{collectionId}_item_{index}` identifier for each cell (kjui
        # testTag parity — jsonui-test-runner's tapItem clicks `#id`).
        # Generated components apply the `id` prop to their root element.
        # Only a literal collection id qualifies; without one, tapItem has
        # no way to address the collection anyway.
        def cell_item_id_attr(index_var)
          collection_id = attributes['id']
          return '' unless collection_id.is_a?(String) && !collection_id.empty? && !collection_id.include?('@{')

          " id={`#{collection_id}_item_${#{index_var}}`}"
        end

        # The class-list shape — `cellClasses` (with `headerClasses` /
        # `footerClasses`), `items` and no `sections` — drawn as sjui codegen
        # draws it (the route table kjui codegen and both Dynamic renderers
        # follow, 4f ruling 2026-09-26), from the data's own sections:
        #
        #   vertical (list, grid, lazy:none)   every data section; header before, footer after
        #   horizontal, flow, paging           the first data section; no header / footer
        #
        # (paging: a snap child per cell — 4f ruling 2026-09-26, round 6; it
        # drew nothing until jsonui-cli 1.9.0)
        #
        # A header / footer is its view with no data. No `items`: no cell
        # (the shared LayoutValidator names it) — until jsonui-cli 1.9.0 this
        # path drew one cell with no data, on every route. Until jsonui-cli 1.9.0
        # the cells mapped `items` itself as an array — `data.rows?.map(…)`,
        # which a CollectionDataSource (the type every face gives a Collection's
        # items) does not have: tsc TS2339 "Property 'map' does not exist on
        # type 'CollectionDataSource'" (measured on 798f6e64, 2026-09-26) — and
        # the header and footer were drawn on every route.
        def generate_legacy_content(indent)
          lines = []

          cell_classes = attributes['cellClasses'] || []
          header_classes = attributes['headerClasses'] || []
          footer_classes = attributes['footerClasses'] || []

          cell_view = extract_view_name(cell_classes.first) if cell_classes.any?
          header_view = extract_view_name(header_classes.first) if header_classes.any?
          footer_view = extract_view_name(footer_classes.first) if footer_classes.any?

          items_binding = extract_collection_binding(attributes['items'])
          # An items property declared as a list (`Array`, `[T]`) is one
          # section — the cells mapped over it, as this path has always drawn
          # it (4f ruling, 2026-09-26, Collection.items: a CollectionDataSource
          # or an array). Its header, footer and cells are written as they
          # were, on every route.
          return legacy_array_content(indent, cell_view, header_view, footer_view, items_binding) if legacy_items_list_element

          first_only = flow_collection? || horizontal_collection?
          edges = !first_only

          lines << "#{indent_str(indent)}<#{header_view} />" if header_view && edges

          if cell_view && items_binding
            cast = config['typescript'] ? " as unknown as #{cell_view}Data" : ''
            if first_only
              lanes = horizontal_lanes
              if lanes
                lines << horizontal_lanes_open(lanes, indent)
                indent += 2
              end
              lines << "#{indent_str(indent)}{(#{items_binding}?.sections?.[0]?.cells?.data ?? []).map((cellData, cellIndex) => ("
              lines.concat(legacy_cell_lines(cell_view, 'cellIndex', "cellData#{cast}", indent + 2))
              lines << "#{indent_str(indent)}))}"
              if lanes
                indent -= 2
                lines << "#{indent_str(indent)}</div>"
              end
            else
              lines << "#{indent_str(indent)}{(#{items_binding}?.sections ?? []).map((section, sectionIndex) =>"
              lines << "#{indent_str(indent + 2)}(section.cells?.data ?? []).map((cellData, cellIndex) => ("
              lines.concat(legacy_cell_lines(cell_view, '`${sectionIndex}_${cellIndex}`', "cellData#{cast}", indent + 4))
              lines << "#{indent_str(indent + 2)}))"
              lines << "#{indent_str(indent)})}"
            end
          elsif !cell_view
            lines << "#{indent_str(indent)}{/* No cellClasses specified */}"
          end

          lines << "#{indent_str(indent)}<#{footer_view} />" if footer_view && edges

          lines.join("\n")
        end

        # The element type of the list the class-list `items` binds (the
        # layout's own `data` declaration, AttributeTypes.list_element), or
        # nil — a CollectionDataSource, or no declaration (the canonical
        # CollectionDataSource).
        def legacy_items_list_element
          items = attributes['items']
          return nil unless items.is_a?(String) && (name = items[/\A@\{\s*([A-Za-z_]\w*)\s*\}\z/, 1])

          JsonUIShared::AttributeTypes.list_element((config['_data_classes'] || {})[name])
        end

        # A class-list Collection whose items are a list: every item with
        # cellClasses[0], the header before and the footer after — what this
        # path wrote until jsonui-cli 1.9.0, kept as it was, except that the
        # map's `index: number` is TypeScript's only (a .jsx file wrote it too,
        # and it does not parse there).
        def legacy_array_content(indent, cell_view, header_view, footer_view, items_binding)
          lines = []
          lines << "#{indent_str(indent)}<#{header_view} />" if header_view
          if cell_view
            item_type = typescript? ? ": #{cell_view}Data" : ''
            index_type = typescript? ? ': number' : ''
            lanes = horizontal_lanes
            if lanes
              lines << horizontal_lanes_open(lanes, indent)
              indent += 2
            end
            lines << "#{indent_str(indent)}{#{items_binding}?.map((item#{item_type}, index#{index_type}) => ("
            if (cell_size = cell_size_style)
              lines << "#{indent_str(indent + 2)}<div key={index} className=\"shrink-0 overflow-hidden\"#{cell_size}>"
              lines << "#{indent_str(indent + 4)}<#{cell_view}#{cell_item_id_attr('index')} data={item} />"
              lines << "#{indent_str(indent + 2)}</div>"
            else
              lines << "#{indent_str(indent + 2)}<#{cell_view} key={index}#{cell_item_id_attr('index')} data={item} />"
            end
            lines << "#{indent_str(indent)}))}"
            if lanes
              indent -= 2
              lines << "#{indent_str(indent)}</div>"
            end
          else
            lines << "#{indent_str(indent)}{/* No cellClasses specified */}"
          end
          lines << "#{indent_str(indent)}<#{footer_view} />" if footer_view
          lines.join("\n")
        end

        # One class-list cell; the key rides the outermost element of the map
        # (the section path's wrapper contract).
        def legacy_cell_lines(cell_view, key_expr, data_expr, indent)
          if (cell_size = cell_size_style)
            ["#{indent_str(indent)}<div key={#{key_expr}} className=\"shrink-0 overflow-hidden\"#{cell_size}>",
             "#{indent_str(indent + 2)}<#{cell_view}#{cell_item_id_attr('cellIndex')} data={#{data_expr}} />",
             "#{indent_str(indent)}</div>"]
          else
            ["#{indent_str(indent)}<#{cell_view} key={#{key_expr}}#{cell_item_id_attr('cellIndex')} data={#{data_expr}} />"]
          end
        end

        # The component a class reference names — the same name the import
        # and the cell Data type use (React::ComponentName).
        def extract_view_name(class_info)
          ComponentName.for_reference(class_info)
        end

        def to_pascal_case(string)
          string.split('_').map(&:capitalize).join
        end

        # `items` only. `bind` was read as the items when `items` was absent
        # (BaseConverter#with_bind_fallback) — rjui was the one path that did;
        # sjui, kjui and both Dynamics never read it, so a Collection bound by
        # `bind` drew on web and nowhere else. `bind` is not a Collection's
        # data source; the validator says so (ticket
        # collection-attributes-declared-but-not-drawn-on-some-paths).
        def extract_collection_binding(items_property)
          return nil unless items_property.is_a?(String)
          return nil unless has_binding?(items_property)

          extract_binding_property(items_property)
        end
      end
    end
  end
end
