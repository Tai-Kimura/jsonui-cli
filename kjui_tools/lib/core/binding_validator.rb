#!/usr/bin/env ruby

require 'json'
require 'set'

module KjuiTools
  module Core
    # Validates binding expressions in JSON layouts
    # Warns when bindings contain business logic that should be in ViewModel
    class BindingValidator
      attr_reader :warnings

      # Patterns that indicate business logic in bindings
      BUSINESS_LOGIC_PATTERNS = [
        # Ternary operators (Kotlin: if-else expression or ternary-like)
        {
          pattern: /\?.*:/,
          message: "ternary operator (?:) - move condition logic to ViewModel"
        },
        # Kotlin if expression
        {
          pattern: /\bif\s*\(/,
          message: "if expression - move condition logic to ViewModel"
        },
        # Kotlin when expression
        {
          pattern: /\bwhen\s*[({]/,
          message: "when expression - move logic to ViewModel"
        },
        # Comparison operators
        {
          pattern: /[<>=!]=|[<>]/,
          message: "comparison operator - move to ViewModel computed property"
        },
        # Arithmetic operators (but allow simple negation)
        {
          pattern: /(?<![a-zA-Z_])[+\/*%]|(?<![a-zA-Z_0-9])-(?![a-zA-Z_0-9}])/,
          message: "arithmetic operator - compute value in ViewModel"
        },
        # Logical operators
        {
          pattern: /&&|\|\|/,
          message: "logical operator (&&, ||) - move logic to ViewModel"
        },
        # Elvis operator (null coalescing)
        {
          pattern: /\?:/,
          message: "elvis operator (?:) - handle null in ViewModel"
        },
        # Method calls with arguments (but allow simple property access)
        {
          pattern: /\.\w+\([^)]+\)/,
          message: "method call with arguments - move to ViewModel"
        },
        # String interpolation
        {
          pattern: /\$\{|\$[a-zA-Z]/,
          message: "string interpolation - compose string in ViewModel"
        },
        # Array subscript with complex expression
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        # Type casting
        {
          pattern: /\s+as[?\s]+\w+/,
          message: "type casting - handle type conversion in ViewModel"
        },
        # Not-null assertion
        {
          pattern: /!!/,
          message: "not-null assertion (!!) - handle nullability safely in ViewModel"
        },
        # Lambda expressions
        {
          pattern: /\{[^}]*->[^}]*\}/,
          message: "lambda expression - move to ViewModel"
        },
        # Range operators
        {
          pattern: /\.\.|\s+until\s+|\s+downTo\s+/,
          message: "range operator - create range in ViewModel"
        },
        # let/run/apply/also blocks
        {
          pattern: /\.(let|run|apply|also|with)\s*\{/,
          message: "scope function - move logic to ViewModel"
        },
        # Negation operator (generates invalid code like data.!isLogin)
        {
          pattern: /^!/,
          message: "negation operator (!) - create a computed property in ViewModel instead (e.g., isLoggedOut instead of !isLoggedIn)"
        }
      ].freeze

      # Allowed simple patterns that look like logic but are acceptable
      ALLOWED_PATTERNS = [
        # Simple property access (including safe call)
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*(\??\.[a-zA-Z_][a-zA-Z0-9_]*)*\}$/,
        # Simple array access with constant index
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*\[\d+\]\}$/,
        # Action bindings (callbacks)
        /^@\{on[A-Z][a-zA-Z0-9_]*\}$/,
        # data. prefix for accessing data properties (e.g., @{data.name} in Collection cells)
        /^@\{data\.[a-zA-Z_][a-zA-Z0-9_.]*\}$/,
        # Simple boolean negation of a single property (e.g., @{!isHidden})
        /^@\{!\s*[a-zA-Z_][a-zA-Z0-9_]*(\??\.[a-zA-Z_][a-zA-Z0-9_]*)*\}$/
      ].freeze

      def initialize
        @warnings = []
        @data_properties = Set.new
        @used_properties = Set.new  # Track used properties for unused detection
        @data_types = {} # Store property name -> type mapping
        @attribute_definitions = load_attribute_definitions
        @my_platform = 'kotlin'
        @my_mode = 'compose'
      end

      # Validate all bindings in a JSON component tree
      # @param json_data [Hash] The root component
      # @param file_name [String] The file name for error messages
      # @return [Array<String>] Array of warning messages
      def validate(json_data, file_name = nil)
        @warnings = []
        @current_file = file_name
        @data_properties = Set.new
        @used_properties = Set.new
        @data_types = {}

        # First pass: collect all data property names and types
        collect_data_properties(json_data)

        # Second pass: validate bindings and collect used properties
        validate_component(json_data)

        # Third pass: check for unused data properties
        check_unused_properties

        @warnings
      end

      # Check if there are any warnings
      def has_warnings?
        !@warnings.empty?
      end

      # Print all warnings to stdout
      def print_warnings
        @warnings.each do |warning|
          puts "\e[33m[KJUI Binding Warning]\e[0m #{warning}"
        end
      end

      # Check a single binding expression
      # @param binding_expr [String] The binding expression (without @{ })
      # @param attribute_name [String] The attribute name
      # @param component_type [String] The component type
      # @return [Array<String>] Array of warning messages
      def check_binding(binding_expr, attribute_name, component_type)
        warnings = []

        # Check if it's allowed simple pattern
        full_binding = "@{#{binding_expr}}"
        return warnings if allowed_pattern?(full_binding)

        # Check for business logic patterns
        BUSINESS_LOGIC_PATTERNS.each do |rule|
          if binding_expr.match?(rule[:pattern])
            context = @current_file ? "[#{@current_file}] " : ""
            warnings << "#{context}Binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' contains #{rule[:message]}"
          end
        end

        warnings
      end

      private

      # Collect all data property names and types from the component tree
      def collect_data_properties(component)
        return unless component.is_a?(Hash)

        # Check for data declarations
        if component['data'].is_a?(Array)
          component['data'].each do |data_item|
            next unless data_item.is_a?(Hash)
            # Platform/mode filter
            next if data_item['platform'] && data_item['platform'] != 'kotlin'
            next if data_item['mode'] && !['compose', 'xml'].include?(data_item['mode'])
            # Skip ViewModel class declarations (they have 'class' key but no 'name')
            # e.g., { "class": "MyViewModel" } - this is a ViewModel class, not a property
            # But include property declarations: { "name": "userName", "class": "String" }
            next if data_item['class'] && !data_item['name']
            # Add property name and type to the maps
            if data_item['name']
              @data_properties << data_item['name']
              @data_types[data_item['name']] = data_item['class'] if data_item['class']
            end
          end
        end

        # Recurse into children
        children = component['child'] || component['children'] || []
        children = [children] unless children.is_a?(Array)
        children.each { |child| collect_data_properties(child) if child.is_a?(Hash) }

        # Recurse into sections
        if component['sections'].is_a?(Array)
          component['sections'].each do |section|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              collect_data_properties(section[key]) if section[key].is_a?(Hash)
            end
          end
        end
      end

      def validate_component(component, parent_type = nil)
        return unless component.is_a?(Hash)

        component_type = component['type'] || parent_type || 'Unknown'

        # Track used properties from include's shared_data and data
        collect_used_from_include(component)

        # Embed-specific structural rules (params tree grammar + navigationMode)
        validate_embed_component(component) if component_type == 'Embed'

        # Check each attribute for bindings
        component.each do |key, value|
          next if key == 'type' || key == 'child' || key == 'children' || key == 'sections'
          next if key == 'data' || key == 'generatedBy' || key == 'include' || key == 'style' || key == 'shared_data'
          next if attribute_excluded_for_platform?(component_type, key)

          check_value_for_bindings(value, key, component_type)
        end

        # Validate children
        children = component['child'] || component['children'] || []
        children = [children] unless children.is_a?(Array)
        children.each { |child| validate_component(child, component_type) if child.is_a?(Hash) }

        # Validate sections (Collection/Table)
        if component['sections'].is_a?(Array)
          component['sections'].each do |section|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              validate_component(section[key], component_type) if section[key].is_a?(Hash)
            end
          end
        end
      end

      def check_value_for_bindings(value, attribute_name, component_type)
        # Check visibility attribute for Boolean type (should use String enum: visible, gone, invisible)
        # Must be called for all value types including TrueClass/FalseClass
        check_visibility_type(value, attribute_name, component_type)

        case value
        when String
          if value.start_with?('@{') && value.end_with?('}')
            binding_expr = value[2..-2] # Remove @{ and }
            binding_warnings = check_binding(binding_expr, attribute_name, component_type)
            @warnings.concat(binding_warnings)

            # Check if binding variables are defined in data
            check_undefined_variables(binding_expr, attribute_name, component_type)

            # Check if color attributes have correct type (should be Color, not String)
            check_color_type(binding_expr, attribute_name, component_type)
          end
        when Hash
          value.each do |k, v|
            check_value_for_bindings(v, "#{attribute_name}.#{k}", component_type)
          end
        when Array
          value.each_with_index do |item, index|
            check_value_for_bindings(item, "#{attribute_name}[#{index}]", component_type)
          end
        end
      end

      # Check if variables in binding expression are defined in data
      def check_undefined_variables(binding_expr, attribute_name, component_type)
        # Skip data. prefix bindings (Collection cell bindings)
        return if binding_expr.start_with?('data.')

        # Extract variable names from the binding expression
        variables = extract_variables(binding_expr)

        variables.each do |var|
          # Track as used property
          @used_properties << var if @data_properties.include?(var)

          unless @data_properties.include?(var)
            context = @current_file ? "[#{@current_file}] " : ""
            @warnings << "#{context}Binding variable '#{var}' in '#{component_type}.#{attribute_name}' is not defined in data. Add: { \"class\": \"#{infer_type(var, attribute_name, component_type)}\", \"name\": \"#{var}\" }"
          end
        end
      end

      # Extract variable names from binding expression
      def extract_variables(binding_expr)
        variables = Set.new

        # Remove string literals to avoid false positives
        expr = binding_expr.gsub(/'[^']*'/, '').gsub(/"[^"]*"/, '')

        # Match variable names (identifiers that are not keywords or literals)
        # Skip: numbers, true, false, null, visible, gone
        keywords = %w[true false null visible gone]

        expr.scan(/\b([a-zA-Z_][a-zA-Z0-9_]*)\b/).flatten.each do |match|
          next if keywords.include?(match)
          next if match =~ /^\d/ # Skip if starts with digit
          variables << match
        end

        variables.to_a
      end

      # Infer type from variable name and attribute context
      # Returns Kotlin type format
      def infer_type(var_name, attribute_name, component_type = nil)
        # Callbacks with Int parameter
        return '((Int) -> Unit)?' if %w[onTabChange onItemAppear].include?(var_name) || %w[onTabChange onItemAppear].include?(attribute_name)

        # onClick, onXxx -> (() -> Unit)? (Kotlin callback type)
        return '(() -> Unit)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> List<Any>
        return 'List<Any>' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Boolean
        return 'Boolean' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # xxxMargin, xxxPadding -> Dp (Kotlin Compose)
        return 'Dp' if var_name.end_with?('Margin', 'Padding')

        # Based on attribute name
        case attribute_name
        when 'onTabChange', 'onItemAppear'
          '((Int) -> Unit)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Unit)?'
        when 'items'
          'CollectionDataSource'
        when 'sections'
          'List<Any>'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Boolean'
        when 'topMargin', 'bottomMargin', 'leftMargin', 'rightMargin', 'startMargin', 'endMargin'
          'Dp'
        when 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'paddingStart', 'paddingEnd'
          'Dp'
        when 'src', 'srcName'
          # NetworkImage uses URL string, Image/CircleImage uses Image type
          if component_type&.include?('Network')
            'String'
          else
            'Image'
          end
        else
          'Any'
        end
      end

      def allowed_pattern?(binding)
        ALLOWED_PATTERNS.any? { |pattern| binding.match?(pattern) }
      end

      # Check if visibility attribute is using Boolean instead of String enum
      # Valid values: "visible", "gone", "invisible"
      # Invalid: true, false, @{booleanProperty}
      def check_visibility_type(value, attribute_name, component_type)
        return unless attribute_name == 'visibility'

        # Check for literal boolean values
        if value == true || value == false || value == 'true' || value == 'false'
          context = @current_file ? "[#{@current_file}] " : ""
          @warnings << "#{context}'#{component_type}.visibility' should use String enum (\"visible\", \"gone\", \"invisible\"), not Boolean. Use a String property in data section with visibility values."
          return
        end

        # Check for binding to boolean property (isXxx, hasXxx, etc.)
        if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
          binding_expr = value[2..-2]
          # Check if binding name suggests boolean (isXxx, hasXxx, canXxx, shouldXxx)
          if binding_expr.match?(/^(is|has|can|should)[A-Z]/)
            context = @current_file ? "[#{@current_file}] " : ""
            @warnings << "#{context}'#{component_type}.visibility' binding '@{#{binding_expr}}' appears to be Boolean. Use String property with values: \"visible\", \"gone\", or \"invisible\"."
          end
        end
      end

      # Color attributes that should use Color type, not String
      COLOR_ATTRIBUTES = %w[
        background fontColor borderColor tintColor
        disabledBackground disabledFontColor
        selectedBackground selectedFontColor
        highlightedBackground highlightedFontColor
        placeholderColor cursorColor
        trackColor progressColor thumbColor
        separatorColor indicatorColor
      ].freeze

      # Check if color attributes have correct type (should be Color, not String)
      def check_color_type(binding_expr, attribute_name, component_type)
        # Get the base attribute name (without nested path like "shadow.color")
        base_attr = attribute_name.split('.').last

        # Check if this is a color attribute
        return unless COLOR_ATTRIBUTES.include?(base_attr) || base_attr.end_with?('Color')

        # Extract the variable name from binding expression
        var_name = binding_expr.split('.').first.gsub(/[^a-zA-Z0-9_]/, '')
        return if var_name.empty?

        # Check the declared type in data
        declared_type = @data_types[var_name]
        return unless declared_type

        # String is allowed for color attributes (color name resolved at runtime)
        if declared_type != 'String' && declared_type != 'Color' && !declared_type.nil?
          context = @current_file ? "[#{@current_file}] " : ""
          @warnings << "#{context}'#{component_type}.#{attribute_name}' binding '@{#{binding_expr}}' has type '#{declared_type}' but should be 'Color' or 'String'."
        end
      end

      # Collect used properties from include's shared_data and data
      # Embed structural rules (v1.5 nested params + isolated):
      # - params is a tree: intermediate nodes are literal objects only,
      #   @{} bindings may appear only at leaf scalar positions. Binding a
      #   whole subtree (a Map-typed VM property) is rejected — reactivity
      #   semantics for subtree bindings can't be guaranteed cross-platform.
      # - arrays are unsupported anywhere in params.
      # - keys must be camelCase at every level.
      # - navigationMode must be a known enum value ('delegate'/'isolated').
      def validate_embed_component(component)
        context = @current_file ? "[#{@current_file}] " : ""
        mode = component['navigationMode']
        if mode.is_a?(String) && !%w[delegate isolated].include?(mode)
          @warnings << "#{context}'Embed.navigationMode' has unknown value '#{mode}'. Supported: 'delegate', 'isolated'."
        end

        params = component['params']
        validate_embed_params_node(params, 'params', context) if params.is_a?(Hash)
      end

      def validate_embed_params_node(node, path, context)
        node.each do |key, value|
          key_path = "#{path}.#{key}"
          unless key.match?(/\A[a-z][a-zA-Z0-9]*\z/)
            @warnings << "#{context}'Embed.#{key_path}' key must be camelCase (at every nesting level)."
          end
          case value
          when Hash
            validate_embed_params_node(value, key_path, context)
          when Array
            @warnings << "#{context}'Embed.#{key_path}' is an array — arrays are not supported in Embed params. Nest literal objects or bind a scalar leaf instead."
          when String
            if value.start_with?('@{') && value.end_with?('}')
              prop = value[2..-2]
              type = @data_types[prop]
              if type.is_a?(String) && type.match?(/\AMap\s*<|\AHashMap\s*</)
                @warnings << "#{context}'Embed.#{key_path}' binds map-typed property '#{prop}' — bindings are leaf-only in Embed params (bind scalar leaves; intermediate nodes must be literal objects)."
              end
            end
          end
        end
      end

      def collect_used_from_include(component)
        # Check shared_data (values passed to included component)
        if component['shared_data'].is_a?(Hash)
          component['shared_data'].each_value do |value|
            next unless value.is_a?(String)
            # Value can be a direct property name or a binding expression
            if value.start_with?('@{') && value.end_with?('}')
              # Extract variables from binding expression
              binding_expr = value[2..-2]
              extract_variables(binding_expr).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            else
              # Direct property name reference
              @used_properties << value if @data_properties.include?(value)
            end
          end
        end

        # Check data (values passed to included component for invalidateAll)
        if component['data'].is_a?(Hash)
          component['data'].each_value do |value|
            next unless value.is_a?(String)
            # Value can be a direct property name or a binding expression
            if value.start_with?('@{') && value.end_with?('}')
              # Extract variables from binding expression
              binding_expr = value[2..-2]
              extract_variables(binding_expr).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            else
              # Direct property name reference
              @used_properties << value if @data_properties.include?(value)
            end
          end
        end
      end

      # Check for unused data properties and warn
      def check_unused_properties
        unused = @data_properties - @used_properties

        unused.each do |prop|
          context = @current_file ? "[#{@current_file}] " : ""
          @warnings << "#{context}Data property '#{prop}' is defined but never used in bindings, shared_data, or data."
        end
      end

      # Load attribute_definitions.json and collect attribute names that are excluded
      # Load attribute_definitions.json for platform/mode checking
      def load_attribute_definitions
        definitions_path = File.join(File.dirname(__FILE__), 'attribute_definitions.json')
        return {} unless File.exist?(definitions_path)

        begin
          JSON.parse(File.read(definitions_path))
        rescue JSON::ParserError
          {}
        end
      end

      # Check if an attribute is excluded for the current platform/mode
      # by looking up the component type's attribute definition
      def attribute_excluded_for_platform?(component_type, attr_name)
        # Check component-specific definition first, then common
        [component_type, 'common'].each do |type_key|
          component_defs = @attribute_definitions[type_key]
          next unless component_defs.is_a?(Hash)
          attr_def = component_defs[attr_name]
          next unless attr_def.is_a?(Hash)

          # platform / mode may be a String or an Array of platforms —
          # Array(x) normalizes both. The old `!= @my_platform` comparison
          # was always true for Array values, silently excluding the
          # attribute (and its @{...} binding) from validation.
          if attr_def['platform'] && !Array(attr_def['platform']).include?(@my_platform)
            return true
          end
          if attr_def['mode'] && !Array(attr_def['mode']).include?(@my_mode)
            return true
          end
          # Found a matching definition without exclusion
          return false
        end
        false
      end
    end
  end
end
