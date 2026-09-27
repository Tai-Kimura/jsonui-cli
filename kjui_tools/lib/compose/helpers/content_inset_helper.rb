# frozen_string_literal: true

require_relative 'bound_value'
require_relative '../../core/enum_spelling'

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
        #
        # `inset_horizontal:` / `inset_vertical:` (a Collection's
        # insetHorizontal / insetVertical) are added to the safe area, as iOS
        # adds them: measured 2026-09-27 on sjui codegen and SwiftJsonUI
        # Dynamic, a Collection at the top of the safe area with insetVertical
        # 8 put its first cell at the safe area's top + 8 (70 of a 62pt safe
        # area), `always` alike; `never` at 8 (4f ruling, round 16). Until
        # jsonui-cli 1.9.0 kjui dropped the safe area for them and KotlinJsonUI
        # Dynamic dropped them for the safe area.
        def safe_area_padding(value, horizontal: false, inset_horizontal: nil, inset_vertical: nil)
          insets = case JsonUIShared::EnumSpelling.lowered(value, 'ScrollView', 'contentInsetAdjustmentBehavior')
                   when 'always', 'automatic'
                     'WindowInsets.safeDrawing'
                   when 'scrollableaxes'
                     side = horizontal ? 'Horizontal' : 'Vertical'
                     "WindowInsets.safeDrawing.only(WindowInsetsSides.#{side})"
                   end
          return nil unless insets
          return FULL if insets == 'WindowInsets.safeDrawing' && !inset_horizontal && !inset_vertical

          if inset_horizontal || inset_vertical
            h = BoundValue.dp(inset_horizontal || 0)
            v = BoundValue.dp(inset_vertical || 0)
            insets += ".add(WindowInsets(left = #{h}, top = #{v}, right = #{h}, bottom = #{v}))"
          end
          "#{insets}.asPaddingValues()"
        end

        # True when this declaration asks for an inset the caller has to emit.
        def adjusts?(value)
          !safe_area_padding(value).nil?
        end

        # The import keys the emitted text needs, or [] when it emits nothing.
        # `insets:` — the Collection also declares insetHorizontal /
        # insetVertical, added to the safe area (safe_area_padding).
        def imports_for(value, insets: false)
          return [] unless adjusts?(value)

          keys = %i[window_insets]
          keys << :window_insets_add if insets
          keys << :window_insets_sides if JsonUIShared::EnumSpelling.lowered(value, 'ScrollView', 'contentInsetAdjustmentBehavior') == 'scrollableaxes'
          keys
        end
      end
    end
  end
end
