# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative 'layout_variant'

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
  #   - the Collection cellIdProperty + scrollTo type override runs on every
  #     platform (string-level no-op on Kotlin today — its scroll types don't
  #     match the rewritten spelling; kotlin-side parity is a type_converter
  #     follow-up)
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
      data_properties = extract_data_properties(expanded_data, [], event_bindings)

      # Scan for collections with cellIdProperty + scrollTo to override scrollTo type
      override_scroll_to_types(expanded_data, data_properties)

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
        component_type = json_data['type']

        event_binding_attrs.each do |attr|
          value = json_data[attr]
          next unless value.is_a?(String) && value.start_with?('@{') && value.end_with?('}')

          handler_name = value[2...-1]
          # onToggle is an alias of onValueChange on Switch/Toggle.
          # Normalize so type_mapping.json (keyed on onValueChange) resolves correctly.
          normalized_attr = attr
          if attr == 'onToggle' && %w[Switch Toggle].include?(component_type)
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

    # Scan layout for Collection components with cellIdProperty + scrollTo
    # and override the matching data property type from the Int-keyed scroll
    # publisher to the String-keyed one (cell ids are strings). The rewrite
    # targets the sjui Combine spelling; on Kotlin it is a string-level
    # no-op today — kotlin-side parity is a type_converter follow-up.
    def override_scroll_to_types(json_data, data_properties)
      scroll_to_props = collect_string_scroll_to_props(json_data)
      return if scroll_to_props.empty?

      data_properties.each do |prop|
        if scroll_to_props.include?(prop['name'])
          prop['class'] = prop['class'].to_s.gsub('PassthroughSubject<Int', 'PassthroughSubject<String')
        end
      end
    end

    # Recursively find scrollTo property names that need String type (cellIdProperty is set)
    def collect_string_scroll_to_props(json_data, result = Set.new)
      return result unless json_data.is_a?(Hash) || json_data.is_a?(Array)

      if json_data.is_a?(Hash)
        if json_data['type'] == 'Collection' && json_data['cellIdProperty'] && json_data['scrollTo']
          scroll_to = json_data['scrollTo']
          if scroll_to.is_a?(String) && scroll_to.start_with?('@{') && scroll_to.end_with?('}')
            prop_name = scroll_to[2...-1]
            result.add(prop_name)
          end
        end

        child = json_data['child']
        if child.is_a?(Array)
          child.each { |c| collect_string_scroll_to_props(c, result) }
        elsif child
          collect_string_scroll_to_props(child, result)
        end
      elsif json_data.is_a?(Array)
        json_data.each { |item| collect_string_scroll_to_props(item, result) }
      end

      result
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

              # Platform/mode filter: skip if not matching
              if data_item['platform']
                next unless data_item['platform'] == data_platform_filter
              end
              if data_item['mode']
                next unless data_item['mode'] == data_mode_filter
              end

              # Check if property already exists (by name) to avoid duplicate
              # fields in the generated Data type
              next if properties.any? { |p| p['name'] == data_item['name'] }

              properties << finalize_data_property(data_item, event_bindings)
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

        # Auto-generate the <id>IsFocused property for TextField / TextView
        # components (EditText / Input are aliases for TextField —
        # attribute_definitions `_alias_of: TextField`): the platform
        # TextField/TextView converters emit data.<id>IsFocused focus wiring
        # for every component with an id, so the Data type must carry it.
        if %w[TextField EditText Input TextView].include?(json_data['type']) && json_data['id']
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
        if json_data['type'] == 'Radio'
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
