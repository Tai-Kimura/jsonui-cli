#!/usr/bin/env ruby

require 'json'

module SjuiTools
  module Core
    # Validates binding expressions in JSON layouts.
    # Enforces the canonical validatorRules from
    # shared/core/binding_semantics.json (rule ids appear verbatim in the
    # emitted messages) and warns when bindings contain business logic that
    # should be in ViewModel.
    class BindingValidator
      attr_reader :warnings
      # Error-severity canonical rule violations (subset of the messages
      # returned by #validate; kept separately so callers can escalate)
      attr_reader :errors

      # Patterns that indicate business logic in bindings
      BUSINESS_LOGIC_PATTERNS = [
        # Ternary operators
        {
          pattern: /\?.*:/,
          message: "ternary operator (?:) - move condition logic to ViewModel"
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
        # NOTE: nil coalescing (??) is NOT flagged here — '@{path ?? default}'
        # is officially supported (shared/core/binding_semantics.json). The
        # canonical validator rules below enforce its grammar instead.
        # Method calls with arguments (but allow simple property access)
        {
          pattern: /\.\w+\([^)]+\)/,
          message: "method call with arguments - move to ViewModel"
        },
        # Zero-argument function/method calls (getName(), items.first())
        {
          pattern: /\w+\(\s*\)/,
          message: "method call - move to ViewModel computed property"
        },
        # String interpolation
        {
          pattern: /\\?\$\{|\\\(/,
          message: "string interpolation - compose string in ViewModel"
        },
        # Array subscript with complex expression
        {
          pattern: /\[[^\]]*[+\-*\/<>=]/,
          message: "complex array subscript - simplify in ViewModel"
        },
        # Casting/type conversion
        {
          pattern: /\s+as[?\s!]+\w+/,
          message: "type casting - handle type conversion in ViewModel"
        },
        # Force unwrap
        {
          pattern: /[^?]!/,
          message: "force unwrap (!) - handle optionals safely in ViewModel"
        },
        # Closures/lambdas (complex)
        {
          pattern: /\{[^}]*(?:in|->)[^}]*\}/,
          message: "closure/lambda - move to ViewModel"
        },
        # Range operators
        {
          pattern: /\.\.\.|\.\.</,
          message: "range operator - create range in ViewModel"
        },
        # Prefix/postfix operators
        {
          pattern: /\+\+|--/,
          message: "increment/decrement - update value in ViewModel"
        }
        # NOTE: '!' negation is no longer a blanket warning — '@{!path}' is
        # canonical in boolean value contexts; other contexts get the
        # binding-negation-context error from the canonical rules below.
      ].freeze

      # Canonical path: identifier segments joined by '.', optional bracket
      # index per segment (items[0].title) — shared/core/binding_semantics.json
      CANONICAL_PATH = /[a-zA-Z_][a-zA-Z0-9_]*(\[\d+\])?(\.[a-zA-Z_][a-zA-Z0-9_]*(\[\d+\])?)*/
      # Canonical default literal: "str" | 'str' | true | false | null | number
      CANONICAL_DEFAULT = /("[^"]*"|'[^']*'|true|false|null|-?\d+(\.\d+)?)/
      # Two-way bindings must be a single flat identifier
      FLAT_IDENTIFIER = /\A[a-zA-Z_][a-zA-Z0-9_]*\z/

      # Allowed simple patterns that look like logic but are acceptable
      ALLOWED_PATTERNS = [
        # Simple property access (including optional chaining)
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*(\?)?\.?[a-zA-Z_][a-zA-Z0-9_]*\}$/,
        # Simple array access with constant index
        /^@\{[a-zA-Z_][a-zA-Z0-9_]*\[\d+\]\}$/,
        # Action bindings (callbacks)
        /^@\{on[A-Z][a-zA-Z0-9_]*\}$/,
        # data. prefix for accessing data properties (e.g., @{data.name} in Collection cells)
        /^@\{data\.[a-zA-Z_][a-zA-Z0-9_.]*\}$/,
        # Canonical '??' default: @{path ?? literal} (single default only —
        # arity is enforced by the binding-double-default rule)
        /^@\{\s*#{CANONICAL_PATH.source}\s*\?\?\s*#{CANONICAL_DEFAULT.source}\s*\}$/,
        # Canonical negation: @{!path} (context is enforced by the
        # binding-negation-context rule)
        /^@\{\s*!\s*#{CANONICAL_PATH.source}\s*\}$/
      ].freeze

      def initialize
        @warnings = []
        @errors = []
        @in_cell_context = false
        @data_properties = Set.new
        @cell_data_properties = Set.new  # Properties declared inside section cells
        @used_properties = Set.new  # Track used properties for unused detection
        @data_types = {} # Store property name -> type mapping
        @current_file = nil
        @current_view_id = nil
        @current_view_type = nil
        @current_hierarchy = nil
        @attribute_definitions = load_attribute_definitions
        @my_platform = 'swift'
        @my_mode = 'swiftui'
      end

      # Validate all bindings in a JSON component tree
      # @param json_data [Hash] The root component
      # @param file_name [String] The file name for error messages
      # @return [Array<String>] Array of warning messages
      def validate(json_data, file_name = nil)
        @warnings = []
        @errors = []
        @in_cell_context = false
        @current_file = file_name
        @data_properties = Set.new
        @cell_data_properties = Set.new
        @used_properties = Set.new
        @data_types = {}

        # First pass: collect all data property names and types
        collect_data_properties(json_data)

        # Second pass: validate bindings and collect used properties (root component is marked as is_root: true)
        validate_component(json_data, nil, is_root: true)

        # Third pass: check for unused data properties
        check_unused_properties

        @warnings
      end

      # Check if there are any warnings
      def has_warnings?
        !@warnings.empty?
      end

      # Check if there are any error-severity canonical rule violations
      def has_errors?
        !@errors.empty?
      end

      # Print all warnings to stdout
      def print_warnings
        @warnings.each do |warning|
          puts "\e[33m⚠️  [SJUI Warning] #{warning}\e[0m"
        end
      end

      # Check a single binding expression
      # @param binding_expr [String] The binding expression (without @{ })
      # @param attribute_name [String] The attribute name
      # @param component_type [String] The component type
      # @param mixed_text [Boolean] true when the binding occurs inside mixed
      #   text (interpolation context) rather than as the whole value
      # @return [Array<String>] Array of warning messages
      def check_binding(binding_expr, attribute_name, component_type, mixed_text: false)
        warnings = []

        # Canonical validator rules run first — they apply even to
        # expressions the business-logic allowlist would wave through
        warnings.concat(check_canonical_rules(binding_expr, attribute_name, component_type, mixed_text: mixed_text))

        # Check if it's allowed simple pattern
        full_binding = "@{#{binding_expr}}"
        return warnings if allowed_pattern?(full_binding)

        # Check for business logic patterns
        BUSINESS_LOGIC_PATTERNS.each do |rule|
          if binding_expr.match?(rule[:pattern])
            warnings << "#{build_context_prefix}Binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' contains #{rule[:message]}"
          end
        end

        warnings
      end

      # Canonical validatorRules from shared/core/binding_semantics.json.
      # Rule ids appear verbatim in the emitted messages; error-severity
      # violations are also recorded in #errors.
      def check_canonical_rules(binding_expr, attribute_name, component_type, mixed_text: false)
        messages = []
        expr = binding_expr.strip

        # binding-double-default (error, any context): more than one '??'
        if expr.scan('??').length >= 2
          messages << canonical_error("binding-double-default",
            "Binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' has more than one '??' — exactly one default per expression.")
        end

        if two_way_attribute?(component_type, attribute_name)
          # binding-two-way-complex (error): must be a single flat identifier
          unless expr.match?(FLAT_IDENTIFIER)
            messages << canonical_error("binding-two-way-complex",
              "Two-way binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' must be a single flat identifier (no '.', '[', '??', '!').")
          end
        elsif expr.start_with?('!')
          # binding-negation-context (error): '!' is only valid in boolean
          # value contexts. Mixed text is always a text context; whole-value
          # usage is invalid when the attribute is not boolean-typed.
          if mixed_text || non_boolean_value_attribute?(component_type, attribute_name)
            messages << canonical_error("binding-negation-context",
              "Negation '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' is only valid in boolean value contexts.")
          end
        end

        messages
      end

      private

      # Collect all data property names and types from the component tree
      def collect_data_properties(component, in_cell: false)
        return unless component.is_a?(Hash)

        # Check for data declarations
        if component['data'].is_a?(Array)
          component['data'].each do |data_item|
            next unless data_item.is_a?(Hash)
            # Platform/mode filter
            next if data_item['platform'] && data_item['platform'] != 'swift'
            next if data_item['mode'] && data_item['mode'] != 'swiftui'
            # Skip ViewModel class declarations (they have 'class' key but no 'name')
            # e.g., { "class": "MyViewModel" } - this is a ViewModel class, not a property
            # But include property declarations: { "name": "userName", "class": "String" }
            next if data_item['class'] && !data_item['name']
            # Add property name and type to the maps
            if data_item['name']
              @data_properties << data_item['name']
              @cell_data_properties << data_item['name'] if in_cell
              @data_types[data_item['name']] = data_item['class'] if data_item['class']
            end
          end
        end

        # Recurse into children
        children = component['child'] || component['children'] || []
        children = [children] unless children.is_a?(Array)
        children.each { |child| collect_data_properties(child, in_cell: in_cell) if child.is_a?(Hash) }

        # Recurse into sections
        if component['sections'].is_a?(Array)
          component['sections'].each do |section|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              next unless section[key].is_a?(Hash)
              collect_data_properties(section[key], in_cell: in_cell || key == 'cell')
            end
          end
        end
      end

      def validate_component(component, parent_type = nil, is_root: false, hierarchy: nil)
        return unless component.is_a?(Hash)

        component_type = component['type'] || parent_type || 'Unknown'
        has_id = component.key?('id') || component.key?('binding_id')
        @current_view_id = component['id'] || component['binding_id']
        @current_view_type = component['type'] || (component['include'] ? "include:#{component['include']}" : nil)
        @current_hierarchy = hierarchy

        # Track used properties from include's shared_data and data
        collect_used_from_include(component)

        # Embed-specific structural rules (params tree grammar + navigationMode)
        validate_embed_component(component) if component_type == 'Embed'

        # Check each attribute for bindings
        component.each do |key, value|
          next if key == 'type' || key == 'child' || key == 'children' || key == 'sections'
          next if key == 'data' || key == 'generatedBy' || key == 'include' || key == 'style' || key == 'shared_data'
          next if key == 'bindingScript' # bindingScript allows arbitrary Swift code, skip validation
          next if attribute_excluded_for_platform?(component_type, key)

          check_value_for_bindings(value, key, component_type)

          # Check for binding on component without id (UIKit mode issue)
          # Skip 'id' attribute itself
          # Root component also needs id for onClick bindings (generates click handler code)
          next if key == 'id'
          if has_binding?(value) && !has_id
            check_binding_without_id(value, key, component_type)
          end
        end

        # Validate children
        children = component['child'] || component['children'] || []
        children = [children] unless children.is_a?(Array)
        children.each_with_index do |child, index|
          next unless child.is_a?(Hash)
          child_hierarchy = hierarchy ? "#{hierarchy}.child[#{index}]" : "child[#{index}]"
          validate_component(child, component_type, is_root: false, hierarchy: child_hierarchy)
        end

        # Validate sections (Collection/Table)
        if component['sections'].is_a?(Array)
          component['sections'].each_with_index do |section, section_index|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              next unless section[key].is_a?(Hash)
              section_hierarchy = hierarchy ? "#{hierarchy}.sections[#{section_index}].#{key}" : "sections[#{section_index}].#{key}"
              # Cell subtrees resolve against the item's own fields (flat) +
              # 'index' — parent-screen data is NOT guaranteed there
              # (binding-cell-parent-scope)
              previous_cell_context = @in_cell_context
              @in_cell_context = true if key == 'cell'
              validate_component(section[key], component_type, is_root: false, hierarchy: section_hierarchy)
              @in_cell_context = previous_cell_context
            end
          end
        end
      end

      # Check if a value contains a binding expression
      def has_binding?(value)
        case value
        when String
          value.start_with?('@{') && value.end_with?('}')
        when Hash
          value.values.any? { |v| has_binding?(v) }
        when Array
          value.any? { |v| has_binding?(v) }
        else
          false
        end
      end

      # Warn about binding on component without id
      def check_binding_without_id(value, attribute_name, component_type)
        binding_expr = value.is_a?(String) ? value : value.to_s
        @warnings << "#{build_context_prefix}'#{component_type}.#{attribute_name}' has binding '#{binding_expr}' but component has no 'id'. In UIKit mode, bindings require an id to reference the view."
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
          elsif value.include?('@{')
            # Mixed-text interpolation: apply the canonical rules to each
            # '@{...}' occurrence (text context)
            value.scan(/@\{([^}]+)\}/).flatten.each do |inner|
              @warnings.concat(check_canonical_rules(inner, attribute_name, component_type, mixed_text: true))
            end
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

          if @in_cell_context
            # binding-cell-parent-scope (warning): a cell binding that only
            # resolves against the parent screen's data section is
            # non-portable — cell scope guarantees the item's own fields
            # (flat) plus 'index' only.
            if @data_properties.include?(var) && !@cell_data_properties.include?(var)
              @warnings << "#{build_context_prefix}[binding-cell-parent-scope] Cell binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' refers to parent screen data property '#{var}' — cell scope only guarantees the item's own fields and 'index'."
            end
            # Item fields are unknowable statically — skip the undefined check
            next
          end

          unless @data_properties.include?(var)
            @warnings << "#{build_context_prefix}Binding variable '#{var}' in '#{component_type}.#{attribute_name}' is not defined in data. Add: { \"class\": \"#{infer_type(var, attribute_name, component_type)}\", \"name\": \"#{var}\" }"
          end
        end
      end

      # Extract variable names from binding expression
      def extract_variables(binding_expr)
        variables = Set.new

        # Remove string literals to avoid false positives
        expr = binding_expr.gsub(/'[^']*'/, '').gsub(/"[^"]*"/, '')

        # Match variable names (identifiers that are not keywords or literals)
        # Skip: numbers, true, false, nil, null, visible, gone, and the
        # reserved cell-scope key 'index'
        keywords = %w[true false nil null visible gone index]

        expr.scan(/\b([a-zA-Z_][a-zA-Z0-9_]*)\b/).flatten.each do |match|
          next if keywords.include?(match)
          next if match =~ /^\d/ # Skip if starts with digit
          variables << match
        end

        variables.to_a
      end

      # Infer type from variable name and attribute context
      # Returns Swift type format
      def infer_type(var_name, attribute_name, component_type = nil)
        # confirmationDialog.actions -> (() -> AnyView)? (SwiftUI callback returning Button views)
        return '(() -> AnyView)?' if attribute_name == 'confirmationDialog.actions'

        # Callbacks with Int parameter
        return '((Int) -> Void)?' if %w[onTabChange onItemAppear].include?(var_name) || %w[onTabChange onItemAppear].include?(attribute_name)

        # TextField/TextView event handlers with UITextField/UITextView parameter
        text_field_events = %w[onBeginEditing onEndEditing onTextChange onDeleteBackward onChangeSelection]
        text_field_bool_events = %w[onShouldReturn onShouldClear onShouldBeginEditing onShouldEndEditing]
        text_field_change_events = %w[onShouldChangeCharacters]
        text_view_change_events = %w[onShouldChangeText]

        return '((UITextField) -> Void)?' if text_field_events.include?(var_name) || text_field_events.include?(attribute_name)
        return '((UITextField) -> Bool)?' if text_field_bool_events.include?(var_name) || text_field_bool_events.include?(attribute_name)
        return '((UITextField, NSRange, String) -> Bool)?' if text_field_change_events.include?(var_name) || text_field_change_events.include?(attribute_name)
        return '((UITextView, NSRange, String) -> Bool)?' if text_view_change_events.include?(var_name) || text_view_change_events.include?(attribute_name)

        # onClick, onXxx -> (() -> Void)? (Swift callback type)
        return '(() -> Void)?' if var_name.start_with?('on') && var_name[2]&.match?(/[A-Z]/)

        # xxxItems, xxxOptions, xxxList -> [Any]
        return '[Any]' if var_name.end_with?('Items', 'Options', 'List', 'Args', 'Subcommands')

        # isXxx, hasXxx, canXxx, shouldXxx -> Bool
        return 'Bool' if var_name.start_with?('is', 'has', 'can', 'should')

        # xxxVisibility -> String
        return 'String' if var_name.end_with?('Visibility')

        # xxxIndex, xxxCount, xxxTab -> Int
        return 'Int' if var_name.end_with?('Index', 'Count', 'Tab')

        # xxxMargin, xxxPadding -> CGFloat
        return 'CGFloat' if var_name.end_with?('Margin', 'Padding')

        # Based on attribute name
        case attribute_name
        when 'onTabChange', 'onItemAppear'
          '((Int) -> Void)?'
        when 'onClick', 'onValueChanged', 'onValueChange', 'onTap'
          '(() -> Void)?'
        when 'items'
          'CollectionDataSource'
        when 'sections'
          '[Any]'
        when 'visibility', 'text', 'fontColor', 'background'
          'String'
        when 'selectedIndex', 'width', 'height'
          'Int'
        when 'hidden', 'enabled', 'disabled'
          'Bool'
        when 'topMargin', 'bottomMargin', 'leftMargin', 'rightMargin', 'startMargin', 'endMargin'
          'CGFloat'
        when 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight', 'paddingStart', 'paddingEnd'
          'CGFloat'
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

      # Build context prefix with file name and view id (or hierarchy + type if no id)
      def build_context_prefix
        parts = []
        parts << @current_file if @current_file
        if @current_view_id
          parts << "id=#{@current_view_id}"
        elsif @current_hierarchy || @current_view_type
          # No id - show hierarchy and type instead
          location = [@current_hierarchy, @current_view_type].compact.join(' ')
          parts << location unless location.empty?
        end
        parts.empty? ? "" : "[#{parts.join(' ')}] "
      end

      # Check if visibility attribute is using Boolean instead of String enum
      # Valid values: "visible", "gone", "invisible"
      # Invalid: true, false, @{booleanProperty}
      def check_visibility_type(value, attribute_name, component_type)
        return unless attribute_name == 'visibility'

        # Check for literal boolean values
        if value == true || value == false || value == 'true' || value == 'false'
          @warnings << "#{build_context_prefix}'#{component_type}.visibility' should use String enum (\"visible\", \"gone\", \"invisible\"), not Boolean. Use a String property in data section with visibility values."
          return
        end

        # Check for binding to boolean property (isXxx, hasXxx, etc.)
        if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
          binding_expr = value[2..-2]
          # Check if binding name suggests boolean (isXxx, hasXxx, canXxx, shouldXxx)
          if binding_expr.match?(/^(is|has|can|should)[A-Z]/)
            @warnings << "#{build_context_prefix}'#{component_type}.visibility' binding '@{#{binding_expr}}' appears to be Boolean. Use String property with values: \"visible\", \"gone\", or \"invisible\"."
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
        # Only warn for clearly wrong types (not String, not Color)
        if declared_type != 'String' && declared_type != 'Color' && !declared_type.nil?
          @warnings << "#{build_context_prefix}'#{component_type}.#{attribute_name}' binding '@{#{binding_expr}}' has type '#{declared_type}' but should be 'Color' or 'String'."
        end
      end

      # Collect used properties and validate bindings from include's shared_data and data
      # Embed structural rules (v1.5 nested params + isolated):
      # - params is a tree: intermediate nodes are literal objects only,
      #   @{} bindings may appear only at leaf scalar positions. Binding a
      #   whole subtree (a dict-typed VM property) is rejected — reactivity
      #   semantics for subtree bindings can't be guaranteed cross-platform.
      # - arrays are unsupported anywhere in params.
      # - keys must be camelCase at every level.
      # - navigationMode must be a known enum value ('delegate'/'isolated').
      def validate_embed_component(component)
        mode = component['navigationMode']
        if mode.is_a?(String) && !%w[delegate isolated].include?(mode)
          @warnings << "#{build_context_prefix}'Embed.navigationMode' has unknown value '#{mode}'. Supported: 'delegate', 'isolated'."
        end

        params = component['params']
        validate_embed_params_node(params, 'params') if params.is_a?(Hash)
      end

      def validate_embed_params_node(node, path)
        node.each do |key, value|
          key_path = "#{path}.#{key}"
          unless key.match?(/\A[a-z][a-zA-Z0-9]*\z/)
            @warnings << "#{build_context_prefix}'Embed.#{key_path}' key must be camelCase (at every nesting level)."
          end
          case value
          when Hash
            validate_embed_params_node(value, key_path)
          when Array
            @warnings << canonical_error("binding-params-array",
              "'Embed.#{key_path}' is an array — arrays are not supported in Embed params. Nest literal objects or bind a scalar leaf instead.")
          when String
            if value.start_with?('@{') && value.end_with?('}')
              inner = value[2..-2].strip
              # (binding-double-default for params leaves is covered by the
              # generic attribute traversal — not duplicated here)

              # binding-default-in-params (error): '??' defaults belong to
              # the embedded screen's data section, not to params leaves
              if inner.include?('??')
                @warnings << canonical_error("binding-default-in-params",
                  "'??' default in Embed params leaf '#{key_path}' — defaults belong to the embedded screen's data section (defaultValue).")
              end

              # binding-negation-context (error): '!' is not valid in
              # embedParams context
              if inner.start_with?('!')
                @warnings << canonical_error("binding-negation-context",
                  "Negation '@{#{inner}}' in Embed params leaf '#{key_path}' is only valid in boolean value contexts.")
              end

              prop = value[2..-2]
              type = @data_types[prop]
              if type.is_a?(String) && type.match?(/\[\s*String\s*:|Dictionary\s*</)
                @warnings << "#{build_context_prefix}'Embed.#{key_path}' binds dict-typed property '#{prop}' — bindings are leaf-only in Embed params (bind scalar leaves; intermediate nodes must be literal objects)."
              end
            end
          end
        end
      end

      def collect_used_from_include(component)
        # Only process include elements (elements with 'include' key)
        return unless component.key?('include')

        component_type = "include:#{component['include']}"

        # Check shared_data (values passed to included component)
        # Note: include's shared_data should only contain simple property references, not complex expressions
        if component['shared_data'].is_a?(Hash)
          component['shared_data'].each do |key, value|
            next unless value.is_a?(String)
            # Value can be a direct property name or a binding expression
            if value.start_with?('@{') && value.end_with?('}')
              binding_expr = value[2..-2]
              # Check for complex expressions (ternary, comparison, method calls with arguments)
              if complex_binding_expression?(binding_expr)
                @warnings << "#{build_context_prefix}'#{component_type}.shared_data.#{key}' contains complex expression '@{#{binding_expr}}'. Include's shared_data should only contain simple property references (e.g., '@{propertyName}')."
                # Skip undefined variable check for complex expressions (causes false positives)
              else
                # Only validate undefined variables for simple expressions
                check_undefined_variables(binding_expr, "shared_data.#{key}", component_type)
              end
            else
              # Direct property name reference
              @used_properties << value if @data_properties.include?(value)
            end
          end
        end

        # Check data (values passed to included component for invalidateAll)
        # Note: include's data should only contain simple property references, not complex expressions
        if component['data'].is_a?(Hash)
          component['data'].each do |key, value|
            next unless value.is_a?(String)
            # Value can be a direct property name or a binding expression
            if value.start_with?('@{') && value.end_with?('}')
              binding_expr = value[2..-2]
              # Check for complex expressions (ternary, comparison, method calls with arguments)
              # include's data is for invalidateAll and should be simple property references
              if complex_binding_expression?(binding_expr)
                @warnings << "#{build_context_prefix}'#{component_type}.data.#{key}' contains complex expression '@{#{binding_expr}}'. Include's data should only contain simple property references (e.g., '@{propertyName}') for invalidateAll."
                # Skip undefined variable check for complex expressions (causes false positives)
              else
                # Only validate undefined variables for simple expressions
                check_undefined_variables(binding_expr, "data.#{key}", component_type)
              end
            else
              # Direct property name reference
              @used_properties << value if @data_properties.include?(value)
            end
          end
        end
      end

      # Check if binding expression is complex (not a simple property reference)
      # Simple: propertyName, object.property
      # Complex: ternary (?:), comparison (==, !=, <, >), method calls with args, arithmetic
      def complex_binding_expression?(expr)
        # Check for ternary operator
        return true if expr.include?('?') && expr.include?(':')
        # Check for comparison operators
        return true if expr.match?(/[=!<>]=?/)
        # Check for method calls with arguments (parentheses with content)
        return true if expr.match?(/\([^)]+\)/)
        # Check for arithmetic operators
        return true if expr.match?(/[+\-*\/%]/)
        # Check for logical operators
        return true if expr.match?(/&&|\|\|/)
        false
      end

      # Check for unused data properties and warn
      def check_unused_properties
        unused = @data_properties - @used_properties

        unused.each do |prop|
          @warnings << "[#{@current_file}] Data property '#{prop}' is defined but never used in bindings, shared_data, or data."
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

      # Record an error-severity canonical rule violation and return its
      # message (rule id appears verbatim for machine matching)
      def canonical_error(rule_id, detail)
        message = "#{build_context_prefix}[#{rule_id}] #{detail}"
        @errors << message
        message
      end

      # Look up an attribute definition for [component_type, 'common']
      def attribute_definition(component_type, attr_name)
        [component_type, 'common'].each do |type_key|
          component_defs = @attribute_definitions[type_key]
          next unless component_defs.is_a?(Hash)
          attr_def = component_defs[attr_name]
          return attr_def if attr_def.is_a?(Hash)
        end
        nil
      end

      # Two-way attributes (TextField text, Switch isOn, ...) carry
      # binding_direction: "two-way" in attribute_definitions.json
      def two_way_attribute?(component_type, attr_name)
        attr_def = attribute_definition(component_type, attr_name)
        !!(attr_def && attr_def['binding_direction'] == 'two-way')
      end

      # True when the attribute is known and NOT boolean-typed (negation is
      # canonical only in boolean value contexts). Unknown attributes return
      # false — be lenient rather than false-positive.
      def non_boolean_value_attribute?(component_type, attr_name)
        attr_def = attribute_definition(component_type, attr_name)
        return false unless attr_def
        types = Array(attr_def['type'])
        !types.include?('boolean')
      end

      # Check if an attribute is excluded for the current platform/mode
      # by looking up the component type's attribute definition
      def attribute_excluded_for_platform?(component_type, attr_name)
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
          return false
        end
        false
      end
    end
  end
end
