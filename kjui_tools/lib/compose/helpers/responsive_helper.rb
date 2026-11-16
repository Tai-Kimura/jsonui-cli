# frozen_string_literal: true

require_relative '../../core/responsive_resolver'

module KjuiTools
  module Compose
    module Helpers
      # Detects components with `responsive` blocks.
      #
      # This class once also generated extracted responsive wrapper
      # @Composables (generate_container_wrapper / generate_leaf_wrapper /
      # build_if_else_chain), but that extraction path was structurally wrong
      # — the file-scope helper lost the enclosing GeneratedView's
      # `data`/`viewModel` scope and the caller's Row/Column/Box scope (bug
      # reports: kjui-view-responsive-helper-data-closure-scope-leak,
      # kjui-responsive-helper-wraps-with-box-loses-row-column-scope). All
      # live responsive emission is the inline if/else path in
      # ComposeBuilder (generate_*_responsive_inline), which owns its own
      # condition tables. The dead generators were removed 2026-07-03.
      class ResponsiveHelper
        # Check if a component has responsive overrides
        def self.responsive?(component)
          JsonUIShared::ResponsiveResolver.responsive?(component)
        end
      end
    end
  end
end
