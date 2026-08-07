# frozen_string_literal: true

require_relative 'base_converter'

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

          content = generate_collection_content(indent + 2)

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr}#{ref_attr} className="#{class_name}"#{style_attr}#{scroll_attr}#{testid_attr}#{tag_attr}>
            #{content}
            #{indent_str(indent)}</div>
          JSX

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
          layout.to_s.downcase == 'horizontal'
        end

        # layout: flow — wrapping layout, packed to the top-left. Unified
        # 2026-08-03: 'LeftAligned' IS flow (the accepted spellings survive
        # as aliases, same case-insensitive read sjui/kjui use for 'Flow').
        # sjui renders a custom flow layout, kjui a FlowRow; the CSS shape
        # of the same thing is a wrapping flex row.
        def flow_collection?
          layout = attributes['orientation'] || attributes['layout'] || ''
          %w[flow leftaligned].include?(layout.to_s.downcase)
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
            'onItemAppear' => attributes['onItemAppear']
          }.compact.keys
        end

        def build_collection_ref_attr
          declared = scroll_control_attrs
          return '' if declared.empty?

          id = scroll_control_id
          unless id
            warn "[rjui] Collection: #{declared.join(', ')} #{declared.one? ? 'needs' : 'need'} " \
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
          current_page = attributes['currentPage']
          return '' unless current_page.is_a?(String) && has_binding?(current_page)
          return '' unless scroll_control_id

          prop = extract_binding_property(current_page)
          handler = "data.on#{capitalize_first(extract_raw_binding_property(current_page))}Change"
          " onScroll={() => { const page = currentCollectionPage(#{ref_var}, #{horizontal_collection?}); " \
            "if (page !== #{prop}) #{handler}?.(page); }}"
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
          classes = [super]

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
            classes << 'flex flex-row flex-wrap content-start'
            if is_lazy && attributes['scrollEnabled'] != false
              classes << 'overflow-y-auto'
              dynamic_styles['overflowY'] = "#{lazy_expr} === 'none' ? 'visible' : 'auto'" if lazy_expr
            end
            # lineSpacing = gap between wrapped lines, itemSpacing = gap
            # within a line (the grid branch's row/column mapping).
            # `columnSpacing` is the SSoT's own name for the column gap and
            # was read only in the horizontal branch — a flow or grid
            # Collection ignored it, which is every Collection that declares
            # `columns` (plan 34: pixel-identical to its control on web while
            # both mobile platforms honoured it).
            row_gap = attributes['lineSpacing']
            col_gap = attributes['columnSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            if row_gap && col_gap
              classes << "gap-x-[#{col_gap}px] gap-y-[#{row_gap}px]"
            elsif row_gap
              classes << "gap-y-[#{row_gap}px]"
            elsif col_gap
              classes << "gap-[#{col_gap}px]"
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
            # For horizontal: columnSpacing (or lineSpacing/itemSpacing) = gap between items
            spacing = attributes['columnSpacing'] || attributes['lineSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            classes << "gap-[#{spacing}px]" if spacing
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
            classes << "gap-[#{spacing}px]" if spacing
            # listStyle / hideSeparator — the List chrome, on the one branch
            # that IS a list (sjui parity: TableConverter takes the List path
            # only for the unsectioned single-column shape).
            classes.concat(list_style_classes)
          else
            # Grid layout
            classes << 'grid'
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
            # lineSpacing for row gap, columnSpacing/itemSpacing for column gap
            row_gap = attributes['lineSpacing']
            col_gap = attributes['columnSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            if row_gap && col_gap
              classes << "gap-x-[#{col_gap}px] gap-y-[#{row_gap}px]"
            elsif row_gap
              classes << "gap-y-[#{row_gap}px]"
            elsif col_gap
              classes << "gap-[#{col_gap}px]"
            end
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
            classes << "pt-[#{top}px]" if top&.positive?
            classes << "pl-[#{left}px]" if left&.positive?
            classes << "pb-[#{bottom}px]" if bottom&.positive?
            classes << "pr-[#{right}px]" if right&.positive?
          end

          # insetVertical — vertical content padding (the UIKit content
          # inset's vertical half).
          if attributes['insetVertical'].is_a?(Numeric)
            classes << "py-[#{attributes['insetVertical']}px]"
          end

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

        #: listStyle -> the chrome that draws it. Enumerated from the SSoT
        #: (plain / grouped / insetGrouped / sidebar, TableConverter's own
        #: vocabulary); an unrecognised value falls back to plain, which is
        #: the declared default. The greys are the iOS system list colours
        #: (#C6C6C8 separator, #F2F2F7 grouped background) — the same
        #: constants the chrome imitates.
        LIST_STYLE_CHROME = {
          'plain' => [].freeze,
          'grouped' => %w[bg-[#F2F2F7]].freeze,
          'insetgrouped' => %w[bg-[#F2F2F7] rounded-[10px] mx-[16px]].freeze,
          'sidebar' => %w[bg-[#F2F2F7] rounded-[8px] px-[8px]].freeze
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

          chrome = LIST_STYLE_CHROME[style.downcase] || LIST_STYLE_CHROME['plain']
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
          items_binding = extract_collection_binding(with_bind_fallback(attributes['items']))

          content_lines = []

          if sections.any?
            # Section-based rendering
            sections.each_with_index do |section, section_index|
              content_lines << generate_section_content(section, section_index, items_binding, indent)
            end
          else
            # Legacy cellClasses-based rendering
            content_lines << generate_legacy_content(indent)
          end

          content_lines.join("\n")
        end

        def generate_section_content(section, section_index, items_binding, indent)
          lines = []

          header_view = extract_view_name(section['header'])
          cell_view = extract_view_name(section['cell'])
          footer_view = extract_view_name(section['footer'])
          cell_id_prop = attributes['cellIdProperty']
          auto_tracking = attributes['autoChangeTrackingId'] == true

          # Header
          if header_view
            lines << "#{indent_str(indent)}<#{header_view} data={#{items_binding}?.sections?.[#{section_index}]?.header || {}} />"
          end

          # Cells with map
          if cell_view && items_binding
            cell_cast = config['typescript'] ? " as unknown as #{cell_view}Data" : ''
            source_expr = "(#{items_binding}?.sections?.[#{section_index}]?.cells?.data ?? [])"
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
              lines << "#{indent_str(indent + 4)}<#{cell_view}#{cell_item_id_attr('cellIndex')} data={cellData#{cell_cast}} />"
              lines << "#{indent_str(indent + 2)}</div>"
            else
              lines << "#{indent_str(indent + 2)}<#{cell_view} key={#{key_expr}}#{cell_item_id_attr('cellIndex')} data={cellData#{cell_cast}} />"
            end
            lines << "#{indent_str(indent)}))}"
          elsif cell_view
            # Placeholder for static content
            lines << "#{indent_str(indent)}{/* Cells for section #{section_index} */}"
            lines << "#{indent_str(indent)}<#{cell_view} />"
          end

          # Footer
          if footer_view
            lines << "#{indent_str(indent)}<#{footer_view} data={#{items_binding}?.sections?.[#{section_index}]?.footer || {}} />"
          end

          lines.join("\n")
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

        def generate_legacy_content(indent)
          lines = []

          cell_classes = attributes['cellClasses'] || []
          header_classes = attributes['headerClasses'] || []
          footer_classes = attributes['footerClasses'] || []

          cell_view = extract_view_name(cell_classes.first) if cell_classes.any?
          header_view = extract_view_name(header_classes.first) if header_classes.any?
          footer_view = extract_view_name(footer_classes.first) if footer_classes.any?

          items_binding = extract_collection_binding(with_bind_fallback(attributes['items']))

          # Header
          if header_view
            if items_binding
              lines << "#{indent_str(indent)}<#{header_view} data={#{items_binding}?.header || {}} />"
            else
              lines << "#{indent_str(indent)}<#{header_view} />"
            end
          end

          # Cells placeholder
          if cell_view
            if items_binding
              # Add type annotation for TypeScript
              item_type = config['typescript'] ? ": #{cell_view}Data" : ''
              lines << "#{indent_str(indent)}{#{items_binding}?.map((item#{item_type}, index: number) => ("
              # Same wrapper contract as the section path: the key rides the
              # outermost element of the map.
              if (cell_size = cell_size_style)
                lines << "#{indent_str(indent + 2)}<div key={index} className=\"shrink-0 overflow-hidden\"#{cell_size}>"
                lines << "#{indent_str(indent + 4)}<#{cell_view}#{cell_item_id_attr('index')} data={item} />"
                lines << "#{indent_str(indent + 2)}</div>"
              else
                lines << "#{indent_str(indent + 2)}<#{cell_view} key={index}#{cell_item_id_attr('index')} data={item} />"
              end
              lines << "#{indent_str(indent)}))}"
            else
              lines << "#{indent_str(indent)}{/* Add items prop to render cells */}"
              lines << "#{indent_str(indent)}<#{cell_view} />"
            end
          else
            lines << "#{indent_str(indent)}{/* No cellClasses specified */}"
          end

          # Footer
          if footer_view
            if items_binding
              lines << "#{indent_str(indent)}<#{footer_view} data={#{items_binding}?.footer || {}} />"
            else
              lines << "#{indent_str(indent)}<#{footer_view} />"
            end
          end

          lines.join("\n")
        end

        def extract_view_name(class_info)
          return nil unless class_info

          class_name = if class_info.is_a?(Hash)
                         class_info['className']
                       elsif class_info.is_a?(String)
                         class_info
                       end

          return nil unless class_name

          # Handle path-based component references like "components/attribute_row"
          if class_name.include?('/')
            # Extract the last part of the path and convert to PascalCase
            base_name = class_name.split('/').last
            return to_pascal_case(base_name)
          end

          # Layout-file view names ("conformance_cell") resolve exactly like
          # the path branch above: the component rjui build generates from
          # conformance_cell.json is ConformanceCell — the same name
          # extract_included_components imports and
          # extract_collection_cell_types types against. The UIKit-suffix
          # heuristics below are for migrated UIKit CLASS names, which are
          # always PascalCase; running a snake_case name through them emitted
          # "conformance_CellView", a component that exists nowhere.
          return to_pascal_case(class_name) if class_name.include?('_') || class_name.match?(/^[a-z]/)

          # If already PascalCase React component name (starts with uppercase, no underscores),
          # use as-is without appending 'View'
          if class_name.match?(/^[A-Z]/) && !class_name.include?('_') &&
             !class_name.end_with?('Cell') && !class_name.end_with?('CollectionViewCell')
            return class_name
          end

          # Convert UIKit cell class name to React component name
          # InformationListCollectionViewCell -> InformationListView
          # SomeCell -> SomeCellView
          if class_name.end_with?('CollectionViewCell')
            class_name.sub(/CollectionViewCell$/, 'View')
          elsif class_name.end_with?('cell')
            class_name.sub(/cell$/, 'Cell') + 'View'
          elsif class_name.end_with?('Cell')
            class_name + 'View'
          elsif !class_name.end_with?('View')
            class_name + 'View'
          else
            class_name
          end
        end

        def to_pascal_case(string)
          string.split('_').map(&:capitalize).join
        end

        def extract_collection_binding(items_property)
          return nil unless items_property.is_a?(String)
          return nil unless has_binding?(items_property)

          extract_binding_property(items_property)
        end
      end
    end
  end
end
