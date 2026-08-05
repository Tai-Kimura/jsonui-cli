# frozen_string_literal: true

require_relative 'bound_value'

module KjuiTools
  module Compose
    module Helpers
      # The `contentMode` vocabulary, shared by Image and NetworkImage.
      #
      # Both components carried their own copy of this `case` (40: "duplicated
      # vocabulary always drifts" — and these two HAD drifted: Image emitted
      # nothing for an unknown mode where NetworkImage fell back to Fit, and
      # only Image's alignment table knew `center`). Neither copy could match a
      # `"@{...}"`, so a bound contentMode froze to each component's default
      # (plan 49 lane C: Image.contentMode, NetworkImage.contentMode).
      #
      # Those two differences are GONE now, and the answer was written down
      # the whole time. `shared/core/attribute_semantics.json#image` records
      # the 2026-08-03 user rulings: the default contentMode is `fit` on every
      # platform, and all three platforms implement the full mapping including
      # the positional modes. So NetworkImage was right about the default and
      # Image was right about `center`, which is why neither could be folded
      # into the other by inspection — and why reading the ruling instead of
      # inspecting was the whole job (plan 49 lane C, #11b).
      module ContentScaleHelper
        module_function

        # The declared default, in one place: `fit` on every platform
        # (attribute_semantics.json#image, 2026-08-03 user ruling).
        DEFAULT_SCALE = 'ContentScale.Fit'

        SCALE_MAPPING = {
          # `fit` is the canonical spelling and was missing from this table —
          # it only ever worked because it fell through to a caller-supplied
          # default that happened to be Fit. NetworkImage supplied one; Image
          # did not, and emitted nothing.
          'fit' => 'ContentScale.Fit',
          'aspectfit' => 'ContentScale.Fit',
          'aspectfill' => 'ContentScale.Crop',
          'fill' => 'ContentScale.FillBounds',
          'scaletofill' => 'ContentScale.FillBounds',
          # Positional modes draw unscaled and aligned (UIKit contentMode
          # positions — mirrors the dynamic component).
          'center' => 'ContentScale.None',
          'top' => 'ContentScale.None',
          'bottom' => 'ContentScale.None',
          'left' => 'ContentScale.None',
          'right' => 'ContentScale.None'
        }.freeze

        ALIGNMENT_MAPPING = {
          'top' => 'Alignment.TopCenter',
          'bottom' => 'Alignment.BottomCenter',
          'left' => 'Alignment.CenterStart',
          'right' => 'Alignment.CenterEnd',
          'center' => 'Alignment.Center'
        }.freeze

        # Kotlin `ContentScale` expression. An unknown value resolves to the
        # declared default rather than to whatever each caller happened to do
        # — Image emitted nothing and NetworkImage `Fit`, for the same input.
        def scale_expression(value, default: DEFAULT_SCALE)
          BoundValue.enum(value, SCALE_MAPPING,
                          default: default,
                          bound_default: default || DEFAULT_SCALE,
                          lowercase: true)
        end

        # Kotlin `Alignment` expression for the positional modes, or nil. The
        # table is the canonical five; `center` was missing from one caller.
        def alignment_expression(value)
          BoundValue.enum(value, ALIGNMENT_MAPPING,
                          bound_default: 'Alignment.Center', lowercase: true)
        end
      end
    end
  end
end
