# frozen_string_literal: true

require_relative '../helpers/modifier_builder'

module KjuiTools
  module Compose
    module Components
      class TableComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:lazy_column)
          
          # Table uses data binding for items
          items = if json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          elsif json_data['items'] && json_data['items'].match(/@\{([^}]+)\}/)
            variable = $1
            "data.#{variable}"
          else
            'emptyList()'
          end
          
          code = indent("LazyColumn(", depth)
          
          # Content padding
          if json_data['contentPadding']
            padding = json_data['contentPadding']
            if padding.is_a?(Array) && padding.length == 4
              code += "\n" + indent("contentPadding = PaddingValues(top = #{padding[0]}.dp, end = #{padding[1]}.dp, bottom = #{padding[2]}.dp, start = #{padding[3]}.dp),", depth + 1)
            elsif padding.is_a?(Numeric)
              code += "\n" + indent("contentPadding = PaddingValues(#{padding}.dp),", depth + 1)
            end
          end
          
          # Vertical arrangement (spacing between rows)
          if json_data['rowSpacing'] || json_data['spacing']
            required_imports&.add(:arrangement)
            spacing = json_data['rowSpacing'] || json_data['spacing'] || 0
            code += "\n" + indent("verticalArrangement = Arrangement.spacedBy(#{spacing}.dp),", depth + 1)
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_background(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_clickable(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth)
          
          code += "\n" + indent(") {", depth)
          
          # Table header if specified
          if json_data['header']
            code += "\n" + indent("item {", depth + 1)
            code += generate_header_row(json_data['header'], depth + 2, required_imports)
            code += "\n" + indent("}", depth + 1)
            
            # Divider after header
            if json_data['separatorStyle'] != 'none'
              code += "\n" + indent("item {", depth + 1)
              code += "\n" + indent("Divider(", depth + 2)
              code += "\n" + indent("color = Color.LightGray,", depth + 3)
              code += "\n" + indent("thickness = 1.dp", depth + 3)
              code += "\n" + indent(")", depth + 2)
              code += "\n" + indent("}", depth + 1)
            end
          end
          
          # Table rows
          code += "\n" + indent("items(#{items}) { item ->", depth + 1)
          
          # Row content
          if json_data['cell']
            # Custom cell template
            cell_content = generate_table_cell(json_data['cell'], depth + 2, required_imports)
            code += "\n" + cell_content
          else
            # Default row
            code += generate_default_row(json_data, depth + 2, required_imports)
          end
          
          # Separator between rows
          if json_data['separatorStyle'] != 'none'
            code += "\n" + indent("Divider(", depth + 2)
            
            # Separator inset
            if json_data['separatorInset']
              inset = json_data['separatorInset']
              if inset.is_a?(Hash)
                start_padding = inset['left'] || inset['start'] || 0
                code += "\n" + indent("modifier = Modifier.padding(start = #{start_padding}.dp),", depth + 3)
              end
            end
            
            code += "\n" + indent("color = Color.LightGray,", depth + 3)
            code += "\n" + indent("thickness = 0.5.dp", depth + 3)
            code += "\n" + indent(")", depth + 2)
          end
          
          code += "\n" + indent("}", depth + 1)
          
          code += "\n" + indent("}", depth)
          code
        end
        
        private
        
        def self.generate_header_row(header_data, depth, required_imports)
          code = indent("Row(", depth)
          code += "\n" + indent("modifier = Modifier", depth + 1)
          code += "\n" + indent("    .fillMaxWidth()", depth + 1)
          code += "\n" + indent("    .padding(horizontal = 16.dp, vertical = 12.dp),", depth + 1)
          code += "\n" + indent("horizontalArrangement = Arrangement.SpaceBetween", depth + 1)
          code += "\n" + indent(") {", depth)
          
          if header_data.is_a?(Array)
            header_data.each do |column|
              code += "\n" + indent("Text(", depth + 1)
              code += "\n" + indent("text = \"#{column}\",", depth + 2)
              code += "\n" + indent("fontWeight = FontWeight.Bold,", depth + 2)
              code += "\n" + indent("modifier = Modifier.weight(1f)", depth + 2)
              code += "\n" + indent(")", depth + 1)
            end
          else
            code += "\n" + indent("Text(text = \"Header\", fontWeight = FontWeight.Bold)", depth + 1)
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        def self.generate_table_cell(cell_data, depth, required_imports)
          code = indent("Row(", depth)
          code += "\n" + indent("modifier = Modifier", depth + 1)
          code += "\n" + indent("    .fillMaxWidth()", depth + 1)
          code += "\n" + indent("    .clickable { /* Handle row click */ }", depth + 1)
          code += "\n" + indent("    .padding(horizontal = 16.dp, vertical = 12.dp)", depth + 1)
          code += "\n" + indent(") {", depth)
          
          # Cell content based on template
          code += "\n" + indent("// Custom cell rendering", depth + 1)
          code += "\n" + indent("Text(text = item.toString())", depth + 1)
          
          code += "\n" + indent("}", depth)
          code
        end
        
        def self.generate_default_row(json_data, depth, required_imports)
          row_height = json_data['rowHeight'] || 60
          
          code = "\n" + indent("Row(", depth)
          code += "\n" + indent("modifier = Modifier", depth + 1)
          code += "\n" + indent("    .fillMaxWidth()", depth + 1)
          code += "\n" + indent("    .height(#{row_height}.dp)", depth + 1)
          code += "\n" + indent("    .clickable { /* Handle row click */ }", depth + 1)
          code += "\n" + indent("    .padding(horizontal = 16.dp),", depth + 1)
          code += "\n" + indent("verticalAlignment = Alignment.CenterVertically", depth + 1)
          code += "\n" + indent(") {", depth)
          code += "\n" + indent("Text(text = item.toString())", depth + 1)
          code += "\n" + indent("}", depth)
          code
        end
        
        def self.indent(text, level)
          return text if level == 0
          spaces = '    ' * level
          text.split("\n").map { |line| 
            line.empty? ? line : spaces + line 
          }.join("\n")
        end
      end
    end
  end
end