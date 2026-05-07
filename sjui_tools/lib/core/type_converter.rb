# frozen_string_literal: true

require 'json'
require_relative 'config_manager'
require_relative 'project_finder'

module SjuiTools
  module Core
    # Converts JSON primitive types to Swift types
    # This ensures cross-platform compatibility with KotlinJsonUI and ReactJsonUI
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
        # @param mode [String] the mode (swiftui, uikit)
        # @return [String, nil] the mapped type or nil
        def get_type_mapping(json_type, mode = nil)
          mapping = load_type_mapping
          type_info = mapping.dig('types', json_type, LANGUAGE)
          return nil unless type_info

          if type_info.is_a?(Hash) && mode
            type_info[mode] || type_info.values.first
          else
            type_info
          end
        end

        # Get event type mapping for a component and attribute
        # @param component [String] the component type (e.g., "Button")
        # @param attribute [String] the attribute name (e.g., "onClick")
        # @param mode [String] the mode (swiftui, uikit)
        # @return [String, Array, nil] the event type or nil
        def get_event_type(component, attribute, mode = nil)
          mapping = load_type_mapping
          event_info = mapping.dig('events', component, attribute, LANGUAGE)
          return nil unless event_info

          if event_info.is_a?(Hash) && mode
            event_info[mode] || event_info.values.first
          else
            event_info
          end
        end

        # Get default value for a type
        # @param swift_type [String] the Swift type
        # @return [String] the default value
        def get_default_value(swift_type)
          mapping = load_type_mapping
          mapping.dig('defaults', LANGUAGE, swift_type) || 'nil'
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
            # Use ConfigManager and ProjectFinder to get correct path
            config = ConfigManager.load_config
            ProjectFinder.setup_paths
            source_path = ProjectFinder.get_full_source_path || Dir.pwd
            layouts_dir = config['layouts_directory'] || 'Layouts'
            resources_dir = File.join(source_path, layouts_dir, 'Resources')
            @colors_file_path = File.join(resources_dir, 'colors.json')
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
      LANGUAGE = 'swift'

      # Available modes for this platform
      MODES = %w[swiftui uikit].freeze

      # JSON type -> Swift type mapping (common types)
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      TYPE_MAPPING = {
        # Standard types (cross-platform)
        'String' => 'String',
        'string' => 'String',
        'Int' => 'Int',
        'int' => 'Int',
        'Integer' => 'Int',
        'integer' => 'Int',
        'Double' => 'Double',
        'double' => 'Double',
        'Float' => 'Float',
        'float' => 'Float',
        'Bool' => 'Bool',
        'bool' => 'Bool',
        'Boolean' => 'Bool',
        'boolean' => 'Bool',
        # Swift-specific types
        'CGFloat' => 'CGFloat',
        'EdgeInsets' => 'EdgeInsets',
        # Kotlin-specific types mapped to Swift equivalents
        'Unit' => 'Void',
        'unit' => 'Void'
      }.freeze

      # Mode-specific type mapping (types that differ between swiftui and uikit)
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      MODE_TYPE_MAPPING = {
        'Color' => { 'swiftui' => 'Color', 'uikit' => 'UIColor' },
        'color' => { 'swiftui' => 'Color', 'uikit' => 'UIColor' },
        'Image' => { 'swiftui' => 'String', 'uikit' => 'UIImage' },
        'image' => { 'swiftui' => 'String', 'uikit' => 'UIImage' },
        'Visibility' => { 'swiftui' => 'String', 'uikit' => 'SJUIView.Visibility' },
        'visibility' => { 'swiftui' => 'String', 'uikit' => 'SJUIView.Visibility' },
        # Collection types
        'CollectionDataSource' => { 'swiftui' => 'CollectionDataSource', 'uikit' => 'UIKitCollectionDataSource' }
      }.freeze

      # Default values for each Swift type
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      DEFAULT_VALUES = {
        'String' => '""',
        'Int' => '0',
        'Double' => '0.0',
        'Float' => '0.0',
        'Bool' => 'false',
        'CGFloat' => '0.0',
        'Color' => '.clear',
        'UIColor' => '.clear',
        'UIImage' => 'nil',
        'EdgeInsets' => 'EdgeInsets()',
        'CollectionDataSource' => 'CollectionDataSource()',
        'UIKitCollectionDataSource' => 'UIKitCollectionDataSource()',
        'Visibility' => '.visible',
        'SJUIView.Visibility' => '.visible'
      }.freeze

      class << self
        # Extract platform-specific value from a potentially nested hash
        # Supports three formats:
        # 1. Simple value: "String" -> "String"
        # 2. Language only: { "swift": "Int", "kotlin": "Int" } -> "Int"
        # 3. Language + mode: { "swift": { "swiftui": "Color", "uikit": "UIColor" } } -> "Color" or "UIColor"
        #
        # @param value [Object] the value (String, Hash, or other)
        # @param mode [String] the mode (swiftui, uikit)
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

        # Convert JSON type to Swift type
        # @param json_type [String] the type specified in JSON
        # @param mode [String] the mode (swiftui, uikit) for mode-specific types
        # @return [String] the corresponding Swift type
        def to_swift_type(json_type, mode = nil)
          return json_type if json_type.nil? || json_type.to_s.empty?

          type_str = json_type.to_s.strip

          # Check for optional type suffix
          is_optional = type_str.end_with?('?')
          base_type = is_optional ? type_str[0...-1] : type_str

          # Check for Array(ElementType) syntax -> [ElementType]
          if (match = base_type.match(/^Array\((.+)\)$/))
            element_type = to_swift_type(match[1].strip, mode)
            result = "[#{element_type}]"
            return is_optional ? "#{result}?" : result
          end

          # Check for Dictionary(KeyType,ValueType) syntax -> [KeyType: ValueType]
          if (match = base_type.match(/^Dictionary\((.+),\s*(.+)\)$/))
            key_type = to_swift_type(match[1].strip, mode)
            value_type = to_swift_type(match[2].strip, mode)
            result = "[#{key_type}: #{value_type}]"
            return is_optional ? "#{result}?" : result
          end

          # Check for function type: (params) -> ReturnType or ((params) -> ReturnType)?
          func_result = parse_function_type(type_str, mode)
          return func_result if func_result

          # Check mode-specific mapping first
          if mode && MODE_TYPE_MAPPING.key?(base_type)
            result = MODE_TYPE_MAPPING[base_type][mode] || MODE_TYPE_MAPPING[base_type]['swiftui']
            return is_optional ? "#{result}?" : result
          end

          # Then check common mapping, or return as-is if not found
          result = TYPE_MAPPING[base_type] || base_type
          is_optional ? "#{result}?" : result
        end

        # Parse a function type string and convert to Swift
        # Handles: (Int) -> Void, ((Image) -> Color), (() -> Unit)?, etc.
        # All function types are converted to optional by default (for callbacks)
        # @param type_str [String] the type string to parse
        # @param mode [String] the mode (swiftui, uikit)
        # @return [String, nil] the Swift function type or nil if not a function type
        def parse_function_type(type_str, mode = nil)
          working_str = type_str.strip

          # Check for optional wrapper: ((...) -> ...)? or (() -> ...)?
          # Remove it if present, we'll add it back at the end
          if working_str.end_with?(')?')
            # Could be optional function: ((...) -> ...)?
            # Find matching opening paren
            if working_str.start_with?('(')
              inner = extract_balanced_content(working_str[1...-2], '(', ')')
              if inner && inner == working_str[1...-2]
                # The entire content inside is the function signature
                working_str = working_str[1...-2]
              end
            end
          # Check for grouping parentheses: ((params) -> ReturnType) without ?
          elsif working_str.start_with?('(') && working_str.end_with?(')')
            # Check if inner content is a valid function type
            inner = working_str[1...-1]
            if find_arrow_position(inner)
              # Has arrow inside, this is a grouped function type
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

          # Parse parameters (handling nested types) - use convert_single_type to avoid adding ?
          converted_params = parse_parameter_list_no_optional(params_inner, mode)

          # Convert return type - use convert_single_type to avoid adding ?
          converted_return = convert_single_type(return_part, mode)

          # Build result - all function types become optional (for callbacks)
          "((#{converted_params}) -> #{converted_return})?"
        end

        # Convert a single type without making it optional (for use inside function signatures)
        # @param type_str [String] the type string
        # @param mode [String] the mode
        # @return [String] the converted type
        def convert_single_type(type_str, mode = nil)
          return type_str if type_str.nil? || type_str.to_s.empty?

          str = type_str.to_s.strip

          # Check for optional suffix
          is_optional = str.end_with?('?')
          base = is_optional ? str[0...-1] : str

          # Check mode-specific mapping first
          if mode && MODE_TYPE_MAPPING.key?(base)
            result = MODE_TYPE_MAPPING[base][mode] || MODE_TYPE_MAPPING[base]['swiftui']
            return is_optional ? "#{result}?" : result
          end

          # Then check common mapping
          result = TYPE_MAPPING[base] || base
          is_optional ? "#{result}?" : result
        end

        # Parse parameter list without making types optional
        # @param params_str [String] the parameters string
        # @param mode [String] the mode
        # @return [String] converted parameters
        def parse_parameter_list_no_optional(params_str, mode = nil)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.map { |p| convert_single_type(p.strip, mode) }.join(', ')
        end

        # Find the position of the arrow (->) that separates params from return type
        # Must handle nested parentheses
        # @param str [String] the string to search
        # @return [Integer, nil] position of '->' or nil
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

        # Parse a comma-separated parameter list, handling nested types
        # @param params_str [String] the parameters string (without outer parens)
        # @param mode [String] the mode
        # @return [String] converted parameters joined by ', '
        def parse_parameter_list(params_str, mode = nil)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.map { |p| to_swift_type(p.strip, mode) }.join(', ')
        end

        # Event handler parameter type constants
        # These are used to determine how to pass arguments to event handlers
        EVENT_VALUE_TYPES = %w[
          Boolean Bool bool boolean
          Int Integer int integer
          Double Float double float Number number
          String string
          Color color
        ].freeze

        EVENT_OBJECT_TYPE = 'Event'

        # Extract parameter types from a function type string
        # Used by converters to determine the expected argument types for event handlers
        # @param type_str [String] the function type string, e.g., "((Boolean) -> Void)?"
        # @return [Array<String>] array of parameter type strings (raw, not converted)
        # @example
        #   extract_function_parameter_types("((Boolean) -> Void)?") # => ["Boolean"]
        #   extract_function_parameter_types("((Int, String) -> Void)?") # => ["Int", "String"]
        #   extract_function_parameter_types("(() -> Void)?") # => []
        #   extract_function_parameter_types("String") # => nil (not a function type)
        def extract_function_parameter_types(type_str)
          return nil if type_str.nil? || type_str.to_s.empty?

          working_str = type_str.to_s.strip

          # Remove optional wrapper: ((...) -> ...)? or (() -> ...)?
          if working_str.end_with?(')?')
            if working_str.start_with?('(')
              inner = extract_balanced_content(working_str[1...-2], '(', ')')
              if inner && inner == working_str[1...-2]
                working_str = working_str[1...-2]
              end
            end
          # Remove grouping parentheses: ((params) -> ReturnType)
          elsif working_str.start_with?('(') && working_str.end_with?(')')
            inner = working_str[1...-1]
            if find_arrow_position(inner)
              working_str = inner
            end
          end

          # Parse as function: (params) -> ReturnType
          arrow_pos = find_arrow_position(working_str)
          return nil unless arrow_pos

          params_part = working_str[0...arrow_pos].strip

          # params_part should be (...)
          return nil unless params_part.start_with?('(') && params_part.end_with?(')')

          params_inner = params_part[1...-1].strip

          # Return empty array for no parameters
          return [] if params_inner.empty?

          # Split and return parameter types
          split_parameters(params_inner)
        end

        # Determine the event handler mode based on the first parameter type
        # @param type_str [String] the function type string
        # @return [Symbol] :value if expects value type, :event if expects Event object, :none if no params
        # @example
        #   event_handler_mode("((Boolean) -> Void)?") # => :value
        #   event_handler_mode("((Event) -> Void)?") # => :event
        #   event_handler_mode("(() -> Void)?") # => :none
        def event_handler_mode(type_str)
          params = extract_function_parameter_types(type_str)
          return :none if params.nil? || params.empty?

          first_param = params.first.to_s.sub(/\?$/, '') # Remove optional suffix

          if first_param == EVENT_OBJECT_TYPE
            :event
          elsif EVENT_VALUE_TYPES.any? { |t| t.casecmp(first_param).zero? }
            :value
          else
            # Unknown type, default to value mode
            :value
          end
        end

        # Check if a function type expects a value (not Event object) as first parameter
        # @param type_str [String] the function type string
        # @return [Boolean] true if expects value type
        def expects_value?(type_str)
          event_handler_mode(type_str) == :value
        end

        # Check if a function type expects an Event object as first parameter
        # @param type_str [String] the function type string
        # @return [Boolean] true if expects Event object
        def expects_event?(type_str)
          event_handler_mode(type_str) == :event
        end

        # Get the first parameter type of a function type
        # Commonly used for single-argument event handlers
        # @param type_str [String] the function type string
        # @return [String, nil] the first parameter type or nil
        def get_first_parameter_type(type_str)
          params = extract_function_parameter_types(type_str)
          params&.first
        end

        # Split parameters by comma, respecting nested parentheses and generics
        # @param str [String] the string to split
        # @return [Array<String>] array of parameter strings
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

        # Extract balanced content (for finding matching parens)
        # @param str [String] the string to check
        # @param open_char [String] opening character
        # @param close_char [String] closing character
        # @return [String, nil] the content if balanced, nil otherwise
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

        # Get default value for a Swift type
        # @param swift_type [String] the Swift type
        # @return [String] the default value as Swift code
        def default_value(swift_type)
          DEFAULT_VALUES[swift_type] || 'nil'
        end

        # Format a value for Swift code based on type
        # @param value [Object] the value to format
        # @param swift_type [String] the Swift type
        # @return [String] the formatted value as Swift code
        def format_value(value, swift_type)
          return 'nil' if value.nil?

          case swift_type
          when 'String'
            format_string_value(value)
          when 'Int'
            value.to_i.to_s
          when 'Double', 'CGFloat'
            value.to_f.to_s
          when 'Float'
            "#{value.to_f}"
          when 'Bool'
            value.to_s.downcase
          when 'Color'
            format_color_value(value)
          else
            value.to_s
          end
        end

        # Convert data property from JSON format to normalized format
        # @param data_prop [Hash] the data property from JSON
        # @param mode [String] the mode (swiftui, uikit)
        # @return [Hash] normalized data property with Swift type
        def normalize_data_property(data_prop, mode = nil)
          return data_prop unless data_prop.is_a?(Hash)

          normalized = data_prop.dup

          # Extract platform-specific class
          raw_class = nil
          if normalized['class']
            raw_class = extract_platform_value(normalized['class'], mode)
            normalized['class'] = to_swift_type(raw_class, mode)
          end

          # Extract platform-specific defaultValue and convert for special types
          if normalized['defaultValue']
            raw_value = extract_platform_value(normalized['defaultValue'], mode)
            normalized['defaultValue'] = convert_default_value(raw_value, raw_class, mode)
          end

          normalized
        end

        # Convert defaultValue based on the type
        # For Color: convert hex/color name to platform-specific format
        # For Image: convert image name to platform-specific format
        # For Visibility: convert visibility string to enum value
        # @param value [Object] the raw default value
        # @param raw_class [String] the original class type from JSON
        # @param mode [String] the mode (swiftui, uikit)
        # @return [Object] the converted default value
        def convert_default_value(value, raw_class, mode = nil)
          return value unless value.is_a?(String) && raw_class.is_a?(String)

          base_class = raw_class.end_with?('?') ? raw_class[0...-1] : raw_class

          case base_class.downcase
          when 'color'
            convert_color_default_value(value, mode)
          when 'image'
            convert_image_default_value(value, mode)
          when 'visibility'
            convert_visibility_default_value(value, mode)
          else
            # Check MODE_TYPE_MAPPING for type constructor conversion
            # e.g., "CollectionDataSource()" → "UIKitCollectionDataSource()" in uikit mode
            convert_type_constructor(value, mode)
          end
        end

        # Convert type constructors in default values using MODE_TYPE_MAPPING
        # e.g., "CollectionDataSource()" → "UIKitCollectionDataSource()" in uikit mode
        def convert_type_constructor(value, mode)
          return value unless mode
          MODE_TYPE_MAPPING.each do |generic_type, mode_map|
            mapped_type = mode_map[mode]
            next unless mapped_type && mapped_type != generic_type
            # Use word-boundary match so we don't replace within other identifiers
            # (e.g., don't turn "UIColor.blue" into "UIUIColor.blue" when mapping Color -> UIColor).
            pattern = /(?<![A-Za-z0-9_])#{Regexp.escape(generic_type)}(?![A-Za-z0-9_])/
            if value =~ pattern
              return value.gsub(pattern, mapped_type)
            end
          end
          value
        end

        # Convert visibility string to platform-specific value
        # UIKit: .visible / .gone / .invisible (SJUIView.Visibility enum)
        # SwiftUI: "visible" / "gone" / "invisible" (String for VisibilityWrapper)
        def convert_visibility_default_value(value, mode = nil)
          if mode == 'swiftui'
            # SwiftUI uses String - wrap in quotes
            "\"#{value}\""
          else
            # UIKit uses SJUIView.Visibility enum
            case value.downcase
            when 'visible'
              '.visible'
            when 'gone'
              '.gone'
            when 'invisible'
              '.invisible'
            else
              value.start_with?('.') ? value : ".#{value}"
            end
          end
        end

        # Convert color value (hex or color name) to Swift Color/UIColor
        # Uses UIColor.colorWithHexString for hex colors
        # Uses ColorManager for named colors (from colors.json)
        # @param value [String] hex string (#RRGGBB or #RRGGBBAA) or color name from colors.json
        # @param mode [String] the mode (swiftui, uikit)
        # @return [String] Swift color code
        def convert_color_default_value(value, mode = nil)
          # Already formatted as Swift code
          return value if value.start_with?('.') || value.start_with?('Color') || value.start_with?('UIColor')

          if value.start_with?('#')
            # Hex color - use UIColor.colorWithHexString
            if mode == 'uikit'
              "UIColor.colorWithHexString(\"#{value}\") ?? .clear"
            else
              # SwiftUI: convert UIColor to Color
              "Color(uiColor: UIColor.colorWithHexString(\"#{value}\") ?? .clear)"
            end
          else
            # Color name from colors.json (e.g., "medium_gray", "deep_blue")
            # Validate that the color exists in colors.json
            unless color_exists?(value)
              warn "[TypeConverter] Warning: Color '#{value}' is not defined in colors.json"
            end

            # ColorManager generates camelCase property names (medium_gray -> mediumGray)
            property_name = snake_to_camel(value)
            if mode == 'uikit'
              "ColorManager.uikit.#{property_name} ?? .clear"
            else
              "ColorManager.swiftui.#{property_name} ?? .clear"
            end
          end
        end

        # Convert snake_case to camelCase
        # @param snake_case [String] the snake_case string
        # @return [String] the camelCase string
        def snake_to_camel(snake_case)
          return snake_case unless snake_case.is_a?(String) && snake_case.include?('_')

          parts = snake_case.split('_')
          first_part = parts.shift
          first_part + parts.map(&:capitalize).join
        end

        # Convert image name to Swift Image/UIImage
        # @param value [String] image name
        # @param mode [String] the mode (swiftui, uikit)
        # @return [String] Swift image code
        def convert_image_default_value(value, mode = nil)
          # Already formatted as Swift code
          return value if value.start_with?('UIImage') || value.start_with?('Image') || value.start_with?('"')

          if mode == 'uikit'
            "UIImage(named: \"#{value}\")"
          else
            # For SwiftUI, Image type is String (image name)
            "\"#{value}\""
          end
        end

        # Convert array of data properties
        # @param data_props [Array<Hash>] array of data properties
        # @param mode [String] the mode (swiftui, uikit)
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

        def format_color_value(value)
          if value.is_a?(String) && value.start_with?('#')
            "Color(uiColor: UIColor.colorWithHexString(\"#{value}\") ?? .clear)"
          else
            value.to_s
          end
        end
      end
    end
  end
end
