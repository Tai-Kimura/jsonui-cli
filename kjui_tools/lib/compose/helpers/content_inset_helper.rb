# frozen_string_literal: true

require_relative 'bound_value'

module KjuiTools
  module Compose
    module Helpers
      # `contentInsetAdjustmentBehavior` for the Compose scrollables.
      #
      # The attribute is UIKit's, and it names something Compose does not
      # have: UIScrollView adjusts its content inset for the safe area BY
      # DEFAULT, and the attribute decides whether to stop it. Compose has no
      # automatic adjustment at all — a LazyColumn insets its content only if
      # you hand it a `contentPadding`.
      #
      # So the concept does not port, but the EFFECT does, and it is the
      # effect the declaration is about: whether the scrolled content clears
      # the system bars. `WindowInsets.safeDrawing.asPaddingValues()` is
      # exactly the value UIKit would have computed, and `contentPadding` is
      # the argument kjui already passes for the numeric spelling
      # (collection_component.rb, table_component.rb).
      #
      # Which way each value falls is therefore inverted from iOS:
      #
      #   never          -> emit nothing. Compose's default IS "no adjustment",
      #                     so this is the one value that needs no code, where
      #                     on iOS it is the only value that does.
      #   always         -> the full safe-area inset.
      #   automatic      -> the same. Compose has no "depending on context".
      #   scrollableAxes -> the inset on the scrolled axis only.
      #
      # Emitting nothing for `never` is also what keeps every existing Compose
      # screen exactly where it is: they have all been running with no inset,
      # which is what `never` means (plan 49 lane C, #4).
      module ContentInsetHelper
        module_function

        FULL = 'WindowInsets.safeDrawing.asPaddingValues()'

        # PaddingValues expression, or nil when nothing should be emitted.
        # `horizontal:` picks the axis for `scrollableAxes`.
        def safe_area_padding(value, horizontal: false)
          case value.to_s.downcase
          when 'always', 'automatic'
            FULL
          when 'scrollableaxes'
            side = horizontal ? 'Horizontal' : 'Vertical'
            "WindowInsets.safeDrawing.only(WindowInsetsSides.#{side}).asPaddingValues()"
          end
        end

        # True when this declaration asks for an inset the caller has to emit.
        def adjusts?(value)
          !safe_area_padding(value).nil?
        end

        # The import keys the emitted text needs, or [] when it emits nothing.
        def imports_for(value)
          return [] unless adjusts?(value)

          keys = %i[window_insets]
          keys << :window_insets_sides if value.to_s.downcase == 'scrollableaxes'
          keys
        end
      end
    end
  end
end
