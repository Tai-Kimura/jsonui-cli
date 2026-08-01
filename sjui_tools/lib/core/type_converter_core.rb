# frozen_string_literal: true

require 'json'

module JsonUIShared
  # Shared body of the three toolchain TypeConverters: the
  # type_mapping.json / colors.json caches, the platform-value extraction
  # for `{ "swift": ..., "kotlin": ..., "typescript": ... }` hashes, the
  # function-type signature parser, the event-handler introspection API,
  # and the data-property normalization skeleton. Canonical copy lives in
  # shared/core/type_converter_core.rb; the per-tool copies under
  # <tool>/lib/core/ must stay byte-identical (pinned by each tool's
  # shared_core_mirror_spec).
  #
  # The platform type SYSTEM stays in the profile
  # (<tool>/lib/core/type_converter.rb): LANGUAGE / MODES, the legacy
  # TYPE_MAPPING / MODE_TYPE_MAPPING / DEFAULT_VALUES tables, the
  # to_swift/kotlin/typescript_type grammar (bracket syntaxes differ per
  # platform), and the default-value emitters (color/image/visibility).
  # Profile hooks used by the core:
  #
  #   nil_literal                'nil' / 'null' / 'undefined'
  #   default_colors_json_path   project-layout-specific colors.json path
  #   convert_type(raw, mode)    the platform type conversion
  #   store_normalized_class(normalized, converted)
  #                              where the converted type lands ('class'
  #                              on swift/kotlin, 'tsType' on react)
  #   convert_default_value(value, raw_class, mode)
  #                              the platform default-value emitter
  #
  # Unified 2026-08-02 (W3-2, file 7). Divergences resolved toward the
  # correct side:
  #   - escape_string actually escapes backslashes now. All three tools
  #     carried `gsub('\\', '\\\\')`, which in a gsub REPLACEMENT string
  #     means "backslash" — a no-op that emitted lone backslashes into
  #     generated Swift/Kotlin/TS string literals (invalid source). The
  #     block form sidesteps the replacement-escape trap
  #   - the event-handler introspection API (extract_function_parameter_types,
  #     event_handler_mode, expects_value?/expects_event?) was sjui-only;
  #     it reasons about JSON-side types, so it is platform-neutral and
  #     now available everywhere
  class TypeConverterCore
    class << self
      attr_accessor :colors_data, :colors_file_path, :type_mapping

      # ---- platform profile hooks --------------------------------------

      def nil_literal
        raise NotImplementedError, 'platform profile must define nil_literal'
      end

      def default_colors_json_path
        raise NotImplementedError, 'platform profile must define default_colors_json_path'
      end

      def convert_type(_raw_class, _mode = nil)
        raise NotImplementedError, 'platform profile must define convert_type'
      end

      def store_normalized_class(normalized, converted)
        normalized['class'] = converted
      end

      def convert_default_value(value, _raw_class, _mode = nil)
        value
      end

      # ------------------------------------------------------------------

      # Load type_mapping.json (per-tool copy alongside this file)
      # @return [Hash] the type mapping data
      def load_type_mapping
        return @type_mapping if @type_mapping

        mapping_path = File.join(type_mapping_dir, 'type_mapping.json')
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

      # Directory that holds this tool's type_mapping.json. The profile
      # class lives in <tool>/lib/core/, so resolve from ITS file — the
      # core mirror asks the subclass, and the subclass overrides this
      # with its own __dir__.
      def type_mapping_dir
        raise NotImplementedError, 'platform profile must define type_mapping_dir'
      end

      # Get type mapping for a JSON type
      # @param json_type [String] the JSON type
      # @param mode [String, nil] the platform mode
      # @return [String, nil] the mapped type or nil
      def get_type_mapping(json_type, mode = nil)
        mapping = load_type_mapping
        type_info = mapping.dig('types', json_type, self::LANGUAGE)
        return nil unless type_info

        if type_info.is_a?(Hash)
          (mode && type_info[mode]) || type_info.values.first
        else
          type_info
        end
      end

      # Get event type mapping for a component and attribute
      # @param component [String] the component type (e.g., "Button")
      # @param attribute [String] the attribute name (e.g., "onClick")
      # @param mode [String, nil] the platform mode
      # @return [String, Array, nil] the event type or nil
      def get_event_type(component, attribute, mode = nil)
        mapping = load_type_mapping
        event_info = mapping.dig('events', component, attribute, self::LANGUAGE)
        return nil unless event_info

        if event_info.is_a?(Hash)
          (mode && event_info[mode]) || event_info.values.first
        else
          event_info
        end
      end

      # Get default value for a platform type from type_mapping.json
      def get_default_value(platform_type)
        mapping = load_type_mapping
        mapping.dig('defaults', self::LANGUAGE, platform_type) || nil_literal
      end

      # Clear the type mapping cache (useful for testing)
      def clear_type_mapping_cache
        @type_mapping = nil
      end

      # Load colors.json from the specified path or auto-detect from
      # project config (path resolution is a platform-layout fact).
      # @param path [String, nil] optional path to colors.json
      # @return [Hash] the colors data
      def load_colors_json(path = nil)
        return @colors_data if @colors_data && (@colors_file_path == path || path.nil?)

        @colors_file_path = path || default_colors_json_path

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
      def color_exists?(color_name)
        load_colors_json
        @colors_data.key?(color_name)
      end

      # Get hex value for a color name from colors.json
      def get_color_hex(color_name)
        load_colors_json
        @colors_data[color_name]
      end

      # Clear the cached colors data (useful for testing)
      def clear_colors_cache
        @colors_data = nil
        @colors_file_path = nil
      end

      # Extract platform-specific value from a potentially nested hash
      # Supports three formats:
      # 1. Simple value: "String" -> "String"
      # 2. Language only: { "swift": "Int", "kotlin": "Int" } -> "Int"
      # 3. Language + mode: { "swift": { "swiftui": "Color", "uikit": "UIColor" } }
      #
      # @param value [Object] the value (String, Hash, or other)
      # @param mode [String, nil] the platform mode
      # @return [Object] the extracted value for this platform/mode
      def extract_platform_value(value, mode = nil)
        return value unless value.is_a?(Hash)

        lang_value = value[self::LANGUAGE]
        return value unless lang_value # No language key found, return original hash

        if lang_value.is_a?(Hash) && mode
          mode_value = lang_value[mode]
          return mode_value if mode_value

          # Fallback: try first available mode
          self::MODES.each do |m|
            return lang_value[m] if lang_value[m]
          end

          # No mode found, return the hash as-is (might be a custom structure)
          lang_value
        else
          lang_value
        end
      end

      # Parse a function type string into its parts. Handles the shared
      # unwrapping — optional wrapper `((...) -> ...)?` and grouping
      # parentheses `((...) -> ...)` — and splits at the top-level arrow.
      # @param type_str [String] the type string
      # @return [Array(String, String), nil] [params_inner, return_part]
      #   or nil when the string is not a function type
      def parse_function_signature(type_str)
        working_str = type_str.to_s.strip

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

        arrow_pos = find_arrow_position(working_str)
        return nil unless arrow_pos

        params_part = working_str[0...arrow_pos].strip
        return_part = working_str[(arrow_pos + 2)..].strip

        # params_part should be (...)
        return nil unless params_part.start_with?('(') && params_part.end_with?(')')

        [params_part[1...-1].strip, return_part]
      end

      # Find the position of the arrow (->) that separates params from
      # return type. Handles nested parentheses.
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

      # Extract balanced content (for finding matching parens)
      def extract_balanced_content(str, open_char, close_char)
        depth = 0
        str.each_char do |char|
          depth += 1 if char == open_char
          depth -= 1 if char == close_char
          return nil if depth < 0
        end
        depth == 0 ? str : nil
      end

      # ---- event-handler introspection (JSON-side types, platform-neutral) --

      # Event handler parameter type constants: used to determine how to
      # pass arguments to event handlers.
      EVENT_VALUE_TYPES = %w[
        Boolean Bool bool boolean
        Int Integer int integer
        Double Float double float Number number
        String string
        Color color
      ].freeze

      EVENT_OBJECT_TYPE = 'Event'

      # Extract parameter types from a function type string (raw, not
      # platform-converted).
      # @example
      #   extract_function_parameter_types("((Boolean) -> Void)?") # => ["Boolean"]
      #   extract_function_parameter_types("(() -> Void)?")        # => []
      #   extract_function_parameter_types("String")               # => nil
      def extract_function_parameter_types(type_str)
        return nil if type_str.nil? || type_str.to_s.empty?

        sig = parse_function_signature(type_str)
        return nil unless sig

        params_inner, = sig
        return [] if params_inner.empty?

        split_parameters(params_inner)
      end

      # Determine the event handler mode based on the first parameter type.
      # @return [Symbol] :value | :event | :none
      def event_handler_mode(type_str)
        params = extract_function_parameter_types(type_str)
        return :none if params.nil? || params.empty?

        first_param = params.first.to_s.sub(/\?$/, '')

        if first_param == EVENT_OBJECT_TYPE
          :event
        elsif EVENT_VALUE_TYPES.any? { |t| t.casecmp(first_param).zero? }
          :value
        else
          # Unknown type, default to value mode
          :value
        end
      end

      def expects_value?(type_str)
        event_handler_mode(type_str) == :value
      end

      def expects_event?(type_str)
        event_handler_mode(type_str) == :event
      end

      def get_first_parameter_type(type_str)
        params = extract_function_parameter_types(type_str)
        params&.first
      end

      # ------------------------------------------------------------------

      # Check if the type is a primitive type (per the platform table)
      def primitive?(json_type)
        return false if json_type.nil? || json_type.to_s.empty?

        self::TYPE_MAPPING.key?(json_type.to_s)
      end

      # Get default value for a platform type (legacy table)
      def default_value(platform_type)
        self::DEFAULT_VALUES[platform_type] || nil_literal
      end

      # Convert data property from JSON format to normalized format
      # @param data_prop [Hash] the data property from JSON
      # @param mode [String, nil] the platform mode
      # @return [Hash] normalized data property with the platform type
      def normalize_data_property(data_prop, mode = nil)
        return data_prop unless data_prop.is_a?(Hash)

        normalized = data_prop.dup

        # Extract platform-specific class
        raw_class = nil
        if normalized['class']
          raw_class = extract_platform_value(normalized['class'], mode)
          store_normalized_class(normalized, convert_type(raw_class, mode))
        end

        # Extract platform-specific defaultValue and convert for special types
        if normalized['defaultValue']
          raw_value = extract_platform_value(normalized['defaultValue'], mode)
          normalized['defaultValue'] = convert_default_value(raw_value, raw_class, mode)
        end

        normalized
      end

      # Convert array of data properties
      def normalize_data_properties(data_props, mode = nil)
        return [] unless data_props.is_a?(Array)

        data_props.map { |prop| normalize_data_property(prop, mode) }
      end

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

      # Escape a string for embedding in a generated string literal.
      # The backslash pass uses the BLOCK form: in a gsub replacement
      # string, '\\\\' collapses back to a single backslash (a no-op all
      # three tools shipped for years, emitting lone backslashes into
      # generated source). The block form takes the text literally.
      def escape_string(str)
        str.gsub('\\') { '\\\\' }.gsub('"', '\\"')
      end
    end
  end
end
