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
      #
      # What `always` adds is the part of the window's safe area the
      # scrollable's frame OVERLAPS — a UIScrollView's safeAreaInsets are its
      # own frame's overlap, so inside a SafeAreaView, or below a header, it is
      # 0. Until jsonui-cli 2.5.40 this emitted the WHOLE window's inset
      # (`WindowInsets.safeDrawing.asPaddingValues()`) wherever the scrollable
      # sat, and a Collection inside a SafeAreaView drew an empty band of the
      # status bar's height above its first row (ticket kjui-collection-
      # content-inset-always-adds-whole-window-insets). The overlap needs the
      # frame, so the emit is KotlinJsonUI's helper (rememberSafeAreaOverlap,
      # the same one KotlinJsonUI's Dynamic calls):
      #
      #   run {
      #       val safeArea = rememberSafeAreaOverlap(<sides>)
      #       LazyColumn(modifier = Modifier…offset….then(safeArea.modifier)…,
      #                  contentPadding = safeArea.contentPadding(<own>)) { … }
      #   }
      #
      # `run` keeps the name to the one scrollable (siblings each have their
      # own) and keeps the parent's scope (weight, align).
      module ContentInsetHelper
        module_function

        NAME = 'safeArea'

        # KotlinJsonUI's first release with rememberSafeAreaOverlap.
        MIN_LIBRARY_VERSION = '2.59.0'

        def behaviour(value)
          JsonUIShared::EnumSpelling.lowered(value, 'ScrollView', 'contentInsetAdjustmentBehavior')
        end

        # PaddingValues expression for the content, or nil when nothing should
        # be emitted. `own` is the scrollable's declared content padding (a
        # PaddingValues expression), added side by side (4f rulings
        # 2026-09-27, rounds 16 and 17).
        def safe_area_padding(value, horizontal: false, own: nil)
          return nil unless adjusts?(value)

          "#{NAME}.contentPadding(#{own})"
        end

        # True when this declaration asks for an inset the caller has to emit.
        def adjusts?(value)
          %w[always automatic scrollableaxes].include?(behaviour(value))
        end

        # The modifier measuring the frame the overlap is computed from: after
        # the margins, the size and the offset (the box drawn), before the
        # padding and the scroll (whose content would move under it).
        def frame_modifiers(value)
          adjusts?(value) ? [".then(#{NAME}.modifier)"] : []
        end

        # The sides argument: the scrolled axis for scrollableAxes, every side otherwise.
        def sides_arg(value, horizontal:)
          return '' unless behaviour(value) == 'scrollableaxes'

          "WindowInsetsSides.#{horizontal ? 'Horizontal' : 'Vertical'}"
        end

        # `code` (one scrollable at `depth`) inside the run block that
        # declares `safeArea`, or `code` unchanged when nothing is adjusted.
        #
        # A component that hands its children to the builder returns
        # { code:, children:, closing: } (ScrollView): the block opens before
        # the code and closes after the closing, and the children the builder
        # draws in between stay at their depth.
        def wrap(code, value, depth, horizontal:)
          return code unless adjusts?(value)

          pad = '    ' * depth
          if code.is_a?(Hash)
            return code.merge(code: "#{pad}// Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (safe-area overlap)\n" \
                                    "#{pad}run {\n#{pad}    val #{NAME} = rememberSafeAreaOverlap(#{sides_arg(value, horizontal: horizontal)})\n" \
                                    "#{code[:code]}",
                              closing: "#{code[:closing]}\n#{pad}}")
          end
          inner = code.split("\n").map { |line| line.empty? ? line : "    #{line}" }.join("\n")
          "#{pad}// Requires KotlinJsonUI >= #{MIN_LIBRARY_VERSION} (safe-area overlap)\n" \
            "#{pad}run {\n#{pad}    val #{NAME} = rememberSafeAreaOverlap(#{sides_arg(value, horizontal: horizontal)})\n" \
            "#{inner}\n#{pad}}"
        end

        # The import keys the emitted text needs, or [] when it emits nothing.
        def imports_for(value)
          return [] unless adjusts?(value)

          keys = %i[safe_area_overlap]
          keys << :window_insets_sides_enum if behaviour(value) == 'scrollableaxes'
          keys
        end
      end
    end
  end
end
