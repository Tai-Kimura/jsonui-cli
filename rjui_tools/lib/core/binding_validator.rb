#!/usr/bin/env ruby

require 'json'
require 'set'

module RjuiTools
  module Core
    # Validates binding expressions in JSON layouts
    # Warns when bindings contain business logic that should be in ViewModel
    # Also validates that binding variables are defined in data declarations
    class BindingValidator
      PLATFORM = 'react'.freeze

      attr_reader :warnings

      # Patterns that indicate business logic in bindings
      # Note: Order matters - more specific patterns should come before general ones
      BUSINESS_LOGIC_PATTERNS = [
        # Ternary operator (condition ? value : value) - most common violation
        {
          pattern: /\?.*:/,
          message: "ternary operator (? :) - compute value in ViewModel (e.g., showContent: currentTab === 0)"
        },
        # Comparison operators (===, ==, !==, !=, <, >, <=, >=)
        {
          pattern: /===|==|!==|!=|<=|>=|<|>/,
          message: "comparison operator - move comparison to ViewModel"
        },
        # viewModel. prefix in binding - should use direct property name
        {
          pattern: /viewModel\./,
          message: "viewModel. prefix - use direct property name (e.g., @{propertyName} instead of @{viewModel.propertyName})"
        },
        # Increment/decrement operators (must be before arithmetic)
        {
          pattern: /\+\+|--/,
          message: "increment/decrement - update value in ViewModel"
        },
        # Arithmetic operators (but allow simple negation, and exclude ++ --)
        {
          pattern: /(?<!\+)\+(?!\+)|(?<!-)\/|(?<![a-zA-Z_])\*|(?<![a-zA-Z_])%/,
          message: "arithmetic operator - compute value in ViewModel"
        },
        # Logical operators
        {
          pattern: /&&|\|\|/,
          message: "logical operator (&&, ||) - move logic to ViewModel"
        },
        # Nil coalescing
        {
          pattern: /\?\?/,
          message: "nil coalescing (??) - handle nil in ViewModel"
        },
        # Function calls with arguments (standalone or chained)
        {
          pattern: /\w+\([^)]+\)/,
          message: "function call with arguments - move to ViewModel"
        },
        # String interpolation (JavaScript template literals)
        {
          pattern: /`[^`]*\$\{/,
          message: "string interpolation - compose string in ViewModel"
        },
        # Array subscript with complex expression
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        # Spread operator
        {
          pattern: /\.\.\./,
          message: "spread operator - handle in ViewModel"
        },
        # Negation operator (generates invalid code)
        {
          pattern: /^!/,
          message: "negation operator (!) - create a computed property in ViewModel instead (e.g., isLoggedOut instead of !isLoggedIn)"
        }
      ].freeze

      # Allowed simple patterns that look like logic but are acceptable
      ALLOWED_PATTERNS = [
        # Simple property access (no dot notation - direct property name only)
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*\}$/,
        # Simple array access with constant index
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*\[\d+\]\}$/,
        # Action bindings (callbacks) - onXxx pattern
        /^@\{on[A-Z][a-zA-Z0-9_]*\}$/,
        # data. prefix for accessing data properties (e.g., @{data.name} in Collection cells)
        /^@\{data\.[a-zA-Z_][a-zA-Z0-9_.]*\}$/
      ].freeze

      def initialize
        @warnings = []
        @data_properties = Set.new
        @used_properties = Set.new  # Track used properties for unused detection
        @data_types = {} # Store property name -> type mapping
        @has_data_definitions = false
        @incompatible_attrs_by_type = load_incompatible_attrs
      end

      # Load attribute_definitions.json and collect, per component type, the set
      # of attribute names marked for platforms other than 'react'. Bindings
      # inside these attributes are iOS/Android-only and should be skipped.
      def load_incompatible_attrs
        # Deployed copies mirror the file into lib/core/ alongside this file.
        # Source-repo layout keeps the canonical copy at ../../../shared/core/.
        candidates = [
          File.join(File.dirname(__FILE__), 'attribute_definitions.json'),
          File.expand_path('../../../../shared/core/attribute_definitions.json', __FILE__)
        ]
        path = candidates.find { |p| File.exist?(p) }
        return {} unless path

        defs = JSON.parse(File.read(path))
        result = {}
        defs.each do |component_type, attrs|
          next unless attrs.is_a?(Hash)
          incompatible = Set.new
          attrs.each do |attr_name, attr_def|
            next unless attr_def.is_a?(Hash)
            next unless attr_def['platform']

            platforms = Array(attr_def['platform'])
            unless platforms.include?(PLATFORM) || platforms.include?('all')
              incompatible << attr_name
            end
          end
          result[component_type] = incompatible unless incompatible.empty?
        end
        result
      rescue JSON::ParserError
        {}
      end

      def incompatible_attr?(component_type, attr_name)
        # Strip nested-path suffix: "confirmationDialog.isPresented" → "confirmationDialog"
        top_level = attr_name.to_s.split('.').first
        type_attrs = @incompatible_attrs_by_type[component_type]
        common_attrs = @incompatible_attrs_by_type['common']
        (type_attrs && type_attrs.include?(top_level)) ||
          (common_attrs && common_attrs.include?(top_level))
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
        @has_data_definitions = false

        # First pass: collect all data property names and types
        collect_data_properties(json_data)

        # Second pass: validate bindings and collect used properties
        validate_component(json_data)

        # Third pass: check for unused data properties
        check_unused_properties

        @warnings
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

      # Check if there are any warnings
      def has_warnings?
        !@warnings.empty?
      end

      # Print all warnings to stdout
      def print_warnings
        @warnings.each do |warning|
          puts "\e[33m[RJUI Binding Warning]\e[0m #{warning}"
        end
      end

      private

      # Collect all data property names and types from the component tree
      def collect_data_properties(component)
        return unless component.is_a?(Hash)

        # Check for data declarations
        if component['data'].is_a?(Array)
          component['data'].each do |data_item|
            next unless data_item.is_a?(Hash)
            # Skip ViewModel class declarations (class ends with 'ViewModel')
            next if data_item['class'].to_s.end_with?('ViewModel')
            # Add property name and type to the maps
            if data_item['name']
              @data_properties << data_item['name']
              @data_types[data_item['name']] = data_item['class'] if data_item['class']
              @has_data_definitions = true
            end
          end
        end

        # Recurse into children
        children = component['child'] || component['children'] || []
        children = [children] unless children.is_a?(Array)
        children.each do |child|
          next unless child.is_a?(Hash)
          # Check if child is a data-only object (no 'type' key, has 'data' key)
          if child['data'] && !child['type']
            collect_data_from_array(child['data'])
          else
            collect_data_properties(child)
          end
        end

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

      # Helper to collect data from a data array
      def collect_data_from_array(data_array)
        return unless data_array.is_a?(Array)

        data_array.each do |data_item|
          next unless data_item.is_a?(Hash)
          # Skip ViewModel class declarations (class ends with 'ViewModel')
          next if data_item['class'].to_s.end_with?('ViewModel')
          # Add property name to the set
          if data_item['name']
            @data_properties << data_item['name']
            @has_data_definitions = true
          end
        end
      end

      def validate_component(component, parent_type = nil)
        return unless component.is_a?(Hash)

        component_type = component['type'] || parent_type || 'Unknown'

        # Track used properties from include's shared_data and data
        collect_used_from_include(component)

        # Track auto-generated onChange handlers from text/selectedValue bindings
        collect_auto_generated_handlers(component, component_type)

        # Check each attribute for bindings
        component.each do |key, value|
          next if key == 'type' || key == 'child' || key == 'children' || key == 'sections'
          next if key == 'data' || key == 'generatedBy' || key == 'include' || key == 'style' || key == 'shared_data'
          # Skip attributes marked for other platforms (e.g. confirmationDialog is
          # swift-only; its bindings reference SwiftUI-specific state).
          next if incompatible_attr?(component_type, key)

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

            # Check if binding variables are defined in data (only for components with data definitions)
            # Pages/components without data definitions get bindings from ViewModel props
            check_undefined_variables(binding_expr, attribute_name, component_type) if @has_data_definitions

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
        # Skip: numbers, true, false, null, undefined, visible, gone
        keywords = %w[true false null undefined visible gone]

        expr.scan(/\b([a-zA-Z_][a-zA-Z0-9_]*)\b/).flatten.each do |match|
          next if keywords.include?(match)
          next if match =~ /^\d/ # Skip if starts with digit
          variables << match
        end

        variables.to_a
      end

      # Infer type from variable name and attribute context
      # Returns cross-platform type format (works with Swift, Kotlin, React)
      def infer_type(var_name, attribute_name, component_type = nil)
        # onTabChange -> ((Int) -> Void)? (callback with Int parameter)
        return '((Int) -> Void)?' if var_name == 'onTabChange' || attribute_name == 'onTabChange'

        # onClick, onXxx -> (() -> Void)? (cross-platform callback type)
        return '(() -> Void)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> Array
        return 'Array' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Bool
        return 'Bool' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # Based on attribute name
        case attribute_name
        when 'onTabChange'
          '((Int) -> Void)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Void)?'
        when 'items', 'sections'
          'Array'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Bool'
        when 'src', 'srcName'
          # NetworkImage uses URL string, Image/CircleImage uses Image type
          if component_type&.include?('Network')
            'String'
          else
            'Image'
          end
        else
          'any'
        end
      end

      def allowed_pattern?(binding)
        ALLOWED_PATTERNS.any? { |pattern| binding.match?(pattern) }
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

        # Warn if type is String instead of Color
        if declared_type == 'String'
          context = @current_file ? "[#{@current_file}] " : ""
          @warnings << "#{context}'#{component_type}.#{attribute_name}' binding '@{#{binding_expr}}' has type 'String' but should be 'Color'. Change the data declaration to: { \"name\": \"#{var_name}\", \"class\": \"Color\" }"
        end
      end

      # Collect used properties from include's shared_data and data
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

      # Collect auto-generated onChange handler names that converters create from bindings
      # e.g. text: "@{email}" → onEmailChange, selectedValue: "@{carrier}" → onCarrierChange
      def collect_auto_generated_handlers(component, component_type)
        # TextField / TextView: text binding → onXxxChange
        if %w[TextField EditText TextView TextArea TextInput].include?(component_type)
          text = component['text']
          if text.is_a?(String) && text.start_with?('@{') && text.end_with?('}')
            prop = text[2..-2]
            handler = "on#{prop[0].upcase}#{prop[1..]}Change"
            @used_properties << handler if @data_properties.include?(handler)
          end
        end

        # SelectBox: selectedValue/value binding → onXxxChange
        if %w[SelectBox Spinner Picker].include?(component_type)
          value_key = component['selectedValue'] || component['value'] || component['selectedIndex']
          if value_key.is_a?(String) && value_key.start_with?('@{') && value_key.end_with?('}')
            prop = value_key[2..-2]
            handler = "on#{prop[0].upcase}#{prop[1..]}Change"
            @used_properties << handler if @data_properties.include?(handler)
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
    end
  end
end
