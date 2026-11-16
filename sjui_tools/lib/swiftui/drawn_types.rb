# frozen_string_literal: true

require_relative '../core/type_synonyms'

module SjuiTools
  module SwiftUI
    # Whether a node is drawn as a Collection / a ScrollView — asked by the
    # passes that look for those nodes before anything is drawn (the build's
    # warnings, the scrolling-ancestor stamp, the cell indexes), so they agree
    # with the converter factory. The factory draws a node by its type as
    # written, resolved through the type synonyms and the declared alias
    # sections (TypeSynonyms.canonicalize, then `when 'Collection'`), so a
    # `List` or a `Table` is a Collection there and here, and a "collection"
    # (another case) is neither (jsonui-cli 1.9.0: a type name is its
    # declared spelling).
    module DrawnTypes
      module_function

      def collection?(type)
        JsonUIShared::TypeSynonyms.section(type) == 'Collection'
      end

      def scroll_view?(type)
        JsonUIShared::TypeSynonyms.section(type) == 'ScrollView'
      end
    end
  end
end
