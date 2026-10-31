# frozen_string_literal: true

require 'json'
require_relative 'config_manager'
require_relative 'type_converter_core'
require_relative 'logger'

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
          converted = to_typescript_type(raw_class)
          # A type TypeScript has no spelling for is said, not written silently.
          if (why = unportable_reason(converted, 'typescript'))
            report_warning("type '#{raw_class}' comes out as '#{converted}', which is not a TypeScript type (#{why})")
          end
          converted
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

          # A collection in the spec's own shapes (`[T]`, `[K: V]`,
          # `Array(T)`, `List(T)`, `Dictionary(K, V)`, `Map(K, V)`, nested
          # to any depth) -> T[] / Record<K, V>. Works for custom element
          # types too — [SelectOption] once leaked through verbatim and read
          # as a TS one-element tuple; `List(T)` and `Map(K, V)` still did.
          if (kind, members = collection_shape(base_type))
            converted = members.map { |m| to_typescript_type(m) }
            result = kind == :list ? array_of(converted[0]) : "Record<#{converted[0]}, #{converted[1]}>"
            return is_optional ? "#{result} | undefined" : result
          end

          # Check for function type: (params) -> ReturnType or ((params) -> ReturnType)?
          func_result = parse_function_type(type_str)
          return func_result if func_result

          # Return mapped type, or original type as-is if not found
          result = TYPE_MAPPING[base_type] || base_type
          is_optional ? "#{result} | undefined" : result
        end

        # `Element[]` for an already-converted element type. `[]` binds
        # tighter than `|` and `=>` in TypeScript, so an element that is a
        # union (`Double?` -> `number | undefined`) or a function type is
        # written in parentheses: `[Double?]` -> `(number | undefined)[]`.
        # Without them `number | undefined[]` reads as "a number, or an
        # array of undefined", and an array holding values is rejected.
        # Both array spellings ([Element] and Array(Element)) come through
        # here, so nesting ([[Double?]] -> `(number | undefined)[][]`) does
        # too: the outer element `(number | undefined)[]` has no top-level
        # `|` and stays bare.
        def array_of(element_type)
          needs_parens = top_level_union_or_function?(element_type)
          needs_parens ? "(#{element_type})[]" : "#{element_type}[]"
        end

        # True when a converted TypeScript type has `|` or `=>` outside any
        # (), [], <> or {} — the operators `[]` would otherwise bind under.
        # The `>` of `=>` is not a closing bracket.
        def top_level_union_or_function?(ts_type)
          depth = 0
          prev = nil
          ts_type.each_char do |ch|
            case ch
            when '(', '[', '<', '{' then depth += 1
            when ')', ']', '}' then depth -= 1
            when '>'
              if prev == '='
                return true if depth.zero?
              else
                depth -= 1
              end
            when '|' then return true if depth.zero?
            end
            prev = ch
          end
          false
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

        # Convert a single type without making it optional: a parameter or
        # the return of a function type. A collection here is converted as
        # one outside a function is — `(([File]) -> Void)?` once wrote
        # `(arg0: [File]) => void`, a one-element tuple — and a function
        # here is written in TypeScript, optional only when declared so.
        def convert_single_type(type_str)
          return type_str if type_str.nil? || type_str.to_s.empty?

          str = type_str.to_s.strip
          is_optional = str.end_with?('?')
          base = is_optional ? str[0...-1] : str

          return to_typescript_type(str) if collection_shape(base)

          if (sig = parse_function_signature(str))
            params_inner, return_part = sig
            result = "(#{parse_parameter_list(params_inner)}) => #{convert_single_type(return_part)}"
            # The `?` is the function's when the signature parser took it off a wrapper, not off the return.
            return str.end_with?(return_part) ? result : "(#{result}) | undefined"
          end

          result = TYPE_MAPPING[base] || base
          is_optional ? "#{result} | undefined" : result
        end

        # Parse parameter list and convert types
        def parse_parameter_list(params_str)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.each_with_index.map do |p, i|
            # A Swift label names the parameter (`_ id: Int` -> `id: number`); it was written into the type.
            _label, name, type = labeled_parameter(p)
            "#{name || "arg#{i}"}: #{convert_single_type((type || p).strip)}"
          end.join(', ')
        end

        # A build warning from the shared core (a data default with no
        # value for this platform) goes where the tool's others go.
        def report_warning(message)
          Core::Logger.warn(message)
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
              report_warning("Color '#{value}' is not defined in colors.json")
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
