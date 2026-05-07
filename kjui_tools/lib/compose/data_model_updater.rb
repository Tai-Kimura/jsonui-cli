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

module KjuiTools
  module Compose
    class DataModelUpdater
      def initialize
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        source_directory = @config['source_directory'] || 'src/main'
        @layouts_dir = File.join(@source_path, source_directory, @config['layouts_directory'] || 'assets/Layouts')
        @data_dir = File.join(@source_path, source_directory, @config['data_directory'] || 'kotlin/com/example/kotlinjsonui/sample/data')
        @package_name = @config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.app'
        @mode = @config['mode'] || 'compose'
      end

      def update_data_models(files_to_update = nil)
        # If specific files provided, only update those
        if files_to_update && !files_to_update.empty?
          puts "  Updating data models for #{files_to_update.length} modified files..."
          files_to_update.each do |json_file|
            process_json_file(json_file)
          end
        else
          # Process all JSON files in Layouts directory but exclude Resources and Styles folders
          json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
            # Skip Resources and Styles folders (styles don't need data models)
            file.include?('/Resources/') || file.include?('/Styles/')
          end

          puts "  Updating data models for #{json_files.length} files..."
          json_files.each do |json_file|
            process_json_file(json_file)
          end
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

        # Load and merge styles into the JSON data
        json_data = StyleLoader.load_and_merge(json_data)

        # Process includes - expand inline with ID prefix support (like SwiftJsonUI)
        json_data = IncludeExpander.process_includes(json_data, File.dirname(json_file))

        # Extract event bindings (handler name => component/attribute info)
        event_bindings = extract_event_bindings(json_data)

        # Extract data properties from JSON (pass event_bindings for Event type conversion)
        data_properties = extract_data_properties(json_data, [], 0, event_bindings)

        # Extract onclick actions from JSON (now includes actions from styles)
        onclick_actions = extract_onclick_actions(json_data)

        # Collect all view IDs and check for conflicts with data property names
        view_ids = collect_view_ids(json_data)
        check_id_data_conflicts(json_file, view_ids, data_properties)

        # Always create/update data file, even if no properties
        # Get the view name from file path
        base_name = File.basename(json_file, '.json')

        # Update the Data model file
        update_data_file(base_name, data_properties, onclick_actions)
      end

      # Collect all 'id' values from the JSON tree (converted to camelCase)
      def collect_view_ids(json_data, ids = Set.new)
        return ids unless json_data.is_a?(Hash) || json_data.is_a?(Array)

        if json_data.is_a?(Hash)
          if json_data['id']
            ids << snake_to_camel(json_data['id'])
          end
          child = json_data['child']
          if child.is_a?(Array)
            child.each { |c| collect_view_ids(c, ids) }
          elsif child
            collect_view_ids(child, ids)
          end
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

      def snake_to_camel(str)
        parts = str.split('_')
        parts[0] + parts[1..].map(&:capitalize).join
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

          # Event attributes to check (both camelCase and snake_case)
          event_attrs = %w[onClick onclick onValueChange onTextChange onChange onLongPress]

          event_attrs.each do |attr|
            value = json_data[attr]
            next unless value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

            handler_name = value[2...-1]
            bindings[handler_name] = {
              component: component_type,
              attribute: attr
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

      def extract_onclick_actions(json_data, actions = Set.new)
        if json_data.is_a?(Hash)
          # Check for onclick attribute
          if json_data['onclick'] && json_data['onclick'].is_a?(String)
            actions.add(json_data['onclick'])
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

      def extract_data_properties(json_data, properties = [], depth = 0, event_bindings = {})
        if json_data.is_a?(Hash)
          # Note: includes are now expanded inline by IncludeExpander, so we should
          # not see 'include' keys here. All data definitions (including those from
          # expanded includes with ID prefixes) should be collected.

          # Check for data section at any level and collect ALL data definitions
          if json_data['data']
            if json_data['data'].is_a?(Array)
              json_data['data'].each do |data_item|
                if data_item.is_a?(Hash) && data_item['name']
                  # Platform/mode filter: skip if not matching
                  if data_item['platform']
                    next unless data_item['platform'] == 'kotlin'
                  end
                  if data_item['mode']
                    next unless data_item['mode'] == @mode  # 'compose' or 'xml'
                  end

                  # Check if property already exists (by name) to avoid duplicates
                  unless properties.any? { |p| p['name'] == data_item['name'] }
                    # Normalize type using TypeConverter with mode
                    normalized = Core::TypeConverter.normalize_data_property(data_item, @mode)

                    # Check if this property is bound to an event and has Event type
                    prop_name = normalized['name']
                    prop_class = normalized['class'].to_s

                    if event_bindings[prop_name] && prop_class.include?('Event')
                      # Get event type from type_mapping.json
                      binding_info = event_bindings[prop_name]
                      event_type = Core::TypeConverter.get_event_type(
                        binding_info[:component],
                        binding_info[:attribute],
                        'compose'
                      )

                      if event_type
                        # Convert Event to platform-specific type in the function signature
                        # event_type is an array like ["String", "Boolean"] for compose
                        if event_type.is_a?(Array)
                          # Convert to Kotlin Pair type or multiple params
                          converted_type = event_type.join(', ')
                          normalized['class'] = prop_class.gsub('Event', converted_type)
                        else
                          normalized['class'] = prop_class.gsub('Event', event_type)
                        end
                      end
                    end

                    properties << normalized
                  end
                end
              end
            elsif json_data['data'].is_a?(Hash)
              # Handle simple data object format from styles
              json_data['data'].each do |name, value|
                unless properties.any? { |p| p['name'] == name }
                  # Infer type from value
                  class_type = if value.is_a?(Integer)
                    'Int'
                  elsif value.is_a?(Float)
                    'Float'
                  elsif value.is_a?(TrueClass) || value.is_a?(FalseClass)
                    'Boolean'
                  else
                    'String'
                  end

                  properties << {
                    'name' => name,
                    'class' => class_type,
                    'defaultValue' => value
                  }
                end
              end
            end
          end

          # Continue searching in children (collect all data, not just the first)
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_data_properties(child, properties, depth + 1, event_bindings)
              end
            else
              extract_data_properties(json_data['child'], properties, depth + 1, event_bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_data_properties(item, properties, depth, event_bindings)
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
          # Extract the actual data class name from the existing file
          existing_class_name = extract_class_name(existing_file)
          if existing_class_name
            # Use the exact class name from the existing file
            view_name = existing_class_name.sub(/Data$/, '')
          else
            # Fallback to pascal case if we can't extract the name
            view_name = pascal_view_name
          end
          data_file_path = existing_file
        else
          # For new files, use pascal case
          view_name = pascal_view_name
          data_file_path = File.join(@data_dir, "#{view_name}Data.kt")
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
        exact_path = File.join(@data_dir, "#{view_name}Data.kt")
        return exact_path if File.exist?(exact_path)
        
        # Try case-insensitive search
        Dir.glob(File.join(@data_dir, '*Data.kt')).find do |file|
          File.basename(file, '.kt').downcase == "#{view_name}Data".downcase
        end
      end
      
      def extract_class_name(file_path)
        content = File.read(file_path)
        if match = content.match(/data\s+class\s+(\w+Data)\s*\(/)
          match[1]
        else
          nil
        end
      end

      def generate_data_content(view_name, data_properties, onclick_actions = [], json_base_name: nil)
        marker_source = json_base_name ? "Layouts/#{json_base_name}.json" : "#{view_name}Data"
        marker_header = Core::GeneratedMarker.comment_header(
          source: marker_source,
          generator: "kjui build"
        )
        content = <<~KOTLIN
        #{marker_header}

        package #{@package_name}.data

        KOTLIN

        # Add Color import if any property uses Color type
        has_color = data_properties.any? { |prop| prop['class'] == 'Color' }
        if has_color
          content += "import androidx.compose.ui.graphics.Color\n"
        end

        # Add Painter import if any property uses Image/Painter type
        if data_properties.any? { |prop| prop['class'] == 'Image' || prop['class'] == 'Painter' }
          content += "import androidx.compose.ui.graphics.painter.Painter\n"
          # Check if any Image default value uses painterResource
          needs_painter_resource = data_properties.any? do |prop|
            (prop['class'] == 'Image' || prop['class'] == 'Painter') &&
              prop['defaultValue'].is_a?(String) &&
              prop['defaultValue'].include?('painterResource')
          end
          if needs_painter_resource
            content += "import androidx.compose.ui.res.painterResource\n"
          end
        end

        content += "\ndata class #{view_name}Data(\n"
        
        if data_properties.empty?
            content += "    // No data properties defined in JSON\n"
            content += "    val placeholder: String = \"placeholder\"\n"
        else
          # Add each property with correct type and default value
          data_properties.each_with_index do |prop, index|
            name = prop['name']
            class_type = map_to_kotlin_type(prop['class'])
            default_value = prop['defaultValue']

            # If no default value or nil, make it nullable
            if default_value.nil? || default_value == 'nil'
              # Don't add ? if type already ends with ? (already nullable)
              if class_type.end_with?('?')
                content += "    var #{name}: #{class_type} = null"
              else
                content += "    var #{name}: #{class_type}? = null"
              end
            else
              formatted_value = format_default_value(default_value, prop['class'])
              content += "    var #{name}: #{class_type} = #{formatted_value}"
            end
            
            # Add comma if not last property
            content += "," if index < data_properties.length - 1
            content += "\n"
          end
        end
        
        content += ") {\n"
        
        # Add companion object with update function
        content += "    companion object {\n"
        content += "        // Update properties from map\n"

        # Add @Suppress("UNCHECKED_CAST") if there are callback properties
        has_callback_properties = data_properties.any? { |prop|
          class_type = prop['class'].to_s
          class_type.include?('-> Unit') || class_type.include?('-> Void')
        }
        if has_callback_properties
          content += "        @Suppress(\"UNCHECKED_CAST\")\n"
        end

        content += "        fun fromMap(map: Map<String, Any>): #{view_name}Data {\n"
        content += "            return #{view_name}Data(\n"
        
        if !data_properties.empty?
          data_properties.each_with_index do |prop, index|
            name = prop['name']
            class_type = prop['class']
            kotlin_type = map_to_kotlin_type(class_type)
            
            # Generate conversion code based on type
            content += "                #{name} = "
            
            case class_type
            when 'String'
              content += "map[\"#{name}\"] as? String ?: \"\""
            when 'Int'
              content += "(map[\"#{name}\"] as? Number)?.toInt() ?: 0"
            when 'Double'
              content += "(map[\"#{name}\"] as? Number)?.toDouble() ?: 0.0"
            when 'Float'
              content += "(map[\"#{name}\"] as? Number)?.toFloat() ?: 0f"
            when 'Bool', 'Boolean'
              content += "map[\"#{name}\"] as? Boolean ?: false"
            when 'Color'
              content += "map[\"#{name}\"] as? Color ?: Color.Unspecified"
            when 'CollectionDataSource'
              content += "com.kotlinjsonui.data.CollectionDataSource()"
            when /^List<.*>$/
              content += "map[\"#{name}\"] as? #{kotlin_type} ?: emptyList()"
            when /^Map<.*>$/
              content += "map[\"#{name}\"] as? #{kotlin_type} ?: emptyMap()"
            else
              # For custom types, try to cast directly
              content += "map[\"#{name}\"] as? #{kotlin_type}"
            end
            
            content += "," if index < data_properties.length - 1
            content += "\n"
          end
        else
          content += "                placeholder = \"placeholder\"\n"
        end
        
        content += "            )\n"
        content += "        }\n"
        content += "    }\n"
        
        # Add toMap function
        content += "\n"
        content += "    // Convert properties to map for runtime use\n"
        content += "    fun toMap(): MutableMap<String, Any> {\n"
        content += "        val map = mutableMapOf<String, Any>()\n"

        # Add data properties
        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties\n"
          data_properties.each do |prop|
            name = prop['name']
            default_value = prop['defaultValue']

            # If it's nullable, check for null
            if default_value.nil? || default_value == 'nil'
              content += "        #{name}?.let { map[\"#{name}\"] = it }\n"
            else
              content += "        map[\"#{name}\"] = #{name}\n"
            end
          end
        end

        if data_properties.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return map\n"
        content += "    }\n"
        content += "}\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"
        content
      end

      def map_to_kotlin_type(json_class)
        case json_class
        when 'String'
          'String'
        when 'Int'
          'Int'
        when 'Double'
          'Double'
        when 'Float'
          'Float'
        when 'Bool', 'Boolean'
          'Boolean'
        when 'CGFloat'
          'Float'
        when 'Color'
          'Color'
        when 'Image', 'Painter'
          'Painter'
        when 'CollectionDataSource'
          # Use the actual CollectionDataSource type
          'com.kotlinjsonui.data.CollectionDataSource'
        when /^\(\) -> Unit$/
          # Non-optional callback becomes optional in data class
          '(() -> Unit)?'
        when /^\((.+)\) -> Unit$/
          # Callback with parameters becomes optional
          "((#{$1}) -> Unit)?"
        when /^\(\(\) -> Unit\)\?$/
          # Already optional, keep as is
          '(() -> Unit)?'
        when /^\(\((.+)\) -> Unit\)\?$/
          # Already optional with params, keep as is
          "((#{$1}) -> Unit)?"
        else
          # Return as-is for custom types
          json_class
        end
      end

      def format_default_value(value, json_class)
        case json_class
        when 'String'
          # Handle string default values (matching SwiftUI implementation)
          value_str = value.to_s
          if value_str == "''"
            # Handle '' as empty string (common shorthand)
            '""'
          elsif value_str.start_with?("'") && value_str.end_with?("'") && value_str.length > 1
            # Handle single-quoted strings like "'gone'" -> "gone"
            inner_content = value_str[1...-1]
            escaped_content = inner_content.gsub('\\', '\\\\').gsub('"', '\\"')
            "\"#{escaped_content}\""
          elsif !value_str.start_with?('"') || !value_str.end_with?('"')
            # Handle unquoted strings like "gone" -> "gone"
            escaped_content = value_str.gsub('\\', '\\\\').gsub('"', '\\"')
            "\"#{escaped_content}\""
          else
            # Already properly quoted
            value_str
          end
        when 'Bool', 'Boolean'
          # Convert to boolean
          if value.is_a?(TrueClass) || value.is_a?(FalseClass)
            value.to_s
          else
            value.to_s.downcase == 'true' ? 'true' : 'false'
          end
        when 'Int'
          # Ensure it's an integer
          value.to_i.to_s
        when 'Double'
          # Ensure it's a double
          "#{value.to_f}"
        when 'Float', 'CGFloat'
          # Ensure it's a float with f suffix
          "#{value.to_f}f"
        when 'Color'
          # Handle color values - type_converter already converts color names to Color(0xFFxxxxxx)
          if value.is_a?(String) && value.start_with?('Color(')
            value # Already converted Color() expression
          elsif value.is_a?(String) && value.start_with?('Color.')
            value # Direct Color reference like Color.Red
          elsif value.is_a?(String) && value.start_with?('#')
            # Hex color - convert to Color()
            hex = value.sub('#', '')
            if hex.length == 6
              "Color(0xFF#{hex.upcase})"
            elsif hex.length == 8
              "Color(0x#{hex.upcase})"
            else
              'Color.Unspecified'
            end
          else
            'Color.Unspecified'
          end
        when 'CollectionDataSource'
          # Return the actual default value string or create new instance
          if value.is_a?(String) && value == 'CollectionDataSource()'
            'com.kotlinjsonui.data.CollectionDataSource()'
          else
            'com.kotlinjsonui.data.CollectionDataSource()'
          end
        when /^List<.*>$/
          # Handle generic List types
          if value.is_a?(Array) && value.empty?
            'emptyList()'
          elsif value == '[]' || value == []
            'emptyList()'
          else
            'emptyList()'
          end
        when /^Map<.*>$/
          # Handle generic Map types
          if value.is_a?(Hash) && value.empty?
            'emptyMap()'
          elsif value == '{}' || value == {} || value == '{}'
            'emptyMap()'
          else
            'emptyMap()'
          end
        else
          # For all other cases, use value as-is
          value
        end
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