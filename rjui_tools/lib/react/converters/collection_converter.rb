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

          content = generate_collection_content(indent + 2)

          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}>
            #{content}
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
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
          layout = attributes['orientation'] || attributes['layout'] || attributes['scrollDirection'] || 'vertical'
          is_horizontal = layout.to_s.downcase == 'horizontal'
          # lazy: "none" → drop overflow scroll classes; Collection is expected to
          # render inside an already-scrollable parent.
          is_lazy = attributes['lazy'] != 'none'

          if is_horizontal
            # Horizontal scroll collection
            classes << 'overflow-x-auto' if is_lazy
            classes << 'flex flex-row'
            classes << 'flex-nowrap' if is_lazy && attributes['scrollEnabled'] != false
            # For horizontal: columnSpacing (or lineSpacing/itemSpacing) = gap between items
            spacing = attributes['columnSpacing'] || attributes['lineSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            classes << "gap-[#{spacing}px]" if spacing
          elsif !columns_binding && columns == 1
            # List style (single column). A binding-form `columns` can't
            # reach this branch — the runtime count is unknown at codegen
            # time so we always route through the grid path below to keep
            # the layout structure stable across runtime column changes.
            classes << 'flex flex-col'
            classes << 'overflow-y-auto' if is_lazy && attributes['scrollEnabled'] != false
            # lineSpacing for vertical spacing between items
            spacing = attributes['lineSpacing'] || attributes['itemSpacing'] || attributes['spacing']
            classes << "gap-[#{spacing}px]" if spacing
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
            # lineSpacing for row gap, itemSpacing for column gap
            row_gap = attributes['lineSpacing']
            col_gap = attributes['itemSpacing'] || attributes['spacing']
            if row_gap && col_gap
              classes << "gap-x-[#{col_gap}px] gap-y-[#{row_gap}px]"
            elsif row_gap
              classes << "gap-y-[#{row_gap}px]"
            elsif col_gap
              classes << "gap-[#{col_gap}px]"
            end
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

          classes.compact.reject(&:empty?).join(' ')
        end

        private

        def generate_collection_content(indent)
          sections = attributes['sections'] || []
          items_binding = extract_collection_binding(attributes['items'])

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
            lines << "#{indent_str(indent + 2)}<#{cell_view} key={#{key_expr}} data={cellData#{cell_cast}} />"
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

        def generate_legacy_content(indent)
          lines = []

          cell_classes = attributes['cellClasses'] || []
          header_classes = attributes['headerClasses'] || []
          footer_classes = attributes['footerClasses'] || []

          cell_view = extract_view_name(cell_classes.first) if cell_classes.any?
          header_view = extract_view_name(header_classes.first) if header_classes.any?
          footer_view = extract_view_name(footer_classes.first) if footer_classes.any?

          items_binding = extract_collection_binding(attributes['items'])

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
              lines << "#{indent_str(indent + 2)}<#{cell_view} key={index} data={item} />"
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
