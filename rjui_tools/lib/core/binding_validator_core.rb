#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'
require 'set'

module JsonUIShared
  # Validates binding expressions in JSON layouts. Shared body of the three
  # toolchain BindingValidators — canonical copy lives in
  # shared/core/binding_validator_core.rb; the per-tool copies under
  # <tool>/lib/core/ must stay byte-identical (pinned by each tool's
  # shared_core_mirror_spec).
  #
  # Enforces the canonical validatorRules from
  # shared/core/binding_semantics.json — rule ids appear verbatim in the
  # emitted messages so tooling and the shared binding_vectors.json
  # validation cases can match on them. Advisory business-logic warnings
  # (move it to the ViewModel) ride alongside; their pattern lists are
  # per-language and injected by the profile.
  #
  # Platform hooks (implemented by the per-tool subclass):
  #
  #   platform_id                     'swift' / 'kotlin' / 'react'
  #   log_tag                         'SJUI' / 'KJUI' / 'RJUI'
  #   data_item_applies?(item)        data[] platform/mode filter
  #   business_logic_patterns         per-language advisory pattern list
  #   extra_allowed_patterns          per-language additions to the
  #                                   business-logic allowlist
  #   infer_type(var, attr, type)     per-platform type spelling for the
  #                                   "add this to data" suggestion
  #   map_typed_class?(class_str)     dict/map-typed data class detection
  #                                   for the Embed leaf-only rule
  #   warn_binding_without_id?        UIKit-era "binding needs an id" advisory
  #   skip_undefined_without_data_section?
  #                                   react components without a data section
  #                                   take props from the ViewModel
  #   collect_platform_used_properties(component, type)
  #                                   extra used-property sources (react's
  #                                   auto-generated onXxxChange handlers and
  #                                   partialAttributes onclick handlers)
  #
  # Unified 2026-08-02 (W3-2, file 5). The architecture follows rjui
  # (attribute tables prebuilt from the SSoT, canonical rules applied to
  # every @{...} occurrence including mixed text); divergences resolved
  # toward the correct side:
  #   - warning context prefixes ([file id=x] / hierarchy) — was sjui-only
  #   - the Embed grammar (navigationMode enum, camelCase keys, arrays,
  #     '??' defaults, negation, map-typed leaf bindings) runs identically
  #     everywhere — rjui had no navigationMode/camelCase checks, and the
  #     transitional attribute_validator flag from W3-2 file 1 retires
  #   - variable extraction counts a dotted/indexed path as its ROOT only
  #     (rjui semantics) — sjui/kjui warned "not defined in data" for every
  #     path SEGMENT (@{user.name} produced a bogus warning about 'name')
  #   - the '??' arity check strips string literals first (kjui semantics)
  #     so a default containing '??' cannot false-positive
  #   - color-attribute bindings accept String-typed properties (sjui/kjui
  #     semantics, matching the SSoT color type string|binding) — rjui's
  #     "should be Color" warning contradicted the SSoT
  #   - cell scope tracks cell-declared data separately (sjui/rjui) so a
  #     property redeclared inside the cell never fires
  #     binding-cell-parent-scope — kjui lacked the refinement
  #   - include shared_data/data complex-expression advisory (sjui) runs
  #     everywhere; extraction keywords are the cross-language union
  class BindingValidatorCore
    attr_reader :warnings
    # Error-severity canonical rule violations. Kept separate from the
    # advisory warnings; #validate returns both streams concatenated, so
    # callers that treat the return value as "all messages" see no change.
    attr_reader :errors

    # Canonical binding grammar (shared/core/binding_semantics.json):
    # inner = [!]path [?? default]; path = identifier segments joined by
    # '.' with optional bracket index; default = quoted string, true/false,
    # number, or null.
    FLAT_IDENTIFIER_RE = /\A[a-zA-Z_$][\w$]*\z/
    CANONICAL_EXPR_RE = /\A!?\s*[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[\d+\])*(?:\s*\?\?\s*(?:"[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?))?\z/

    # Base allowlist all platforms share; profiles append language extras.
    BASE_ALLOWED_PATTERNS = [
      # Simple property access (direct property name)
      /^@\{[a-zA-Z_][a-zA-Z0-9_]*\}$/,
      # Simple array access with constant index
      /^@\{[a-zA-Z_][a-zA-Z0-9_]*\[\d+\]\}$/,
      # Action bindings (callbacks) - onXxx pattern
      /^@\{on[A-Z][a-zA-Z0-9_]*\}$/,
      # data. prefix for accessing data properties (Collection cells)
      /^@\{data\.[a-zA-Z_][a-zA-Z0-9_.]*\}$/
    ].freeze

    # Identifiers that never count as data-property references. Union of
    # the platform literal spellings plus the reserved cell-scope 'index'.
    EXTRACTION_KEYWORDS = %w[true false nil null undefined visible gone index].freeze

    # Color attributes accept a semantic String key or a Color — matching
    # the SSoT color type (string|binding); only clearly wrong declared
    # types warn.
    COLOR_ATTRIBUTES = %w[
      background fontColor borderColor tintColor
      disabledBackground disabledFontColor
      selectedBackground selectedFontColor
      highlightedBackground highlightedFontColor
      placeholderColor cursorColor
      trackColor progressColor thumbColor
      separatorColor indicatorColor
    ].freeze

    def initialize
      @warnings = []
      @errors = []
      @data_properties = Set.new
      @used_properties = Set.new
      @cell_local_properties = Set.new
      @data_types = {}
      @has_data_definitions = false
      @cell_depth = 0
      @current_file = nil
      @current_view_id = nil
      @current_view_type = nil
      @current_hierarchy = nil
      defs = load_attribute_definitions
      @attribute_definitions = defs
      @component_alias_by_type = build_component_aliases(defs)
      @incompatible_attrs_by_type = build_incompatible_attrs(defs)
      @two_way_attrs_by_type = build_two_way_attrs(defs)
      @boolean_attrs_by_type = build_boolean_attrs(defs)
      @known_attrs_by_type = build_known_attrs(defs)
    end

    # Validate all bindings in a JSON component tree
    # @param json_data [Hash] The root component
    # @param file_name [String] The file name for error messages
    # @return [Array<String>] Advisory warnings followed by canonical-rule errors
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

    def has_warnings?
      !@warnings.empty?
    end

    def has_errors?
      !@errors.empty?
    end

    # Print advisory warnings and canonical-rule errors to stdout
    def print_warnings
      @warnings.each do |warning|
        puts "\e[33m[#{log_tag} Binding Warning]\e[0m #{warning}"
      end
      @errors.each do |error|
        puts "\e[31m[#{log_tag} Binding Error]\e[0m #{error}"
      end
    end

    # Check a single binding expression for business logic (advisory).
    # @param binding_expr [String] The binding expression (without @{ })
    # @return [Array<String>] Array of warning messages
    def check_binding(binding_expr, attribute_name, component_type)
      warnings = []

      # Check if it's an allowed simple pattern
      full_binding = "@{#{binding_expr}}"
      return warnings if allowed_pattern?(full_binding)

      # Canonical binding expressions ([!]path [?? literal]) are never
      # business logic — dot-paths, bracket indices, bool negation and a
      # single '??' default are all official grammar. Context violations
      # are reported as canonical rule errors, not here. The viewModel.
      # prefix stays a per-platform advisory (legacy spelling).
      if binding_expr.strip.match?(CANONICAL_EXPR_RE) &&
         !binding_expr.strip.sub(/\A!\s*/, '').start_with?('viewModel.')
        return warnings
      end

      business_logic_patterns.each do |rule|
        if binding_expr.match?(rule[:pattern])
          warnings << "#{build_context_prefix}Binding '@{#{binding_expr}}' in '#{component_type}.#{attribute_name}' contains #{rule[:message]}"
        end
      end

      warnings
    end

    private

    # ---- platform profile hooks ------------------------------------------

    def platform_id
      raise NotImplementedError, 'platform profile must define platform_id'
    end

    def log_tag
      raise NotImplementedError, 'platform profile must define log_tag'
    end

    def data_item_applies?(_data_item)
      true
    end

    # The tool's mode for attribute exclusion ('swiftui' / 'compose');
    # nil skips mode filtering (react has no modes).
    def mode_id
      nil
    end

    def business_logic_patterns
      raise NotImplementedError, 'platform profile must define business_logic_patterns'
    end

    def extra_allowed_patterns
      []
    end

    def infer_type(_var_name, _attribute_name, _component_type = nil)
      raise NotImplementedError, 'platform profile must define infer_type'
    end

    def map_typed_class?(_class_str)
      false
    end

    def warn_binding_without_id?
      false
    end

    def skip_undefined_without_data_section?
      false
    end

    def collect_platform_used_properties(_component, _component_type)
      nil
    end

    # ----------------------------------------------------------------------

    # Load attribute_definitions.json (deployed copies mirror the file into
    # lib/core/ alongside this file; source-repo layout keeps the canonical
    # copy at shared/core/).
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

    # Per component type, the set of attribute names marked for platforms
    # or modes other than this one (their bindings reference other
    # platforms'/modes' state — e.g. widthWeight is UIKit-only).
    def build_incompatible_attrs(defs)
      result = {}
      defs.each do |component_type, attrs|
        next unless attrs.is_a?(Hash)
        incompatible = Set.new
        attrs.each do |attr_name, attr_def|
          next unless attr_def.is_a?(Hash)

          if attr_def['platform']
            platforms = Array(attr_def['platform'])
            unless platforms.include?(platform_id) || platforms.include?('all')
              incompatible << attr_name
              next
            end
          end
          if mode_id && attr_def['mode']
            modes = Array(attr_def['mode'])
            unless modes.include?(mode_id) || modes.include?('all')
              incompatible << attr_name
            end
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

    # Collect all data property names and types from the component tree.
    # `in_cell` tracks Collection cell subtrees so cell-declared properties
    # can be told apart from parent-screen data (binding-cell-parent-scope).
    def collect_data_properties(component, in_cell = false)
      return unless component.is_a?(Hash)

      if component['data'].is_a?(Array)
        component['data'].each do |data_item|
          next unless data_item.is_a?(Hash)
          next unless data_item_applies?(data_item)
          # Skip ViewModel class declarations: either the bare
          # { "class": "MyViewModel" } shape (class without name) or a
          # class name ending in 'ViewModel'.
          next if data_item['class'] && !data_item['name']
          next if data_item['class'].to_s.end_with?('ViewModel')
          if data_item['name']
            @data_properties << data_item['name']
            @cell_local_properties << data_item['name'] if in_cell
            @data_types[data_item['name']] = data_item['class'] if data_item['class']
            @has_data_definitions = true
          end
        end
      end

      children = component['child'] || component['children'] || []
      children = [children] unless children.is_a?(Array)
      children.each do |child|
        next unless child.is_a?(Hash)
        # A data-only child object (no 'type', has 'data') still declares
        # properties.
        if child['data'] && !child['type']
          collect_data_from_array(child['data'], in_cell)
        else
          collect_data_properties(child, in_cell)
        end
      end

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

    def collect_data_from_array(data_array, in_cell = false)
      return unless data_array.is_a?(Array)

      data_array.each do |data_item|
        next unless data_item.is_a?(Hash)
        next unless data_item_applies?(data_item)
        next if data_item['class'] && !data_item['name']
        next if data_item['class'].to_s.end_with?('ViewModel')
        if data_item['name']
          @data_properties << data_item['name']
          @cell_local_properties << data_item['name'] if in_cell
          @data_types[data_item['name']] = data_item['class'] if data_item['class']
          @has_data_definitions = true
        end
      end
    end

    def validate_component(component, parent_type = nil, hierarchy: nil)
      return unless component.is_a?(Hash)

      component_type = component['type'] || parent_type || 'Unknown'
      has_id = component.key?('id') || component.key?('binding_id')
      @current_view_id = component['id'] || component['binding_id']
      @current_view_type = component['type'] || (component['include'] ? "include:#{component['include']}" : nil)
      @current_hierarchy = hierarchy

      # Track used properties from include's shared_data and data
      collect_used_from_include(component)

      # Platform-specific used-property sources (react's auto-generated
      # handlers / partialAttributes onclick handlers)
      collect_platform_used_properties(component, component_type)

      # Embed-specific structural rules (params tree grammar + navigationMode)
      validate_embed_component(component) if component_type == 'Embed'

      component.each do |key, value|
        next if key == 'type' || key == 'child' || key == 'children' || key == 'sections'
        next if key == 'data' || key == 'generatedBy' || key == 'include' || key == 'style' || key == 'shared_data'
        next if key == 'bindingScript' # arbitrary platform code, not a binding
        next if incompatible_attr?(component_type, key)

        check_value_for_bindings(value, key, component_type)

        # UIKit-era advisory: bindings need an id to reference the view.
        next if key == 'id'
        if warn_binding_without_id? && !has_id && has_binding?(value)
          check_binding_without_id(value, key, component_type)
        end
      end

      children = component['child'] || component['children'] || []
      children = [children] unless children.is_a?(Array)
      children.each_with_index do |child, index|
        next unless child.is_a?(Hash)
        child_hierarchy = hierarchy ? "#{hierarchy}.child[#{index}]" : "child[#{index}]"
        validate_component(child, component_type, hierarchy: child_hierarchy)
      end

      # Validate sections (Collection/Table). Cell subtrees run with the
      # cell-scope depth so binding-cell-parent-scope can fire; header /
      # footer render in parent scope and are exempt — see
      # collectionCellScope in shared/core/binding_semantics.json.
      if component['sections'].is_a?(Array)
        component['sections'].each_with_index do |section, section_index|
          next unless section.is_a?(Hash)
          ['header', 'footer', 'cell'].each do |key|
            next unless section[key].is_a?(Hash)
            section_hierarchy = hierarchy ? "#{hierarchy}.sections[#{section_index}].#{key}" : "sections[#{section_index}].#{key}"
            if key == 'cell'
              @cell_depth += 1
              validate_component(section[key], component_type, hierarchy: section_hierarchy)
              @cell_depth -= 1
            else
              validate_component(section[key], component_type, hierarchy: section_hierarchy)
            end
          end
        end
      end
    end

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

    def check_binding_without_id(value, attribute_name, component_type)
      binding_expr = value.is_a?(String) ? value : value.to_s
      @warnings << "#{build_context_prefix}'#{component_type}.#{attribute_name}' has binding '#{binding_expr}' but component has no 'id'. In UIKit mode, bindings require an id to reference the view."
    end

    def check_value_for_bindings(value, attribute_name, component_type)
      # visibility must use the String enum, whatever the value type
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
          binding_expr = value[2..-2]
          @warnings.concat(check_binding(binding_expr, attribute_name, component_type))

          unless skip_undefined_without_data_section? && !@has_data_definitions
            check_undefined_variables(binding_expr, attribute_name, component_type)
          end

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

    # Canonical validator rules from shared/core/binding_semantics.json.
    # Rule ids are embedded in the emitted messages so tooling and the
    # shared vector suite can match them.
    def check_canonical_binding_rules(value, attribute_name, component_type)
      # Embed params leaves are validated by validate_embed_params_node
      # (binding-default-in-params / binding-negation-context /
      # binding-params-array) — skip here to avoid duplicate reports.
      return if embed_params_attr?(component_type, attribute_name)

      exprs = value.scan(/@\{([^}]*)\}/).flatten
      return if exprs.empty?

      top_attr = attribute_name.to_s.split(/[.\[]/).first
      two_way = two_way_attr?(component_type, top_attr)
      whole_value = exprs.length == 1 && value.strip == "@{#{exprs.first}}"

      exprs.each do |inner|
        expr = inner.strip

        # binding-double-default: exactly one '??' per expression. String
        # literals are removed first so a default containing '??' does not
        # false-positive.
        stripped = expr.gsub(/'[^']*'/, '').gsub(/"[^"]*"/, '')
        if stripped.scan(/\?\?/).length > 1
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
    # guaranteed only the item's own fields plus the reserved 'index'.
    # Binding a bare key that is declared in the PARENT screen's data
    # section (and not redeclared inside the cell) is non-portable. Only
    # inline `sections` cells are detectable here — cell layouts in
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
      entry = "#{build_context_prefix}[#{rule_id}] #{message}"
      @errors << entry unless @errors.include?(entry)
    end

    def add_rule_warning(rule_id, message)
      entry = "#{build_context_prefix}[#{rule_id}] #{message}"
      @warnings << entry unless @warnings.include?(entry)
    end

    # Build context prefix with file name and view id (or hierarchy + type)
    def build_context_prefix
      parts = []
      parts << @current_file if @current_file
      if @current_view_id
        parts << "id=#{@current_view_id}"
      elsif @current_hierarchy || @current_view_type
        location = [@current_hierarchy, @current_view_type].compact.join(' ')
        parts << location unless location.empty?
      end
      parts.empty? ? "" : "[#{parts.join(' ')}] "
    end

    # Check if variables in binding expression are defined in data
    def check_undefined_variables(binding_expr, attribute_name, component_type)
      # Skip data. prefix bindings (Collection cell bindings)
      return if binding_expr.start_with?('data.')

      # Inside a section cell the binding scope is the ITEM object (flat
      # fields + 'index'), which the screen-level validator cannot know —
      # parent-scope references are reported separately as
      # binding-cell-parent-scope.
      return if @cell_depth > 0

      variables = extract_variables(binding_expr)

      variables.each do |var|
        @used_properties << var if @data_properties.include?(var)

        unless @data_properties.include?(var)
          @warnings << "#{build_context_prefix}Binding variable '#{var}' in '#{component_type}.#{attribute_name}' is not defined in data. Add: { \"class\": \"#{infer_type(var, attribute_name, component_type)}\", \"name\": \"#{var}\" }"
        end
      end
    end

    # Extract variable references. A dotted/indexed path (user.name,
    # items[0].title) counts as its ROOT variable only — data defines the
    # root, not each segment.
    def extract_variables(binding_expr)
      variables = Set.new

      # Remove string literals to avoid false positives
      expr = binding_expr.gsub(/'[^']*'/, '').gsub(/"[^"]*"/, '')

      expr.scan(/\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*/).each do |match|
        root = match.split(/[.\[]/).first
        next if EXTRACTION_KEYWORDS.include?(root)
        next if root =~ /^\d/
        variables << root
      end

      variables.to_a
    end

    def allowed_pattern?(binding)
      BASE_ALLOWED_PATTERNS.any? { |pattern| binding.match?(pattern) } ||
        extra_allowed_patterns.any? { |pattern| binding.match?(pattern) }
    end

    # Check if visibility attribute is using Boolean instead of String enum
    # Valid values: "visible", "gone", "invisible"
    def check_visibility_type(value, attribute_name, component_type)
      return unless attribute_name == 'visibility'

      if value == true || value == false || value == 'true' || value == 'false'
        @warnings << "#{build_context_prefix}'#{component_type}.visibility' should use String enum (\"visible\", \"gone\", \"invisible\"), not Boolean. Use a String property in data section with visibility values."
        return
      end

      if value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')
        binding_expr = value[2..-2]
        if binding_expr.match?(/^(is|has|can|should)[A-Z]/)
          @warnings << "#{build_context_prefix}'#{component_type}.visibility' binding '@{#{binding_expr}}' appears to be Boolean. Use String property with values: \"visible\", \"gone\", or \"invisible\"."
        end
      end
    end

    # Color-attribute bindings: String and Color declared types are both
    # fine (SSoT color type is string|binding — semantic keys resolve at
    # runtime); only clearly wrong declared types warn.
    def check_color_type(binding_expr, attribute_name, component_type)
      base_attr = attribute_name.split('.').last
      return unless COLOR_ATTRIBUTES.include?(base_attr) || base_attr.end_with?('Color')

      var_name = binding_expr.split('.').first.gsub(/[^a-zA-Z0-9_]/, '')
      return if var_name.empty?

      declared_type = @data_types[var_name]
      return unless declared_type

      if declared_type != 'String' && declared_type != 'Color' && !declared_type.nil?
        @warnings << "#{build_context_prefix}'#{component_type}.#{attribute_name}' binding '@{#{binding_expr}}' has type '#{declared_type}' but should be 'Color' or 'String'."
      end
    end

    # Embed structural rules (v1.5 nested params + isolated):
    # - params is a tree: intermediate nodes are literal objects only,
    #   @{} bindings may appear only at leaf scalar positions. Binding a
    #   whole subtree (a dict/map-typed VM property) is rejected —
    #   reactivity semantics for subtree bindings can't be guaranteed
    #   cross-platform.
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
        unless key.to_s.match?(/\A[a-z][a-zA-Z0-9]*\z/)
          @warnings << "#{build_context_prefix}'Embed.#{key_path}' key must be camelCase (at every nesting level)."
        end
        case value
        when Hash
          validate_embed_params_node(value, key_path)
        when Array
          add_error('binding-params-array',
                    "'Embed.#{key_path}' is an array — arrays are not supported in Embed params. Nest literal objects or bind a scalar leaf instead.")
        when String
          next unless value.start_with?('@{') && value.end_with?('}')
          inner = value[2..-2].strip

          # binding-default-in-params: '??' defaults are not allowed in
          # params leaves — the embedded screen's own data-section
          # defaultValue is the canonical fallback (unresolved leaves are
          # dropped so it applies). String literals stripped first.
          if inner.gsub(/'[^']*'/, '').gsub(/"[^"]*"/, '').include?('??')
            add_error('binding-default-in-params',
                      "'Embed.#{key_path}' uses a '??' default inside Embed params — defaults belong to the embedded screen's data section. Remove the '??' and declare a defaultValue there.")
          end

          # binding-negation-context: params leaves are not a boolean
          # value context.
          if inner.start_with?('!')
            add_error('binding-negation-context',
                      "'Embed.#{key_path}' uses '!' negation in Embed params — negation is only valid on boolean value attributes.")
          end

          prop = inner.sub(/\A!\s*/, '').split('??').first.to_s.strip
          type = @data_types[prop]
          if type.is_a?(String) && map_typed_class?(type)
            @warnings << "#{build_context_prefix}'Embed.#{key_path}' binds dict-typed property '#{prop}' — bindings are leaf-only in Embed params (bind scalar leaves; intermediate nodes must be literal objects)."
          end
        end
      end
    end

    # Collect used properties from include's shared_data and data, and
    # keep include payloads honest: they should be simple property
    # references, not complex expressions.
    def collect_used_from_include(component)
      include_type = component.key?('include') ? "include:#{component['include']}" : nil

      if component['shared_data'].is_a?(Hash)
        component['shared_data'].each do |key, value|
          next unless value.is_a?(String)
          if value.start_with?('@{') && value.end_with?('}')
            binding_expr = value[2..-2]
            if include_type && complex_binding_expression?(binding_expr)
              @warnings << "#{build_context_prefix}'#{include_type}.shared_data.#{key}' contains complex expression '@{#{binding_expr}}'. Include's shared_data should only contain simple property references (e.g., '@{propertyName}')."
              # Skip the undefined-variable check for complex expressions
              # (causes false positives)
            elsif include_type
              check_undefined_variables(binding_expr, "shared_data.#{key}", include_type)
            else
              extract_variables(binding_expr).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            end
          else
            @used_properties << value if @data_properties.include?(value)
          end
        end
      end

      # include's data (for invalidateAll) uses the Hash form; a data
      # ARRAY is a declaration section, not an include payload.
      if component['data'].is_a?(Hash)
        component['data'].each do |key, value|
          next unless value.is_a?(String)
          if value.start_with?('@{') && value.end_with?('}')
            binding_expr = value[2..-2]
            if include_type && complex_binding_expression?(binding_expr)
              @warnings << "#{build_context_prefix}'#{include_type}.data.#{key}' contains complex expression '@{#{binding_expr}}'. Include's data should only contain simple property references (e.g., '@{propertyName}') for invalidateAll."
              # Skip the undefined-variable check for complex expressions
              # (causes false positives)
            elsif include_type
              check_undefined_variables(binding_expr, "data.#{key}", include_type)
            else
              extract_variables(binding_expr).each do |var|
                @used_properties << var if @data_properties.include?(var)
              end
            end
          else
            @used_properties << value if @data_properties.include?(value)
          end
        end
      end
    end

    # Simple: propertyName, object.property. Complex: ternary, comparison,
    # calls with args, arithmetic, logical operators.
    def complex_binding_expression?(expr)
      return true if expr.include?('?') && expr.include?(':')
      return true if expr.match?(/[=!<>]=?/)
      return true if expr.match?(/\([^)]+\)/)
      return true if expr.match?(/[+\-*\/%]/)
      return true if expr.match?(/&&|\|\|/)
      false
    end

    def check_unused_properties
      unused = @data_properties - @used_properties

      context = @current_file ? "[#{@current_file}] " : ""
      unused.each do |prop|
        @warnings << "#{context}Data property '#{prop}' is defined but never used in bindings, shared_data, or data."
      end
    end
  end
end
