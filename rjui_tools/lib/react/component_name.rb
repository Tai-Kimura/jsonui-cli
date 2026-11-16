# frozen_string_literal: true

module RjuiTools
  module React
    # The component a layout reference names — a cell / header / footer class
    # (`cellClasses`, `headerClasses`, `footerClasses`, `sections[].cell` …):
    # the last path segment, kept as written when it is already PascalCase,
    # otherwise snake_case joined into PascalCase.
    #
    # One rule for the three places that spell the name: the import
    # (ReactGenerator#extract_included_components), the cell Data type
    # (ReactGenerator#extract_collection_cell_types) and the JSX element
    # (CollectionConverter#extract_view_name). Until 1.9.0 the JSX side ran
    # its own UIKit-migration heuristics — `HeaderCell` became
    # `<HeaderCellView/>` under `import HeaderCell …`, which tsc refuses
    # (ticket collection-attributes-declared-but-not-drawn-on-some-paths).
    module ComponentName
      module_function

      def for_reference(reference)
        name = reference.is_a?(Hash) ? reference['className'] : reference
        return nil unless name.is_a?(String) && !name.empty?

        base = name.split('/').last
        return base if base.match?(/^[A-Z]/) && !base.include?('_')

        base.split('_').map(&:capitalize).join
      end
    end
  end
end
