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
      # The two behavioural differences above are preserved as PARAMETERS
      # rather than silently unified — changing them would move static output,
      # which is out of scope here. They are recorded in the lane report.
      module ContentScaleHelper
        module_function

        SCALE_MAPPING = {
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

        # Kotlin `ContentScale` expression, or nil when nothing should be
        # emitted. `default:` is the caller's own unknown-value behaviour.
        def scale_expression(value, default: nil)
          BoundValue.enum(value, SCALE_MAPPING,
                          default: default,
                          bound_default: default || 'ContentScale.Fit',
                          lowercase: true)
        end

        # Kotlin `Alignment` expression for the positional modes, or nil.
        # `keys:` lets a caller keep a narrower table than the canonical one.
        def alignment_expression(value, keys: ALIGNMENT_MAPPING.keys)
          mapping = ALIGNMENT_MAPPING.select { |k, _| keys.include?(k) }
          BoundValue.enum(value, mapping, bound_default: 'Alignment.Center', lowercase: true)
        end
      end
    end
  end
end
