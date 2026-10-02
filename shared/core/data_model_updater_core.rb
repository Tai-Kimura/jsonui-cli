# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative 'layout_variant'
require_relative 'type_synonyms'
require_relative 'data_item_platform'
require_relative 'data_class_conflict'

module JsonUIShared
  # Shared body of the sjui/kjui Data-model updaters: walks every layout
  # JSON, extracts the data contract (data[] properties, event bindings,
  # onclick actions, auto-focus props), enforces project-wide basename
  # uniqueness, and drives the per-platform Data file writer. Canonical
  # copy lives in shared/core/data_model_updater_core.rb; the per-tool
  # copies under <tool>/lib/core/ must stay byte-identical (pinned by each
  # tool's shared_core_mirror_spec — same contract as layout_validator).
  #
  # The platform halves stay in the tool profile
  # (<tool>/lib/{swiftui,compose}/data_model_updater.rb): the profile owns
  # its constructor (config, directory layout, mode) and implements the
  # hooks below. Everything that emits Swift/Kotlin text lives there.
  #
  #   skip_layout_file_extra?(file)   extra per-platform layout filters
  #                                   (sjui skips "mode": "uikit" files)
  #   expand_styles(json, file)       StyleLoader.load_and_merge — per-tool API
  #   expand_includes(json, dir)      IncludeExpander.process_includes
  #   event_binding_attrs             which attributes create event bindings
  #                                   (kjui also listens to legacy 'onclick')
  #   onclick_action_name(node)       the onclick callback-name convention
  #                                   (sjui: onClick as @{fn}; kjui: bare onclick)
  #   data_platform_filter            data[] platform tag this tool accepts
  #   data_mode_filter                data[] mode tag this tool accepts
  #   boolean_class                   'Bool' / 'Boolean' for the auto focus prop
  #   finalize_data_property(item, b) Event-type conversion + TypeConverter
  #                                   normalization — ORDER differs per
  #                                   platform on purpose (sjui converts
  #                                   Event before normalizing to avoid
  #                                   double-wrapping; kjui normalizes first)
  #   data_file_extension             'swift' / 'kt'
  #   extract_type_name(content)      pull the existing struct/data-class name
  #   generate_data_content(...)      the platform emitter
  #
  # Unified 2026-08-01 (W3-2, file 2). Divergences resolved toward the
  # correct side:
  #   - duplicate data[] property names are dropped on every platform
  #     (was kjui-only; sjui emitted duplicate struct fields — invalid Swift)
  #   - data as a Hash (style-provided simple objects) is accepted on every
  #     platform with type inference (was kjui-only)
  #   - a data[] item must carry a 'name' to count (was kjui-only)
  #   - the Collection cellIdProperty + scrollTo type override ran on every
  #     platform; it is gone (4f round 15, jsonui-cli 1.9.0): a scrollTo's
  #     declared class says what the value names (the SSoT's
  #     Collection.scrollTo), and cellIdProperty does not change it
  #   - onToggle joins the event-binding attributes and normalizes to
  #     onValueChange on Switch/Toggle so type_mapping.json (keyed on
  #     onValueChange) resolves — was sjui-only, kjui onToggle handlers
  #     never got their Event signature resolved
  #   - Resources/ is skipped at any depth (sjui matched only the top-level
  #     folder), and incremental updates + progress counts (kjui) are
  #     available everywhere
  class DataModelUpdaterCore
    def update_data_models(files_to_update = nil)
      # Uniqueness is a project-wide invariant, so check the full glob
      # even on incremental (files_to_update) runs.
      all_json_files = Dir.glob(File.join(@layouts_dir, '**/*.json')).reject do |file|
        # Skip Resources and Styles folders (styles don't need data models)
        # and responsive variant files (data contract is base-canonical)
        next true if file.include?('/Resources/') || file.include?('/Styles/') ||
                     JsonUIShared::LayoutVariant.variant?(file)
        skip_layout_file_extra?(file)
      end
      ensure_unique_layout_basenames!(all_json_files)

      # If specific files provided, only update those
      if files_to_update && !files_to_update.empty?
        puts "  Updating data models for #{files_to_update.length} modified files..."
        files_to_update.each do |json_file|
          process_json_file(json_file)
        end
      else
        puts "  Updating data models for #{all_json_files.length} files..."
        all_json_files.each do |json_file|
          process_json_file(json_file)
        end
      end
    end

    # Data models are written as <Basename>Data files into a single flat
    # directory/package (with no directory namespacing), so layout
    # basenames must be unique project-wide. A silent last-write-wins
    # overwrite corrupts the earlier screen's Data model, so duplicates
    # abort the build. Mirrors the identical check in rjui.
    def ensure_unique_layout_basenames!(json_files)
      duplicates = json_files.group_by { |f| File.basename(f) }
                             .select { |_, files| files.size > 1 }
      return if duplicates.empty?

      details = duplicates.map do |base, files|
        rels = files.map { |f| f.sub(%r{\A#{Regexp.escape(@layouts_dir)}/?}, '') }.sort
        "  #{base}: #{rels.join(', ')}"
      end
      abort(
        "ERROR: duplicate layout file name(s) detected.\n" \
        "Data models are generated as <Name>Data files into a single directory/package " \
        "on every platform (TypeScript/Swift/Kotlin), so layout basenames must be unique " \
        "project-wide even across subdirectories — otherwise the last one processed " \
        "silently overwrites the others. Rename one file of each pair (and its references):\n" +
        details.join("\n")
      )
    end

    private

    # ---- platform profile hooks (implemented by the per-tool subclass) ----

    def skip_layout_file_extra?(_file)
      false
    end

    def expand_styles(_json_data, _json_file)
      raise NotImplementedError, 'platform profile must define expand_styles'
    end

    def expand_includes(_json_data, _dir)
      raise NotImplementedError, 'platform profile must define expand_includes'
    end

    def event_binding_attrs
      raise NotImplementedError, 'platform profile must define event_binding_attrs'
    end

    def onclick_action_name(_node)
      raise NotImplementedError, 'platform profile must define onclick_action_name'
    end

    def data_platform_filter
      raise NotImplementedError, 'platform profile must define data_platform_filter'
    end

    def data_mode_filter
      raise NotImplementedError, 'platform profile must define data_mode_filter'
    end

    def boolean_class
      raise NotImplementedError, 'platform profile must define boolean_class'
    end

    def finalize_data_property(_data_item, _event_bindings)
      raise NotImplementedError, 'platform profile must define finalize_data_property'
    end

    def data_file_extension
      raise NotImplementedError, 'platform profile must define data_file_extension'
    end

    def extract_type_name(_content)
      raise NotImplementedError, 'platform profile must define extract_type_name'
    end

    def generate_data_content(_view_name, _data_properties, _onclick_actions, json_base_name: nil)
      raise NotImplementedError, 'platform profile must define generate_data_content'
    end

    # -----------------------------------------------------------------------

    def process_json_file(json_file)
      # The layout a warning about one of its data properties names
      # (finalize_data_property passes it to the TypeConverter).
      @current_layout = @layouts_dir ? json_file.sub(%r{\A#{Regexp.escape(@layouts_dir)}/?}, '') : json_file
      json_content = File.read(json_file)
      json_data = JSON.parse(json_content)

      # Skip partial files (they are included in other views, not standalone)
      if json_data['partial'] == true
        return
      end

      # Expand styles before extracting data and actions
      expanded_data = expand_styles(json_data, json_file)

      # Expand includes inline with ID prefixes
      expanded_data = expand_includes(expanded_data, File.dirname(json_file))

      # Extract event bindings (handler name => component/attribute info)
      event_bindings = extract_event_bindings(expanded_data)

      # Extract data properties from expanded JSON (pass event_bindings for Event type conversion)
      @declared_data_properties = {}.compare_by_identity
      @data_class_conflicts = JsonUIShared::DataClassConflict.new(@current_layout)
      data_properties = extract_data_properties(expanded_data, [], event_bindings)

      # A scrollTo's class is the one its data declares: cellIdProperty
      # decides what a key is, not what the value is (4f round 15; the SSoT's
      # Collection.scrollTo). Until jsonui-cli 1.9.0 a Collection with
      # cellIdProperty and scrollTo had its data's `PassthroughSubject<Int`
      # rewritten to `PassthroughSubject<String` here.

      # Extract onclick actions from expanded JSON
      onclick_actions = extract_onclick_actions(expanded_data)

      # Collect all view IDs and check for conflicts with data property names
      view_ids = collect_view_ids(expanded_data)
      check_id_data_conflicts(json_file, view_ids, data_properties)

      # Always create/update data file, even if no properties
      # Get the view name from file path
      base_name = File.basename(json_file, '.json')

      # Update the Data model file (always in root Data directory)
      update_data_file(base_name, data_properties, onclick_actions)
    end

    # The properties a data[] item declared, by identity — a name the walk
    # made up (the <id>IsFocused and Radio group properties) is not a
    # declaration, and a declaration it shadows is not this check's.
    def declared_data_properties
      @declared_data_properties ||= {}.compare_by_identity
    end

    # A later data[] item naming a declared property with another type. The
    # types compared are the ones this face writes: the dropped item goes
    # through finalize_data_property like the kept one did, without its
    # defaultValue — defaults are not compared, and a default's own warnings
    # belong to the declaration that is kept.
    def report_data_class_conflict(kept, data_item, event_bindings)
      return unless declared_data_properties.key?(kept)

      dropped = finalize_data_property(data_item.reject { |key, _| key == 'defaultValue' }, event_bindings)
      @data_class_conflicts ||= JsonUIShared::DataClassConflict.new(@current_layout)
      @data_class_conflicts.report(kept['name'], kept['class'], dropped['class'])
    end

    # Collect all 'id' values from the JSON tree (converted to camelCase)
    def collect_view_ids(json_data, ids = Set.new)
      return ids unless json_data.is_a?(Hash) || json_data.is_a?(Array)

      if json_data.is_a?(Hash)
        if json_data['id']
          ids << snake_to_camel(json_data['id'])
        end
        child = json_data['child']
        if child.is_a?(Array)
          child.each { |c| collect_view_ids(c, ids) }
        elsif child
          collect_view_ids(child, ids)
        end
        # Check header/footer/cell in Collections
        %w[header footer cell].each do |key|
          collect_view_ids(json_data[key], ids) if json_data[key]
        end
      elsif json_data.is_a?(Array)
        json_data.each { |item| collect_view_ids(item, ids) }
      end

      ids
    end

    # Warn if any data property name conflicts with a view ID
    def check_id_data_conflicts(json_file, view_ids, data_properties)
      data_names = data_properties.map { |p| p['name'] }
      conflicts = data_names & view_ids.to_a
      return if conflicts.empty?

      file_name = File.basename(json_file)
      conflicts.each do |name|
        puts "\e[33m  WARNING: #{file_name}: data property '#{name}' conflicts with a view ID. Add a suffix to the view ID (e.g., '#{name}_view', '#{name}_label', '#{name}_container').\e[0m"
      end
    end

    # Extract event bindings from JSON to map handler names to component/attribute
    # Used for converting Event type to platform-specific types
    # @param json_data [Hash] the JSON data
    # @param bindings [Hash] accumulated bindings (handler_name => { component:, attribute: })
    # @return [Hash] event bindings
    def extract_event_bindings(json_data, bindings = {})
      return bindings unless json_data.is_a?(Hash) || json_data.is_a?(Array)

      if json_data.is_a?(Hash)
        # The type the node is drawn as (a synonym or alias spelling maps to
        # the handler types of what draws it — type_synonyms.rb)
        component_type = JsonUIShared::TypeSynonyms.drawn_type(json_data['type'])

        event_binding_attrs.each do |attr|
          value = json_data[attr]
          next unless value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

          handler_name = value[2...-1]
          # onToggle is an alias of onValueChange on Switch (Toggle is drawn
          # as Switch). Normalize so type_mapping.json (keyed on
          # onValueChange) resolves correctly.
          normalized_attr = attr
          if attr == 'onToggle' && component_type == 'Switch'
            normalized_attr = 'onValueChange'
          end
          bindings[handler_name] = {
            component: component_type,
            attribute: normalized_attr
          }
        end

        # Process children
        child = json_data['child']
        if child.is_a?(Array)
          child.each { |c| extract_event_bindings(c, bindings) }
        elsif child
          extract_event_bindings(child, bindings)
        end
      elsif json_data.is_a?(Array)
        json_data.each { |item| extract_event_bindings(item, bindings) }
      end

      bindings
    end

    def extract_onclick_actions(json_data, actions = Set.new)
      if json_data.is_a?(Hash)
        action_name = onclick_action_name(json_data)
        actions.add(action_name) if action_name

        # Process children
        if json_data['child']
          if json_data['child'].is_a?(Array)
            json_data['child'].each do |child|
              extract_onclick_actions(child, actions)
            end
          else
            extract_onclick_actions(json_data['child'], actions)
          end
        end
      elsif json_data.is_a?(Array)
        json_data.each do |item|
          extract_onclick_actions(item, actions)
        end
      end

      actions.to_a
    end

    def extract_data_properties(json_data, properties = [], event_bindings = {})
      if json_data.is_a?(Hash)
        # Check for data section at any level and collect ALL data definitions
        if json_data['data']
          if json_data['data'].is_a?(Array)
            json_data['data'].each do |data_item|
              next unless data_item.is_a?(Hash) && data_item['name']

              # Platform/mode filter: skip if not matching. The platform is
              # read as `jui build` reads it (DataItemPlatform: any of the
              # platform's tokens, comma-separated) — until jsonui-cli 1.9.0
              # only a value equal to data_platform_filter was this tool's.
              next unless JsonUIShared::DataItemPlatform.applies?(data_item, data_platform_filter)
              if data_item['mode']
                next unless data_item['mode'] == data_mode_filter
              end

              # Check if property already exists (by name) to avoid duplicate
              # fields in the generated Data type. The first declaration is
              # kept; a later one with another type is said out loud
              # (data_class_conflict.rb — silent until jsonui-cli 1.9.6).
              kept = properties.find { |p| p['name'] == data_item['name'] }
              if kept
                report_data_class_conflict(kept, data_item, event_bindings)
                next
              end

              property = finalize_data_property(data_item, event_bindings)
              declared_data_properties[property] = true
              properties << property
            end
          elsif json_data['data'].is_a?(Hash)
            # Handle simple data object format from styles
            json_data['data'].each do |name, value|
              unless properties.any? { |p| p['name'] == name }
                # Infer type from value
                class_type = if value.is_a?(Integer)
                  'Int'
                elsif value.is_a?(Float)
                  'Float'
                elsif value.is_a?(TrueClass) || value.is_a?(FalseClass)
                  boolean_class
                else
                  'String'
                end

                properties << {
                  'name' => name,
                  'class' => class_type,
                  'defaultValue' => value
                }
              end
            end
          end
        end

        # Auto-generate the <id>IsFocused property for a node drawn as a
        # TextField / TextView — the aliases (EditText, Input) and the
        # synonyms (Textarea, MultiLineEditText) included, by the type they
        # are drawn as (type_synonyms.rb): the platform TextField/TextView
        # converters emit data.<id>IsFocused focus wiring for every component
        # with an id, so the Data type must carry it.
        if %w[TextField TextView].include?(JsonUIShared::TypeSynonyms.drawn_type(json_data['type'])) && json_data['id']
          focus_prop_name = snake_to_camel(json_data['id']) + 'IsFocused'
          unless properties.any? { |p| p['name'] == focus_prop_name }
            properties << { 'name' => focus_prop_name, 'class' => boolean_class, 'defaultValue' => false }
          end
        end

        # Auto-generate the group-selection property for Radio components
        # without a bound selectedValue — same contract as the focus props
        # above: the Compose converter emits `data.selected<Group>` wiring
        # for every radio item, so the Data type must carry the property or
        # the generated view does not compile (caught by the codegen parity
        # host on the Radio fixtures, 2026-08-02). Group 'default' (or no
        # group) maps to selectedRadiogroup — the converter's spelling.
        if JsonUIShared::TypeSynonyms.drawn_type(json_data['type']) == 'Radio'
          selected_value = json_data['selectedValue']
          unless selected_value.is_a?(String) && selected_value.start_with?('@{')
            group = (json_data['group'] || 'default').to_s
            prop = group.downcase == 'default' ? 'selectedRadiogroup' : "selected#{group.capitalize}"
            unless properties.any? { |p| p['name'] == prop }
              properties << { 'name' => prop, 'class' => 'String', 'defaultValue' => '' }
            end
          end
        end

        # Process children
        if json_data['child']
          if json_data['child'].is_a?(Array)
            json_data['child'].each do |child|
              extract_data_properties(child, properties, event_bindings)
            end
          else
            extract_data_properties(json_data['child'], properties, event_bindings)
          end
        end
      elsif json_data.is_a?(Array)
        json_data.each do |item|
          extract_data_properties(item, properties, event_bindings)
        end
      end

      properties
    end

    def update_data_file(base_name, data_properties, onclick_actions = [])
      # Convert base_name to PascalCase for searching
      pascal_view_name = to_pascal_case(base_name)

      # Check for existing file with different casing
      existing_file = find_existing_data_file(pascal_view_name)

      if existing_file
        # Extract the actual type name from the existing file
        existing_type_name = extract_type_name(File.read(existing_file))
        if existing_type_name
          # Use the exact type name from the existing file
          view_name = existing_type_name.sub(/Data$/, '')
        else
          # Fallback to pascal case if we can't extract the name
          view_name = pascal_view_name
        end
        data_file_path = existing_file
      else
        # For new files, use pascal case
        view_name = pascal_view_name
        data_file_path = File.join(@data_dir, "#{view_name}Data.#{data_file_extension}")
        # If file doesn't exist, create it with empty data structure
        unless File.exist?(data_file_path)
          # Create directory if needed
          FileUtils.mkdir_p(@data_dir)
        end
      end

      # Generate new content
      content = generate_data_content(view_name, data_properties, onclick_actions, json_base_name: base_name)

      # Write the updated content
      File.write(data_file_path, content)
      puts "  Updated Data model: #{data_file_path}"
    end

    def find_existing_data_file(view_name)
      # Try exact match first
      exact_path = File.join(@data_dir, "#{view_name}Data.#{data_file_extension}")
      return exact_path if File.exist?(exact_path)

      # Try case-insensitive search
      Dir.glob(File.join(@data_dir, "*Data.#{data_file_extension}")).find do |file|
        File.basename(file, ".#{data_file_extension}").downcase == "#{view_name}data".downcase
      end
    end

    # Convert snake_case id to lowerCamelCase (e.g. "two_fa_hidden_input" -> "twoFaHiddenInput")
    def snake_to_camel(str)
      parts = str.split('_')
      parts[0] + parts[1..].map(&:capitalize).join
    end

    def to_pascal_case(str)
      # Handle various naming patterns
      snake = str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
                 .gsub(/([a-z\d])([A-Z])/, '\1_\2')
                 .downcase
      snake.split(/[_\-]/).map(&:capitalize).join
    end
  end
end
