# frozen_string_literal: true

require 'json'
require_relative 'attribute_validator_core'

module JsonUIShared
  # Build-time consistency checks for Layout JSON trees. Called by the
  # sjui / kjui / rjui builders so every platform emits the same warnings.
  module LayoutValidator
    module_function

    # Returns an Array of { level:, message:, location: } warning Hashes for
    # a single node (usually a Collection component).
    def check_collection(component, source_path:)
      warnings = []
      auto_tracking = component['autoChangeTrackingId'] == true
      cell_id_prop = component['cellIdProperty']

      if auto_tracking && (cell_id_prop.nil? || cell_id_prop.to_s.empty?)
        component_id = component['id'] ? " (id=#{component['id']})" : ''
        warnings << {
          level: :warning,
          message: "Collection#{component_id} has autoChangeTrackingId=true but cellIdProperty is not set. " \
                   'Auto cellId generation is disabled; cells will fall back to index-based identity. ' \
                   'Fix: add "cellIdProperty": "id" (or the field that uniquely identifies a row).',
          location: source_path
        }
      end

      # Several cell layouts, and no `sections` to say which goes where.
      #
      # SSoT (`/Collection/cellClasses`): with `items` and no `sections`, ONE
      # declared cell layout renders every item. All three faces implement
      # that by taking `cellClasses.first` — kjui `cell_classes.first`, rjui
      # `cell_classes.first`, sjui the same — so declaring several renders the
      # first and drops the rest silently, on every face.
      #
      # Rendering the first is a guess at which one the author meant, and a
      # silent guess is the shape that cost a whole night elsewhere in this
      # corpus: the layout looks accepted and the output is wrong. The
      # declaration is refused instead, naming the count and the fix.
      cell_classes = component['cellClasses'] || []
      sections = component['sections'] || []
      if cell_classes.length > 1 && sections.empty?
        component_id = component['id'] ? " (id=#{component['id']})" : ''
        warnings << {
          level: :error,
          message: "Collection#{component_id}: #{cell_classes.length} cellClasses " \
                   'declared without sections — only the first would render. ' \
                   'Fix: assign cells via sections[].cell, or declare a single cellClass.',
          location: source_path
        }
      end

      warnings
    end

    #: A binding where the declaration takes a list and never a string.
    #:
    #: `Collection.sections` is declared `type: array` with no binding, and
    #: `"@{secs}"` reached the converters as a String: rjui, sjui and kjui
    #: each call `.each_with_index` / `.any?` on it, so the screen died with
    #: `NoMethodError: undefined method 'each' for "@{secs}":String` — the
    #: failure furthest from the cause, and a different exception depending
    #: on which converter ran first. Reported here, before conversion, so
    #: the layout is refused by name instead.
    #:
    #: The population comes from the declaration (43 attributes), never a
    #: list of names: the defect IS "the tool assumed something the
    #: declaration does not say", so a second list would be a second thing
    #: to keep in step. `string` in the declared types is the exemption that
    #: matters — a binding is a string, so `common.onclick`, `common.gravity`
    #: and four others legitimately take one and must not be reported.
    def check_undeclared_bindings(component, source_path:)
      component_type = component['type']
      return [] unless component_type.is_a?(String)

      # `each_with_object`, not `filter_map`: consumers run this on system
      # ruby 2.6, where `Hash#filter_map` does not exist.
      component.each_with_object([]) do |(name, value), found|
        next unless value.is_a?(String)

        stripped = value.strip
        next unless stripped.start_with?('@{') && stripped.end_with?('}')

        definition = attribute_definition(component_type, name)
        next unless AttributeValidatorCore.binding_disallowed_by_declaration?(definition)

        component_id = component['id'] ? " (id=#{component['id']})" : ''
        declared = Array(definition['type']).map(&:to_s).join(', ')
        found << {
          level: :error,
          message: "#{component_type}#{component_id}: '#{name}' is a binding, but the " \
                   "declaration is type: #{declared} with no binding — the generators " \
                   "receive the string itself and cannot iterate it. " \
                   "Fix: pass a literal list, or declare the attribute binding-capable.",
          location: source_path
        }
      end
    end

    #: Component-specific declaration first, then `common`. Mirrors how the
    #: attribute validator resolves a key, so both agree about which
    #: declaration governs an attribute.
    def attribute_definition(component_type, name)
      defs = definitions
      component_defs = defs[component_type]
      found = component_defs.is_a?(Hash) ? component_defs[name] : nil
      return found if found.is_a?(Hash)

      common = defs['common']
      common.is_a?(Hash) ? common[name] : nil
    end

    def definitions
      @definitions ||= begin
        path = File.join(File.dirname(__FILE__), 'attribute_definitions.json')
        File.exist?(path) ? JSON.parse(File.read(path)) : {}
      end
    end

    #: Children given to a component whose definition says it takes none.
    #:
    #: `g converter <Name> --no-container` scaffolds a component with no
    #: content slot, and every generated reading of it drops a layout's
    #: children without a word: sjui and rjui emit the call without them,
    #: the Dynamic adapter never reads them, and kjui's call fails kotlinc on
    #: the generated line rather than on the layout (measured on 1.8.120 /
    #: e1a85ca2). Children that are not drawn are a missing part of the
    #: screen, so the layout is refused by name, as several cellClasses
    #: without sections are.
    #:
    #: Only a DECLARED leaf (`"_children": "none"`, which the generator
    #: writes). A definition without `child` is not one: before 1.8.121 the
    #: default mode wrote none either, and those components draw children.
    #: They keep the attribute validator's "Unknown attribute 'child'".
    def check_leaf_children(component, source_path:, extension_definitions:, path: nil)
      component_type = component['type']
      return [] unless component_type.is_a?(String) && extension_definitions.is_a?(Hash)

      definition = extension_definitions[component_type]
      return [] unless definition.is_a?(Hash) &&
                       definition[AttributeValidatorCore::CHILDREN_DECLARATION] == AttributeValidatorCore::NO_CHILDREN

      dropped = AttributeValidatorCore::CHILD_KEYS.flat_map do |key|
        value = component[key]
        items = value.is_a?(Array) ? value.each_with_index.to_a : (value.is_a?(Hash) ? [[value, nil]] : [])
        # `map` + `compact`, not `filter_map`: consumers run this on the
        # system Ruby 2.6, which has no filter_map.
        items.map do |item, index|
          next unless item.is_a?(Hash) && (item.key?('type') || item.key?('include'))

          label = index ? "#{key}[#{index}]" : key
          label += " (id=#{item['id']})" if item['id']
          label
        end.compact
      end
      return [] if dropped.empty?

      node = component['id'] ? "id=#{component['id']}" : (path || 'root')
      [{
        level: :error,
        message: "'#{component_type}' (#{node}) takes no children — it is declared a leaf " \
                 "(`g converter #{component_type} --no-container`), so #{dropped.join(', ')} " \
                 'would be dropped. Remove the children, or regenerate the component with --container.',
        location: source_path
      }]
    end

    # Walks `layout_json` and returns an aggregated warnings Array for every
    # Collection node found. `extension_definitions` is the project's
    # (AttributeValidator.extension_definitions): without it, a declared leaf
    # is not recognised and its children are not checked.
    def validate_layout(layout_json, source_path:, extension_definitions: nil)
      warnings = []
      walk_with_path(layout_json, nil) do |node, path|
        next unless node.is_a?(Hash)

        warnings.concat(check_undeclared_bindings(node, source_path: source_path))
        warnings.concat(check_collection(node, source_path: source_path)) if node['type'] == 'Collection'
        warnings.concat(check_leaf_children(node, source_path: source_path,
                                                  extension_definitions: extension_definitions, path: path))
      end
      warnings
    end

    #: True when the layout must not be converted. `:warning` keeps its old
    #: behaviour (printed, build carries on); `:error` means the screen is
    #: not generated and the build ends non-zero via the stage ledger.
    def blocking?(warnings)
      Array(warnings).any? { |w| w[:level] == :error }
    end

    # Prints warnings to stderr. Returns the count printed. Callers pass the
    # array produced by validate_layout.
    def print_warnings(warnings, io: $stderr)
      warnings.each do |w|
        prefix = case w[:level]
                 when :warning then "\e[33m[warning]\e[0m"
                 when :error then "\e[31m[error]\e[0m"
                 else "[#{w[:level]}]"
                 end
        io.puts "#{prefix} #{w[:location]}: #{w[:message]}"
      end
      warnings.size
    end

    def walk(node, &block)
      yield node
      case node
      when Hash then node.each_value { |v| walk(v, &block) }
      when Array then node.each { |v| walk(v, &block) }
      end
    end

    # `walk`, with where each value sits ("child[1].child[0]"; nil for the
    # root), so a node without an id can still be named.
    def walk_with_path(node, path, &block)
      yield node, path
      case node
      when Hash
        node.each { |k, v| walk_with_path(v, path ? "#{path}.#{k}" : k.to_s, &block) }
      when Array
        node.each_with_index { |v, i| walk_with_path(v, "#{path}[#{i}]", &block) }
      end
    end
  end
end
