#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'
require_relative 'tap_accessibility'
require_relative 'enum_spelling'
require_relative 'type_synonyms'

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

    # How an extension component's definition says it takes no children
    # (`<tool> g converter <Name> --no-container`), inside the component's
    # entry in attribute_definitions/<Name>.json:
    #
    #   "Name": { "title": { … }, "_children": "none" }
    #
    # The shared LayoutValidator refuses a layout that gives such a component
    # children (check_leaf_children). It is a declaration because the absence
    # of `child` / `children` already means something else: definitions
    # written before 1.9.0 declare no child for the default mode either,
    # and those components draw the children they are given.
    #
    # A string, not `false`: validators before 1.9.0 read every entry here
    # as a Hash, and `false['required']` raised on every node of that type —
    # measured on 1.8.120 — where a string is passed over the way the SSoT's
    # own `_comment` entries are.
    CHILDREN_DECLARATION = '_children'
    NO_CHILDREN = 'none'

    # The sentence a node of a type the tool cannot draw is named with (4f's
    # ruling, jsonui-cli 1.9.0): the type as written, and — when it matches a
    # type the tool draws but for its case — that type. Type names are
    # matched as written, as the SSoT spells them. One sentence: the kjui /
    # sjui / rjui codegen write it where they draw nothing, and KotlinJsonUI
    # Dynamic holds the same one in its library.
    UNKNOWN_COMPONENT_TYPE = "Unknown component type '%<written>s'"
    UNKNOWN_COMPONENT_TYPE_HINT = " — did you mean '%<canonical>s'? Type names are case-sensitive."

    # The sentence for `written`, given the types the tool draws.
    def self.unknown_component_type_message(written, known_types)
      message = format(UNKNOWN_COMPONENT_TYPE, written: written)
      # The spelling it differs from only in case, by the one search every
      # caller asks (TypeSynonyms.case_only_match: `known_types` first, then
      # the synonyms, the alias sections and the app's types); `written` is a
      # type the caller does not know.
      canonical = JsonUIShared::TypeSynonyms.case_only_match(written, known_types)
      canonical ? message + format(UNKNOWN_COMPONENT_TYPE_HINT, canonical: canonical) : message
    end

    # A type the validator knows (known_component_types: declared in the SSoT
    # or the project's extension definitions, a type synonym, registered by
    # the app) that a tool has no drawer for is not unknown: the codegen
    # names it in this sentence and draws it as a View, its children in it
    # (4f's ruling, jsonui-cli 1.9.0). An unknown type is named in the one
    # above and drawn as nothing.
    DECLARED_WITHOUT_DRAWER = "'%<written>s' is declared but has no %<platform>s converter — drawn as a View"

    # The sentence for a known `written` the `platform` codegen (SwiftUI,
    # Compose, web) has no drawer for.
    def self.declared_without_drawer_message(written, platform)
      format(DECLARED_WITHOUT_DRAWER, written: written, platform: platform)
    end

    # The project's extension definitions alone, read the way a validator in
    # `mode` reads them (the paths are the platform profile's). For the
    # shared LayoutValidator, which knows the SSoT but not the project.
    #
    # Not cached: a build asks once per layout and these are a few small
    # files, while a cache would answer "what did the tree say when this
    # process started" — the question sjui's build cache used to answer
    # instead of "what does this tree say".
    def self.extension_definitions(mode = :all)
      reader = allocate
      reader.instance_variable_set(:@mode, mode)
      reader.send(:load_extension_definitions)
    end

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

      # A type the tool cannot draw
      check_component_type(type)

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
          # A declared leaf's children are refused by name by the shared
          # LayoutValidator; "Unknown attribute 'child'" would say the same
          # defect a second time, in the sentence a container in the default
          # mode also draws.
          next if valid_attrs[CHILDREN_DECLARATION] == NO_CHILDREN
        end

        if valid_attrs.key?(key)
          attr_def = valid_attrs[key]
          # An attribute the SSoT declares on a section it does not reach
          # (`notApplicableTo`: section -> reason) is written, builds, and is
          # never called there — the component's own operation takes the
          # gesture. Named, on every face in the same words (ruling
          # 2026-10-03: onPan on a text field / slider, onClick on a Web).
          # A bound value with a declared limitation on this face
          # (`bindingInfo`: platform, note) — named once as INFO.
          add_binding_info(key, value, attr_def, type)
          if (reason = not_applicable_reason(attr_def, type))
            add_warning("'#{key}' is not called on a #{map_type_to_definition(type)}: #{reason}")
            next
          end
          # Check platform compatibility first
          if platform_compatible?(attr_def)
            # Check mode compatibility
            if mode_compatible?(attr_def)
              # Validate attribute value
              validate_attribute(key, value, attr_def, type)
            elsif attr_def['warn_outside_mode']
              add_outside_mode_warning(key, attr_def, type)
            else
              # Attribute not supported in current mode - log as info
              add_mode_info(key, attr_def, type)
            end
          elsif attr_def['warn_outside_mode']
            add_outside_mode_warning(key, attr_def, type)
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
        # Only attribute declarations: the SSoT's `_comment` strings and an
        # extension's `_children` declaration are not attributes.
        next unless attr_def.is_a?(Hash)
        next unless platform_compatible?(attr_def)
        if attr_def['required'] && !merged_component.key?(attr_name)
          # Skip width/height required check if weight is set and parent orientation allows it
          next if skip_dimension_required?(attr_name, merged_component, parent_orientation)

          add_warning("Required attribute '#{attr_name}' is missing for component type '#{type}'")
        end
      end

      # Check that child/children actually hold nodes
      check_child_structure(merged_component, type)

      # A text field's declared onClick is not called
      check_text_field_click(merged_component, type)

      # `bind` beside the component's own value attribute
      check_bind_beside_own_value(merged_component, type)

      # A value attribute of the other kind (a Date SelectBox's selectedValue)
      check_value_attribute_of_another_kind(merged_component, type)

      # A style named inside a responsive override is not applied
      check_responsive_override_style(merged_component)

      # Check for conflicting attributes
      check_spacing_gravity_conflict(merged_component, type)

      # A synonym spelling whose node sets an attribute the spelling means
      # otherwise (an HStack with orientation vertical): the node's value is
      # drawn, and the author is told
      JsonUIShared::TypeSynonyms.disagreements(merged_component, type_synonyms_path).each { |m| add_warning(m) }

      # Check for weight + dimension conflict
      check_weight_dimension_conflict(merged_component, type, parent_orientation)

      # `bind` on a Collection (a Table is one): not its data source. rjui read
      # it as the items when `items` was absent and no other path did, so a
      # Collection bound that way drew on web only (ticket
      # collection-attributes-declared-but-not-drawn-on-some-paths).
      if map_type_to_definition(type) == 'Collection' && merged_component.key?('bind')
        add_warning("'bind' is not a Collection's data source; use 'items' (e.g. \"items\": \"@{rows}\")")
      end

      # `columns` on a flow Collection — its own or a section's: a flow wraps
      # by content width, and every face ignores a column count there (sjui,
      # kjui and rjui codegen, both Dynamic renderers; ruling 2026-09-26,
      # ticket collection-attributes-declared-but-not-drawn-on-some-paths).
      check_flow_columns(merged_component) if map_type_to_definition(type) == 'Collection'

      # Check Collection requires cellIdProperty in SwiftUI/Compose mode
      if map_type_to_definition(type) == 'Collection' && (@mode == :swiftui || @mode == :compose)
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

    # The sentence for a node of `written`, with the types this tool draws —
    # the codegen says the validator's sentence where it draws nothing.
    def unknown_component_type_message(written)
      self.class.unknown_component_type_message(written, known_component_types)
    end

    # Whether the validator knows `written` as a type (known_component_types):
    # what a codegen asks before it names a type it has no drawer for.
    def known_component_type?(written)
      known_component_types.include?(written)
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
        # Every attribute is then checked against no definitions. Named at
        # the end of the build, once — until 1.9.0 this line was all, and
        # the build ended in its success line (ticket
        # uikit-build-reports-success-after-a-binding-error).
        begin
          require_relative 'stage_failures'
          JsonUI::StageFailures.record_once(
            'validation', "#{definitions_path} was not found; the attributes were checked without it"
          )
        rescue LoadError
          nil
        end
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

    # The reason an attribute is declared not to reach this type's section,
    # or nil (`notApplicableTo`, keyed by the canonical section: EditText /
    # Input resolve to TextField through the type synonyms).
    def add_binding_info(key, value, attr_def, type)
      info = attr_def['bindingInfo']
      return unless info.is_a?(Hash) && value.is_a?(String) && value.include?('@{')
      return unless Array(info['platform']).include?(self.class::PLATFORM)

      add_info("'#{key}' on #{type} is bound: #{info['note']}")
    end

    def not_applicable_reason(attr_def, type)
      table = attr_def['notApplicableTo']
      return nil unless table.is_a?(Hash)

      table[map_type_to_definition(type)]
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
    # 1. the cross-platform synonym table (display spellings that are not
    #    sections themselves: Text, Scroll, Checkbox, ...), read from
    #    type_synonyms.json beside attribute_definitions.json — the one
    #    table, which jui_cli's alias_table.py reads too and the renderers
    #    are to draw synonyms from
    #    (jui_tools/tests/test_type_synonyms_cross_language.py checks each
    #    reader answers what the file says),
    # 2. a component-alias hop: sections that are `_alias_of` pointers
    #    (EditText/Input -> TextField, Check -> CheckBox, Toggle ->
    #    Switch) resolve to their canonical section, driven by the SSoT.
    #
    # A spelling in neither (Button, IconLabel, TabView, Embed, ...)
    # resolves by the identity fallback to its own definition section.
    def map_type_to_definition(type)
      entry = type_synonyms[type]
      resolve_component_alias(entry ? entry['canonical'] : type)
    end

    # spelling -> { 'canonical' => section, 'render_as' => type (optional) },
    # read once per validator through JsonUIShared::TypeSynonyms.load
    # (type_synonyms.rb beside this file, the one parser of the table), which
    # also says why a table cannot be used. `@type_synonyms_path` points a
    # validator at another copy of the table (the cross-language test's swap
    # arm).
    #
    # A table that cannot be used — missing (what a plain copy of a tool
    # leaves: the file is a link into shared/core, as
    # attribute_definitions.json is), not JSON, or not the declared shape — is
    # met the way load_definitions meets a missing definitions file: named
    # where it is met, a validation stage that did not complete — in the
    # ledger once, however many validators meet it — and the synonym
    # spellings checked against the common attributes only. An empty table
    # read in silence would do that and say nothing; this says it.
    #
    # Until 1.9.0 each case raised, and each tool carried the raise its own
    # way (measured on 46a54fc3, 2026-09-26, two layouts): a missing file —
    # sjui exit 1, kjui every layout failed with exit 1, rjui one entry per
    # layout; a file that is not JSON — sjui (SwiftUI) "build completed!" with
    # nothing said, kjui "Failed to parse home.json: unexpected end of input"
    # (the layout blamed, exit 1, no ledger), rjui one entry per layout, and
    # none of them named type_synonyms.json; the wrong shape — sjui
    # "WARNING: Failed to parse home.json: …" and "build completed!", kjui
    # exit 1 with no ledger.
    def type_synonyms
      @type_synonyms ||= begin
        entries, problem = JsonUIShared::TypeSynonyms.load(type_synonyms_path)
        problem ? unusable_type_synonyms(*problem) : entries
      end
    end

    def type_synonyms_path
      @type_synonyms_path || JsonUIShared::TypeSynonyms::DEFAULT_PATH
    end

    # {} after naming the unusable table (see type_synonyms): `said` where it
    # is met, `entry` in the ledger (TypeSynonyms.load gives both).
    def unusable_type_synonyms(said, entry)
      puts "\e[31m[#{log_tag} Error] #{said}\e[0m"
      begin
        require_relative 'stage_failures'
        JsonUI::StageFailures.record_once(
          'validation', "#{entry}; the type synonyms were checked against the common attributes only"
        )
      rescue LoadError
        nil
      end
      {}
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

      # A tap handler that names no method: reported once, as what it is,
      # instead of as a type mismatch ("expects binding, got string").
      return if check_tap_handler(name, value, current_path, component_type)

      # Check for invalid binding syntax
      check_invalid_binding_syntax(value, current_path, component_type)
      check_scalar_items(name, value, current_path, component_type)

      # Check if value is a binding expression (full-string @{...} only —
      # a string merely containing @{ is template text and still validates)
      is_binding = value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

      # A binding where the declaration does not allow one. The early return
      # below skips the type check for EVERY binding, so an attribute
      # declared `type: array` with no `binding` accepted a String and handed
      # it to a converter that calls `.each` on it: measured as
      # `NoMethodError: undefined method 'each' for "@{secs}":String` on
      # `Collection.sections`, which killed that one screen while `jui build`
      # still exited 0. Same hole 1.8.39 closed for `Segment.items`, but
      # stated once from the declaration instead of per attribute.
      # Skip validation for binding expressions. A binding the declaration
      # does not allow is reported by LayoutValidator instead, at :error —
      # reported here too it would say the same thing twice, once at a level
      # that does not stop the build.
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

      # An attribute declared as a binding only, given a literal array /
      # number / boolean / object: named for what it is — nothing draws a
      # literal there. `Collection.items` lost its array form on 2026-09-26
      # (declared, drawn by no platform, used by no face); this is the
      # sentence a layout still writing one gets (ticket
      # collection-attributes-declared-but-not-drawn-on-some-paths).
      if expected_types == ['binding'] && actual_type != 'string'
        add_warning("Attribute '#{current_path}' in '#{component_type}' takes a binding (\"@{…}\"), got a literal #{actual_type}: " \
                    'no platform draws a literal here — bind it')
        return
      end

      unless type_matches?(actual_type, expected_types, value, definition)
        # Edge-inset style attributes (padding / margin) also accept
        # numeric arrays of length 1/2/4 regardless of declared type —
        # every renderer consumes them (e.g. kjui modifier_builder), so
        # warning here would be a false positive. The SSoT type widening
        # is tracked separately.
        if actual_type == 'array' && edge_inset_array?(name, value)
          # accepted
        elsif inline_layout?(value) && expected_types == ['string']
          add_warning(inline_layout_sentence(current_path))
          return
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
          add_warning("Attribute '#{path}' in '#{component_type}' has invalid value(s) '#{invalid_values.inspect}'. Valid values: #{enum_values.join(', ')}#{near_miss(invalid_values, enum_values)}")
        end
      else
        # For single values
        unless enum_values.include?(value)
          add_warning("Attribute '#{path}' in '#{component_type}' has invalid value '#{value}'. Valid values: #{enum_values.join(', ')}#{near_miss([value], enum_values)}")
        end
      end
    end

    # " — did you mean 'x'?" for a value that differs from a declared
    # spelling only in case: a value is its declared spelling, case and all
    # (1.9.0), and the near miss is named as the generated parsers name it.
    def near_miss(values, enum_values)
      near = values.map { |v| v.is_a?(String) && enum_values.find { |e| e.is_a?(String) && e.casecmp?(v) } }
      near = near.select { |n| n }.uniq
      near.empty? ? '' : " — did you mean #{near.map { |n| "'#{n}'" }.join(', ')}?"
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

      # A property's declared `aliases` (a partialAttributes range's `onClick`
      # declares `onclick`) are accepted as it on an L0 layout, as a node's
      # own are (expand_aliases); the normalizer folds them, so a normalized
      # layout carries the canonical name only.
      properties = expand_aliases(properties) unless @normalized

      obj.each do |key, value|
        if properties.key?(key)
          validate_attribute(key, value, properties[key], component_type, path)
        elsif %w[child children].include?(key) && inline_layout?(value)
          add_warning(inline_layout_sentence("#{path}.#{key}"))
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
            next
          end
          # An item vocabulary (safeAreaInsetPositions: top / bottom / leading
          # / trailing / vertical / all) names an item declared in no case, as
          # a top-level enum does (1.9.0): it reserves nothing and is named.
          validate_enum_value(item, item_def['enum'], item_path, component_type) if item_def['enum'].is_a?(Array)
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

    # The types this tool draws: the SSoT's sections and the project's
    # extension definitions (@definitions holds both), the type-synonym
    # spellings, and the extension components the tool's own registry
    # draws (registered_component_types, the profile's). A registered type
    # with no attribute definition (a converter and no definition file) is
    # known: its attributes are checked against the common ones, as before.
    def known_component_types
      @known_component_types ||= (
        @definitions.select { |key, body| body.is_a?(Hash) && key != 'common' && !key.start_with?('_') }.keys +
        type_synonyms.keys + registered_component_types
      ).uniq
    end

    # The extension component types the tool's registry draws — a platform
    # fact, read by the profile where it reads the registry the tool's
    # dispatch reads. None by default.
    def registered_component_types
      []
    end

    # A node whose type the tool cannot draw, named by the type (4f's ruling:
    # "Unknown attribute 'isOn' for component type 'switch'" did not say
    # that the type was the cause). Nothing is said when there are no SSoT
    # definitions to know types by (load_definitions names that).
    def check_component_type(type)
      return unless @definitions.key?('common')
      return if known_component_types.include?(type)

      add_warning(self.class.unknown_component_type_message(type, known_component_types))
    end

    # A text field — a section whose `text` the user writes, so its binding
    # is two-way (read from the definitions, not a list of types: TextField
    # and TextView, and every spelling that maps to them) — does not call a
    # declared onClick: its own tap focuses it. The ruling for the five paths
    # (ticket control-onclick-is-called-differently-on-every-path) leaves the
    # handler uncalled on sjui, kjui and rjui alike, and this is the one
    # sentence that tells the author, from the validator all three run.
    def check_text_field_click(component, type)
      handler = component['onClick']
      tap = JsonUIShared::TapAccessibility
      declared = handler.is_a?(Hash) || tap.handler?(handler) || tap.handler?(component['onclick'])
      return unless declared

      section = map_type_to_definition(type)
      text = @definitions.dig(section, 'text')
      return unless text.is_a?(Hash) && text['binding_direction'] == 'two-way'

      add_warning("onClick on a #{section} is not called: a text field's tap focuses it")
    end

    # `bind` is an alternative spelling of the component's own value
    # attribute, "which takes precedence when both are set" (SSoT
    # common.bind; `primaryValue` lists, per section, the attributes that are
    # that value). The layout normalizer drops such a `bind` with this same
    # sentence; this is it for a layout the normalizer did not fold
    # (normalizeLayouts false, a tool run on its own).
    def check_bind_beside_own_value(component, type)
      return unless component.key?('bind')

      section = map_type_to_definition(type)
      values = bind_value_attributes(section, component)
      return unless values.is_a?(Array)

      own = values.find { |key| component.key?(key) }
      return unless own

      value = component[own]
      shown = value.is_a?(String) ? value : JSON.generate(value)
      add_warning("'bind: #{component['bind']}' is ignored: '#{own}: #{shown}' is the #{section}'s value")
    end

    # A section whose value depends on another attribute (a `primaryValue`
    # object — SelectBox by selectItemType): the attributes of the
    # `whenAbsent` kind that are not this node's value are read by no path. A
    # Date SelectBox's value is selectedDate (4f's ruling, jsonui-cli 1.9.0);
    # sjui read it alone, while the kjui codegen, rjui and KotlinJsonUI
    # Dynamic fell back to selectedItem / selectedValue / selectedIndex, each
    # to a different few.
    def check_value_attribute_of_another_kind(component, type)
      section = map_type_to_definition(type)
      entry = @definitions.dig('common', 'bind', 'primaryValue', section)
      return unless entry.is_a?(Hash) && entry['lists'].is_a?(Hash)

      own = bind_value_attributes(section, component) || []
      kind = component[entry['by']]
      return unless kind.is_a?(String) && entry['lists'].key?(kind) && kind != entry['whenAbsent']

      Array(entry['lists'][entry['whenAbsent']]).each do |attr|
        next if own.include?(attr) || !component.key?(attr)

        add_warning("'#{attr}' has no effect on a #{kind} #{section} — its value is #{own.first}")
      end
    end

    # The attributes `bind` stands for on a section (common.bind
    # primaryValue): a list, or — for a section whose value depends on
    # another attribute — the object's list for the node's value of it
    # (`lists[node[by]]`, else `lists[whenAbsent]`). nil for a section the
    # table does not map.
    def bind_value_attributes(section, component)
      entry = @definitions.dig('common', 'bind', 'primaryValue', section)
      return entry if entry.is_a?(Array)
      return nil unless entry.is_a?(Hash) && entry['lists'].is_a?(Hash)

      kind = component[entry['by']]
      kind = entry['whenAbsent'] unless kind.is_a?(String) && entry['lists'].key?(kind)
      list = entry['lists'][kind]
      list.is_a?(Array) ? list : nil
    end

    # A flow Collection: `layout` (or `orientation`) flow or one of its alias
    # spellings, not turned horizontal by `horizontalScroll: true` — the
    # reading every codegen routes by.
    # A `style` inside a responsive override (`responsive.<class>.style`): an
    # override's attributes are its own, and no path applies a style named
    # there — sjui / kjui codegen, rjui and both Dynamic runtimes did not; jui's
    # normalizer did, so the hotloader drew what no build draws (4f's ruling,
    # 1.9.0: named on every path, applied by none). The same sentence as the
    # normalizer's StyleMerger and SwiftJsonUI Dynamic's ResponsiveResolver.
    STYLE_IN_RESPONSIVE_OVERRIDE =
      "'style' inside a responsive override is not applied — put the attributes in the override"

    # A layout written inline where the declaration takes a layout's name —
    # a tab's `child` (a tab names its layout with `view`), a section's
    # header / cell / footer as a node — is declared nowhere, and no path
    # draws it: sjui / kjui / rjui and both Dynamic runtimes read names (4f's
    # ruling, 1.9.0). sjui's and kjui's builds raised on an inline cell; they
    # go on without it now. It was "Unknown property" or "expects string".
    def inline_layout?(value)
      node = ->(v) { v.is_a?(Hash) && (v.key?('type') || v.key?('child') || v.key?('children')) }
      node.call(value) || (value.is_a?(Array) && !value.empty? && value.all?(&node))
    end

    def inline_layout_sentence(path)
      "'#{path}' is an inline layout, which is not declared and is not drawn — name a layout file instead"
    end

    def check_responsive_override_style(component)
      responsive = component['responsive']
      return unless responsive.is_a?(Hash)
      return unless responsive.values.any? { |override| override.is_a?(Hash) && override.key?('style') }

      add_warning(STYLE_IN_RESPONSIVE_OVERRIDE)
    end

    def check_flow_columns(component)
      # `orientation` is read as the layout when `layout` is absent, as the
      # converters read it — so its value is judged by layout's spellings.
      layout = JsonUIShared::EnumSpelling.lowered(component['layout'] || component['orientation'], 'Collection', 'layout')
      return unless %w[flow leftaligned].include?(layout) && component['horizontalScroll'] != true

      said = 'has no effect on a flow Collection (it wraps by content width)'
      add_warning("columns #{said}") if component.key?('columns')
      sections = component['sections']
      return unless sections.is_a?(Array)

      sections.each_with_index do |section, index|
        add_warning("sections[#{index}].columns #{said}") if section.is_a?(Hash) && section.key?('columns')
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
    # An empty or blank tap handler (`onClick` / `onclick`, on a component or
    # a partialAttributes range) names no method — shared/core/
    # tap_accessibility.rb `handler?` — so no codegen emits a tap for it, and
    # a blank element of an `onclick` array is not called. The codegens used
    # to emit a call on the blank name, which did not compile; the author
    # meant a tap, so it is said here. Returns true when the value names no
    # method at all (the other checks have nothing left to say about it).
    def check_tap_handler(name, value, path, component_type)
      return false unless JsonUIShared::TapAccessibility::TAP_KEYS.include?(name)
      return false unless value.is_a?(String) || value.is_a?(Array)

      tap = JsonUIShared::TapAccessibility
      unless tap.handler?(value)
        add_warning("Attribute '#{path}' in '#{component_type}' names no handler (#{value.inspect}) — " \
                    'no tap is generated for it. Name the method, or remove the attribute')
        return true
      end
      if value.is_a?(Array)
        blank = value.each_index.select { |i| value[i].is_a?(String) && !tap.names_a_method?(value[i]) }
        unless blank.empty?
          add_warning("Attribute '#{path}' in '#{component_type}' has a blank handler at " \
                      "#{blank.map { |i| "[#{i}]" }.join(', ')} — it names no method and is not called")
        end
      end
      false
    end

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

    #: Name every undeclared ELEMENT by index: the generator drops it, and
    #: a segment that silently renders one fewer tab is worse than a named
    #: warning.
    #:
    #: A BINDING in `items` is no longer handled here. It used to warn
    #: "ignored, and no items are generated" and let the build go green
    #: with an empty Segment on screen — a declaration violation reported
    #: at a level that stops nothing. `check_undeclared_bindings` now
    #: refuses it at `:error` like every other `type: array` attribute with
    #: no binding, so the two rules cannot disagree about the same value.
    def check_scalar_items(name, value, path, component_type)
      self.class.non_scalar_item_indices(component_type, name, value).each do |index|
        add_warning(
          "Attribute '#{path}[#{index}]' in '#{component_type}' is " \
          "#{self.class.item_kind(value[index])}; items are string labels (literal text or a " \
          "strings key) per the declaration — dropped from the generated output, as both " \
          "runtimes already drop it"
        )
      end
    end

    #: Attributes that take a list and never a string. Derived from the
    #: declaration, never from a hand-written list of names: the defect this
    #: catches is exactly "the declaration says one thing and the tool
    #: assumed another", so a second list of names would be a second thing
    #: to keep in step.
    #:
    #: `string` in the declared types is the exemption that matters. A
    #: binding IS a string, so an attribute that legitimately accepts one —
    #: `common.onclick`, `common.gravity`, `Collection.insets` — must not be
    #: reported here. Only an attribute that can accept no string at all is
    #: unambiguously receiving something undeclared.
    def self.binding_disallowed_by_declaration?(definition)
      return false unless definition.is_a?(Hash)

      types = Array(definition['type']).map(&:to_s)
      types.include?('array') && !types.include?('binding') && !types.include?('string')
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
        case JsonUIShared::EnumSpelling.lowered(component['orientation'], 'View', 'orientation')
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

    # An attribute declared `warn_outside_mode` is read by its mode alone, and
    # a layout that writes it elsewhere expects something that does not
    # happen — so it is named, a WARNING, not the usual INFO:
    # `touchDisabledState` is UIKit's hit-test mode, and SwiftUI read any
    # value of it as "stop everything" until jsonui-cli 1.9.0.
    def add_outside_mode_warning(attr_name, attr_def, component_type)
      modes = Array(attr_def['mode']).map { |m| m == 'uikit' ? 'UIKit' : m.capitalize }
      add_warning("Attribute '#{attr_name}' in '#{component_type}' is #{modes.join('/')} only — " \
                  "#{attr_def['description']}")
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
