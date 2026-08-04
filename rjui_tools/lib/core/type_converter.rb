# frozen_string_literal: true

require 'json'
require_relative 'config_manager'
require_relative 'type_converter_core'

module RjuiTools
  module Core
    # Converts JSON primitive types to TypeScript types. Web profile over
    # the shared body (lib/core/type_converter_core.rb — byte-identical
    # mirror of shared/core/type_converter_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb): caches, platform-value
    # extraction, function-signature parsing and event-handler
    # introspection live there; the TypeScript type system and
    # default-value emitters live here.
    class TypeConverter < ::JsonUIShared::TypeConverterCore
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
        # The portable "no constraint" spelling. Swift and Kotlin both take
        # `Any` verbatim, so a layout declaring it typechecked on two of the
        # three platforms and emitted a bare `Any` — an undefined name — into
        # TypeScript.
        'Any' => 'any',
        'any' => 'any',
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
        def nil_literal
          'undefined'
        end

        def type_mapping_dir
          File.dirname(__FILE__)
        end

        def default_colors_json_path
          # Use ConfigManager to get correct path
          config = ConfigManager.load_config
          layouts_dir = config['layouts_directory'] || 'src/Layouts'
          File.join(Dir.pwd, layouts_dir, 'Resources', 'colors.json')
        end

        def convert_type(raw_class, _mode = nil)
          to_typescript_type(raw_class)
        end

        # The react consumer contract keeps the raw 'class' and adds the
        # converted TypeScript type under 'tsType'.
        def store_normalized_class(normalized, converted)
          normalized['tsType'] = converted
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

          # Check for Swift bracket syntax: [Element] -> Element[] and
          # [Key: Value] -> Record<Key, Value>. Works for custom element
          # types too — previously e.g. [SelectOption] leaked through
          # verbatim and read as a TS one-element tuple.
          if base_type.start_with?('[') && base_type.end_with?(']')
            inner = base_type[1...-1].strip
            colon = top_level_colon_index(inner)
            result = if colon
                       key_type = to_typescript_type(inner[0...colon].strip)
                       value_type = to_typescript_type(inner[(colon + 1)..].strip)
                       "Record<#{key_type}, #{value_type}>"
                     else
                       "#{to_typescript_type(inner)}[]"
                     end
            return is_optional ? "#{result} | undefined" : result
          end

          # Check for function type: (params) -> ReturnType or ((params) -> ReturnType)?
          func_result = parse_function_type(type_str)
          return func_result if func_result

          # Return mapped type, or original type as-is if not found
          result = TYPE_MAPPING[base_type] || base_type
          is_optional ? "#{result} | undefined" : result
        end

        # Index of the first colon at bracket/paren depth 0, or nil.
        # Distinguishes [Key: Value] dictionaries from [Element] arrays
        # whose element type may itself contain colons at depth > 0.
        # Angle brackets are deliberately not counted — `->` in closure
        # types would unbalance them.
        def top_level_colon_index(str)
          depth = 0
          str.each_char.with_index do |ch, i|
            case ch
            when '(', '[' then depth += 1
            when ')', ']' then depth -= 1
            when ':' then return i if depth.zero?
            end
          end
          nil
        end

        # Parse a function type string and convert to TypeScript.
        # All function types are converted to optional (for callbacks).
        # @return [String, nil] the TypeScript function type or nil
        def parse_function_type(type_str)
          sig = parse_function_signature(type_str)
          return nil unless sig

          params_inner, return_part = sig
          converted_params = parse_parameter_list(params_inner)
          converted_return = convert_single_type(return_part)

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
      end
    end
  end
end
