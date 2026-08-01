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

      # Canonical binding grammar (shared/core/binding_semantics.json):
      # inner = [!]path [?? default]; path = identifier segments joined by
      # '.' with optional bracket index; default = quoted string ('' or ""),
      # true/false, number, or null.
      FLAT_IDENTIFIER_RE = /\A[a-zA-Z_$][\w$]*\z/
      CANONICAL_PATH_RE = /\A[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[\d+\])*\z/
      CANONICAL_DEFAULT_RE = /\A(?:"[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?)\z/
      CANONICAL_EXPR_RE = /\A!?\s*[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[\d+\])*(?:\s*\?\?\s*(?:"[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?))?\z/

      # Errors are canonical validator-rule violations
      # (binding_semantics.json validatorRules, severity: error); warnings
      # keep the advisory role they always had. Both message streams carry
      # the rule id in the form "[rule-id] ..." when a canonical rule fired.
      attr_reader :warnings, :errors

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
        # NOTE: '?? default' is officially supported (binding SSoT track 15,
        # shared/core/binding_semantics.json defaultOperator) — a single
        # '??' with a literal default is canonical and no longer warned.
        # More than one '??' is the binding-double-default ERROR instead.
        # Function calls with arguments (standalone or chained)
        {
          pattern: /\w+\([^)]+\)/,
          message: "function call with arguments - move to ViewModel"
        },
        # Zero-argument function/method calls (getName(), items.first())
        {
          pattern: /\w+\(\s*\)/,
          message: "function call - move to ViewModel computed property"
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
        }
        # NOTE: '!' negation is canonical on boolean value attributes
        # (@{!flag} emits {!data.flag}); outside a boolean value context it
        # is the binding-negation-context ERROR (see check_canonical_binding_rules).
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
        @errors = []
        @data_properties = Set.new
        @used_properties = Set.new  # Track used properties for unused detection
        @cell_local_properties = Set.new # data declared inside a Collection cell subtree
        @data_types = {} # Store property name -> type mapping
        @has_data_definitions = false
        @cell_depth = 0
        defs = load_attribute_definitions
        @component_alias_by_type = build_component_aliases(defs)
        @incompatible_attrs_by_type = build_incompatible_attrs(defs)
        @two_way_attrs_by_type = build_two_way_attrs(defs)
        @boolean_attrs_by_type = build_boolean_attrs(defs)
        @known_attrs_by_type = build_known_attrs(defs)
      end

      # `_alias_of` pointer sections (EditText/Input -> TextField, Check ->
      # CheckBox, Toggle -> Switch) carry no attribute copies of their own —
      # every per-type table lookup resolves through this map first. One hop
      # only; a pointer to a missing or alias-shaped target is ignored.
      def build_component_aliases(defs)
        out = {}
        defs.each do |component_type, section|
          next unless section.is_a?(Hash)
          target = section['_alias_of']
          next unless target.is_a?(String)
          target_section = defs[target]
          next unless target_section.is_a?(Hash)
          next if target_section['_alias_of'].is_a?(String)
          out[component_type] = target
        end
        out
      end

      def resolve_component_alias(component_type)
        @component_alias_by_type[component_type] || component_type
      end

      # Load attribute_definitions.json (deployed copies mirror the file
      # into lib/core/ alongside this file; source-repo layout keeps the
      # canonical copy at ../../../shared/core/).
      def load_attribute_definitions
        candidates = [
          File.join(File.dirname(__FILE__), 'attribute_definitions.json'),
          File.expand_path('../../../../shared/core/attribute_definitions.json', __FILE__)
        ]
        path = candidates.find { |p| File.exist?(p) }
        return {} unless path

        JSON.parse(File.read(path))
      rescue JSON::ParserError
        {}
      end

      # Per component type, the set of attribute names marked for platforms
      # other than 'react'. Bindings inside these attributes are
      # iOS/Android-only and should be skipped.
      def build_incompatible_attrs(defs)
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
      end

      # Per component type, attribute names declared `binding_direction:
      # "two-way"` (TextField.text, Toggle.isOn, Slider.value, ...). These
      # write back to the binding, so the canonical twoWay context applies:
      # the expression must be a single flat identifier.
      def build_two_way_attrs(defs)
        collect_attrs_by(defs) do |attr_def|
          attr_def['binding_direction'] == 'two-way'
        end
      end

      # Per component type, attribute names whose declared type includes
      # 'boolean' — the only value context where '!' negation is canonical.
      def build_boolean_attrs(defs)
        collect_attrs_by(defs) do |attr_def|
          Array(attr_def['type']).include?('boolean')
        end
      end

      # Per component type, every declared attribute name (used to decide
      # whether a whole-value negation target is a KNOWN non-bool attribute
      # — unknown/custom attributes are left alone to avoid false errors).
      def build_known_attrs(defs)
        collect_attrs_by(defs) { |_attr_def| true }
      end

      def collect_attrs_by(defs)
        result = {}
        defs.each do |component_type, attrs|
          next unless attrs.is_a?(Hash)
          matched = Set.new
          attrs.each do |attr_name, attr_def|
            next unless attr_def.is_a?(Hash)
            next unless yield(attr_def)

            matched << attr_name
            Array(attr_def['aliases']).each { |a| matched << a }
          end
          result[component_type] = matched unless matched.empty?
        end
        result
      end

      def two_way_attr?(component_type, attr_name)
        lookup_attr_set(@two_way_attrs_by_type, component_type, attr_name)
      end

      def boolean_attr?(component_type, attr_name)
        lookup_attr_set(@boolean_attrs_by_type, component_type, attr_name)
      end

      def known_attr?(component_type, attr_name)
        lookup_attr_set(@known_attrs_by_type, component_type, attr_name)
      end

      def lookup_attr_set(table, component_type, attr_name)
        (table[resolve_component_alias(component_type)]&.include?(attr_name)) ||
          (table['common']&.include?(attr_name)) || false
      end

      def incompatible_attr?(component_type, attr_name)
        # Strip nested-path suffix: "confirmationDialog.isPresented" → "confirmationDialog"
        top_level = attr_name.to_s.split('.').first
        type_attrs = @incompatible_attrs_by_type[resolve_component_alias(component_type)]
        common_attrs = @incompatible_attrs_by_type['common']
        (type_attrs && type_attrs.include?(top_level)) ||
          (common_attrs && common_attrs.include?(top_level))
      end

      # Validate all bindings in a JSON component tree
      # @param json_data [Hash] The root component
      # @param file_name [String] The file name for error messages
      # @return [Array<String>] Warnings followed by canonical-rule errors
      def validate(json_data, file_name = nil)
        @warnings = []
        @errors = []
        @current_file = file_name
        @data_properties = Set.new
        @used_properties = Set.new
        @cell_local_properties = Set.new
        @data_types = {}
        @has_data_definitions = false
        @cell_depth = 0

        # First pass: collect all data property names and types
        collect_data_properties(json_data)

        # Second pass: validate bindings and collect used properties
        validate_component(json_data)

        # Third pass: check for unused data properties
        check_unused_properties

        @warnings + @errors
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

        # Canonical binding expressions ([!]path [?? literal]) are never
        # business logic — dot-paths, bracket indices, bool negation and a
        # single '??' default are all official grammar now (binding SSoT
        # track 15). Context violations are reported as canonical rule
        # errors in check_canonical_binding_rules, not here. The
        # viewModel. prefix stays a warning (legacy spelling).
        if binding_expr.strip.match?(CANONICAL_EXPR_RE) &&
           !binding_expr.strip.sub(/\A!\s*/, '').start_with?('viewModel.')
          return warnings
        end

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

      # Check if there are any canonical-rule errors
      def has_errors?
        !@errors.empty?
      end

      # Print all warnings (and canonical-rule errors) to stdout
      def print_warnings
        @warnings.each do |warning|
          puts "\e[33m[RJUI Binding Warning]\e[0m #{warning}"
        end
        @errors.each do |error|
          puts "\e[31m[RJUI Binding Error]\e[0m #{error}"
        end
      end

      private

      # Collect all data property names and types from the component tree.
      # `in_cell` tracks Collection cell subtrees so cell-declared
      # properties can be told apart from parent-screen data (used by the
      # binding-cell-parent-scope rule).
      def collect_data_properties(component, in_cell = false)
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
              @cell_local_properties << data_item['name'] if in_cell
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
            collect_data_from_array(child['data'], in_cell)
          else
            collect_data_properties(child, in_cell)
          end
        end

        # Recurse into sections
        if component['sections'].is_a?(Array)
          component['sections'].each do |section|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              next unless section[key].is_a?(Hash)
              collect_data_properties(section[key], in_cell || key == 'cell')
            end
          end
        end
      end

      # Helper to collect data from a data array
      def collect_data_from_array(data_array, in_cell = false)
        return unless data_array.is_a?(Array)

        data_array.each do |data_item|
          next unless data_item.is_a?(Hash)
          # Skip ViewModel class declarations (class ends with 'ViewModel')
          next if data_item['class'].to_s.end_with?('ViewModel')
          # Add property name to the set
          if data_item['name']
            @data_properties << data_item['name']
            @cell_local_properties << data_item['name'] if in_cell
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
        collect_partial_attribute_handlers(component)

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

        # Validate sections (Collection/Table). Cell subtrees run with the
        # cell-scope flag so binding-cell-parent-scope can fire; header /
        # footer render in parent scope and are exempt.
        if component['sections'].is_a?(Array)
          component['sections'].each do |section|
            next unless section.is_a?(Hash)
            ['header', 'footer', 'cell'].each do |key|
              next unless section[key].is_a?(Hash)
              if key == 'cell'
                @cell_depth += 1
                validate_component(section[key], component_type)
                @cell_depth -= 1
              else
                validate_component(section[key], component_type)
              end
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
          if value.include?('@{')
            # Canonical binding-resolution rules (errors) run on every
            # occurrence, including mixed-text interpolation.
            check_canonical_binding_rules(value, attribute_name, component_type)
            check_cell_parent_scope(value, attribute_name, component_type)
          end

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
          # Arrays are unsupported anywhere inside Embed params
          # (binding-params-array — embed isolated+params track).
          if embed_params_attr?(component_type, attribute_name)
            add_error('binding-params-array',
                      "'#{component_type}.#{attribute_name}' is an array — arrays are not supported in Embed params (nest literal objects or bind a scalar leaf)")
          end
          value.each_with_index do |item, index|
            check_value_for_bindings(item, "#{attribute_name}[#{index}]", component_type)
          end
        end
      end

      # Canonical validator rules from shared/core/binding_semantics.json
      # (renderer SSoT track 15). Rule ids are embedded in the emitted
      # messages so tooling and the shared vector suite can match them.
      def check_canonical_binding_rules(value, attribute_name, component_type)
        exprs = value.scan(/@\{([^}]*)\}/).flatten
        return if exprs.empty?

        top_attr = attribute_name.to_s.split(/[.\[]/).first
        embed_params = embed_params_attr?(component_type, attribute_name)
        two_way = !embed_params && two_way_attr?(component_type, top_attr)
        whole_value = exprs.length == 1 && value.strip == "@{#{exprs.first}}"

        exprs.each do |inner|
          expr = inner.strip

          # binding-double-default: exactly one '??' per expression
          if expr.scan(/\?\?/).length > 1
            add_error('binding-double-default',
                      "Binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' uses '??' more than once — exactly one default is allowed. Split the fallback chain in the ViewModel.")
          end

          # binding-two-way-complex: two-way bindings write back, so the
          # expression must be a single flat identifier — no '.', '[',
          # '??', '!' and no surrounding text.
          if two_way
            unless whole_value && expr.match?(FLAT_IDENTIFIER_RE)
              add_error('binding-two-way-complex',
                        "Two-way binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' must be a single flat identifier (no '.', '[', '??', '!'). Bind a flat property and derive the value in the ViewModel.")
            end
            next
          end

          if embed_params
            if expr.start_with?('!')
              add_error('binding-negation-context',
                        "Binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' uses '!' negation in an Embed params leaf — negation is only valid on boolean value attributes. Compute the negated flag in the ViewModel.")
            elsif expr.include?('??')
              add_error('binding-default-in-params',
                        "Binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' uses a '??' default in an Embed params leaf — defaults belong to the embedded screen's data-section defaultValue.")
            end
            next
          end

          # binding-negation-context: '!' is canonical only as the whole
          # value of a boolean attribute. Unknown/custom attributes are
          # left alone (their type cannot be established here).
          next unless expr.start_with?('!')

          if !whole_value
            add_error('binding-negation-context',
                      "Binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' uses '!' negation inside text interpolation — negation is only valid as the whole value of a boolean attribute. Compute the negated flag in the ViewModel.")
          elsif known_attr?(component_type, top_attr) && !boolean_attr?(component_type, top_attr)
            add_error('binding-negation-context',
                      "Binding '@{#{expr}}' in '#{component_type}.#{attribute_name}' uses '!' negation on a non-boolean attribute — negation is only valid on boolean value attributes (e.g. hidden, enabled). Compute the negated flag in the ViewModel.")
          end
        end
      end

      # binding-cell-parent-scope (warning): a Collection cell layout is
      # guaranteed only the item's own fields (data.-prefixed in rjui cell
      # convention) plus the reserved 'index'. Binding a bare key that is
      # declared in the parent screen's data section is non-portable.
      # Only inline `sections` cells are detectable here — cell layouts in
      # separate files are validated standalone, without parent data context.
      def check_cell_parent_scope(value, attribute_name, component_type)
        return unless @cell_depth > 0

        value.scan(/@\{([^}]*)\}/).flatten.each do |inner|
          expr = inner.strip
          expr = expr[1..].to_s.strip if expr.start_with?('!')
          path = expr.split(/\s*\?\?\s*/, 2).first.to_s
          next if path.start_with?('data.')

          root = path.split(/[.\[]/).first.to_s
          next if root.empty? || root == 'index'
          next if @cell_local_properties.include?(root)
          next unless @data_properties.include?(root)

          add_rule_warning('binding-cell-parent-scope',
                           "Cell binding '@{#{inner.strip}}' in '#{component_type}.#{attribute_name}' depends on parent-screen data key '#{root}' — cell scope guarantees only the item's own fields plus 'index'. Pass the value through the item data instead.")
        end
      end

      def embed_params_attr?(component_type, attribute_name)
        component_type == 'Embed' && attribute_name.to_s.split(/[.\[]/).first == 'params'
      end

      def add_error(rule_id, message)
        context = @current_file ? "[#{@current_file}] " : ""
        entry = "#{context}[#{rule_id}] #{message}"
        @errors << entry unless @errors.include?(entry)
      end

      def add_rule_warning(rule_id, message)
        context = @current_file ? "[#{@current_file}] " : ""
        entry = "#{context}[#{rule_id}] #{message}"
        @warnings << entry unless @warnings.include?(entry)
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

        # Match variable references. A dotted/indexed path (user.name, items[0].title)
        # counts as its root variable only — data defines the root, not each segment.
        # Skip: numbers, true, false, null, undefined, visible, gone
        keywords = %w[true false null undefined visible gone]

        expr.scan(/\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*/).each do |match|
          root = match.split(/[.\[]/).first
          next if keywords.include?(root)
          next if root =~ /^\d/ # Skip if starts with digit
          variables << root
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

      # A handler named by a partialAttributes entry IS a use.
      #
      # These are ordinary handler references, just nested one level deeper
      # than the node's own onclick, and the scan never descended into them.
      # A consumer who declared the handler got "defined but never used";
      # one who omitted it got a generated Data type without the property.
      # There was no spelling that satisfied both, so the zero-warning gate
      # made partial handlers unusable.
      def collect_partial_attribute_handlers(component)
        partials = component['partialAttributes']
        return unless partials.is_a?(Array)

        partials.each do |partial|
          next unless partial.is_a?(Hash)

          %w[onclick onClick].each do |key|
            handler = partial[key]
            next unless handler.is_a?(String) && !handler.empty?

            if handler.start_with?('@{') && handler.end_with?('}')
              extract_variables(handler[2..-2]).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            elsif @data_properties.include?(handler)
              @used_properties << handler
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
