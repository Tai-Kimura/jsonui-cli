# frozen_string_literal: true

require 'json'
require_relative 'config_manager'

module RjuiTools
  module Core
    # Converts JSON primitive types to TypeScript types
    # This ensures cross-platform compatibility with SwiftJsonUI and KotlinJsonUI
    class TypeConverter
      # Cache for colors.json data
      @colors_data = nil
      @colors_file_path = nil

      # Cache for type_mapping.json data
      @type_mapping = nil

      class << self
        attr_accessor :colors_data, :colors_file_path, :type_mapping

        # Load type_mapping.json
        # @return [Hash] the type mapping data
        def load_type_mapping
          return @type_mapping if @type_mapping

          mapping_path = File.join(File.dirname(__FILE__), 'type_mapping.json')
          if File.exist?(mapping_path)
            begin
              @type_mapping = JSON.parse(File.read(mapping_path))
            rescue JSON::ParserError => e
              warn "[TypeConverter] Warning: Failed to parse type_mapping.json: #{e.message}"
              @type_mapping = { 'types' => {}, 'events' => {}, 'defaults' => {} }
            end
          else
            warn "[TypeConverter] Warning: type_mapping.json not found at #{mapping_path}"
            @type_mapping = { 'types' => {}, 'events' => {}, 'defaults' => {} }
          end

          @type_mapping
        end

        # Get type mapping for a JSON type
        # @param json_type [String] the JSON type
        # @param mode [String] the mode (not used for React, kept for API compatibility)
        # @return [String, nil] the mapped type or nil
        def get_type_mapping(json_type, mode = nil)
          mapping = load_type_mapping
          type_info = mapping.dig('types', json_type, LANGUAGE)
          return nil unless type_info

          # React doesn't have modes, so just return the value directly
          type_info.is_a?(Hash) ? type_info.values.first : type_info
        end

        # Get event type mapping for a component and attribute
        # @param component [String] the component type (e.g., "Button")
        # @param attribute [String] the attribute name (e.g., "onClick")
        # @param mode [String] the mode (not used for React)
        # @return [String, nil] the event type or nil
        def get_event_type(component, attribute, mode = nil)
          mapping = load_type_mapping
          mapping.dig('events', component, attribute, LANGUAGE)
        end

        # Get default value for a type
        # @param ts_type [String] the TypeScript type
        # @return [String] the default value
        def get_default_value(ts_type)
          mapping = load_type_mapping
          mapping.dig('defaults', LANGUAGE, ts_type) || 'undefined'
        end

        # Clear the type mapping cache (useful for testing)
        def clear_type_mapping_cache
          @type_mapping = nil
        end

        # Load colors.json from the specified path or auto-detect from project config
        # @param path [String, nil] optional path to colors.json
        # @return [Hash] the colors data
        def load_colors_json(path = nil)
          return @colors_data if @colors_data && (@colors_file_path == path || path.nil?)

          if path
            @colors_file_path = path
          else
            # Use ConfigManager to get correct path
            config = ConfigManager.load_config
            layouts_dir = config['layouts_directory'] || 'src/Layouts'
            resources_path = File.join(Dir.pwd, layouts_dir, 'Resources', 'colors.json')
            @colors_file_path = resources_path
          end

          if @colors_file_path && File.exist?(@colors_file_path)
            begin
              raw = JSON.parse(File.read(@colors_file_path))
              @colors_data = flatten_colors_for_lookup(raw)
            rescue JSON::ParserError => e
              warn "[TypeConverter] Warning: Failed to parse colors.json: #{e.message}"
              @colors_data = {}
            end
          else
            @colors_data = {}
          end

          @colors_data
        end

        # Reduce colors.json (flat or themed schema) to a flat name=>hex lookup.
        # Themed schema picks the palette pointed to by `fallback_mode`, falling
        # back to `modes.first`, then `'light'`, then the first content key.
        # Why: type_converter only validates color name existence, so a flat
        # lookup is the right shape regardless of underlying schema.
        def flatten_colors_for_lookup(raw)
          return {} unless raw.is_a?(Hash) && !raw.empty?

          meta_keys = %w[fallback_mode systemModeMapping modes]
          content_keys = raw.keys - meta_keys
          return {} if content_keys.empty?

          first_value = raw[content_keys.first]
          if first_value.is_a?(Hash)
            fallback = raw['fallback_mode'] if raw['fallback_mode'].is_a?(String)
            fallback ||= raw['modes'].first if raw['modes'].is_a?(Array) && raw['modes'].first.is_a?(String)
            fallback = nil unless fallback.is_a?(String) && raw[fallback].is_a?(Hash)
            fallback ||= 'light' if raw['light'].is_a?(Hash)
            fallback ||= content_keys.first
            palette = raw[fallback]
            palette.is_a?(Hash) ? palette.reject { |_, v| !(v.is_a?(String) || v.nil?) } : {}
          else
            raw.reject { |k, _| meta_keys.include?(k) }
          end
        end

        # Check if a color name exists in colors.json
        # @param color_name [String] the color name to check
        # @return [Boolean] true if the color exists
        def color_exists?(color_name)
          load_colors_json
          @colors_data.key?(color_name)
        end

        # Clear the cached colors data (useful for testing)
        def clear_colors_cache
          @colors_data = nil
          @colors_file_path = nil
        end
      end

      # Language key for this platform
      LANGUAGE = 'typescript'

      # Available modes for this platform
      MODES = %w[react].freeze

      # JSON type -> TypeScript type mapping
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      TYPE_MAPPING = {
        # Standard types (cross-platform)
        'String' => 'string',
        'string' => 'string',
        'Int' => 'number',
        'int' => 'number',
        'Integer' => 'number',
        'integer' => 'number',
        'Double' => 'number',
        'double' => 'number',
        'Float' => 'number',
        'float' => 'number',
        'Number' => 'number',
        'number' => 'number',
        'Bool' => 'boolean',
        'bool' => 'boolean',
        'Boolean' => 'boolean',
        'boolean' => 'boolean',
        # iOS-specific types mapped to TypeScript equivalents
        'CGFloat' => 'number',
        # Array types
        'Array' => 'any[]',
        'array' => 'any[]',
        # Object types
        'Object' => 'Record<string, any>',
        'object' => 'Record<string, any>',
        'Hash' => 'Record<string, any>',
        'hash' => 'Record<string, any>',
        # Void/Unit types (Swift -> Kotlin -> TypeScript)
        'Void' => 'void',
        'void' => 'void',
        'Unit' => 'void',
        'unit' => 'void',
        # Color/Image types
        'Color' => 'string',
        'color' => 'string',
        'Image' => 'string',
        'image' => 'string'
      }.freeze

      # Default values for each TypeScript type
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      DEFAULT_VALUES = {
        'string' => '""',
        'number' => '0',
        'boolean' => 'false',
        'any[]' => '[]',
        'Record<string, any>' => '{}'
      }.freeze

      class << self
        # Extract platform-specific value from a potentially nested hash
        # Supports three formats:
        # 1. Simple value: "String" -> "String"
        # 2. Language only: { "swift": "Int", "react": "number" } -> "number"
        # 3. Language + mode: { "react": { "react": "string" } } -> "string"
        #
        # @param value [Object] the value (String, Hash, or other)
        # @param mode [String] the mode (react)
        # @return [Object] the extracted value for this platform/mode
        def extract_platform_value(value, mode = nil)
          return value unless value.is_a?(Hash)

          # Try to get language-specific value
          lang_value = value[LANGUAGE]
          return value unless lang_value # No language key found, return original hash

          # If language value is a hash, try to get mode-specific value
          if lang_value.is_a?(Hash) && mode
            mode_value = lang_value[mode]
            return mode_value if mode_value

            # Fallback: try first available mode
            MODES.each do |m|
              return lang_value[m] if lang_value[m]
            end

            # No mode found, return the hash as-is (might be a custom structure)
            lang_value
          else
            # Language value is not a hash, return it directly
            lang_value
          end
        end

        # Convert JSON type to TypeScript type
        # @param json_type [String] the type specified in JSON
        # @return [String] the corresponding TypeScript type
        def to_typescript_type(json_type)
          return 'any' if json_type.nil? || json_type.to_s.empty?

          type_str = json_type.to_s.strip

          # Check for optional type suffix
          is_optional = type_str.end_with?('?')
          base_type = is_optional ? type_str[0...-1] : type_str

          # Check for Array(ElementType) syntax -> ElementType[]
          if (match = base_type.match(/^Array\((.+)\)$/))
            element_type = to_typescript_type(match[1].strip)
            result = "#{element_type}[]"
            return is_optional ? "#{result} | undefined" : result
          end

          # Check for Dictionary(KeyType,ValueType) syntax -> Record<KeyType, ValueType>
          if (match = base_type.match(/^Dictionary\((.+),\s*(.+)\)$/))
            key_type = to_typescript_type(match[1].strip)
            value_type = to_typescript_type(match[2].strip)
            result = "Record<#{key_type}, #{value_type}>"
            return is_optional ? "#{result} | undefined" : result
          end

          # Check for function type: (params) -> ReturnType or ((params) -> ReturnType)?
          func_result = parse_function_type(type_str)
          return func_result if func_result

          # Return mapped type, or original type as-is if not found
          result = TYPE_MAPPING[base_type] || base_type
          is_optional ? "#{result} | undefined" : result
        end

        # Parse a function type string and convert to TypeScript
        # Handles: (Int) -> Void, ((Image) -> Color), (() -> Unit)?, etc.
        # All function types are converted to optional by default (for callbacks)
        # @param type_str [String] the type string to parse
        # @return [String, nil] the TypeScript function type or nil if not a function type
        def parse_function_type(type_str)
          working_str = type_str.strip

          # Check for optional wrapper: ((...) -> ...)? or (() -> ...)?
          if working_str.end_with?(')?')
            if working_str.start_with?('(')
              inner = extract_balanced_content(working_str[1...-2], '(', ')')
              if inner && inner == working_str[1...-2]
                working_str = working_str[1...-2]
              end
            end
          # Check for grouping parentheses: ((params) -> ReturnType) without ?
          elsif working_str.start_with?('(') && working_str.end_with?(')')
            inner = working_str[1...-1]
            if find_arrow_position(inner)
              working_str = inner
            end
          end

          # Now try to parse as function: (params) -> ReturnType
          arrow_pos = find_arrow_position(working_str)
          return nil unless arrow_pos

          params_part = working_str[0...arrow_pos].strip
          return_part = working_str[(arrow_pos + 2)..].strip

          # params_part should be (...)
          return nil unless params_part.start_with?('(') && params_part.end_with?(')')

          params_inner = params_part[1...-1].strip

          # Parse parameters (handling nested types)
          converted_params = parse_parameter_list(params_inner)

          # Convert return type (Void/Unit -> void)
          converted_return = convert_single_type(return_part)

          # Build result - all function types become optional (for callbacks)
          "((#{converted_params}) => #{converted_return}) | undefined"
        end

        # Convert a single type without making it optional
        def convert_single_type(type_str)
          return type_str if type_str.nil? || type_str.to_s.empty?

          str = type_str.to_s.strip
          is_optional = str.end_with?('?')
          base = is_optional ? str[0...-1] : str

          result = TYPE_MAPPING[base] || base
          is_optional ? "#{result} | undefined" : result
        end

        # Parse parameter list and convert types
        def parse_parameter_list(params_str)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.each_with_index.map do |p, i|
            converted = convert_single_type(p.strip)
            "arg#{i}: #{converted}"
          end.join(', ')
        end

        # Find the position of the arrow (->) that separates params from return type
        def find_arrow_position(str)
          depth = 0
          i = 0
          while i < str.length
            char = str[i]
            if char == '('
              depth += 1
            elsif char == ')'
              depth -= 1
            elsif char == '-' && str[i + 1] == '>' && depth == 0
              return i
            end
            i += 1
          end
          nil
        end

        # Split parameters by comma, respecting nested parentheses and generics
        def split_parameters(str)
          return [] if str.nil? || str.empty?

          params = []
          current = ''
          depth = 0

          str.each_char do |char|
            if char == '(' || char == '<' || char == '['
              depth += 1
              current += char
            elsif char == ')' || char == '>' || char == ']'
              depth -= 1
              current += char
            elsif char == ',' && depth == 0
              params << current.strip unless current.strip.empty?
              current = ''
            else
              current += char
            end
          end

          params << current.strip unless current.strip.empty?
          params
        end

        # Extract balanced content
        def extract_balanced_content(str, open_char, close_char)
          depth = 0
          str.each_char do |char|
            depth += 1 if char == open_char
            depth -= 1 if char == close_char
            return nil if depth < 0
          end
          depth == 0 ? str : nil
        end

        # Check if the type is a primitive type
        # @param json_type [String] the type to check
        # @return [Boolean] true if it's a primitive type
        def primitive?(json_type)
          return false if json_type.nil? || json_type.to_s.empty?

          TYPE_MAPPING.key?(json_type.to_s)
        end

        # Get default value for a TypeScript type
        # @param ts_type [String] the TypeScript type
        # @return [String] the default value as TypeScript code
        def default_value(ts_type)
          DEFAULT_VALUES[ts_type] || 'undefined'
        end

        # Format a value for TypeScript code based on type
        # @param value [Object] the value to format
        # @param ts_type [String] the TypeScript type
        # @return [String] the formatted value as TypeScript code
        def format_value(value, ts_type)
          return 'undefined' if value.nil?

          case ts_type
          when 'string'
            format_string_value(value)
          when 'number'
            value.to_f.to_s
          when 'boolean'
            value.to_s.downcase
          when 'any[]'
            value.is_a?(Array) ? value.to_json : '[]'
          when 'Record<string, any>'
            value.is_a?(Hash) ? value.to_json : '{}'
          else
            value.to_s
          end
        end

        # Convert data property from JSON format to normalized format
        # @param data_prop [Hash] the data property from JSON
        # @param mode [String] the mode (react)
        # @return [Hash] normalized data property with TypeScript type
        def normalize_data_property(data_prop, mode = nil)
          return data_prop unless data_prop.is_a?(Hash)

          normalized = data_prop.dup

          # Extract platform-specific class
          raw_class = nil
          if normalized['class']
            raw_class = extract_platform_value(normalized['class'], mode)
            normalized['tsType'] = to_typescript_type(raw_class)
          end

          # Extract platform-specific defaultValue and convert for special types
          if normalized['defaultValue']
            raw_value = extract_platform_value(normalized['defaultValue'], mode)
            normalized['defaultValue'] = convert_default_value(raw_value, raw_class, mode)
          end

          normalized
        end

        # Convert defaultValue based on the type
        # For Color: convert hex/color name to CSS format
        # For Image: convert image name to path string
        # @param value [Object] the raw default value
        # @param raw_class [String] the original class type from JSON
        # @param mode [String] the mode (react)
        # @return [Object] the converted default value
        def convert_default_value(value, raw_class, mode = nil)
          return value unless value.is_a?(String) && raw_class.is_a?(String)

          base_class = raw_class.end_with?('?') ? raw_class[0...-1] : raw_class

          case base_class.downcase
          when 'color'
            convert_color_default_value(value)
          when 'image'
            convert_image_default_value(value)
          else
            value
          end
        end

        # Convert color value (hex or color name) to CSS color string
        # @param value [String] hex string (#RRGGBB or #RRGGBBAA) or color name
        # @return [String] CSS color string (quoted)
        def convert_color_default_value(value)
          # Already formatted as quoted string
          return value if value.start_with?('"') || value.start_with?("'")

          if value.start_with?('#')
            # Hex color - keep as-is but quote it
            "\"#{value}\""
          else
            # Color name - validate against colors.json and warn if not found
            unless color_exists?(value)
              warn "[TypeConverter] Warning: Color '#{value}' is not defined in colors.json"
            end
            # Keep as CSS color name
            "\"#{value}\""
          end
        end

        # Convert image name to image path string
        # @param value [String] image name
        # @return [String] image path string (quoted)
        def convert_image_default_value(value)
          # Already formatted as quoted string
          return value if value.start_with?('"') || value.start_with?("'")

          # For React, images are typically paths or URLs
          "\"/images/#{value}\""
        end

        # Convert array of data properties
        # @param data_props [Array<Hash>] array of data properties
        # @param mode [String] the mode (react)
        # @return [Array<Hash>] normalized data properties
        def normalize_data_properties(data_props, mode = nil)
          return [] unless data_props.is_a?(Array)

          data_props.map { |prop| normalize_data_property(prop, mode) }
        end

        private

        def format_string_value(value)
          str = value.to_s
          # Handle already quoted strings
          if str.start_with?('"') && str.end_with?('"')
            str
          elsif str.start_with?("'") && str.end_with?("'")
            # Convert single quotes to double quotes
            inner = str[1..-2]
            "\"#{escape_string(inner)}\""
          else
            "\"#{escape_string(str)}\""
          end
        end

        def escape_string(str)
          str.gsub('\\', '\\\\').gsub('"', '\\"')
        end
      end
    end
  end
end
