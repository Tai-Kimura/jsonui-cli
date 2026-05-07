# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/type_converter'
require_relative '../core/generated_marker'
require_relative 'style_loader'
require_relative 'include_expander'
require_relative 'helpers/string_manager_helper'

module SjuiTools
  module SwiftUI
    class DataModelUpdater
      include Helpers::StringManagerHelper
      def initialize(mode: nil)
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        @layouts_dir = File.join(@source_path, @config['layouts_directory'] || 'Layouts')
        @data_dir = File.join(@source_path, @config['data_directory'] || 'Data')
        @styles_dir = File.join(@source_path, @config['styles_directory'] || 'Styles')
        @mode = mode || @config['mode'] || 'swiftui'
      end

      def update_data_models
        # Process all JSON files in Layouts directory (excluding Resources and Styles folders)
        json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          # Skip Resources and Styles folders (styles don't need data models)
          next true if file.include?(File.join(@layouts_dir, 'Resources')) || file.include?('/Styles/')
          # Skip files with "mode": "uikit" (SwiftUI data models don't need UIKit-only files)
          begin
            json_content = JSON.parse(File.read(file))
            file_mode = json_content['mode']
            next true if file_mode && file_mode.downcase == 'uikit'
          rescue JSON::ParserError
            # continue
          end
          false
        end

        json_files.each do |json_file|
          process_json_file(json_file)
        end
      end

      private

      def process_json_file(json_file)
        json_content = File.read(json_file)
        json_data = JSON.parse(json_content)

        # Skip partial files (they are included in other views, not standalone)
        if json_data['partial'] == true
          return
        end

        # Expand styles before extracting data and actions
        expanded_data = StyleLoader.load_and_merge(json_data, @styles_dir)

        # Expand includes inline with ID prefixes
        expanded_data = IncludeExpander.process_includes(expanded_data, File.dirname(json_file))

        # Extract event bindings (handler name => component/attribute info)
        event_bindings = extract_event_bindings(expanded_data)

        # Extract data properties from expanded JSON (pass event_bindings for Event type conversion)
        data_properties = extract_data_properties(expanded_data, [], event_bindings)

        # Scan for collections with cellIdProperty + scrollTo to override scrollTo type
        override_scroll_to_types(expanded_data, data_properties)

        # Extract onclick actions from expanded JSON
        onclick_actions = extract_onclick_actions(expanded_data)

        # Collect all view IDs and check for conflicts with data property names
        view_ids = collect_view_ids(expanded_data)
        check_id_data_conflicts(json_file, view_ids, data_properties)

        # Always create/update data file, even if no properties
        # Get the view name from file path
        base_name = File.basename(json_file, '.json')

        # Update the Data model file (always in root Data directory)
        update_data_file(base_name, data_properties, onclick_actions)
      end

      # Collect all 'id' values from the JSON tree
      def collect_view_ids(json_data, ids = Set.new)
        return ids unless json_data.is_a?(Hash) || json_data.is_a?(Array)

        if json_data.is_a?(Hash)
          if json_data['id']
            ids << to_camel_case_id(json_data['id'])
          end
          child = json_data['child']
          if child.is_a?(Array)
            child.each { |c| collect_view_ids(c, ids) }
          elsif child
            collect_view_ids(child, ids)
          end
          # Check header/footer/cell in Collections
          %w[header footer cell].each do |key|
            collect_view_ids(json_data[key], ids) if json_data[key]
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| collect_view_ids(item, ids) }
        end

        ids
      end

      # Warn if any data property name conflicts with a view ID
      def check_id_data_conflicts(json_file, view_ids, data_properties)
        data_names = data_properties.map { |p| p['name'] }
        conflicts = data_names & view_ids.to_a
        return if conflicts.empty?

        file_name = File.basename(json_file)
        conflicts.each do |name|
          puts "\e[33m  WARNING: #{file_name}: data property '#{name}' conflicts with a view ID. Add a suffix to the view ID (e.g., '#{name}_view', '#{name}_label', '#{name}_container').\e[0m"
        end
      end
      
      # Extract event bindings from JSON to map handler names to component/attribute
      # Used for converting Event type to platform-specific types
      # @param json_data [Hash] the JSON data
      # @param bindings [Hash] accumulated bindings (handler_name => { component:, attribute: })
      # @return [Hash] event bindings
      def extract_event_bindings(json_data, bindings = {})
        return bindings unless json_data.is_a?(Hash) || json_data.is_a?(Array)

        if json_data.is_a?(Hash)
          component_type = json_data['type']

          # Event attributes to check
          event_attrs = %w[onClick onValueChange onToggle onTextChange onChange onLongPress]

          event_attrs.each do |attr|
            value = json_data[attr]
            next unless value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

            handler_name = value[2...-1]
            # onToggle is an alias of onValueChange on Switch/Toggle.
            # Normalize so type_mapping.json (keyed on onValueChange) resolves correctly.
            normalized_attr = attr
            if attr == 'onToggle' && %w[Switch Toggle].include?(component_type)
              normalized_attr = 'onValueChange'
            end
            bindings[handler_name] = {
              component: component_type,
              attribute: normalized_attr
            }
          end

          # Process children
          child = json_data['child']
          if child.is_a?(Array)
            child.each { |c| extract_event_bindings(c, bindings) }
          elsif child
            extract_event_bindings(child, bindings)
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_event_bindings(item, bindings) }
        end

        bindings
      end

      # Scan layout for Collection components with cellIdProperty + scrollTo
      # and override the matching data property type from PassthroughSubject<Int, Never>
      # to PassthroughSubject<String, Never>
      def override_scroll_to_types(json_data, data_properties)
        scroll_to_props = collect_string_scroll_to_props(json_data)
        return if scroll_to_props.empty?

        data_properties.each do |prop|
          if scroll_to_props.include?(prop['name'])
            prop['class'] = prop['class'].to_s.gsub('PassthroughSubject<Int', 'PassthroughSubject<String')
          end
        end
      end

      # Recursively find scrollTo property names that need String type (cellIdProperty is set)
      def collect_string_scroll_to_props(json_data, result = Set.new)
        return result unless json_data.is_a?(Hash) || json_data.is_a?(Array)

        if json_data.is_a?(Hash)
          if json_data['type'] == 'Collection' && json_data['cellIdProperty'] && json_data['scrollTo']
            scroll_to = json_data['scrollTo']
            if scroll_to.is_a?(String) && scroll_to.start_with?('@{') && scroll_to.end_with?('}')
              prop_name = scroll_to[2...-1]
              result.add(prop_name)
            end
          end

          child = json_data['child']
          if child.is_a?(Array)
            child.each { |c| collect_string_scroll_to_props(c, result) }
          elsif child
            collect_string_scroll_to_props(child, result)
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| collect_string_scroll_to_props(item, result) }
        end

        result
      end

      def extract_onclick_actions(json_data, actions = Set.new)
        if json_data.is_a?(Hash)
          # Check for onClick attribute (binding format: @{functionName})
          if json_data['onClick'] && json_data['onClick'].is_a?(String)
            # Extract function name from binding format
            method_name = json_data['onClick'].gsub(/^@\{|\}$/, '')
            actions.add(method_name)
          end

          # Process children
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_onclick_actions(child, actions)
              end
            else
              extract_onclick_actions(json_data['child'], actions)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_onclick_actions(item, actions)
          end
        end

        actions.to_a
      end

      def extract_data_properties(json_data, properties = [], event_bindings = {})
        if json_data.is_a?(Hash)
          # Check for data section
          if json_data['data'] && json_data['data'].is_a?(Array)
            json_data['data'].each do |data_item|
              if data_item.is_a?(Hash)
                # Platform/mode filter: skip if not matching
                if data_item['platform']
                  next unless data_item['platform'] == 'swift'
                end
                if data_item['mode']
                  next unless data_item['mode'] == 'swiftui'
                end

                # Check if this property is bound to an event and has Event type
                # Do this BEFORE normalize_data_property to avoid double-wrapping
                prop_name = data_item['name']
                raw_class = data_item['class'].to_s

                modified_item = data_item.dup
                if event_bindings[prop_name] && raw_class.include?('Event')
                  # Get event type from type_mapping.json
                  binding_info = event_bindings[prop_name]
                  event_type = Core::TypeConverter.get_event_type(
                    binding_info[:component],
                    binding_info[:attribute],
                    'swiftui'
                  )

                  if event_type
                    # Convert Event to platform-specific type in the function signature
                    # event_type is an array like ["String", "Bool"] for swiftui
                    if event_type.is_a?(Array)
                      # Convert to tuple type: String, Bool (without extra parens)
                      # Replace (Event) with (String, Bool) - the parens are already there
                      converted_type = event_type.join(', ')
                      modified_item['class'] = raw_class.gsub('(Event)', "(#{converted_type})")
                    else
                      modified_item['class'] = raw_class.gsub('Event', event_type)
                    end
                  end
                end

                # Normalize type using TypeConverter (mode: swiftui) after Event replacement
                normalized = Core::TypeConverter.normalize_data_property(modified_item, 'swiftui')
                properties << normalized
              end
            end
          end

          # Auto-generate isFocused property for TextField components
          if json_data['type'] == 'TextField' && json_data['id']
            focus_prop_name = to_camel_case_id(json_data['id']) + 'IsFocused'
            unless properties.any? { |p| p['name'] == focus_prop_name }
              properties << { 'name' => focus_prop_name, 'class' => 'Bool', 'defaultValue' => false }
            end
          end

          # Process children
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_data_properties(child, properties, event_bindings)
              end
            else
              extract_data_properties(json_data['child'], properties, event_bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_data_properties(item, properties, event_bindings)
          end
        end

        properties
      end

      def update_data_file(base_name, data_properties, onclick_actions = [])
        # Convert base_name to PascalCase for searching
        pascal_view_name = to_pascal_case(base_name)

        # Check for existing file with different casing
        existing_file = find_existing_data_file(pascal_view_name)

        if existing_file
          # Extract the actual struct name from the existing file
          existing_struct_name = extract_struct_name(existing_file)
          if existing_struct_name
            # Use the exact struct name from the existing file
            view_name = existing_struct_name.sub(/Data$/, '')
          else
            # Fallback to pascal case if we can't extract the name
            view_name = pascal_view_name
          end
          data_file_path = existing_file
        else
          # For new files, use pascal case
          view_name = pascal_view_name
          data_file_path = File.join(@data_dir, "#{view_name}Data.swift")
          # If file doesn't exist, create it with empty data structure
          unless File.exist?(data_file_path)
            # Create directory if needed
            FileUtils.mkdir_p(@data_dir)
          end
        end
        
        # Generate new content
        content = generate_data_content(view_name, data_properties, onclick_actions, json_base_name: base_name)
        
        # Write the updated content
        File.write(data_file_path, content)
        puts "  Updated Data model: #{data_file_path}"
      end
      
      def find_existing_data_file(view_name)
        # Try exact match first
        exact_path = File.join(@data_dir, "#{view_name}Data.swift")
        return exact_path if File.exist?(exact_path)

        # Try case-insensitive search
        Dir.glob(File.join(@data_dir, '*Data.swift')).find do |file|
          File.basename(file, '.swift').downcase == "#{view_name}data".downcase
        end
      end
      
      def extract_struct_name(file_path)
        content = File.read(file_path)
        if match = content.match(/struct\s+(\w+Data)\s*{/)
          match[1]
        else
          nil
        end
      end

      def generate_data_content(view_name, data_properties, onclick_actions = [], json_base_name: nil)
        needs_combine = data_properties.any? { |p| p['class'].to_s.include?('PassthroughSubject') || p['class'].to_s.include?('CurrentValueSubject') }
        combine_import = needs_combine ? "\nimport Combine" : ""
        marker_source = json_base_name ? "Layouts/#{json_base_name}.json" : "#{view_name}Data"
        marker_header = Core::GeneratedMarker.comment_header(
          source: marker_source,
          generator: "sjui build"
        )
        content = <<~SWIFT
        #{marker_header}

        import Foundation
        import SwiftUI
        import SwiftJsonUI#{combine_import}

        struct #{view_name}Data {
            // Data properties from JSON
        SWIFT
        
        if data_properties.empty?
          content += "    // No data properties defined in JSON\n"
        else
          # Add each property with correct type and default value
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']  # Use class name directly
            default_value = prop['defaultValue']

            # If no default value or nil, make it optional
            if default_value.nil? || default_value == 'nil'
              # Check if type already ends with '?' (already optional)
              if class_type.end_with?('?')
                content += "    var #{name}: #{class_type} = nil\n"
              else
                content += "    var #{name}: #{class_type}? = nil\n"
              end
            else
              formatted_value = format_default_value(default_value, class_type)
              content += "    var #{name}: #{class_type} = #{formatted_value}\n"
            end
          end
        end

        # Add onclick action properties as closures (skip if already in data_properties)
        data_prop_names = data_properties.map { |p| p['name'] }
        extra_onclick_actions = onclick_actions.reject { |action| data_prop_names.include?(action) }
        if !extra_onclick_actions.empty?
          content += "\n"
          content += "    // onClick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "    var #{action}: (() -> Void)? = nil\n"
          end
        end

        # Add update function to allow dynamic property updates
        content += "\n"
        content += "    // Update properties from dictionary\n"
        content += "    mutating func update(dictionary: [String: Any]) {\n"
        
        if !data_properties.empty?
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']
            
            # Generate update code based on type
            content += "        if let value = dictionary[\"#{name}\"] {\n"
            
            case class_type
            when 'String'
              content += "            if let stringValue = value as? String {\n"
              content += "                self.#{name} = stringValue\n"
              content += "            }\n"
            when 'Int'
              content += "            if let intValue = value as? Int {\n"
              content += "                self.#{name} = intValue\n"
              content += "            }\n"
            when 'Double'
              content += "            if let doubleValue = value as? Double {\n"
              content += "                self.#{name} = doubleValue\n"
              content += "            }\n"
            when 'Bool'
              content += "            if let boolValue = value as? Bool {\n"
              content += "                self.#{name} = boolValue\n"
              content += "            }\n"
            when 'CGFloat'
              content += "            if let floatValue = value as? CGFloat {\n"
              content += "                self.#{name} = floatValue\n"
              content += "            } else if let doubleValue = value as? Double {\n"
              content += "                self.#{name} = CGFloat(doubleValue)\n"
              content += "            }\n"
            else
              # For custom types, try to cast directly
              content += "            if let typedValue = value as? #{class_type} {\n"
              content += "                self.#{name} = typedValue\n"
              content += "            }\n"
            end
            
            content += "        }\n"
          end
        else
          # No properties, but still include empty function body
          content += "        // No properties to update\n"
        end
        
        content += "    }\n"
        
        # Add toDictionary function
        content += "\n"
        content += "    // Convert properties to dictionary for Dynamic mode\n"
        content += "    func toDictionary() -> [String: Any] {\n"
        content += "        var dict: [String: Any] = [:]\n"
        
        # Add data properties
        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties\n"
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']
            default_value = prop['defaultValue']
            
            # If it's optional, check for nil
            if default_value.nil? || default_value == 'nil'
              content += "        if let value = #{name} {\n"
              content += "            dict[\"#{name}\"] = value\n"
              content += "        }\n"
            else
              content += "        dict[\"#{name}\"] = #{name}\n"
            end
          end
        end
        
        # Add onclick actions not already in data_properties
        if !extra_onclick_actions.empty?
          content += "        \n"
          content += "        // Add onclick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "        if let #{action} = #{action} {\n"
            content += "            dict[\"#{action}\"] = #{action}\n"
            content += "        }\n"
          end
        end
        
        if data_properties.empty? && onclick_actions.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return dict\n"
        content += "    }\n"

        # Add toDictionary(binding:) for Dynamic mode reactivity
        content += "\n"
        content += "    #if DEBUG\n"
        content += "    // Convert properties to binding dictionary for Dynamic mode reactivity\n"
        content += "    // SwiftUI.Binding<T> values enable automatic re-rendering on changes\n"
        content += "    func toDictionary(binding dataBinding: SwiftUI.Binding<#{view_name}Data>) -> [String: Any] {\n"
        content += "        var dict: [String: Any] = [:]\n"

        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties as SwiftUI.Binding for reactivity\n"
          data_properties.each do |prop|
            name = prop['name']
            class_type = prop['class']
            default_value = prop['defaultValue']
            is_optional = default_value.nil? || default_value == 'nil'

            # Determine if type is bindable (primitive types)
            binding_type = case class_type.gsub('?', '')
              when 'String' then 'String'
              when 'Bool' then 'Bool'
              when 'Int' then 'Int'
              when 'Double' then 'Double'
              when 'CGFloat' then 'CGFloat'
              else nil
            end

            # Skip closure types
            if class_type.include?('->') || class_type.include?('Void')
              # Closure: keep as plain value
              content += "        if let #{name} = #{name} {\n"
              content += "            dict[\"#{name}\"] = #{name}\n"
              content += "        }\n"
            elsif binding_type
              # Bindable primitive type
              default_for_type = case binding_type
                when 'String' then '""'
                when 'Bool' then 'false'
                when 'Int' then '0'
                when 'Double' then '0.0'
                when 'CGFloat' then '0.0'
                else '""'
              end

              if is_optional
                content += "        if #{name} != nil {\n"
                content += "            dict[\"#{name}\"] = SwiftUI.Binding<#{binding_type}>(\n"
                content += "                get: { dataBinding.wrappedValue.#{name} ?? #{default_for_type} },\n"
                content += "                set: { dataBinding.wrappedValue.#{name} = $0 }\n"
                content += "            )\n"
                content += "        }\n"
              else
                content += "        dict[\"#{name}\"] = SwiftUI.Binding<#{binding_type}>(\n"
                content += "            get: { dataBinding.wrappedValue.#{name} },\n"
                content += "            set: { dataBinding.wrappedValue.#{name} = $0 }\n"
                content += "        )\n"
              end
            else
              # Non-bindable type (custom struct, array, etc.): keep as plain value
              if is_optional
                content += "        if let value = #{name} {\n"
                content += "            dict[\"#{name}\"] = value\n"
                content += "        }\n"
              else
                content += "        dict[\"#{name}\"] = #{name}\n"
              end
            end
          end
        end

        # Add onclick callbacks (same as toDictionary)
        if !extra_onclick_actions.empty?
          content += "        \n"
          content += "        // Add onclick action callbacks\n"
          extra_onclick_actions.each do |action|
            content += "        if let #{action} = #{action} {\n"
            content += "            dict[\"#{action}\"] = #{action}\n"
            content += "        }\n"
          end
        end

        if data_properties.empty? && onclick_actions.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return dict\n"
        content += "    }\n"
        content += "    #endif\n"

        content += "}\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"
        content
      end

      def format_default_value(value, json_class)
        if json_class == 'String'
          # Handle '' as empty string (common shorthand)
          if value == "''" || value.to_s.empty?
            '""'
          else
            # Use StringManager for localized strings
            get_text_with_string_manager("\"#{value}\"")
          end
        else
          # Check if default value contains a type constructor that needs mode conversion
          # e.g., "CollectionDataSource()" -> "UIKitCollectionDataSource()" in UIKit mode
          val_str = value.to_s
          Core::TypeConverter::MODE_TYPE_MAPPING.each do |generic_type, mode_map|
            mode = @mode || 'swiftui'
            mapped_type = mode_map[mode]
            if mapped_type && mapped_type != generic_type && val_str.include?(generic_type)
              return val_str.gsub(generic_type, mapped_type)
            end
          end
          value
        end
      end

      # Convert snake_case id to lowerCamelCase (e.g. "two_fa_hidden_input" -> "twoFaHiddenInput")
      def to_camel_case_id(str)
        parts = str.split('_')
        parts[0] + parts[1..].map(&:capitalize).join
      end

      def to_pascal_case(str)
        # Handle various naming patterns
        snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                   .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                   .downcase
        snake.split(/[_\-]/).map(&:capitalize).join
      end
    end
  end
end