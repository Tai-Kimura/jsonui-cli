#!/usr/bin/env ruby

require 'json'

module KjuiTools
  module Core
    # Validates JSON component attributes against defined schemas
    # Used by both XML and Compose converters
    class AttributeValidator
      attr_reader :definitions, :warnings, :infos
      attr_accessor :mode, :styles_dir

      # Valid modes for this platform
      MODES = [:xml, :compose, :dynamic, :all].freeze

      # Current platform identifier
      PLATFORM = 'kotlin'.freeze

      # All supported platforms across JsonUI libraries
      ALL_PLATFORMS = ['swift', 'kotlin', 'react'].freeze

      def initialize(mode = :all, styles_dir = nil)
        @definitions = load_definitions
        @warnings = []
        @infos = []
        @mode = mode
        @styles_dir = styles_dir
        @styles_cache = {}
      end

      # Validate a component and return warnings
      # @param component [Hash] The component to validate
      # @param component_type [String] The type of component (e.g., "Label", "TextField")
      # @param parent_orientation [String] The parent's orientation ('horizontal' or 'vertical')
      # @return [Array<String>] Array of warning messages
      def validate(component, component_type = nil, parent_orientation = nil)
        @warnings = []
        @infos = []

        # Merge style attributes before validation
        merged_component = merge_style_attributes(component)

        type = component_type || merged_component['type']

        return @warnings unless type

        # Get valid attributes for this component type
        valid_attrs = get_valid_attributes(type)

        # Check each attribute in the merged component
        merged_component.each do |key, value|
          # Skip internal/structural attributes (including _ prefixed internal
          # flags and the `$jui` normalization marker added by `jui build`)
          next if key == 'type' || key == 'mode' || key == '$jui' || key.start_with?('_')

          # Skip child/children if all items are data-only definitions (no type)
          if (key == 'child' || key == 'children') && !valid_attrs.key?(key)
            next if value.is_a?(Array) && value.all? { |item| item.is_a?(Hash) && item.key?('data') && !item.key?('type') }
          end

          if valid_attrs.key?(key)
            attr_def = valid_attrs[key]
            # Check platform compatibility first
            if platform_compatible?(attr_def)
              # Check mode compatibility
              if mode_compatible?(attr_def)
                # Validate attribute value
                validate_attribute(key, value, attr_def, type)
              else
                # Attribute not supported in current mode - log as info
                add_mode_info(key, attr_def, type)
              end
            else
              # Attribute for other platform - log as info
              add_platform_info(key, attr_def, type)
            end
          else
            # Unknown attribute
            add_warning("Unknown attribute '#{key}' for component type '#{type}'")
          end
        end

        # Check for required attributes (only for current platform)
        valid_attrs.each do |attr_name, attr_def|
          next unless platform_compatible?(attr_def)
          if attr_def['required'] && !merged_component.key?(attr_name)
            # Skip width/height required check if weight is set and parent orientation allows it
            next if skip_dimension_required?(attr_name, merged_component, parent_orientation)

            add_warning("Required attribute '#{attr_name}' is missing for component type '#{type}'")
          end
        end

        # Check for conflicting attributes
        check_spacing_gravity_conflict(merged_component, type)

        # Check for weight + dimension conflict
        check_weight_dimension_conflict(merged_component, type, parent_orientation)

        # Check Collection requires cellIdProperty in SwiftUI/Compose mode
        if type == 'Collection' && (@mode == :swiftui || @mode == :compose)
          unless merged_component.key?('cellIdProperty')
            add_warning("Collection should have 'cellIdProperty' for unique cell identity (e.g., \"cellIdProperty\": \"id\")")
          end
        end

        @warnings
      end

      # Print all warnings to console
      def print_warnings
        @warnings.each do |warning|
          puts "\e[33m⚠️  [KJUI Warning] #{warning}\e[0m"
        end
      end

      # Print all info messages to console
      def print_infos
        @infos.each do |info|
          puts "\e[36mℹ️  [KJUI Info] #{info}\e[0m"
        end
      end

      # Check if there are any warnings
      def has_warnings?
        !@warnings.empty?
      end

      # Check if there are any info messages
      def has_infos?
        !@infos.empty?
      end

      private

      def load_definitions
        definitions_path = File.join(File.dirname(__FILE__), 'attribute_definitions.json')
        base_definitions = if File.exist?(definitions_path)
          JSON.parse(File.read(definitions_path))
        else
          puts "\e[31m[KJUI Error] attribute_definitions.json not found at #{definitions_path}\e[0m"
          {}
        end

        # Load and merge extension attribute definitions
        extension_definitions = load_extension_definitions
        merge_definitions(base_definitions, extension_definitions)
      end

      # Load extension attribute definitions from the extensions directory
      def load_extension_definitions
        extension_defs = {}

        # Check for extension definitions in various locations
        extension_paths = [
          # Main KotlinJsonUI structure
          File.join(Dir.pwd, 'kjui_tools', 'lib', 'compose', 'components', 'extensions', 'attribute_definitions'),
          # Test app structure
          File.join(Dir.pwd, 'app', 'kjui_tools', 'lib', 'compose', 'components', 'extensions', 'attribute_definitions')
        ]

        extension_paths.each do |ext_dir|
          next unless File.directory?(ext_dir)

          Dir.glob(File.join(ext_dir, '*.json')).each do |file|
            begin
              component_defs = JSON.parse(File.read(file))
              extension_defs.merge!(component_defs)
            rescue JSON::ParserError => e
              puts "\e[33m[KJUI Warning] Failed to parse extension definition #{file}: #{e.message}\e[0m"
            end
          end
        end

        extension_defs
      end

      # Merge extension definitions into base definitions
      def merge_definitions(base, extensions)
        extensions.each do |key, value|
          if base.key?(key) && base[key].is_a?(Hash) && value.is_a?(Hash)
            # Merge attributes for existing component types
            base[key] = base[key].merge(value)
          else
            # Add new component type definitions
            base[key] = value
          end
        end
        base
      end

      # Get valid attributes for a component type (common + type-specific)
      def get_valid_attributes(type)
        attrs = {}

        # Add common attributes
        attrs.merge!(@definitions['common'] || {})

        # Map component type to definition key
        def_key = map_type_to_definition(type)

        # Add type-specific attributes
        if @definitions[def_key]
          attrs.merge!(@definitions[def_key])
        end

        expand_aliases(attrs)
      end

      # Expand attributes carrying an `aliases: [...]` list into additional
      # entries that share the canonical definition. Alias entries are marked
      # with `_alias_of` so the validator can emit deprecation messages.
      def expand_aliases(attrs)
        expanded = attrs.dup
        attrs.each do |canonical, definition|
          next unless definition.is_a?(Hash)
          aliases = definition['aliases']
          next unless aliases.is_a?(Array)

          aliases.each do |alias_name|
            next if expanded.key?(alias_name)
            expanded[alias_name] = definition.merge('_alias_of' => canonical)
          end
        end
        expanded
      end

      # Map JSON type to definition key
      def map_type_to_definition(type)
        case type
        when 'Label', 'Text'
          'Label'
        when 'TextField', 'EditText'
          'TextField'
        when 'TextView', 'MultiLineEditText'
          'TextView'
        when 'Button'
          'Button'
        when 'Image', 'ImageView'
          'Image'
        when 'NetworkImage', 'NetworkImageView'
          'NetworkImage'
        when 'CircleImage', 'CircleImageView'
          'CircleImage'
        when 'SelectBox', 'Spinner', 'DatePicker'
          'SelectBox'
        when 'Toggle', 'Switch'
          'Toggle'
        when 'CheckBox', 'Check'
          type == 'CheckBox' ? 'CheckBox' : 'Check'
        when 'Radio', 'RadioButton', 'RadioGroup'
          'Radio'
        when 'Segment', 'SegmentedControl', 'TabLayout'
          'Segment'
        when 'Slider', 'SeekBar'
          'Slider'
        when 'Progress', 'ProgressBar'
          'Progress'
        when 'Indicator', 'ActivityIndicator'
          'Indicator'
        when 'View', 'Container', 'SafeAreaView', 'LinearLayout', 'RelativeLayout', 'FrameLayout',
             'VStack', 'HStack', 'ZStack', 'Column', 'Row', 'Box'
          'View'
        when 'ScrollView', 'Scroll'
          'ScrollView'
        when 'Collection', 'CollectionView', 'RecyclerView', 'LazyGrid', 'Grid'
          'Collection'
        when 'Table', 'TableView', 'ListView', 'LazyColumn'
          'Table'
        when 'GradientView'
          'GradientView'
        when 'Blur', 'BlurView'
          'Blur'
        when 'IconLabel'
          'IconLabel'
        when 'Web', 'WebView'
          'Web'
        when 'TabView'
          'TabView'
        when 'ConstraintLayout'
          'View'
        else
          type
        end
      end

      # Validate a single attribute value
      def validate_attribute(name, value, definition, component_type, path = nil)
        return unless definition

        current_path = path ? "#{path}.#{name}" : name

        # Emit deprecation warning (alias usage or canonical deprecation)
        emit_deprecation(name, current_path, definition, component_type)

        # Check for invalid binding syntax
        check_invalid_binding_syntax(value, current_path, component_type)

        # Check if value is a binding expression
        is_binding = value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

        # Skip validation for binding expressions
        return if is_binding

        # Check type
        expected_types = Array(definition['type'])
        actual_type = get_value_type(value)

        unless type_matches?(actual_type, expected_types, value, definition)
          add_warning("Attribute '#{current_path}' in '#{component_type}' expects #{format_expected_types(expected_types)}, got #{actual_type}")
          return # Don't validate nested properties if type is wrong
        end

        # Check enum values
        if definition['enum']
          validate_enum_value(value, definition['enum'], current_path, component_type)
        end

        # Check min/max for numbers
        if actual_type == 'number'
          if definition['min'] && value < definition['min']
            add_warning("Attribute '#{current_path}' in '#{component_type}' value #{value} is less than minimum #{definition['min']}")
          end
          if definition['max'] && value > definition['max']
            add_warning("Attribute '#{current_path}' in '#{component_type}' value #{value} is greater than maximum #{definition['max']}")
          end
        end

        # Validate nested object properties
        if actual_type == 'object' && definition['properties']
          validate_nested_object(value, definition['properties'], component_type, current_path)
        end

        # Validate array items
        if actual_type == 'array' && definition['items']
          validate_array_items(value, definition['items'], component_type, current_path)
        end
      end

      # Validate enum value (supports both single values and arrays)
      def validate_enum_value(value, enum_values, path, component_type)
        if value.is_a?(Array)
          # For array values, check each element
          invalid_values = value.reject { |v| enum_values.include?(v) }
          unless invalid_values.empty?
            add_warning("Attribute '#{path}' in '#{component_type}' has invalid value(s) '#{invalid_values.inspect}'. Valid values: #{enum_values.join(', ')}")
          end
        else
          # For single values
          unless enum_values.include?(value)
            add_warning("Attribute '#{path}' in '#{component_type}' has invalid value '#{value}'. Valid values: #{enum_values.join(', ')}")
          end
        end
      end

      # Format expected types for error messages
      def format_expected_types(expected_types)
        formatted = expected_types.map do |type|
          if type.is_a?(Hash) && type['enum']
            "enum(#{type['enum'].join(', ')})"
          else
            type
          end
        end
        formatted.join(' or ')
      end

      # Validate nested object properties
      def validate_nested_object(obj, properties, component_type, path)
        return unless obj.is_a?(Hash)

        obj.each do |key, value|
          if properties.key?(key)
            validate_attribute(key, value, properties[key], component_type, path)
          else
            add_warning("Unknown property '#{path}.#{key}' in '#{component_type}'")
          end
        end
      end

      # Validate array items
      def validate_array_items(arr, item_def, component_type, path)
        return unless arr.is_a?(Array)

        arr.each_with_index do |item, index|
          item_path = "#{path}[#{index}]"

          if item_def['type'] == 'object' && item_def['properties']
            if item.is_a?(Hash)
              validate_nested_object(item, item_def['properties'], component_type, item_path)
            else
              add_warning("#{item_path} in '#{component_type}' expects object, got #{get_value_type(item)}")
            end
          else
            # Simple type validation for array items
            expected_types = Array(item_def['type'])
            actual_type = get_value_type(item)
            unless type_matches?(actual_type, expected_types, item, item_def)
              add_warning("#{item_path} in '#{component_type}' expects #{expected_types.join(' or ')}, got #{actual_type}")
            end
          end
        end
      end

      def get_value_type(value)
        case value
        when String
          'string'
        when Integer, Float
          'number'
        when TrueClass, FalseClass
          'boolean'
        when Array
          'array'
        when Hash
          'object'
        when NilClass
          'null'
        else
          'unknown'
        end
      end

      def type_matches?(actual, expected_types, value, definition = nil)
        expected_types.any? do |expected|
          case expected
          when 'string'
            actual == 'string'
          when 'number'
            actual == 'number'
          when 'boolean'
            actual == 'boolean'
          when 'array'
            actual == 'array'
          when 'object'
            actual == 'object'
          when 'binding'
            # binding type requires @{propertyName} format
            actual == 'string' && value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
          when 'any'
            true
          when Hash
            # Handle enum type definition: {"enum": [...]}
            if expected['enum']
              if actual == 'string'
                expected['enum'].include?(value)
              elsif actual == 'array'
                # For array values, check if all elements are in enum
                value.is_a?(Array) && value.all? { |v| expected['enum'].include?(v) }
              else
                false
              end
            else
              false
            end
          else
            # For union types or special cases
            actual == expected
          end
        end
      end

      def add_warning(message)
        @warnings << message unless @warnings.include?(message)
      end

      def add_info(message)
        @infos << message unless @infos.include?(message)
      end

      # Emit a deprecation warning when an attribute is marked deprecated or
      # is being accessed via an alias whose canonical form is preferred.
      # `deprecated` may be:
      #   - true                         → always warn (all platforms/modes)
      #   - "swift"/"kotlin"/"react"     → warn only on that platform
      #   - "swiftui"/"uikit"/...        → warn only in that mode
      #   - array of the above           → warn if any scope matches
      def emit_deprecation(used_name, path, definition, component_type)
        return unless deprecation_applies?(definition)

        canonical = definition['_alias_of']
        note = definition['deprecation_note']

        base = if canonical && canonical != used_name
                 "Attribute '#{path}' is an alias for '#{canonical}' and is deprecated for '#{component_type}'"
               else
                 "Attribute '#{path}' in '#{component_type}' is deprecated"
               end
        base += " — #{note}" if note && !note.empty?
        add_warning(base)
      end

      # Decide whether a deprecation warning applies to the current
      # platform/mode combination.
      def deprecation_applies?(definition)
        deprecated = definition['deprecated']
        return false unless deprecated
        return true if deprecated == true

        scopes = Array(deprecated).map(&:to_s)
        own_scopes = [self.class::PLATFORM]
        if @mode == :all
          own_scopes.concat((self.class::MODES - [:all]).map(&:to_s))
        else
          own_scopes << @mode.to_s
        end
        scopes.any? { |s| own_scopes.include?(s) }
      end

      # Check for invalid binding syntax (starts with @{ but doesn't end with })
      def check_invalid_binding_syntax(value, path, component_type)
        return unless value.is_a?(String)
        return unless value.start_with?('@{')
        return if value.end_with?('}')

        add_warning("Attribute '#{path}' in '#{component_type}' has invalid binding syntax (starts with '@{' but doesn't end with '}')")
      end

      # Check for conflicting spacing and gravity attributes
      # Using both spacing and gravity together can cause unexpected layout behavior
      def check_spacing_gravity_conflict(component, component_type)
        has_spacing = component.key?('spacing') || component.key?('distribution')
        has_gravity = component.key?('gravity')

        if has_spacing && has_gravity
          add_warning("Component '#{component_type}' has both 'spacing'/'distribution' and 'gravity' set. This combination may cause unexpected layout behavior. Consider using only one of these attributes.")
        end
      end

      # Check for weight + dimension conflict in the same direction as parent orientation
      # - parent orientation: horizontal + width + weight -> warning
      # - parent orientation: vertical + height + weight -> warning
      # - no orientation (ZStack) + weight -> warning (weight is invalid)
      def check_weight_dimension_conflict(component, component_type, parent_orientation)
        return unless component.key?('weight')

        case parent_orientation
        when 'horizontal'
          if component.key?('width')
            add_warning("Component '#{component_type}' has both 'weight' and 'width' in horizontal layout. 'weight' will override 'width'. Consider removing 'width'.")
          end
        when 'vertical'
          if component.key?('height')
            add_warning("Component '#{component_type}' has both 'weight' and 'height' in vertical layout. 'weight' will override 'height'. Consider removing 'height'.")
          end
        else
          # No orientation means ZStack - weight is not applicable
          add_warning("Component '#{component_type}' has 'weight' but parent has no orientation (ZStack). 'weight' only works in horizontal/vertical layouts. Consider removing 'weight'.")
        end
      end

      # Check if width/height required warning should be skipped
      # When weight is set, the dimension in the parent's orientation direction is not required
      # - parent orientation: horizontal -> width not required if weight is set
      # - parent orientation: vertical -> height not required if weight is set
      def skip_dimension_required?(attr_name, component, parent_orientation)
        return false unless component.key?('weight')
        return false unless %w[width height].include?(attr_name)

        case parent_orientation
        when 'horizontal'
          # In horizontal layout, weight determines width
          attr_name == 'width'
        when 'vertical'
          # In vertical layout, weight determines height
          attr_name == 'height'
        else
          # Default orientation is vertical, so height is determined by weight
          attr_name == 'height'
        end
      end

      # Check if attribute is compatible with current platform
      # Attributes with platform specified for other platforms are silently skipped
      def platform_compatible?(attr_def)
        return true unless attr_def['platform']

        attr_platforms = Array(attr_def['platform'])
        attr_platforms.include?(PLATFORM) || attr_platforms.include?('all')
      end

      # Check if attribute is compatible with current mode
      def mode_compatible?(attr_def)
        return true if @mode == :all
        return true unless attr_def['mode']

        attr_modes = Array(attr_def['mode'])
        attr_modes.include?(@mode.to_s) || attr_modes.include?('all')
      end

      # Add info for mode-incompatible attribute (not an error, just informational)
      def add_mode_info(attr_name, attr_def, component_type)
        attr_modes = Array(attr_def['mode'])
        mode_str = attr_modes.map { |m| m.capitalize }.join('/')
        current_mode_str = @mode.to_s.capitalize

        add_info("Attribute '#{attr_name}' in '#{component_type}' is for #{mode_str} mode (current: #{current_mode_str})")
      end

      # Add info for platform-specific attribute (not an error, just informational)
      def add_platform_info(attr_name, attr_def, component_type)
        attr_platforms = Array(attr_def['platform'])
        platform_str = attr_platforms.map { |p| p.capitalize }.join('/')

        add_info("Attribute '#{attr_name}' in '#{component_type}' is for #{platform_str} platform (current: #{PLATFORM.capitalize})")
      end

      # Merge style attributes into component for validation
      # Style provides base attributes, component attributes override
      # @param component [Hash] The component to process
      # @return [Hash] Component with style attributes merged
      def merge_style_attributes(component)
        return component unless component.is_a?(Hash)
        return component unless component['style']

        style_name = component['style']
        style_data = load_style_file(style_name)

        return component unless style_data

        # Create merged result: style as base, component overrides
        component_without_style = component.dup
        component_without_style.delete('style')

        # If component has type, ignore style's type
        style_data_for_merge = style_data.dup
        if component_without_style['type']
          style_data_for_merge.delete('type')
        end

        # Deep merge: style as base, component properties override
        deep_merge(style_data_for_merge, component_without_style)
      end

      # Load style file from styles directory
      # @param style_name [String] Name of the style file (without .json extension)
      # @return [Hash, nil] Parsed style data or nil if not found
      def load_style_file(style_name)
        return @styles_cache[style_name] if @styles_cache.key?(style_name)

        styles_dir = determine_styles_dir
        return nil unless styles_dir

        style_file = File.join(styles_dir, "#{style_name}.json")
        return nil unless File.exist?(style_file)

        begin
          style_data = JSON.parse(File.read(style_file))
          @styles_cache[style_name] = style_data
          style_data
        rescue JSON::ParserError
          nil
        end
      end

      # Determine the styles directory path
      # @return [String, nil] Path to styles directory or nil
      def determine_styles_dir
        return @styles_dir if @styles_dir && Dir.exist?(@styles_dir)

        # Try to read from config first
        config = load_kjui_config
        if config
          source_dir = config['source_directory']
          styles_dir = config['styles_directory']
          if source_dir && styles_dir
            config_path = File.join(Dir.pwd, source_dir, styles_dir)
            return config_path if Dir.exist?(config_path)
          end
        end

        # Fallback to common locations for Android projects
        possible_dirs = [
          # Styles inside Layouts directory (common pattern)
          File.join(Dir.pwd, 'src', 'main', 'assets', 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'app', 'src', 'main', 'assets', 'Layouts', 'Styles'),
          # Styles at assets root
          File.join(Dir.pwd, 'src', 'main', 'assets', 'Styles'),
          File.join(Dir.pwd, 'app', 'src', 'main', 'assets', 'Styles'),
          # Other common locations
          File.join(Dir.pwd, 'Styles'),
          File.join(Dir.pwd, 'styles'),
          File.join(Dir.pwd, 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'Layouts', 'styles')
        ]

        possible_dirs.find { |dir| Dir.exist?(dir) }
      end

      # Load kjui.config.json if it exists
      # @return [Hash, nil] Config hash or nil
      def load_kjui_config
        config_path = File.join(Dir.pwd, 'kjui.config.json')
        return nil unless File.exist?(config_path)

        JSON.parse(File.read(config_path))
      rescue JSON::ParserError
        nil
      end

      # Deep merge two hashes
      # @param hash1 [Hash] Base hash
      # @param hash2 [Hash] Override hash
      # @return [Hash] Merged hash
      def deep_merge(hash1, hash2)
        return hash2 if hash1.nil?
        return hash1 if hash2.nil?

        result = hash1.dup

        hash2.each do |key, value|
          if result[key].is_a?(Hash) && value.is_a?(Hash)
            result[key] = deep_merge(result[key], value)
          else
            result[key] = value
          end
        end

        result
      end
    end
  end
end
