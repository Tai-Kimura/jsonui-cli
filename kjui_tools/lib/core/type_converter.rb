# frozen_string_literal: true

require 'json'
require_relative 'config_manager'
require_relative 'type_converter_core'

module KjuiTools
  module Core
    # Converts JSON primitive types to Kotlin types. Android profile over
    # the shared body (lib/core/type_converter_core.rb — byte-identical
    # mirror of shared/core/type_converter_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb): caches, platform-value
    # extraction, function-signature parsing and event-handler
    # introspection live there; the Kotlin type system, default-value
    # emitters and the project type-map import resolution live here.
    class TypeConverter < ::JsonUIShared::TypeConverterCore
      # Cache for the consumer project's .jsonui-type-map.json (separate from
      # kjui_tools/lib/core/type_mapping.json). Holds custom domain type →
      # Android imports mappings authored by the project.
      @project_type_map = nil

      # Kotlin primitive / built-in types that don't need imports.
      PRIMITIVE_TYPES = %w[
        String Int Long Float Double Boolean Any Unit Char Byte Short
        Nothing Number List Map Set Array Pair Triple
      ].freeze

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
        attr_accessor :project_type_map

        def nil_literal
          'null'
        end

        def type_mapping_dir
          File.dirname(__FILE__)
        end

        def default_colors_json_path
          # Use ConfigManager to get correct path
          config = ConfigManager.load_config
          config_dir = config['_config_dir'] || Dir.pwd
          source_dir = config['source_directory'] || 'app/src/main'
          layouts_dir = config['layouts_directory'] || 'assets/Layouts'
          File.join(config_dir, source_dir, layouts_dir, 'Resources', 'colors.json')
        end

        def convert_type(raw_class, mode = nil)
          to_kotlin_type(raw_class, mode)
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

        # Parse a function type string and convert to Kotlin.
        # All function types are converted to optional (for callbacks).
        # @return [String, nil] the Kotlin function type or nil
        def parse_function_type(type_str, mode = nil)
          sig = parse_function_signature(type_str)
          return nil unless sig

          params_inner, return_part = sig
          converted_params = parse_parameter_list_no_optional(params_inner, mode)
          converted_return = convert_single_type(return_part, mode)

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

        private

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
