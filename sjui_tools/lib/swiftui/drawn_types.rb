# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    # The spellings the converter factory draws as a Collection and as a
    # ScrollView, as written — a type name is its declared spelling, case and
    # all (jsonui-cli 1.9.0). The passes that look for those nodes before
    # anything is drawn (the build's warnings, the scrolling-ancestor stamp,
    # the cell indexes) read the same sets, so a node the factory does not
    # draw as one ("collection", "SCROLLVIEW") is not treated as one first.
    # The other synonyms (List, Grid, …) are the normalizer's to rewrite.
    module DrawnTypes
      COLLECTION = %w[Collection Table].freeze
      SCROLL_VIEW = %w[Scroll ScrollView].freeze
    end
  end
end
