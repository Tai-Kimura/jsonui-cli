# frozen_string_literal: true

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

      warnings
    end

    # Walks `layout_json` and returns an aggregated warnings Array for every
    # Collection node found.
    def validate_layout(layout_json, source_path:)
      warnings = []
      walk(layout_json) do |node|
        if node.is_a?(Hash) && node['type'] == 'Collection'
          warnings.concat(check_collection(node, source_path: source_path))
        end
      end
      warnings
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
  end
end
