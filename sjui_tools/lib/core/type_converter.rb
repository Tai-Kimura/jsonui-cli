# frozen_string_literal: true

require 'json'
require_relative 'config_manager'
require_relative 'project_finder'
require_relative 'type_converter_core'

module SjuiTools
  module Core
    # Converts JSON primitive types to Swift types. iOS profile over the
    # shared body (lib/core/type_converter_core.rb — byte-identical mirror
    # of shared/core/type_converter_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb): caches, platform-value
    # extraction, function-signature parsing and event-handler
    # introspection live there; the Swift type system and default-value
    # emitters live here.
    class TypeConverter < ::JsonUIShared::TypeConverterCore
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
        'unit' => 'Void',
        # JSON container classes. These name a SHAPE, not a Swift type, and
        # without an entry the declared name was emitted verbatim —
        # `var profile: Object = ...` does not compile. The web face already
        # maps the same spellings (Object/object/Hash/hash ->
        # Record<string, any>).
        'Object' => '[String: Any]',
        'object' => '[String: Any]',
        'Hash' => '[String: Any]',
        'hash' => '[String: Any]',
        'Array' => '[Any]',
        'array' => '[Any]'
      }.freeze

      # Declared classes naming a JSON container rather than a model type.
      # Only these are re-spelled for the data model; every other class name is
      # a type the project declares and is emitted as written.
      JSON_CONTAINER_CLASSES = %w[Object object Hash hash Array array].freeze

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
        def nil_literal
          'nil'
        end

        def type_mapping_dir
          File.dirname(__FILE__)
        end

        def default_colors_json_path
          # Use ConfigManager and ProjectFinder to get correct path
          config = ConfigManager.load_config
          ProjectFinder.setup_paths
          source_path = ProjectFinder.get_full_source_path || Dir.pwd
          layouts_dir = config['layouts_directory'] || 'Layouts'
          File.join(source_path, layouts_dir, 'Resources', 'colors.json')
        end

        def convert_type(raw_class, mode = nil)
          to_swift_type(raw_class, mode)
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

        # Parse a function type string and convert to Swift.
        # All function types are converted to optional (for callbacks).
        # @return [String, nil] the Swift function type or nil
        def parse_function_type(type_str, mode = nil)
          sig = parse_function_signature(type_str)
          return nil unless sig

          params_inner, return_part = sig
          converted_params = parse_parameter_list_no_optional(params_inner, mode)
          converted_return = convert_single_type(return_part, mode)

          "((#{converted_params}) -> #{converted_return})?"
        end

        # Convert a single type without making it optional (for use inside function signatures)
        def convert_single_type(type_str, mode = nil)
          return type_str if type_str.nil? || type_str.to_s.empty?

          str = type_str.to_s.strip
          is_optional = str.end_with?('?')
          base = is_optional ? str[0...-1] : str

          # Check mode-specific mapping first
          if mode && MODE_TYPE_MAPPING.key?(base)
            result = MODE_TYPE_MAPPING[base][mode] || MODE_TYPE_MAPPING[base]['swiftui']
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

        # Parse a comma-separated parameter list, handling nested types
        def parse_parameter_list(params_str, mode = nil)
          return '' if params_str.nil? || params_str.empty?

          params = split_parameters(params_str)
          params.map { |p| to_swift_type(p.strip, mode) }.join(', ')
        end

        # Format a value for Swift code based on type
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

        # Convert defaultValue based on the type
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
        def snake_to_camel(snake_case)
          return snake_case unless snake_case.is_a?(String) && snake_case.include?('_')

          parts = snake_case.split('_')
          first_part = parts.shift
          first_part + parts.map(&:capitalize).join
        end

        # Convert image name to Swift Image/UIImage
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

        private

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
