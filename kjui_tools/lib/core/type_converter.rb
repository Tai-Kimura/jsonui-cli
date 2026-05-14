# frozen_string_literal: true

require 'json'
require_relative 'config_manager'

module KjuiTools
  module Core
    # Converts JSON primitive types to Kotlin types
    # This ensures cross-platform compatibility with SwiftJsonUI and ReactJsonUI
    class TypeConverter
      # Cache for colors.json data
      @colors_data = nil
      @colors_file_path = nil

      # Cache for type_mapping.json data
      @type_mapping = nil

      # Cache for the consumer project's .jsonui-type-map.json (separate from
      # kjui_tools/lib/core/type_mapping.json). Holds custom domain type →
      # Android imports mappings authored by the project.
      @project_type_map = nil

      # Kotlin primitive / built-in types that don't need imports.
      PRIMITIVE_TYPES = %w[
        String Int Long Float Double Boolean Any Unit Char Byte Short
        Nothing Number List Map Set Array Pair Triple
      ].freeze

      class << self
        attr_accessor :colors_data, :colors_file_path, :type_mapping, :project_type_map

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
        # @param mode [String] the mode (compose, xml)
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
        # @param mode [String] the mode (compose, xml)
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
        # @param kotlin_type [String] the Kotlin type
        # @return [String] the default value
        def get_default_value(kotlin_type)
          mapping = load_type_mapping
          mapping.dig('defaults', LANGUAGE, kotlin_type) || 'null'
        end

        # Clear the type mapping cache (useful for testing)
        def clear_type_mapping_cache
          @type_mapping = nil
        end

        # Clear the project type-map cache (useful for testing)
        def clear_project_type_map_cache
          @project_type_map = nil
        end

        # Load the consumer project's .jsonui-type-map.json — the registry of
        # custom domain types with their platform-specific class names and
        # imports. Returns `{ 'types' => {} }` if absent.
        def load_project_type_map
          return @project_type_map unless @project_type_map.nil?

          path = find_project_type_map
          if path && File.exist?(path)
            begin
              @project_type_map = JSON.parse(File.read(path))
            rescue JSON::ParserError => e
              warn "[TypeConverter] Failed to parse .jsonui-type-map.json: #{e.message}"
              @project_type_map = { 'types' => {} }
            end
          else
            @project_type_map = { 'types' => {} }
          end

          @project_type_map
        end

        # Walk up from CWD looking for `.jsonui-type-map.json`. The file lives
        # at the jui project root (alongside `jui.config.json`), which is one
        # level above the Android subproject's CWD when `jui build` runs.
        def find_project_type_map
          current = Dir.pwd
          4.times do
            candidate = File.join(current, '.jsonui-type-map.json')
            return candidate if File.exist?(candidate)
            parent = File.dirname(current)
            break if parent == current
            current = parent
          end
          nil
        end

        # Given a Kotlin type expression (e.g. `List<ProductListing>`,
        # `Map<String, ProductListing?>`, `ProductListing?`), look up Android imports
        # for each non-primitive leaf type from the project type-map.
        # @return [Array<String>] fully-qualified import paths (uniq)
        def imports_for_type(kotlin_type)
          return [] if kotlin_type.nil? || kotlin_type.to_s.empty?

          mapping = load_project_type_map
          leaves = extract_leaf_types(kotlin_type.to_s)
          leaves.flat_map do |leaf|
            type_info = mapping.dig('types', leaf, 'android', 'imports')
            type_info.is_a?(Array) ? type_info : []
          end.uniq
        end

        # Aggregate imports needed across a list of data properties.
        # @param data_properties [Array<Hash>] each with a 'class' key
        # @return [Array<String>] unique import paths
        def collect_imports_for_data_properties(data_properties)
          return [] unless data_properties.is_a?(Array)
          data_properties.flat_map { |p| imports_for_type(p['class']) }.uniq
        end

        # Decompose a Kotlin type expression into its non-primitive leaf type
        # names. Strips `?` nullability, unwraps `List<...>` / `Map<K,V>` /
        # `Set<...>` / `Array<...>` / `Pair<...>` / `Triple<...>`.
        def extract_leaf_types(type_str)
          cleaned = type_str.strip
          cleaned = cleaned[0...-1] if cleaned.end_with?('?')
          cleaned = cleaned.strip

          if (m = cleaned.match(/^(?:List|Map|Set|Array|MutableList|MutableMap|MutableSet|Pair|Triple)<(.+)>$/))
            inner = m[1]
            split_top_level_commas(inner).flat_map { |p| extract_leaf_types(p) }.uniq
          else
            PRIMITIVE_TYPES.include?(cleaned) ? [] : [cleaned]
          end
        end

        # Split a Kotlin generic argument list on top-level commas (commas
        # inside nested `<...>` are ignored).
        def split_top_level_commas(str)
          parts = []
          buf = String.new
          depth = 0
          str.each_char do |c|
            case c
            when '<' then depth += 1; buf << c
            when '>' then depth -= 1; buf << c
            when ','
              if depth == 0
                parts << buf.strip
                buf = String.new
              else
                buf << c
              end
            else
              buf << c
            end
          end
          parts << buf.strip unless buf.strip.empty?
          parts
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
            config_dir = config['_config_dir'] || Dir.pwd
            source_dir = config['source_directory'] || 'app/src/main'
            layouts_dir = config['layouts_directory'] || 'assets/Layouts'
            resources_path = File.join(config_dir, source_dir, layouts_dir, 'Resources', 'colors.json')
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

        # Get hex value for a color name from colors.json
        # @param color_name [String] the color name
        # @return [String, nil] the hex value or nil if not found
        def get_color_hex(color_name)
          load_colors_json
          @colors_data[color_name]
        end

        # Clear the cached colors data (useful for testing)
        def clear_colors_cache
          @colors_data = nil
          @colors_file_path = nil
        end
      end

      # Language key for this platform
      LANGUAGE = 'kotlin'

      # Available modes for this platform
      MODES = %w[compose xml].freeze

      # JSON type -> Kotlin type mapping (common types)
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
        'Bool' => 'Boolean',
        'bool' => 'Boolean',
        'Boolean' => 'Boolean',
        'boolean' => 'Boolean',
        # iOS-specific types mapped to Kotlin equivalents
        'CGFloat' => 'Float',
        'Void' => 'Unit',
        'void' => 'Unit',
        # Kotlin/Compose-specific types
        'Dp' => 'Dp',
        'Alignment' => 'Alignment',
        # Collection types
        'CollectionDataSource' => 'CollectionDataSource',
        # Visibility (cross-platform - maps to String in Kotlin)
        'Visibility' => 'String',
        'visibility' => 'String'
      }.freeze

      # Mode-specific type mapping (types that differ between compose and xml)
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      MODE_TYPE_MAPPING = {
        'Color' => { 'compose' => 'Color', 'xml' => 'Int' },
        'color' => { 'compose' => 'Color', 'xml' => 'Int' },
        'Image' => { 'compose' => 'Painter', 'xml' => 'Drawable' },
        'image' => { 'compose' => 'Painter', 'xml' => 'Drawable' }
      }.freeze

      # Default values for each Kotlin type
      # NOTE: These are kept for backward compatibility, but type_mapping.json is preferred
      DEFAULT_VALUES = {
        'String' => '""',
        'Int' => '0',
        'Double' => '0.0',
        'Float' => '0f',
        'Boolean' => 'false',
        'Color' => 'Color.Unspecified',
        'Dp' => '0.dp',
        'Alignment' => 'Alignment.TopStart',
        'Painter' => 'EmptyPainter()',
        'Drawable' => 'null',
        'CollectionDataSource' => 'CollectionDataSource()'
      }.freeze

      class << self
        # Extract platform-specific value from a potentially nested hash
        # Supports three formats:
        # 1. Simple value: "String" -> "String"
        # 2. Language only: { "swift": "Int", "kotlin": "Int" } -> "Int"
        # 3. Language + mode: { "kotlin": { "compose": "Color", "xml": "Int" } } -> "Color" or "Int"
        #
        # @param value [Object] the value (String, Hash, or other)
        # @param mode [String] the mode (compose, xml)
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

        # Convert JSON type to Kotlin type
        # @param json_type [String] the type specified in JSON
        # @param mode [String] the mode (compose, xml) for mode-specific types
        # @return [String] the corresponding Kotlin type
        def to_kotlin_type(json_type, mode = nil)
          return json_type if json_type.nil? || json_type.to_s.empty?

          type_str = json_type.to_s.strip

          # Check for optional type suffix
          is_optional = type_str.end_with?('?')
          base_type = is_optional ? type_str[0...-1] : type_str

          # Check for Array(ElementType) syntax -> List<ElementType>
          if (match = base_type.match(/^Array\((.+)\)$/))
            element_type = to_kotlin_type(match[1].strip, mode)
            result = "List<#{element_type}>"
            return is_optional ? "#{result}?" : result
          end

          # Check for Swift bracket syntax [ElementType] -> List<ElementType>.
          # Recurses on the inner type so `[ProductListing?]`, `[[Inner]]` etc.
          # are also normalized.
          if (match = base_type.match(/^\[(.+)\]$/))
            element_type = to_kotlin_type(match[1].strip, mode)
            result = "List<#{element_type}>"
            return is_optional ? "#{result}?" : result
          end

          # Check for Dictionary(KeyType,ValueType) syntax -> Map<KeyType, ValueType>
          if (match = base_type.match(/^Dictionary\((.+),\s*(.+)\)$/))
            key_type = to_kotlin_type(match[1].strip, mode)
            value_type = to_kotlin_type(match[2].strip, mode)
            result = "Map<#{key_type}, #{value_type}>"
            return is_optional ? "#{result}?" : result
          end

          # Check for function type: (params) -> ReturnType or ((params) -> ReturnType)?
          func_result = parse_function_type(type_str, mode)
          return func_result if func_result

          # Check mode-specific mapping first
          if mode && MODE_TYPE_MAPPING.key?(base_type)
            result = MODE_TYPE_MAPPING[base_type][mode] || MODE_TYPE_MAPPING[base_type]['compose']
            return is_optional ? "#{result}?" : result
          end

          # Then check common mapping, or return as-is if not found
          result = TYPE_MAPPING[base_type] || base_type
          is_optional ? "#{result}?" : result
        end

        # Parse a function type string and convert to Kotlin
        # Handles: (Int) -> Void, ((Image) -> Color), (() -> Unit)?, etc.
        # All function types are converted to optional by default (for callbacks)
        # @param type_str [String] the type string to parse
        # @param mode [String] the mode (compose, xml)
        # @return [String, nil] the Kotlin function type or nil if not a function type
        def parse_function_type(type_str, mode = nil)
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
          converted_params = parse_parameter_list_no_optional(params_inner, mode)

          # Convert return type (Void -> Unit)
          converted_return = convert_single_type(return_part, mode)

          # Build result - all function types become optional (for callbacks)
          "((#{converted_params}) -> #{converted_return})?"
        end

        # Convert a single type without making it optional
        def convert_single_type(type_str, mode = nil)
          return type_str if type_str.nil? || type_str.to_s.empty?

          str = type_str.to_s.strip
          is_optional = str.end_with?('?')
          base = is_optional ? str[0...-1] : str

          # Check mode-specific mapping first
          if mode && MODE_TYPE_MAPPING.key?(base)
            result = MODE_TYPE_MAPPING[base][mode] || MODE_TYPE_MAPPING[base]['compose']
            return is_optional ? "#{result}?" : result
          end

          result = TYPE_MAPPING[base] || base
          is_optional ? "#{result}?" : result
        end

        # Parse parameter list without making types optional
        def parse_parameter_list_no_optional(params_str, mode = nil)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.map { |p| convert_single_type(p.strip, mode) }.join(', ')
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

        # Get default value for a Kotlin type
        # @param kotlin_type [String] the Kotlin type
        # @return [String] the default value as Kotlin code
        def default_value(kotlin_type)
          DEFAULT_VALUES[kotlin_type] || 'null'
        end

        # Format a value for Kotlin code based on type
        # @param value [Object] the value to format
        # @param kotlin_type [String] the Kotlin type
        # @return [String] the formatted value as Kotlin code
        def format_value(value, kotlin_type)
          return 'null' if value.nil?

          case kotlin_type
          when 'String'
            format_string_value(value)
          when 'Int'
            value.to_i.to_s
          when 'Double'
            "#{value.to_f}"
          when 'Float'
            "#{value.to_f}f"
          when 'Boolean'
            value.to_s.downcase
          when 'Color'
            format_color_value(value)
          else
            value.to_s
          end
        end

        # Convert data property from JSON format to normalized format
        # @param data_prop [Hash] the data property from JSON
        # @param mode [String] the mode (compose, xml)
        # @return [Hash] normalized data property with Kotlin type
        def normalize_data_property(data_prop, mode = nil)
          return data_prop unless data_prop.is_a?(Hash)

          normalized = data_prop.dup

          # Extract platform-specific class
          raw_class = nil
          if normalized['class']
            raw_class = extract_platform_value(normalized['class'], mode)
            normalized['class'] = to_kotlin_type(raw_class, mode)
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
        # @param value [Object] the raw default value
        # @param raw_class [String] the original class type from JSON
        # @param mode [String] the mode (compose, xml)
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
            # Visibility maps to String in Kotlin - wrap in quotes
            "\"#{value}\""
          else
            value
          end
        end

        # Convert color value (hex or color name) to Kotlin Color
        # @param value [String] hex string (#RRGGBB or #RRGGBBAA) or color name
        # @param mode [String] the mode (compose, xml)
        # @return [String] Kotlin color code
        def convert_color_default_value(value, mode = nil)
          # Already formatted as Kotlin code
          return value if value.start_with?('Color') || value.start_with?('0x') || value.start_with?('0X')

          if value.start_with?('#')
            # Hex color
            hex = value.sub('#', '')
            if mode == 'xml'
              # For XML, use Int format
              if hex.length == 6
                "0xFF#{hex.upcase}"
              elsif hex.length == 8
                "0x#{hex.upcase}"
              else
                "0"
              end
            else
              # For Compose, use Color()
              if hex.length == 6
                "Color(0xFF#{hex.upcase})"
              elsif hex.length == 8
                "Color(0x#{hex.upcase})"
              else
                "Color.Unspecified"
              end
            end
          else
            # Color name from colors.json (e.g., "medium_gray", "deep_blue")
            # Get hex value from colors.json and convert to Color()
            hex_value = get_color_hex(value)
            if hex_value
              hex = hex_value.sub('#', '')
              if mode == 'xml'
                if hex.length == 6
                  "0xFF#{hex.upcase}"
                elsif hex.length == 8
                  "0x#{hex.upcase}"
                else
                  "0"
                end
              else
                # For Compose, use Color() with hex value from colors.json
                if hex.length == 6
                  "Color(0xFF#{hex.upcase})"
                elsif hex.length == 8
                  "Color(0x#{hex.upcase})"
                else
                  "Color.Unspecified"
                end
              end
            else
              warn "[TypeConverter] Warning: Color '#{value}' is not defined in colors.json"
              if mode == 'xml'
                "0"
              else
                "Color.Unspecified"
              end
            end
          end
        end

        # Convert image name to Kotlin Painter/Drawable
        # @param value [String] image name
        # @param mode [String] the mode (compose, xml)
        # @return [String] Kotlin image code
        def convert_image_default_value(value, mode = nil)
          # Already formatted as Kotlin code
          return value if value.start_with?('painterResource') || value.start_with?('R.')

          if mode == 'xml'
            # For XML, reference drawable resource
            "R.drawable.#{value}"
          else
            # For Compose, use painterResource
            "painterResource(R.drawable.#{value})"
          end
        end

        # Convert array of data properties
        # @param data_props [Array<Hash>] array of data properties
        # @param mode [String] the mode (compose, xml)
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
            hex = value.sub('#', '')
            if hex.length == 6
              "Color(0xFF#{hex.upcase})"
            elsif hex.length == 8
              "Color(0x#{hex.upcase})"
            else
              "Color.Unspecified"
            end
          else
            value.to_s
          end
        end
      end
    end
  end
end
