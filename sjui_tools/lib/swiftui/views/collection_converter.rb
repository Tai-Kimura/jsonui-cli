#!/usr/bin/env ruby

require_relative 'base_view_converter'
require_relative 'responsive_helper'
require_relative '../../core/responsive_resolver'

module SjuiTools
  module SwiftUI
    module Views
      class CollectionConverter < BaseViewConverter
        def initialize(component, indent_level = 0, action_manager = nil, binding_registry = nil, data_properties = [])
          super(component, indent_level, action_manager, binding_registry)
          @data_properties = data_properties || []
        end

        # Top-level entry: when a `responsive` block is present, regenerate the
        # collection per size-class branch with the merged attrs. Collection is
        # not a generic container (no children closure), so view_converter's
        # responsive wrapper can't host it — we have to handle it locally.
        def convert
          if JsonUIShared::ResponsiveResolver.responsive?(@component)
            return convert_responsive
          end

          convert_non_responsive
        end

        # Resolve the `columns` attribute into its Swift emit form. A literal
        # int returns `{ expr: "5", literal: 5, is_binding: false }`; a
        # `@{prop}` binding returns `{ expr: "data.prop", literal: nil,
        # is_binding: true }`. The caller interpolates `expr` into
        # `Array(repeating: ..., count: ...)` and uses `is_binding` to
        # suppress compile-time fast-paths (single-column list, etc.) that
        # require a known column count.
        def columns_info
          # itemWeight has its say first (mirror of the dynamic face's
          # effectiveGridColumns): a weight is a per-ITEM width, and in a
          # spacing-0 grid "each item is W×w wide" IS "round(1/w) flexible
          # columns" — so the weight wins over a conflicting `columns`
          # declaration, the same way the UIKit layout
          # (SJUICollectionView.getCollectionViewLayout) never consults
          # `columns` for item sizing.
          if (count = item_weight_count)
            return { expr: count.to_s, literal: count, is_binding: false }
          end
          value = @component['columns']
          if value.is_a?(String) && is_binding?(value)
            { expr: "data.#{extract_binding_property(value)}", literal: nil, is_binding: true }
          else
            literal = (value || 1).to_i
            { expr: literal.to_s, literal: literal, is_binding: false }
          end
        end

        # `itemWeight` as a column count. Declared `number` with no binding
        # form; 0 < w <= 1, anything else inert (same guard the dynamic face
        # and the retired content-level emit used).
        def item_weight_count
          weight = @component['itemWeight']
          return nil if weight.nil?

          value = weight.to_f
          return nil unless value > 0 && value <= 1.0

          (1.0 / value).round
        end

        # True when the runtime column count is unknown or > 1. Used to gate
        # the grid emit path; binding-form columns always take the grid path
        # so a runtime resolution to 5/3 doesn't tear the layout structure.
        def columns_is_multi?
          info = columns_info
          info[:is_binding] || (info[:literal] && info[:literal] > 1)
        end

        # Swift expression for the column count of one section. A literal
        # `section['columns']` override emits as an Int literal. Absent or
        # nil falls back to the parent Collection's `columns` expression
        # (literal or `data.<prop>` binding).
        def section_columns_expr(section)
          if section['columns']
            section['columns'].to_i.to_s
          else
            columns_info[:expr]
          end
        end

        def convert_non_responsive
          id = @component['id'] || 'collection'
          apply_scroll_container_attrs
          info = columns_info
          # Sentinel for downstream control flow: any value > 1 routes
          # through the multi-column grid path. Compile-time LCM with
          # per-section overrides is forfeited for bindings because the
          # runtime column count is unknown.
          columns = info[:literal] || 2
          # Support both 'layout' and 'orientation' attributes for
          # horizontal/vertical; `horizontalScroll: true` is ScrollView's
          # boolean spelling of the same direction (used by real carousels).
          layout = @component['layout'] || @component['orientation'] || 'vertical'
          layout = 'horizontal' if @component['horizontalScroll'] == true
          is_horizontal = layout == 'horizontal'

          # `lazy` accepts one of:
          #   "lazy"  -> ScrollView + LazyVStack/LazyHStack  (default)
          #   "eager" -> ScrollView + VStack/HStack          (no virtualization, smooth for heavy cells)
          #   "none"  -> VStack/HStack only                  (parent already scrollable)
          # `@{prop}` bindings resolve at runtime via CollectionStackMode.
          is_lazy = collection_lazy_mode != :none

          # Check if sections are defined
          sections = @component['sections'] || []

          # Legacy: cellClasses, headerClasses, footerClasses の処理
          cell_classes = @component['cellClasses'] || []
          header_classes = @component['headerClasses'] || []
          footer_classes = @component['footerClasses'] || []

          # Extract the first cell class name (SwiftUI will use this as the view name)
          cell_class_name = extract_view_name(cell_classes.first) if cell_classes.any?
          header_class_name = extract_view_name(header_classes.first) if header_classes.any?
          footer_class_name = extract_view_name(footer_classes.first) if footer_classes.any?

          # setTargetAsDataSource と setTargetAsDelegate
          if @component['setTargetAsDataSource']
            add_line "// setTargetAsDataSource: true"
          end
          if @component['setTargetAsDelegate']
            add_line "// setTargetAsDelegate: true"
          end

          # Create the main collection view structure
          # Use LazyVStack for section-based collections, List for legacy single column
          has_sections = @component['sections'] && !@component['sections'].empty?

          # Case-insensitive: the declared enum admits 'Flow' as well as
          # 'flow', and dynamic reads the value after the runtime
          # normalizer downcases it (same defect measured on kjui as
          # parity d=32 — Collection/layout__flow_2). 'leftAligned' is an
          # alias spelling of flow (SSoT valueAliases, 2026-08-03
          # unification) — dynamic folds it via the generated enum, so the
          # raw-reading codegen must accept it too.
          is_flow = %w[flow leftaligned].include?(layout.to_s.downcase)

          if !is_lazy
            generate_non_lazy(
              columns: columns,
              is_horizontal: is_horizontal,
              has_sections: has_sections,
              is_flow: is_flow,
              cell_class_name: cell_class_name,
              header_class_name: header_class_name,
              footer_class_name: footer_class_name,
              id: id
            )

            # scrollEnabled is a no-op here (no scroll container); skip.
            apply_modifiers(skip_insets: true)
            return generated_code
          end

          if is_flow
            # Flow layout - items wrap naturally based on content size
            generate_flow_layout(has_sections)
          elsif columns == 1 && !is_horizontal && has_sections && @component['listStyle']
            # Sectioned vertical collection WITH list chrome: `listStyle` is
            # what opts a collection into list-ness (the web face words the
            # same gate the same way, and the android chrome already applies
            # on its sectioned lazy path — the three faces agree on the WIDER
            # gate, 2026-08-08). SwiftUI's List holds Sections natively, so
            # the F4 section content renders inside a List instead of
            # CollectionStackView; a chrome-less sectioned collection keeps
            # the CollectionStackView branch below unchanged.
            generate_scroll_reader_open
            hide_separators = [true, 'true'].include?(@component['hideSeparator'])
            add_line "List {"
            indent do
              # listRowSeparator styles ROWS, not the List — a Group forwards
              # the modifier to every row it contains.
              add_line "Group {" if hide_separators
              maybe_indent(hide_separators) do
                generate_collection_content_sections_vertical
              end
              if hide_separators
                add_line "}"
                add_modifier_line ".listRowSeparator(.hidden)"
              end
            end
            add_line "}"
            add_modifier_line ".listStyle(#{list_style_to_swiftui})"
            generate_scroll_reader_close
          elsif columns == 1 && !is_horizontal && has_sections
            # Section-based vertical collection — delegate outer container
            # (ScrollView + LazyVStack/VStack/none) to SwiftJsonUI's
            # CollectionStackView so `lazy: "eager"` etc. become a literal
            # parameter instead of a structural code branch.
            generate_scroll_reader_open
            generate_collection_stack_view_open(axis: :vertical)
            indent do
              generate_collection_content_sections_vertical
            end
            add_line "}"
            generate_scroll_reader_close
          elsif columns == 1 && !is_horizontal && !has_sections &&
                cell_class_name.nil? && header_class_name.nil? && footer_class_name.nil? &&
                @component['listStyle'].nil?
            # Nothing renderable: no declared sections and no cell class to
            # draw the items with. Every other face — web, android (both
            # pipelines) and ios dynamic — renders only the collection's own
            # box; this path fell into the legacy List below and drew a white
            # List holding a placeholder Text per item
            # (control_Collection__no-sections parity d=42, run 31202080745).
            # Same declaration-faithful stance as the 2026-08-02 bare-
            # Collection ruling: undeclared content is not invented.
            # A declared listStyle keeps the List: the chrome belongs to the
            # CONTAINER on every face (web's list_style_classes, android's
            # container-level chrome), so an empty chromed List is the
            # cross-face picture — and short-circuiting it made the spelling
            # unread on this face (C0, ci run 31234713735).
            add_line "// Nothing renderable — nothing rendered (declaration-faithful)"
            add_line "Color.clear"
          elsif columns == 1 && !is_horizontal
            # Legacy single column vertical without sections - use List
            add_line "List {"
            indent do
              # Header
              if header_class_name
                add_line "Section {"
                indent do
                  generate_collection_content(cell_class_name, id)
                end
                add_line "} header: {"
                indent do
                  add_line "#{header_class_name}()"
                end
                add_line "}"

                # Footer
                if footer_class_name
                  add_modifier_line ".listSectionSeparator(.hidden)"
                  add_line "Section {"
                  indent do
                    add_line "#{footer_class_name}()"
                  end
                  add_line "}"
                end
              else
                hide_rows = [true, 'true'].include?(@component['hideSeparator'])
                add_line "Group {" if hide_rows
                maybe_indent(hide_rows) do
                  generate_collection_content(cell_class_name, id)
                end
                if hide_rows
                  add_line "}"
                  # hideSeparator finally has a List to act on here — the row
                  # was C0 (unread) on this face until 2026-08-08.
                  add_modifier_line ".listRowSeparator(.hidden)"
                end

                # Footer without header
                if footer_class_name
                  add_line ""
                  add_line "#{footer_class_name}()"
                end
              end
            end
            add_line "}"
            add_modifier_line ".listStyle(#{list_style_to_swiftui})"
          elsif is_horizontal && @component['paging']
            # Horizontal paging collection - use TabView with page style
            generate_paging_horizontal
          elsif is_horizontal
            # Horizontal scroll collection — delegate outer container
            # (ScrollView + LazyHStack/HStack/none) to SwiftJsonUI's
            # CollectionStackView. inset spacers and scroll-disabled handling
            # live inside the library so the generated cell-content closure
            # is identical across modes.
            generate_scroll_reader_open
            generate_collection_stack_view_open(axis: :horizontal)
            indent do
                # Check if we have sections defined
                if @component['sections'] && !@component['sections'].empty?
                  property_name = extract_property_name(@component['items'])
                  @component['sections'].each_with_index do |section, index|
                    cell_view_name = extract_view_name(section['cell']) if section['cell']

                    if cell_view_name && property_name
                      # Check if property is optional based on data_properties
                      is_optional = is_property_optional?(property_name)

                      if is_optional
                        add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                      else
                        add_line "if data.#{property_name}.sections.count > #{index} {"
                      end
                      indent do
                        if is_optional
                          add_line "let section = dataSource.sections[#{index}]"
                        else
                          add_line "let section = data.#{property_name}.sections[#{index}]"
                        end
                        add_line "if let cellsData = section.cells?.data {"
                        indent do
                          vars = open_cell_foreach('cellsData')
                          indent do
                            add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                            generate_cell_identity(vars[:index_var])

                            apply_cell_frame

                            # Add accessibilityIdentifier for test automation (tapItem action)
                            if @component['id']
                              add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                            end
                          end
                          add_line "}"
                        end
                        add_line "}"
                      end
                      add_line "}"
                    elsif cell_view_name
                      # Fallback: use collectionDataSource
                      original_class_name = section['cell'].is_a?(Hash) ? section['cell']['className'] : section['cell']
                      vars = open_cell_foreach("data.collectionDataSource.getCellData(for: \"#{original_class_name}\")")
                      indent do
                        add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                        generate_cell_identity(vars[:index_var])

                        apply_cell_frame

                        # Add accessibilityIdentifier for test automation (tapItem action)
                        if @component['id']
                          add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                        end
                      end
                      add_line "}"
                    end
                  end
                else
                  # Legacy: no sections defined, use cellClasses
                  cell_class_name = extract_view_name(@component['cellClasses']&.first)
                  if cell_class_name
                    property_name = extract_property_name(@component['items'])
                    if property_name
                      is_optional = is_property_optional?(property_name)
                      if is_optional
                        add_line "if let dataSource = data.#{property_name}, let cellsData = dataSource.sections.first?.cells?.data {"
                      else
                        add_line "if let cellsData = data.#{property_name}.sections.first?.cells?.data {"
                      end
                      indent do
                        vars = open_cell_foreach('cellsData')
                        indent do
                          add_line "#{cell_class_name}(data: #{vars[:data_var]})"
                          generate_cell_identity(vars[:index_var])
                          apply_cell_frame
                          # Add accessibilityIdentifier for test automation (tapItem action)
                          if @component['id']
                            add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                          end
                        end
                        add_line "}"
                      end
                      add_line "}"
                    else
                      # Declaration-faithful (2026-08-02 ruling): no items
                      # binding declared → nothing rendered. The old 10-item
                      # placeholder ForEach was undeclared behavior.
                      add_line "// No items binding — nothing rendered (declaration-faithful)"
                    end
                  else
                    # Declaration-faithful: no cell class declared → nothing
                    # rendered (was a 10-item placeholder ForEach).
                    add_line "// No cellClasses — nothing rendered (declaration-faithful)"
                  end
                end
            end  # End indent for CollectionStackView content
            add_line "}"  # End CollectionStackView
            generate_scroll_reader_close
          else
            # Multiple columns - use ScrollView with LazyVGrid
            shows_indicators = @component['showsVerticalScrollIndicator'] != false
            generate_scroll_reader_open
            add_line "ScrollView(.vertical, showsIndicators: #{shows_indicators}) {"
            indent do
              # Check if we have sections defined
              if @component['sections'] && !@component['sections'].empty?
                # For sections, iterate through sections and render header/cells/footer
                property_name = extract_property_name(@component['items'])
                @component['sections'].each_with_index do |section, index|
                  header_view_name = extract_view_name(section['header']) if section['header']
                  cell_view_name = extract_view_name(section['cell']) if section['cell']
                  footer_view_name = extract_view_name(section['footer']) if section['footer']

                  # Grid with cells - use section columns if specified, otherwise use component columns
                  section_columns = section_columns_expr(section)

                  if property_name
                    # Section wrapper with let binding
                    # Check if property is optional based on data_properties
                    is_optional = is_property_optional?(property_name)

                    add_line "// Section #{index + 1}: #{cell_view_name || 'Unknown'} (#{section_columns} columns)"
                    if is_optional
                      add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                    else
                      add_line "if data.#{property_name}.sections.count > #{index} {"
                    end
                    indent do
                      if is_optional
                        add_line "let section = dataSource.sections[#{index}]"
                      else
                        add_line "let section = data.#{property_name}.sections[#{index}]"
                      end

                      # Header with data binding
                      if header_view_name
                        add_line "// Section #{index + 1} Header: #{header_view_name}"
                        add_line "if let headerData = section.header?.data {"
                        indent do
                          add_line "#{header_view_name}(data: headerData)"
                          apply_header_footer_padding
                        end
                        add_line "}"
                      end

                      # Grid for cells
                      add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['columnSpacing'] || @component['itemSpacing'] || 0}), count: #{section_columns}), alignment: #{get_grid_alignment}, spacing: #{@component['lineSpacing'] || @component['itemSpacing'] || 0}) {"
                      indent do
                        if cell_view_name
                          add_line "if let cellsData = section.cells?.data {"
                          indent do
                            vars = open_cell_foreach('cellsData')
                            indent do
                              add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                              generate_cell_identity(vars[:index_var])

                              apply_cell_frame(grid: true)

                              # Add accessibilityIdentifier for test automation (tapItem action)
                              if @component['id']
                                add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                              end
                            end
                            add_line "}"
                          end
                          add_line "}"
                        end
                      end
                      add_line "}"
                      apply_grid_padding

                      # Footer with data binding
                      if footer_view_name
                        add_line "// Section #{index + 1} Footer: #{footer_view_name}"
                        add_line "if let footerData = section.footer?.data {"
                        indent do
                          add_line "#{footer_view_name}(data: footerData)"
                          apply_header_footer_padding
                        end
                        add_line "}"
                      end
                    end
                    add_line "}"
                  else
                    # No property binding - use static rendering
                    if header_view_name
                      add_line "#{header_view_name}()"
                      apply_header_footer_padding
                    end

                    add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['columnSpacing'] || @component['itemSpacing'] || 0}), count: #{section_columns}), alignment: #{get_grid_alignment}, spacing: #{@component['lineSpacing'] || @component['itemSpacing'] || 0}) {"
                    indent do
                      add_line "// No items binding specified"
                    end
                    add_line "}"
                    apply_grid_padding

                    if footer_view_name
                      add_line "#{footer_view_name}()"
                      apply_header_footer_padding
                    end
                  end
                end
              else
                # Legacy behavior - header/footer from cellClasses
                if header_class_name
                  add_line "#{header_class_name}()"
                  apply_header_footer_padding
                end
                
                add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['columnSpacing'] || @component['itemSpacing'] || 0}), count: #{columns_info[:expr]}), alignment: #{get_grid_alignment}, spacing: #{@component['lineSpacing'] || @component['itemSpacing'] || 0}) {"
                indent do
                  generate_collection_content(cell_class_name, id)
                end
                add_line "}"
                apply_grid_padding

                if footer_class_name
                  add_line ""
                  add_line "#{footer_class_name}()"
                  apply_header_footer_padding
                end
              end
            end
            add_line "}"
            generate_default_scroll_anchor
            generate_scroll_reader_close
          end

          # scrollEnabled — emit .scrollDisabled(_:) (not .disabled(_:)) so a
          # dynamic toggle does not interrupt an in-flight pan / deceleration
          # and does not change the modifier chain shape.
          scroll_enabled = @component['scrollEnabled']
          if scroll_enabled == false
            add_modifier_line ".scrollDisabled(true)"
          elsif scroll_enabled.is_a?(String) && is_binding?(scroll_enabled)
            prop = extract_property_name(scroll_enabled)
            add_modifier_line ".scrollDisabled(!data.#{prop})"
          end

          # Apply common modifiers (skip insets since we handle them with spacers for contentInset effect)
          apply_modifiers(skip_insets: true)

          generated_code
        end

        # Wrap convert_non_responsive in a size-class if/else, regenerating the
        # full collection per branch with merged attrs. Mirrors the kjui pattern
        # (compose_builder dispatches per-branch with `generate_non_responsive_component`).
        # Output is inline (not a separate function) because Collection's
        # generated code is self-contained per branch.
        #
        # `@modifier_bag` is reset per branch because `apply_modifiers` at the
        # end of `convert_non_responsive` calls `emit_all` against it. Without
        # a reset, branch N would re-emit modifiers accumulated by branch N-1.
        def convert_responsive
          branches = JsonUIShared::ResponsiveResolver.build_branches(@component)
          saved_component = @component

          # Wrap the if/else chain in `Group { }` so it parses inside an
          # `AnyView(...)` argument position. AnyView takes a single View
          # expression and a bare `if/else` is @ViewBuilder content, not an
          # expression. Group is a transparent @ViewBuilder container that
          # legalizes the conditional in either nesting context. Mirrors
          # embed_converter#convert_responsive.
          add_line "Group {"
          @indent_level += 1

          branches.each_with_index do |branch, idx|
            condition = branch[:size_class] ? Views::ResponsiveHelper.size_class_condition(branch[:size_class]) : nil

            if idx == 0 && condition
              add_line "if #{condition} {"
            elsif condition
              add_line "} else if #{condition} {"
            elsif idx > 0
              add_line "} else {"
            end

            branch_attrs = branch[:attrs].dup
            branch_attrs.delete('responsive')
            @component = branch_attrs
            @modifier_bag = ModifierBag.new
            @indent_level += 1
            convert_non_responsive
            @indent_level -= 1
          end

          add_line "}" if branches.size > 1
          @indent_level -= 1
          add_line "}"
          @component = saved_component
          # See embed_converter#convert_responsive for the same fix rationale:
          # generated_code emits the modifier_bag as a side effect, which would
          # re-emit the LAST branch's modifiers outside the Group's closing
          # brace. Reset so the final generated_code call is a no-op.
          @modifier_bag = ModifierBag.new
          generated_code
        end

        # ScrollView vocabulary shared by Collection (measured in real
        # layouts): content insets, safe-area adjustment, and the keyboard
        # avoidance opt-out. Applied as modifiers on the whole emitted
        # container, mirroring ScrollViewConverter's mappings.
        def apply_scroll_container_attrs
          inset = @component['containerInset']
          if inset.is_a?(Numeric)
            @modifier_bag.append(:component_specific, ".contentMargins(.all, #{inset}, for: .scrollContent)")
          elsif inset.is_a?(Array)
            edge = case inset.length
                   when 1 then "EdgeInsets(top: #{inset[0]}, leading: #{inset[0]}, bottom: #{inset[0]}, trailing: #{inset[0]})"
                   when 2 then "EdgeInsets(top: #{inset[0]}, leading: #{inset[1]}, bottom: #{inset[0]}, trailing: #{inset[1]})"
                   when 4 then "EdgeInsets(top: #{inset[0]}, leading: #{inset[1]}, bottom: #{inset[2]}, trailing: #{inset[3]})"
                   end
            @modifier_bag.append(:component_specific, ".contentMargins(.all, #{edge}, for: .scrollContent)") if edge
          end

          case @component['contentInsetAdjustmentBehavior']
          when 'never'
            @modifier_bag.append(:component_specific, ".ignoresSafeArea()")
          when 'scrollableAxes'
            @modifier_bag.append(:component_specific, ".ignoresSafeArea(edges: .horizontal)")
          end

          # Default (true) is the system behaviour; only the opt-out emits.
          if @component['keyboardAvoidance'] == false
            @modifier_bag.append(:component_specific, ".ignoresSafeArea(.keyboard)")
          end
        end

        private

        # The cell's own frame, in ONE place.
        #
        # Sixteen call sites render a cell, and they had grown three dialects
        # of this: six applied cellWidth + cellHeight, three applied cellHeight
        # and a grid `maxWidth`, and SEVEN applied nothing at all. Which
        # dialect a layout got depended on which container shape it happened to
        # select, so `cellWidth` was honoured or silently dropped by accident
        # of routing — the conformance probe's shape (sections + bound items)
        # lands on a do-nothing site, which is why it measured the spelling
        # unread while four call sites plainly read it.
        #
        # The declaration settles what they should all do: "Fixed width for
        # EVERY cell […] applied to the cell view AFTER it is built, so it
        # overrides whatever width the cell layout asked for".
        #
        # `grid:` keeps the one legitimate difference. In a LazyVGrid the
        # column governs the width, so a cell with no declared cellWidth fills
        # its column — but a declared one still overrides it, per "overrides
        # whatever width the cell layout asked for". Emission order inside each
        # dialect is unchanged: `.frame` wraps, so reordering these would move
        # pixels.
        # `alignment: .topLeading` + `.clipped()`: a declared cell size can
        # UNDER-fit the cell's content, and SwiftUI's default .center frame
        # let the overflow spill symmetrically — the cell drew shifted half
        # out of its lane (Collection_cellWidth__static parity d=50, run
        # 31202080745). Web anchors the cell at its leading edge and hides
        # the overflow; the frame here reads the same way.
        def apply_cell_frame(grid: false)
          clipped = false
          if grid
            if @component['cellHeight']
              add_modifier_line ".frame(height: #{@component['cellHeight']}, alignment: .topLeading)"
              clipped = true
            end
            if @component['cellWidth']
              add_modifier_line ".frame(width: #{@component['cellWidth']}, alignment: .topLeading)"
              clipped = true
            else
              add_modifier_line ".frame(maxWidth: .infinity)"
            end
          else
            if @component['cellWidth']
              add_modifier_line ".frame(width: #{@component['cellWidth']}, alignment: .topLeading)"
              clipped = true
            end
            if @component['cellHeight']
              add_modifier_line ".frame(height: #{@component['cellHeight']}, alignment: .topLeading)"
              clipped = true
            end
          end
          add_modifier_line ".clipped()" if clipped
        end

        #: Declared `listStyle` -> SwiftUI list chrome. Enumerated by the
        #: `collectionSeparators` ruling (2026-08-07) from the only
        #: implementation that reads it, SwiftJsonUI's
        #: TableConverter.applyListStyle.
        LIST_STYLES = {
          'plain' => 'PlainListStyle()',
          'grouped' => 'GroupedListStyle()',
          'insetgrouped' => 'InsetGroupedListStyle()',
          'sidebar' => 'SidebarListStyle()',
        }.freeze

        # This line hardcoded `PlainListStyle()` and never read the attribute,
        # which is why a declared `listStyle` was inert on the codegen face.
        # The ruling is explicit that the hardcoding could not be replaced
        # before the vocabulary existed — a bare string could be neither
        # validated nor discriminated. It exists now.
        #
        # `plain` is the declared default and the declared fallback for an
        # unrecognised value, so both land on the same arm.
        #
        # ORTHOGONAL to `hideSeparator`: this picks the chrome, that hides the
        # separators, and neither overrides the other.
        def list_style_to_swiftui
          LIST_STYLES[@component['listStyle'].to_s.downcase] || LIST_STYLES['plain']
        end

        # Non-lazy path: no ScrollView, no Lazy* containers. The Collection is
        # expected to live inside an already-scrollable parent. Sticky headers
        # and programmatic scrollTo are not supported here; scrollEnabled/
        # scrollAnchor/defaultScrollAnchor/onPageChanged are ignored.
        def generate_non_lazy(columns:, is_horizontal:, has_sections:, is_flow:,
                              cell_class_name:, header_class_name:, footer_class_name:, id:)
          if is_flow
            # VStack + FlowLayout (no outer ScrollView)
            generate_non_lazy_flow(has_sections)
          elsif is_horizontal
            generate_non_lazy_horizontal(has_sections, cell_class_name)
          elsif has_sections && columns == 1
            line_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 0
            vstack_alignment = get_vstack_alignment_from_gravity(@component['gravity'])
            add_line "VStack(alignment: #{vstack_alignment}, spacing: #{line_spacing}) {"
            indent do
              generate_collection_content_sections_vertical
            end
            add_line "}"
            apply_insets_only
          elsif columns == 1 && !has_sections
            # Legacy single column without sections — plain VStack with ForEach
            line_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 0
            vstack_alignment = get_vstack_alignment_from_gravity(@component['gravity'])
            add_line "VStack(alignment: #{vstack_alignment}, spacing: #{line_spacing}) {"
            indent do
              if header_class_name
                add_line "#{header_class_name}()"
              end
              generate_collection_content(cell_class_name, id)
              if footer_class_name
                add_line "#{footer_class_name}()"
              end
            end
            add_line "}"
            apply_insets_only
          else
            # Multi-column grid — LazyVGrid without ScrollView renders eagerly
            generate_non_lazy_grid(has_sections, cell_class_name, header_class_name, footer_class_name)
          end
        end

        def generate_non_lazy_horizontal(has_sections, cell_class_name)
          spacing = @component['itemSpacing'] || @component['columnSpacing'] || 0
          hstack_alignment = get_hstack_alignment_from_gravity(@component['gravity'])
          add_line "HStack(alignment: #{hstack_alignment}, spacing: #{spacing}) {"
          indent do
            if has_sections
              property_name = extract_property_name(@component['items'])
              @component['sections'].each_with_index do |section, index|
                cell_view_name = extract_view_name(section['cell']) if section['cell']
                next unless cell_view_name && property_name

                is_optional = is_property_optional?(property_name)
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                else
                  add_line "if data.#{property_name}.sections.count > #{index} {"
                end
                indent do
                  data_ref = is_optional ? "dataSource" : "data.#{property_name}"
                  add_line "let section = #{data_ref}.sections[#{index}]"
                  add_line "if let cellsData = section.cells?.data {"
                  indent do
                    vars = open_cell_foreach('cellsData')
                    indent do
                      add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                      generate_cell_identity(vars[:index_var])
                      apply_cell_frame
                      if @component['id']
                        add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                      end
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
                add_line "}"
              end
            elsif cell_class_name
              property_name = extract_property_name(@component['items'])
              if property_name
                is_optional = is_property_optional?(property_name)
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, let cellsData = dataSource.sections.first?.cells?.data {"
                else
                  add_line "if let cellsData = data.#{property_name}.sections.first?.cells?.data {"
                end
                indent do
                  vars = open_cell_foreach('cellsData')
                  indent do
                    add_line "#{cell_class_name}(data: #{vars[:data_var]})"
                    generate_cell_identity(vars[:index_var])
                    apply_cell_frame
                    if @component['id']
                      add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                    end
                  end
                  add_line "}"
                end
                add_line "}"
              end
            end
          end
          add_line "}"
          apply_insets_only
        end

        def generate_non_lazy_grid(has_sections, cell_class_name, header_class_name, footer_class_name)
          # Inter-column gap: columnSpacing first, kjui's order.
          spacing = @component['columnSpacing'] || @component['itemSpacing'] || 0
          grid_cols = "Array(repeating: GridItem(.flexible(), spacing: #{spacing}), count: #{columns_info[:expr]})"

          if has_sections
            property_name = extract_property_name(@component['items'])
            section_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 0
            vstack_alignment = get_vstack_alignment_from_gravity(@component['gravity'])
            add_line "VStack(alignment: #{vstack_alignment}, spacing: #{section_spacing}) {"
            indent do
              @component['sections'].each_with_index do |section, index|
                header_view_name = extract_view_name(section['header']) if section['header']
                cell_view_name = extract_view_name(section['cell']) if section['cell']
                footer_view_name = extract_view_name(section['footer']) if section['footer']
                section_columns = section_columns_expr(section)
                section_grid_cols = "Array(repeating: GridItem(.flexible(), spacing: #{spacing}), count: #{section_columns})"

                if property_name
                  is_optional = is_property_optional?(property_name)
                  if is_optional
                    add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                  else
                    add_line "if data.#{property_name}.sections.count > #{index} {"
                  end
                  indent do
                    data_ref = is_optional ? "dataSource" : "data.#{property_name}"
                    add_line "let section = #{data_ref}.sections[#{index}]"

                    if header_view_name
                      add_line "if let headerData = section.header?.data {"
                      indent do
                        add_line "#{header_view_name}(data: headerData)"
                      end
                      add_line "}"
                    end

                    add_line "LazyVGrid(columns: #{section_grid_cols}, alignment: #{get_grid_alignment}, spacing: #{spacing}) {"
                    indent do
                      if cell_view_name
                        add_line "if let cellsData = section.cells?.data {"
                        indent do
                          vars = open_cell_foreach('cellsData')
                          indent do
                            add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                            generate_cell_identity(vars[:index_var])
                            apply_cell_frame(grid: true)
                            if @component['id']
                              add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                            end
                          end
                          add_line "}"
                        end
                        add_line "}"
                      end
                    end
                    add_line "}"

                    if footer_view_name
                      add_line "if let footerData = section.footer?.data {"
                      indent do
                        add_line "#{footer_view_name}(data: footerData)"
                      end
                      add_line "}"
                    end
                  end
                  add_line "}"
                end
              end
            end
            add_line "}"
            apply_insets_only
          else
            if header_class_name
              add_line "#{header_class_name}()"
            end
            add_line "LazyVGrid(columns: #{grid_cols}, alignment: #{get_grid_alignment}, spacing: #{spacing}) {"
            indent do
              generate_collection_content(cell_class_name, id = @component['id'] || 'collection')
            end
            add_line "}"
            apply_insets_only
            if footer_class_name
              add_line "#{footer_class_name}()"
            end
          end
        end

        def generate_non_lazy_flow(has_sections)
          # kjui's chain order on the declared attrs: inter-item prefers
          # columnSpacing, inter-line prefers lineSpacing, itemSpacing is the
          # uniform fallback for both axes. The flow default 8 is symmetric
          # with kjui (unlike the grid paths' removed 10) and stays.
          h_spacing = @component['columnSpacing'] || @component['itemSpacing'] || 8
          v_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 8
          flow_alignment = get_flow_alignment
          section_spacing = @component['sectionSpacing'] || @component['lineSpacing'] || 8

          add_line "VStack(spacing: #{section_spacing}) {"
          indent do
            if has_sections
              property_name = extract_property_name(@component['items'])
              if property_name
                is_optional = is_property_optional?(property_name)
                @component['sections'].each_with_index do |section, index|
                  cell_view_name = extract_view_name(section['cell']) if section['cell']
                  next unless cell_view_name

                  if is_optional
                    add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                  else
                    add_line "if data.#{property_name}.sections.count > #{index} {"
                  end
                  indent do
                    data_ref = is_optional ? "dataSource" : "data.#{property_name}"
                    add_line "let section = #{data_ref}.sections[#{index}]"
                    add_line "if let cellsData = section.cells?.data {"
                    indent do
                      add_line "FlowLayout(alignment: #{flow_alignment}, horizontalSpacing: #{h_spacing}, verticalSpacing: #{v_spacing}) {"
                      indent do
                        vars = open_cell_foreach('cellsData')
                        indent do
                          add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                          generate_cell_identity(vars[:index_var])
                          apply_cell_frame
                          if @component['id']
                            add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                          end
                        end
                        add_line "}"
                      end
                      add_line "}"
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
              end
            else
              cell_class_name = extract_view_name(@component['cellClasses']&.first)
              property_name = extract_property_name(@component['items'])
              if cell_class_name && property_name
                is_optional = is_property_optional?(property_name)
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, let cellsData = dataSource.sections.first?.cells?.data {"
                else
                  add_line "if let cellsData = data.#{property_name}.sections.first?.cells?.data {"
                end
                indent do
                  add_line "FlowLayout(alignment: #{flow_alignment}, horizontalSpacing: #{h_spacing}, verticalSpacing: #{v_spacing}) {"
                  indent do
                    vars = open_cell_foreach('cellsData')
                    indent do
                      add_line "#{cell_class_name}(data: #{vars[:data_var]})"
                      generate_cell_identity(vars[:index_var])
                      apply_cell_frame
                      if @component['id']
                        add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                      end
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
                add_line "}"
              end
            end
          end
          add_line "}"
          apply_insets_only
        end

        # Generate horizontal paging collection using TabView
        def generate_paging_horizontal
          spacing = @component['itemSpacing'] || @component['columnSpacing'] || 0
          property_name = extract_property_name(@component['items'])

          # currentPage binding
          current_page_prop = nil
          if @component['currentPage'] && is_binding?(@component['currentPage'])
            current_page_prop = extract_binding_property(@component['currentPage'])
          end

          # TabView with optional selection binding
          if current_page_prop
            add_line "TabView(selection: $data.#{current_page_prop}) {"
          else
            add_line "TabView {"
          end

          indent do
            if @component['sections'] && !@component['sections'].empty? && property_name
              @component['sections'].each_with_index do |section, index|
                cell_view_name = extract_view_name(section['cell']) if section['cell']
                next unless cell_view_name && property_name

                is_optional = is_property_optional?(property_name)
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                else
                  add_line "if data.#{property_name}.sections.count > #{index} {"
                end
                indent do
                  data_ref = is_optional ? "dataSource" : "data.#{property_name}"
                  add_line "let section = #{data_ref}.sections[#{index}]"
                  add_line "if let cellsData = section.cells?.data {"
                  indent do
                    vars = open_cell_foreach('cellsData')
                    indent do
                      add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                      generate_cell_identity(vars[:index_var])
                      apply_cell_frame
                      if spacing > 0
                        add_modifier_line ".padding(.horizontal, #{spacing / 2.0})"
                      end
                      if @component['id']
                        add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                      end
                      add_modifier_line ".tag(#{vars[:index_var]})"
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
                add_line "}"
              end
            end
          end
          add_line "}"
          add_modifier_line ".tabViewStyle(.page(indexDisplayMode: .never))"

          # Page-change callback - guard against feedback loop.
          # onValueChange is the canonical name; onValueChanged /
          # onPageChanged are its definitions aliases (L0 fallback only).
          page_changed_handler = attr_with_alias('onValueChange', 'onValueChanged', 'onPageChanged')
          if page_changed_handler && is_binding?(page_changed_handler) && current_page_prop
            handler_call = get_event_handler_invocation(page_changed_handler, @component['id'] || 'collection', 'newValue')
            add_modifier_line ".onChange(of: data.#{current_page_prop}) { oldValue, newValue in"
            indent do
              add_line "guard oldValue != newValue else { return }"
              add_line handler_call
            end
            add_line "}"
          end

          # Apply common modifiers
          apply_modifiers
        end

        # Generate flow layout using FlowLayout (iOS 16+)
        def generate_flow_layout(has_sections)
          # kjui's chain order on the declared attrs: inter-item prefers
          # columnSpacing, inter-line prefers lineSpacing, itemSpacing is the
          # uniform fallback for both axes. The flow default 8 is symmetric
          # with kjui (unlike the grid paths' removed 10) and stays.
          h_spacing = @component['columnSpacing'] || @component['itemSpacing'] || 8
          v_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 8
          flow_alignment = get_flow_alignment

          shows_indicators = @component['showsVerticalScrollIndicator'] != false
          section_spacing = @component['sectionSpacing'] || @component['lineSpacing'] || 8
          add_line "ScrollView(.vertical, showsIndicators: #{shows_indicators}) {"
          indent do
            add_line "VStack(spacing: #{section_spacing}) {"
            indent do
            if has_sections
              property_name = extract_property_name(@component['items'])
              return unless property_name

              is_optional = is_property_optional?(property_name)

              @component['sections'].each_with_index do |section, index|
                cell_view_name = extract_view_name(section['cell']) if section['cell']
                next unless cell_view_name

                if is_optional
                  add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                else
                  add_line "if data.#{property_name}.sections.count > #{index} {"
                end
                indent do
                  if is_optional
                    add_line "let section = dataSource.sections[#{index}]"
                  else
                    add_line "let section = data.#{property_name}.sections[#{index}]"
                  end
                  add_line "if let cellsData = section.cells?.data {"
                  indent do
                    add_line "FlowLayout(alignment: #{flow_alignment}, horizontalSpacing: #{h_spacing}, verticalSpacing: #{v_spacing}) {"
                    indent do
                      vars = open_cell_foreach('cellsData')
                      indent do
                        add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                        generate_cell_identity(vars[:index_var])
                        apply_cell_frame
                        if @component['id']
                          add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                        end
                      end
                      add_line "}"
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
                add_line "}"
              end
            else
              # Legacy: no sections
              cell_class_name = extract_view_name(@component['cellClasses']&.first)
              property_name = extract_property_name(@component['items'])
              if cell_class_name && property_name
                is_optional = is_property_optional?(property_name)
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, let cellsData = dataSource.sections.first?.cells?.data {"
                else
                  add_line "if let cellsData = data.#{property_name}.sections.first?.cells?.data {"
                end
                indent do
                  add_line "FlowLayout(alignment: #{flow_alignment}, horizontalSpacing: #{h_spacing}, verticalSpacing: #{v_spacing}) {"
                  indent do
                    vars = open_cell_foreach('cellsData')
                    indent do
                      add_line "#{cell_class_name}(data: #{vars[:data_var]})"
                      generate_cell_identity(vars[:index_var])
                      apply_cell_frame
                      if @component['id']
                        add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                      end
                    end
                    add_line "}"
                  end
                  add_line "}"
                end
                add_line "}"
              end
            end
            end
            add_line "}"
            apply_insets_only
          end
          add_line "}"
        end

        # Extract horizontal alignment from gravity for FlowLayout (default: .leading)
        def get_flow_alignment
          gravity = @component['gravity']
          return '.leading' unless gravity
          horizontal = extract_horizontal_from_gravity(gravity)
          case horizontal
          when 'center' then '.center'
          when 'right' then '.trailing'
          else '.leading'
          end
        end

        # Extract horizontal alignment from gravity for LazyVGrid
        # LazyVGrid uses HorizontalAlignment: .leading, .center, .trailing
        def get_grid_alignment
          gravity = @component['gravity']
          return '.center' unless gravity
          horizontal = extract_horizontal_from_gravity(gravity)
          case horizontal
          when 'left' then '.leading'
          when 'right' then '.trailing'
          else '.center'
          end
        end

        # Extract horizontal alignment from gravity for VStack
        # VStack uses horizontal alignment: .leading, .center, .trailing
        def get_vstack_alignment_from_gravity(gravity)
          horizontal = extract_horizontal_from_gravity(gravity)
          case horizontal
          when 'left' then '.leading'
          when 'center' then '.center'
          when 'right' then '.trailing'
          else '.leading'
          end
        end

        # Extract vertical alignment from gravity for HStack
        # HStack uses vertical alignment: .top, .center, .bottom
        def get_hstack_alignment_from_gravity(gravity)
          vertical = extract_vertical_from_gravity(gravity)
          case vertical
          when 'top' then '.top'
          when 'center' then '.center'
          when 'bottom' then '.bottom'
          else '.top'
          end
        end

        def extract_horizontal_from_gravity(gravity)
          gravity = gravity || 'left|top'
          if gravity.is_a?(Array)
            result = gravity.find { |g| ['left', 'center', 'right', 'centerHorizontal'].include?(g) } || 'left'
            result == 'centerHorizontal' ? 'center' : result
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              result = parts.find { |p| ['left', 'center', 'right', 'centerHorizontal'].include?(p) } || 'left'
              result == 'centerHorizontal' ? 'center' : result
            else
              return 'center' if gravity == 'centerHorizontal'
              ['left', 'center', 'right'].include?(gravity) ? gravity : 'left'
            end
          else
            'left'
          end
        end

        def extract_vertical_from_gravity(gravity)
          gravity = gravity || 'left|top'
          if gravity.is_a?(Array)
            result = gravity.find { |g| ['top', 'center', 'bottom', 'centerVertical'].include?(g) } || 'top'
            result == 'centerVertical' ? 'center' : result
          elsif gravity.is_a?(String)
            if gravity.include?('|')
              parts = gravity.split('|')
              result = parts.find { |p| ['top', 'center', 'bottom', 'centerVertical'].include?(p) } || 'top'
              result == 'centerVertical' ? 'center' : result
            else
              return 'center' if gravity == 'centerVertical'
              ['top', 'center', 'bottom'].include?(gravity) ? gravity : 'top'
            end
          else
            'top'
          end
        end

        # ScrollViewReader helpers for programmatic scrolling
        def has_scroll_to?
          @component['scrollTo'] != nil
        end

        def generate_scroll_reader_open
          return unless has_scroll_to?
          add_line "ScrollViewReader { scrollProxy in"
          @indent_level += 1
        end

        def generate_default_scroll_anchor
          default_anchor = @component['defaultScrollAnchor']
          return unless default_anchor
          if default_anchor.is_a?(String) && is_binding?(default_anchor)
            prop = extract_property_name(default_anchor)
            add_modifier_line ".defaultScrollAnchor(data.#{prop} == \"bottom\" ? .bottom : data.#{prop} == \"center\" ? .center : .top)"
          else
            anchor = case default_anchor
                     when 'top' then '.top'
                     when 'center' then '.center'
                     when 'bottom' then '.bottom'
                     else '.top'
                     end
            add_modifier_line ".defaultScrollAnchor(#{anchor})"
          end
        end

        def generate_scroll_reader_close
          return unless has_scroll_to?
          scroll_prop = extract_property_name(@component['scrollTo'])
          return unless scroll_prop
          anchor = @component['scrollAnchor'] || 'bottom'
          scroll_animated = @component['scrollAnimated']
          cell_id_property = @component['cellIdProperty']
          recv_var = cell_id_property ? 'cellId' : 'index'
          # `scrollTo` is declared as a PLAIN VALUE — `String` when
          # `cellIdProperty` is set, `Int` otherwise. This used to emit
          # `data.x.throttle(...)`, which only typechecks if the property is a
          # Combine publisher, so the attribute forced consumers to declare
          # `PassthroughSubject<Int, Never>` in their data section. The SSoT
          # withdrew that (2026-08-05, plan 49-E): naming a Swift transport in
          # a cross-platform declaration is what made kjui's
          # `map_to_kotlin_type` pass the Combine type through verbatim and
          # kill the Kotlin build. How the request travels is each platform's
          # own business.
          #
          # The other two platforms both key an effect on the value —
          # Compose `LaunchedEffect(data.<prop>)`
          # (collection_component.rb:364), web a `useEffect` on it — and
          # `.onChange(of:)` is that same shape in SwiftUI. Derived from them
          # rather than invented here.
          #
          # The throttle goes with the publisher: it existed to damp a rapid
          # stream of sends, and a value that changes has nothing to damp
          # (neither of the other two throttles either). What is also gone is
          # "sending the SAME value again re-scrolls" — that is publisher
          # behaviour a plain value cannot express, and the declaration is now
          # a plain value.
          add_modifier_line ".onChange(of: data.#{scroll_prop}) { _, #{recv_var} in"
          indent do
            scroll_call = "scrollProxy.scrollTo(#{recv_var}, anchor: .#{anchor})"
            if scroll_animated.is_a?(String) && scroll_animated.start_with?('@{') && scroll_animated.end_with?('}')
              # Binding: runtime check (canonical expression parsing)
              animated_expr = SwiftUI::Binding::BindingExpression.swift_bool_expr(scroll_animated[2..-2])
              add_line "if #{animated_expr} {"
              indent do
                add_line "withAnimation {"
                indent do
                  add_line scroll_call
                end
                add_line "}"
              end
              add_line "} else {"
              indent do
                add_line scroll_call
              end
              add_line "}"
            elsif scroll_animated == false
              add_line scroll_call
            else
              add_line "withAnimation {"
              indent do
                add_line scroll_call
              end
              add_line "}"
            end
          end
          add_line "}"
          @indent_level -= 1
          add_line "}"
        end

        # Open a ForEach block with appropriate identity strategy.
        # Returns { data_var:, index_var: } for use in the body.
        # When cellIdProperty is set: maps to IdentifiedCellItem + ForEach(Identifiable)
        # When not set: uses enumerated() + id: \.offset
        #
        # When autoChangeTrackingId is true (plus cellIdProperty), the data
        # source is wrapped with `.reconfigured(...)` so CellIdGenerator
        # enriches each cell with a `"cellId"` = `"<primary>_<hash>"` entry.
        # Idempotent: safe to combine with Mode A (VM pre-sets attributes).
        def open_cell_foreach(data_source_expr)
          cell_id_property = @component['cellIdProperty']
          auto_tracking = @component['autoChangeTrackingId'] == true

          if auto_tracking && cell_id_property
            source_expr = "#{data_source_expr}.reconfigured(" \
                          "cellIdProperty: \"#{cell_id_property}\", " \
                          "autoChangeTrackingId: true)"
          else
            source_expr = data_source_expr
            if auto_tracking && cell_id_property.nil?
              warn "[sjui] Collection at #{@component['id'] || '(unnamed)'}: " \
                   'autoChangeTrackingId is true but cellIdProperty is not set; ignoring.'
            end
          end

          if cell_id_property
            add_line "let items = #{source_expr}.enumerated().map { index, data in"
            indent do
              # Prefer the pre-enriched "cellId" when autoChangeTrackingId is on;
              # otherwise fall back to the user's primary key.
              add_line "IdentifiedCellItem(id: (data[\"cellId\"] as? String) ?? (data[\"#{cell_id_property}\"] as? String) ?? \"\\(index)\", index: index, data: data)"
            end
            add_line "}"
            add_line "ForEach(items) { cell in"
            { data_var: 'cell.data', index_var: 'cell.index' }
          else
            add_line "ForEach(Array(#{source_expr}.enumerated()), id: \\.offset) { cellIndex, cellData in"
            { data_var: 'cellData', index_var: 'cellIndex' }
          end
        end

        def generate_cell_identity(index_var = 'cellIndex')
          # When cellIdProperty is set, ForEach(Identifiable) handles identity — no .id() needed
          unless @component['cellIdProperty']
            # Integer-based ID for scroll target only
            if has_scroll_to?
              add_modifier_line ".id(#{index_var})"
            end
          end

          # onItemAppear: fire callback with index when cell appears
          on_item_appear = @component['onItemAppear']
          if on_item_appear && is_binding?(on_item_appear)
            prop = extract_binding_property(on_item_appear)
            add_modifier_line ".onAppear { data.#{prop}?(#{index_var}) }"
          end
        end

        # Check if a property is optional based on data_properties
        # A property is optional if it has no defaultValue or defaultValue is nil
        def is_property_optional?(property_name)
          return true if @data_properties.nil? || @data_properties.empty?

          prop = @data_properties.find { |p| p['name'] == property_name }
          return true unless prop

          # If defaultValue is nil or not specified, it's optional
          prop['defaultValue'].nil? || prop['defaultValue'] == 'nil'
        end

        def extract_view_name(class_info)
          return nil unless class_info

          if class_info.is_a?(Hash)
            # Format: { "className": "InformationListCollectionViewCell" }
            class_name = class_info['className']
          elsif class_info.is_a?(String)
            # Format: "InformationListCollectionViewCell" or "item_card"
            class_name = class_info
          else
            return nil
          end

          # Strip directory path if present (e.g., "Chat/candidate_card" -> "candidate_card")
          class_name = File.basename(class_name) if class_name.include?('/')

          # First, convert snake_case to PascalCase if needed
          # e.g., "item_card" -> "ItemCard"
          if class_name.include?('_')
            class_name = to_pascal_case(class_name)
          end

          # Convert UIKit cell class name to SwiftUI view name
          # If it ends with CollectionViewCell, replace with View
          # If it ends with Cell, replace with CellView
          # Otherwise add View
          view_name = if class_name.end_with?('CollectionViewCell')
                        class_name.sub(/CollectionViewCell$/, 'View')
                      elsif class_name.end_with?('cell')
                        # Handle lowercase 'cell' - convert to CellView with proper casing
                        class_name.sub(/cell$/, 'Cell') + 'View'
                      elsif class_name.end_with?('Cell')
                        # Handle uppercase 'Cell' - just add View
                        class_name + 'View'
                      elsif !class_name.end_with?('View')
                        class_name + 'View'
                      else
                        class_name
                      end

          view_name
        end

        # Convert snake_case, kebab-case, camelCase, or PascalCase to PascalCase
        # e.g., "item_card" -> "ItemCard", "HomeHeader" -> "HomeHeader"
        def to_pascal_case(str)
          # First convert camelCase/PascalCase to snake_case, then to PascalCase
          snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                     .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                     .downcase
          snake.split(/[_\-]/).map(&:capitalize).join
        end

        # Generate vertical section-based collection content using LazyVStack
        # Conditionally indent a block — the Group wrappers above read better
        # than duplicated branches.
        def maybe_indent(condition, &block)
          if condition
            indent(&block)
          else
            block.call
          end
        end

        def generate_collection_content_sections_vertical
          property_name = extract_property_name(@component['items'])
          return unless property_name

          is_optional = is_property_optional?(property_name)

          @component['sections'].each_with_index do |section, index|
            cell_view_name = extract_view_name(section['cell']) if section['cell']
            header_view_name = extract_view_name(section['header']) if section['header']
            footer_view_name = extract_view_name(section['footer']) if section['footer']

            # Wrap in optional check
            if is_optional
              add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
            else
              add_line "if data.#{property_name}.sections.count > #{index} {"
            end
            indent do
              if is_optional
                add_line "let section = dataSource.sections[#{index}]"
              else
                add_line "let section = data.#{property_name}.sections[#{index}]"
              end

              # Header
              if header_view_name
                add_line "if let headerData = section.header?.data {"
                indent do
                  add_line "#{header_view_name}(data: headerData)"
                end
                add_line "}"
              end

              # Cells
              if cell_view_name
                add_line "if let cellsData = section.cells?.data {"
                indent do
                  vars = open_cell_foreach('cellsData')
                  indent do
                    add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                    generate_cell_identity(vars[:index_var])
                    apply_cell_frame
                    # Add accessibilityIdentifier for test automation (tapItem action)
                    if @component['id']
                      add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                    end
                  end
                  add_line "}"
                end
                add_line "}"
              end

              # Footer
              if footer_view_name
                add_line "if let footerData = section.footer?.data {"
                indent do
                  add_line "#{footer_view_name}(data: footerData)"
                end
                add_line "}"
              end
            end
            add_line "}"
          end
        end

        def generate_collection_content_sections(property_name)
          # If sections are defined in JSON, use those
          if @component['sections'] && !@component['sections'].empty?
            # Generate based on predefined sections structure
            is_optional = is_property_optional?(property_name)

            @component['sections'].each_with_index do |section, index|
              cell_view_name = extract_view_name(section['cell']) if section['cell']
              header_view_name = extract_view_name(section['header']) if section['header']
              footer_view_name = extract_view_name(section['footer']) if section['footer']

              # Generate section - use section-specific columns if specified.
              # A binding-form top-level `columns` ALWAYS routes through the
              # grid path here (`section_columns == 1` evaluates false on
              # the sentinel 2) because the runtime column count is unknown.
              # An explicit literal `section['columns'] = 1` still picks the
              # list-style path.
              section_columns = section['columns'] || columns_info[:literal] || (columns_info[:is_binding] ? 2 : 1)
              if section_columns == 1
                # List-style section with header/footer
                # Wrap in optional check
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                else
                  add_line "if data.#{property_name}.sections.count > #{index} {"
                end
                indent do
                  if is_optional
                    add_line "let section = dataSource.sections[#{index}]"
                  else
                    add_line "let section = data.#{property_name}.sections[#{index}]"
                  end

                  # Header
                  if header_view_name
                    add_line "if let headerData = section.header?.data {"
                    indent do
                      add_line "#{header_view_name}(data: headerData)"
                    end
                    add_line "}"
                  end

                  # Cells
                  if cell_view_name
                    add_line "if let cellsData = section.cells?.data {"
                    indent do
                      vars = open_cell_foreach('cellsData')
                      indent do
                        add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                        generate_cell_identity(vars[:index_var])
                        apply_cell_frame
                        # Add accessibilityIdentifier for test automation (tapItem action)
                        if @component['id']
                          add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                        end
                      end
                      add_line "}"
                    end
                    add_line "}"
                  end

                  # Footer
                  if footer_view_name
                    add_line "if let footerData = section.footer?.data {"
                    indent do
                      add_line "#{footer_view_name}(data: footerData)"
                    end
                    add_line "}"
                  end
                end
                add_line "}"
              else
                # Grid-style sections don't work the same way - cells go in the grid
                # This shouldn't happen in grid layout with sections
                add_line "// Warning: Section-based rendering in grid layout"
                if is_optional
                  add_line "if let dataSource = data.#{property_name}, dataSource.sections.count > #{index} {"
                else
                  add_line "if data.#{property_name}.sections.count > #{index} {"
                end
                indent do
                  if cell_view_name
                    if is_optional
                      add_line "if let cellsData = dataSource.sections[#{index}].cells?.data {"
                    else
                      add_line "if let cellsData = data.#{property_name}.sections[#{index}].cells?.data {"
                    end
                    indent do
                      vars = open_cell_foreach('cellsData')
                      indent do
                        add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                        generate_cell_identity(vars[:index_var])

                        apply_cell_frame(grid: columns_is_multi?)

                        # Add accessibilityIdentifier for test automation (tapItem action)
                        if @component['id']
                          add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                        end
                      end
                      add_line "}"
                    end
                    add_line "}"
                  end
                end
                add_line "}"
              end
            end
          else
            # Fallback to dynamic sections from data (when sections not defined in JSON)
            is_optional_fallback = is_property_optional?(property_name)
            data_source_ref = if is_optional_fallback
                                "dataSource"
                              else
                                "data.#{property_name}"
                              end

            if is_optional_fallback
              add_line "if let dataSource = data.#{property_name} {"
              indent do
                generate_fallback_foreach(data_source_ref)
              end
              add_line "}"
            else
              generate_fallback_foreach(data_source_ref)
            end
          end
        end
        
        def generate_fallback_foreach(data_source_ref)
          add_line "ForEach(Array(#{data_source_ref}.sections.enumerated()), id: \\.offset) { sectionIndex, section in"
          indent do
            # Generate cells for this section - need to dynamically instantiate view based on viewName
            add_line "if let cellsData = section.cells?.data, let viewName = section.cells?.viewName {"
            indent do
              add_line "ForEach(Array(cellsData.enumerated()), id: \\.offset) { cellIndex, cellData in"
              indent do
                # Since we don't know the view name at compile time, we need to use AnyView or a ViewBuilder
                add_line "// TODO: Implement dynamic view instantiation based on viewName"
                add_line "Text(\"\\(viewName): \\(cellIndex)\")"

                apply_cell_frame(grid: columns_is_multi?)
              end
              add_line "}"
            end
            add_line "}"
          end
          add_line "}"
        end

        def extract_property_name(items_property)
          return nil unless items_property
          
          if items_property.start_with?('@{') && items_property.end_with?('}')
            # Data-source reference: parsed path only ('??'/'!' are not
            # meaningful for collection data sources)
            SwiftUI::Binding::BindingExpression.parse(items_property[2...-1]).path
          else
            nil
          end
        end
        
        def generate_collection_content(cell_class_name, id)
          # Check if items property is specified (e.g., "@{items}")
          property_name = extract_property_name(@component['items'])
          
          if property_name
            # Use section-based rendering
            generate_collection_content_sections(property_name)
          else
            # Legacy behavior for backward compatibility
            generate_collection_content_legacy(cell_class_name, id)
          end
        end
        
        def generate_collection_content_legacy(cell_class_name, id)
          if cell_class_name
            # Extract the original class name from the cell classes
            cell_class_info = @component['cellClasses']&.first
            original_class_name = if cell_class_info.is_a?(Hash)
                                    cell_class_info['className']
                                  elsif cell_class_info.is_a?(String)
                                    cell_class_info
                                  else
                                    cell_class_name.sub('View', '')
                                  end
            
            add_line "// Legacy non-section based collection"
            vars = open_cell_foreach("data.collectionDataSource.getCellData(for: \"#{original_class_name}\")")
            indent do
              add_line "#{cell_class_name}(data: #{vars[:data_var]})"
              generate_cell_identity(vars[:index_var])

              apply_cell_frame(grid: columns_is_multi?)

              # Add accessibilityIdentifier for test automation (tapItem action)
              if @component['id']
                add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
              end
            end
            add_line "}"
          else
            # Declaration-faithful (2026-08-02 ruling): no cell class
            # declared → nothing rendered (was a 10-item placeholder).
            add_line "// No cellClasses — nothing rendered (declaration-faithful)"
          end
        end
        
        # Generate .padding() from declared insets — declaration-faithful:
        # nothing declared, nothing emitted. The old else-branch injected the
        # SwiftUI system default (.padding(.horizontal) ≈16pt) that Compose
        # never had, so an insets-free Collection rendered 16pt wider gutters
        # on iOS only.
        # insets format: [top, left, bottom, right]
        def apply_grid_padding
          insets = collection_insets_array(@component['insets']) ||
                   collection_insets_array(@component['contentInsets'])
          if insets
            top, left, bottom, right = insets
            add_modifier_line ".padding(EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}))"
          end
          apply_inset_vertical
        end

        # Section headers/footers sit outside the LazyVGrid; follow the
        # declared insets' horizontal edges so they line up with the grid
        # body. Nothing declared → nothing emitted. They used to get an
        # unconditional .padding(.horizontal) — even when insets WERE
        # declared, which misaligned them from the grid.
        def apply_header_footer_padding
          insets = collection_insets_array(@component['insets']) ||
                   collection_insets_array(@component['contentInsets'])
          return unless insets

          _top, left, _bottom, right = insets
          add_modifier_line ".padding(EdgeInsets(top: 0, leading: #{left}, bottom: 0, trailing: #{right}))"
        end

        # Resolve the `lazy` attribute into one of three symbols matching
        # SwiftJsonUI's CollectionStackMode enum. Returns :lazy / :eager / :none.
        # Bindings always resolve to :lazy at build time; the runtime expression
        # in `collection_mode_swift_expr` handles the dynamic case.
        def collection_lazy_mode
          value = @component['lazy']
          case value
          when 'eager' then :eager
          when 'none' then :none
          when 'lazy', nil then :lazy
          else :lazy
          end
        end

        # Swift-source expression evaluating to a CollectionStackMode value.
        # Literal modes return `.lazy` / `.eager` / `.none`; bindings emit a
        # runtime-resolved `CollectionStackMode(json: data.<prop>)` so toggles
        # propagate without rebuilding the modifier chain.
        def collection_mode_swift_expr
          value = @component['lazy']
          if value.is_a?(String) && is_binding?(value)
            prop = extract_binding_property(value)
            "CollectionStackMode(json: data.#{prop})"
          else
            ".#{collection_lazy_mode}"
          end
        end

        # Convert array-form insets to a Swift EdgeInsets literal. Returns nil
        # when no insets attribute is present so the generator can omit the
        # parameter (uses CollectionStackView's default `nil`).
        #
        # Reads `contentInsets` as well as `insets`. Both are declared and the
        # UIKit runtime honours both — SJUICollectionView parses `contentInsets`
        # (string "t|l|b|r" or array) into the section inset — while this only
        # looked at `insets`, so the SwiftUI path dropped it. `insets` wins when
        # both are present, matching UIKit's order.
        # insetVertical / insetHorizontal fold into the same content-padding
        # channel (the dynamic renderer's applyCollectionContentInsets does
        # the same). The horizontal axis keeps insetHorizontal on its
        # insetLeading/insetTrailing params instead, so the caller excludes
        # it there to avoid double-application.
        def collection_content_insets_swift_expr(include_horizontal: true)
          insets = collection_insets_array(@component['insets']) ||
                   collection_insets_array(@component['contentInsets'])
          inset_v = @component['insetVertical']
          inset_h = include_horizontal ? @component['insetHorizontal'] : nil
          return nil unless insets || inset_v || inset_h
          top, left, bottom, right = insets || [0, 0, 0, 0]
          if inset_v
            top += inset_v.to_i
            bottom += inset_v.to_i
          end
          if inset_h
            left += inset_h.to_i
            right += inset_h.to_i
          end
          "EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right})"
        end

        # `[t, l, b, r]` from either the array form or UIKit's pipe-separated
        # string form, or nil when the value is not usable. A short array is
        # padded the way SJUICollectionView pads it (1 value = all sides,
        # 2 = vertical/horizontal) rather than being dropped.
        def collection_insets_array(value)
          parts = case value
                  when Array then value
                  when String then value.split('|')
                  else return nil
                  end
          nums = parts.map { |v| v.to_s.strip }.reject(&:empty?).map(&:to_i)
          case nums.length
          when 4 then nums
          when 2 then [nums[0], nums[1], nums[0], nums[1]]
          when 1 then [nums[0]] * 4
          else nil
          end
        end

        # itemWeight is folded into the COLUMN COUNT (columns_info /
        # item_weight_count), not emitted as a modifier. The previous emit
        # here — `.containerRelativeFrame(.horizontal, count:, span: 1)` on
        # the collection CONTENT via apply_insets_only — declared the
        # per-item intent in its own comment and then squeezed the whole
        # content to 1/count width instead: run 5 measured ZERO cell pixels
        # against 43k on neighbouring Collection fixtures. The dynamic face
        # (effectiveGridColumns) carries the canonical reading.

        # insetVertical — vertical-only content inset.
        #
        # UIKit folds it into the section inset; here it is vertical padding on
        # the scroll content, which is what the attribute says and what the
        # Dynamic runtime does.
        def apply_inset_vertical
          value = @component['insetVertical']
          return if value.nil?

          add_modifier_line ".padding(.vertical, #{value})"
        end

        # Open a CollectionStackView(...) call. The caller is responsible for
        # emitting the trailing closing `}` after the cell-content block.
        def generate_collection_stack_view_open(axis:)
          params = collection_stack_view_params(axis: axis)
          add_line "CollectionStackView("
          indent do
            params.each_with_index do |line, idx|
              add_line(idx == params.length - 1 ? line : "#{line},")
            end
          end
          add_line ") {"
        end

        # Build the ordered parameter list (without trailing commas) for a
        # CollectionStackView call. Tests can validate this list directly.
        def collection_stack_view_params(axis:)
          if axis == :vertical
            shows_indicators = @component['showsVerticalScrollIndicator'] != false
            line_spacing = @component['lineSpacing'] || @component['itemSpacing'] || 0
            alignment_param = "horizontalAlignment: #{get_vstack_alignment_from_gravity(@component['gravity'])}"
          else
            shows_indicators = @component['showsHorizontalScrollIndicator'] != false
            # `lineSpacing` historically named the inter-line gap; with a
            # horizontal single-column CollectionStackView, the inter-cell gap
            # IS the inter-line gap (one cell per line), so authoring
            # `lineSpacing` for a horizontal Collection should still set the
            # spacing. kjui's CollectionStack matches this fallback order AND
            # the all-absent default of 0 (the composable's `spacing: Dp = 0.dp`).
            line_spacing = @component['itemSpacing'] || @component['columnSpacing'] || @component['lineSpacing'] || 0
            alignment_param = "verticalAlignment: #{get_hstack_alignment_from_gravity(@component['gravity'])}"
          end

          # scrollDisabled: derived from scrollEnabled (binding or literal).
          scroll_enabled = @component['scrollEnabled']
          scroll_disabled_expr =
            if scroll_enabled.is_a?(String) && is_binding?(scroll_enabled)
              "!data.#{extract_binding_property(scroll_enabled)}"
            elsif scroll_enabled == false
              "true"
            else
              "false"
            end

          params = [
            "mode: #{collection_mode_swift_expr}",
            "axis: .#{axis}",
            alignment_param,
            "spacing: #{line_spacing}",
            "showsIndicators: #{shows_indicators}",
            "scrollDisabled: #{scroll_disabled_expr}"
          ]

          if axis == :vertical
            anchor_expr = collection_default_scroll_anchor_swift_expr
            params << "defaultScrollAnchor: #{anchor_expr}" unless anchor_expr == 'nil'
          else
            insets = @component['insets']
            inset_horizontal = (@component['insetHorizontal'] || 0).to_i
            inset_leading = insets.is_a?(Array) && insets.length == 4 ? insets[1].to_i : inset_horizontal
            inset_trailing = insets.is_a?(Array) && insets.length == 4 ? insets[3].to_i : inset_horizontal
            params << "insetLeading: #{inset_leading}" if inset_leading > 0
            params << "insetTrailing: #{inset_trailing}" if inset_trailing > 0
          end

          if (insets_expr = collection_content_insets_swift_expr(include_horizontal: axis == :vertical))
            params << "contentInsets: #{insets_expr}"
          end

          params
        end

        # defaultScrollAnchor expressed as a UnitPoint? Swift expression. Returns
        # 'nil' when no anchor is configured.
        def collection_default_scroll_anchor_swift_expr
          raw = @component['defaultScrollAnchor']
          return 'nil' unless raw
          if raw.is_a?(String) && is_binding?(raw)
            prop = extract_binding_property(raw)
            "data.#{prop} == \"bottom\" ? .bottom : data.#{prop} == \"center\" ? .center : .top"
          else
            case raw
            when 'bottom' then '.bottom'
            when 'center' then '.center'
            when 'top' then '.top'
            else 'nil'
            end
          end
        end

        # Apply insets only when explicitly specified (no default padding)
        # Used for LazyVStack paths that originally had no padding
        # Every collection path funnels through here for its content padding,
        # so `contentInsets` / `itemWeight` / `insetVertical` are applied here
        # too rather than at each of the eight call sites.
        def apply_insets_only
          insets = collection_insets_array(@component['insets']) ||
                   collection_insets_array(@component['contentInsets'])
          if insets
            top, left, bottom, right = insets
            add_modifier_line ".padding(EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}))"
          end
          apply_inset_vertical
        end

        def to_camel_case(str)
          return str if str.nil? || str.empty?

          # Handle snake_case to camelCase
          parts = str.split('_')
          parts[0] + parts[1..-1].map(&:capitalize).join
        end
      end
    end
  end
end