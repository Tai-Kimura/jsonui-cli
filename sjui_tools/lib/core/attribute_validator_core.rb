#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'

module JsonUIShared
  # Validates JSON component attributes against the SSoT definitions
  # (attribute_definitions.json). Shared body of the three toolchain
  # validators — canonical copy lives in shared/core/attribute_validator_core.rb;
  # the per-tool copies under <tool>/lib/core/ must stay byte-identical
  # (same distribution contract as layout_validator.rb / plural_validator.rb,
  # pinned by each tool's shared_core_mirror_spec).
  #
  # Platform facts are injected by a thin per-tool subclass
  # (<tool>/lib/core/attribute_validator.rb) through these hooks:
  #
  #   MODES / PLATFORM              constants — the tool's mode symbols and
  #                                 its SSoT platform id ('swift'/'kotlin'/'react')
  #   log_tag                       'SJUI' / 'KJUI' / 'RJUI' console prefix
  #   extension_definition_paths    where project-local extension attribute
  #                                 definitions live (may consult @mode)
  #   styles_fallback_dirs          style-directory candidates when config
  #                                 does not resolve one
  #   config_file_name              '<tool>.config.json'
  #
  # The Embed params tree grammar is the binding validator's job on every
  # platform (W3-2 file 5 retired the transitional react-only reporting
  # that briefly lived here).
  #
  # Everything else is deliberately identical across toolchains. Unified
  # 2026-08-01 (W3-2); divergences resolved toward canonical semantics:
  #   - warning context prefixes ([file id=x]) — previously sjui-only
  #   - nil parent_orientation means "include-file root, orientation
  #     unknown": weight/dimension checks stay silent instead of guessing
  #     ZStack — previously sjui-only (kjui/rjui warned spuriously)
  #   - widthWeight/heightWeight substitute for required width/height —
  #     previously missing in kjui
  #   - padding/margin-style numeric arrays are accepted regardless of the
  #     declared scalar type (the renderers consume them on every
  #     platform; the SSoT type is the one lagging) — previously rjui-only
  #   - a binding expression is a FULL-string @{...} value; a string that
  #     merely contains @{ is template text and still validates against
  #     the declared type/enum — previously rjui skipped all checks on any
  #     string containing @{
  class AttributeValidatorCore
    attr_reader :definitions, :warnings, :infos
    attr_accessor :mode, :styles_dir
    # When true the layout under validation carried the `$jui` L1
    # normalization marker: alias spellings were already rewritten to
    # canonical names by `jui build`, so aliases are not accepted (an
    # alias in normalized input is stale data, not author input).
    # Default (false) keeps the alias-tolerant L0 behavior.
    attr_accessor :normalized

    # All supported platforms across JsonUI libraries
    ALL_PLATFORMS = ['swift', 'kotlin', 'react'].freeze

    # Attributes whose value may also be a padding/margin-style array
    # ([all] | [vertical, horizontal] | [top, right, bottom, left])
    # even when their schema declares them as number|binding.
    EDGE_INSET_ATTRIBUTES = %w[
      padding paddings
      margin margins
    ].freeze

    # Keys that hold nested component nodes.
    #
    # The declaration is the authority for their SHAPE: `"type": "array"`
    # plus `"acceptsSingle": true`, which validate_attribute reads. This
    # constant exists for check_child_structure, which asks the further
    # question the declared type cannot: whether what is in there is a node.
    #
    # A renderer can skip an attribute it does not understand and still draw
    # the screen. It cannot skip a child — the child IS the screen — and the
    # shorthand is implemented everywhere as `[value] unless is_a?(Array)`,
    # a negation of Array where it means "a node". A String, number, null or
    # boolean was wrapped just as happily and then iterated over, matching
    # nothing, which is how a layout that cannot be rendered became an empty
    # view and a green run.
    CHILD_KEYS = %w[child children].freeze

    def initialize(mode = :all, styles_dir = nil)
      @mode = mode
      @definitions = load_definitions
      @warnings = []
      @structural_errors = []
      @infos = []
      @normalized = false
      @styles_dir = styles_dir
      @styles_cache = {}
      @current_file = nil
      @current_view_id = nil
      @current_view_type = nil
      @current_hierarchy = nil
    end

    # Validate a component and return warnings
    # @param component [Hash] The component to validate
    # @param component_type [String] The type of component (e.g., "Label", "TextField")
    # @param parent_orientation [String] The parent's orientation ('horizontal' or 'vertical')
    # @param file_name [String] The file name for context in warning messages
    # @param view_id [String] The view id for context in warning messages
    # @param hierarchy [String] The hierarchy path for context when no id (e.g., "child[0].child[1]")
    # @return [Array<String>] Array of warning messages
    def validate(component, component_type = nil, parent_orientation = nil, file_name: nil, view_id: nil, hierarchy: nil)
      @warnings = []
      @infos = []
      @current_file = file_name
      @current_view_id = view_id || component['id']
      @current_view_type = component['type']
      @current_hierarchy = hierarchy

      # Merge style attributes before validation
      merged_component = merge_style_attributes(component)

      type = component_type || merged_component['type']

      return @warnings unless type

      # Get valid attributes for this component type
      valid_attrs = get_valid_attributes(type)

      # Check each attribute in the merged component
      merged_component.each do |key, value|
        # Skip internal/structural attributes (including the `$jui`
        # normalization marker added by `jui build` normalizeLayouts)
        next if key == 'type' || key == 'mode' || key == 'parent_orientation' || key == '$jui' || key.start_with?('_')

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

      # Check that child/children actually hold nodes
      check_child_structure(merged_component, type)

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
        puts "\e[33m⚠️  [#{log_tag} Warning] #{warning}\e[0m"
      end
    end

    # Print all info messages to console
    def print_infos
      @infos.each do |info|
        puts "\e[36mℹ️  [#{log_tag} Info] #{info}\e[0m"
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

    # Violations that make a node unrenderable rather than merely
    # questionable: `child`/`children` holding something that is not a node.
    #
    # `validate` clears @warnings on every call, and callers recurse into the
    # tree with one validator instance, so a per-call channel would only ever
    # describe the last node visited. These accumulate instead, and the
    # caller clears them once per file.
    attr_reader :structural_errors

    def reset_structural_errors!
      @structural_errors = []
    end

    def structural_errors?
      !@structural_errors.empty?
    end

    private

    # A renderer can skip an attribute it does not understand and still draw
    # the screen. It cannot skip a child: the child IS the screen. So a
    # `child`/`children` value that is not a node — or an array with a
    # non-node in it — is reported as structural, not as one more warning in
    # a list the build prints and then ignores.
    def check_child_structure(component, component_type)
      CHILD_KEYS.each do |key|
        next unless component.key?(key)
        value = component[key]

        # A data-only definition list (entries with `data` and no `type`) is
        # not a node list; the loop above skips those for the same reason.
        next if value.is_a?(Array) &&
                value.all? { |i| i.is_a?(Hash) && i.key?('data') && !i.key?('type') }

        if value.is_a?(Array)
          value.each_with_index do |item, index|
            next if item.is_a?(Hash)
            add_structural_error(
              "'#{key}[#{index}]' in '#{component_type}' must be a component " \
              "node, got #{get_value_type(item)} — it cannot be rendered and " \
              "would be dropped silently"
            )
          end
        elsif !value.is_a?(Hash)
          # `warn: false`: the declared type is `array`, so validate_attribute
          # has already said `expects array, got string` for this same value.
          # Two sentences about one defect only teaches readers to skim. The
          # structural record is still made — it is what fails the build,
          # which a type warning on its own does not do.
          add_structural_error(
            "'#{key}' in '#{component_type}' must be a component node or an " \
            "array of them, got #{get_value_type(value)} — it cannot be " \
            "rendered and would be dropped silently",
            warn: false
          )
        end
      end
    end

    # ---- platform profile hooks (implemented by the per-tool subclass) ----

    def log_tag
      raise NotImplementedError, 'platform profile must define log_tag'
    end

    def extension_definition_paths
      raise NotImplementedError, 'platform profile must define extension_definition_paths'
    end

    def styles_fallback_dirs
      raise NotImplementedError, 'platform profile must define styles_fallback_dirs'
    end

    def config_file_name
      raise NotImplementedError, 'platform profile must define config_file_name'
    end

    # -----------------------------------------------------------------------

    def load_definitions
      definitions_path = File.join(File.dirname(__FILE__), 'attribute_definitions.json')
      base_definitions = if File.exist?(definitions_path)
        JSON.parse(File.read(definitions_path))
      else
        puts "\e[31m[#{log_tag} Error] attribute_definitions.json not found at #{definitions_path}\e[0m"
        {}
      end

      # Load and merge extension attribute definitions
      extension_definitions = load_extension_definitions
      merge_definitions(base_definitions, extension_definitions)
    end

    # Load extension attribute definitions from the tool's extension
    # directories (locations are a platform fact — see the profile hook).
    def load_extension_definitions
      extension_defs = {}

      extension_definition_paths.each do |ext_dir|
        next unless File.directory?(ext_dir)

        Dir.glob(File.join(ext_dir, '*.json')).each do |file|
          begin
            component_defs = JSON.parse(File.read(file))
            extension_defs.merge!(component_defs)
          rescue JSON::ParserError => e
            puts "\e[33m[#{log_tag} Warning] Failed to parse extension definition #{file}: #{e.message}\e[0m"
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

      # Canonical-only path for L1-normalized layouts: aliases were
      # already rewritten by `jui build`, so don't accept them here.
      return attrs if @normalized

      expand_aliases(attrs)
    end

    # Expand attributes carrying an `aliases: [...]` list into additional
    # entries that share the canonical definition. Alias entries are marked
    # with `_alias_of` so the validator can emit deprecation messages that
    # reference the canonical name. If the alias key already has its own
    # explicit definition (e.g. the platform defines a distinct behavior),
    # that explicit definition wins.
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

    # Map JSON type to definition key, in two layers:
    #
    # 1. the cross-platform synonym table below (display spellings that
    #    are not sections themselves: Text, Scroll, Checkbox, ...),
    # 2. a component-alias hop: sections that are `_alias_of` pointers
    #    (EditText/Input -> TextField, Check -> CheckBox, Toggle ->
    #    Switch) resolve to their canonical section, driven by the SSoT
    #    rather than by arms of this case.
    #
    # The synonym table is one of four implementations of the same
    # mapping — the shared Ruby core here (mirrored into {s,k,r}jui_tools)
    # and the Python jui_cli/core/normalizer/alias_table.py _TYPE_SYNONYMS.
    # jui_tools/tests/test_type_synonyms_cross_language.py holds the
    # agreed canon and fails CI on any divergence: change both together
    # with the canon table, never one alone. Types without a branch
    # (Button, IconLabel, TabView, Embed, ...) resolve by the identity
    # fallback to their own definition section.
    def map_type_to_definition(type)
      mapped = case type
      when 'Label', 'Text'
        'Label'
      when 'TextView', 'MultiLineEditText', 'Textarea'
        'TextView'
      when 'Image', 'ImageView', 'Img', 'CircleImage', 'CircleImageView'
        'Image'
      when 'NetworkImage', 'NetworkImageView', 'AsyncImage'
        'NetworkImage'
      when 'SelectBox', 'Spinner', 'DatePicker', 'Select', 'Picker'
        'SelectBox'
      when 'CheckBox', 'Checkbox'
        'CheckBox'
      when 'Radio', 'RadioButton', 'RadioGroup'
        'Radio'
      when 'Segment', 'SegmentedControl', 'TabLayout', 'TabGroup'
        'Segment'
      when 'Slider', 'SeekBar', 'Range'
        'Slider'
      when 'Progress', 'ProgressBar'
        'Progress'
      when 'Indicator', 'ActivityIndicator', 'Loading'
        'Indicator'
      when 'View', 'LinearLayout', 'RelativeLayout', 'FrameLayout', 'HStack', 'VStack', 'ZStack',
           'Div', 'Box', 'Container', 'Column', 'Row', 'ConstraintLayout'
        'View'
      when 'SafeAreaView'
        'SafeAreaView'
      when 'ScrollView', 'Scroll'
        'ScrollView'
      when 'Collection', 'CollectionView', 'RecyclerView', 'Table', 'TableView', 'List', 'Grid',
           'LazyGrid', 'ListView', 'LazyColumn'
        'Collection'
      when 'GradientView', 'Gradient'
        'GradientView'
      when 'Blur', 'BlurView'
        'Blur'
      when 'Web', 'WebView', 'Iframe'
        'Web'
      else
        type
      end
      resolve_component_alias(mapped)
    end

    # Follow a component-alias section (an `_alias_of` pointer such as
    # EditText -> TextField) to its canonical section. One hop only; a
    # pointer to a missing or alias-shaped target is ignored and the
    # spelling resolves to its own (empty) section instead.
    def resolve_component_alias(key)
      section = @definitions[key]
      return key unless section.is_a?(Hash)

      target = section['_alias_of']
      return key unless target.is_a?(String)

      target_section = @definitions[target]
      return key unless target_section.is_a?(Hash)

      target_section['_alias_of'].is_a?(String) ? key : target
    end

    # Validate a single attribute value
    def validate_attribute(name, value, definition, component_type, path = nil)
      return unless definition

      current_path = path ? "#{path}.#{name}" : name

      # Emit deprecation warning (alias usage or canonical deprecation)
      emit_deprecation(name, current_path, definition, component_type)

      # Check for invalid binding syntax
      check_invalid_binding_syntax(value, current_path, component_type)
      check_scalar_items(name, value, current_path, component_type)

      # Check if value is a binding expression (full-string @{...} only —
      # a string merely containing @{ is template text and still validates)
      is_binding = value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

      # Skip validation for binding expressions
      return if is_binding

      # `acceptsSingle` on an array attribute declares that a single node
      # object stands for a one-element array. Every renderer already reads
      # it that way (`[value] unless value.is_a?(Array)`); this is the same
      # rule stated once on the tool side, at the boundary, so the declared
      # type stays `array` and the declaration is what the check consults.
      #
      # Only an object is wrapped. Wrapping a scalar too would move the
      # complaint about `"child": "notalist"` from `'child'` to `'child[0]'`
      # — an index the author never wrote — and the author is the reader.
      if definition['acceptsSingle'] && value.is_a?(Hash) &&
         Array(definition['type']).include?('array')
        value = [value]
      end

      # Check type
      expected_types = Array(definition['type'])
      actual_type = get_value_type(value)

      unless type_matches?(actual_type, expected_types, value, definition)
        # Edge-inset style attributes (padding / margin) also accept
        # numeric arrays of length 1/2/4 regardless of declared type —
        # every renderer consumes them (e.g. kjui modifier_builder), so
        # warning here would be a false positive. The SSoT type widening
        # is tracked separately.
        if actual_type == 'array' && edge_inset_array?(name, value)
          # accepted
        else
          add_warning("Attribute '#{current_path}' in '#{component_type}' expects #{format_expected_types(expected_types)}, got #{actual_type}")
          return # Don't validate nested properties if type is wrong
        end
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

    # True when the attribute is a padding/margin-style key and the value is
    # a numeric array of length 1/2/4 (all | vertical,horizontal | t,r,b,l).
    def edge_inset_array?(attr_name, value)
      return false unless value.is_a?(Array)
      return false unless EDGE_INSET_ATTRIBUTES.include?(attr_name)
      return false unless [1, 2, 4].include?(value.length)
      value.all? { |v| v.is_a?(Numeric) }
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
      context = build_context_prefix
      full_message = context.empty? ? message : "#{context}#{message}"
      @warnings << full_message unless @warnings.include?(full_message)
    end

    # Structural violations are warnings too — they belong in the same
    # summary a reader already looks at — but they are also kept on their own
    # channel so a build can act on them without matching warning text.
    def add_structural_error(message, warn: true)
      context = build_context_prefix
      full_message = context.empty? ? message : "#{context}#{message}"
      @structural_errors << full_message unless @structural_errors.include?(full_message)
      return unless warn

      @warnings << full_message unless @warnings.include?(full_message)
    end

    def add_info(message)
      context = build_context_prefix
      full_message = context.empty? ? message : "#{context}#{message}"
      @infos << full_message unless @infos.include?(full_message)
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

    # Emit a deprecation warning when an attribute is marked deprecated or
    # is being accessed via an alias whose canonical form is preferred.
    # `deprecated` may be:
    #   - true                         → always warn (all platforms/modes)
    #   - "swift"/"kotlin"/"react"     → warn only on that platform
    #   - "swiftui"/"uikit"/...        → warn only in that mode
    #   - array of the above           → warn if any scope matches
    # Non-deprecated aliases are silently treated as synonyms.
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
      unless value.end_with?('}')
        add_warning("Attribute '#{path}' in '#{component_type}' has invalid binding syntax (starts with '@{' but doesn't end with '}')")
        return
      end

      check_binding_content(value[2..-2].to_s, path, component_type)
    end

    #: Two values with nothing between them — `bad name`, `items[0] count`,
    #: `"a" "b"`. Every generator interpolates a binding's CONTENT into its
    #: own language, so this reaches the output as `${data.bad name}` (JS),
    #: `\(data.bad name ?? "")` (Swift) and `${data.bad name ?: ""}`
    #: (Kotlin), none of which parse.
    #:
    #: Operators are deliberately NOT refused: `a ?? "x"`, `cond ? a : b`
    #: and `x + y` all put something between their operands, so none of them
    #: match. That is the shape real bindings take: measured with THIS rule
    #: over a consumer's layouts, 1877 live bindings contained 0 juxtaposed
    #: pairs (4 held whitespace, all operator forms). A first count of 1980
    #: added 103 prose examples from strings.json — text the site renders to
    #: explain binding syntax, not bindings that run — and 1877 is the
    #: denominator that means anything here.
    BINDING_JUXTAPOSED_VALUES = /[A-Za-z0-9_$)\]"']\s+[A-Za-z0-9_$"']/.freeze

    #: Array attributes whose elements the SSoT declares as plain labels —
    #: no element sub-schema, so nothing else here checks them.
    #:
    #: `Segment.items` is "Static labels; an entry may be a strings key".
    #: An object element is therefore undeclared, and every generator used
    #: to stringify it: iOS and Android shipped `Text("{\"label\"=>\"opt_a\",
    #: …}")` on screen and web wrote a Ruby hash into JSX, which does not
    #: parse (measured 2026-09-04). Both dynamic runtimes already drop such
    #: an element — Android `DynamicSegmentComponent` keeps primitives only,
    #: iOS `asStrings` compacts to String/NSNumber — so dropping it in the
    #: generators is what makes the four agree.
    #:
    #: Deliberately NOT a general rule over every element-schema-less array:
    #: `Collection.items` is a data source, where an object element is
    #: exactly what a face may legitimately pass. Widening this needs its
    #: own measurement.
    #: A `null` element passed this rule when it only named Hash and Array,
    #: and web emitted an empty `<button>` whose id was real — so every
    #: later `s_tab_n` sat one index off the runtimes, which drop it
    #: (reported by the rjui lane, 2026-09-04).
    SCALAR_ITEM_ATTRIBUTES = { 'Segment' => %w[items].freeze }.freeze

    #: True when a labels-only attribute was given a binding string.
    #:
    #: `Segment.items` is declared `type: "array"` — no binding — yet kjui
    #: resolved `@{options}` into a `forEachIndexed` and sjui raised
    #: `NoMethodError: undefined method 'each_with_index' for String`
    #: (measured 2026-09-04). One face invented a feature, the other
    #: crashed, and nothing warned: the type check lets a binding string
    #: stand in for any declared type. Usage across seven faces: 0.
    def self.binding_in_scalar_items?(component_type, attribute_name, value)
      return false unless SCALAR_ITEM_ATTRIBUTES[component_type.to_s]&.include?(attribute_name.to_s)

      value.is_a?(String) && value.strip.start_with?('@{') && value.strip.end_with?('}')
    end

    #: Indices of elements a generator must not emit. Public so the
    #: converters decide with the same predicate that warns — a warning and
    #: an emit that disagree is how this defect stayed invisible.
    def self.non_scalar_item_indices(component_type, attribute_name, value)
      return [] unless SCALAR_ITEM_ATTRIBUTES[component_type.to_s]&.include?(attribute_name.to_s)
      return [] unless value.is_a?(Array)

      value.each_index.reject { |index| scalar_item?(value[index]) }
    end

    #: What both runtimes keep: a JSON scalar. Android tests
    #: `element.isJsonPrimitive` (string, number, boolean — Gson's JsonNull
    #: is not one) and iOS casts to `String` / `NSNumber` (a Bool bridges to
    #: NSNumber, an NSNull casts to neither).
    #:
    #: Booleans are kept deliberately, though `[true]` renders "true" on web
    #: and Android and "1" on iOS: BOTH runtimes render it, so dropping it
    #: here would make the generated screen show fewer tabs than the running
    #: one — the divergence this rule exists to close. That rendering split
    #: is a real defect, and it belongs to whoever owns the declaration and
    #: the runtimes, not to a unilateral drop in the generators.
    def self.scalar_item?(item)
      item.is_a?(String) || item.is_a?(Numeric) || item == true || item == false
    end

    #: The word the warning uses for what was found.
    def self.item_kind(item)
      case item
      when nil then 'null'
      when Hash then 'an object'
      when Array then 'an array'
      else item.class.name.downcase
      end
    end

    # The delimiters were only ever half the check.
    #
    # `@{ bad name }` closes correctly, so the old check passed it, and each
    # generator then interpolated the content verbatim into a syntax error
    # while the build exited 0. Measured 2026-09-04 on 1.8.36 and again on
    # 1.8.37, same input on three faces: web reported NOTHING; iOS and
    # Android split the content on the space and reported two undefined
    # variables — noticing, and writing the broken code anyway.
    #
    # Only what cannot be an expression in any target is refused here. A
    # padded identifier is not refused, because it is not broken: `@{ title
    # }` is trimmed and emits `${data.title ?? ""}` (measured, not assumed).
    # The same judgment the generators need, so the two cannot disagree:
    # a validator that warns while a converter still emits is how this
    # reached a release. Returns :empty, :juxtaposed, or nil.
    def self.binding_content_problem(content)
      text = content.to_s
      return :empty if text.strip.empty?
      return :juxtaposed if text.match?(BINDING_JUXTAPOSED_VALUES)

      nil
    end

    #: Name every undeclared element by index: the generator drops it, and
    #: a segment that silently renders one fewer tab is worse than a named
    #: warning.
    def check_scalar_items(name, value, path, component_type)
      if self.class.binding_in_scalar_items?(component_type, name, value)
        add_warning(
          "Attribute '#{path}' in '#{component_type}' is a binding; items are static labels " \
          "per the declaration (type: array, no binding) — ignored, and no items are generated"
        )
        return
      end

      self.class.non_scalar_item_indices(component_type, name, value).each do |index|
        add_warning(
          "Attribute '#{path}[#{index}]' in '#{component_type}' is " \
          "#{self.class.item_kind(value[index])}; items are string labels (literal text or a " \
          "strings key) per the declaration — dropped from the generated output, as both " \
          "runtimes already drop it"
        )
      end
    end

    def check_binding_content(content, path, component_type)
      if content.strip.empty?
        add_warning("Attribute '#{path}' in '#{component_type}' is an empty binding '@{}' — it is emitted as the literal text '@{}', not as a value")
        return
      end
      return unless content.match?(BINDING_JUXTAPOSED_VALUES)

      add_warning("Attribute '#{path}' in '#{component_type}' has a binding that is not an expression: '#{content.strip}' puts two values side by side with nothing between them. The generators interpolate this verbatim, so the generated JavaScript/Swift/Kotlin does not parse")
    end

    # Check for conflicting distribution and gravity attributes.
    # Only a real axis conflict warns: `distribution` arranges children
    # along the main axis, so a main-axis gravity value is overridden.
    # `spacing` (gap) composes with any gravity on every platform
    # (gap + items-*/justify-* in flexbox, HStack(alignment:, spacing:)
    # in SwiftUI, Arrangement.spacedBy(x, alignment) in Compose) and a
    # cross-axis gravity never conflicts.
    def check_spacing_gravity_conflict(component, component_type)
      return unless component.key?('distribution') && component.key?('gravity')

      main_axis_values =
        case component['orientation'].to_s.downcase
        when 'horizontal' then %w[left right centerHorizontal]
        when 'vertical' then %w[top bottom centerVertical]
        else return # no linear axis — no main-axis conflict possible
        end

      gravity = component['gravity']
      gravity_values = gravity.is_a?(Array) ? gravity.map(&:to_s) : gravity.to_s.split('|')
      conflicting = gravity_values & (main_axis_values + ['center'])
      return if conflicting.empty?

      add_warning("Component '#{component_type}' has 'distribution' and main-axis gravity #{conflicting.join(', ')}. 'distribution' controls the main-axis arrangement, so this gravity value is overridden. Consider using only one of these attributes.")
    end

    # Check for weight + dimension conflict in the same direction as parent orientation
    # - parent orientation: horizontal + width + weight -> warning
    # - parent orientation: vertical + height + weight -> warning
    # - no orientation (ZStack) + weight -> warning (weight is invalid)
    # - nil orientation (include file root) -> skip warning (parent orientation unknown)
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
      when nil
        # nil means include file root - parent orientation unknown
        # Skip warning since the actual parent may have a valid orientation
        nil
      else
        # Unknown orientation means ZStack - weight is not applicable
        add_warning("Component '#{component_type}' has 'weight' but parent has no orientation (ZStack). 'weight' only works in horizontal/vertical layouts. Consider removing 'weight'.")
      end
    end

    # Check if width/height required warning should be skipped
    # When weight or widthWeight/heightWeight is set, the corresponding dimension is not required
    # - widthWeight can substitute for width
    # - heightWeight can substitute for height
    # - weight can substitute for width (horizontal) or height (vertical)
    # - nil parent_orientation means include file root, skip warning since parent orientation is unknown
    def skip_dimension_required?(attr_name, component, parent_orientation)
      return false unless %w[width height].include?(attr_name)

      # Check for specific dimension weight
      # widthWeight can substitute for width, heightWeight can substitute for height
      if attr_name == 'width' && component.key?('widthWeight')
        return true
      end
      if attr_name == 'height' && component.key?('heightWeight')
        return true
      end

      # Check for generic weight
      return false unless component.key?('weight')

      case parent_orientation
      when 'horizontal'
        # In horizontal layout, weight determines width
        attr_name == 'width'
      when 'vertical'
        # In vertical layout, weight determines height
        attr_name == 'height'
      when nil
        # nil means include file root - parent orientation unknown
        # Skip warning since the actual parent may provide the needed orientation
        true
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
      attr_platforms.include?(self.class::PLATFORM) || attr_platforms.include?('all')
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

      add_info("Attribute '#{attr_name}' in '#{component_type}' is for #{platform_str} platform (current: #{self.class::PLATFORM.capitalize})")
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
      config = load_tool_config
      if config
        source_dir = config['source_directory']
        styles_dir = config['styles_directory']
        if source_dir && styles_dir
          config_path = File.join(Dir.pwd, source_dir, styles_dir)
          return config_path if Dir.exist?(config_path)
        end
      end

      # Fallback to the tool's conventional locations
      styles_fallback_dirs.find { |dir| Dir.exist?(dir) }
    end

    # Load <tool>.config.json if it exists
    # @return [Hash, nil] Config hash or nil
    def load_tool_config
      config_path = File.join(Dir.pwd, config_file_name)
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
