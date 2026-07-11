# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/type_converter'
require_relative '../core/generated_marker'
require_relative 'style_loader'

module RjuiTools
  module React
    class DataModelGenerator
      def initialize
        @config = Core::ConfigManager.load_config
        @source_path = @config['source_path'] || Dir.pwd
        @layouts_dir = File.join(@source_path, @config['layouts_directory'] || 'Layouts')
        @data_dir = File.join(@source_path, @config['data_directory'] || 'src/generated/data')
        @styles_dir = File.join(@source_path, @config['styles_directory'] || 'Styles')
        @use_typescript = @config['typescript'] != false
      end

      def update_data_models
        # Ensure data directory exists
        FileUtils.mkdir_p(@data_dir)

        # Generate CollectionDataSource if not exists
        generate_collection_data_source

        # Process all JSON files in Layouts directory
        json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
          # Skip Resources folder and Styles folder
          file.include?(File.join(@layouts_dir, 'Resources')) ||
            file.include?(File.join(@layouts_dir, 'Styles'))
        end

        ensure_unique_layout_basenames!(json_files)

        json_files.each do |json_file|
          process_json_file(json_file)
        end
      end

      # Data models are written as <Basename>Data.<ext> into a single flat
      # directory on EVERY platform (ts here, swift/kt on sjui/kjui — Swift
      # has no directory namespacing at all), so layout basenames must be
      # unique project-wide. A silent last-write-wins overwrite corrupts the
      # earlier screen's Data model (rjui-cell-data-model-name-collision-
      # across-screens), so duplicates abort the build.
      def ensure_unique_layout_basenames!(json_files)
        duplicates = json_files.group_by { |f| File.basename(f) }
                               .select { |_, files| files.size > 1 }
        return if duplicates.empty?

        details = duplicates.map do |base, files|
          rels = files.map { |f| f.sub(%r{\A#{Regexp.escape(@layouts_dir)}/?}, '') }.sort
          "  #{base}: #{rels.join(', ')}"
        end
        abort(
          "ERROR: duplicate layout file name(s) detected.\n" \
          "Data models are generated as <Name>Data files into a single directory/package " \
          "on every platform (TypeScript/Swift/Kotlin), so layout basenames must be unique " \
          "project-wide even across subdirectories — otherwise the last one processed " \
          "silently overwrites the others. Rename one file of each pair (and its references):\n" +
          details.join("\n")
        )
      end

      private

      def process_json_file(json_file)
        json_content = File.read(json_file, encoding: 'UTF-8')
        json_data = JSON.parse(json_content)

        # Expand styles before extracting data and actions
        expanded_data = StyleLoader.load_and_merge(json_data, @styles_dir)

        # Extract event bindings (handler name => component/attribute info) for Event type conversion
        event_bindings = extract_event_bindings_for_type(expanded_data)

        # Extract data properties from expanded JSON (pass event_bindings for Event type conversion)
        data_properties = extract_data_properties(expanded_data, [], true, event_bindings)

        # Extract onclick actions from expanded JSON
        onclick_actions = extract_onclick_actions(expanded_data)

        # Extract TextField bindings for onChange handlers
        text_field_bindings = extract_text_field_bindings(expanded_data)

        # Extract event handler bindings (Switch, SelectBox, etc.)
        event_handlers = extract_event_handler_bindings(expanded_data)

        # Extract value bindings (Switch, Slider, SelectBox, etc.)
        value_bindings = extract_value_bindings(expanded_data)

        # Get the view name from file path
        base_name = File.basename(json_file, '.json')

        # Update the Data model file
        update_data_file(base_name, data_properties, onclick_actions, text_field_bindings, event_handlers, value_bindings)
      end

      # Extract event bindings from JSON to map handler names to component/attribute
      # Used for converting Event type to platform-specific types
      # @param json_data [Hash] the JSON data
      # @param bindings [Hash] accumulated bindings (handler_name => { component:, attribute: })
      # @return [Hash] event bindings
      def extract_event_bindings_for_type(json_data, bindings = {})
        return bindings unless json_data.is_a?(Hash) || json_data.is_a?(Array)

        if json_data.is_a?(Hash)
          component_type = json_data['type']

          # Event attributes to check
          event_attrs = %w[onClick onclick onValueChange onValueChanged onTextChange onChange onLongPress]

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
          child = json_data['child'] || json_data['children']
          if child.is_a?(Array)
            child.each { |c| extract_event_bindings_for_type(c, bindings) }
          elsif child
            extract_event_bindings_for_type(child, bindings)
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_event_bindings_for_type(item, bindings) }
        end

        bindings
      end

      def extract_onclick_actions(json_data, actions = Set.new)
        if json_data.is_a?(Hash)
          # Check for onclick attribute (selector format)
          if json_data['onclick'] && json_data['onclick'].is_a?(String)
            actions.add(json_data['onclick'])
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each do |c|
                extract_onclick_actions(c, actions)
              end
            else
              extract_onclick_actions(child, actions)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_onclick_actions(item, actions)
          end
        end

        actions.to_a
      end

      # Extract TextField text bindings for auto-generating onChange handlers
      # e.g., TextField with text: "@{email}" -> "email"
      def extract_text_field_bindings(json_data, bindings = Set.new)
        if json_data.is_a?(Hash)
          # Check for TextField type with text binding
          if json_data['type'] == 'TextField' && json_data['text']
            text_value = json_data['text']
            # Check if it's a binding (@{propertyName})
            if text_value.is_a?(String) && text_value.start_with?('@{') && text_value.end_with?('}')
              # Skip if custom onChange is already defined
              unless json_data['onTextChange'] || json_data['onChange']
                property_name = text_value[2...-1]
                bindings.add(property_name)
              end
            end
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each do |c|
                extract_text_field_bindings(c, bindings)
              end
            else
              extract_text_field_bindings(child, bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_text_field_bindings(item, bindings)
          end
        end

        bindings.to_a
      end

      # Extract event handler bindings from components
      # Returns hash with handler name => { type: value_type, binding: property_name }
      def extract_event_handler_bindings(json_data, handlers = {})
        if json_data.is_a?(Hash)
          component_type = json_data['type']

          # Switch, Toggle, Slider, Radio, Segment - onValueChange with boolean/number/string
          if %w[Switch Toggle].include?(component_type)
            extract_handler_binding(json_data, 'onValueChange', 'boolean', handlers)
          elsif component_type == 'Slider'
            extract_handler_binding(json_data, 'onValueChange', 'number', handlers)
          elsif %w[Radio Segment].include?(component_type)
            extract_handler_binding(json_data, 'onValueChange', 'string', handlers)
          # SelectBox - onValueChanged or onChange with string
          elsif component_type == 'SelectBox'
            handler_key = json_data['onValueChanged'] ? 'onValueChanged' : 'onChange'
            extract_handler_binding(json_data, handler_key, 'string', handlers)
          # TextView - onTextChange or onChange with string
          elsif component_type == 'TextView'
            handler_key = json_data['onTextChange'] ? 'onTextChange' : 'onChange'
            extract_handler_binding(json_data, handler_key, 'string', handlers) if json_data[handler_key]
          end


          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_event_handler_bindings(c, handlers) }
            else
              extract_event_handler_bindings(child, handlers)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_event_handler_bindings(item, handlers) }
        end

        handlers
      end

      def extract_handler_binding(json_data, handler_key, value_type, handlers)
        handler = json_data[handler_key]
        return unless handler.is_a?(String) && handler.start_with?('@{') && handler.end_with?('}')

        handler_name = handler[2...-1]
        handlers[handler_name] = { type: value_type }
      end

      # Extract value bindings from components (Switch, Slider, SelectBox, TextField, TextView, etc.)
      # These are the bound values like @{notificationsEnabled} in Switch isOn attribute
      def extract_value_bindings(json_data, bindings = {})
        if json_data.is_a?(Hash)
          component_type = json_data['type']

          # Switch, Toggle - isOn/checked/value binding (boolean)
          if %w[Switch Toggle].include?(component_type)
            is_on = json_data['isOn'] || json_data['checked'] || json_data['value']
            if is_on.is_a?(String) && is_on.start_with?('@{') && is_on.end_with?('}')
              property_name = is_on[2...-1]
              bindings[property_name] = { type: 'boolean', defaultValue: false }
            end
          end

          # CheckBox, Check - isOn/checked binding (boolean)
          if %w[CheckBox Check].include?(component_type)
            is_on = json_data['isOn'] || json_data['checked']
            if is_on.is_a?(String) && is_on.start_with?('@{') && is_on.end_with?('}')
              property_name = is_on[2...-1]
              bindings[property_name] = { type: 'boolean', defaultValue: false }
            end
          end

          # Slider - value binding (number)
          if component_type == 'Slider'
            value = json_data['value']
            if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
              property_name = value[2...-1]
              bindings[property_name] = { type: 'number', defaultValue: 0 }
            end
          end

          # Radio, Segment, SelectBox - value binding (string)
          if %w[Radio Segment SelectBox].include?(component_type)
            value = json_data['value']
            if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
              property_name = value[2...-1]
              bindings[property_name] = { type: 'string', defaultValue: '""' }
            end
          end

          # Focus-state binding (cross-platform parity with sjui/kjui
          # data.<id>IsFocused): every editable field with a literal id gets a
          # boolean prop the ViewModel can set to drive focus (the generated
          # component hoists a ref + effect). The paired optional
          # on<Camel>IsFocusedChange report-back handler is derived from this
          # binding by the value-binding handler loop in update_data_file.
          if %w[TextField EditText Input TextView].include?(component_type)
            field_id = json_data['id']
            if field_id.is_a?(String) && !field_id.empty? && !field_id.include?('@{')
              camel = snake_to_camel_id(field_id)
              bindings["#{camel}IsFocused"] ||= { type: 'boolean', defaultValue: false }
            end
          end

          # TextField - text binding (string)
          if component_type == 'TextField'
            text = json_data['text']
            if text.is_a?(String) && text.start_with?('@{') && text.end_with?('}')
              property_name = text[2...-1]
              bindings[property_name] = { type: 'string', defaultValue: '""' }
            end
          end

          # TextView - text binding (string)
          if component_type == 'TextView'
            text = json_data['text']
            if text.is_a?(String) && text.start_with?('@{') && text.end_with?('}')
              property_name = text[2...-1]
              bindings[property_name] = { type: 'string', defaultValue: '""' }
            end
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each { |c| extract_value_bindings(c, bindings) }
            else
              extract_value_bindings(child, bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each { |item| extract_value_bindings(item, bindings) }
        end

        bindings
      end

      def extract_data_properties(json_data, properties = [], is_root = true, event_bindings = {})
        if json_data.is_a?(Hash)
          # Check for data section
          if json_data['data'] && json_data['data'].is_a?(Array)
            # Extract from root element OR data-only elements (no type, just data key)
            should_extract = is_root || json_data.keys == ['data'] || (json_data.keys - ['data', 'type']).empty?
            if should_extract
              json_data['data'].each do |data_item|
                if data_item.is_a?(Hash)
                  # Normalize type using TypeConverter (mode: react)
                  normalized = Core::TypeConverter.normalize_data_property(data_item, 'react')

                  # Check if this property is bound to an event and has Event type
                  prop_name = normalized['name']
                  prop_class = normalized['class'].to_s

                  if event_bindings[prop_name] && prop_class.include?('Event')
                    # Get event type from type_mapping.json
                    binding_info = event_bindings[prop_name]
                    event_type = Core::TypeConverter.get_event_type(
                      binding_info[:component],
                      binding_info[:attribute]
                    )

                    if event_type
                      # Convert Event to platform-specific type (React event type string)
                      converted_class = prop_class.gsub('Event', event_type)
                      normalized['class'] = converted_class
                      # Recalculate tsType with the converted class
                      normalized['tsType'] = Core::TypeConverter.to_typescript_type(converted_class)
                    end
                  end

                  properties << normalized
                end
              end
            end
          end

          # Check for TabView tabs - generate data properties for each tab's view
          if json_data['type'] == 'TabView' && json_data['tabs'].is_a?(Array)
            # Add setSelectedTabIndex function for tab switching
            properties << {
              'name' => 'setSelectedTabIndex',
              'class' => 'Function',
              'tsType' => '(index: number) => void',
              'defaultValue' => nil
            }

            json_data['tabs'].each do |tab|
              if tab['view']
                # Convert view name to camelCase + Data (e.g., home -> homeData, item_card -> itemCardData)
                view_name = tab['view']
                data_prop_name = view_name.split('_').each_with_index.map { |part, i| i == 0 ? part.downcase : part.capitalize }.join + 'Data'
                pascal_name = view_name.split('_').map(&:capitalize).join
                properties << {
                  'name' => data_prop_name,
                  'class' => 'Object',
                  'tsType' => "#{pascal_name}Data",
                  'defaultValue' => nil
                }
              end
            end
          end

          # Process children
          child = json_data['child'] || json_data['children']
          if child
            if child.is_a?(Array)
              child.each do |c|
                extract_data_properties(c, properties, false, event_bindings)
              end
            else
              extract_data_properties(child, properties, false, event_bindings)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_data_properties(item, properties, false, event_bindings)
          end
        end

        properties
      end

      def update_data_file(base_name, data_properties, onclick_actions = [], text_field_bindings = [], event_handlers = {}, value_bindings = {})
        # Convert base_name to PascalCase
        view_name = to_pascal_case(base_name)

        # Determine file extension
        extension = @use_typescript ? '.ts' : '.js'
        data_file_path = File.join(@data_dir, "#{view_name}Data#{extension}")

        # Create directory if needed
        FileUtils.mkdir_p(@data_dir)

        # Generate new content
        content = generate_data_content(view_name, data_properties, onclick_actions, text_field_bindings, event_handlers, value_bindings)

        # Write the updated content
        File.write(data_file_path, content)
        puts "  Updated Data model: #{data_file_path}"
      end

      def generate_data_content(view_name, data_properties, onclick_actions = [], text_field_bindings = [], event_handlers = {}, value_bindings = {})
        if @use_typescript
          generate_typescript_content(view_name, data_properties, onclick_actions, text_field_bindings, event_handlers, value_bindings)
        else
          generate_javascript_content(view_name, data_properties, onclick_actions, text_field_bindings, event_handlers, value_bindings)
        end
      end

      def generate_typescript_content(view_name, data_properties, onclick_actions = [], text_field_bindings = [], event_handlers = {}, value_bindings = {})
        # Check if we need to import CollectionDataSource
        needs_collection_import = data_properties.any? { |p| p['tsType']&.include?('CollectionDataSource') || p['class'] == 'CollectionDataSource' }

        # Check for other Data type imports (e.g., HomeData, SearchData).
        # tsType may be a bare identifier (FooData), an array (FooData[]),
        # a union (FooData | undefined), or an array of union etc. — scan
        # out every FooData token rather than relying on an exact match.
        data_type_imports = data_properties
          .map { |p| p['tsType'] }
          .compact
          .flat_map { |t| t.scan(/\b([A-Z][a-zA-Z0-9]*Data)\b/).flatten }
          .uniq
          .reject { |t| t == "#{view_name}Data" }

        # Get existing property names from data section to avoid duplicates
        existing_prop_names = data_properties.map { |p| p['name'] }.to_set

        marker_header = Core::GeneratedMarker.comment_header(
          source: "#{view_name}Data",
          generator: "rjui build"
        )
        imports = "#{marker_header}\n\n"
        imports += "import { CollectionDataSource } from './CollectionDataSource';\n" if needs_collection_import
        data_type_imports.each do |data_type|
          imports += "import type { #{data_type} } from './#{data_type}';\n"
        end
        imports += "\n"

        content = <<~TS
          #{imports}export interface #{view_name}Data {
        TS

        if data_properties.empty? && onclick_actions.empty? && text_field_bindings.empty? && event_handlers.empty? && value_bindings.empty?
          content += "  // No data properties defined in JSON\n"
        else
          # Add each property with correct type
          data_properties.each do |prop|
            name = prop['name']
            ts_type = prop['tsType'] || Core::TypeConverter.to_typescript_type(prop['class'])
            default_value = prop['defaultValue']

            # Properties are optional by default
            if default_value.nil?
              content += "  #{name}?: #{ts_type};\n"
            else
              content += "  #{name}: #{ts_type};\n"
            end
          end

          # Add value bindings (Switch, Slider, SelectBox values) - skip if already in data_properties
          value_bindings.each do |prop_name, info|
            next if existing_prop_names.include?(prop_name)

            ts_type = info[:type]
            content += "  #{prop_name}: #{ts_type};\n"
          end

          # Add onclick actions as function properties
          onclick_actions.each do |action|
            content += "  #{action}?: () => void;\n"
          end

          # Add onChange handlers for TextField bindings
          text_field_bindings.each do |binding|
            handler_name = "on#{capitalize_first(binding)}Change"
            content += "  #{handler_name}?: (value: string) => void;\n"
          end

          # Add onChange handlers for value bindings (auto-generated handlers)
          # Skip if already handled by text_field_bindings
          text_field_set = text_field_bindings.to_set
          value_bindings.each do |prop_name, info|
            next if text_field_set.include?(prop_name)
            handler_name = "on#{capitalize_first(prop_name)}Change"
            next if existing_prop_names.include?(handler_name)
            ts_type = info[:type]
            content += "  #{handler_name}?: (value: #{ts_type}) => void;\n"
          end

          # Add event handlers (Switch, SelectBox, etc.) - skip if already in data_properties
          event_handlers.each do |handler_name, info|
            next if existing_prop_names.include?(handler_name)

            ts_type = info[:type]
            content += "  #{handler_name}?: (value: #{ts_type}) => void;\n"
          end
        end

        content += "}\n\n"

        # Generate default data object
        content += "export const create#{view_name}Data = (): #{view_name}Data => ({\n"

        data_properties.each do |prop|
          name = prop['name']
          ts_type = prop['tsType'] || Core::TypeConverter.to_typescript_type(prop['class'])
          default_value = prop['defaultValue']

          formatted_value = format_default_value(default_value, ts_type, prop['class'])
          content += "  #{name}: #{formatted_value},\n"
        end

        # Add value bindings with default values - skip if already in data_properties
        value_bindings.each do |prop_name, info|
          next if existing_prop_names.include?(prop_name)

          default_val = info[:defaultValue]
          content += "  #{prop_name}: #{default_val},\n"
        end

        onclick_actions.each do |action|
          content += "  #{action}: undefined,\n"
        end

        # Add onChange handlers with undefined default
        text_field_bindings.each do |binding|
          handler_name = "on#{capitalize_first(binding)}Change"
          content += "  #{handler_name}: undefined,\n"
        end

        # Add onChange handlers for value bindings with undefined default
        # Skip if already handled by text_field_bindings
        value_bindings.each do |prop_name, _info|
          next if text_field_set.include?(prop_name)
          handler_name = "on#{capitalize_first(prop_name)}Change"
          next if existing_prop_names.include?(handler_name)
          content += "  #{handler_name}: undefined,\n"
        end

        # Add event handlers with undefined default - skip if already in data_properties
        event_handlers.each do |handler_name, _info|
          next if existing_prop_names.include?(handler_name)

          content += "  #{handler_name}: undefined,\n"
        end

        content += "});\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"

        content
      end

      # snake_case id -> lowerCamel stem (sync: BaseConverter#snake_to_camel_id)
      def snake_to_camel_id(str)
        parts = str.split('_')
        parts[0] + parts[1..].map(&:capitalize).join
      end

      def capitalize_first(str)
        return str if str.nil? || str.empty?
        str[0].upcase + str[1..]
      end

      def generate_javascript_content(view_name, data_properties, onclick_actions = [], text_field_bindings = [], event_handlers = {}, value_bindings = {})
        # Get existing property names from data section to avoid duplicates
        existing_prop_names = data_properties.map { |p| p['name'] }.to_set
        marker_header = Core::GeneratedMarker.comment_header(
          source: "#{view_name}Data",
          generator: "rjui build"
        )
        content = <<~JS
          #{marker_header}

          /**
           * @typedef {Object} #{view_name}Data
        JS

        data_properties.each do |prop|
          name = prop['name']
          ts_type = prop['tsType'] || Core::TypeConverter.to_typescript_type(prop['class'])
          content += " * @property {#{ts_type}} [#{name}]\n"
        end

        # Add value bindings (Switch, Slider, SelectBox values) - skip if already in data_properties
        value_bindings.each do |prop_name, info|
          next if existing_prop_names.include?(prop_name)

          ts_type = info[:type]
          content += " * @property {#{ts_type}} #{prop_name}\n"
        end

        onclick_actions.each do |action|
          content += " * @property {(() => void) | undefined} [#{action}]\n"
        end

        # Add onChange handlers for TextField bindings
        text_field_bindings.each do |binding|
          handler_name = "on#{capitalize_first(binding)}Change"
          content += " * @property {((value: string) => void) | undefined} [#{handler_name}]\n"
        end

        # Add onChange handlers for value bindings (auto-generated handlers)
        # Skip if already handled by text_field_bindings
        text_field_set = text_field_bindings.to_set
        value_bindings.each do |prop_name, info|
          next if text_field_set.include?(prop_name)

          handler_name = "on#{capitalize_first(prop_name)}Change"
          ts_type = info[:type]
          content += " * @property {((value: #{ts_type}) => void) | undefined} [#{handler_name}]\n"
        end

        # Add event handlers (Switch, SelectBox, etc.)
        event_handlers.each do |handler_name, info|
          ts_type = info[:type]
          content += " * @property {((value: #{ts_type}) => void) | undefined} [#{handler_name}]\n"
        end

        content += " */\n\n"

        # Generate default data object
        content += "export const create#{view_name}Data = () => ({\n"

        data_properties.each do |prop|
          name = prop['name']
          ts_type = prop['tsType'] || Core::TypeConverter.to_typescript_type(prop['class'])
          default_value = prop['defaultValue']

          formatted_value = format_default_value(default_value, ts_type, prop['class'])
          content += "  #{name}: #{formatted_value},\n"
        end

        # Add value bindings with default values - skip if already in data_properties
        value_bindings.each do |prop_name, info|
          next if existing_prop_names.include?(prop_name)

          default_val = info[:defaultValue]
          content += "  #{prop_name}: #{default_val},\n"
        end

        onclick_actions.each do |action|
          content += "  #{action}: undefined,\n"
        end

        # Add onChange handlers with undefined default
        text_field_bindings.each do |binding|
          handler_name = "on#{capitalize_first(binding)}Change"
          content += "  #{handler_name}: undefined,\n"
        end

        # Add onChange handlers for value bindings with undefined default
        # Skip if already handled by text_field_bindings
        value_bindings.each do |prop_name, _info|
          next if text_field_set.include?(prop_name)

          handler_name = "on#{capitalize_first(prop_name)}Change"
          content += "  #{handler_name}: undefined,\n"
        end

        # Add event handlers with undefined default - skip if already in data_properties
        event_handlers.each do |handler_name, _info|
          next if existing_prop_names.include?(handler_name)

          content += "  #{handler_name}: undefined,\n"
        end

        content += "});\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"

        content
      end

      def format_default_value(value, ts_type, json_class = nil)
        return 'undefined' if value.nil?

        case ts_type
        when 'string'
          # Handle '' as empty string (common shorthand)
          if value == "''"
            '""'
          elsif value.is_a?(String) && (value.start_with?('"') || value.start_with?("'"))
            # Already quoted (e.g., from TypeConverter for Color/Image types)
            value
          else
            value.is_a?(String) ? "\"#{value}\"" : "\"#{value}\""
          end
        when 'number'
          value.to_s
        when 'boolean'
          value.to_s.downcase
        else
          # For arrays and objects
          if value.is_a?(Array)
            '[]'
          elsif value.is_a?(Hash)
            '{}'
          elsif value.is_a?(String) && value =~ /^CollectionDataSource\(/
            "new #{value}"
          else
            value.to_s
          end
        end
      end

      def to_pascal_case(str)
        # Handle various naming patterns
        snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                   .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                   .downcase
        snake.split(/[_\-]/).map(&:capitalize).join
      end

      def generate_collection_data_source
        extension = @use_typescript ? '.ts' : '.js'
        file_path = File.join(@data_dir, "CollectionDataSource#{extension}")

        # Always regenerate — the body is static boilerplate and the
        # @generated marker has to stay fresh even if the file pre-existed
        # from an older tool version.
        content = if @use_typescript
                    generate_collection_data_source_typescript
                  else
                    generate_collection_data_source_javascript
                  end

        File.write(file_path, content)
        puts "  Generated: #{file_path}"
      end

      def generate_collection_data_source_typescript
        marker_header = Core::GeneratedMarker.comment_header(
          source: "CollectionDataSource",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer
        <<~TS
          #{marker_header}

          /**
           * Section data for collection views.
           *
           * Defaults T to `unknown` rather than `Record<string, unknown>` so that
           * user-defined closed shapes (from .jsonui-type-map.json) can be
           * supplied directly without TS2345 — `Record<string, unknown>`
           * would require an index signature the user type doesn't carry.
           */
          export interface CollectionDataSection<T = unknown> {
            /** Header data */
            header?: Record<string, unknown>;
            /** Cell data array */
            cells?: {
              data: T[];
            };
            /** Footer data */
            footer?: Record<string, unknown>;
          }

          /**
           * Collection data source configuration
           */
          export class CollectionDataSource<T = unknown> {
            sections: CollectionDataSection<T>[];

            constructor(sections: CollectionDataSection<T>[] = []) {
              this.sections = sections;
            }

            /** Add a new section */
            addSection(section: CollectionDataSection<T>): void {
              this.sections.push(section);
            }

            /** Create and add a new empty section */
            createSection(): CollectionDataSection<T> {
              const section: CollectionDataSection<T> = {};
              this.sections.push(section);
              return section;
            }

            /** Set cells for a section */
            setCells(sectionIndex: number, data: T[]): void {
              if (this.sections[sectionIndex]) {
                this.sections[sectionIndex].cells = { data };
              }
            }

            /** Get all cell data from all sections */
            getAllCells(): T[] {
              return this.sections.flatMap(section => section.cells?.data || []);
            }
          }

          /** Create a new CollectionDataSource instance */
          export const createCollectionDataSource = <T = unknown>(
            sections: CollectionDataSection<T>[] = []
          ): CollectionDataSource<T> => {
            return new CollectionDataSource<T>(sections);
          };

          #{marker_footer}
        TS
      end

      def generate_collection_data_source_javascript
        marker_header = Core::GeneratedMarker.comment_header(
          source: "CollectionDataSource",
          generator: "rjui build"
        )
        marker_footer = Core::GeneratedMarker.comment_footer
        <<~JS
          #{marker_header}

          /**
           * @typedef {Object} CollectionDataSection
           * @property {Object} [header] - Header data
           * @property {{ data: Array }} [cells] - Cell data array
           * @property {Object} [footer] - Footer data
           */

          /**
           * Collection data source configuration
           */
          export class CollectionDataSource {
            /**
             * @param {CollectionDataSection[]} sections
             */
            constructor(sections = []) {
              this.sections = sections;
            }

            /**
             * Add a new section
             * @param {CollectionDataSection} section
             */
            addSection(section) {
              this.sections.push(section);
            }

            /**
             * Create and add a new empty section
             * @returns {CollectionDataSection}
             */
            createSection() {
              const section = {};
              this.sections.push(section);
              return section;
            }

            /**
             * Set cells for a section
             * @param {number} sectionIndex
             * @param {Array} data
             */
            setCells(sectionIndex, data) {
              if (this.sections[sectionIndex]) {
                this.sections[sectionIndex].cells = { data };
              }
            }

            /**
             * Get all cell data from all sections
             * @returns {Array}
             */
            getAllCells() {
              return this.sections.flatMap(section => section.cells?.data || []);
            }
          }

          /**
           * Create a new CollectionDataSource instance
           * @param {CollectionDataSection[]} sections
           * @returns {CollectionDataSource}
           */
          export const createCollectionDataSource = (sections = []) => {
            return new CollectionDataSource(sections);
          };

          #{marker_footer}
        JS
      end
    end
  end
end
