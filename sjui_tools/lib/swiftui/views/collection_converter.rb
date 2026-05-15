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

        def convert_non_responsive
          id = @component['id'] || 'collection'
          columns = @component['columns'] || 1
          # Support both 'layout' and 'orientation' attributes for horizontal/vertical
          layout = @component['layout'] || @component['orientation'] || 'vertical'
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

          is_flow = layout == 'flow'

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
                generate_collection_content(cell_class_name, id)

                # Footer without header
                if footer_class_name
                  add_line ""
                  add_line "#{footer_class_name}()"
                end
              end
            end
            add_line "}"
            add_modifier_line ".listStyle(PlainListStyle())"
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

                            # Only apply cellWidth/cellHeight if explicitly specified
                            # The cell view itself should define its own size
                            if @component['cellWidth']
                              add_modifier_line ".frame(width: #{@component['cellWidth']})"
                            end

                            if @component['cellHeight']
                              add_modifier_line ".frame(height: #{@component['cellHeight']})"
                            end

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

                        if @component['cellWidth']
                          add_modifier_line ".frame(width: #{@component['cellWidth']})"
                        end

                        if @component['cellHeight']
                          add_modifier_line ".frame(height: #{@component['cellHeight']})"
                        end

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
                          if @component['cellWidth']
                            add_modifier_line ".frame(width: #{@component['cellWidth']})"
                          end
                          if @component['cellHeight']
                            add_modifier_line ".frame(height: #{@component['cellHeight']})"
                          end
                          # Add accessibilityIdentifier for test automation (tapItem action)
                          if @component['id']
                            add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
                          end
                        end
                        add_line "}"
                      end
                      add_line "}"
                    else
                      # Placeholder when no items binding
                      add_line "ForEach(0..<10, id: \\.self) { index in"
                      indent do
                        add_line "Text(\"Item \\(index)\")"
                        add_modifier_line ".frame(width: 150, height: 80)"
                        add_modifier_line ".background(Color.gray.opacity(0.1))"
                        add_modifier_line ".cornerRadius(8)"
                      end
                      add_line "}"
                    end
                  else
                    # No cell class - show placeholder
                    add_line "ForEach(0..<10, id: \\.self) { index in"
                    indent do
                      add_line "Text(\"Item \\(index)\")"
                      add_modifier_line ".frame(width: 150, height: 80)"
                      add_modifier_line ".background(Color.gray.opacity(0.1))"
                      add_modifier_line ".cornerRadius(8)"
                    end
                    add_line "}"
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
                  section_columns = section['columns'] || columns

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
                          add_modifier_line ".padding(.horizontal)"
                        end
                        add_line "}"
                      end

                      # Grid for cells
                      add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['itemSpacing'] || 10}), count: #{section_columns}), alignment: #{get_grid_alignment}, spacing: #{@component['itemSpacing'] || 10}) {"
                      indent do
                        if cell_view_name
                          add_line "if let cellsData = section.cells?.data {"
                          indent do
                            vars = open_cell_foreach('cellsData')
                            indent do
                              add_line "#{cell_view_name}(data: #{vars[:data_var]}).equatable()"
                              generate_cell_identity(vars[:index_var])

                              if @component['cellHeight']
                                add_modifier_line ".frame(height: #{@component['cellHeight']})"
                              end

                              add_modifier_line ".frame(maxWidth: .infinity)"

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
                          add_modifier_line ".padding(.horizontal)"
                        end
                        add_line "}"
                      end
                    end
                    add_line "}"
                  else
                    # No property binding - use static rendering
                    if header_view_name
                      add_line "#{header_view_name}()"
                      add_modifier_line ".padding(.horizontal)"
                    end

                    add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['itemSpacing'] || 10}), count: #{section_columns}), alignment: #{get_grid_alignment}, spacing: #{@component['itemSpacing'] || 10}) {"
                    indent do
                      add_line "// No items binding specified"
                    end
                    add_line "}"
                    apply_grid_padding

                    if footer_view_name
                      add_line "#{footer_view_name}()"
                      add_modifier_line ".padding(.horizontal)"
                    end
                  end
                end
              else
                # Legacy behavior - header/footer from cellClasses
                if header_class_name
                  add_line "#{header_class_name}()"
                  add_modifier_line ".padding(.horizontal)"
                end
                
                add_line "LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: #{@component['itemSpacing'] || 10}), count: #{columns}), alignment: #{get_grid_alignment}, spacing: #{@component['itemSpacing'] || 10}) {"
                indent do
                  generate_collection_content(cell_class_name, id)
                end
                add_line "}"
                apply_grid_padding

                if footer_class_name
                  add_line ""
                  add_line "#{footer_class_name}()"
                  add_modifier_line ".padding(.horizontal)"
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

        private

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
          spacing = @component['itemSpacing'] || @component['columnSpacing'] || 10
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
                      if @component['cellWidth']
                        add_modifier_line ".frame(width: #{@component['cellWidth']})"
                      end
                      if @component['cellHeight']
                        add_modifier_line ".frame(height: #{@component['cellHeight']})"
                      end
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
                    if @component['cellWidth']
                      add_modifier_line ".frame(width: #{@component['cellWidth']})"
                    end
                    if @component['cellHeight']
                      add_modifier_line ".frame(height: #{@component['cellHeight']})"
                    end
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
          columns = @component['columns'] || 1
          spacing = @component['itemSpacing'] || 10
          grid_cols = "Array(repeating: GridItem(.flexible(), spacing: #{spacing}), count: #{columns})"

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
                section_columns = section['columns'] || columns
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
                            if @component['cellHeight']
                              add_modifier_line ".frame(height: #{@component['cellHeight']})"
                            end
                            add_modifier_line ".frame(maxWidth: .infinity)"
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
          h_spacing = @component['itemSpacing'] || @component['columnSpacing'] || 8
          v_spacing = @component['lineSpacing'] || 8
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

          # onPageChanged callback - guard against feedback loop
          if @component['onPageChanged'] && is_binding?(@component['onPageChanged']) && current_page_prop
            handler_call = get_event_handler_invocation(@component['onPageChanged'], @component['id'] || 'collection', 'newValue')
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
          h_spacing = @component['itemSpacing'] || @component['columnSpacing'] || 8
          v_spacing = @component['lineSpacing'] || 8
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
          # Throttle scrollTo to prevent animation stalls during rapid updates
          add_modifier_line ".onReceive(data.#{scroll_prop}.throttle(for: .milliseconds(100), scheduler: DispatchQueue.main, latest: true)) { #{recv_var} in"
          indent do
            scroll_call = "scrollProxy.scrollTo(#{recv_var}, anchor: .#{anchor})"
            if scroll_animated.is_a?(String) && scroll_animated.start_with?('@{') && scroll_animated.end_with?('}')
              # Binding: runtime check
              prop_name = to_camel_case(scroll_animated[2..-2])
              add_line "if data.#{prop_name} {"
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

              # Generate section - use section-specific columns if specified
              section_columns = section['columns'] || @component['columns'] || 1
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

                        if @component['cellHeight']
                          add_modifier_line ".frame(height: #{@component['cellHeight']})"
                        end

                        if @component['columns'] && @component['columns'] > 1
                          add_modifier_line ".frame(maxWidth: .infinity)"
                        end

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

                # Cell-specific modifiers
                if @component['cellHeight']
                  add_modifier_line ".frame(height: #{@component['cellHeight']})"
                end

                # For grid layouts, ensure cells expand to fill width
                if @component['columns'] && @component['columns'] > 1
                  add_modifier_line ".frame(maxWidth: .infinity)"
                end
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
            items_property[2...-1]
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

              if @component['cellHeight']
                add_modifier_line ".frame(height: #{@component['cellHeight']})"
              end

              if @component['columns'] && @component['columns'] > 1
                add_modifier_line ".frame(maxWidth: .infinity)"
              end

              # Add accessibilityIdentifier for test automation (tapItem action)
              if @component['id']
                add_modifier_line ".accessibilityIdentifier(\"#{@component['id']}_item_\\(#{vars[:index_var]})\")"
              end
            end
            add_line "}"
          else
            # No cell class specified - show placeholder
            add_line "// No cellClasses specified"
            add_line "ForEach(0..<10, id: \\.self) { index in"
            indent do
              add_line "Text(\"Item \\(index)\")"
              add_modifier_line ".frame(maxWidth: .infinity)"
              add_modifier_line ".frame(height: 80)"
              add_modifier_line ".background(Color.gray.opacity(0.1))"
              add_modifier_line ".cornerRadius(8)"
            end
            add_line "}"
          end
        end
        
        # Generate .padding() modifier from insets array or default .padding(.horizontal)
        # Used for LazyVGrid paths that previously had .padding(.horizontal)
        # insets format: [top, left, bottom, right]
        def apply_grid_padding
          insets = @component['insets']
          if insets.is_a?(Array) && insets.length == 4
            top, left, bottom, right = insets.map(&:to_i)
            add_modifier_line ".padding(EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}))"
          else
            add_modifier_line ".padding(.horizontal)"
          end
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
        def collection_content_insets_swift_expr
          insets = @component['insets']
          return nil unless insets.is_a?(Array) && insets.length == 4
          top, left, bottom, right = insets.map(&:to_i)
          "EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right})"
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
            line_spacing = @component['itemSpacing'] || @component['columnSpacing'] || 10
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

          if (insets_expr = collection_content_insets_swift_expr)
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
        def apply_insets_only
          insets = @component['insets']
          if insets.is_a?(Array) && insets.length == 4
            top, left, bottom, right = insets.map(&:to_i)
            add_modifier_line ".padding(EdgeInsets(top: #{top}, leading: #{left}, bottom: #{bottom}, trailing: #{right}))"
          end
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