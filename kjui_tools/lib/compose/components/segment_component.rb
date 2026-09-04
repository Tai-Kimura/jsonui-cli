# frozen_string_literal: true

require_relative '../helpers/modifier_builder'
require_relative '../helpers/resource_resolver'

module KjuiTools
  module Compose
    module Components
      class SegmentComponent
        def self.generate(json_data, depth, required_imports = nil, parent_type = nil)
          required_imports&.add(:segment)

          # `selectedTabIndex` is the declared alias of selectedIndex (the
          # dynamic table folds it; TabView declares the same alias). Folding
          # it once here reaches every read site below — the alias fixture
          # measured a parity gap against the dynamic render because only the
          # canonical spelling was read (d=15, run 31202080745). Canonical
          # wins when both are written.
          if json_data['selectedTabIndex'] && !json_data['selectedIndex']
            json_data = json_data.merge('selectedIndex' => json_data['selectedTabIndex'])
          end

          # Segment uses 'selectedIndex' or 'bind' for selected index
          # Track if the selected index is dynamic (from data binding) or static
          is_dynamic_index = false
          selected_index = if json_data['selectedIndex']
            if json_data['selectedIndex'].is_a?(String) && json_data['selectedIndex'].match(/@\{([^}]+)\}/)
              variable = $1
              is_dynamic_index = true
              "data.#{variable}"
            else
              # Direct integer value - keep as integer for proper comparison
              json_data['selectedIndex'].to_i
            end
          elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
            variable = $1
            is_dynamic_index = true
            "data.#{variable}"
          else
            0  # Default to 0 as integer
          end
          
          # `items` only. `segments` was an undeclared alias -- absent from
          # attribute_definitions.json, read by no other face, and used by no
          # consumer layout (measured across six faces: 0). It is gone from the
          # extract vocabulary in the same commit, so a layout still writing it
          # now renders nothing rather than rendering from strings nobody
          # collected.
          # Objects are not items — the declaration says static labels, and
          # the dynamic runtime keeps primitives only (DynamicSegmentComponent
          # mapNotNull). Dropped before anything indexes them.
          # Declared `type: "array"` with no binding, so only an array is
          # items. A binding string used to be resolved here into a
          # `forEachIndexed` — a feature this face invented alone (sjui
          # raised NoMethodError on the same input, iOS dynamic takes
          # strings only, and no face uses it). The validator names it.
          raw_items = json_data['items']
          segments = raw_items.is_a?(Array) ? raw_items.reject { |item| item.is_a?(Hash) || item.is_a?(Array) } : []
          
          code = indent("Segment(", depth)
          # For display in Segment parameter, always output as string
          selected_tab_param = is_dynamic_index ? selected_index : selected_index.to_s
          code += "\n" + indent("selectedTabIndex = #{selected_tab_param},", depth + 1)
          
          # Add enabled state if specified
          if json_data.key?('enabled')
            enabled_value = json_data['enabled']
            if enabled_value.is_a?(String) && (enabled_inner = Helpers::BindingExpression.extract_inner(enabled_value))
              code += "\n" + indent("enabled = #{Helpers::BindingExpression.value_access(enabled_inner, negatable: true)},", depth + 1)
            else
              code += "\n" + indent("enabled = #{enabled_value},", depth + 1)
            end
          end
          
          # Tab colors - only add if specified, otherwise use defaults from Configuration
          colors_params = []

          # Background color (containerColor) - default to transparent
          bg_value = json_data['backgroundColor'] || json_data['background']
          if bg_value
            bg_color = Helpers::ResourceResolver.process_color(bg_value, required_imports)
            colors_params << "containerColor = #{bg_color}"
          else
            colors_params << "containerColor = Color.Transparent"
          end
          
          # Label colours: fontColor is the unselected label and
          # selectedFontColor the selected one, falling back to fontColor
          # (contract: semantics.segmentLabelColors). normalColor / selectedColor
          # are declared aliases — the normalizer canonicalizes them, so only the
          # canonical spellings are read here.
          # Normal text color (contentColor) - for unselected tabs
          if json_data['fontColor']
            normal_color = Helpers::ResourceResolver.process_color(json_data['fontColor'], required_imports)
            colors_params << "contentColor = #{normal_color}"
          end
          
          # Selected text color (selectedContentColor)
          if json_data['selectedFontColor'] || json_data['fontColor']
            color = json_data['selectedFontColor'] || json_data['fontColor']
            selected_color = Helpers::ResourceResolver.process_color(color, required_imports)
            colors_params << "selectedContentColor = #{selected_color}"
          end

          # Selected-segment background. tintColor paints the SELECTED SEGMENT'S
          # BACKGROUND on every platform (ios selectedSegmentTintColor, web bg-*);
          # android used to feed it into the label colour instead, so the same
          # declaration coloured different things (contract:
          # semantics.segmentLabelColors). The indicator is this component's
          # selected-state background — its default is Configuration.Segment
          # .defaultSelectedBackgroundColor. indicatorColor was an undeclared
          # second spelling for the same thing and is no longer read.
          if json_data['tintColor'] || json_data['selectedSegmentTintColor']
            indicator_color = Helpers::ResourceResolver.process_color(
              json_data['tintColor'] || json_data['selectedSegmentTintColor'],
              required_imports
            )
            colors_params << "indicatorColor = #{indicator_color}"
          end
          
          if colors_params.any?
            code += "\n" + indent(colors_params.join(",\n"), depth + 1) + ","
          end
          
          # Build modifiers
          modifiers = []
          modifiers.concat(Helpers::ModifierBuilder.build_test_tag(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_margins(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_size(json_data, parent_type, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_offset(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_alpha(json_data, required_imports))
          modifiers.concat(Helpers::ModifierBuilder.build_padding(json_data))
          modifiers.concat(Helpers::ModifierBuilder.build_weight(json_data, parent_type))

          code += Helpers::ModifierBuilder.format(modifiers, depth) if modifiers.any?
          
          code += "\n" + indent(") {", depth)
          
          # Generate tabs
          if segments.is_a?(Array)
            segments.each_with_index do |segment, index|
              code += "\n" + indent("Tab(", depth + 1)
              # For selected comparison, handle both dynamic and static cases
              selected_comparison = is_dynamic_index ? "(#{selected_index} == #{index})" : (selected_index == index).to_s
              code += "\n" + indent("selected = #{selected_comparison},", depth + 2)
              
              # Add enabled state to Tab if segment is disabled
              if json_data.key?('enabled')
                enabled_value = json_data['enabled']
                if enabled_value.is_a?(String) && (enabled_inner = Helpers::BindingExpression.extract_inner(enabled_value))
                  code += "\n" + indent("enabled = #{Helpers::BindingExpression.value_access(enabled_inner, negatable: true)},", depth + 2)
                else
                  code += "\n" + indent("enabled = #{enabled_value},", depth + 2)
                end
              end
              
              code += "\n" + indent("onClick = {", depth + 2)
              
              # Check if we have a binding variable
              has_binding = false
              binding_variable = nil
              
              if json_data['selectedIndex'] && json_data['selectedIndex'].is_a?(String) && json_data['selectedIndex'].match(/@\{([^}]+)\}/)
                has_binding = true
                binding_variable = $1
              elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
                has_binding = true
                binding_variable = $1
              end
              
              # Generate onClick handler
              # onValueChange (camelCase) -> binding format only (@{functionName})
              view_id = json_data['id'] || 'segment'
              if json_data['onValueChange']
                if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                  handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, index.to_s)
                  if has_binding
                    code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to #{index}))", depth + 3)
                    code += "\n" + indent("#{handler_call}", depth + 3)
                  else
                    code += "\n" + indent("#{handler_call}", depth + 3)
                  end
                else
                  code += "\n" + indent("// ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 3)
                end
              elsif json_data['valueChange'].is_a?(String) && !json_data['valueChange'].empty?
                # `valueChange` is the legacy SELECTOR spelling (a bare
                # method name, like `onclick`) that only UIKit read. Selector
                # names camelize, matching the rjui/sjui handling of the same
                # attribute.
                selector = camelize_selector(json_data['valueChange'])
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to #{index}))", depth + 3) if has_binding
                code += "\n" + indent("data.#{selector}?.invoke()", depth + 3)
              elsif has_binding
                # Update the bound variable
                code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to #{index}))", depth + 3)
              else
                # No action if selectedIndex is a static value with no binding
                code += "\n" + indent("// Static selected index", depth + 3)
              end
              
              code += "\n" + indent("},", depth + 2)
              
              # Generate text with color based on selection
              # Store color info for later use
              normal_color = json_data['fontColor']
              selected_color = json_data['selectedFontColor'] || json_data['fontColor']
              
              if normal_color || selected_color
                # Need to handle text color based on selection
                resolved_text = Helpers::ResourceResolver.process_text(segment, required_imports)
                code += "\n" + indent("text = {", depth + 2)
                code += "\n" + indent("Text(", depth + 3)
                code += "\n" + indent("#{resolved_text},", depth + 4)
                
                # Use conditional color based on selection
                if is_dynamic_index
                  if selected_color && normal_color
                    selected_resolved = Helpers::ResourceResolver.process_color(selected_color, required_imports)
                    normal_resolved = Helpers::ResourceResolver.process_color(normal_color, required_imports)
                    code += "\n" + indent("color = if (#{selected_index} == #{index}) #{selected_resolved} else #{normal_resolved}", depth + 4)
                  elsif selected_color
                    selected_resolved = Helpers::ResourceResolver.process_color(selected_color, required_imports)
                    code += "\n" + indent("color = if (#{selected_index} == #{index}) #{selected_resolved} else Color.Unspecified", depth + 4)
                  elsif normal_color
                    normal_resolved = Helpers::ResourceResolver.process_color(normal_color, required_imports)
                    code += "\n" + indent("color = if (#{selected_index} == #{index}) Color.Unspecified else #{normal_resolved}", depth + 4)
                  end
                else
                  # Static index
                  is_selected = (selected_index == index)
                  if is_selected && selected_color
                    selected_resolved = Helpers::ResourceResolver.process_color(selected_color, required_imports)
                    code += "\n" + indent("color = #{selected_resolved}", depth + 4)
                  elsif !is_selected && normal_color
                    normal_resolved = Helpers::ResourceResolver.process_color(normal_color, required_imports)
                    code += "\n" + indent("color = #{normal_resolved}", depth + 4)
                  end
                end
                
                code += "\n" + indent(")", depth + 3)
                code += "\n" + indent("}", depth + 2)
              else
                resolved_text = Helpers::ResourceResolver.process_text(segment, required_imports)
                code += "\n" + indent("text = { Text(#{resolved_text}) }", depth + 2)
              end
              
              code += "\n" + indent(")", depth + 1)
            end
          elsif segments.is_a?(String) && segments.match(/@\{([^}]+)\}/)
            # Dynamic segments from data binding
            segments_var = $1
            code += "\n" + indent("data.#{segments_var}.forEachIndexed { index, segment ->", depth + 1)
            code += "\n" + indent("Tab(", depth + 2)
            # For dynamic segments, selected_index comparison depends on whether the index itself is dynamic
            selected_comparison = is_dynamic_index ? "(#{selected_index} == index)" : "(#{selected_index} == index)"
            code += "\n" + indent("selected = #{selected_comparison},", depth + 3)
            
            # Add enabled state to Tab if segment is disabled
            if json_data.key?('enabled')
              enabled_value = json_data['enabled']
              if enabled_value.is_a?(String) && (enabled_inner = Helpers::BindingExpression.extract_inner(enabled_value))
                code += "\n" + indent("enabled = #{Helpers::BindingExpression.value_access(enabled_inner, negatable: true)},", depth + 3)
              else
                code += "\n" + indent("enabled = #{enabled_value},", depth + 3)
              end
            end
            
            code += "\n" + indent("onClick = {", depth + 3)
            
            # Check if we have a binding variable
            has_binding = false
            binding_variable = nil
            
            if json_data['selectedIndex'] && json_data['selectedIndex'].is_a?(String) && json_data['selectedIndex'].match(/@\{([^}]+)\}/)
              has_binding = true
              binding_variable = $1
            elsif json_data['bind'] && json_data['bind'].match(/@\{([^}]+)\}/)
              has_binding = true
              binding_variable = $1
            end
            
            # Generate onClick handler
            # onValueChange (camelCase) -> binding format only (@{functionName})
            view_id = json_data['id'] || 'segment'
            if json_data['onValueChange']
              if Helpers::ModifierBuilder.is_binding?(json_data['onValueChange'])
                handler_call = Helpers::ModifierBuilder.get_event_handler_invocation(json_data['onValueChange'], view_id, 'index')
                if has_binding
                  code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to index))", depth + 4)
                  code += "\n" + indent("#{handler_call}", depth + 4)
                else
                  code += "\n" + indent("#{handler_call}", depth + 4)
                end
              else
                code += "\n" + indent("// ERROR: #{json_data['onValueChange']} - camelCase events require binding format @{functionName}", depth + 4)
              end
            elsif json_data['valueChange'].is_a?(String) && !json_data['valueChange'].empty?
              # `valueChange` is the legacy SELECTOR spelling (a bare method
              # name, like `onclick`) that only UIKit read. Selector names
              # camelize, matching the rjui/sjui handling of the same
              # attribute.
              code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to index))", depth + 4) if has_binding
              code += "\n" + indent("data.#{camelize_selector(json_data['valueChange'])}?.invoke()", depth + 4)
            elsif has_binding
              # Update the bound variable
              code += "\n" + indent("viewModel.updateData(mapOf(\"#{binding_variable}\" to index))", depth + 4)
            else
              # No action if selectedIndex is a static value with no binding
              code += "\n" + indent("// Static selected index", depth + 4)
            end
            
            code += "\n" + indent("},", depth + 3)
            
            # Generate text with color based on selection for dynamic segments
            normal_color = json_data['fontColor']
            selected_color = json_data['selectedFontColor'] || json_data['fontColor']
            
            if normal_color || selected_color
              code += "\n" + indent("text = {", depth + 3)
              code += "\n" + indent("Text(", depth + 4)
              code += "\n" + indent("segment,", depth + 5)
              
              # Use conditional color based on selection
              if selected_color && normal_color
                selected_resolved = Helpers::ResourceResolver.process_color(selected_color, required_imports)
                normal_resolved = Helpers::ResourceResolver.process_color(normal_color, required_imports)
                code += "\n" + indent("color = if (#{selected_comparison}) #{selected_resolved} else #{normal_resolved}", depth + 5)
              elsif selected_color
                selected_resolved = Helpers::ResourceResolver.process_color(selected_color, required_imports)
                code += "\n" + indent("color = if (#{selected_comparison}) #{selected_resolved} else Color.Unspecified", depth + 5)
              elsif normal_color
                normal_resolved = Helpers::ResourceResolver.process_color(normal_color, required_imports)
                code += "\n" + indent("color = if (#{selected_comparison}) Color.Unspecified else #{normal_resolved}", depth + 5)
              end
              
              code += "\n" + indent(")", depth + 4)
              code += "\n" + indent("}", depth + 3)
            else
              code += "\n" + indent("text = { Text(segment) }", depth + 3)
            end
            
            code += "\n" + indent(")", depth + 2)
            code += "\n" + indent("}", depth + 1)
          end
          
          code += "\n" + indent("}", depth)
          code
        end
        
        private
        
        # snake_case selector -> camelCase data-property name.
        def self.camelize_selector(name)
          name.split('_').each_with_index.map { |w, i| i.zero? ? w : w.capitalize }.join
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